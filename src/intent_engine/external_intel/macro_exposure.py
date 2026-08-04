"""Establish, from THIS company's evidence, which macro factors reach it.

HOW AN EXPOSURE IS ESTABLISHED
-------------------------------
By a phrase in a retrieved document, carrying that document's observation id.
Not by sector, not by the company's name, not by what the model knows about
the company from training.

The test that keeps this honest: masking the company name must not change the
result. If Palantir gets defence exposure because a retrieved filing describes
government contracts, that is evidence. If it gets defence exposure because it
is Palantir, that is the model's prior wearing evidence's clothes -- and it
will produce the same confident sentence for a company that pivoted away from
government work last year.

WHY PHRASE MATCHING RATHER THAN AN LLM CLASSIFIER
--------------------------------------------------
The exposure claim has to be checkable. A phrase match points at the sentence
that triggered it, which is what makes `matched_on` and the evidence id
meaningful on the page: a reader can click through and see the words. A model
judgement would be better at recall and could not be checked, and an unfalsi-
fiable macro claim is the thing this whole contract exists to prevent.

The cost is stated rather than hidden: recall is limited to the vocabulary
below, so a real exposure phrased unusually is MISSED. A missed factor is a
quiet omission; a fabricated one is a wrong decision. This trades the first
for safety from the second.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from .macro_contract import Exposure, MacroRejected

#: Factor keys. One per series the provider can actually serve -- a rule for a
#: factor with no data would produce an exposure that never renders.
PUBLIC_DEFENCE_SPEND = "public_defence_spending"
INTEREST_RATES = "interest_rates"
CONSUMER_PRICES = "consumer_prices"
LABOUR_MARKET = "labour_market"


class _Rule:
    """One exposure mechanism, and the vocabulary that establishes it.

    `triggers` are matched on WORD BOUNDARIES against retrieved evidence text.
    Substring matching would let "credit" fire on "accreditation" and
    "rates" on "corporate rates of growth" -- both seen while calibrating this.
    """

    def __init__(self, factor_key, triggers, mechanism, consequence,
                 decision, min_hits=1):
        self.factor_key = factor_key
        self.triggers = triggers
        self.mechanism = mechanism
        self.consequence = consequence
        self.decision = decision
        self.min_hits = min_hits
        self._patterns = [re.compile(rf"\b{re.escape(t)}\b", re.I)
                          for t in triggers]

    def match(self, texts) -> tuple:
        """(evidence_ids, matched phrase) for the observations that fire."""
        ids, phrases = [], []
        for observation_id, text in texts:
            for pattern, trigger in zip(self._patterns, self.triggers):
                found = pattern.search(text or "")
                if found:
                    if observation_id:
                        ids.append(observation_id)
                    phrases.append(trigger)
                    break
        return list(dict.fromkeys(ids)), phrases


#: The rules. Every mechanism is a sentence about how money actually reaches
#: or leaves the company -- not a restatement of the factor's name.
RULES = (
    _Rule(
        PUBLIC_DEFENCE_SPEND,
        ("government contract", "government contracts", "federal agency",
         "federal agencies", "public sector", "public-sector", "defense",
         "defence", "military", "department of defense", "intelligence "
         "community", "procurement", "gsa", "govcloud", "fedramp",
         "classified"),
        mechanism=(
            "The company sells into government and defence budgets, so the "
            "size of the federal appropriation is the size of the pool its "
            "contracts are awarded from."),
        consequence=(
            "A larger appropriation widens the addressable pool, but public "
            "procurement converts slowly and concentrates revenue in a few "
            "large awards, so growth arrives late and lumpy rather than "
            "smoothly."),
        decision=(
            "Whether to fund specialist public-sector delivery and "
            "accreditation capacity ahead of awards that have not yet been "
            "announced."),
    ),
    _Rule(
        INTEREST_RATES,
        ("interest rate", "interest rates", "borrowing", "credit",
         "lending", "loan", "loans", "financing", "capital markets",
         "debt", "mortgage", "leasing", "working capital", "installment",
         "instalment", "buy now pay later", "merchant cash advance"),
        mechanism=(
            "The company's customers or its own balance sheet depend on "
            "borrowing, so the cost of credit changes what those customers "
            "can afford and what the company can fund."),
        consequence=(
            "Dearer credit compresses customer budgets and lengthens payback "
            "on anything sold as an investment case, which shows up as longer "
            "sales cycles before it shows up in revenue."),
        decision=(
            "Whether to shift pricing toward smaller committed steps, and "
            "whether to fund growth from operating cash rather than debt."),
    ),
    _Rule(
        CONSUMER_PRICES,
        ("consumer spending", "consumer demand", "retail", "merchants",
         "merchant", "shoppers", "discretionary", "basket", "checkout",
         "e-commerce", "ecommerce", "gross merchandise", "shipping costs",
         "input costs", "cost of goods", "freight"),
        mechanism=(
            "The company's revenue tracks what end consumers spend through "
            "its customers, so household purchasing power sets the volume "
            "flowing through the platform."),
        consequence=(
            "Rising prices move household budgets toward essentials and "
            "squeeze the discretionary categories most platform volume comes "
            "from, so take-rate revenue can fall even when the customer count "
            "holds."),
        decision=(
            "Whether to prioritise merchant retention and cost-to-serve over "
            "new-merchant acquisition while volumes are soft."),
    ),
    _Rule(
        LABOUR_MARKET,
        ("hiring", "headcount", "recruiting", "recruitment", "talent",
         "payroll", "workforce", "employees", "staffing", "labour market",
         "labor market", "wage", "wages", "attrition"),
        mechanism=(
            "The company's cost base or its customers' buying behaviour is "
            "tied to employment, so the labour market moves either what it "
            "pays to staff or what its customers are willing to commit to."),
        consequence=(
            "A tight labour market raises the cost of the engineering and "
            "delivery capacity that growth plans assume, so the same plan "
            "costs more than budgeted rather than failing outright."),
        decision=(
            "Whether the hiring plan behind the current growth target is "
            "still affordable at present wage levels."),
    ),
)

RULES_BY_KEY = {rule.factor_key: rule for rule in RULES}


def evidence_texts(observations) -> List[tuple]:
    """(observation_id, text) pairs from a run's retrieved observations."""
    out = []
    for observation in observations or ():
        if not isinstance(observation, dict):
            continue
        # `text_content` is what the ingestion store writes on a retrieved
        # document; `text` is what an observation carries. Reading only the
        # second made every filing body invisible here -- live on the preview,
        # Palantir's 10-Q was retrieved, stored, and never searched for an
        # exposure phrase, so the macro section fell back to "nothing
        # retrieved ties this decision to a macro factor" with the evidence
        # sitting in the run.
        text = " ".join(str(observation.get(field) or "")
                        for field in ("text", "text_content", "quote",
                                      "summary", "title"))
        out.append((observation.get("observation_id") or "", text))
    return out


def find_exposures(observations, *, extra_texts=()) -> List[Exposure]:
    """Every exposure this company's own evidence supports.

    `extra_texts` carries retrieved document bodies that are not observations
    (a filing's business section, say), so a mechanism stated in a 10-Q counts
    -- but only when the document contributes an id a reader can follow.
    """
    texts = evidence_texts(observations) + list(extra_texts or ())
    found = []
    for rule in RULES:
        ids, phrases = rule.match(texts)
        if len(ids) < rule.min_hits or not phrases:
            continue
        try:
            found.append(Exposure(
                factor_key=rule.factor_key, mechanism=rule.mechanism,
                business_consequence=rule.consequence,
                decision_implication=rule.decision,
                evidence_ids=tuple(ids[:4]), matched_on=phrases[0]))
        except MacroRejected:  # pragma: no cover - guarded by min_hits above
            continue
    return found

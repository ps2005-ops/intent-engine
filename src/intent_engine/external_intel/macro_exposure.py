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

    TWO TIERS, AND THE REASON IS A REAL FAILURE. The first version had one
    flat trigger list and fired on any single hit. Shopify's B2B page says
    "procurement workflows and purchase orders", `procurement` was a defence
    trigger, and the deployed product told a commerce company its decision
    turned on US Department of Defense outlays -- with a confident mechanism
    about federal appropriations attached. That is precisely the fabricated,
    unfalsifiable macro claim this whole contract exists to refuse, and a
    keyword did it.

        strong      unambiguous on its own. "department of defense",
                    "government contracts", "fedramp" are not written by
                    accident, and one is enough.
        supporting  real signal, ambiguous alone. "procurement", "military",
                    "credit" appear in ordinary commercial prose. They add
                    evidence to an exposure a strong trigger already
                    established, and can never establish one themselves.

    Matched on WORD BOUNDARIES: substring matching let "credit" fire on
    "accreditation" and "rates" on "corporate rates of growth".
    """

    def __init__(self, factor_key, strong, mechanism, consequence,
                 decision, supporting=()):
        self.factor_key = factor_key
        self.strong = tuple(strong)
        self.supporting = tuple(supporting)
        self.triggers = self.strong + self.supporting
        self.mechanism = mechanism
        self.consequence = consequence
        self.decision = decision
        self._strong_p = [(t, re.compile(rf"\b{re.escape(t)}\b", re.I))
                          for t in self.strong]
        self._support_p = [(t, re.compile(rf"\b{re.escape(t)}\b", re.I))
                           for t in self.supporting]

    def match(self, texts) -> tuple:
        """(evidence_ids, phrases) — empty unless a STRONG trigger fired."""
        strong_ids, support_ids, phrases = [], [], []
        for observation_id, text in texts:
            body = text or ""
            hit = next((t for t, p in self._strong_p if p.search(body)), None)
            if hit:
                if observation_id:
                    strong_ids.append(observation_id)
                phrases.append(hit)
                continue
            weak = next((t for t, p in self._support_p if p.search(body)),
                        None)
            if weak and observation_id:
                support_ids.append(observation_id)
        if not strong_ids:
            # Supporting evidence with nothing to support establishes nothing.
            return [], []
        ids = list(dict.fromkeys(strong_ids + support_ids))
        return ids, phrases


#: The rules. Every mechanism is a sentence about how money actually reaches
#: or leaves the company -- not a restatement of the factor's name.
RULES = (
    _Rule(
        PUBLIC_DEFENCE_SPEND,
        strong=("government contract", "government contracts",
                "federal agency", "federal agencies",
                "department of defense", "department of defence",
                "public sector", "public-sector", "fedramp", "govcloud",
                "intelligence community", "defense department",
                "national security", "federal government"),
        supporting=("procurement", "classified", "gsa", "defense", "defence",
                    "military"),
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
        strong=("interest rate", "interest rates", "borrowing cost",
                "borrowing costs", "cost of capital", "merchant cash advance",
                "buy now pay later", "installment", "instalment", "lending",
                "loan", "loans", "mortgage", "leasing", "capital markets",
                "working capital"),
        supporting=("credit", "financing", "debt", "borrowing"),
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
        strong=("consumer spending", "consumer demand", "merchants",
                "merchant", "shoppers", "gross merchandise", "e-commerce",
                "ecommerce", "retail", "checkout", "discretionary",
                "direct-to-consumer", "storefront"),
        supporting=("basket", "shipping costs", "input costs",
                    "cost of goods", "freight"),
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
        # "hiring" and "employees" are NOT strong: every company hires and
        # every About page names employees, so firing on them would produce
        # the same labour-market paragraph for every company in the product.
        strong=("labour market", "labor market", "wage inflation", "wages",
                "payroll", "attrition", "hiring plan", "staffing costs",
                "headcount", "recruiting"),
        supporting=("talent", "employees", "workforce", "hiring", "staffing",
                    "wage", "recruitment"),
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
        if not ids or not phrases:
            continue
        try:
            found.append((len(ids), Exposure(
                factor_key=rule.factor_key, mechanism=rule.mechanism,
                business_consequence=rule.consequence,
                decision_implication=rule.decision,
                evidence_ids=tuple(ids[:4]), matched_on=phrases[0])))
        except MacroRejected:  # pragma: no cover - guarded above
            continue
    # BEST-EVIDENCED FIRST, not declaration order. Surfaces with room for one
    # factor take the first, and taking whichever rule happens to be written
    # first is how a commerce company led with defence spending.
    found.sort(key=lambda pair: -pair[0])
    return [exposure for _, exposure in found]

"""Which analysis this company gets, and why that one.

THE DEFECT THIS CLOSES
----------------------
Every company was asked the same question, so every company got the same
answer shaped differently. The question was a constant:

    "What should be concluded about {company} from the published market
     record, and what would change it?"

That is not a decision question. It is the name of the product, with a
company inserted. A CEO cannot act on it, and it cannot differ between a
bank and a mining company because nothing in it refers to either.

WHAT THIS MODULE DOES
---------------------
Given what kind of business this is (`company_profile`) and what the
published record actually contains (counts, states, exposures), it SELECTS:

    the decision archetype, and why that one over the alternatives
    the decision question, in this business's own variables
    the signals worth ranking
    the economic channels that have a mechanism into this business
    the causal question worth asking
    the historical regimes worth replaying
    the competitors that actually compete
    the adversary's plausible moves
    the scenarios and the lever they start from

THE SELECTION IS THE PRODUCT. Two companies get different words because
they are being asked different questions -- not because a template was
filled from a different synonym list.

WHAT IT MAY NOT DO
------------------
Invent a fact about the company. Every sentence here is composed from (a)
the manifest's classification of the business model, and (b) states and
counts the market engine published. There is no third source, and in
particular there is no model call: the whole path runs with no Anthropic
credential, which is the state this deployment is in.

Where the record is empty the selection says so and the decision question
becomes the one that is actually live -- what to establish first. That is a
real answer, and it is the honest one.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Tuple

from intent_engine.executive import decision_object as _decision_object
from intent_engine.executive import strategic_delta as _strategic_delta
from intent_engine.executive.company_profile import (UNKNOWN,
                                                     CompanyIntelligenceProfile,
                                                     profile_for)

CONTRACT = "analysis_selection.v1"

#: What each archetype is a decision ABOUT, in the second person a CEO uses.
#: The wording carries the lever, so the question below is a decision and not
#: a topic.
_ARCHETYPE_SUBJECT = {
    # ADDED AFTER MEASUREMENT. ADVERTISING_PLATFORM proposes exactly two
    # archetypes and NEITHER had a subject, so Meta and Alphabet fell through
    # to the epistemic fallback -- "What does the published record establish
    # about X, and what would have to be true before a commitment rests on
    # it?" -- as their CENTRAL QUESTION, which is the single most important
    # line on the page. Composed offline from their own filings 2026-08-20:
    # the two companies' reads were identical on 10 of 12 projected fields
    # and this was one of only two that differed, by company name alone.
    #
    # The same shape as the model-keyed tables: a class was added, and a
    # table keyed on something that class INTRODUCES never got its rows.
    # `_ARCHETYPE_SUBJECT` is keyed on archetype rather than model class, so
    # the model-class registry guard could not see it.
    "ENGAGEMENT": "how much of the audience's attention to convert into "
                  "inventory, and where",
    "MONETISATION_RATE": "what to charge for a unit of attention, and in "
                         "which formats",
    "PRICING": "what to charge, and for what",
    "CAPACITY": "how much capacity to commit, and when",
    "PRODUCTIZATION": "what to build and package next",
    "MARKET_ENTRY": "which market to enter, and on what terms",
    "CUSTOMER_SEGMENT": "which customers to serve, and which to stop serving",
    "RETENTION": "what to spend to keep the customers already won",
    "CAPITAL_ALLOCATION": "where the next increment of capital goes",
    "SALES_MOTION": "how the product is sold, and by whom",
    "SUPPLY_CHAIN": "how supply is secured, and at what cost",
    "COST_STRUCTURE": "which costs are structural and which are choices",
    "M&A": "what to buy or sell, and at what price",
    "REGULATORY_RESPONSE": "how to respond to what the regulator has done",
    "COMPETITIVE_RESPONSE": "whether and how to respond to a competitor",
    "INVENTORY": "how much inventory to carry through the cycle",
    "R&D_ROADMAP": "which development programmes to fund and which to stop",
}

#: Decisions whose OUTCOME depends on who the buyer is, so naming the buyer
#: changes what the question asks rather than decorating it.
#:
#: Price elasticity is a property of the buyer, and what to build next is a
#: property of who will use it -- so PRICING and PRODUCTIZATION are in.
#: CAPITAL_ALLOCATION, COST_STRUCTURE, M&A and SUPPLY_CHAIN are out: naming
#: a customer segment inside "where the next increment of capital goes" adds
#: a noun and no meaning, which is the template-injection §8 forbids. The
#: test for membership is whether a DIFFERENT buyer would give a different
#: answer, never whether the sentence reads better.
_BUYER_BEARS_ON = ("PRICING", "PRODUCTIZATION", "CUSTOMER_SEGMENT",
                   "SALES_MOTION", "RETENTION", "MARKET_ENTRY")

#: The management lever a scenario starts from, per archetype.
_ARCHETYPE_LEVER = {
    "PRICING": "a pricing action",
    "CAPACITY": "a capacity commitment",
    "PRODUCTIZATION": "a product investment",
    "MARKET_ENTRY": "entering a new market",
    "CUSTOMER_SEGMENT": "reweighting the customer mix",
    "RETENTION": "a retention investment",
    "CAPITAL_ALLOCATION": "committing the next increment of capital",
    "SALES_MOTION": "changing the sales motion",
    "SUPPLY_CHAIN": "requalifying or dual-sourcing supply",
    "COST_STRUCTURE": "a cost reduction programme",
    "M&A": "an acquisition",
    "REGULATORY_RESPONSE": "a compliance or engagement posture",
    "COMPETITIVE_RESPONSE": "a direct competitive response",
    "INVENTORY": "changing the inventory position",
    "R&D_ROADMAP": "funding or stopping a development programme",
}

#: Which archetype an economic channel bears on most directly. Used to move
#: a decision UP the list when the channel is live for this company -- the
#: economy choosing the question, which is the point of measuring it.
_CHANNEL_FAVOURS = {
    "MARKET_RATE": ("CAPITAL_ALLOCATION", "PRICING"),
    "CURRENCY": ("PRICING", "COST_STRUCTURE"),
    "COMMODITY": ("CAPITAL_ALLOCATION", "COST_STRUCTURE", "PRICING"),
    "INFLATION": ("PRICING", "COST_STRUCTURE"),
    "LABOR": ("COST_STRUCTURE", "CAPACITY"),
    "UNEMPLOYMENT": ("CUSTOMER_SEGMENT", "CAPITAL_ALLOCATION"),
    "INDUSTRIAL_DEMAND": ("CAPACITY", "INVENTORY"),
    "POLICY_RATE": ("CAPITAL_ALLOCATION", "PRICING"),
}

#: The measurable business variable each channel moves. Model-specific where
#: the channel means something structurally different -- a commodity price is
#: an INPUT COST almost everywhere and the REVENUE LINE at a producer, and
#: reporting those the same way would be the single worst error here.
_CHANNEL_VARIABLE = {
    "MARKET_RATE": "cost of funds and the hurdle rate on committed capital",
    "POLICY_RATE": "the policy path that sets funding cost and demand",
    "CURRENCY": "translated revenue and the local-currency cost base",
    "COMMODITY": "input cost per unit produced",
    "INFLATION": "input and wage cost measured against realised price",
    "LABOR": "cost and availability of the people who deliver",
    "UNEMPLOYMENT": "household income, and therefore end demand",
    "INDUSTRIAL_DEMAND": "order rate and capacity utilisation",
}
_CHANNEL_VARIABLE_BY_MODEL = {
    ("COMMODITY", "COMMODITY_PRODUCER"):
        "realised price per unit sold -- the revenue line itself",
    ("MARKET_RATE", "BALANCE_SHEET_OR_NETWORK"):
        "net interest spread between assets and funding",
    ("POLICY_RATE", "BALANCE_SHEET_OR_NETWORK"):
        "net interest spread between assets and funding",
    ("UNEMPLOYMENT", "BALANCE_SHEET_OR_NETWORK"):
        "credit losses on the existing book",
    ("LABOR", "PEOPLE_OR_ROUTE_BASED_SERVICES"):
        "billable capacity and the cost of each billable hour",
    ("INDUSTRIAL_DEMAND", "MANUFACTURE_AND_AFTERMARKET"):
        "orders and backlog, which set the production rate later",
    ("CURRENCY", "COMMODITY_PRODUCER"):
        "the gap between revenue currency and cost currency",
}


@dataclasses.dataclass(frozen=True)
class Signal:
    """One thing worth watching, and why it matters for THIS business."""
    name: str
    why: str
    kind: str           #: REVENUE_DRIVER / COST_DRIVER / EVIDENCE_TYPE
    observed: str = ""  #: what the published record currently says about it

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Transmission:
    """economic factor -> mechanism -> business variable -> implication."""
    channel: str
    mechanism: str
    business_variable: str
    decision_implication: str
    observed_ids: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class AdversaryMove:
    """One level of competitive reasoning about one actor."""
    level: str          #: L0 / L1 / L2
    actor: str
    objective: str
    action: str
    rationale: str
    evidence: str
    observable_signal: str
    impact: str
    countermeasure: str
    kill_switch: str

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Scenario:
    """A lever, traced through its consequences."""
    name: str           #: BASE / UPSIDE / DOWNSIDE / ADVERSARIAL
    lever: str
    first_order: str
    second_order: str
    third_order: str
    competitor_response: str
    economic_exposure: str
    outcome_range: str
    kill_switch: str

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class AnalysisSelection:
    """Everything this company's analysis chose, and why it chose it."""
    company_id: str
    company_name: str
    profile: Optional[CompanyIntelligenceProfile] = None
    archetype: str = UNKNOWN
    why_this_question: str = ""
    considered: Tuple[dict, ...] = ()       #: every archetype and its score
    decision_question: str = ""
    decision_object: Optional[object] = None
    question_basis: dict = dataclasses.field(default_factory=dict)
    delta: Optional[object] = None
    information_priorities: Tuple[object, ...] = ()
    signals: Tuple[Signal, ...] = ()
    transmission: Tuple[Transmission, ...] = ()
    no_exposure_reason: str = ""
    causal_question: str = ""
    why_this_causal_question: str = ""
    historical_dimensions: Tuple[str, ...] = ()
    adversary: Tuple[AdversaryMove, ...] = ()
    scenarios: Tuple[Scenario, ...] = ()
    contract: str = CONTRACT

    def as_dict(self) -> dict:
        return {
            "contract": self.contract,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "profile": self.profile.as_dict() if self.profile else None,
            "archetype": self.archetype,
            "why_this_question": self.why_this_question,
            "considered": list(self.considered),
            "decision_question": self.decision_question,
            "decision_object": (self.decision_object.as_dict()
                                if self.decision_object is not None else None),
            "question_basis": dict(self.question_basis or {}),
            "delta": (self.delta.as_dict() if self.delta is not None else None),
            "information_priorities": [p.as_dict()
                                       for p in self.information_priorities],
            "signals": [s.as_dict() for s in self.signals],
            "transmission": [t.as_dict() for t in self.transmission],
            "no_exposure_reason": self.no_exposure_reason,
            "causal_question": self.causal_question,
            "why_this_causal_question": self.why_this_causal_question,
            "historical_dimensions": list(self.historical_dimensions),
            "adversary": [a.as_dict() for a in self.adversary],
            "scenarios": [s.as_dict() for s in self.scenarios],
        }


@dataclasses.dataclass(frozen=True)
class _Preview:
    """The three fields the delta builder reads, before the full selection
    exists. Passing a half-constructed `AnalysisSelection` is how a producer
    comes to depend on a field that is not populated yet."""
    archetype: str = ""
    decision_question: str = ""
    considered: Tuple[dict, ...] = ()


@dataclasses.dataclass(frozen=True)
class RecordFacts:
    """What the published record contains. Counts and states only.

    Deliberately a small value object rather than the dossier itself, so
    this module cannot reach for a field the market engine does not
    actually publish -- which is how a selection layer starts inventing.
    """
    evidence: int = 0
    beliefs: int = 0
    expectations: int = 0
    contradictions: int = 0
    theses: int = 0
    causal_questions: int = 0
    causal_resolved: int = 0
    causal_refused: bool = False
    economic_ids: Tuple[str, ...] = ()
    hidden_state: str = ""
    available: bool = True


def _channel_of(economic_id: str) -> str:
    """'US:MARKET_RATE' -> 'MARKET_RATE'. The region is not the channel."""
    text = str(economic_id or "")
    return (text.split(":", 1)[1] if ":" in text else text).upper()


#: Which decision an identified operating posture is a decision ABOUT.
#:
#: WHY THIS TABLE EXISTS. The market engine identifies which of seventeen
#: postures a company is in, and this layer used to collapse every one of
#: them to a single "+3 to pricing and competitive response" -- so a company
#: cutting cost and a company preparing an acquisition were steered to the
#: same decision, and the engine's most specific output was discarded at the
#: moment it should have been used.
#:
#: The effect of discarding it was measurable and large: the decision
#: question is a function of (business model, archetype), so within a model
#: class the archetype decided everything, and 21 of the 100 manifest
#: companies share SUBSCRIPTION_SOFTWARE. Every one of them got the pricing
#: question. That is the original template collapse one layer down, and it
#: was invisible to the cross-industry measurement that closed the first one.
#:
#: Each row is definitional: a company that is cutting cost is by definition
#: deciding about its cost structure. None of it claims the posture is
#: correct -- that is the market engine's belief with its own standing, and
#: an archetype that wins on a wrong posture is still the right decision to
#: have asked about given what was believed.
_POSTURE_FAVOURS = {
    "GROWING": ("CAPACITY", "SALES_MOTION", "CUSTOMER_SEGMENT"),
    "DEFENDING": ("COMPETITIVE_RESPONSE", "RETENTION"),
    "EXPANDING": ("MARKET_ENTRY", "CAPACITY"),
    "COST_CUTTING": ("COST_STRUCTURE",),
    "CAPITAL_CONSTRAINED": ("CAPITAL_ALLOCATION",),
    "PREPARING_ACQUISITION": ("M&A",),
    "PREPARING_DIVESTITURE": ("CAPITAL_ALLOCATION", "M&A"),
    "PRICE_AGGRESSIVE": ("PRICING", "COMPETITIVE_RESPONSE"),
    "CAPACITY_CONSTRAINED": ("CAPACITY", "SUPPLY_CHAIN"),
    "EXPERIMENTING": ("PRODUCTIZATION",),
    "REGULATORY_DEFENSIVE": ("REGULATORY_RESPONSE",),
    "PLATFORM_EXPANDING": ("PRODUCTIZATION", "MARKET_ENTRY"),
    "SERVICES_DEPENDENT": ("PRODUCTIZATION",),
    "PRODUCTIZING": ("PRODUCTIZATION",),
    "MARKET_SHARE_SEEKING": ("PRICING", "SALES_MOTION"),
    "MARGIN_PROTECTING": ("PRICING", "COST_STRUCTURE"),
    # WAITING is deliberately empty: a company that is waiting has not
    # committed to a decision, so nothing may be inferred about which one it
    # faces. It falls through to the standing menu order.
    "WAITING": (),
}

_POSTURE_ENGLISH = {
    "GROWING": "growing the business",
    "DEFENDING": "defending a position",
    "EXPANDING": "expanding into new ground",
    "COST_CUTTING": "cutting cost",
    "CAPITAL_CONSTRAINED": "constrained on capital",
    "PREPARING_ACQUISITION": "preparing an acquisition",
    "PREPARING_DIVESTITURE": "preparing a divestiture",
    "PRICE_AGGRESSIVE": "pricing aggressively",
    "CAPACITY_CONSTRAINED": "constrained on capacity",
    "EXPERIMENTING": "experimenting",
    "REGULATORY_DEFENSIVE": "defending a regulatory position",
    "PLATFORM_EXPANDING": "expanding a platform",
    "SERVICES_DEPENDENT": "dependent on services revenue",
    "PRODUCTIZING": "turning services into product",
    "MARKET_SHARE_SEEKING": "seeking market share",
    "MARGIN_PROTECTING": "protecting margin",
    "WAITING": "waiting",
}

#: States that mean "no posture was identified". These are STATUSES of the
#: market engine's run, not postures, and must never select a decision.
_NO_POSTURE = frozenset({
    "TRACKED_NO_IDENTIFIED_STATE", "HIDDEN_STATE_NOT_RUN",
    "HIDDEN_STATE_NONE_TRACKED", "", "UNKNOWN",
})


def _posture(hidden_state: str) -> str:
    """The identified operating posture, or "" when none was identified."""
    text = str(hidden_state or "").strip().upper()
    return "" if text in _NO_POSTURE else text


#: An OBSERVATION of this company outranks a PRIOR about its business model.
#:
#: The base score is the model class's standing order -- a prior, identical
#: for every company sharing the model, and at most `len(menu)` (six). The
#: posture is a belief the market engine formed about THIS company from THIS
#: company's record. Scoring the observation below the prior meant the prior
#: always won: a software company observed cutting cost still got the
#: pricing question, because pricing leads the software menu.
#:
#: Set above the largest possible base so an identified posture decides the
#: archetype, and left as one named constant so the ordering is a stated
#: policy rather than an accident of two literals.
_POSTURE_WEIGHT = 8


#: WHAT A COMPANY FACING EACH DECISION PUTS ON ITS OWN RECORD.
#:
#: WHY THIS TABLE EXISTS. MEASURED across cohort A on 1b0d803c: SEVEN of nine
#: companies were handed the identical central question --
#:
#:     "what to charge, and for what, without losing more customer count
#:      than the price gains?"
#:
#: -- with the identical watch metrics, across four unrelated categories. A
#: freight-visibility company, a data-protection company, an integration
#: platform and an event-intelligence company were all told their decision was
#: a pricing decision about seats per customer.
#:
#: The cause is structural, not a bad rule. `_score_archetypes` ranks the menu
#: by the MODEL CLASS's own ordering, then adjusts by live economic channels
#: and identified posture. For a private company with neither, nothing
#: company-specific reaches the ordering at all, so the class prior IS the
#: answer -- and every SUBSCRIPTION_SOFTWARE company gets whatever sits first
#: on the software menu. `select` already receives the company's own text and
#: spent it entirely on classification: its words decided WHAT KIND of
#: business it is and then played no part in WHICH DECISION it faces.
#:
#: So the menu still comes from the model -- a bank does not choose between
#: inventory and certification -- and the ORDER may now be moved by the
#: subject's own record, which is what this module's docstring already
#: claimed it did.
#:
#: THE PHRASES ARE DECISION-BEARING, NOT TOPICAL. "price" appears on every
#: SaaS page ever written; "list price", "discounting" and "price increase"
#: appear when a company is actually deciding what to charge. A topical word
#: would reorder the menu for every company and reproduce the collapse with
#: extra steps.
_ARCHETYPE_EVIDENCE = {
    "PRICING": ("list price", "price increase", "discounting", "repricing",
                "pricing model", "per-seat", "consumption pricing",
                "price realisation", "price realization"),
    "CAPACITY": ("capacity expansion", "capacity commitment",
                 "capacity constraint", "footprint expansion",
                 "utilisation rate", "utilization rate", "overprovisioned",
                 "under-utilised", "under-utilized",
                 "add capacity", "capacity headroom"),
    "PRODUCTIZATION": ("general availability", "product launch",
                       "we launched", "new module", "repackaged",
                       "packaging change", "bundling change",
                       "unbundled", "sunset the", "end of life"),
    "MARKET_ENTRY": ("new market", "expansion into", "we entered",
                     "market entry", "first customer in", "localisation",
                     "localization", "opened an office"),
    "CUSTOMER_SEGMENT": ("moved upmarket", "moved downmarket", "upmarket",
                         "mid-market push", "enterprise segment",
                         "segment focus", "stopped serving",
                         "account concentration", "customer concentration"),
    # A DISCLOSED METRIC IS NOT A DECISION. "net revenue retention",
    # "churn", "renewal rate" and "expansion revenue" are numbers a
    # subscription filer must report; they say the company MEASURES
    # retention, not that it is deciding what to spend on it. RETENTION
    # stays second on the software menu, so it remains reachable by the
    # class prior without any evidence at all.
    "RETENTION": ("customer retention", "retention programme",
                  "retention program", "customer success investment",
                  "renewal risk", "churn increased", "churn reduction",
                  "win-back", "upsell motion"),
    # MEASURED on a 10-K's ordinary register: "free cash flow", "dividend"
    # and "capital expenditure" are mandatory line items and fired three
    # hits on text where nothing was being decided.
    "CAPITAL_ALLOCATION": ("capital allocation", "buyback",
                           "share repurchase", "repurchase programme",
                           "repurchase program", "initiated a dividend",
                           "increased the dividend", "suspended the dividend",
                           "funding round", "series b", "series c",
                           "series d", "raised a round"),
    # MEASURED on cohort A: "go-to-market" and "channel partner" are on
    # almost every B2B page ever published, and two hits of them moved
    # SALES_MOTION above the class prior for three unrelated companies --
    # a supply-chain planner, an event-intelligence firm and a storage
    # vendor all received "how the product is sold, and by whom". A phrase
    # earns a place here by showing the company DECIDING how it sells, not
    # by showing that it sells.
    "SALES_MOTION": ("channel conflict", "partner-led", "partner led",
                     "channel dependence", "route to market",
                     "route-to-market", "direct sales force",
                     "sales capacity", "sales productivity",
                     "quota capacity", "partner concentration",
                     "reseller margin", "reseller economics",
                     "customer acquisition cost", "cac payback",
                     "payback period", "land and expand",
                     "sales cycle lengthened", "shift to direct",
                     "shift to channel"),
    "SUPPLY_CHAIN": ("supply chain", "freight", "shipment", "carrier",
                     "logistics", "tariff", "customs", "seaport",
                     "supplier", "procurement", "lead time"),
    # "gross margin", "headcount" and "operating leverage" are what a
    # filing REPORTS; "restructuring" and "reduction in force" are what a
    # company DOES.
    "COST_STRUCTURE": ("cost structure", "restructuring",
                       "restructuring charge", "layoff",
                       "reduction in force", "workforce reduction",
                       "cost reduction", "cost programme", "cost program"),
    # THE ONE THAT SHIPPED. Rubrik, a LEVEL A filer with 32 filings, was
    # handed "what to buy or sell, and at what price" on "acquired by,
    # acquisition of, combination with" -- the exact wording of an ASC 805
    # business-combination note, which is in essentially every 10-K.
    "M&A": ("announced the acquisition", "agreed to acquire",
            "definitive agreement", "we acquired", "merger agreement",
            "divestiture of", "divested", "tender offer",
            "letter of intent"),
    "REGULATORY_RESPONSE": ("new regulation", "regulatory change",
                            "regulatory approval", "compliance obligation",
                            "audit requirement", "data residency",
                            "data sovereignty", "sec rule",
                            "enforcement action", "consent decree",
                            "regulatory deadline"),
    "COMPETITIVE_RESPONSE": ("migrate from", "switch from",
                             "alternative to", "displace", "displaced",
                             "win rate against", "competitive displacement",
                             "rip and replace"),
    "INVENTORY": ("inventory", "stock levels", "working capital",
                  "days of supply", "safety stock"),
    "R&D_ROADMAP": ("research and development", "clinical trial",
                    "clinical programme", "clinical program",
                    "pipeline programme", "pipeline program",
                    "development programme", "development program",
                    "phase iii", "phase ii"),
}

#: How many DISTINCT phrases a company's own record must carry before its
#: evidence may move an archetype up the menu.
#:
#: Two, not one. One incidental phrase is a coincidence -- every company
#: mentions "regulation" somewhere -- and a menu reordered by a coincidence is
#: the same defect with more steps. Requiring two distinct phrases is the
#: applicability gate a pattern library needs before it fires.
_EVIDENCE_MIN_HITS = 2

#: What two hits are worth, and how much more weight more of them carry.
#:
#: THE FLOOR IS BELOW THE LIVE-CHANNEL BONUS (4) on purpose: a measured
#: economic condition reaching this business is stronger evidence than the
#: company having written about a subject, and must still win at the margin.
#:
#: BUT IT HAS TO BE ABLE TO OUTRANK THE CLASS PRIOR, or the whole path is
#: unreachable for the decisions that matter most. Measured with a flat +3: a
#: freight record naming shipment, carrier, customs, tariff, logistics, supply
#: chain and procurement -- SEVEN distinct terms -- still lost to PRICING,
#: because SUPPLY_CHAIN is not on the software menu and so starts at zero
#: against a five-deep standing list. A company whose entire published record
#: is about moving freight is not facing a seat-pricing decision, and an
#: evidence path that cannot say so is decoration.
#:
#: So the bonus SCALES with how much of the record points one way. Two terms
#: is a mention and cannot displace the class prior; seven is what the company
#: is about and can. The cap stops one repetitive page from running away.
_EVIDENCE_WEIGHT = 3
_EVIDENCE_SCALE_CAP = 4


def _evidence_bonus(hits: int) -> int:
    return _EVIDENCE_WEIGHT + min(max(hits - _EVIDENCE_MIN_HITS, 0),
                                  _EVIDENCE_SCALE_CAP)


#: Phrases matched as WHOLE WORDS, never as substrings.
#:
#: MEASURED on cohort A: "support" and "reporting" -- two of the commonest
#: words in enterprise prose -- contain "port", so Cohesity's page told the
#: reader that its own record discusses "logistics, port, supply chain" when
#: the word "port" never appears in it. "industrial" contains "trial" the
#: same way. That is a false statement about a company's record, and it also
#: inflated the hit count that decides which decision wins.
#:
#: A phrase boundary, not `\b` on the whole string: "per-seat" and
#: "go-to-market" end in word characters but contain punctuation, and `\b`
#: around the whole phrase is still correct for those. What matters is that
#: neither END of the phrase may sit inside a longer word.
_BOUNDARY = {}


def _says(text: str, phrase: str) -> bool:
    """Does this record use this phrase as its own word(s)?

    A NECESSARY-CONDITION PREFILTER, because the boundary is not free.
    MEASURED on a 0.79MB record with the full 142-phrase table: the plain
    substring scan cost 43ms/MB and the bounded scan 1381ms/MB -- 32x, or
    ~2.8 seconds on a realistic 2MB record, on every call, on a path that
    composes twice per run. That is a worse defect than the one the boundary
    fixes.
    
    A phrase cannot appear as a WORD unless it appears as a SUBSTRING, so the
    cheap test runs first and the regex only adjudicates the small set that
    passes it. Same answer, and the ~90% that miss never touch the engine.
    """
    if phrase not in text:
        return False
    pattern = _BOUNDARY.get(phrase)
    if pattern is None:
        pattern = _BOUNDARY[phrase] = re.compile(
            r"(?<![0-9a-z])" + re.escape(phrase) + r"(?![0-9a-z])")
    return bool(pattern.search(text))


def _evidence_archetypes(own_text: str) -> dict:
    """Which decisions this company's OWN record shows it facing.

    Returns {archetype: (hits, phrases)} for archetypes clearing the gate.
    Never raises and returns nothing for an empty record, which is the honest
    answer when a company published nothing we could read.
    """
    text = " ".join(str(own_text or "").lower().split())
    if len(text) < 200:
        return {}
    found = {}
    for archetype, phrases in _ARCHETYPE_EVIDENCE.items():
        hit = tuple(sorted({p for p in phrases if _says(text, p)}))
        if len(hit) >= _EVIDENCE_MIN_HITS:
            found[archetype] = (len(hit), hit)
    return found


def _score_archetypes(profile, facts: RecordFacts, own_text: str = ""):
    """Rank this business's decision archetypes against what is known.

    The MENU comes from the business model -- a bank does not choose between
    inventory and certification -- and the ORDER comes from the evidence. So
    two banks share a menu, and a bank and a software company share almost
    nothing, which is the specialisation this is for.
    """
    live_channels = {_channel_of(i) for i in facts.economic_ids}
    rows = []
    standing = tuple(profile.decision_archetypes or ())
    # THE MENU IS EXTENDED BY WHAT WAS OBSERVED, not only by the model.
    #
    # The standing menu is what this KIND of business normally decides. A
    # software company does not normally face a cost-structure decision, so
    # COST_STRUCTURE is not on its menu -- and a software company OBSERVED
    # cutting cost was therefore steered back to the pricing question,
    # because the posture had nothing to land on. The most informative
    # observation the market engine can make, a company facing a decision
    # its business model does not standardly face, was the one case the
    # menu could not represent.
    #
    # Posture-added archetypes enter BELOW every standing one (score 0 before
    # the posture bonus), so they win only on the strength of the observation
    # and never merely by being unusual.
    posture = _posture(facts.hidden_state)
    shown = _evidence_archetypes(own_text)
    added = tuple(a for a in _POSTURE_FAVOURS.get(posture, ())
                  if a not in standing and a in _ARCHETYPE_SUBJECT)
    # AND BY WHAT THE COMPANY'S OWN RECORD SHOWS IT FACING. Same rule as the
    # posture additions above: it enters BELOW every standing archetype, so it
    # wins on the strength of the evidence and never merely by being unusual.
    from_record = tuple(a for a in shown
                        if a not in standing and a not in added
                        and a in _ARCHETYPE_SUBJECT)
    menu = standing + added + from_record
    for position, archetype in enumerate(menu):
        # BASE: the model class's own ordering. For a commodity producer
        # capital allocation leads; for a software company pricing does.
        score = (len(standing) - position) if position < len(standing) else 0
        # WHAT MOVED THIS ARCHETYPE, ITEMISED. Without it a cohort cannot tell
        # "these companies genuinely look alike" from "the class prior won
        # again", which is the distinction that took seven identical X-Rays to
        # notice. The four sources are reported separately and never summed
        # into one opaque number.
        contrib = {"class_prior": score, "evidence": 0, "econ": 0,
                   "posture": 0, "causal": 0}
        if archetype in from_record:
            hits, phrases = shown[archetype]
            reasons_extra = (
                f"this is not a standing decision for a "
                f"{profile.business_model_class.replace('_', ' ').lower()} "
                f"business, and is on the list because this company's own "
                f"record discusses it: {', '.join(phrases[:3])}")
        elif archetype in added:
            reasons_extra = (
                f"this is not a standing decision for a "
                f"{profile.business_model_class.replace('_', ' ').lower()} "
                f"business, and is on the list only because the record shows "
                f"the company facing it")
        else:
            reasons_extra = ""
        reasons = [reasons_extra or
                   (f"{_ARCHETYPE_SUBJECT.get(archetype, archetype)} is a "
                    f"standing decision for this business model")]
        for channel in sorted(live_channels):
            if archetype in _CHANNEL_FAVOURS.get(channel, ()):
                score += 4
                contrib["econ"] += 4
                reasons.append(
                    f"measured {channel.replace('_', ' ').lower()} conditions "
                    f"reach this business and bear directly on it")
        # THE SUBJECT'S OWN RECORD, ORDERING ITS OWN MENU. Without this the
        # base score is the model class's ordering and nothing else, so every
        # company sharing a class receives the same central question -- which
        # is what seven of nine cohort-A companies did.
        if archetype in shown:
            hits, phrases = shown[archetype]
            score += _evidence_bonus(hits)
            contrib["evidence"] += _evidence_bonus(hits)
            contrib["evidence_terms"] = list(phrases[:6])
            reasons.append(
                f"this company's own record discusses this decision in "
                f"{hits} distinct terms ({', '.join(phrases[:3])}), which is "
                f"evidence it is facing it rather than an assumption from "
                f"its business model")
        if posture:
            if archetype in _POSTURE_FAVOURS.get(posture, ()):
                score += _POSTURE_WEIGHT
                contrib["posture"] += _POSTURE_WEIGHT
                english = _POSTURE_ENGLISH.get(
                    posture, "in an identified operating posture")
                reasons.append(
                    f"the company is {english}, which is decided by "
                    f"{_ARCHETYPE_SUBJECT.get(archetype, archetype)}")
            elif not _POSTURE_FAVOURS.get(posture):
                # An identified posture this build has no decision mapping
                # for still means SOMETHING was identified, so the standing
                # response decisions rise -- the pre-posture behaviour.
                if archetype in ("COMPETITIVE_RESPONSE", "PRICING"):
                    score += 3
                    reasons.append(
                        "the operating posture has been identified, which is "
                        "what a response would be responding to")
        if facts.contradictions and archetype in ("COMPETITIVE_RESPONSE",
                                                  "REGULATORY_RESPONSE"):
            score += 2
            reasons.append("the record carries contradictions worth resolving "
                           "before acting elsewhere")
        if facts.causal_resolved and archetype in ("PRICING", "CAPACITY",
                                                   "PRODUCTIZATION"):
            score += 2
            reasons.append("a causal question has been resolved, so an acting "
                           "decision is better supported than an "
                           "information-gathering one")
            contrib["causal"] = contrib.get("causal", 0) or 1
        # A decision is CLASS_PRIOR_ONLY when nothing but the model class's
        # own menu ordering put it where it is. Recorded per archetype so the
        # cohort-level detector reads a measurement rather than re-deriving
        # one from prose.
        contrib["class_prior_only"] = not any(
            contrib[k] for k in ("evidence", "econ", "posture", "causal"))
        rows.append({"archetype": archetype, "score": score,
                     "subject": _ARCHETYPE_SUBJECT.get(archetype, archetype),
                     "contributions": contrib,
                     "why": "; ".join(reasons)})
    # A TIE IS NOT EVIDENCE OUTRANKING THE PRIOR.
    #
    # The key was (-score, archetype), so two archetypes on the same score
    # were separated by DICTIONARY ORDER of the enum name. MEASURED live:
    # Rubrik's PRICING (class prior, base 5) tied M&A (off-menu, evidence 5)
    # and lost because "M&A" sorts before "PRICING" -- the alphabet chose the
    # company's central decision. The same tie went the other way for HYCU,
    # whose REGULATORY_RESPONSE tied PRICING at 5 and lost because "P" < "R".
    #
    # The menu is what this KIND of business normally decides and is the
    # better-founded default; §2 asks that a company's own record win where
    # it is SUFFICIENTLY distinguishing, and equal is not more. So on a tie
    # the standing menu holds, in its own order, and an off-menu archetype
    # must strictly exceed it to displace it. The name remains only as a
    # deterministic last resort.
    order = {a: i for i, a in enumerate(menu)}
    standing_set = set(standing)
    rows.sort(key=lambda r: (-r["score"],
                             0 if r["archetype"] in standing_set else 1,
                             order.get(r["archetype"], len(menu)),
                             r["archetype"]))
    return tuple(rows)


#: Nouns that ALREADY measure something, so "more <noun>" needs no help.
#: A closed list is defensible here in a way a closed VERB list was not:
#: this is the small vocabulary a company uses to say what it counts, and a
#: miss costs a redundant but grammatical "count", never a broken sentence.
_MEASURE_NOUNS = frozenset("""
count usage capacity volume revenue spend throughput bandwidth storage
traffic data time value consumption utilisation utilization headcount
""".split())


def _countable(unit: str) -> str:
    """`unit` in a form that can follow the word "more".

    MEASURED LIVE on NinjaOne (591041b0): the company establishes that it
    charges per device, the slot took "device", and the central question
    read "what to charge, and for what, without losing more device than the
    price gains?".

    THE COMMENT BELOW THIS FUNCTION'S CALLER SAYS THE TAILS ARE "PHRASED TO
    AVOID SUBJECT-VERB AGREEMENT" -- and they are. Number agreement is a
    second problem it does not cover: "more X" needs a plural or a mass
    noun, and a billing unit is usually a singular count noun.

    NOT PLURALISED BY GUESSWORK. "capacity" has no plural and "device" and
    "seat" have irregular company. The class constant this slot REPLACES is
    already "customer count", so a singular unit is given that same shape --
    "device count" -- which is both grammatical and the phrasing the rest of
    the product uses.
    """
    text = " ".join(str(unit or "").split())
    if not text:
        return text
    last = text.split()[-1].lower()
    # ALREADY COUNTABLE AFTER "MORE": a plural, or a noun that is itself a
    # measure. A first version appended unconditionally and produced
    # "customer count count" -- the class constant is already in this shape,
    # so the rule has to be idempotent -- and "capacity count", when "more
    # capacity" was grammatical to begin with.
    if _decision_object.is_plural_noun(last) or last in _MEASURE_NOUNS:
        return text
    return f"{text} count"


def _decision_question(profile, archetype: str, facts: RecordFacts,
                       objects=None) -> str:
    """The question, in this business's own variables.

    Composed from the archetype's subject and the driver the archetype acts
    on, so a pricing question at a bank names the spread and a pricing
    question at a consumer brand names promotional depth.

    WHERE THE VARIABLES COME FROM, AND WHY IT CHANGED
    -------------------------------------------------
    The driver and cost slots used to be filled ONLY from
    `_ECONOMICS[business_model_class]` -- a table keyed on the class. So the
    question was `f(archetype, model_class)` and nothing else, and on the
    frozen 40-company qualification 22 companies received one byte-identical
    pricing question because all 22 share `primary_revenue_drivers[0] ==
    "customer count"`. Four distinct questions across 33 companies is not a
    reading of 33 companies.

    `objects` is `decision_object.DecisionObject`: what THIS company said
    about what a unit of its revenue is counted in and who decides to buy
    it. Where it established something, that fills the slot; where it did
    not, the class constant still fills it and `question_basis()` says which
    happened. A slot filled by assumption that reads as though the company
    told us is the one outcome forbidden here.
    """
    name = profile.company_name
    subject = _ARCHETYPE_SUBJECT.get(archetype, "")
    if not profile.known or not subject:
        return (f"What does the published record establish about {name}, and "
                f"what would have to be true before a commitment rests on it?")
    drivers = profile.primary_revenue_drivers or ()
    costs = profile.primary_cost_drivers or ()
    driver = drivers[0] if drivers else "the revenue base"
    cost = costs[0] if costs else "the cost base"
    unit = getattr(getattr(objects, "billing_unit", None), "value", "")
    if getattr(getattr(objects, "billing_unit", None), "known", False):
        driver = _countable(unit)
    buyer = getattr(getattr(objects, "buyer", None), "value", "")
    if getattr(getattr(objects, "buyer", None), "known", False):
        # The buyer sharpens the decisions that are ABOUT a buyer, and is
        # left out of the ones that are not: a capital-allocation question
        # does not become better by naming a customer segment.
        if archetype in _BUYER_BEARS_ON:
            driver = f"{driver} among {buyer}"
    tail = {
        "PRICING": f"without losing more {driver} than the price gains",
        # PHRASED TO AVOID SUBJECT-VERB AGREEMENT. The driver and cost slots
        # hold noun phrases that may be singular ("customer count") or plural
        # ("orders and backlog"), and no single conjugation is correct for
        # both -- "supply chain and component availability IS committed
        # before the orders and backlog it is meant to serve ARRIVES" reached
        # a customer. Every tail below therefore puts the slot in a position
        # where it governs no verb.
        "CAPACITY": f"given that the commitment to {cost} is made before the "
                    f"{driver} it is meant to serve",
        "CAPITAL_ALLOCATION": f"given what the same capital would earn "
                              f"against {driver} elsewhere",
        "COST_STRUCTURE": f"without cutting into the {driver} the cost base "
                          f"exists to produce",
        "SUPPLY_CHAIN": f"given what {cost} allows to be delivered",
        "R&D_ROADMAP": f"given how long it takes a programme to reach "
                       f"{driver}",
        "REGULATORY_RESPONSE": f"before the decision changes what may be "
                               f"sold, or at what price",
        "CUSTOMER_SEGMENT": f"measured on {driver} net of what it costs to "
                            f"serve",
        "RETENTION": f"measured against what the same spend would win in new "
                     f"{driver}",
        "SALES_MOTION": f"measured on acquisition cost per unit of {driver}",
        "PRODUCTIZATION": f"given what it displaces in the existing {driver}",
        "MARKET_ENTRY": f"given what the established markets return on the "
                        f"same {cost}",
        "INVENTORY": f"given that the position is set before {driver} can be "
                     f"observed",
        "COMPETITIVE_RESPONSE": f"before the move reaches {driver}",
        "M&A": f"measured against building the same {driver} internally",
        "ENGAGEMENT": f"given that ad load taken today is paid for out of "
                      f"{driver} tomorrow",
        "MONETISATION_RATE": f"given what {driver} the auction clears at that "
                             f"price",
    }.get(archetype, "")
    return (f"For {name}: {subject}, {tail}?" if tail
            else f"For {name}: {subject}?")


def question_basis(profile, archetype: str, objects=None) -> dict:
    """Which slots in the decision question the COMPANY filled, and which the
    class prior filled.

    This is the field that makes the repair auditable. Without it a reader
    cannot tell a question that names this company's own billing unit from
    one that names the class constant, and a cohort cannot measure whether
    anything actually changed -- which is how 22 identical questions went
    twenty-two times unnoticed.
    """
    unit = getattr(objects, "billing_unit", None)
    buyer = getattr(objects, "buyer", None)
    drivers = tuple(getattr(profile, "primary_revenue_drivers", ()) or ())
    prior_driver = drivers[0] if drivers else "the revenue base"
    from_company, from_prior = [], []
    (from_company if getattr(unit, "known", False) else from_prior).append(
        "the unit revenue is counted in")
    uses_buyer = archetype in _BUYER_BEARS_ON
    if uses_buyer:
        (from_company if getattr(buyer, "known", False)
         else from_prior).append("who decides to buy")
    return {
        "slots_from_company": tuple(from_company),
        "slots_from_class_prior": tuple(from_prior),
        "company_slot_count": len(from_company),
        "billing_unit": getattr(unit, "value", ""),
        "billing_unit_state": getattr(unit, "state", "NOT_ESTABLISHED"),
        "billing_unit_quote": getattr(unit, "quote", ""),
        "buyer": getattr(buyer, "value", ""),
        "buyer_state": getattr(buyer, "state", "NOT_ESTABLISHED"),
        "buyer_quote": getattr(buyer, "quote", ""),
        "buyer_used": bool(uses_buyer),
        "class_prior_driver": prior_driver,
        "why": _basis_sentence(from_company, from_prior, objects, profile),
    }


def _basis_sentence(from_company, from_prior, objects, profile) -> str:
    """One sentence a reader can act on, never a status code."""
    unit = getattr(objects, "billing_unit", None)
    model = str(getattr(profile, "business_model_class", "") or "").replace(
        "_", " ").lower()
    if from_company and getattr(unit, "known", False):
        return (f"The question is measured in {unit.value}, which is what "
                f"this company says it charges for -- not the unit a "
                f"{model} business is assumed to charge for.")
    if from_company:
        return ("Part of this question is in this company's own terms; the "
                "rest is what a business of this kind normally decides.")
    reason = str(getattr(unit, "reason", "") or "")
    return (f"Every variable in this question comes from what a {model} "
            f"business normally decides, not from this company: "
            f"{reason or 'it published nothing we could read on the point'}.")


def _signals(profile, facts: RecordFacts) -> Tuple[Signal, ...]:
    """The variables this business actually turns on, ranked.

    Revenue drivers first because a decision that does not reach revenue or
    cost is not a commercial decision; then the cost drivers that bind; then
    the evidence classes that would show either moving.
    """
    if not profile.known:
        return ()
    rows = []
    for driver in profile.primary_revenue_drivers[:4]:
        rows.append(Signal(
            name=driver, kind="REVENUE_DRIVER",
            why=f"revenue at a business of this kind moves with {driver}"))
    for driver in profile.primary_cost_drivers[:3]:
        rows.append(Signal(
            name=driver, kind="COST_DRIVER",
            why=f"{driver} is one of the costs that decides whether revenue "
                f"converts to margin here"))
    observed = (f"the published record carries {facts.evidence} evidence "
                f"row(s) for this company") if facts.evidence else \
        "nothing in the published record speaks to this yet"
    for kind in profile.relevant_evidence_types[:4]:
        rows.append(Signal(name=kind, kind="EVIDENCE_TYPE", observed=observed,
                           why=f"{kind} is where a change in this business "
                               f"becomes visible from outside it"))
    return tuple(rows)


def _transmission(profile, facts: RecordFacts, archetype: str = ""):
    """Only channels with a mechanism into THIS business (§6).

    A channel the record reports but this business model has no mechanism
    for is dropped and named -- reporting the economy at a company it does
    not reach is the generic macro paragraph this product exists to not be.
    """
    if not profile.known:
        return (), ("this company's business model is not classified, so no "
                    "economic mechanism can be established")
    by_channel = {}
    for raw in facts.economic_ids:
        by_channel.setdefault(_channel_of(raw), []).append(str(raw))
    rows, dropped = [], []
    for channel, ids in sorted(by_channel.items()):
        mechanism = profile.transmission_for(channel)
        if not mechanism and channel == "POLICY_RATE":
            mechanism = profile.transmission_for("MARKET_RATE")
        if not mechanism:
            dropped.append(channel)
            continue
        variable = _CHANNEL_VARIABLE_BY_MODEL.get(
            (channel, profile.business_model_class),
            _CHANNEL_VARIABLE.get(channel, ""))
        if not variable:
            dropped.append(channel)
            continue
        # POINT AT THE DECISION THAT WAS ACTUALLY SELECTED.
        #
        # This used to name the first archetype the channel favours, which
        # for JPMorgan meant the rates paragraph on the deck ended "...a
        # decision about where the next increment of capital goes" while the
        # decision on slide 1 was pricing. Two answers to what is being
        # decided, on adjacent slides.
        favours = _CHANNEL_FAVOURS.get(channel, ())
        target = (archetype if archetype and archetype in favours else
                  next((a for a in favours
                        if a in profile.decision_archetypes), ""))
        implication = (
            f"track {variable}; it is the variable a decision about "
            f"{_ARCHETYPE_SUBJECT.get(target, 'this business')} would move "
            f"through" if target else
            f"track {variable} as the channel through which this condition "
            f"reaches the business")
        rows.append(Transmission(
            channel=channel, mechanism=mechanism, business_variable=variable,
            decision_implication=implication, observed_ids=tuple(ids)))
    if rows:
        return tuple(rows), ""
    if dropped:
        return (), (f"measured conditions were published "
                    f"({', '.join(sorted(set(dropped)))}) and none has an "
                    f"established mechanism into a business of this kind, so "
                    f"none is reported as an exposure")
    return (), ("the economy is measured and no condition reaches this "
                "company through an exposure its own evidence establishes")


def _causal(profile, archetype: str, facts: RecordFacts):
    """The one causal question this decision turns on.

    Chosen from (business model, archetype) -- the pair, because a pricing
    question at a bank and a pricing question at a consumer brand are
    different questions with different identification problems. Never
    chosen by scanning for the largest effect.
    """
    if not profile.known:
        return "", ("the business model is not classified, so no causal "
                    "question specific to it can be selected")
    from intent_engine.executive.company_profile import _CAUSAL
    question = _CAUSAL.get((profile.business_model_class, archetype))
    if not question:
        for candidate in profile.relevant_causal_questions:
            question = candidate
            break
    if not question:
        return "", ("no causal question is defined for this business model "
                    "and decision")
    return question, (
        f"selected because the decision in front of management is about "
        f"{_ARCHETYPE_SUBJECT.get(archetype, archetype)}, and this is the "
        f"question whose answer would change it; it was chosen from the "
        f"decision, never by looking for the largest measurable effect")


def _adversary(profile, archetype: str, facts: RecordFacts, rivals=()):
    """L0/L1/L2 against the nearest real competitor.

    QRE is not attempted: utilities cannot be defensibly populated from
    counts, and §10 says name that rather than fabricate a probability.

    THE SEAM THAT KEPT THIS OFF EVERY PAGE. This was gated on
    `profile.known`, which is True only for companies in the curated
    validation manifest. Measured across the 50-company gauntlet: the
    adversarial response appears on NO surface of ANY of the fifty, because
    almost none of them are in that manifest -- a complete L0/L1/L2 engine
    that ran for nobody.

    A rival established from the SUBJECT'S OWN FILING is not a lesser fact
    than a rival typed into the manifest; it is a better one. `rivals` is
    that list, already qualified as economic actors by
    `competitive_qualification`, and it is used when the manifest has
    nothing. Neither source invents a competitor: with no rival from either,
    this still returns nothing rather than reasoning against a placeholder.
    """
    selected = tuple(profile.strategic_competitors or ()) if profile.known \
        else ()
    if not selected:
        selected = tuple(rivals or ())
    if not selected:
        return ()
    rival = selected[0]
    lever = _ARCHETYPE_LEVER.get(archetype, "this decision")
    drivers = profile.primary_revenue_drivers or ("the revenue base",)
    evidence = (f"{rival.name} was selected because it {rival.why}"
                if rival.why else rival.name)
    watch = profile.relevant_evidence_types[:1]
    signal = watch[0] if watch else "public disclosure by the competitor"
    return (
        AdversaryMove(
            level="L0", actor=rival.name,
            objective="hold its existing position",
            action="continues its current course and does not react",
            rationale=("the move is below the threshold that would justify a "
                       "response, or is not visible to it in time"),
            evidence=evidence,
            observable_signal=f"no change in {signal}",
            impact=(f"the full effect of {lever} accrues, and {drivers[0]} "
                    f"moves by the amount the decision assumed"),
            countermeasure="none required",
            kill_switch=("none: this is the branch the decision is already "
                         "sized for")),
        AdversaryMove(
            level="L1", actor=rival.name,
            objective="defend the customers the move would take",
            action=f"responds directly to {lever} once it is visible",
            rationale=("it shares this business model, so the same move is "
                       "available to it at comparable cost"),
            evidence=evidence,
            observable_signal=f"a matching change appearing in {signal}",
            impact=(f"the gain on {drivers[0]} is partly competed away, and "
                    f"the industry ends at a worse position than it started"),
            countermeasure=("sequence the move so the response arrives after "
                            "the position is held, and size it to survive "
                            "being matched"),
            kill_switch=(f"if a matching response appears in {signal} before "
                         f"the position is established, stop the move rather "
                         f"than raising it")),
        AdversaryMove(
            level="L2", actor=rival.name,
            objective="take the position before it is contested",
            action=f"anticipates {lever} and moves first",
            rationale=("the same public evidence is available to it, and it "
                       "faces the same conditions at the same time"),
            evidence=evidence,
            observable_signal=(f"{signal} from the competitor BEFORE any "
                               f"move of ours"),
            impact=("the decision is being made into a market that has "
                    "already moved, so the assumptions under it are stale"),
            countermeasure=("re-establish the read before committing; treat "
                            "a pre-emptive move as evidence the window has "
                            "changed"),
            kill_switch=("if the competitor moves first, the decision returns "
                         "to the read rather than proceeding on the old one")),
    )


def _scenarios(profile, archetype: str, facts: RecordFacts,
               transmission) -> Tuple[Scenario, ...]:
    """One lever, four branches, traced to a kill switch.

    No invented numbers -- §11. Every branch is a direction and a mechanism,
    which is what is actually supportable from counts and classifications.
    """
    if not profile.known:
        return ()
    lever = _ARCHETYPE_LEVER.get(archetype, "the decision in front of you")
    drivers = profile.primary_revenue_drivers or ("the revenue base",)
    costs = profile.primary_cost_drivers or ("the cost base",)
    rival = (profile.strategic_competitors[0].name
             if profile.strategic_competitors else "the nearest competitor")
    exposure = (f"{transmission[0].business_variable} moves with "
                f"{transmission[0].channel.replace('_', ' ').lower()}"
                if transmission else
                "no measured economic condition reaches this decision through "
                "an established mechanism")
    leverage = profile.operating_leverage.split(":")[0] if \
        profile.operating_leverage != UNKNOWN else "UNKNOWN"
    return (
        Scenario(
            name="BASE", lever=lever,
            first_order=f"{drivers[0]} responds in the direction the decision "
                        f"assumes",
            second_order=f"{costs[0]} follows at the lag this business model "
                         f"imposes, so margin moves after volume does",
            third_order=("the position holds long enough to be measured "
                         "before anyone responds to it"),
            competitor_response=f"{rival} does not respond within the window",
            economic_exposure=exposure,
            outcome_range=("direction is supportable from the published "
                           "record; magnitude is not, and no figure is put "
                           "on it here"),
            kill_switch=("if the direction is not visible by the next review, "
                         "the assumption under the decision has failed")),
        Scenario(
            name="UPSIDE", lever=lever,
            first_order=f"{drivers[0]} responds further than assumed",
            second_order=(f"operating leverage reads {leverage}, so more of "
                          f"the gain reaches margin than reaches revenue"),
            third_order="the result funds the next commitment sooner",
            competitor_response=(f"{rival} responds late, by which point the "
                                 f"position is established"),
            economic_exposure=exposure,
            outcome_range="better than base, by an amount not measured here",
            kill_switch=("upside that appears without a mechanism behind it "
                         "should be treated as noise until it repeats")),
        Scenario(
            name="DOWNSIDE", lever=lever,
            first_order=f"{drivers[0]} does not respond",
            second_order=(f"{costs[0]} was committed anyway, so the cost "
                          f"lands without the revenue it was meant to serve"),
            third_order=("the capital and attention are unavailable for the "
                         "next decision"),
            competitor_response=f"{rival} is unaffected either way",
            economic_exposure=exposure,
            outcome_range="worse than base; the exposure is the committed cost",
            kill_switch=("stop at the point where the committed cost exceeds "
                         "what the decision was sized to lose")),
        Scenario(
            name="ADVERSARIAL", lever=lever,
            first_order=f"{rival} moves first or matches immediately",
            second_order=(f"the gain on {drivers[0]} is competed away while "
                          f"{costs[0]} stays committed"),
            third_order=("the industry settles at a worse position for every "
                         "participant, which is hard to reverse"),
            competitor_response="direct and immediate",
            economic_exposure=exposure,
            outcome_range=("the worst supportable branch; it is the one to "
                           "size the commitment against"),
            kill_switch=("withdraw rather than escalate: a matched move that "
                         "is raised again is how this branch becomes "
                         "permanent")),
    )


def select(company_id: str = "", *, name: str = "", domain: str = "",
           facts: Optional[RecordFacts] = None,
           profile: Optional[CompanyIntelligenceProfile] = None,
           manifest=None, registrant=None,
           evidence_text: str = "", published_text: str = "",
           rivals=()) -> AnalysisSelection:
    """Choose this company's analysis. Deterministic, no model call.

    `registrant` is the SEC's classification of this filer, used only when
    the company is outside the validation manifest -- see `profile_for`.
    `evidence_text` is that company's own filing text, used only to correct
    an industry code that covers two different businesses. `published_text`
    is that company's own published material more broadly -- pages as well as
    filings -- and is consulted ONLY when neither the manifest nor an
    industry code produced a classification, which is every private company.
    Both are pass-through to `profile_for`, which owns the ordering.
    """
    facts = facts or RecordFacts()
    if profile is None:
        profile = profile_for(company_id, name=name, domain=domain,
                              manifest=manifest, registrant=registrant,
                              evidence_text=evidence_text,
                              published_text=published_text)
    # THE COMPANY'S OWN WORDS REACH THE ORDERING, NOT ONLY THE
    # CLASSIFICATION. `evidence_text` is its filing text and `published_text`
    # its wider published material; both were already accepted here and spent
    # entirely on deciding WHAT KIND of business this is.
    _own = " ".join(t for t in (evidence_text, published_text) if t)
    considered = (_score_archetypes(profile, facts, own_text=_own)
                  if profile.known else ())
    archetype = considered[0]["archetype"] if considered else UNKNOWN
    why = (considered[0]["why"] if considered else
           (profile.profile_limitation or
            "this company's business model is not classified, so the "
            "analysis is selected from the published record alone and is "
            "not specific to its economics"))
    if considered and len(considered) > 1:
        # Ends with a full stop: this string is rendered on its own in the
        # X-Ray's "Why this decision" panel, where the missing one showed.
        why = (f"{why}. It was ranked above "
               f"{considered[1]['archetype'].replace('_', ' ').lower()} on "
               f"the same evidence.")
    # THE COMPANY'S OWN DECISION VARIABLES. Built from the same two texts
    # the classifier already reads, so this adds no retrieval and no model
    # call; it spends text that was previously used only to decide what KIND
    # of business this is on deciding what the question is MEASURED IN.
    objects = _decision_object.build(
        company=profile.company_name or name or company_id,
        evidence_text=evidence_text, published_text=published_text)
    transmission, no_exposure = _transmission(profile, facts, archetype)
    causal_question, why_causal = _causal(profile, archetype, facts)
    # THE COMPARATOR IS A REAL SECOND STATE, not a placeholder. Running the
    # same builder with `objects=None` is exactly "what would the class prior
    # alone have said", so the delta measures the difference between two
    # readings this code actually produces rather than against a constant.
    question = _decision_question(profile, archetype, facts, objects)
    prior_question = _decision_question(profile, archetype, facts, None)
    _terms = ()
    if considered:
        _terms = tuple((considered[0].get("contributions") or {}).get(
            "evidence_terms") or ())
    delta = _strategic_delta.build_delta(
        company=profile.company_name or name or company_id,
        selection=_Preview(archetype=archetype, decision_question=question,
                           considered=considered),
        prior_question=prior_question, prior_archetype=archetype,
        decision_object=objects, evidence_terms=_terms)
    priorities = _strategic_delta.information_priorities(
        company=profile.company_name or name or company_id,
        selection=_Preview(archetype=archetype, decision_question=question,
                           considered=considered),
        decision_object=objects, delta=delta)
    return AnalysisSelection(
        company_id=profile.company_id or company_id,
        company_name=profile.company_name or name or company_id,
        profile=profile,
        archetype=archetype,
        why_this_question=why,
        considered=considered,
        decision_question=question,
        decision_object=objects,
        question_basis=question_basis(profile, archetype, objects),
        delta=delta,
        information_priorities=priorities,
        signals=_signals(profile, facts),
        transmission=transmission,
        no_exposure_reason=no_exposure,
        causal_question=causal_question,
        why_this_causal_question=why_causal,
        historical_dimensions=profile.relevant_historical_dimensions,
        adversary=_adversary(profile, archetype, facts,
                             rivals=rivals),
        scenarios=_scenarios(profile, archetype, facts, transmission),
    )

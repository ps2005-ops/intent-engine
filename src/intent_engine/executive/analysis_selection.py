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
from typing import Optional, Tuple

from intent_engine.executive.company_profile import (UNKNOWN,
                                                     CompanyIntelligenceProfile,
                                                     profile_for)

CONTRACT = "analysis_selection.v1"

#: What each archetype is a decision ABOUT, in the second person a CEO uses.
#: The wording carries the lever, so the question below is a decision and not
#: a topic.
_ARCHETYPE_SUBJECT = {
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


def _score_archetypes(profile, facts: RecordFacts):
    """Rank this business's decision archetypes against what is known.

    The MENU comes from the business model -- a bank does not choose between
    inventory and certification -- and the ORDER comes from the evidence. So
    two banks share a menu, and a bank and a software company share almost
    nothing, which is the specialisation this is for.
    """
    live_channels = {_channel_of(i) for i in facts.economic_ids}
    rows = []
    menu = profile.decision_archetypes or ()
    for position, archetype in enumerate(menu):
        # BASE: the model class's own ordering. For a commodity producer
        # capital allocation leads; for a software company pricing does.
        score = len(menu) - position
        reasons = [f"{_ARCHETYPE_SUBJECT.get(archetype, archetype)} is a "
                   f"standing decision for this business model"]
        for channel in sorted(live_channels):
            if archetype in _CHANNEL_FAVOURS.get(channel, ()):
                score += 4
                reasons.append(
                    f"measured {channel.replace('_', ' ').lower()} conditions "
                    f"reach this business and bear directly on it")
        if facts.hidden_state and facts.hidden_state not in (
                "TRACKED_NO_IDENTIFIED_STATE", "HIDDEN_STATE_NOT_RUN",
                "HIDDEN_STATE_NONE_TRACKED"):
            if archetype in ("COMPETITIVE_RESPONSE", "PRICING"):
                score += 3
                reasons.append(
                    "the operating posture has been identified, which is what "
                    "a response would be responding to")
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
        rows.append({"archetype": archetype, "score": score,
                     "subject": _ARCHETYPE_SUBJECT.get(archetype, archetype),
                     "why": "; ".join(reasons)})
    rows.sort(key=lambda r: (-r["score"], r["archetype"]))
    return tuple(rows)


def _decision_question(profile, archetype: str, facts: RecordFacts) -> str:
    """The question, in this business's own variables.

    Composed from the archetype's subject and the driver the archetype acts
    on, so a pricing question at a bank names the spread and a pricing
    question at a consumer brand names promotional depth.
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
    tail = {
        "PRICING": f"without losing more {driver} than the price gains",
        "CAPACITY": f"given that {cost} is committed before the {driver} it "
                    f"is meant to serve arrives",
        "CAPITAL_ALLOCATION": f"given what the same capital would earn "
                              f"against {driver} elsewhere",
        "COST_STRUCTURE": f"without cutting into the {driver} the cost base "
                          f"exists to produce",
        "SUPPLY_CHAIN": f"given that {cost} sets what can actually be "
                        f"delivered",
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
        "INVENTORY": f"given that the position is set before {driver} is "
                     f"known",
        "COMPETITIVE_RESPONSE": f"before the move reaches {driver}",
        "M&A": f"measured against building the same {driver} internally",
    }.get(archetype, "")
    return (f"For {name}: {subject}, {tail}?" if tail
            else f"For {name}: {subject}?")


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


def _adversary(profile, archetype: str, facts: RecordFacts):
    """L0/L1/L2 against the nearest real competitor.

    Built only where a competitor was actually selected. QRE is not
    attempted: utilities cannot be defensibly populated from counts, and
    §10 says name that rather than fabricate a probability.
    """
    if not profile.known or not profile.strategic_competitors:
        return ()
    rival = profile.strategic_competitors[0]
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
           manifest=None) -> AnalysisSelection:
    """Choose this company's analysis. Deterministic, no model call."""
    facts = facts or RecordFacts()
    if profile is None:
        profile = profile_for(company_id, name=name, domain=domain,
                              manifest=manifest)
    considered = _score_archetypes(profile, facts) if profile.known else ()
    archetype = considered[0]["archetype"] if considered else UNKNOWN
    why = (considered[0]["why"] if considered else
           "this company's business model is not classified in the "
           "validation manifest, so the analysis is selected from the "
           "published record alone and is not specific to its economics")
    if considered and len(considered) > 1:
        why = (f"{why}. It was ranked above "
               f"{considered[1]['archetype'].replace('_', ' ').lower()} "
               f"on the same evidence")
    transmission, no_exposure = _transmission(profile, facts, archetype)
    causal_question, why_causal = _causal(profile, archetype, facts)
    return AnalysisSelection(
        company_id=profile.company_id or company_id,
        company_name=profile.company_name or name or company_id,
        profile=profile,
        archetype=archetype,
        why_this_question=why,
        considered=considered,
        decision_question=_decision_question(profile, archetype, facts),
        signals=_signals(profile, facts),
        transmission=transmission,
        no_exposure_reason=no_exposure,
        causal_question=causal_question,
        why_this_causal_question=why_causal,
        historical_dimensions=profile.relevant_historical_dimensions,
        adversary=_adversary(profile, archetype, facts),
        scenarios=_scenarios(profile, archetype, facts, transmission),
    )

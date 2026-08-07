"""Evidence proposes a belief — and the belief must say what it expects to see.

WHY THIS EXISTS
---------------
`learning_cycle.run` was handed evidence and a store, and revised whatever
beliefs the store already held. Nothing anywhere created the first one. So
production could translate perfect evidence for twenty-eight companies and
still report `belief_knowledge_gain: 0`, because there was no belief for the
evidence to be about. Learning was gated on a bootstrap that never happened.

WHAT A CANDIDATE BELIEF IS
--------------------------
A proposition about how a company is behaving, attached to the evidence that
proposed it and to an observation that would show it to be wrong. "The company
is changing", "growth may happen" and "the market is uncertain" are not
candidates here and cannot be: a family without an expectation template does
not exist, so every belief this module can produce is one somebody could
later be shown to have got wrong.

THE DIRECTION IS READ, NOT FELT
-------------------------------
A price cut and a price rise are the same evidence TYPE and opposite
strategic facts. The direction comes from explicit markers in the sentence
("increased", "lowered", "cut") — never from how the sentence sounds. A
sentence carrying a type but no direction marker proposes nothing, which is
the honest answer: the engine saw a pricing event and does not know which way.

A COMPANY MAY NOT TALK ITSELF INTO A STRUCTURAL BELIEF
------------------------------------------------------
Structural claims — capacity, productisation, capital posture — are SLOW
beliefs, and a single company-authored item cannot open one. Company material
is the most abundant source class by an order of magnitude, so without this
rule a company could install beliefs about itself in this engine simply by
publishing more press releases. Fast-moving families are allowed on one item
but their prior stays near uncertainty.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import beliefs as B
from . import expectation as EXP
from . import micro_evidence as ME

FORMATION_VERSION = "belief_formation.v1"

# --- direction markers ----------------------------------------------------
# Explicit words in the sentence. Not sentiment, not tone, not inference.
_UP = re.compile(
    r"\b(increas\w+|ros\w*e|rise|risen|grew|grow\w*|higher|up \d|"
    r"gain\w*|expand\w+|rais\w+|surpass\w+|exceed\w+|beat|record|"
    r"strong\w*|accelerat\w+|added|more than)\b", re.I)
_DOWN = re.compile(
    r"\b(decreas\w+|declin\w+|fell|fall\w*|lower\w+|down \d|loss\w*|"
    r"cut|cuts|reduc\w+|weak\w*|slow\w+|miss\w+|shortfall|"
    r"contract\w*ed|shrank|shrunk)\b", re.I)


def direction_of(text: str) -> str:
    """UP, DOWN or "" — read off the words, never inferred from tone."""
    up, down = bool(_UP.search(text or "")), bool(_DOWN.search(text or ""))
    if up and not down:
        return EXP.UP
    if down and not up:
        return EXP.DOWN
    return ""


@dataclass(frozen=True)
class Family:
    """One belief family: what it claims, and what it commits to seeing."""
    key: str
    proposition: str                  # "{subject} ..." — formatted per company
    learning_speed: str
    expected_event: str
    expected_direction: str
    falsifier: str
    window_days: int
    limitation: str
    #: SLOW families are structural and need more than one company press
    #: release before they may be declared at all.
    structural: bool = False


# --- the families ---------------------------------------------------------
#
# Every proposition below is a behaviour, not a mood, and every one names an
# observation that would refute it. If a family cannot state its falsifier it
# does not belong here.
FAMILIES: Dict[str, Family] = {f.key: f for f in (
    Family("demand_strengthening",
           "{subject} is seeing demand strengthen rather than plateau",
           B.MEDIUM,
           "the next reported revenue or guidance figure",
           EXP.UP,
           "the next reported revenue or guidance figure comes in flat or "
           "lower than the one that proposed this belief",
           120,
           "one period's result is a data point, not a trend"),
    Family("demand_weakening",
           "{subject} is seeing demand weaken rather than pause",
           B.MEDIUM,
           "the next reported revenue or guidance figure",
           EXP.DOWN,
           "the next reported revenue or guidance figure is flat or higher",
           120,
           "one period's result is a data point, not a trend"),
    Family("pricing_power",
           "{subject} is exercising pricing power rather than defending "
           "volume",
           B.MEDIUM,
           "further price increases, or margin holding as volumes soften",
           EXP.UP,
           "a subsequent price cut, discounting programme, or margin "
           "compression attributed to pricing",
           180,
           "a single price move can be a mix change rather than a posture"),
    Family("market_share_seeking",
           "{subject} is buying market share with price rather than "
           "protecting margin",
           B.MEDIUM,
           "further price reductions, bundling, or acquisition-led messaging",
           EXP.UP,
           "prices are raised again, or margin protection is stated as the "
           "priority",
           180,
           "a discount can be inventory clearance rather than a strategy"),
    Family("capacity_expansion",
           "{subject} is committing capital to capacity ahead of the demand "
           "for it",
           B.SLOW,
           "further capital commitments, or the capacity coming online",
           EXP.UP,
           "the programme is paused, cancelled, or capital spending is cut",
           365,
           "announced capital is not spent capital",
           True),
    Family("capital_return_posture",
           "{subject} is prioritising returning capital over reinvesting it",
           B.SLOW,
           "further dividend increases or buyback authorisations",
           EXP.UP,
           "the dividend is held or cut, or capital is redirected into "
           "capacity or acquisitions",
           365,
           "returning capital and investing are not always exclusive",
           True),
    Family("productization",
           "{subject} is converting delivered work into repeatable product",
           B.SLOW,
           "further product launches or general-availability announcements",
           EXP.UP,
           "the offering is withdrawn, or delivery moves back toward "
           "bespoke engagements",
           365,
           "a launch is a claim about intent, not about adoption",
           True),
    Family("procurement_momentum",
           "{subject} is converting procurement processes into awards in its "
           "category",
           B.MEDIUM,
           "further contract awards or task orders",
           EXP.UP,
           "a subsequent competitive loss, or an award to a rival in the "
           "same programme",
           180,
           "one award does not establish a pattern of winning"),
    Family("partner_led_distribution",
           "{subject} is reaching its market through partners rather than "
           "only directly",
           B.SLOW,
           "further partnership or joint-venture announcements",
           EXP.UP,
           "a partnership is ended, or distribution is brought back "
           "in-house",
           365,
           "an announced partnership is not a revenue channel yet",
           True),
    Family("consolidation_posture",
           "{subject} is buying capability rather than building it",
           B.SLOW,
           "further acquisitions or divestitures",
           EXP.UP,
           "an acquisition is abandoned, or the company states a build-first "
           "priority",
           365,
           "one transaction is not a programme",
           True),
    Family("margin_protection",
           "{subject} is protecting margin by taking cost out rather than "
           "growing into it",
           B.MEDIUM,
           "further cost reductions, or margin holding while revenue is flat",
           EXP.UP,
           "headcount and spending resume growing before margin improves",
           180,
           "a reduction can be a reorganisation rather than a cost posture"),
    Family("capacity_hiring",
           "{subject} is adding people ahead of the work they will do",
           B.MEDIUM,
           "further hiring, or revenue per employee falling",
           EXP.UP,
           "hiring is frozen or reversed within the window",
           180,
           "job postings are intent, not headcount"),
    Family("regulatory_pressure",
           "{subject} is operating under active regulatory pressure",
           B.SLOW,
           "further regulatory actions, filings, or disclosed proceedings",
           EXP.UP,
           "the matter is closed, dismissed, or settled without ongoing "
           "obligations",
           365,
           "an investigation is not a finding",
           True),
    Family("supply_constraint",
           "{subject} is constrained by its suppliers rather than by demand",
           B.MEDIUM,
           "further supplier commentary on lead times or shortages",
           EXP.UP,
           "lead times normalise, or the company attributes shortfalls to "
           "demand instead",
           180,
           "supplier commentary is about the supplier's book, not this "
           "company's"),
    Family("competitor_aggression",
           "{subject} faces a rival competing on price or capability rather "
           "than coexisting",
           B.MEDIUM,
           "further competitor moves in the same segment",
           EXP.UP,
           "the rival withdraws, raises prices, or exits the segment",
           180,
           "a competitor's action is not always aimed at this company"),
    Family("leadership_transition",
           "{subject} is going through a leadership transition that will "
           "change what it prioritises",
           B.MEDIUM,
           "a named successor, or a stated change of priorities",
           EXP.UP,
           "the role is filled by an internal continuity appointment with no "
           "stated change of direction",
           180,
           "a board departure need not change operating strategy"),
)}

# --- evidence type -> family ---------------------------------------------
#
# `None` in the direction slot means the family applies whichever way the
# evidence points. A tuple means the family applies only for that direction,
# and evidence with no readable direction proposes nothing.
_ROUTES: Tuple[Tuple[str, str, Optional[str]], ...] = (
    (ME.EARNINGS_RESULT, "demand_strengthening", EXP.UP),
    (ME.EARNINGS_RESULT, "demand_weakening", EXP.DOWN),
    (ME.EARNINGS_SURPRISE, "demand_strengthening", EXP.UP),
    (ME.EARNINGS_SURPRISE, "demand_weakening", EXP.DOWN),
    (ME.GUIDANCE_REVISION, "demand_strengthening", EXP.UP),
    (ME.GUIDANCE_REVISION, "demand_weakening", EXP.DOWN),
    (ME.PRICING_SIGNAL, "pricing_power", EXP.UP),
    (ME.PRICING_SIGNAL, "market_share_seeking", EXP.DOWN),
    (ME.PRICE_CHANGE, "pricing_power", EXP.UP),
    (ME.PRICE_CHANGE, "market_share_seeking", EXP.DOWN),
    (ME.CAPEX_SIGNAL, "capacity_expansion", None),
    (ME.CAPITAL_RETURN, "capital_return_posture", None),
    (ME.PRODUCT_LAUNCH, "productization", None),
    (ME.CONTRACT_AWARD, "procurement_momentum", None),
    (ME.PROCUREMENT_SIGNAL, "procurement_momentum", None),
    (ME.PARTNERSHIP, "partner_led_distribution", None),
    (ME.MA_ACTIVITY, "consolidation_posture", None),
    (ME.LAYOFF, "margin_protection", None),
    (ME.HIRING, "capacity_hiring", None),
    (ME.REGULATORY_ACTION, "regulatory_pressure", None),
    (ME.SUPPLIER_COMMENT, "supply_constraint", None),
    (ME.COMPETITOR_ACTION, "competitor_aggression", None),
    (ME.EXECUTIVE_CHANGE, "leadership_transition", None),
    (ME.INVENTORY_CHANGE, "demand_weakening", EXP.UP),
    (ME.INVENTORY_CHANGE, "demand_strengthening", EXP.DOWN),
    # Committed demand reads the same way round as revenue and the OPPOSITE
    # way from inventory: a rising order book is demand customers have signed
    # for, whereas rising inventory is goods nobody has bought yet. Routed in
    # BOTH directions so it lands in a falsifiable family and can be tested by
    # `observation_binding` rather than only ever proposing beliefs.
    (ME.COMMITTED_DEMAND, "demand_strengthening", EXP.UP),
    (ME.COMMITTED_DEMAND, "demand_weakening", EXP.DOWN),
    # A tariff is a margin event before it is anything else. Occurrence-only:
    # the absence of a tariff disclosure refutes nothing, so this family stays
    # outside the falsifiable set on purpose -- binding it would build a
    # channel that can only confirm.
    (ME.COST_SHOCK, "margin_protection", None),
)

#: a structural family needs this much independent-equivalent evidence, or a
#: source that is not the subject talking about itself
MIN_STRUCTURAL_ITEMS = 2
#: the most a first declaration may claim. A belief opened by one press
#: release starts barely off the fence, and has to earn the rest.
MAX_INITIAL_PRIOR = 0.68
BASE_PRIOR = 0.55
#: a belief supported only by the subject's own material cannot start above
#: this, whatever the volume
SELF_AUTHORED_CEILING = 0.58


@dataclass
class Candidate:
    """A belief the evidence proposes, and the expectation it commits to."""
    belief: B.StrategicBelief
    expectation: Optional[EXP.ExpectedObservation]
    family: str
    evidence_ids: Tuple[str, ...]
    self_authored_only: bool

    def as_dict(self) -> dict:
        return {"belief_id": self.belief.belief_id, "family": self.family,
                "proposition": self.belief.proposition,
                "subject": self.belief.subject,
                "prior": self.belief.prior_probability,
                "evidence_ids": list(self.evidence_ids),
                "self_authored_only": self.self_authored_only,
                "expectation_id": (self.expectation.expectation_id
                                   if self.expectation else "")}


def belief_id_for(subject: str, family: str) -> str:
    """Deterministic, so the same proposition is never opened twice.

    Keyed on subject and family only — deliberately NOT on the evidence. The
    second contract award is more support for one belief about procurement
    momentum, not a second belief that says the same thing.
    """
    raw = f"{subject.strip().lower()}|{family}"
    return "bel_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def routes_for(item: ME.MicroEvidence) -> List[str]:
    """The families this one item could propose, given what it says."""
    direction = direction_of(item.fact)
    out = []
    for etype, family, required in _ROUTES:
        if etype != item.evidence_type:
            continue
        if required is not None and direction != required:
            continue
        out.append(family)
    return out


def propose(evidence: Sequence[ME.MicroEvidence], *, as_of: str,
            existing: Sequence[B.StrategicBelief] = ()
            ) -> Tuple[List[Candidate], Dict[str, int]]:
    """Candidate beliefs from evidence. Returns (candidates, why-not counts).

    The refusal counts are returned rather than dropped, because "no belief
    formed" has several causes — no direction in the text, a structural claim
    resting on the company's own word, a belief that already exists — and an
    operator reading a zero deserves to know which.
    """
    known = {b.belief_id for b in existing}
    grouped: Dict[Tuple[str, str], List[ME.MicroEvidence]] = {}
    refused: Dict[str, int] = {}

    def refuse(reason: str) -> None:
        refused[reason] = refused.get(reason, 0) + 1

    for item in ME.deduplicate(evidence):
        families = routes_for(item)
        if not families:
            # Either the type routes nowhere, or it routes only on a
            # direction this sentence does not state.
            refuse("no_family" if not any(
                e == item.evidence_type for e, _, _ in _ROUTES)
                else "no_direction_stated")
            continue
        for family in families:
            grouped.setdefault((item.subject_company, family), []).append(item)

    out: List[Candidate] = []
    for (subject, family), items in sorted(grouped.items()):
        spec = FAMILIES[family]
        bid = belief_id_for(subject, family)
        if bid in known:
            refuse("belief_already_declared")
            continue
        self_only = all(i.self_authored for i in items)
        if spec.structural and self_only and len(items) < MIN_STRUCTURAL_ITEMS:
            # One press release may not open a structural belief about the
            # company that published it.
            refuse("structural_claim_on_self_authored_evidence")
            continue

        ess = B.design_effect(items)
        prior = min(MAX_INITIAL_PRIOR, BASE_PRIOR + 0.04 * ess)
        if self_only:
            prior = min(prior, SELF_AUTHORED_CEILING)
        limitations = [spec.limitation]
        if self_only:
            limitations.append(
                "every supporting item is authored by the subject; this is "
                "the company's own account of itself")
        belief = B.create(
            belief_id=bid, proposition=spec.proposition.format(subject=subject),
            subject=subject, prior=round(prior, 4), at=as_of,
            learning_speed=spec.learning_speed,
            confidence_basis=(
                f"opened by {len(items)} translated evidence item(s) of type "
                # Rounded because this string is read by a founder, not by a
                # calculation: "effective sample 1.4722" spends four digits of
                # apparent precision on an estimate of how much four
                # correlated items are really worth.
                f"{items[0].evidence_type}, effective sample "
                f"{ess:.2f}"),
            review_interval_days=spec.window_days,
            limitations=limitations,
            supporting_evidence_ids=tuple(i.evidence_id for i in items))
        ids = tuple(i.evidence_id for i in items)
        out.append(Candidate(
            belief=belief,
            expectation=_expectation_for(spec, belief, as_of=as_of,
                                         evidence=items),
            family=family, evidence_ids=ids, self_authored_only=self_only))
        known.add(bid)
    return out, refused


def _expectation_for(spec: Family, belief: B.StrategicBelief, *, as_of: str,
                     evidence: Sequence[ME.MicroEvidence]
                     ) -> Optional[EXP.ExpectedObservation]:
    """Commit to what this belief expects to see, before it sees it.

    `preregistered_at` is the session date and the window opens from there,
    so an expectation cannot be written against an observation that already
    arrived. `EXP.preregister` refuses a window that closes before it opens
    and refuses an expectation with no falsifier.
    """
    from datetime import date, timedelta
    try:
        ends = (date.fromisoformat(as_of[:10])
                + timedelta(days=spec.window_days)).isoformat()
    except (TypeError, ValueError):
        return None
    try:
        return EXP.preregister(
            hypothesis_id=belief.belief_id, subject=belief.subject,
            expected_event=spec.expected_event,
            expected_direction=spec.expected_direction,
            preregistered_at=as_of[:10], evaluation_window_ends=ends,
            falsifier=spec.falsifier,
            metric=spec.key,
            evidence_basis=tuple(i.evidence_id for i in evidence),
            relevant_actors=(belief.subject,),
            uncertainty=round(1.0 - belief.prior_probability, 4))
    except EXP.ExpectationRejected:
        return None


def summarise(candidates: Sequence[Candidate],
              refused: Optional[Dict[str, int]] = None) -> dict:
    """Bounded counts for the cycle report."""
    by_family: Dict[str, int] = {}
    for c in candidates:
        by_family[c.family] = by_family.get(c.family, 0) + 1
    return {
        "contract": FORMATION_VERSION,
        "candidates": len(candidates),
        "expectations": sum(1 for c in candidates if c.expectation),
        "by_family": dict(sorted(by_family.items())),
        "self_authored_only": sum(1 for c in candidates
                                  if c.self_authored_only),
        "subjects": sorted({c.belief.subject for c in candidates}),
        "refused": dict(sorted((refused or {}).items())),
    }

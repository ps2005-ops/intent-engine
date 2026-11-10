"""§11-§14/§18/§20/§22: the live economic world model, and what it changes.

WHAT THIS IS FOR
----------------
The historical human-state programme is frozen. That is not a reason to stop:
the economic world model is a separate claim and it can be demonstrated
without any psychology in it. The demonstration that matters is narrow and
falsifiable —

    THE SAME ECONOMIC STATE MUST PRODUCE DIFFERENT, TRACEABLE IMPLICATIONS
    FOR DIFFERENT COMPANIES.

Six copies of "consumers are cautious" is the failure mode, and it is the
default one: a template that reads the state, notices demand is weak, and
prints the same paragraph under six names. `DecisionDelta` is the measurement
that makes that visible, and `assert_company_specific` is the refusal.

THE DOUBLE-COUNTING WALL
------------------------
A signal derived FROM company evidence cannot then corroborate that same
evidence. Every derived reading carries `depends_on`, and `assert_no_double_
count` walks it. This is the same lesson the historical programme learned as
pseudo-replication, applied to lineage instead of to time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_worldmodel.v1"

OBSERVED, INFERRED, UNKNOWN = "OBSERVED", "INFERRED", "UNKNOWN"
STANDINGS = (OBSERVED, INFERRED, UNKNOWN)


class WorldModelDefect(EconError):
    """The world model produced something it is not entitled to."""


# =============================================================================
# §11 COVERAGE AUDIT
# =============================================================================

@dataclass(frozen=True)
class DimensionAudit:
    """One economic dimension, and whether anything actually measures it."""

    dimension: str
    producer: str
    source: str
    frequency: str
    as_of: str
    freshness_days: Optional[int]
    persisted: bool
    consumer: Sequence[str]
    standing: str
    uncertainty: str = ""
    note: str = ""

    @property
    def live(self) -> bool:
        return (self.standing == OBSERVED and self.freshness_days is not None
                and self.freshness_days <= 400)

    @property
    def status(self) -> str:
        if self.standing == UNKNOWN:
            return "BLOCKED"
        if self.live:
            return "LIVE"
        return "PARTIAL"

    def as_dict(self) -> dict:
        return {"dimension": self.dimension, "producer": self.producer,
                "source": self.source, "frequency": self.frequency,
                "as_of": self.as_of, "freshness_days": self.freshness_days,
                "persisted": self.persisted, "consumer": list(self.consumer),
                "standing": self.standing, "status": self.status,
                "uncertainty": self.uncertainty, "note": self.note}


#: The dimensions §11 names, mapped to the panel series that would measure
#: them. A dimension with no series is BLOCKED and says so; it does not
#: quietly vanish from the denominator.
DIMENSIONS = {
    "growth": ("INDPRO", "PCEC96"),
    "inflation": ("CPIAUCSL",),
    "labour": ("UNRATE", "U6RATE", "EMRATIO", "CIVPART", "UEMP15OV"),
    "liquidity": (),
    "funding": ("T10Y3M",),
    "policy_rates": ("DFF",),
    "real_rates": (),
    "yield_curve": ("DGS2", "DGS10", "T10Y3M"),
    "credit": ("BAA10Y", "AAA10Y", "BAA", "DRCCLACBS", "CORCACBS"),
    "fx": (),
    "commodities": (),
    "volatility": (),
    "risk_appetite": ("BAA10Y",),
    "positioning": (),
    "housing": ("HOUST", "PERMIT", "MORTGAGE30US", "HSN1F"),
    "household_balance_sheet": ("PSAVERT", "REVOLSL", "TDSP"),
    "sentiment": ("UMCSENT", "MICH"),
}

#: Which dimensions a company decision actually turns on, highest first.
#: Used to rank gaps by DECISION IMPACT rather than by how easy they are.
DECISION_IMPACT = {
    "policy_rates": 5, "credit": 5, "labour": 5, "growth": 5,
    "inflation": 4, "housing": 4, "yield_curve": 4,
    "household_balance_sheet": 3, "funding": 3, "risk_appetite": 3,
    "commodities": 3, "fx": 3, "sentiment": 2, "volatility": 2,
    "real_rates": 2, "liquidity": 2, "positioning": 1,
}


def audit_dimensions(panel, *, as_of: str) -> Dict[str, DimensionAudit]:
    """What the world model measures, per dimension, with its freshness."""
    import datetime as _dt
    out = {}
    for dim, series in sorted(DIMENSIONS.items()):
        readable = []
        latest = ""
        for sid in series:
            h = panel.history(sid, as_of=as_of, lookback=2)
            if h:
                readable.append(sid)
                latest = max(latest, h[-1][0])
        if not readable:
            out[dim] = DimensionAudit(
                dimension=dim, producer="", source="", frequency="",
                as_of="", freshness_days=None, persisted=False,
                consumer=("EconomicState",), standing=UNKNOWN,
                note=("no series in this panel measures it. BLOCKED, not "
                      "absent: the dimension stays in the denominator."))
            continue
        days = None
        if latest:
            days = (_d(as_of) - _d(latest)).days
        out[dim] = DimensionAudit(
            dimension=dim, producer="econ.panel", source="ALFRED/FRED",
            frequency="mixed", as_of=latest, freshness_days=days,
            persisted=True,
            consumer=("EconomicState", "CompanyEconomicState",
                      "founder_view"),
            standing=OBSERVED,
            uncertainty=f"{len(readable)} of {len(series)} series readable",
            note=f"from {readable}")
    return out


def _d(s: str):
    import datetime as _dt
    return _dt.date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def rank_gaps(audit: Dict[str, DimensionAudit]) -> List[dict]:
    """Gaps ordered by DECISION IMPACT, not by how easy they are to fix."""
    rows = []
    for dim, a in audit.items():
        if a.status == "LIVE":
            continue
        rows.append({"dimension": dim, "status": a.status,
                     "decision_impact": DECISION_IMPACT.get(dim, 1),
                     "why": a.note})
    return sorted(rows, key=lambda r: (-r["decision_impact"], r["dimension"]))


# =============================================================================
# §12/§13 TYPED CROSS-ASSET RELATIONSHIPS AND MULTI-ORDER TRANSMISSION
# =============================================================================

@dataclass(frozen=True)
class Relation:
    """One typed cross-asset relationship. Not a macro sentence."""

    driver: str
    effect: str
    sign: int
    mechanism: str
    lag_days: int
    uncertainty: str
    regime: str
    falsifier: str
    evidence: str
    order: int = 1

    def __post_init__(self) -> None:
        require(self.sign in (1, -1), "a relation has a direction")
        require(bool(self.falsifier.strip()),
                f"{self.driver}->{self.effect}: a relation that cannot be "
                "wrong is a slogan")
        require(bool(self.mechanism.strip()),
                f"{self.driver}->{self.effect}: state the path, not the "
                "correlation")

    def as_dict(self) -> dict:
        return {"driver": self.driver, "effect": self.effect,
                "sign": self.sign, "mechanism": self.mechanism,
                "lag_days": self.lag_days, "uncertainty": self.uncertainty,
                "regime": self.regime, "falsifier": self.falsifier,
                "evidence": self.evidence, "order": self.order}


@dataclass(frozen=True)
class TransmissionPath:
    """An ordered chain, with every step persisted."""

    name: str
    shock: str
    steps: Tuple[Relation, ...]

    def __post_init__(self) -> None:
        require(len(self.steps) >= 2,
                f"{self.name}: a transmission path has at least two steps, "
                "or it is a relation")
        for a, b in zip(self.steps, self.steps[1:]):
            if a.effect != b.driver:
                raise WorldModelDefect(
                    f"{self.name} is broken: {a.effect!r} does not feed "
                    f"{b.driver!r}. Recording only the endpoints loses every "
                    "place the chain could break, which is the only useful "
                    "thing the chain contains.")

    @property
    def total_lag_days(self) -> int:
        return sum(s.lag_days for s in self.steps)

    @property
    def net_sign(self) -> int:
        n = 1
        for s in self.steps:
            n *= s.sign
        return n

    @property
    def weakest_step(self) -> Relation:
        rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return max(self.steps, key=lambda s: rank.get(s.uncertainty, 1))

    def as_dict(self) -> dict:
        return {"name": self.name, "shock": self.shock,
                "steps": [s.as_dict() for s in self.steps],
                "orders": len(self.steps),
                "total_lag_days": self.total_lag_days,
                "net_sign": self.net_sign,
                "weakest_step": self.weakest_step.as_dict()}


# =============================================================================
# §14 CAUSAL BLEEDS
# =============================================================================

@dataclass(frozen=True)
class Bleed:
    """A link that should have fired and did not."""

    source: str
    expected_target: str
    expected_timing_days: int
    expected_direction: str
    actual_direction: str
    transmission_gap: float
    candidate_explanation: str
    evidence: str
    uncertainty: str
    controllability: str
    decision_impact: int

    @property
    def occurred(self) -> bool:
        return self.expected_direction != self.actual_direction

    @property
    def priority(self) -> float:
        c = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}
        u = {"LOW": 1.0, "MEDIUM": 0.6, "HIGH": 0.3}
        return round(self.decision_impact * c.get(self.controllability, 0.3)
                     * u.get(self.uncertainty, 0.3), 3)

    def statement(self) -> str:
        return (f"{self.source} -> {self.expected_target}: expected "
                f"{self.expected_direction} within "
                f"{self.expected_timing_days}d, observed "
                f"{self.actual_direction}. Gap "
                f"{self.transmission_gap:+.3f}. CANDIDATE explanation: "
                f"{self.candidate_explanation}. This is a measured "
                f"non-response, NOT a demonstrated cause.")

    def as_dict(self) -> dict:
        return {"source": self.source, "expected_target": self.expected_target,
                "expected_timing_days": self.expected_timing_days,
                "expected_direction": self.expected_direction,
                "actual_direction": self.actual_direction,
                "transmission_gap": round(self.transmission_gap, 5),
                "candidate_explanation": self.candidate_explanation,
                "evidence": self.evidence, "uncertainty": self.uncertainty,
                "controllability": self.controllability,
                "decision_impact": self.decision_impact,
                "occurred": self.occurred, "priority": self.priority,
                "status": "CANDIDATE_NOT_PROVEN",
                "statement": self.statement()}


def assert_bleed_not_proven(payload: dict) -> None:
    """§31.10: a bleed may never be rendered as a demonstrated cause."""
    if payload.get("status") != "CANDIDATE_NOT_PROVEN":
        raise WorldModelDefect(
            f"a causal bleed carries status {payload.get('status')!r}. A "
            "bleed is a measured non-response with a CANDIDATE explanation. "
            "Rates fell, demand did not respond, therefore fear -- is a "
            "story, and the whole point of the object is that it stays one "
            "until something tests it.")


# =============================================================================
# §18/§22 COMPANY IMPLICATIONS AND THE DECISION DELTA
# =============================================================================

@dataclass(frozen=True)
class CompanyImplication:
    """What one economic reading means for one company, and why."""

    company_id: str
    driver: str
    channel: str
    mechanism: str
    direction: str
    magnitude: str
    confidence: float
    falsifier: str
    evidence: Tuple[str, ...] = ()
    depends_on: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(bool(self.channel.strip()),
                f"{self.company_id}/{self.driver}: name the CHANNEL. "
                "'affects demand' is true of every company and therefore "
                "informative about none.")
        require(bool(self.falsifier.strip()),
                f"{self.company_id}/{self.driver}: what would make this "
                "wrong?")

    def as_dict(self) -> dict:
        return {"company_id": self.company_id, "driver": self.driver,
                "channel": self.channel, "mechanism": self.mechanism,
                "direction": self.direction, "magnitude": self.magnitude,
                "confidence": round(self.confidence, 3),
                "falsifier": self.falsifier, "evidence": list(self.evidence),
                "depends_on": list(self.depends_on)}


def assert_company_specific(impls: Sequence[CompanyImplication], *,
                            min_distinct_channels: int = 0) -> dict:
    """Six companies must not receive one paragraph under six names.

    Measures the CHANNEL vocabulary, not the prose. Two companies may both be
    hurt by weaker demand; if the channel is 'basket mix' for one and 'ticket
    value' for the other, the analysis is company-specific. If both say
    'consumer demand', it is a template.
    """
    by_company: Dict[str, Set[str]] = {}
    for i in impls:
        by_company.setdefault(i.company_id, set()).add(i.channel)
    channels = [c for s in by_company.values() for c in s]
    distinct = len(set(channels))
    shared = distinct / len(channels) if channels else 0.0
    need = min_distinct_channels or max(2, len(by_company))
    if distinct < need:
        raise WorldModelDefect(
            f"{len(by_company)} companies produced {distinct} distinct "
            f"channel(s). The same economic state is being rendered as the "
            f"same sentence under different names, which is the failure "
            f"§18 exists to prevent.")
    return {"companies": len(by_company), "implications": len(impls),
            "distinct_channels": distinct,
            "channel_specificity": round(shared, 3),
            "channels_by_company": {k: sorted(v)
                                    for k, v in sorted(by_company.items())}}


@dataclass(frozen=True)
class DecisionDelta:
    """Did the world model change the analysis? Measured, not asserted."""

    company_id: str
    without_world_model: Dict[str, Any]
    with_world_model: Dict[str, Any]

    #: The fields a founder actually acts on. A change anywhere else is not
    #: a decision change.
    FIELDS = ("priority", "recommendation", "risk", "scenario",
              "information_request", "confidence")

    @property
    def changed_fields(self) -> Tuple[str, ...]:
        return tuple(f for f in self.FIELDS
                     if self.without_world_model.get(f)
                     != self.with_world_model.get(f))

    @property
    def nonzero(self) -> bool:
        return bool(self.changed_fields)

    def as_dict(self) -> dict:
        return {"company_id": self.company_id,
                "changed_fields": list(self.changed_fields),
                "nonzero": self.nonzero,
                "without_world_model": dict(self.without_world_model),
                "with_world_model": dict(self.with_world_model),
                "reading": (
                    f"the economic state changed "
                    f"{len(self.changed_fields)} of {len(self.FIELDS)} "
                    f"decision fields"
                    if self.nonzero else
                    "the economic state changed nothing a founder acts on. "
                    "For this company, in this state, the world model added "
                    "no decision value -- which is a result, not a bug.")}


# =============================================================================
# §20 THE DOUBLE-COUNTING WALL
# =============================================================================

def assert_no_double_count(signal_id: str, lineage: Dict[str, Sequence[str]],
                           corroborators: Sequence[str]) -> None:
    """A derived aggregate cannot corroborate its own input.

    `lineage` maps a signal to what it was derived from, transitively walked
    here. If a corroborator appears anywhere in the signal's ancestry, it is
    the same evidence arriving twice under a different name -- the lineage
    version of the pseudo-replication the historical programme spent two runs
    correcting for.
    """
    seen, frontier = set(), list(lineage.get(signal_id, ()))
    while frontier:
        cur = frontier.pop()
        if cur in seen:
            continue
        seen.add(cur)
        frontier.extend(lineage.get(cur, ()))
    bad = sorted(set(corroborators) & seen)
    if bad:
        raise WorldModelDefect(
            f"{signal_id} is corroborated by {bad}, which it was derived "
            f"from. A derived aggregate cannot independently support its own "
            f"input; counting it is how one observation becomes three.")
    return None


# =============================================================================
# §16 DIMENSION QUALITY — LIVE IS NOT USEFUL
# =============================================================================

LIVE_DECISION_RELEVANT = "LIVE_DECISION_RELEVANT"
LIVE_CONTEXT_ONLY = "LIVE_CONTEXT_ONLY"
LIVE_UNPROVEN_VALUE = "LIVE_UNPROVEN_VALUE"
BLOCKED = "BLOCKED"
QUALITIES = (LIVE_DECISION_RELEVANT, LIVE_CONTEXT_ONLY, LIVE_UNPROVEN_VALUE,
             BLOCKED)


def classify_dimension(audit, *, deltas_produced: int,
                       relations_supported: int,
                       company_consumers: int) -> str:
    """A dimension can be LIVE and useless. Which is it?

    LIVE counts a series being readable. That is a fact about acquisition, not
    about value: a dimension nothing consumes and nothing decides on is
    infrastructure, and reporting it beside a decision-relevant one inflates
    the coverage number with things that do not matter.
    """
    if audit.status == "BLOCKED":
        return BLOCKED
    if deltas_produced > 0 and company_consumers > 0:
        return LIVE_DECISION_RELEVANT
    if relations_supported > 0 or company_consumers > 0:
        return LIVE_CONTEXT_ONLY
    return LIVE_UNPROVEN_VALUE


# =============================================================================
# §18 RELATION VALIDATION — A LAG THAT HAS NOT ELAPSED IS NOT A FAILURE
# =============================================================================

REL_CANDIDATE = "CANDIDATE"
REL_OBSERVED = "OBSERVED"
REL_SUPPORTED = "SUPPORTED_PREDICTIVE"
REL_NOT_PROVEN = "CANDIDATE_NOT_PROVEN"
REL_CONTRADICTED = "CONTRADICTED"
REL_RETIRED = "RETIRED"
REL_PENDING = "PENDING_LAG"
REL_STATES = (REL_CANDIDATE, REL_OBSERVED, REL_SUPPORTED, REL_NOT_PROVEN,
              REL_CONTRADICTED, REL_RETIRED, REL_PENDING)


@dataclass(frozen=True)
class RelationCheck:
    """One relation, evaluated against what actually happened."""

    relation: str
    source_moved: bool
    source_move: float
    lag_elapsed: bool
    days_since_source_move: Optional[int]
    lag_days: int
    target_moved: Optional[bool]
    target_move: Optional[float]
    direction_correct: Optional[bool]
    magnitude_plausible: Optional[bool]
    regime_applicable: bool
    note: str = ""

    @property
    def state(self) -> str:
        """§18: the ordering matters and it is the whole point.

        A relation whose lag has NOT elapsed is PENDING, never a failure.
        The previous run's bleed detector compared year-on-year changes with
        no lag check at all and reported four of six relations as
        non-firing -- some of which had simply not had time to fire.
        """
        if not self.regime_applicable:
            return REL_CANDIDATE
        if not self.source_moved:
            return REL_CANDIDATE
        if not self.lag_elapsed:
            return REL_PENDING
        if self.target_moved is None:
            return REL_NOT_PROVEN
        if self.direction_correct:
            return (REL_SUPPORTED if self.magnitude_plausible
                    else REL_OBSERVED)
        return REL_CONTRADICTED

    def as_dict(self) -> dict:
        return {"relation": self.relation, "state": self.state,
                "source_moved": self.source_moved,
                "source_move": round(self.source_move, 5),
                "lag_elapsed": self.lag_elapsed,
                "days_since_source_move": self.days_since_source_move,
                "lag_days": self.lag_days,
                "target_moved": self.target_moved,
                "target_move": (round(self.target_move, 5)
                                if self.target_move is not None else None),
                "direction_correct": self.direction_correct,
                "magnitude_plausible": self.magnitude_plausible,
                "regime_applicable": self.regime_applicable,
                "note": self.note}


def assert_lag_respected(check: RelationCheck) -> None:
    """§18/§35.6: a relation may not be scored before its lag has elapsed."""
    if not check.lag_elapsed and check.state in (REL_CONTRADICTED,
                                                 REL_NOT_PROVEN):
        raise WorldModelDefect(
            f"{check.relation} was scored {check.state} with "
            f"{check.days_since_source_move} of {check.lag_days} lag days "
            "elapsed. A mechanism that has not had time to fire has not "
            "failed to fire.")


# =============================================================================
# §26 STAGNATION DETECTOR V2 — SEVEN CATEGORIES, ONE OF THEM FINE
# =============================================================================

DUPLICATE_INPUT = "DUPLICATE_INPUT_STAGNATION"
PRODUCER_STAG = "PRODUCER_STAGNATION"
BELIEF_STAG = "BELIEF_STAGNATION"
EXPECTATION_STAG = "EXPECTATION_STAGNATION"
RESOLUTION_STAG = "RESOLUTION_STAGNATION"
DECISION_STAG = "DECISION_STAGNATION"
LEGITIMATE = "LEGITIMATE_STABILITY"
STAGNATION_KINDS = (DUPLICATE_INPUT, PRODUCER_STAG, BELIEF_STAG,
                    EXPECTATION_STAG, RESOLUTION_STAG, DECISION_STAG,
                    LEGITIMATE)


@dataclass(frozen=True)
class StagnationAlert:
    """One way learning can be quiet, with what to do about it."""

    kind: str
    reason: str
    evidence: str
    next_diagnostic: str

    def __post_init__(self) -> None:
        require(self.kind in STAGNATION_KINDS, f"unknown kind {self.kind!r}")
        require(bool(self.next_diagnostic.strip()),
                f"{self.kind}: an alert with no recommended next diagnostic "
                "is a complaint")

    def as_dict(self) -> dict:
        return {"kind": self.kind, "reason": self.reason,
                "evidence": self.evidence,
                "next_diagnostic": self.next_diagnostic}


def detect_stagnation(*, unique_evidence: int, duplicate_evidence: int,
                      drivers_moved: int, drivers_total: int,
                      belief_updates: int, expectations_opened: int,
                      expectations_due: int, resolutions: int,
                      material_deltas: int, comparisons: int
                      ) -> List[StagnationAlert]:
    """§26: distinguish legitimate stability from broken learning.

    The categories are separate because they call for different repairs. A
    system whose beliefs never move because no evidence arrived has an
    ACQUISITION problem; one whose beliefs never move while evidence pours in
    has a BELIEF problem; one whose expectations never resolve because none is
    due has nothing wrong at all.
    """
    out: List[StagnationAlert] = []
    if duplicate_evidence and unique_evidence == 0:
        out.append(StagnationAlert(
            kind=DUPLICATE_INPUT,
            reason="every observation this cycle was already held",
            evidence=f"{duplicate_evidence} duplicates, 0 unique",
            next_diagnostic="check the acquisition dedupe key; a key that "
                            "includes the read date makes everything look new "
                            "and a key that omits a real field makes "
                            "everything look duplicate"))
    if drivers_total and drivers_moved == 0:
        out.append(StagnationAlert(
            kind=PRODUCER_STAG,
            reason="no economic driver moved at all",
            evidence=f"0 of {drivers_total} drivers moved",
            next_diagnostic="compare the panel content hash against the "
                            "previous cycle; an identical hash means the "
                            "producer did not run"))
    if unique_evidence > 0 and belief_updates == 0:
        out.append(StagnationAlert(
            kind=BELIEF_STAG,
            reason="new evidence arrived and no belief moved",
            evidence=f"{unique_evidence} unique observations, 0 revisions",
            next_diagnostic="check whether the belief engine is reading the "
                            "fresh evidence or only already-ingested nodes"))
    if drivers_moved > 0 and expectations_opened == 0:
        out.append(StagnationAlert(
            kind=EXPECTATION_STAG,
            reason="drivers moved and no expectation was opened",
            evidence=f"{drivers_moved} drivers moved, 0 expectations",
            next_diagnostic="check the eligibility rule; opening none is "
                            "correct only when no relation reached its "
                            "trigger threshold"))
    if expectations_due > 0 and resolutions == 0:
        out.append(StagnationAlert(
            kind=RESOLUTION_STAG,
            reason="expectations came due and none resolved",
            evidence=f"{expectations_due} due, 0 resolved",
            next_diagnostic="check the resolution contract's series and "
                            "vintage policy against the panel"))
    if comparisons > 0 and material_deltas == 0:
        out.append(StagnationAlert(
            kind=DECISION_STAG,
            reason="no company analysis changed in any regime",
            evidence=f"0 material of {comparisons} comparisons",
            next_diagnostic="check whether the state reaches the analysis at "
                            "all; a world model that is present and not read "
                            "produces exactly this"))
    if not out:
        out.append(StagnationAlert(
            kind=LEGITIMATE,
            reason="every producer advanced, evidence was considered, and "
                   "decisions changed where the state bore on them",
            evidence=f"{drivers_moved}/{drivers_total} drivers moved, "
                     f"{material_deltas}/{comparisons} decisions changed",
            next_diagnostic="none required; re-check next cycle"))
    return out

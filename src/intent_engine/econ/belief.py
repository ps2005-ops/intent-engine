"""The belief and expectation ledger — one per economy, read by both products.

WHY BOTH HALVES LIVE IN ONE MODULE
----------------------------------
A belief that never produces a preregistered expectation cannot be wrong, and
a prediction with no belief behind it cannot teach anything when it resolves.
They are one object in two tenses, and separating them is how a system ends up
with a confident belief ledger and an unrelated prediction log — which is the
state this substrate was built to end.

APPEND-ONLY, AND WHAT THAT ACTUALLY FORBIDS
-------------------------------------------
A belief's PROBABILITY moves; its identity, proposition, mechanism, falsifier
and creation time do not. `revise` returns a new object carrying the whole
prior chain, and `Expectation` is frozen from the moment it is created — there
is no supported way to change what was predicted, because the only reason to
want one is to make a past prediction agree with the present.

INFORMATION CUTOFF IS NOT CREATION TIME
---------------------------------------
`created_at` is when the engine wrote the prediction. `information_cutoff` is
the latest `available_at` of any evidence it used. They differ, and the
difference is where hindsight leaks: a prediction created on Tuesday from a
filing that became available on Wednesday is not a prediction. `preregister`
refuses that ordering rather than recording it.

FIVE OUTCOMES, NOT TWO
----------------------
    CORRECT        resolved in the predicted direction
    INCORRECT      resolved against it
    NEAR_MISS      resolved against it inside the stated tolerance
    VOID           the resolution rule could not be evaluated
    OPEN           not yet due

VOID is the one that matters most and is usually missing. A prediction whose
data source went dark did not fail; scoring it as a failure teaches the engine
to avoid subjects with unreliable feeds rather than to be right.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import EconError, PUBLIC, require

CONTRACT = "econ_belief.v1"

# --- belief status ----------------------------------------------------------
ACTIVE = "ACTIVE"
STRENGTHENED = "STRENGTHENED"
WEAKENED = "WEAKENED"
RETIRED = "RETIRED"
BELIEF_STATUSES = (ACTIVE, STRENGTHENED, WEAKENED, RETIRED)

# --- expectation outcome ----------------------------------------------------
OPEN = "OPEN"
CORRECT = "CORRECT"
INCORRECT = "INCORRECT"
NEAR_MISS = "NEAR_MISS"
VOID = "VOID"
OUTCOMES = (OPEN, CORRECT, INCORRECT, NEAR_MISS, VOID)
RESOLVED = frozenset({CORRECT, INCORRECT, NEAR_MISS})

UP, DOWN, FLAT = "UP", "DOWN", "FLAT"
DIRECTIONS = (UP, DOWN, FLAT)


@dataclass(frozen=True)
class BeliefRevision:
    """One movement of one belief, with the reason attached to the number."""

    at: str
    prior: float
    posterior: float
    basis: str
    evidence_nodes: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"at": self.at, "prior": round(self.prior, 4),
                "posterior": round(self.posterior, 4), "basis": self.basis,
                "evidence_nodes": list(self.evidence_nodes)}


@dataclass(frozen=True)
class EconomicBelief:
    """A proposition about the economy with a probability and a way to be wrong."""

    belief_id: str
    proposition: str
    probability: float
    mechanism: str
    falsifier: str
    #: What would have to be observed for this to be true — stated BEFORE
    #: looking. This is what `preregister` turns into an expectation.
    expected_observations: Tuple[str, ...]
    assumptions: Tuple[str, ...]
    created_at: str
    last_updated: str
    #: Days after which the belief must be reviewed. Not a deletion: an
    #: unreviewed belief keeps its probability and is flagged, because
    #: silently decaying a probability invents a movement nobody made.
    decay_days: int = 180
    status: str = ACTIVE
    evidence_for: Tuple[str, ...] = ()
    evidence_against: Tuple[str, ...] = ()
    revisions: Tuple[BeliefRevision, ...] = ()
    #: Which economy/sector/subject this is about.
    subject: str = "US"
    visibility: str = PUBLIC

    def __post_init__(self) -> None:
        require(bool(self.proposition.strip()), "a belief states a proposition")
        require(0.0 <= self.probability <= 1.0,
                "a belief's probability is a probability")
        require(bool(self.mechanism.strip()),
                "a belief with no mechanism is a mood")
        require(bool(self.falsifier.strip()),
                "a belief that cannot be wrong is not a belief")
        require(bool(self.expected_observations),
                "a belief must say what would be observed if it were true, "
                "before looking; otherwise every observation confirms it")
        require(self.status in BELIEF_STATUSES,
                f"unknown belief status {self.status!r}")
        require(self.decay_days > 0, "decay is a positive horizon")

    @property
    def fragility(self) -> float:
        """How much a single new observation could overturn what rests on this.

        VULNERABILITY times COMMITMENT, and both terms are needed.

        `vulnerability` is how far one observation moves a belief, which
        falls as the evidence behind it accumulates. `commitment` is how hard
        a conclusion is being drawn from it, which is the distance from 0.5.

        The first version of this peaked at p=0.5, on the reasoning that an
        indecisive belief is the easiest to flip. That is true and it is the
        wrong question: a belief sitting at 0.55 flips easily and nothing
        depends on it, so flipping it costs nothing. The belief worth naming
        as fragile is the one a decision is resting on that almost nothing
        supports -- 0.95 on a single source. Measured against the alternative
        formula, a 0.55 belief on forty sources scored MORE fragile than a
        0.95 belief on one, which is the opposite of the ranking `/learning`
        exists to produce.

        A belief at exactly 0.5 has fragility 0, and that is correct: nothing
        is being claimed, so nothing can break. What such a belief needs is
        not protection but evidence, and that is `voi.room_to_move` -- a
        DIFFERENT quantity, which does peak at 0.5, deliberately.
        """
        support = len(self.evidence_for) + len(self.evidence_against)
        vulnerability = 1.0 / (1.0 + support)
        commitment = abs(self.probability - 0.5) * 2.0
        return round(vulnerability * commitment, 4)

    def due_for_review(self, at: str) -> bool:
        return _days_between(self.last_updated, at) >= self.decay_days

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "belief_id": self.belief_id,
                "proposition": self.proposition, "subject": self.subject,
                "probability": round(self.probability, 4),
                "mechanism": self.mechanism, "falsifier": self.falsifier,
                "expected_observations": list(self.expected_observations),
                "assumptions": list(self.assumptions),
                "created_at": self.created_at,
                "last_updated": self.last_updated,
                "decay_days": self.decay_days, "status": self.status,
                "evidence_for": list(self.evidence_for),
                "evidence_against": list(self.evidence_against),
                "fragility": self.fragility,
                "revisions": [r.as_dict() for r in self.revisions],
                "visibility": self.visibility}


def belief_id_for(proposition: str, subject: str) -> str:
    material = json.dumps([" ".join(proposition.split()).lower(),
                           subject.strip().lower()], sort_keys=True)
    return "eb-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def declare(*, proposition: str, probability: float, mechanism: str,
            falsifier: str, expected_observations: Sequence[str],
            assumptions: Sequence[str] = (), at: str, subject: str = "US",
            decay_days: int = 180, evidence_for: Sequence[str] = (),
            visibility: str = PUBLIC) -> EconomicBelief:
    return EconomicBelief(
        belief_id=belief_id_for(proposition, subject), proposition=proposition,
        probability=probability, mechanism=mechanism, falsifier=falsifier,
        expected_observations=tuple(expected_observations),
        assumptions=tuple(assumptions), created_at=at, last_updated=at,
        decay_days=decay_days, evidence_for=tuple(evidence_for),
        subject=subject, visibility=visibility)


def revise(b: EconomicBelief, *, to: float, basis: str, at: str,
           evidence_nodes: Sequence[str] = (),
           against: Sequence[str] = ()) -> EconomicBelief:
    """Move a probability, and record what moved it.

    `basis` is required and is not decoration: a posterior with no recorded
    basis is indistinguishable from a number someone typed, and six weeks
    later nobody can tell which it was.
    """
    require(bool(basis.strip()), "a revision states its basis")
    require(0.0 <= to <= 1.0, "a probability")
    rev = BeliefRevision(at=at, prior=b.probability, posterior=to, basis=basis,
                         evidence_nodes=tuple(evidence_nodes))
    status = (STRENGTHENED if to > b.probability
              else WEAKENED if to < b.probability else b.status)
    return replace(b, probability=to, last_updated=at, status=status,
                   revisions=b.revisions + (rev,),
                   evidence_for=b.evidence_for + tuple(evidence_nodes),
                   evidence_against=b.evidence_against + tuple(against))


def retire(b: EconomicBelief, *, reason: str, at: str) -> EconomicBelief:
    require(bool(reason.strip()), "a retirement states why")
    rev = BeliefRevision(at=at, prior=b.probability, posterior=b.probability,
                         basis=f"RETIRED: {reason}")
    return replace(b, status=RETIRED, last_updated=at,
                   revisions=b.revisions + (rev,))


# --- expectations -----------------------------------------------------------
@dataclass(frozen=True)
class Expectation:
    """A preregistered, dated, falsifiable forward claim. Never rewritten."""

    expectation_id: str
    belief_id: str
    subject: str
    quantity: str
    expected_direction: str
    confidence: float
    mechanism: str
    falsifier: str
    resolution_rule: str
    created_at: str
    information_cutoff: str
    horizon_days: int
    expires_at: str
    #: How far the wrong way still counts as a near miss, in the quantity's
    #: own units. Zero means the prediction is strict.
    tolerance: float = 0.0
    outcome: str = OPEN
    resolved_at: str = ""
    observed_value: Optional[float] = None
    reconciliation: str = ""
    visibility: str = PUBLIC

    def __post_init__(self) -> None:
        require(self.expected_direction in DIRECTIONS,
                f"unknown direction {self.expected_direction!r}")
        require(0.0 <= self.confidence <= 1.0, "confidence is a probability")
        require(bool(self.resolution_rule.strip()),
                "a prediction with no resolution rule cannot be scored, and "
                "an unscoreable prediction is a sentence")
        require(bool(self.falsifier.strip()),
                "a prediction must say what would make it wrong")
        require(self.horizon_days > 0, "a horizon is forward-looking")
        require(self.outcome in OUTCOMES, f"unknown outcome {self.outcome!r}")
        require(self.information_cutoff <= self.created_at,
                f"information_cutoff {self.information_cutoff} is after "
                f"created_at {self.created_at}: a prediction cannot use "
                "evidence that arrived after it was made")

    @property
    def open(self) -> bool:
        return self.outcome == OPEN

    def due(self, at: str) -> bool:
        return at >= self.expires_at

    def as_dict(self) -> dict:
        return {"contract": CONTRACT,
                "expectation_id": self.expectation_id,
                "belief_id": self.belief_id, "subject": self.subject,
                "quantity": self.quantity,
                "expected_direction": self.expected_direction,
                "confidence": round(self.confidence, 4),
                "mechanism": self.mechanism, "falsifier": self.falsifier,
                "resolution_rule": self.resolution_rule,
                "created_at": self.created_at,
                "information_cutoff": self.information_cutoff,
                "horizon_days": self.horizon_days,
                "expires_at": self.expires_at, "tolerance": self.tolerance,
                "outcome": self.outcome, "resolved_at": self.resolved_at,
                "observed_value": self.observed_value,
                "reconciliation": self.reconciliation,
                "visibility": self.visibility}


def preregister(*, belief: EconomicBelief, quantity: str, direction: str,
                confidence: float, resolution_rule: str, at: str,
                information_cutoff: str, horizon_days: int,
                expires_at: str, tolerance: float = 0.0,
                subject: str = "") -> Expectation:
    """Write a forward claim BEFORE the window it is about.

    The mechanism and falsifier are taken FROM THE BELIEF rather than passed
    in. A prediction that states a different mechanism from the belief it came
    from is not testing that belief, and allowing the caller to supply one is
    how a ledger fills with predictions that cannot update anything.
    """
    material = json.dumps([belief.belief_id, quantity, direction, at,
                           horizon_days], sort_keys=True)
    eid = "ex-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return Expectation(
        expectation_id=eid, belief_id=belief.belief_id,
        subject=subject or belief.subject, quantity=quantity,
        expected_direction=direction, confidence=confidence,
        mechanism=belief.mechanism, falsifier=belief.falsifier,
        resolution_rule=resolution_rule, created_at=at,
        information_cutoff=information_cutoff, horizon_days=horizon_days,
        expires_at=expires_at, tolerance=tolerance,
        visibility=belief.visibility)


def resolve(e: Expectation, *, observed_direction: str, at: str,
            observed_value: Optional[float] = None,
            miss_size: Optional[float] = None,
            note: str = "") -> Expectation:
    """Score one expectation. The only place an outcome may be written."""
    require(e.outcome == OPEN,
            f"expectation {e.expectation_id} is already {e.outcome}; an "
            "outcome is written once, or the ledger records the last opinion "
            "rather than the first")
    if observed_direction == e.expected_direction:
        outcome = CORRECT
    elif (miss_size is not None and e.tolerance > 0
          and abs(miss_size) <= e.tolerance):
        outcome = NEAR_MISS
    else:
        outcome = INCORRECT
    return replace(e, outcome=outcome, resolved_at=at,
                   observed_value=observed_value,
                   reconciliation=note or f"observed {observed_direction}")


def void(e: Expectation, *, at: str, reason: str) -> Expectation:
    """The resolution rule could not be evaluated. NOT a failure.

    Scoring an unevaluable prediction as wrong teaches the engine to predict
    only where the data is reliable, which is a bias about feeds dressed up as
    a lesson about the economy.
    """
    require(bool(reason.strip()), "a void states why it could not be scored")
    require(e.outcome == OPEN, "already resolved")
    return replace(e, outcome=VOID, resolved_at=at,
                   reconciliation=f"VOID: {reason}")


# --- the ledger -------------------------------------------------------------
class BeliefLedger:
    """Beliefs and their expectations, in memory. Durable form is `store`."""

    def __init__(self, beliefs: Sequence[EconomicBelief] = (),
                 expectations: Sequence[Expectation] = ()) -> None:
        self._beliefs: Dict[str, EconomicBelief] = {b.belief_id: b
                                                    for b in beliefs}
        self._expectations: Dict[str, Expectation] = {
            e.expectation_id: e for e in expectations}

    def put(self, b: EconomicBelief) -> EconomicBelief:
        self._beliefs[b.belief_id] = b
        return b

    def add(self, e: Expectation) -> Expectation:
        require(e.belief_id in self._beliefs,
                f"expectation {e.expectation_id} names belief {e.belief_id}, "
                "which is not in the ledger; an orphan prediction cannot "
                "update anything when it resolves")
        self._expectations[e.expectation_id] = e
        return e

    def belief(self, belief_id: str) -> Optional[EconomicBelief]:
        return self._beliefs.get(belief_id)

    def beliefs(self, *, status: str = "", subject: str = "",
                public_only: bool = False) -> List[EconomicBelief]:
        out = list(self._beliefs.values())
        if status:
            out = [b for b in out if b.status == status]
        if subject:
            out = [b for b in out if b.subject == subject]
        if public_only:
            out = [b for b in out if b.visibility == PUBLIC]
        return sorted(out, key=lambda b: (-b.fragility, b.belief_id))

    def expectations(self, *, outcome: str = "",
                     belief_id: str = "") -> List[Expectation]:
        out = list(self._expectations.values())
        if outcome:
            out = [e for e in out if e.outcome == outcome]
        if belief_id:
            out = [e for e in out if e.belief_id == belief_id]
        return sorted(out, key=lambda e: (e.expires_at, e.expectation_id))

    def due(self, at: str) -> List[Expectation]:
        return [e for e in self.expectations(outcome=OPEN) if e.due(at)]

    def resolved_count(self) -> int:
        return sum(1 for e in self._expectations.values()
                   if e.outcome in RESOLVED)

    def most_fragile(self, n: int = 5) -> List[EconomicBelief]:
        return self.beliefs(status=ACTIVE)[:n]

    def summary(self, *, at: str = "") -> dict:
        by_outcome: Dict[str, int] = {}
        for e in self._expectations.values():
            by_outcome[e.outcome] = by_outcome.get(e.outcome, 0) + 1
        stale = ([b.belief_id for b in self._beliefs.values()
                  if b.status != RETIRED and b.due_for_review(at)]
                 if at else [])
        return {"contract": CONTRACT, "beliefs": len(self._beliefs),
                "active": len(self.beliefs(status=ACTIVE)),
                "retired": len(self.beliefs(status=RETIRED)),
                "expectations": len(self._expectations),
                "by_outcome": by_outcome,
                "resolved_forward": self.resolved_count(),
                "due_for_review": stale}


def _days_between(start: str, end: str) -> int:
    """Calendar days between two ISO dates; 0 when either is unparseable."""
    import datetime
    try:
        a = datetime.date.fromisoformat(start[:10])
        b = datetime.date.fromisoformat(end[:10])
    except (ValueError, TypeError):
        return 0
    return (b - a).days

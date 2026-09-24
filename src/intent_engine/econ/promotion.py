"""Candidate -> durable knowledge, and the defences on the way.

THE STATES
----------
    CANDIDATE    proposed, mechanism stated, nothing tested
    OBSERVED     the predicted observable has been seen at least once
    TESTED       a preregistered expectation about it has resolved
    REPLICATED   it has resolved the same way in a DIFFERENT regime or on a
                 different subject
    PROMOTED     durable knowledge
    WEAKENED     was promoted, has since failed
    RETIRED      withdrawn

WHY REPLICATED REQUIRES A DIFFERENT REGIME OR SUBJECT
------------------------------------------------------
Two confirmations in the same regime on the same company are one confirmation
observed twice. This is the same idea as the double-counting wall, applied to
time instead of to lineage, and it is the single most common way a backtest
looks better than the world.

THE DEFENCES ARE REQUIRED, NOT ADVISORY
---------------------------------------
`promote` refuses without all six of holdout, walk-forward, parameter
sensitivity, regime stability, multiple-testing awareness, and a null
baseline. Not because six is a magic number, but because each one has failed
this class of system before and every one of them is invisible when absent.

MULTIPLE TESTING IS THE ONE PEOPLE SKIP
----------------------------------------
If forty candidate mechanisms are tested at p<0.05, two will pass on noise.
`tests_considered` records how many were in the family, and `promote` raises
the confirmation bar as the family grows. A ledger that records only the
winners cannot do this, which is why candidates are never deleted -- only
RETIRED.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_promotion.v1"

CANDIDATE = "CANDIDATE"
OBSERVED = "OBSERVED"
TESTED = "TESTED"
REPLICATED = "REPLICATED"
PROMOTED = "PROMOTED"
WEAKENED = "WEAKENED"
RETIRED = "RETIRED"
STATES = (CANDIDATE, OBSERVED, TESTED, REPLICATED, PROMOTED, WEAKENED,
          RETIRED)

#: The only transitions that exist. Anything else raises, so a candidate
#: cannot jump from CANDIDATE to PROMOTED because one backtest looked good.
TRANSITIONS = {
    CANDIDATE: (OBSERVED, RETIRED),
    OBSERVED: (TESTED, RETIRED),
    TESTED: (REPLICATED, WEAKENED, RETIRED),
    REPLICATED: (PROMOTED, WEAKENED, RETIRED),
    PROMOTED: (WEAKENED, RETIRED),
    WEAKENED: (TESTED, RETIRED),
    RETIRED: (),
}


class PromotionRefused(EconError):
    """A promotion that the evidence does not support."""


@dataclass(frozen=True)
class Defences:
    """The overfitting defences (Section 26). All six, or no promotion."""

    holdout_period: str = ""
    walk_forward: str = ""
    parameter_sensitivity: str = ""
    regime_stability: str = ""
    #: How many candidates were tested in the same family. Required, and the
    #: one people skip.
    tests_considered: int = 0
    null_baseline: str = ""
    turnover_and_friction: str = ""

    def missing(self) -> List[str]:
        out = [name for name in ("holdout_period", "walk_forward",
                                 "parameter_sensitivity", "regime_stability",
                                 "null_baseline", "turnover_and_friction")
               if not str(getattr(self, name)).strip()]
        if self.tests_considered < 1:
            out.append("tests_considered")
        return out

    def as_dict(self) -> dict:
        return {"holdout_period": self.holdout_period,
                "walk_forward": self.walk_forward,
                "parameter_sensitivity": self.parameter_sensitivity,
                "regime_stability": self.regime_stability,
                "tests_considered": self.tests_considered,
                "null_baseline": self.null_baseline,
                "turnover_and_friction": self.turnover_and_friction,
                "complete": not self.missing()}


@dataclass(frozen=True)
class Candidate:
    """One candidate mechanism on its way to being knowledge, or not."""

    candidate_id: str
    claim: str
    mechanism: str
    state: str
    created_at: str
    last_moved: str
    #: (subject, regime) pairs this has resolved correctly in.
    confirmations: Tuple[Tuple[str, str], ...] = ()
    contradictions: Tuple[Tuple[str, str], ...] = ()
    defences: Defences = field(default_factory=Defences)
    history: Tuple[Tuple[str, str, str], ...] = ()   # (at, state, reason)

    def __post_init__(self) -> None:
        require(self.state in STATES, f"unknown state {self.state!r}")
        require(bool(self.claim.strip()), "a candidate states a claim")
        require(bool(self.mechanism.strip()),
                "a candidate with no mechanism is a correlation waiting to "
                "be promoted by repetition")

    @property
    def independent_confirmations(self) -> int:
        """Confirmations in DISTINCT (subject, regime) pairs.

        Two confirmations on the same company in the same regime are one
        confirmation observed twice.
        """
        return len(set(self.confirmations))

    @property
    def distinct_regimes(self) -> int:
        return len({r for _, r in self.confirmations})

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "candidate_id": self.candidate_id,
                "claim": self.claim, "mechanism": self.mechanism,
                "state": self.state, "created_at": self.created_at,
                "last_moved": self.last_moved,
                "confirmations": len(self.confirmations),
                "independent_confirmations": self.independent_confirmations,
                "distinct_regimes": self.distinct_regimes,
                "contradictions": len(self.contradictions),
                "defences": self.defences.as_dict(),
                "history": [{"at": a, "state": s, "reason": r}
                            for a, s, r in self.history]}


def propose(*, candidate_id: str, claim: str, mechanism: str,
            at: str) -> Candidate:
    return Candidate(candidate_id=candidate_id, claim=claim,
                     mechanism=mechanism, state=CANDIDATE, created_at=at,
                     last_moved=at, history=((at, CANDIDATE, "proposed"),))


def move(c: Candidate, *, to: str, at: str, reason: str) -> Candidate:
    """Advance a candidate along a declared transition. No shortcuts exist."""
    require(to in TRANSITIONS.get(c.state, ()),
            f"{c.state} -> {to} is not a declared transition; from "
            f"{c.state} the only moves are {TRANSITIONS.get(c.state, ())}")
    require(bool(reason.strip()), "a state change states why")
    return replace(c, state=to, last_moved=at,
                   history=c.history + ((at, to, reason),))


def confirm(c: Candidate, *, subject: str, regime: str, at: str) -> Candidate:
    return replace(c, confirmations=c.confirmations + ((subject, regime),),
                   last_moved=at,
                   history=c.history + ((at, c.state,
                                         f"confirmed on {subject}/{regime}"),))


def contradict(c: Candidate, *, subject: str, regime: str,
               at: str) -> Candidate:
    return replace(
        c, contradictions=c.contradictions + ((subject, regime),),
        last_moved=at,
        history=c.history + ((at, c.state,
                              f"contradicted on {subject}/{regime}"),))


#: Independent confirmations required for REPLICATED, in distinct regimes.
MIN_CONFIRMATIONS = 3
MIN_REGIMES = 2


def replicate(c: Candidate, *, at: str) -> Candidate:
    """TESTED -> REPLICATED, on distinct subjects AND distinct regimes."""
    if c.independent_confirmations < MIN_CONFIRMATIONS:
        raise PromotionRefused(
            f"{c.candidate_id} has {c.independent_confirmations} independent "
            f"confirmation(s); {MIN_CONFIRMATIONS} are required. Repeated "
            "confirmations on the same subject in the same regime are one "
            "observation counted more than once.")
    if c.distinct_regimes < MIN_REGIMES:
        raise PromotionRefused(
            f"{c.candidate_id} has only been confirmed in "
            f"{c.distinct_regimes} regime(s). A relationship that has never "
            "been tested outside the conditions it was found in is a "
            "description of those conditions.")
    return move(c, to=REPLICATED, at=at,
                reason=(f"{c.independent_confirmations} independent "
                        f"confirmations across {c.distinct_regimes} regimes"))


def promote(c: Candidate, *, at: str, defences: Defences) -> Candidate:
    """REPLICATED -> PROMOTED. Refuses without all six defences."""
    missing = defences.missing()
    if missing:
        raise PromotionRefused(
            f"{c.candidate_id} cannot be promoted: {missing} not stated. "
            "Every one of these has produced a false positive in this class "
            "of system, and every one is invisible when absent.")
    if c.contradictions:
        raise PromotionRefused(
            f"{c.candidate_id} carries {len(c.contradictions)} "
            "contradiction(s) and may not be promoted while they stand; "
            "retire them explicitly or the promotion is over a filtered "
            "record")
    # Multiple testing. With `tests_considered` candidates in the family, the
    # number of confirmations that would occur by chance grows, so the bar
    # grows with the family.
    required = MIN_CONFIRMATIONS + max(
        0, (defences.tests_considered - 10) // 10)
    if c.independent_confirmations < required:
        raise PromotionRefused(
            f"{c.candidate_id} has {c.independent_confirmations} independent "
            f"confirmations; {required} are required when "
            f"{defences.tests_considered} candidates were tested in the same "
            "family. If forty are tested at p<0.05, two pass on noise.")
    return replace(move(c, to=PROMOTED, at=at,
                        reason=("all six overfitting defences stated; "
                                f"{c.independent_confirmations} independent "
                                f"confirmations against "
                                f"{defences.tests_considered} tested")),
                   defences=defences)


def summarise(candidates: Sequence[Candidate]) -> dict:
    by_state: Dict[str, int] = {s: 0 for s in STATES}
    for c in candidates:
        by_state[c.state] = by_state.get(c.state, 0) + 1
    return {"contract": CONTRACT, "candidates": len(candidates),
            "by_state": by_state, "promoted": by_state[PROMOTED],
            "blocked_on_defences": [
                {"candidate_id": c.candidate_id,
                 "missing": c.defences.missing()}
                for c in candidates
                if c.state == REPLICATED and c.defences.missing()]}

"""Vintage-correct replay: what was knowable at T, and nothing else.

THE CONTAMINATION THIS PREVENTS
--------------------------------
Replaying a decision with today's evidence set produces a system that looks
prescient and has learned nothing. The leak is rarely deliberate: it is a
revised statistic silently replacing its first print, a filing dated by its
period rather than its publication, or a belief object whose probability has
moved since.

`knowable_at` is the whole defence. It reads `available_at` -- never
`occurred_at`, never `retrieved_at` -- and it reads REVISIONS as separate
observations, so a Q2 figure revised in September is not available in July
at its September value.

FOUR OUTCOMES, NOT TWO
----------------------
    RIGHT_FOR_RIGHT_REASON     the mechanism held and the call was right
    RIGHT_FOR_WRONG_REASON     the call was right and the mechanism did not
                               hold. The dangerous one: it reinforces a
                               mechanism that is not working.
    WRONG_FOR_RIGHT_MECHANISM  the mechanism held and something else
                               dominated. Usually a sizing or timing lesson,
                               not a mechanism lesson.
    WRONG_ENTIRELY             neither

Collapsing these into right/wrong is how a system learns the wrong lesson
from a lucky call. RIGHT_FOR_WRONG_REASON must not increase confidence in the
mechanism, and `belief_update_allowed` returns False for it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .belief import EconomicBelief, Expectation
from .evidence import EconomicNode
from .vocabulary import require

CONTRACT = "econ_replay.v1"

RIGHT_FOR_RIGHT_REASON = "RIGHT_FOR_RIGHT_REASON"
RIGHT_FOR_WRONG_REASON = "RIGHT_FOR_WRONG_REASON"
WRONG_FOR_RIGHT_MECHANISM = "WRONG_FOR_RIGHT_MECHANISM"
WRONG_ENTIRELY = "WRONG_ENTIRELY"
VERDICTS = (RIGHT_FOR_RIGHT_REASON, RIGHT_FOR_WRONG_REASON,
            WRONG_FOR_RIGHT_MECHANISM, WRONG_ENTIRELY)


class VintageViolation(ValueError):
    """Evidence from after the replay point reached the replayed decision."""


def knowable_at(nodes: Sequence[EconomicNode], when: str
                ) -> List[EconomicNode]:
    """The evidence set as it stood at `when`, revisions included correctly.

    A node whose CURRENT form became available after `when` falls back to the
    most recent revision that was available -- rather than being dropped.
    Dropping it would understate what the engine knew; keeping the current
    form would overstate it. Both errors are silent, so this returns the
    vintage.
    """
    require(bool(when), "a replay point is a date")
    out: List[EconomicNode] = []
    for n in nodes:
        if n.visible_at(when):
            out.append(n)
            continue
        vintage = [r for r in n.revisions if r.visible_at(when)]
        if vintage:
            out.append(max(vintage, key=lambda r: r.available_at))
    return sorted(out, key=lambda n: (n.available_at, n.node_id))


def assert_vintage(nodes: Sequence[EconomicNode], *, when: str,
                   where: str) -> None:
    """Refuse a decision built on evidence from its own future."""
    leaks = [n.node_id for n in nodes if not n.visible_at(when)]
    if leaks:
        raise VintageViolation(
            f"{where}: {len(leaks)} node(s) were not available at {when} "
            f"({leaks[:3]}). A replay that reads them is not a replay; it is "
            "the present, wearing a past date.")


@dataclass(frozen=True)
class ReplayVerdict:
    """One replayed decision, scored on outcome AND mechanism separately."""

    expectation_id: str
    at: str
    outcome_correct: bool
    mechanism_held: bool
    verdict: str
    basis: str
    evidence_at_decision: int
    evidence_now: int

    @property
    def belief_update_allowed(self) -> bool:
        """May this episode move confidence in the mechanism?

        No for RIGHT_FOR_WRONG_REASON. A right call through a mechanism that
        did not hold is the single most expensive thing to learn from: it
        reinforces exactly the reasoning that failed, and it feels like
        success while doing it.
        """
        return self.verdict != RIGHT_FOR_WRONG_REASON

    def as_dict(self) -> dict:
        return {"contract": CONTRACT,
                "expectation_id": self.expectation_id, "at": self.at,
                "outcome_correct": self.outcome_correct,
                "mechanism_held": self.mechanism_held,
                "verdict": self.verdict, "basis": self.basis,
                "belief_update_allowed": self.belief_update_allowed,
                "evidence_at_decision": self.evidence_at_decision,
                "evidence_now": self.evidence_now}


def score(expectation: Expectation, *, outcome_correct: bool,
          mechanism_held: bool, basis: str, nodes: Sequence[EconomicNode],
          ) -> ReplayVerdict:
    """Classify one replayed decision into the four-way verdict."""
    require(bool(basis.strip()),
            "a replay verdict states how the mechanism was judged; without "
            "that, 'the mechanism held' is an opinion recorded as a fact")
    if outcome_correct and mechanism_held:
        verdict = RIGHT_FOR_RIGHT_REASON
    elif outcome_correct:
        verdict = RIGHT_FOR_WRONG_REASON
    elif mechanism_held:
        verdict = WRONG_FOR_RIGHT_MECHANISM
    else:
        verdict = WRONG_ENTIRELY
    at_decision = knowable_at(nodes, expectation.information_cutoff)
    return ReplayVerdict(
        expectation_id=expectation.expectation_id,
        at=expectation.information_cutoff, outcome_correct=outcome_correct,
        mechanism_held=mechanism_held, verdict=verdict, basis=basis,
        evidence_at_decision=len(at_decision), evidence_now=len(nodes))


def summarise(verdicts: Sequence[ReplayVerdict]) -> dict:
    by_verdict: Dict[str, int] = {v: 0 for v in VERDICTS}
    for r in verdicts:
        by_verdict[r.verdict] = by_verdict.get(r.verdict, 0) + 1
    lucky = by_verdict[RIGHT_FOR_WRONG_REASON]
    right = by_verdict[RIGHT_FOR_RIGHT_REASON] + lucky
    return {
        "contract": CONTRACT, "replayed": len(verdicts),
        "by_verdict": by_verdict,
        "correct": right,
        # The number that matters and that a right/wrong split hides.
        "lucky_share": (round(lucky / right, 3) if right else None),
        "blocked_from_updating_beliefs":
            sum(1 for r in verdicts if not r.belief_update_allowed),
        "note": ("a right call through a mechanism that did not hold may not "
                 "raise confidence in that mechanism; those episodes are "
                 "counted as correct and excluded from belief updates"),
    }

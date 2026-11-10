"""What to go and find out next, and why that rather than more of the same.

BOUNDED VALUE OF INFORMATION
----------------------------
A full VOI calculation needs a decision, a loss function, and the posterior
under every observation. This engine has the first and not the other two, so
what is computed here is a BOUNDED estimate: how much a belief could move,
times how much that movement would change a decision, discounted by how
likely the observation is to be obtainable at all.

That is a ranking device, not a number to put on a screen. `score` is
comparable within one queue at one moment and is meaningless across queues,
and `Priority.as_dict` says so.

THE FAILURE THIS AVOIDS
-----------------------
A named heuristic that computes nothing. This project has had one: a policy
class with a confident name whose method returned a constant, and an
evaluator that never noticed because a constant ranks consistently. So every
term below actually varies with its input, and `test_econ_voi.py` asserts
that changing each one changes the ranking.

CERTAINTY IS WORTHLESS
----------------------
A belief at probability 0.98 has almost no room to move, so observing it is
worth almost nothing however important the subject. This is the term people
leave out, and leaving it out makes the queue permanently recommend more
evidence about the things the engine is already sure of -- which feels
productive and is how a system stops learning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .belief import EconomicBelief
from .vocabulary import require

CONTRACT = "econ_voi.v1"

#: How obtainable an observation is, and what that multiplies by.
ROUTINE = "ROUTINE"            # a scheduled publication or a filing
OBTAINABLE = "OBTAINABLE"      # exists, needs work to find
SPECULATIVE = "SPECULATIVE"    # may not exist in any source we read
UNOBTAINABLE = "UNOBTAINABLE"  # known not to exist publicly
OBTAINABILITY = {ROUTINE: 1.0, OBTAINABLE: 0.7, SPECULATIVE: 0.3,
                 UNOBTAINABLE: 0.0}


@dataclass(frozen=True)
class Priority:
    """One thing worth going to find out."""

    question: str
    belief_id: str
    subject: str
    #: What would be observed. Concrete enough to send someone after.
    observation: str
    obtainability: str
    #: How much the answer would change a decision, 0..1. Supplied by the
    #: decision surface, because only it knows what is being decided.
    decision_impact: float
    #: Days until the answer would arrive.
    latency_days: int
    belief_probability: float
    cost: float = 1.0

    def __post_init__(self) -> None:
        require(self.obtainability in OBTAINABILITY,
                f"unknown obtainability {self.obtainability!r}")
        require(0.0 <= self.decision_impact <= 1.0, "a fraction")
        require(0.0 <= self.belief_probability <= 1.0, "a probability")
        require(self.cost > 0, "cost is positive")
        require(bool(self.observation.strip()),
                "a research priority names what would be OBSERVED; a "
                "priority phrased as a topic cannot be answered or closed")

    @property
    def room_to_move(self) -> float:
        """How much a belief at this probability CAN move. Peaks at 0.5.

        The term everyone leaves out. Without it the queue recommends more
        evidence about what the engine is already sure of, forever.
        """
        return round(1.0 - abs(self.belief_probability - 0.5) * 2.0, 4)

    @property
    def score(self) -> float:
        """A ranking number, comparable within one queue only."""
        urgency = 1.0 / (1.0 + self.latency_days / 30.0)
        return round(
            self.room_to_move * self.decision_impact
            * OBTAINABILITY[self.obtainability] * urgency / self.cost, 6)

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "question": self.question,
                "belief_id": self.belief_id, "subject": self.subject,
                "observation": self.observation,
                "obtainability": self.obtainability,
                "decision_impact": round(self.decision_impact, 3),
                "latency_days": self.latency_days,
                "room_to_move": self.room_to_move,
                "cost": self.cost, "score": self.score,
                "score_note": ("a ranking device: comparable within this "
                               "queue at this moment, and meaningless "
                               "across queues or over time")}


def for_belief(belief: EconomicBelief, *, decision_impact: float,
               observation: str, obtainability: str = OBTAINABLE,
               latency_days: int = 30, cost: float = 1.0,
               question: str = "") -> Priority:
    """A priority derived from a belief's own expected observations."""
    return Priority(
        question=(question or
                  f"what would show whether: {belief.proposition}"),
        belief_id=belief.belief_id, subject=belief.subject,
        observation=observation, obtainability=obtainability,
        decision_impact=decision_impact, latency_days=latency_days,
        belief_probability=belief.probability, cost=cost)


def queue(priorities: Sequence[Priority], *, limit: int = 10
          ) -> List[Priority]:
    """Ranked, highest first. Ties break on the shorter latency."""
    return sorted(priorities,
                  key=lambda p: (-p.score, p.latency_days, p.question))[:limit]


def summarise(priorities: Sequence[Priority], *, limit: int = 10) -> dict:
    ranked = queue(priorities, limit=limit)
    dead = [p for p in priorities if p.obtainability == UNOBTAINABLE]
    return {
        "contract": CONTRACT, "priorities": len(priorities),
        "queue": [p.as_dict() for p in ranked],
        # An UNOBTAINABLE priority scores zero and would silently vanish from
        # the queue. It is reported separately because "the thing that would
        # settle this does not exist publicly" is a finding about the
        # question, and it should stop the engine asking it again.
        "unobtainable": [{"question": p.question, "subject": p.subject}
                         for p in dead],
        "note": ("bounded VOI: how far a belief could move, times how much "
                 "that would change a decision, times how obtainable the "
                 "observation is. Not a decision-theoretic VOI; there is no "
                 "loss function here."),
    }

"""What an actor might be trying to do — held as a hypothesis, never as a fact.

THE ONE MOVE THIS MODULE REFUSES
--------------------------------
Turning an ACTION into an OBJECTIVE. "Shopify cut its Plus pricing" is an
observation. "Shopify is buying share from Magento" is a story about why, and
the distance between them is where every confident, wrong strategy note comes
from.

So an objective may only be recorded alongside ALTERNATIVE objectives that
the same action is equally consistent with, and a hypothesis with no
alternatives is refused by the constructor. That mirrors
`strategic_interaction`, which already refuses an inferred motive arriving
without one.

WHY STANDING IS ORDINAL AND SMALL
---------------------------------
WEAK / PLAUSIBLE / SUPPORTED / CONTESTED. No probability, because there is no
sample to calibrate one against and a number would imply there is. The engine
has one competitive relationship; a 0.62 next to it would be fiction with a
decimal point.

WHAT PROMOTES A HYPOTHESIS
--------------------------
Only a preregistered expected NEXT ACTION that came back the way it said. An
objective that explains the past and predicts nothing is unfalsifiable, and
`expected_next_action` is required for exactly that reason.
"""
from __future__ import annotations

import collections
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "strategic_objective.v1"

WEAK = "WEAK"
PLAUSIBLE = "PLAUSIBLE"
SUPPORTED = "SUPPORTED"
CONTESTED = "CONTESTED"
STANDINGS = (WEAK, PLAUSIBLE, SUPPORTED, CONTESTED)

#: Two, not one. A single alternative is usually the strawman the author
#: already rejected; requiring two makes the set do some work.
MIN_ALTERNATIVES = 2


class ObjectiveRejected(ValueError):
    """The engine was asked to state a motive it cannot support."""


@dataclass(frozen=True)
class StrategicObjectiveHypothesis:
    hypothesis_id: str
    actor: str
    objective: str
    constraint: str
    action: str
    expected_payoff: str
    affected_actor: str
    supporting_evidence: Tuple[str, ...]
    contradicting_evidence: Tuple[str, ...]
    alternative_objectives: Tuple[str, ...]
    standing: str
    falsifier: str
    expected_next_action: str
    provenance: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "hypothesis_id": self.hypothesis_id,
            "actor": self.actor, "objective": self.objective,
            "constraint": self.constraint, "action": self.action,
            "expected_payoff": self.expected_payoff,
            "affected_actor": self.affected_actor,
            "supporting_evidence": list(self.supporting_evidence),
            "contradicting_evidence": list(self.contradicting_evidence),
            "alternative_objectives": list(self.alternative_objectives),
            "standing": self.standing, "falsifier": self.falsifier,
            "expected_next_action": self.expected_next_action,
            "provenance": dict(self.provenance),
            "caution": ("an objective is a hypothesis about why an actor "
                        "acted; the action is observed and the reason is "
                        "not"),
        }


def hypothesise(*, actor: str, objective: str, action: str,
                affected_actor: str, alternative_objectives: Sequence[str],
                falsifier: str, expected_next_action: str,
                constraint: str = "", expected_payoff: str = "",
                supporting_evidence: Sequence[str] = (),
                provenance: Optional[Dict[str, str]] = None
                ) -> StrategicObjectiveHypothesis:
    """Admit one objective hypothesis, or refuse it for asserting a motive."""
    alternatives = tuple(a for a in alternative_objectives if a.strip())
    if len(alternatives) < MIN_ALTERNATIVES:
        raise ObjectiveRejected(
            f"an objective needs at least {MIN_ALTERNATIVES} alternative "
            f"readings of the same action; with fewer, the record asserts a "
            f"motive rather than proposing one")
    if not expected_next_action.strip():
        raise ObjectiveRejected(
            "an objective that explains the past and predicts nothing cannot "
            "be wrong; state the next action it implies")
    if not falsifier.strip():
        raise ObjectiveRejected("state what would rule this objective out")
    if not action.strip():
        raise ObjectiveRejected("an objective with no observed action is a "
                                "guess about a company")
    raw = f"{actor}|{objective}|{action}".lower()
    return StrategicObjectiveHypothesis(
        hypothesis_id="obj_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        actor=actor, objective=objective, constraint=constraint,
        action=action, expected_payoff=expected_payoff,
        affected_actor=affected_actor,
        supporting_evidence=tuple(supporting_evidence),
        contradicting_evidence=(), alternative_objectives=alternatives,
        # Always WEAK at birth. There is no argument that opens one higher.
        standing=WEAK, falsifier=falsifier,
        expected_next_action=expected_next_action,
        provenance=dict(provenance or {}))


def score(hypothesis: StrategicObjectiveHypothesis, *, held: bool,
          evidence_id: str = "") -> StrategicObjectiveHypothesis:
    """Move standing on whether the preregistered next action happened."""
    supporting = hypothesis.supporting_evidence
    contradicting = hypothesis.contradicting_evidence
    if held:
        supporting = tuple(dict.fromkeys(supporting + ((evidence_id,)
                                                       if evidence_id else ())))
    else:
        contradicting = tuple(dict.fromkeys(
            contradicting + ((evidence_id,) if evidence_id else ())))
    if supporting and contradicting:
        standing = CONTESTED
    elif len(supporting) >= 2:
        standing = SUPPORTED
    elif supporting:
        standing = PLAUSIBLE
    else:
        standing = WEAK
    return StrategicObjectiveHypothesis(**{
        **hypothesis.__dict__, "supporting_evidence": supporting,
        "contradicting_evidence": contradicting, "standing": standing})


def summarise(hypotheses: Sequence[StrategicObjectiveHypothesis]) -> dict:
    return {
        "contract": CONTRACT,
        "hypotheses": len(hypotheses),
        "by_standing": dict(collections.Counter(h.standing
                                                for h in hypotheses)),
        "actors": sorted({h.actor for h in hypotheses}),
        "alternatives_per_hypothesis": (
            round(sum(len(h.alternative_objectives) for h in hypotheses)
                  / len(hypotheses), 2) if hypotheses else 0.0),
        "note": ("every hypothesis is born WEAK and is promoted only by a "
                 "preregistered next action coming back the way it said; an "
                 "objective that explains the past and predicts nothing is "
                 "refused at construction"),
    }

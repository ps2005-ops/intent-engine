"""Four kinds of gain, and why they must never be added together.

WHAT THIS PREVENTS
------------------
Wave 9 removed 22 non-actions, three counting defects and one fabricated
attribution. The corpus went from 38 sentences to 16 real ones and every
number got better. The count of established competitive objects stayed at
ONE. Reported as a single figure, that wave reads like progress in
understanding the market; it was progress in understanding our own pipeline.

    ECONOMIC_KNOWLEDGE   new facts, beliefs, revisions, outcomes
    SYSTEM_CAPABILITY    dedupe, classification, routing, recovered misses
    CALIBRATION          mechanisms and predictions actually tested
    FOUNDER_UTILITY      a decision a reader would make differently

A cleaner denominator is not a new fact about the world. Fixing the
instrument is not the same as learning the measurement, and a system that
cannot tell them apart will report a refactor as insight for as long as the
refactors last.

CALIBRATION IS SIX QUESTIONS, NOT ONE
-------------------------------------
"Was the strategic reasoning right?" cannot be answered or acted on. The
chain has six joints and each fails differently: the rivalry may be wrong,
the action may be misclassified, the object may be wrongly established, the
relevance may be misjudged, the predicted response may not come, the motive
may be misread. A single accuracy number hides which one moved.

UNMEASURABLE IS NOT ZERO
------------------------
Most of these tracks have no live tests yet. `UNMEASURABLE` says so, and is
distinct from an accuracy of 0.0, which would claim we tried and failed.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

CONTRACT = "learning_channels.v1"

# --- the four channels ------------------------------------------------------
ECONOMIC_KNOWLEDGE = "ECONOMIC_KNOWLEDGE_GAIN"
SYSTEM_CAPABILITY = "SYSTEM_CAPABILITY_GAIN"
CALIBRATION = "CALIBRATION_GAIN"
FOUNDER_UTILITY = "FOUNDER_UTILITY_GAIN"

CHANNELS = (ECONOMIC_KNOWLEDGE, SYSTEM_CAPABILITY, CALIBRATION,
            FOUNDER_UTILITY)

#: What may be counted in each channel. A movement whose kind is not listed
#: for its channel is refused rather than filed under the nearest match.
_ALLOWED: Dict[str, Tuple[str, ...]] = {
    ECONOMIC_KNOWLEDGE: ("new_fact", "new_belief", "belief_revision",
                         "outcome_observed", "established_object",
                         "relationship_discovered"),
    SYSTEM_CAPABILITY: ("duplicate_removed", "non_action_removed",
                        "misattribution_removed", "near_miss_recovered",
                        "precision_improved", "routing_improved",
                        "counting_defect_fixed"),
    CALIBRATION: ("prediction_tested", "mechanism_tested",
                  "causal_link_tested", "response_reconciled"),
    FOUNDER_UTILITY: ("decision_field_changed", "surface_corrected",
                      "failure_made_legible"),
}

# --- the six calibration tracks --------------------------------------------
RELATIONSHIP_ACCURACY = "RELATIONSHIP_ACCURACY"
ACTION_CLASSIFICATION_ACCURACY = "ACTION_CLASSIFICATION_ACCURACY"
OBJECT_ESTABLISHMENT_ACCURACY = "OBJECT_ESTABLISHMENT_ACCURACY"
RELEVANCE_ACCURACY = "RELEVANCE_ACCURACY"
RESPONSE_PREDICTION_ACCURACY = "RESPONSE_PREDICTION_ACCURACY"
OBJECTIVE_INFERENCE_ACCURACY = "OBJECTIVE_INFERENCE_ACCURACY"

CALIBRATION_TRACKS = (
    RELATIONSHIP_ACCURACY, ACTION_CLASSIFICATION_ACCURACY,
    OBJECT_ESTABLISHMENT_ACCURACY, RELEVANCE_ACCURACY,
    RESPONSE_PREDICTION_ACCURACY, OBJECTIVE_INFERENCE_ACCURACY)

UNMEASURABLE = "UNMEASURABLE"


class ChannelRejected(ValueError):
    pass


@dataclass(frozen=True)
class Movement:
    """One thing that changed, filed under exactly one channel."""
    channel: str
    kind: str
    count: int
    detail: str

    def as_dict(self) -> dict:
        return {"channel": self.channel, "kind": self.kind,
                "count": self.count, "detail": self.detail}


def movement(*, channel: str, kind: str, count: int, detail: str) -> Movement:
    if channel not in CHANNELS:
        raise ChannelRejected(f"{channel} is not one of the four channels")
    if kind not in _ALLOWED[channel]:
        raise ChannelRejected(
            f"{kind!r} cannot be counted as {channel}: a movement whose kind "
            f"does not belong to a channel is filed under the nearest match, "
            f"and the nearest match to a pipeline repair is always a fact "
            f"about the world")
    if count < 0:
        raise ChannelRejected("a movement cannot be negative")
    if not detail.strip():
        raise ChannelRejected("a movement with no detail cannot be audited")
    return Movement(channel=channel, kind=kind, count=count,
                    detail=detail.strip())


@dataclass(frozen=True)
class CalibrationTrack:
    """One joint of the strategic chain, and whether it has ever been tested."""
    track: str
    tested: int = 0
    correct: int = 0
    note: str = ""

    @property
    def accuracy(self) -> Optional[float]:
        """None, never 0.0, when nothing has been tested. An accuracy of zero
        claims we tried and failed."""
        return (self.correct / self.tested) if self.tested else None

    @property
    def standing(self) -> str:
        return UNMEASURABLE if not self.tested else "MEASURED"

    def as_dict(self) -> dict:
        return {"track": self.track, "tested": self.tested,
                "correct": self.correct,
                "accuracy": (round(self.accuracy, 4)
                             if self.accuracy is not None else None),
                "standing": self.standing, "note": self.note}


def report(movements: Sequence[Movement],
           tracks: Sequence[CalibrationTrack] = ()) -> dict:
    """The wave's gains, kept apart, plus which joints were tested."""
    by_channel: Dict[str, list] = collections.defaultdict(list)
    for move in movements:
        by_channel[move.channel].append(move)
    known = {t.track: t for t in tracks}
    all_tracks = [known.get(name, CalibrationTrack(track=name))
                  for name in CALIBRATION_TRACKS]
    return {
        "contract": CONTRACT,
        "by_channel": {
            channel: {
                "movements": [m.as_dict() for m in by_channel.get(channel, ())],
                "total": sum(m.count for m in by_channel.get(channel, ())),
            } for channel in CHANNELS},
        "calibration": [t.as_dict() for t in all_tracks],
        "calibration_unmeasurable": sum(
            1 for t in all_tracks if t.standing == UNMEASURABLE),
        "note": ("the four totals are never summed. A wave can have high "
                 "system capability gain and zero economic knowledge gain, "
                 "and that is a description rather than a disappointment."),
    }

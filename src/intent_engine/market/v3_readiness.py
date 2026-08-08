"""Where the intelligence chain is actually narrowest, and how ready V3 is.

WHY THE ANSWER IS NOT HARDCODED
-------------------------------
Every wave of this project has ended by naming a bottleneck, and four times
the named bottleneck turned out to be an artefact of a counting defect
rather than a fact about the world — 112 actions that were 32, five
established objects that were one, rivalries that were discovered and never
saved. A bottleneck that is asserted is a belief; a bottleneck computed from
stage measurements is a finding.

So `detect` takes the measured throughput of each stage and reports the
narrowest. If the numbers say the wall has moved, the wall has moved,
including when that contradicts the last checkpoint.

WHY READINESS HAS NO PERCENTAGE
-------------------------------
A single number invites averaging PASS against BLOCKED, which is how a
system with one fatal gap reads as 90% done. Each axis carries its own
status and its own measured reason, and the roll-up is a count of statuses
rather than a score.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "v3_readiness.v1"

# --- stages of the intelligence chain ---------------------------------------
STAGES = (
    "SOURCE_DISCOVERY", "SOURCE_RETRIEVAL", "PARSING", "EVENT_IDENTITY",
    "SUBJECT_ATTRIBUTION", "EVENT_CLASSIFICATION", "BELIEF_FORMATION",
    "EXPECTATION_GENERATION", "OUTCOME_OBSERVABILITY", "RECONCILIATION",
    "MECHANISM_TESTING", "RELATIONSHIP_COVERAGE", "TEMPORAL_COVERAGE",
    "CAUSAL_LINKAGE", "STRATEGIC_INTERACTION", "RESPONSE_OBSERVABILITY",
    "HIDDEN_STATE", "VOI", "RESEARCH_PRIORITY", "FOUNDER_CONSUMPTION",
    "FOUNDER_DECISION_IMPACT", "KNOWLEDGE_RETENTION",
)

# --- readiness axes ---------------------------------------------------------
AXES = (
    "EVIDENCE_INTEGRITY", "TEMPORAL_INTEGRITY", "IDENTITY_INTEGRITY",
    "LEARNING_LOOP", "CALIBRATION", "WORLD_MODEL", "CAUSAL_REASONING",
    "STRATEGIC_REASONING", "KNOWLEDGE_RETENTION", "RESEARCH_PRIORITIZATION",
    "FOUNDER_CONSUMPTION", "FOUNDER_DECISION_VALUE", "PRODUCT_RELIABILITY",
    "SAFETY_PAPER", "OBSERVABILITY",
)

PASS = "PASS"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
FAIL = "FAIL"
UNMEASURABLE = "UNMEASURABLE"
STATUSES = (PASS, PARTIAL, BLOCKED, FAIL, UNMEASURABLE)


@dataclass(frozen=True)
class StageMeasure:
    """What went in, what came out, and why the rest did not."""
    stage: str
    inputs: int
    outputs: int
    reason: str = ""
    blocked_by_data: bool = False

    @property
    def throughput(self) -> Optional[float]:
        """None, not zero, when nothing entered: a stage nobody fed has not
        failed, and scoring it at 0.0 would make it the loudest bottleneck
        every time."""
        return (self.outputs / self.inputs) if self.inputs else None

    def as_dict(self) -> dict:
        return {"stage": self.stage, "inputs": self.inputs,
                "outputs": self.outputs,
                "throughput": (round(self.throughput, 4)
                               if self.throughput is not None else None),
                "reason": self.reason,
                "blocked_by_data": self.blocked_by_data}


def detect(measures: Sequence[StageMeasure]) -> dict:
    """The narrowest stage that actually ran, and the next after it."""
    ran = [m for m in measures if m.throughput is not None]
    starved = [m for m in measures if m.throughput is None]
    ordered = sorted(ran, key=lambda m: (m.throughput, m.stage))
    primary = ordered[0] if ordered else None
    secondary = ordered[1] if len(ordered) > 1 else None
    return {
        "contract": CONTRACT,
        "stages_measured": len(ran),
        "stages_never_fed": [m.stage for m in starved],
        "primary_bottleneck": (primary.as_dict() if primary else None),
        "secondary_bottleneck": (secondary.as_dict() if secondary else None),
        "recommended_next_action": (primary.reason if primary else
                                    "no stage has been fed; measure first"),
        "note": ("a stage with no inputs is reported as never fed rather "
                 "than as a throughput of zero, which would make it the "
                 "loudest bottleneck every time"),
    }


@dataclass(frozen=True)
class AxisStatus:
    axis: str
    status: str
    reason: str
    evidence: Dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"axis": self.axis, "status": self.status,
                "reason": self.reason, "evidence": dict(self.evidence)}


def scorecard(axes: Sequence[AxisStatus]) -> dict:
    """Statuses counted, never averaged."""
    missing = [a for a in AXES if a not in {x.axis for x in axes}]
    unreasoned = [a.axis for a in axes if not a.reason.strip()]
    by_status = collections.Counter(a.status for a in axes)
    return {
        "contract": CONTRACT,
        "axes": len(axes),
        "missing_axes": missing,
        "axes_without_a_measured_reason": unreasoned,
        "by_status": {s: by_status.get(s, 0) for s in STATUSES
                      if by_status.get(s, 0)},
        "detail": [a.as_dict() for a in axes],
        "blocking": [a.axis for a in axes if a.status in (FAIL, BLOCKED)],
        "note": ("statuses are counted, not averaged. A single percentage "
                 "lets one fatal gap read as 90% done."),
    }

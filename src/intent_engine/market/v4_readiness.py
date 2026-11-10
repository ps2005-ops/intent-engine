"""V4 readiness, measured off the artifacts rather than asserted.

Same discipline as `v3_readiness`: statuses are COUNTED, never averaged. A
single percentage lets one fatal gap read as 90% done, and the gaps are the
only part of an economic world model worth reading.

The difference from V3 is what counts as done. V3 asked whether a contract
existed and survived a restart. V4 asks whether the thing is POPULATED and
whether anything downstream consumed it — a macro model with no series in it
and a transmission engine nothing calls are both architecturally complete and
economically worthless.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Dict, Sequence

CONTRACT = "v4_readiness.v1"

PASS = "PASS"
PARTIAL = "PARTIAL"
BLOCKED_DATA = "BLOCKED_DATA"
BLOCKED_OWNER = "BLOCKED_OWNER"
UNMEASURABLE = "UNMEASURABLE"
NO = "NO"

STATUSES = (PASS, PARTIAL, BLOCKED_DATA, BLOCKED_OWNER, UNMEASURABLE, NO)

AXES = (
    "MACRO_STATE", "TEMPORAL_TRUTH", "COMPANY_EXPOSURE",
    "CAUSAL_TRANSMISSION", "MULTI_HOP_REASONING", "SUPPLY_CHAIN",
    "DEMAND_CHAIN", "EXPECTATIONS", "REGIME_AWARENESS",
    "SECOND_ORDER_EFFECTS", "COUNTERFACTUALS", "SCENARIOS",
    "INTERNAL_COMPANY_MODEL", "ACTIVE_RESEARCH", "CALIBRATION",
    "ECONOMIC_MEMORY", "FOUNDER_CONSUMPTION", "FOUNDER_DECISION_VALUE",
    "META_LEARNING", "PRODUCT_RELIABILITY",
    # Session 2. Added rather than folded into the existing axes: an engine
    # that discovers structure and an engine that chooses what to research
    # fail in different ways, and one axis covering both would let a working
    # half carry a missing half.
    "SURPRISE", "REGIME_DISCOVERY", "UNSUPERVISED_DISCOVERY",
    "ACTIVE_LEARNING", "RESEARCH_POLICY", "METHOD_PERFORMANCE",
    "THIRD_ORDER", "THESIS_ENGINE", "PROOF_ENGINE", "CEO_CONVERSATION",
    "PRESENTATION", "RETENTION", "PAPER",
    # Session 3. The bottleneck itself became an axis: an engine that
    # cannot say what its evidence changed cannot score anything
    # downstream of the evidence.
    "EVIDENCE_LINKAGE", "RESEARCH_REWARD",
    "PROSPECTIVE_RESEARCH_LOG",
)


@dataclass
class AxisStatus:
    axis: str
    status: str
    reason: str
    evidence: Dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"axis": self.axis, "status": self.status,
                "reason": self.reason, "evidence": dict(self.evidence)}


def scorecard(axes: Sequence[AxisStatus]) -> dict:
    """Counted, never averaged; and every axis must name a measured reason.

    An axis with a status and no reason is a status somebody chose. The
    `axes_without_a_measured_reason` list exists so that choice cannot be made
    quietly.
    """
    known = {a.axis for a in axes}
    bad = [a.axis for a in axes if a.status not in STATUSES]
    if bad:
        raise ValueError(f"unknown status on {bad}")
    counts = collections.Counter(a.status for a in axes)
    return {
        "contract": CONTRACT,
        "axes": len(axes),
        "missing_axes": [a for a in AXES if a not in known],
        "axes_without_a_measured_reason": [a.axis for a in axes
                                           if not a.reason.strip()],
        "by_status": {s: counts[s] for s in STATUSES if counts[s]},
        "blocking": [a.axis for a in axes if a.status == NO],
        "executable_remaining": [a.axis for a in axes
                                 if a.status in (PARTIAL, NO)],
        "detail": [a.as_dict() for a in axes],
        "note": ("statuses are counted, not averaged. V4 asks whether an "
                 "axis is POPULATED and CONSUMED, not whether a contract "
                 "for it exists."),
    }

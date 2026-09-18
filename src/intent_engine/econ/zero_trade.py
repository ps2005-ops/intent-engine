"""Learning when nothing was done (Section 17).

WHY THIS IS THE MOST IMPORTANT LOOP IN THE SYSTEM
--------------------------------------------------
Measured on this engine's own history: eleven consecutive operating cycles,
28 companies evaluated, 27 carrying independent evidence, `net_knowledge_gain
= 0` every time. The cause was structural — the only path to a belief update
ran through a RESOLVED POSITION. No trade meant no learning, so a system that
correctly declined to act learned nothing from having been right to decline.

A trading system takes a position on a small minority of what it looks at.
If learning is gated on positions, the overwhelming majority of the engine's
work is discarded, and the discarded part is the part where its judgement was
most conservative.

THE TWO SHAPES
--------------
    REJECTED   a signal fired and was declined. What happened next, and was
               the decline correct?
    ABSENT     no signal fired, the market moved anyway. What evidence was
               missing, and was it obtainable?

The second is harder and worth more. It is the only way the engine can
discover that a whole class of event is INVISIBLE to it, as opposed to
correctly ignored.

STRUCTURALLY INVISIBLE IS A FINDING, NOT A FAILURE
---------------------------------------------------
When an ABSENT record concludes that the evidence could not have been
obtained from any source this engine reads, that is not a miss to be
corrected by lowering a threshold. It is a coverage gap, and it belongs in
the research queue as a SOURCE problem. Lowering a threshold to catch it
would trade a known blind spot for an unknown false-positive rate.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import require

CONTRACT = "econ_zero_trade.v1"

REJECTED = "REJECTED"
ABSENT = "ABSENT"
SHAPES = (REJECTED, ABSENT)

# verdicts for a REJECTED signal
CORRECTLY_DECLINED = "CORRECTLY_DECLINED"
WRONGLY_DECLINED = "WRONGLY_DECLINED"
UNRESOLVED = "UNRESOLVED"

# verdicts for an ABSENT signal
EVIDENCE_EXISTED_UNREAD = "EVIDENCE_EXISTED_UNREAD"
EVIDENCE_EXISTED_UNRECOGNISED = "EVIDENCE_EXISTED_UNRECOGNISED"
STRUCTURALLY_INVISIBLE = "STRUCTURALLY_INVISIBLE"
NOT_KNOWABLE_IN_ADVANCE = "NOT_KNOWABLE_IN_ADVANCE"

VERDICTS = (CORRECTLY_DECLINED, WRONGLY_DECLINED, UNRESOLVED,
            EVIDENCE_EXISTED_UNREAD, EVIDENCE_EXISTED_UNRECOGNISED,
            STRUCTURALLY_INVISIBLE, NOT_KNOWABLE_IN_ADVANCE)

#: Which verdicts are a claim about THE ENGINE rather than about the world.
#: These are the ones that produce work.
ACTIONABLE = frozenset({WRONGLY_DECLINED, EVIDENCE_EXISTED_UNREAD,
                        EVIDENCE_EXISTED_UNRECOGNISED})


@dataclass(frozen=True)
class ZeroTradeRecord:
    """One thing the engine did not do, and what came of not doing it."""

    record_id: str
    shape: str
    subject: str
    as_of: str
    #: For REJECTED: the gate that declined it, verbatim.
    #: For ABSENT: what moved, and by how much.
    what_happened: str
    reason: str
    verdict: str = UNRESOLVED
    resolved_at: str = ""
    #: What was subsequently observed. Empty while UNRESOLVED.
    subsequent: str = ""
    #: For ABSENT: the evidence that would have been needed.
    missing_evidence: str = ""
    #: Whether that evidence exists anywhere this engine reads.
    obtainable: Optional[bool] = None

    def __post_init__(self) -> None:
        require(self.shape in SHAPES, f"unknown shape {self.shape!r}")
        require(self.verdict in VERDICTS,
                f"unknown verdict {self.verdict!r}")
        require(bool(self.reason.strip()),
                "a zero-trade record states why nothing happened; without "
                "that it records only that nothing happened, which the "
                "absence of a position already records")
        if self.shape == ABSENT and self.verdict == STRUCTURALLY_INVISIBLE:
            require(self.obtainable is False,
                    "STRUCTURALLY_INVISIBLE claims the evidence could not "
                    "have been obtained; `obtainable` must say so explicitly, "
                    "because the alternative reading -- we did not look -- is "
                    "a completely different finding")

    @property
    def actionable(self) -> bool:
        return self.verdict in ACTIONABLE

    @property
    def coverage_gap(self) -> bool:
        """A source problem, not a threshold problem."""
        return self.verdict == STRUCTURALLY_INVISIBLE

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "record_id": self.record_id,
                "shape": self.shape, "subject": self.subject,
                "as_of": self.as_of, "what_happened": self.what_happened,
                "reason": self.reason, "verdict": self.verdict,
                "resolved_at": self.resolved_at,
                "subsequent": self.subsequent,
                "missing_evidence": self.missing_evidence,
                "obtainable": self.obtainable,
                "actionable": self.actionable,
                "coverage_gap": self.coverage_gap}


def _rid(shape: str, subject: str, as_of: str, reason: str) -> str:
    material = json.dumps([shape, subject, as_of,
                           " ".join(reason.split()).lower()], sort_keys=True)
    return "zt-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def rejected(*, subject: str, as_of: str, gate: str, reason: str,
             what_happened: str = "") -> ZeroTradeRecord:
    """A signal fired and was declined. Record it BEFORE knowing the outcome."""
    require(bool(gate.strip()),
            "a rejection names the gate that declined it; 'the system did "
            "not act' is not a reason anyone can review")
    return ZeroTradeRecord(
        record_id=_rid(REJECTED, subject, as_of, reason), shape=REJECTED,
        subject=subject, as_of=as_of,
        what_happened=what_happened or f"declined at gate: {gate}",
        reason=reason)


def absent(*, subject: str, as_of: str, what_moved: str,
           reason: str) -> ZeroTradeRecord:
    """No signal fired and the world moved anyway."""
    return ZeroTradeRecord(
        record_id=_rid(ABSENT, subject, as_of, reason), shape=ABSENT,
        subject=subject, as_of=as_of, what_happened=what_moved,
        reason=reason)


def resolve(r: ZeroTradeRecord, *, verdict: str, at: str, subsequent: str,
            missing_evidence: str = "",
            obtainable: Optional[bool] = None) -> ZeroTradeRecord:
    """Score a zero-trade record once the window has passed."""
    require(r.verdict == UNRESOLVED,
            f"{r.record_id} is already {r.verdict}")
    require(bool(subsequent.strip()),
            "a verdict states what was subsequently observed")
    if r.shape == REJECTED:
        require(verdict in (CORRECTLY_DECLINED, WRONGLY_DECLINED),
                f"{verdict!r} is not a verdict on a rejected signal")
    else:
        require(verdict in (EVIDENCE_EXISTED_UNREAD,
                            EVIDENCE_EXISTED_UNRECOGNISED,
                            STRUCTURALLY_INVISIBLE, NOT_KNOWABLE_IN_ADVANCE),
                f"{verdict!r} is not a verdict on an absent signal")
    return replace(r, verdict=verdict, resolved_at=at, subsequent=subsequent,
                   missing_evidence=missing_evidence, obtainable=obtainable)


def summarise(records: Sequence[ZeroTradeRecord]) -> dict:
    """The report `/learning` renders under "what we did not do"."""
    by_verdict: Dict[str, int] = {}
    for r in records:
        by_verdict[r.verdict] = by_verdict.get(r.verdict, 0) + 1
    rejected_records = [r for r in records if r.shape == REJECTED]
    scored = [r for r in rejected_records if r.verdict != UNRESOLVED]
    correct = sum(1 for r in scored if r.verdict == CORRECTLY_DECLINED)
    gaps = [r for r in records if r.coverage_gap]
    return {
        "contract": CONTRACT, "records": len(records),
        "by_shape": {REJECTED: len(rejected_records),
                     ABSENT: sum(1 for r in records if r.shape == ABSENT)},
        "by_verdict": by_verdict,
        "rejections_scored": len(scored),
        # A RATE over scored rejections only, and named as such. Reporting it
        # over all rejections would count every still-open window as a
        # correct decline, which is how a gate proves itself right by being
        # recent.
        "decline_precision": (round(correct / len(scored), 3)
                              if scored else None),
        "actionable": sum(1 for r in records if r.actionable),
        "coverage_gaps": [{"subject": r.subject,
                           "missing": r.missing_evidence}
                          for r in gaps],
        "note": ("a coverage gap is a source problem. Lowering a threshold "
                 "to catch it trades a known blind spot for an unknown "
                 "false-positive rate."),
    }

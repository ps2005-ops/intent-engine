"""Is the system learning faster, and is it learning as well? (Section 16)

WHY BOTH QUESTIONS
------------------
Velocity alone is trivially gameable: ingest more, declare more beliefs,
revise more often, and every counter rises while the engine knows nothing new.
So every velocity measure here is paired with a QUALITY measure over the same
window, and `classify` refuses to report ACCELERATING when volume is rising
and quality is not.

THE DENOMINATOR IS THE MEASUREMENT
----------------------------------
This project has repeatedly measured its own activity and called it learning:
112 actions that were 32, 5 objects that were 1, a self-test rate that was a
dedupe key. Every counter below therefore names what it is a count OF, and
the duplicate-vs-new split is computed rather than assumed — `new_evidence`
is evidence with a node id not seen in any earlier window, which is a real
question about content, not about how many rows were appended.

STAGNATION IS A STATE, NOT A LOW NUMBER
---------------------------------------
PLATEAUING is reported when belief movement falls while ingestion holds up.
That is the specific shape of a system that is still working hard and no
longer learning, and it is invisible if you only watch throughput.

INSUFFICIENT IS THE DEFAULT
---------------------------
A window with fewer cycles than it needs reports INSUFFICIENT_HISTORY and
names the shortfall. It does not report STABLE, because "we cannot tell" and
"nothing is changing" are different, and the second is a finding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import require

CONTRACT = "econ_acceleration.v1"

ACCELERATING = "ACCELERATING"
STABLE = "STABLE"
PLATEAUING = "PLATEAUING"
DEGRADING = "DEGRADING"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
STATUSES = (ACCELERATING, STABLE, PLATEAUING, DEGRADING, INSUFFICIENT_HISTORY)

#: Rolling windows, in cycles.
WINDOWS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}

#: Below this many cycles a window cannot carry a direction.
MIN_CYCLES_FOR_DIRECTION = 3


@dataclass(frozen=True)
class CycleCounts:
    """What one operating cycle produced. Every field is a count OF something."""

    cycle_id: str
    at: str
    evidence_ingested: int = 0
    evidence_new: int = 0
    candidate_events: int = 0
    beliefs_declared: int = 0
    beliefs_revised: int = 0
    beliefs_retired: int = 0
    expectations_preregistered: int = 0
    expectations_reconciled: int = 0
    hidden_states: int = 0
    strategic_interactions: int = 0
    causal_updates: int = 0
    information_priorities: int = 0
    decayed: int = 0
    near_misses: int = 0
    surprises: int = 0
    counterfactuals: int = 0
    zero_trade_learnings: int = 0
    #: Sum of |posterior - prior| over the cycle's belief revisions. This is
    #: the quality counterpart to `beliefs_revised`: ten revisions that each
    #: moved a probability by 0.001 are not ten units of learning.
    belief_movement: float = 0.0
    contradictions: int = 0

    @property
    def duplicate_evidence(self) -> int:
        return max(0, self.evidence_ingested - self.evidence_new)

    @property
    def novelty(self) -> Optional[float]:
        if self.evidence_ingested <= 0:
            return None
        return round(self.evidence_new / self.evidence_ingested, 4)

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in (
            "cycle_id", "at", "evidence_ingested", "evidence_new",
            "candidate_events", "beliefs_declared", "beliefs_revised",
            "beliefs_retired", "expectations_preregistered",
            "expectations_reconciled", "hidden_states",
            "strategic_interactions", "causal_updates",
            "information_priorities", "decayed", "near_misses", "surprises",
            "counterfactuals", "zero_trade_learnings", "contradictions")}
        d["belief_movement"] = round(self.belief_movement, 4)
        d["duplicate_evidence"] = self.duplicate_evidence
        d["novelty"] = self.novelty
        return d


@dataclass(frozen=True)
class WindowReport:
    name: str
    cycles_required: int
    cycles_available: int
    status: str
    reason: str
    volume: Optional[float] = None
    quality: Optional[float] = None
    novelty: Optional[float] = None
    movement_per_cycle: Optional[float] = None

    def as_dict(self) -> dict:
        return {"window": self.name,
                "cycles_required": self.cycles_required,
                "cycles_available": self.cycles_available,
                "status": self.status, "reason": self.reason,
                "volume": self.volume, "quality": self.quality,
                "novelty": self.novelty,
                "movement_per_cycle": self.movement_per_cycle}


def _mean(xs: Sequence[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 4) if xs else None


def window_report(cycles: Sequence[CycleCounts], *, name: str,
                  size: int) -> WindowReport:
    """One rolling window, or an honest refusal."""
    available = len(cycles)
    if available < max(MIN_CYCLES_FOR_DIRECTION, min(size, available + 1)) \
            and available < size:
        return WindowReport(
            name=name, cycles_required=size, cycles_available=available,
            status=INSUFFICIENT_HISTORY,
            reason=(f"{available} cycle(s) of history against {size} "
                    "required; a direction over fewer cycles than the window "
                    "asks for is a direction over a different window"))
    recent = list(cycles)[-size:]
    if len(recent) < MIN_CYCLES_FOR_DIRECTION:
        return WindowReport(
            name=name, cycles_required=size, cycles_available=available,
            status=INSUFFICIENT_HISTORY,
            reason=(f"{len(recent)} cycle(s) in the window; "
                    f"{MIN_CYCLES_FOR_DIRECTION} are the minimum that can "
                    "carry a direction"))

    half = max(1, len(recent) // 2)
    earlier, later = recent[:half], recent[half:]

    volume = _mean([float(c.evidence_ingested) for c in later])
    novelty_vals = [c.novelty for c in later if c.novelty is not None]
    novelty = _mean(novelty_vals) if novelty_vals else None
    movement = _mean([c.belief_movement for c in later])

    # QUALITY: belief movement per unit of evidence ingested. Rising volume
    # with flat movement drives this down, which is exactly the shape that
    # must not read as ACCELERATING.
    def quality_of(seg: Sequence[CycleCounts]) -> Optional[float]:
        ingested = sum(c.evidence_ingested for c in seg)
        if ingested <= 0:
            return None
        return round(sum(c.belief_movement for c in seg) / ingested, 6)

    q_now, q_before = quality_of(later), quality_of(earlier)
    v_now = _mean([float(c.evidence_ingested) for c in later]) or 0.0
    v_before = _mean([float(c.evidence_ingested) for c in earlier]) or 0.0

    if q_now is None or q_before is None:
        return WindowReport(
            name=name, cycles_required=size, cycles_available=available,
            status=INSUFFICIENT_HISTORY,
            reason="no evidence was ingested in one half of the window, so "
                   "quality per unit of evidence is undefined there",
            volume=volume, novelty=novelty, movement_per_cycle=movement)

    volume_rising = v_now > v_before * 1.05
    quality_rising = q_now > q_before * 1.05
    quality_falling = q_now < q_before * 0.95

    if quality_rising:
        status, reason = ACCELERATING, (
            f"belief movement per unit of evidence rose from {q_before} to "
            f"{q_now}")
    elif volume_rising and quality_falling:
        status, reason = PLATEAUING, (
            f"ingestion rose ({v_before:.1f} -> {v_now:.1f} per cycle) while "
            f"movement per unit of evidence fell ({q_before} -> {q_now}); "
            "the engine is working harder and learning less")
    elif quality_falling:
        status, reason = DEGRADING, (
            f"movement per unit of evidence fell from {q_before} to {q_now} "
            "without a rise in ingestion to explain it")
    else:
        status, reason = STABLE, (
            f"movement per unit of evidence held at about {q_now}")

    return WindowReport(
        name=name, cycles_required=size, cycles_available=available,
        status=status, reason=reason, volume=volume,
        quality=q_now, novelty=novelty, movement_per_cycle=movement)


def report(cycles: Sequence[CycleCounts]) -> dict:
    """Every rolling window, plus the totals a dashboard renders."""
    windows = {name: window_report(cycles, name=name, size=size)
               for name, size in WINDOWS.items()}
    totals: Dict[str, float] = {}
    for c in cycles:
        for key, value in c.as_dict().items():
            if isinstance(value, (int, float)) and key != "novelty":
                totals[key] = totals.get(key, 0) + value
    decided = [w for w in windows.values()
               if w.status != INSUFFICIENT_HISTORY]
    return {
        "contract": CONTRACT, "cycles": len(cycles),
        "windows": {n: w.as_dict() for n, w in windows.items()},
        "totals": {k: (round(v, 4) if isinstance(v, float) else v)
                   for k, v in sorted(totals.items())},
        # The headline is the LONGEST window that can carry a direction, not
        # the most recent one. A one-day reading is noise wearing a status.
        "headline": (max(decided, key=lambda w: w.cycles_required).status
                     if decided else INSUFFICIENT_HISTORY),
        "headline_window": (max(decided,
                                key=lambda w: w.cycles_required).name
                            if decided else ""),
    }

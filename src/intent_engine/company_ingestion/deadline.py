"""§18–§23: one budget for an analysis, propagated to every task that spends it.

WHY THIS EXISTS
---------------
A customer watched "Reading current company evidence" for 4m54s and was then
given nothing. Nothing in the pipeline was broken in a way any test could see:
every individual call was inside its own timeout, every retry was inside its
own policy, and the sum of all of them was bounded by nothing at all.

    14 approved sources
    x 8s connect timeout
    x 3 attempts
    + exponential backoff

is minutes, and no component owns that number. A per-call timeout answers
"how long may THIS request take"; it cannot answer "how long may the customer
wait", because that question is about the whole request and every component
only sees its own part of it.

So the budget is an object, created once when the analysis starts, and passed
down. Every stage asks it how much time is left and spends accordingly. When
it expires the analysis does not fail — it STOPS ACQUIRING and composes what
it already has, which is the difference between a bounded answer and a
spinner.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not cancel work in flight. A thread blocked in `ssl.read` cannot be
interrupted safely, and killing it would leave a half-written record in an
append-only store. The deadline gates what is STARTED, and every individual
call remains separately bounded by its own timeout — so the worst case is one
in-flight call past the deadline, not an unbounded number of them.

It also does not shorten a call below the point of usefulness. A 0.4s budget
handed to an SEC filing fetch buys a guaranteed timeout and a wasted
connection; `budget_for` refuses rather than pretending.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

#: §2. The interactive contract, frozen BEFORE optimizing so that "we hit the
#: target" cannot be achieved by moving the target. Tier 1 is a well-known,
#: high-coverage public company; tier 2 is a deeper strategic read.
TIER1_SOFT_S = 30.0
TIER1_HARD_S = 60.0
TIER2_SOFT_S = 80.0
TIER2_HARD_S = 120.0

#: Below this there is no point starting another network call: the connection
#: alone will not complete, so the only thing the attempt buys is a slower
#: failure. Stopping here is what turns "out of time" into "bounded gaps".
MIN_USEFUL_FETCH_S = 1.5

TIER_1 = "tier1"
TIER_2 = "tier2"

#: §18. What a source is allowed to cost the run. REQUIRED sources may spend
#: from the main budget; OPTIONAL_ENRICHMENT may not delay a result that is
#: already defensible. The classification is about the ANALYSIS, never about
#: how good the source is.
REQUIRED = "REQUIRED"
HIGH_VALUE_OPTIONAL = "HIGH_VALUE_OPTIONAL"
OPTIONAL_ENRICHMENT = "OPTIONAL_ENRICHMENT"

#: The share of the whole budget a single class of source may consume. One
#: slow optional page may not eat the request: measured on the deployed
#: preview, a single unreachable host held a run open for the entire window.
CLASS_SHARE = {
    REQUIRED: 1.0,
    HIGH_VALUE_OPTIONAL: 0.6,
    OPTIONAL_ENRICHMENT: 0.35,
}


class DeadlineExceeded(RuntimeError):
    """Raised only where a caller has asked to be told rather than to degrade."""


@dataclass
class Deadline:
    """The remaining interactive budget for ONE analysis."""

    total_s: float
    tier: str = TIER_1
    started_at: float = field(default_factory=time.monotonic)
    #: Stages that ran out of time, in the order they did. This is what the
    #: reader is eventually shown as "bounded gaps", so it is recorded as it
    #: happens rather than reconstructed afterwards.
    gaps: list = field(default_factory=list)
    #: Seconds already spent per source class. A share has to be CUMULATIVE to
    #: mean anything: capping each individual call at 35% of the budget still
    #: lets thirty optional calls consume all of it, which is the failure this
    #: bounds. Callers report what a call cost through `spend`.
    _spent: dict = field(default_factory=dict)

    @classmethod
    def for_tier(cls, tier: str = TIER_1, *, total_s: float = 0.0):
        hard = TIER1_HARD_S if tier == TIER_1 else TIER2_HARD_S
        return cls(total_s=float(total_s or hard), tier=tier)

    @classmethod
    def unbounded(cls):
        """A budget that never expires — for batch and offline callers.

        Batch analysis is not an interactive request and has no customer
        waiting on it. Forcing the interactive budget on it would make the
        product's own validation runs degrade for a reason that does not
        apply to them.
        """
        return cls(total_s=float("inf"), tier=TIER_2)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def remaining(self) -> float:
        return self.total_s - self.elapsed

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    @property
    def soft_expired(self) -> bool:
        soft = TIER1_SOFT_S if self.tier == TIER_1 else TIER2_SOFT_S
        return self.elapsed >= min(soft, self.total_s)

    def budget_for(self, per_call_s: float, *,
                   source_class: str = REQUIRED) -> float:
        """Seconds this call may take, or 0.0 when it must not be started.

        The answer is the SMALLEST of: what the call would normally take, what
        its class is allowed to consume, and what is actually left. Returning
        0.0 is a decision — "do not start this" — and callers record a gap.
        """
        if self.total_s == float("inf"):
            return per_call_s
        left = self.remaining
        if left < MIN_USEFUL_FETCH_S:
            return 0.0
        share = (CLASS_SHARE.get(source_class, 1.0) * self.total_s
                 - self._spent.get(source_class, 0.0))
        if share < MIN_USEFUL_FETCH_S:
            return 0.0                      # this class has had its share
        return max(MIN_USEFUL_FETCH_S, min(per_call_s, share, left))

    def spend(self, seconds: float, source_class: str = REQUIRED) -> None:
        """Report what a call actually cost, against its class's share."""
        self._spent[source_class] = \
            self._spent.get(source_class, 0.0) + max(0.0, float(seconds))

    def may_start(self, source_class: str = REQUIRED) -> bool:
        return self.budget_for(MIN_USEFUL_FETCH_S,
                               source_class=source_class) > 0.0

    def reserving(self, seconds: float) -> "Deadline":
        """A view of this budget that stops early, keeping `seconds` back.

        WHY A VIEW AND NOT A SECOND BUDGET. Acquisition may not spend the
        whole interactive budget, because composition still has to run
        afterwards and it is the step that produces the answer. But the two
        are not independent timers -- they are one wall clock seen twice, so
        the view shares this object's start time, its gap list and its
        per-class spend. A separate `Deadline` would drift and would report
        two different elapsed times for one request.
        """
        if self.total_s == float("inf"):
            return self
        view = Deadline(total_s=max(0.0, self.total_s - float(seconds)),
                        tier=self.tier, started_at=self.started_at)
        view.gaps = self.gaps               # shared by reference, on purpose
        view._spent = self._spent
        return view

    def record_gap(self, stage: str, detail: str = "") -> None:
        """Name what the budget cost, so the reader is told rather than left
        to infer it from an absence."""
        entry = {"stage": stage, "detail": detail[:200],
                 "at_s": round(self.elapsed, 2)}
        if entry not in self.gaps:
            self.gaps.append(entry)

    def as_dict(self) -> dict:
        return {"tier": self.tier,
                "total_s": (None if self.total_s == float("inf")
                            else round(self.total_s, 1)),
                "elapsed_s": round(self.elapsed, 2),
                "remaining_s": (None if self.total_s == float("inf")
                                else round(self.remaining, 2)),
                "expired": self.expired,
                "spent_by_class": {k: round(v, 2)
                                   for k, v in self._spent.items()},
                "gaps": list(self.gaps)}

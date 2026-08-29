"""Structured spans for one analysis (§17/§18).

WHY THIS EXISTS
---------------
Three separate explanations for the deployed 135-215s CORE latency were
argued from end-to-end totals and ratios, and two of them were wrong:

    "~200s of Apple's 240s is the model call"   -- wrong; deferring the
                                                   model changed nothing
    "the append-only ledger is scanned per
     request and only production has a big one" -- wrong; 92ms at 100,000
                                                   rows, ~1% of the total

Both were plausible, both were reasoned from aggregates, and both cost a
cycle to disprove. An aggregate cannot say WHERE time went, so this records
it at the boundary where it is spent.

WALL AND CPU TOGETHER, because that is the distinction that actually decides
the repair. A span that is 20s wall and 0.2s CPU is waiting on a network and
wants concurrency or a tighter budget; a span that is 20s wall and 19s CPU is
computing and wants an algorithm. Ratios of end-to-end totals cannot tell
those apart, which is precisely how the first two hypotheses survived.

`thread_time` MEASURES THE CALLING THREAD ONLY. Retrieval fans out across a
pool, so a parallel fetch shows the parent's coordination cost here and not
the workers' -- the gap between `wall_ms` and `cpu_ms` on that span is
network AND child-thread compute together. Stated here because a number
whose blind spot is undocumented is the kind that gets over-read later.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

#: Spans a reader may expect on a completed analysis. Not enforced -- a
#: pipeline that grows a stage should record it -- but the interactive budget
#: is written against these, so a missing one is a question worth asking.
CORE_SPANS = ("discovery", "source_selection", "retrieval", "core_composition")
DEEP_SPANS = ("deep_reasoning",)


class Trace:
    """Spans for ONE analysis, in the order they completed."""

    def __init__(self, run_id: str = ""):
        self.run_id = run_id
        self.spans: list = []
        self._origin = time.monotonic()

    @contextmanager
    def span(self, name: str, *, deadline=None, **attrs):
        """Time one boundary. Records even when the body raises.

        A span that vanishes on failure would make every trace look healthy,
        and the failures are the runs worth reading.
        """
        began_wall = time.monotonic()
        began_cpu = time.thread_time()
        rec: dict = {"name": name,
                     "offset_s": round(began_wall - self._origin, 3)}
        rec.update(attrs)
        if deadline is not None:
            try:
                rec["deadline_remaining_start_s"] = round(deadline.remaining, 2)
            except Exception:                     # noqa: BLE001
                pass
        try:
            yield rec
            rec.setdefault("status", "ok")
        except BaseException as exc:              # noqa: BLE001 - re-raised
            rec["status"] = "error"
            rec["failure_class"] = type(exc).__name__
            raise
        finally:
            rec["wall_ms"] = round((time.monotonic() - began_wall) * 1000, 1)
            rec["cpu_ms"] = round((time.thread_time() - began_cpu) * 1000, 1)
            if deadline is not None:
                try:
                    rec["deadline_remaining_end_s"] = round(
                        deadline.remaining, 2)
                except Exception:                 # noqa: BLE001
                    pass
            self.spans.append(rec)

    def waterfall(self) -> dict:
        """What the spans add up to, and what they do NOT account for.

        UNACCOUNTED TIME IS REPORTED, not hidden. If the spans sum to 40s of
        a 135s wall clock then the interesting 95s is somewhere nobody
        instrumented, and a waterfall that quietly omits it would send the
        next reader to optimise the 40s.
        """
        wall = round((time.monotonic() - self._origin) * 1000, 1)
        covered = sum(s.get("wall_ms", 0.0) for s in self.spans)
        return {
            "spans": list(self.spans),
            "total_wall_ms": wall,
            "covered_wall_ms": round(covered, 1),
            "unaccounted_wall_ms": round(wall - covered, 1),
            "total_cpu_ms": round(
                sum(s.get("cpu_ms", 0.0) for s in self.spans), 1),
        }

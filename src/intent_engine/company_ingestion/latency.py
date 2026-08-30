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


#: Work with a KNOWN cost and no I/O whatsoever. Sized to be a few
#: milliseconds on a developer machine -- large enough to measure, far too
#: small to matter next to a 90-second analysis.
_YARDSTICK_ROUNDS = 60_000


def cpu_yardstick() -> dict:
    """Wall AND CPU for a fixed, pure-CPU workload with no I/O of any kind.

    WHY A YARDSTICK AND NOT A RATIO. `wall_ms` high with `cpu_ms` low has two
    completely different causes -- blocking on I/O, or being descheduled
    while ready to run -- and they demand opposite repairs. `build_report`
    assembles in-memory structures and CANNOT do I/O, yet deployed it shows
    2702ms wall against 404ms CPU: its CPU time grew 1.4x while its wall grew
    9.2x. That is a CPU share, not a network. Running a known quantity of
    arithmetic inline turns that inference into a measurement.

    WHY BOTH CLOCKS, AND NOT JUST WALL. Wall alone cannot separate the two
    ways a machine can be slow, and they are bought differently:

        wall up 9x, probe CPU FLAT   -> the work needed the same CPU and
                                        waited to be scheduled. A larger CPU
                                        SHARE fixes this.
        wall up 9x, probe CPU UP 9x  -> the core executes this arithmetic
                                        slower (or the CPU clock is charged
                                        for time stolen by the hypervisor).
                                        A bigger share buys nothing; a
                                        FASTER CLASS of machine is required.

    Recording only wall would let an infrastructure purchase be argued from a
    number that cannot tell those apart. `rounds` is returned so a later
    reader can confirm two readings measured the SAME work -- comparing
    across a changed constant would be silently meaningless.
    """
    import hashlib
    began_wall = time.monotonic()
    began_cpu = time.thread_time()
    digest = b"0" * 64
    for _ in range(_YARDSTICK_ROUNDS):
        digest = hashlib.sha256(digest).digest()
    return {
        "wall_ms": round((time.monotonic() - began_wall) * 1000, 2),
        "cpu_ms": round((time.thread_time() - began_cpu) * 1000, 2),
        "rounds": _YARDSTICK_ROUNDS,
    }


class Trace:
    """Spans for ONE analysis, in the order they completed."""

    def __init__(self, run_id: str = ""):
        self.run_id = run_id
        self.spans: list = []
        self._origin = time.monotonic()
        self._depth = 0

    @contextmanager
    def span(self, name: str, *, deadline=None, **attrs):
        """Time one boundary. Records even when the body raises.

        A span that vanishes on failure would make every trace look healthy,
        and the failures are the runs worth reading.
        """
        began_wall = time.monotonic()
        began_cpu = time.thread_time()
        # DEPTH, because a nested span's time is ALSO its parent's time.
        # `quality_retry_fetch` lives inside `core_composition`; summing every
        # span would count those seconds twice and drive `unaccounted`
        # negative -- an accounting error that would quietly discredit the one
        # number this module exists to make trustworthy.
        rec: dict = {"name": name, "depth": self._depth,
                     "offset_s": round(began_wall - self._origin, 3)}
        self._depth += 1
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
            self._depth -= 1
            rec["wall_ms"] = round((time.monotonic() - began_wall) * 1000, 1)
            rec["cpu_ms"] = round((time.thread_time() - began_cpu) * 1000, 1)
            if deadline is not None:
                try:
                    rec["deadline_remaining_end_s"] = round(
                        deadline.remaining, 2)
                except Exception:                 # noqa: BLE001
                    pass
            self.spans.append(rec)

    def mark(self, name: str, began_wall: float, began_cpu: float,
             **attrs) -> dict:
        """Record a span from timings the caller already took.

        WHY THIS EXISTS ALONGSIDE `span`. Wrapping an existing multi-line
        block in a `with` means re-indenting every line inside it, and doing
        that purely to add a measurement is how a 51-line call had its
        arguments silently re-associated and how an edit referencing a
        helper that did not exist reached the tree. A block that is awkward
        to wrap gets two timestamps and this call instead: no indentation
        changes, so the diff is additive and the code under it is untouched.

        Depth follows the CURRENT nesting, so a marked span sits beside the
        `with`-style spans recorded at the same level rather than looking
        like a top-level stage.
        """
        rec: dict = {"name": name, "depth": self._depth,
                     "offset_s": round(began_wall - self._origin, 3),
                     "wall_ms": round((time.monotonic() - began_wall) * 1000, 1),
                     "cpu_ms": round((time.thread_time() - began_cpu) * 1000, 1),
                     "status": "ok"}
        rec.update(attrs)
        self.spans.append(rec)
        return rec

    def calibrate(self, name: str) -> dict:
        """Record one CPU yardstick reading as a span.

        NOT a pipeline stage: flagged `calibration` so the waterfall excludes
        it from both covered wall and total CPU. A probe that vanished on
        failure would leave the trace looking complete while the one number
        that interprets every other span is missing, so a failure is recorded
        with its class rather than swallowed -- the same bare-`except` that
        hid `external_context` for four wrong hypotheses.
        """
        rec: dict = {"name": name, "depth": 0, "calibration": True,
                     "offset_s": round(time.monotonic() - self._origin, 3)}
        try:
            rec.update(cpu_yardstick())
            rec["status"] = "ok"
        except Exception as exc:                  # noqa: BLE001
            rec["status"] = "error"
            rec["failure_class"] = type(exc).__name__
            rec["wall_ms"] = 0.0
            rec["cpu_ms"] = 0.0
        self.spans.append(rec)
        return rec

    def waterfall(self) -> dict:
        """What the spans add up to, and what they do NOT account for.

        UNACCOUNTED TIME IS REPORTED, not hidden. If the spans sum to 40s of
        a 135s wall clock then the interesting 95s is somewhere nobody
        instrumented, and a waterfall that quietly omits it would send the
        next reader to optimise the 40s.
        """
        wall = round((time.monotonic() - self._origin) * 1000, 1)
        # TOP-LEVEL ONLY. Children are a breakdown OF a parent, not additional
        # elapsed time beside it.
        # Calibration spans are instrument overhead, not pipeline stages, so
        # they are excluded from coverage -- counting them would make the
        # waterfall claim it explained time the product never spent.
        covered = sum(s.get("wall_ms", 0.0) for s in self.spans
                      if s.get("depth", 0) == 0 and not s.get("calibration"))
        return {
            "spans": list(self.spans),
            "total_wall_ms": wall,
            "covered_wall_ms": round(covered, 1),
            "unaccounted_wall_ms": round(wall - covered, 1),
            # SAME EXCLUSION AS `covered`. The probe burns real CPU by
            # design; counting it would charge the product for cycles the
            # instrument spent measuring the machine.
            "total_cpu_ms": round(
                sum(s.get("cpu_ms", 0.0) for s in self.spans
                    if s.get("depth", 0) == 0 and not s.get("calibration")), 1),
        }

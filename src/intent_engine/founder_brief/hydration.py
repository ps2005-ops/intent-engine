"""What is ready to show yet — read from the subsystems, never from a clock.

WHY THIS IS A PROJECTION AND NOT A SYSTEM
-----------------------------------------
A progress bar that advances on elapsed time is a lie with a smooth
animation: it says "checking current evidence" while nothing is checking
anything, and it says "ready" because sixty seconds passed. The only honest
loading state is one derived from whether the canonical output actually
exists, so this module computes NOTHING of its own. It reads what the run has
produced and reports which tier that makes available.

That is also why it lives beside the surfaces rather than in the pipeline. It
has no opinion about the company; it has an opinion about us.

THE TIERS ARE WHAT A READER CAN ACT ON, NOT WHAT THE PIPELINE DOES
------------------------------------------------------------------
    T0  who this is
    T1  what we already knew before this run
    T2  what the evidence says now
    T3  what it means, stressed against alternatives

A reader can use T1 without T3. Ordering the tiers by usefulness rather than
by execution order is what lets the page be worth reading before it is
finished.

DEGRADED IS NOT FAILED, AND NEITHER IS BOUNDED
----------------------------------------------
A tier whose producers ran and honestly found little is BOUNDED -- the
analysis is thin and the page should say so. A tier whose producers were
blocked is DEGRADED. A tier that never ran is PENDING. Collapsing these into
one spinner is how a blocked retrieval and a quiet company come to look
identical, which is the error this codebase has now corrected at four
different layers.
"""
from __future__ import annotations

from typing import Dict, Sequence

CONTRACT = "hydration.v1"

PENDING = "PENDING"
RUNNING = "RUNNING"
READY = "READY"
BOUNDED = "BOUNDED"
DEGRADED = "DEGRADED"
UNMEASURABLE = "UNMEASURABLE"
FAILED = "FAILED"

HYDRATION_STATES = (PENDING, RUNNING, READY, BOUNDED, DEGRADED, UNMEASURABLE,
                    FAILED)

#: States a surface may render content for. BOUNDED and DEGRADED are here:
#: both have something true to show, and hiding them would leave the reader
#: with a blank card and no reason for it.
SHOWS_CONTENT = frozenset({READY, BOUNDED, DEGRADED})

T0, T1, T2, T3 = "T0", "T1", "T2", "T3"
TIERS = (T0, T1, T2, T3)

#: What the reader is told is happening, per tier. Deliberately about the
#: WORK, not about the machinery: "Identifying the company", never "running
#: the identity resolver".
TIER_COPY = {
    T0: "Identifying the company",
    T1: "Loading what we already know",
    T2: "Checking current evidence",
    T3: "Stress-testing the reading",
}

#: The finer-grained lines a surface may cycle through while a tier runs. Each
#: names a real step; none of them claims a result.
STEP_COPY = {
    T1: ("Loading what we already know",
         "Recalling the previous reading"),
    T2: ("Checking current evidence",
         "Looking for independent confirmation",
         "Testing previous beliefs"),
    T3: ("Evaluating economic exposure",
         "Checking relevant history",
         "Stress-testing competitor responses",
         "Updating the recommendation"),
}


def _present(value) -> bool:
    """Whether a producer actually produced something."""
    if value is None or value is False:
        return False
    if isinstance(value, (str, bytes)):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _tier_state(*, produced: Sequence[bool], attempted: bool,
                blocked: bool) -> str:
    """READY only when the canonical outputs exist. Never from a timer."""
    if not attempted:
        return PENDING
    got = sum(1 for p in produced if p)
    if got and got == len(produced):
        return READY
    if got:
        # Some producers delivered and some did not. Real, partial, and
        # sayable -- not a spinner still pretending to work.
        return DEGRADED if blocked else BOUNDED
    return DEGRADED if blocked else RUNNING


def assess(*, identity=None, previous_decision=None, market_snapshot=None,
           source_coverage=None, discovery_coverage=None, decision=None,
           economic_history=None, second_iteration=None,
           blocked: bool = False, finished: bool = False) -> Dict[str, object]:
    """Which tiers a reader can be shown, derived from canonical outputs.

    `finished` says the run has stopped, which turns a tier that produced
    nothing from RUNNING into a settled state. Nothing here consults a clock:
    a run that is still going and a run that finished empty are different
    facts, and only the caller knows which it is holding.
    """
    d = decision if isinstance(decision, dict) else {}

    tiers = {
        T0: _tier_state(produced=[_present(identity)], attempted=True,
                        blocked=False),
        T1: _tier_state(
            produced=[_present(previous_decision), _present(market_snapshot)],
            attempted=True, blocked=blocked),
        T2: _tier_state(
            produced=[_present(source_coverage), _present(discovery_coverage)],
            attempted=True, blocked=blocked),
        T3: _tier_state(
            produced=[_present(d.get("recommended_next_move")),
                      _present(economic_history),
                      _present(second_iteration)],
            attempted=bool(d) or finished, blocked=blocked),
    }
    if finished:
        # A finished run has no RUNNING tiers. Whatever did not arrive is not
        # arriving, and saying otherwise is the animated lie.
        tiers = {k: (BOUNDED if v == RUNNING else v) for k, v in tiers.items()}

    ready = [t for t in TIERS if tiers[t] in SHOWS_CONTENT]
    return {
        "contract": CONTRACT,
        "tiers": tiers,
        "showable": ready,
        "highest_showable": ready[-1] if ready else "",
        "current_step": _current_step(tiers, finished),
        "finished": bool(finished),
    }


def _current_step(tiers: Dict[str, str], finished: bool) -> str:
    """The line a reader sees right now. Empty once nothing is running."""
    if finished:
        return ""
    for tier in TIERS:
        if tiers.get(tier) in (PENDING, RUNNING):
            return TIER_COPY.get(tier, "")
    return ""


def telemetry(marks: Dict[str, float]) -> Dict[str, object]:
    """Durations as MEASURED, with the targets stated beside them.

    The targets are reported, never enforced: a page that adjusted its own
    definition of ready to meet a latency number would be the same lie as the
    timer. `met` is an observation about this run.
    """
    def _ms(key):
        value = marks.get(key)
        return int(value) if isinstance(value, (int, float)) else None

    out = {"contract": CONTRACT}
    for key in ("ttfp_ms", "t1_ms", "t2_ms", "t3_ms", "total_ms",
                "discovery_ms", "fetch_ms", "compose_ms"):
        out[key] = _ms(key)
    targets = {"t1_ms": 2_000, "t2_ms": 15_000, "t3_ms": 60_000}
    out["targets_ms"] = targets
    out["met"] = {k: (None if out.get(k) is None else out[k] <= v)
                  for k, v in targets.items()}
    return out

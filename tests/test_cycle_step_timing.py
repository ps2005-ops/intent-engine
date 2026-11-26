"""A cycle that overruns must be able to say which step overran.

The Nov 18-22 night cycles ran 11-22 hours and held the shared lock through
five 06:30 day cycles. The ledger recorded every step as "ok" and no duration,
so the slow step could not be identified after the fact.
"""
import json

from intent_engine.market import cycle as C


def test_run_step_records_its_duration_and_the_ledger_keeps_it():
    clock = iter([100.0, 107.25])
    real = C.time.monotonic
    C.time.monotonic = lambda: next(clock)
    try:
        ctx = C.CycleContext(cycle="night", as_of="2026-11-26", root=None,
                             session=None, run_id="t", dry_run=True)
        step = C.run_step("replay", lambda c: {"n": 1}, ctx,
                          sleep=lambda s: None)
    finally:
        C.time.monotonic = real
    assert step.seconds == 7.25
    assert json.loads(json.dumps(step.as_dict()))["seconds"] == 7.25


def test_a_failed_step_is_timed_too():
    def boom(ctx):
        raise ValueError("bad payload")
    ctx = C.CycleContext(cycle="night", as_of="2026-11-26", root=None,
                         session=None, run_id="t", dry_run=True)
    step = C.run_step("research", boom, ctx, attempts=1, sleep=lambda s: None)
    assert step.status == "failed"
    assert step.seconds is not None and step.seconds >= 0

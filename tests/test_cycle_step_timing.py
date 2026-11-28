"""A cycle that overruns must say which step, and whether the host slept.

Nov 18-22: night cycles ran 11-22h of wall time on battery (60-248 sleep
entries each) for ~1h of work. On macOS time.monotonic pauses in sleep, so
wall and awake seconds are both recorded: they differ only when the host slept.
"""
import json

from intent_engine.market import cycle as C


def _ctx():
    return C.CycleContext(cycle="night", as_of="2026-11-26", root=None,
                          session=None, run_id="t", dry_run=True)


def test_a_suspended_step_shows_wall_far_above_awake(monkeypatch):
    wall = iter([1000.0, 1000.0 + 22 * 3600])     # 22h of wall time
    awake = iter([50.0, 50.0 + 3600])             # 1h awake
    monkeypatch.setattr(C.time, "time", lambda: next(wall))
    monkeypatch.setattr(C.time, "monotonic", lambda: next(awake))
    step = C.run_step("research", lambda c: {"n": 1}, _ctx(), sleep=lambda s: None)
    assert step.seconds == 22 * 3600 and step.awake_seconds == 3600
    d = json.loads(json.dumps(step.as_dict()))
    assert d["seconds"] == 79200 and d["awake_seconds"] == 3600


def test_a_failed_step_is_timed_too():
    def boom(ctx):
        raise ValueError("bad payload")
    step = C.run_step("research", boom, _ctx(), attempts=1, sleep=lambda s: None)
    assert step.status == "failed"
    assert step.seconds is not None and step.awake_seconds is not None

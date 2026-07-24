"""In-process scheduler (deployment path): due-logic, idempotency,
market-calendar gating, restart-safety, failure retry. No threads/sleeps."""
from datetime import datetime
from types import SimpleNamespace

from intent_engine.runtime.scheduler import (
    MarkerStore, Scheduler, is_due, run_due,
)


def _ok(job):
    return [SimpleNamespace(name=job, status="succeeded", error=None, detail={})]


def _fail(job):
    return [SimpleNamespace(name=job, status="failed", error="boom", detail={})]


MON = datetime(2026, 7, 20, 22, 0)     # a Monday, market day


def test_is_due_daily():
    assert is_due("market_day", MON, None, market_day=True)
    assert not is_due("market_day", MON, MON.isoformat(), market_day=True)
    assert is_due("market_day", MON, "2026-07-19T22:00:00", market_day=True)


def test_is_due_gated_by_market_day():
    assert not is_due("market_day", MON, None, market_day=False)


def test_is_due_weekly_and_monthly():
    assert is_due("weekly", datetime(2026, 7, 27, 9, 0),
                  "2026-07-20T09:00:00", market_day=True)
    assert not is_due("weekly", datetime(2026, 7, 22, 9, 0),
                      "2026-07-20T09:00:00", market_day=True)   # same ISO week
    assert is_due("monthly", datetime(2026, 8, 1, 9, 0),
                  "2026-07-31T09:00:00", market_day=True)
    assert not is_due("monthly", datetime(2026, 7, 31, 9, 0),
                      "2026-07-01T09:00:00", market_day=True)   # same month


def test_run_due_fires_and_is_idempotent(tmp_path):
    fired = []
    def dispatch(job, root, as_of):
        fired.append(job)
        return _ok(job)
    out = run_due(tmp_path, now=MON, dispatch_fn=dispatch,
                  market_day_fn=lambda: True)
    assert set(out) == {"daily", "synthetic-daily", "weekly-eval", "monthly-packet"}
    assert all(v == "fired" for v in out.values())
    fired.clear()
    run_due(tmp_path, now=MON, dispatch_fn=dispatch, market_day_fn=lambda: True)
    assert fired == []                     # nothing due again the same day


def test_failed_job_is_not_marked_done_but_backs_off(tmp_path):
    from datetime import timedelta
    run_due(tmp_path, now=MON, dispatch_fn=lambda job, root, as_of: _fail(job),
            market_day_fn=lambda: True)
    # failed -> recorded but NOT marked fired (period not satisfied)
    assert MarkerStore(tmp_path).fired_at("daily") is None
    # the very next tick must NOT re-attempt (backoff), else it hammers
    fired = []
    run_due(tmp_path, now=MON + timedelta(minutes=5),
            dispatch_fn=lambda job, root, as_of: (fired.append(job) or _ok(job)),
            market_day_fn=lambda: True)
    assert "daily" not in fired
    # after the backoff window it retries and can succeed
    fired.clear()
    run_due(tmp_path, now=MON + timedelta(hours=2),
            dispatch_fn=lambda job, root, as_of: (fired.append(job) or _ok(job)),
            market_day_fn=lambda: True)
    assert "daily" in fired
    assert MarkerStore(tmp_path).fired_at("daily") is not None


def test_persistent_failure_does_not_hammer_every_tick(tmp_path):
    from datetime import timedelta
    attempts = []
    for i in range(6):                       # six 5-minute ticks in one hour
        run_due(tmp_path, now=MON + timedelta(minutes=5 * i),
                dispatch_fn=lambda job, root, as_of: (attempts.append(job) or _fail(job)),
                market_day_fn=lambda: True)
    # backoff caps re-attempts within the hour to one (not six)
    assert attempts.count("daily") == 1


def test_marker_survives_restart(tmp_path):
    run_due(tmp_path, now=MON, dispatch_fn=lambda job, root, as_of: _ok(job),
            market_day_fn=lambda: True)
    # a fresh MarkerStore (simulating a restart) sees the persisted success
    assert MarkerStore(tmp_path).fired_at("daily") is not None


def test_legacy_marker_format_is_read(tmp_path):
    """Migration: the old {job: iso} marker format still loads as a `fired`."""
    import json
    (tmp_path / "status").mkdir()
    (tmp_path / "status" / "scheduler.json").write_text(
        json.dumps({"daily": "2026-07-20T22:00:00"}))
    assert MarkerStore(tmp_path).fired_at("daily") == "2026-07-20T22:00:00"


def test_scheduler_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    assert Scheduler.enabled() is False
    monkeypatch.setenv("SCHEDULER_ENABLED", "1")
    assert Scheduler.enabled() is True


def test_scheduler_tick_is_observable(tmp_path):
    """A scheduler that silently stops is the top production risk. Each tick
    is a persistent, observable job — success AND failure are recorded."""
    from unittest import mock
    from intent_engine.runtime.jobs import latest_status
    sched = Scheduler(tmp_path)
    sched.tick()
    assert latest_status(tmp_path)["scheduler-tick"]["status"] == "succeeded"
    with mock.patch("intent_engine.runtime.scheduler.run_due",
                    side_effect=RuntimeError("dispatch boom")):
        sched.tick()
    st = latest_status(tmp_path)["scheduler-tick"]
    assert st["status"] == "failed" and "dispatch boom" in st["error"]


def test_holiday_skips_market_job_but_not_synthetic(tmp_path):
    fired = []
    run_due(tmp_path, now=MON,
            dispatch_fn=lambda job, root, as_of: (fired.append(job) or _ok(job)),
            market_day_fn=lambda: False)          # holiday
    assert "daily" not in fired                    # market job gated
    assert "synthetic-daily" in fired              # runs every day

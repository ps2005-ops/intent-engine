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


def test_failed_job_marker_not_advanced_so_it_retries(tmp_path):
    run_due(tmp_path, now=MON, dispatch_fn=lambda job, root, as_of: _fail(job),
            market_day_fn=lambda: True)
    assert "daily" not in MarkerStore(tmp_path).read()      # never marked fired
    fired = []
    run_due(tmp_path, now=MON,
            dispatch_fn=lambda job, root, as_of: (fired.append(job) or _ok(job)),
            market_day_fn=lambda: True)
    assert "daily" in fired                                 # retried


def test_marker_survives_restart(tmp_path):
    run_due(tmp_path, now=MON, dispatch_fn=lambda job, root, as_of: _ok(job),
            market_day_fn=lambda: True)
    # a fresh MarkerStore (simulating a restart) sees the persisted markers
    assert "daily" in MarkerStore(tmp_path).read()


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

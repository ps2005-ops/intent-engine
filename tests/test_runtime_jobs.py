"""Scheduler jobs (1B): locking, idempotency, restart-safety, persistent
failure events, and health status."""
import os

from intent_engine.events import CompanyEventBus
from intent_engine.runtime.config_health import check_config, preflight
from intent_engine.runtime.jobs import JobLock, latest_status, run_job
from intent_engine.runtime.locks import JobLockedError


def test_job_success_emits_events_and_status(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    r = run_job("demo", lambda: {"ok": True}, root=tmp_path, bus=bus)
    assert r.status == "succeeded" and r.detail == {"ok": True}
    types = [e.event_type for e in bus.store.read_all()]
    assert "job.started" in types and "job.succeeded" in types
    assert latest_status(tmp_path)["demo"]["status"] == "succeeded"


def test_job_failure_is_persistent(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    def boom():
        raise ValueError("kaboom")
    r = run_job("boom", boom, root=tmp_path, bus=bus, retries=1)
    assert r.status == "failed" and "kaboom" in r.error
    failed = [e for e in bus.store.read_all() if e.event_type == "job.failed"]
    assert len(failed) == 1 and failed[0].payload["attempts"] == 2
    # persisted to disk (survives restart / visible in health)
    assert latest_status(tmp_path)["boom"]["status"] == "failed"


def test_concurrent_lock_prevents_duplicate_run(tmp_path):
    with JobLock("solo", root=tmp_path):
        try:
            with JobLock("solo", root=tmp_path):
                assert False, "second holder must fail"
        except JobLockedError:
            pass


def test_locked_job_reports_locked(tmp_path):
    with JobLock("busy", root=tmp_path):
        r = run_job("busy", lambda: {"x": 1}, root=tmp_path)
    assert r.status == "locked"


def test_lock_released_after_use(tmp_path):
    with JobLock("reuse", root=tmp_path):
        pass
    with JobLock("reuse", root=tmp_path):     # re-acquirable -> restart-safe
        pass


def test_missing_credentials_create_visible_persistent_failure(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    # ensure required keys are absent
    for var in ("TIINGO_API_KEY", "FRED_API_KEY"):
        os.environ.pop(var, None)
    snap = preflight(bus=bus, root=tmp_path)
    assert snap["healthy"] is False
    assert "TIINGO_API_KEY" in snap["missing_required"]
    failed = [e for e in bus.store.read_all()
              if e.event_type == "config.preflight_failed"]
    assert failed and all("value" not in e.payload for e in failed)
    # persisted health snapshot on disk
    assert (tmp_path / "config_health_latest.json").exists()


def test_preflight_never_exposes_secret_values(tmp_path, monkeypatch):
    monkeypatch.setenv("TIINGO_API_KEY", "SUPERSECRETVALUE1234567890")
    report = check_config()
    dumped = str(report)
    assert "SUPERSECRETVALUE" not in dumped
    assert report["TIINGO_API_KEY"]["status"] == "unprobed"   # present, not echoed

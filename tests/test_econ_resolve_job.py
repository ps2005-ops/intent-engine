"""The econ forward ledger's scheduled resolver. Synthetic ALFRED rows only."""
import json
import pathlib

import pytest

from intent_engine.econ import forward_engine as FE
from intent_engine.econ import forward_ledger as FL
from intent_engine.econ import resolve_job as RJ

PERMIT = {"expectation_id": "rl-test-permit", "created_at": "2026-08-27",
          "information_cutoff": "2026-08-27", "confidence": 0.55,
          "expected_direction": "DOWN", "expires_at": "2026-12-25",
          "horizon_days": 120, "outcome": "OPEN",
          "quantity": "PERMIT/MORTGAGE30US->PERMIT",
          "resolution_rule": "PERMIT is DOWN at the horizon relative to 2026-06-01",
          "resolution_contract": {"baseline_period": "2026-06-01",
                                  "direction": "DOWN", "horizon_days": 120,
                                  "resolves_from": "2026-12-25",
                                  "series_id": "PERMIT",
                                  "vintage_policy": "LATEST_REVISION"}}


def _ledger(tmp_path, *recs):
    p = tmp_path / "ledger.jsonl"
    FL.append(list(recs) or [PERMIT], path=p)
    return p


def _rows(oct_value=1300.0, oct_vintage="2026-11-18"):
    return [{"date": "2026-06-01", "realtime_start": "2026-07-17", "value": "1400"},
            {"date": "2026-10-01", "realtime_start": oct_vintage,
             "value": str(oct_value)}]


def _run(tmp_path, ledger, at, fetch, write=True):
    return RJ.run(at=at, ledger_path=ledger, log_path=tmp_path / "log.jsonl",
                  fetch=fetch, write=write)


def test_before_the_horizon_nothing_is_fetched_or_appended(tmp_path):
    led = _ledger(tmp_path)
    called = []
    r = _run(tmp_path, led, "2026-12-24", lambda *a: called.append(a) or [])
    assert r["open"] == 1 and r["appended"] == 0 and not called


def test_due_with_data_resolves_by_appending_and_keeps_the_original(tmp_path):
    led = _ledger(tmp_path)
    before = led.read_text().splitlines()[0]
    r = _run(tmp_path, led, "2026-12-25", lambda *a: _rows())
    assert r["appended"] == 1 and r["resolved"][0]["correct"] is True
    lines = led.read_text().splitlines()
    assert lines[0] == before and len(lines) == 2
    cur = FL.by_id(led)["rl-test-permit"]
    assert cur["outcome"] == FE.RESOLVED and cur["resolved_at"] == "2026-12-25"
    assert cur["confidence"] == 0.55 and cur["expires_at"] == "2026-12-25"
    assert cur["squared_error"] == pytest.approx((0.55 - 1) ** 2)


def test_rerun_after_resolution_appends_nothing(tmp_path):
    led = _ledger(tmp_path)
    _run(tmp_path, led, "2026-12-25", lambda *a: _rows())
    r = _run(tmp_path, led, "2026-12-26", lambda *a: _rows(oct_value=9999))
    assert r["appended"] == 0 and r["terminal"] == 1


def test_a_vintage_published_after_the_run_date_is_never_read(tmp_path):
    led = _ledger(tmp_path)
    r = _run(tmp_path, led, "2026-12-25",
             lambda *a: _rows(oct_vintage="2026-12-30"))
    assert r["appended"] == 0 and r["blocked"]


def test_unpublished_is_blocked_then_expires_only_after_the_grace(tmp_path):
    led = _ledger(tmp_path)
    only_base = lambda *a: _rows()[:1]
    assert _run(tmp_path, led, "2027-01-10", only_base)["appended"] == 0
    late = "2027-04-25"            # 2026-12-25 + 120 days + 1
    r = _run(tmp_path, led, late, only_base)
    assert r["expired"] and FL.by_id(led)["rl-test-permit"]["outcome"] == FE.EXPIRED


def test_a_provider_failure_is_blocked_and_alerts_never_resolves(tmp_path):
    led = _ledger(tmp_path)

    def boom(*a):
        raise OSError("ALFRED down")
    r = _run(tmp_path, led, "2026-12-25", boom)
    assert r["appended"] == 0 and r["status"] == "ALERT"
    assert FL.by_id(led)["rl-test-permit"]["outcome"] == "OPEN"


def test_missed_days_are_reported(tmp_path):
    led = _ledger(tmp_path)
    _run(tmp_path, led, "2026-12-01", lambda *a: [])
    r = _run(tmp_path, led, "2026-12-11", lambda *a: [])
    assert r["missed_runs"] == 9 and r["status"] == "ALERT"


def test_dry_run_writes_neither_ledger_nor_log(tmp_path):
    led = _ledger(tmp_path)
    before = led.read_bytes()
    r = _run(tmp_path, led, "2026-12-25", lambda *a: _rows(), write=False)
    assert r["would_append"] == 1 and led.read_bytes() == before
    assert not (tmp_path / "log.jsonl").exists()


def test_the_cli_refuses_a_backdated_or_future_write(tmp_path):
    led = _ledger(tmp_path)
    with pytest.raises(SystemExit):
        RJ.main(["--ledger", str(led), "--log", str(tmp_path / "l"),
                 "--at", "2020-01-01"])
    with pytest.raises(SystemExit):
        RJ.main(["--ledger", str(led), "--log", str(tmp_path / "l"),
                 "--at", "2999-01-01", "--dry-run"])

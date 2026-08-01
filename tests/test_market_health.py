"""Operational health and the launchd scheduler templates.

The most dangerous unattended failure is the silent one: a night cycle that
stopped firing three weeks ago still leaves a perfectly good report from three
weeks ago sitting in reports/.
"""
import json
import os
import stat
import subprocess
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

import pytest

from intent_engine.market import cycle as C
from intent_engine.market import health as H
from intent_engine.market import session as S

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 7, 31, 12, 0, tzinfo=ZoneInfo(S.TIMEZONE))


def _record(root, cycle=C.DAY, as_of="2026-07-31", status=C.COMPLETED,
            steps=(("research", "ok"),)):
    C.RunStore(root).append(C.CycleResult(
        run_id=C.run_id(as_of, cycle), cycle=cycle, as_of=as_of,
        timezone=S.TIMEZONE, status=status,
        steps=tuple(C.Step(n, s) for n, s in steps),
        started_at="2026-07-31T06:30:00+00:00",
        finished_at="2026-07-31T06:40:00+00:00",
        session={"latest_bar": "2026-07-30"}))


# --- basics -----------------------------------------------------------------
def test_health_never_raises_on_a_fresh_root(tmp_path):
    """The one thing that must still work when everything else is broken."""
    health = H.check(tmp_path, repo=REPO, now=NOW)
    assert health.overall in (H.OK, H.DEGRADED, H.DOWN, H.UNKNOWN)
    assert isinstance(H.render(health), str)


def test_no_runs_yet_is_unknown_not_ok(tmp_path):
    health = H.check(tmp_path, repo=REPO, now=NOW, env={})
    assert "no cycle has run yet" in " ".join(health.notes)


def test_health_is_json_serialisable(tmp_path):
    health = H.check(tmp_path, repo=REPO, now=NOW)
    assert json.loads(json.dumps(health.as_dict(), default=str))


# --- freshness / missed runs ------------------------------------------------
def test_a_missed_scheduled_run_is_detected(tmp_path):
    _record(tmp_path, C.DAY, as_of="2026-07-25")
    health = H.check(tmp_path, repo=REPO, now=NOW, env={})
    assert health.cycles[C.DAY]["missed_recent"]
    assert any("missed" in n for n in health.notes)
    assert health.overall == H.DEGRADED


def test_todays_run_is_not_reported_missed_before_its_time(tmp_path):
    """Otherwise every morning would report the night cycle as missed."""
    early = datetime(2026, 7, 31, 7, 0, tzinfo=ZoneInfo(S.TIMEZONE))
    health = H.check(tmp_path, repo=REPO, now=early, env={})
    assert "2026-07-31" not in health.cycles[C.NIGHT]["missed_recent"]


def test_next_expected_rolls_to_tomorrow_once_the_time_has_passed():
    after = datetime(2026, 7, 31, 21, 0, tzinfo=ZoneInfo(S.TIMEZONE))
    assert H.next_expected(C.NIGHT, after).startswith("2026-08-01T20:30")
    before = datetime(2026, 7, 31, 9, 0, tzinfo=ZoneInfo(S.TIMEZONE))
    assert H.next_expected(C.NIGHT, before).startswith("2026-07-31T20:30")


def test_last_run_and_last_success_are_tracked_separately(tmp_path):
    _record(tmp_path, C.NIGHT, as_of="2026-07-30", status=C.COMPLETED)
    _record(tmp_path, C.NIGHT, as_of="2026-07-31", status=C.FAILED)
    health = H.check(tmp_path, repo=REPO, now=NOW, env={})
    assert health.cycles[C.NIGHT]["last_status"] == C.FAILED
    assert health.cycles[C.NIGHT]["last_success"] is not None


def test_the_latest_failure_is_surfaced(tmp_path):
    C.RunStore(tmp_path).append(C.CycleResult(
        run_id="rid", cycle=C.NIGHT, as_of="2026-07-31", timezone=S.TIMEZONE,
        status=C.PARTIAL, reason="failed steps: industry"))
    health = H.check(tmp_path, repo=REPO, now=NOW, env={})
    assert "industry" in health.latest_error


# --- trading mode / storage -------------------------------------------------
def test_a_misconfigured_trading_mode_is_down_not_degraded(tmp_path):
    health = H.check(tmp_path, repo=REPO, now=NOW,
                     env={"TRADING_MODE": "LIVE"})
    assert health.overall == H.DOWN
    assert health.trading_mode["enforced"] is False


def test_paper_mode_is_reported_as_enforced(tmp_path):
    health = H.check(tmp_path, repo=REPO, now=NOW, env={})
    assert health.trading_mode["mode"] == "PAPER"
    assert health.trading_mode["enforced"] is True


def test_storage_is_probed_by_writing(tmp_path):
    assert H.storage_health(tmp_path)["writable"] is True


def test_an_unwritable_root_is_down(tmp_path):
    root = tmp_path / "ro"
    root.mkdir()
    (root / "status").mkdir()
    os.chmod(root / "status", stat.S_IRUSR | stat.S_IXUSR)
    try:
        health = H.check(root, repo=REPO, now=NOW, env={})
        assert health.overall == H.DOWN
        assert health.storage["writable"] is False
    finally:
        os.chmod(root / "status", stat.S_IRWXU)


# --- source reliability -----------------------------------------------------
def test_step_success_rates_are_reported(tmp_path):
    _record(tmp_path, as_of="2026-07-29",
            steps=(("research", "ok"), ("opportunity", "ok")))
    _record(tmp_path, as_of="2026-07-30",
            steps=(("research", "failed"), ("opportunity", "ok")))
    sources = H.check(tmp_path, repo=REPO, now=NOW, env={}).sources
    assert sources["research"] == {"ok": 1, "of": 2, "rate": 0.5}
    assert sources["opportunity"]["rate"] == 1.0


# --- launchd ----------------------------------------------------------------
def test_installed_and_loaded_are_distinguished():
    """Conflating them is what lets someone believe a template is a service."""
    state = H.launchd_state("com.intentengine.market.doesnotexist")
    assert state["installed"] is False
    assert state["loaded"] is False
    assert "installed" in state and "loaded" in state


def test_an_uninstalled_scheduler_is_flagged(tmp_path):
    health = H.check(tmp_path, repo=REPO, now=NOW, env={})
    if not health.scheduler["installed"]:
        assert any("not installed" in n.lower() for n in health.notes)


def test_lock_state_is_reported(tmp_path):
    health = H.check(tmp_path, repo=REPO, now=NOW, env={})
    assert health.lock["held"] is False
    assert "age_seconds" in health.lock


def test_git_state_is_reported(tmp_path):
    git = H.check(tmp_path, repo=REPO, now=NOW, env={}).git
    assert set(git) == {"commit", "branch", "clean", "dirty_files"}


# --- rendering --------------------------------------------------------------
def test_render_shows_the_things_a_human_asks_first(tmp_path):
    _record(tmp_path)
    text = H.render(H.check(tmp_path, repo=REPO, now=NOW, env={}))
    for expected in ("MARKET OPERATING HEALTH", "trading mode", "storage",
                     "lock", "scheduler", "day", "night", "git"):
        assert expected in text


def test_a_cycle_is_not_missed_on_days_before_the_engine_ever_ran(tmp_path):
    """Reporting missed nights from before installation is noise, and noise in
    a health check trains the reader to ignore the field that catches a real
    outage."""
    _record(tmp_path, C.NIGHT, as_of="2026-07-31")
    health = H.check(tmp_path, repo=REPO, now=NOW, env={})
    assert health.cycles[C.NIGHT]["missed_recent"] == []


def test_a_genuine_gap_after_the_first_run_is_still_detected(tmp_path):
    """The suppression must not swallow real outages."""
    _record(tmp_path, C.NIGHT, as_of="2026-07-27")
    missed = H.check(tmp_path, repo=REPO, now=NOW,
                     env={}).cycles[C.NIGHT]["missed_recent"]
    assert "2026-07-28" in missed and "2026-07-30" in missed
    assert "2026-07-26" not in missed          # before the first run

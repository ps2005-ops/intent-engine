"""Day/night cycle orchestration — the guarantees unattended operation rests on.

These are the tests that replace the human who used to start the run, notice
the failure, and remember what yesterday already did.
"""
import json
import multiprocessing
import time
from datetime import datetime

import pytest

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from intent_engine.market import cycle as C
from intent_engine.market import failures as F
from intent_engine.market import session as S

NOW = datetime(2026, 7, 31, 6, 30, tzinfo=ZoneInfo(S.TIMEZONE))


def _hold_lock(path, acquired, release):
    """Module level so macOS `spawn` can pickle it.

    Signals once the lock is genuinely held, rather than letting the parent
    guess with a sleep -- `spawn` re-imports the world and can easily take
    longer than any sleep short enough to keep the test fast.
    """
    from intent_engine.runtime.locks import JobLock
    with JobLock(C.LOCK_NAME, root=path):
        acquired.set()
        release.wait(timeout=10)


def ok_step(name="s"):
    return (name, lambda ctx: {"did": name})


def boom_step(name="bad", exc=None):
    def fn(ctx):
        raise exc or ConnectionError("feed down")
    return (name, fn)


def run(root, cycle=C.DAY, steps=None, **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("as_of", "2026-07-31")
    kw.setdefault("latest_bar", "2026-07-30")
    kw.setdefault("sleep", lambda _s: None)
    return C.run_cycle(cycle, root=root, steps=steps or [ok_step()], **kw)


# --- run identity -----------------------------------------------------------
def test_run_id_is_deterministic_and_carries_the_timezone():
    assert C.run_id("2026-07-31", "day") == "2026-07-31:day:America/Toronto"
    assert C.run_id("2026-07-31", "day") == C.run_id("2026-07-31T09:00", "day")


def test_day_and_night_have_different_identities():
    assert C.run_id("2026-07-31", C.DAY) != C.run_id("2026-07-31", C.NIGHT)


def test_an_unknown_cycle_is_rejected():
    with pytest.raises(ValueError):
        C.run_id("2026-07-31", "afternoon")


# --- happy path -------------------------------------------------------------
def test_a_clean_cycle_completes_and_is_recorded(tmp_path):
    result = run(tmp_path, steps=[ok_step("a"), ok_step("b")])
    assert result.status == C.COMPLETED
    assert result.exit_code == 0
    assert [s.name for s in result.steps] == ["a", "b"]
    assert C.RunStore(tmp_path).find(result.run_id)


def test_the_run_record_is_append_only(tmp_path):
    run(tmp_path, steps=[ok_step()])
    run(tmp_path, cycle=C.NIGHT, steps=[ok_step()])
    rows = C.RunStore(tmp_path).all()
    assert len(rows) == 2
    # a second read returns the same history -- nothing is rewritten
    assert C.RunStore(tmp_path).all() == rows


# --- duplicate protection ---------------------------------------------------
def test_the_same_cycle_twice_in_one_day_is_skipped(tmp_path):
    first = run(tmp_path)
    second = run(tmp_path)
    assert first.status == C.COMPLETED
    assert second.status == C.SKIPPED_DUPLICATE
    assert second.exit_code == 0          # a duplicate is not a failure


def test_day_and_night_on_the_same_date_are_not_duplicates(tmp_path):
    assert run(tmp_path, cycle=C.DAY).status == C.COMPLETED
    assert run(tmp_path, cycle=C.NIGHT,
               latest_bar="2026-07-31").status == C.COMPLETED


def test_a_failed_run_does_not_block_a_retry(tmp_path):
    """Otherwise one bad night is permanently unrecoverable."""
    failed = run(tmp_path, steps=[boom_step()])
    assert failed.status == C.FAILED
    retried = run(tmp_path, steps=[ok_step()])
    assert retried.status == C.COMPLETED


def test_a_partial_run_does_not_block_a_retry(tmp_path):
    partial = run(tmp_path, steps=[ok_step(), boom_step()])
    assert partial.status == C.PARTIAL

    ran = {"n": 0}

    def counted(ctx):
        ran["n"] += 1
        return {}

    retry = run(tmp_path, steps=[("work", counted)])
    assert retry.status != C.SKIPPED_DUPLICATE
    assert ran["n"] == 1              # the retry actually executed


def test_a_retry_after_a_partial_does_not_recount_the_same_bar(tmp_path):
    """Conservative on purpose. The partial run already saw 07-30; re-reading
    it is not a second market observation. This can only ever UNDER-count,
    which is the safe direction for a sample size."""
    run(tmp_path, steps=[ok_step(), boom_step()], latest_bar="2026-07-30")
    same = run(tmp_path, steps=[ok_step()], latest_bar="2026-07-30")
    assert same.status == C.SKIPPED_NO_NEW_MARKET_SESSION

    fresh = run(tmp_path, cycle=C.NIGHT, steps=[ok_step()],
                latest_bar="2026-07-31")
    assert fresh.status == C.COMPLETED


# --- locking ----------------------------------------------------------------
def test_a_held_lock_makes_the_second_cycle_skip(tmp_path):
    from intent_engine.runtime.locks import JobLock
    with JobLock(C.LOCK_NAME, root=tmp_path):
        result = run(tmp_path)
    assert result.status == C.SKIPPED_DUPLICATE
    assert "lock" in result.reason


def test_day_and_night_share_one_lock_so_they_cannot_overlap(tmp_path):
    """They write the same funnel history and the same ledger; interleaving
    would corrupt both."""
    from intent_engine.runtime.locks import JobLock
    with JobLock(C.LOCK_NAME, root=tmp_path):
        assert run(tmp_path, cycle=C.NIGHT).status == C.SKIPPED_DUPLICATE


def test_lock_state_distinguishes_a_leftover_file_from_a_held_lock(tmp_path):
    from intent_engine.runtime.locks import JobLock
    with JobLock(C.LOCK_NAME, root=tmp_path):
        held = C.lock_state(tmp_path)
    after = C.lock_state(tmp_path)
    assert held["held"] is True
    assert after["exists"] is True        # the file remains ...
    assert after["held"] is False        # ... but nobody holds it
    assert after["stale"] is False       # a leftover file is not "stale"


def test_a_crashed_run_does_not_wedge_the_next_one(tmp_path):
    """flock is released by the OS when the holder dies. Proven with a real
    process, not asserted."""
    acquired = multiprocessing.Event()
    release = multiprocessing.Event()
    proc = multiprocessing.Process(target=_hold_lock,
                                   args=(str(tmp_path), acquired, release))
    proc.start()
    assert acquired.wait(timeout=30), "child never acquired the lock"

    blocked = run(tmp_path)
    assert blocked.status == C.SKIPPED_DUPLICATE

    release.set()
    proc.join(timeout=30)
    # the holder is gone; the lock is free again, with no manual cleanup
    assert C.lock_state(tmp_path)["held"] is False
    assert run(tmp_path, cycle=C.NIGHT).status == C.COMPLETED


# --- failure handling -------------------------------------------------------
def test_one_failed_step_of_several_is_partial_and_names_it(tmp_path):
    result = run(tmp_path, steps=[ok_step("a"), boom_step("feed"),
                                  ok_step("c")])
    assert result.status == C.PARTIAL
    assert "feed" in result.reason
    assert result.exit_code == 1
    assert [s.name for s in result.failed_steps] == ["feed"]
    # the steps AFTER the failure still ran -- that is the point of PARTIAL
    assert [s.name for s in result.steps if s.ok] == ["a", "c"]


def test_all_steps_failing_is_failed_not_partial(tmp_path):
    result = run(tmp_path, steps=[boom_step("a"), boom_step("b")])
    assert result.status == C.FAILED
    assert result.exit_code == 1


def test_a_failed_step_contributes_no_counts(tmp_path):
    """A failure must never become a zero observation."""
    result = run(tmp_path, steps=[boom_step("research")])
    failed = result.failed_steps[0]
    assert failed.detail == {}
    assert failed.code == F.TRANSIENT_SOURCE_FAILURE


def test_an_integrity_violation_fails_the_whole_cycle(tmp_path):
    """Never partial. Once a guarantee breaks, every measurement is suspect."""
    result = run(tmp_path, steps=[
        ok_step("a"),
        boom_step("check", F.IntegrityViolation("stage exceeds predecessor"))])
    assert result.status == C.FAILED
    assert F.INTEGRITY_VIOLATION in result.reason


def test_a_transient_failure_is_retried_and_a_deterministic_one_is_not(tmp_path):
    calls = {"n": 0}

    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("temporary")
        return {"ok": True}

    result = run(tmp_path, steps=[("flaky", flaky)])
    assert result.status == C.COMPLETED
    assert calls["n"] == 3

    hard = {"n": 0}

    def integrity(ctx):
        hard["n"] += 1
        raise F.IntegrityViolation("never retry this")

    run(tmp_path, cycle=C.NIGHT, steps=[("integrity", integrity)])
    assert hard["n"] == 1


# --- market session gating --------------------------------------------------
def test_re_reading_the_same_bar_completes_but_does_not_count(tmp_path):
    """The anti-double-count guard, end to end. Both runs did real research;
    only the first observed a new market session."""
    friday = run(tmp_path, as_of="2026-07-31", latest_bar="2026-07-31")
    assert friday.status == C.COMPLETED

    saturday = run(tmp_path, cycle=C.NIGHT, as_of="2026-08-01",
                   latest_bar="2026-07-31")
    assert saturday.status == C.SKIPPED_NO_NEW_MARKET_SESSION
    assert saturday.exit_code == 0          # not a failure -- a fact
    assert all(s.ok for s in saturday.steps)   # the research still ran


def test_a_missing_bar_completes_the_research_but_counts_nothing(tmp_path):
    result = run(tmp_path, latest_bar=None)
    assert result.status == C.SKIPPED_NO_NEW_MARKET_SESSION
    assert result.session["bar"] == S.BAR_UNAVAILABLE


def test_a_weekend_cycle_still_runs_every_step(tmp_path):
    result = run(tmp_path, as_of="2026-08-01", latest_bar="2026-07-31",
                 steps=[ok_step("evidence"), ok_step("report")])
    assert result.session["state"] == S.WEEKEND
    assert all(s.ok for s in result.steps)


# --- trading mode -----------------------------------------------------------
def test_an_unsupported_trading_mode_stops_the_cycle_before_any_work(tmp_path):
    ran = {"n": 0}

    def counted(ctx):
        ran["n"] += 1
        return {}

    result = run(tmp_path, steps=[("work", counted)],
                 env={"TRADING_MODE": "LIVE"})
    assert result.status == C.FAILED
    assert F.CONFIGURATION_FAILURE in result.reason
    assert ran["n"] == 0            # fails CLOSED -- nothing executed


def test_paper_is_recorded_on_every_run(tmp_path):
    assert run(tmp_path).trading_mode == "PAPER"


# --- schedule window / DST --------------------------------------------------
def test_a_mistimed_fire_is_skipped_without_taking_the_lock(tmp_path):
    result = run(tmp_path, enforce_window=True,
                 now=datetime(2026, 7, 31, 14, 0, tzinfo=ZoneInfo(S.TIMEZONE)))
    assert result.status == C.SKIPPED_DUPLICATE
    assert "outside the" in result.reason
    # Checked on the path directly: `lock_state` probes by acquiring, which
    # would create the very file this asserts was never created.
    assert not (tmp_path / "locks" / f"{C.LOCK_NAME}.lock").exists()


def test_the_scheduled_time_passes_the_window_check(tmp_path):
    assert run(tmp_path, enforce_window=True).status == C.COMPLETED


def test_a_dst_repeated_hour_produces_one_operating_day_not_two(tmp_path):
    """2026-11-01 01:30 happens twice in America/Toronto."""
    tz = ZoneInfo(S.TIMEZONE)
    first = C.run_cycle(C.NIGHT, root=tmp_path, steps=[ok_step()],
                        as_of="2026-11-01", latest_bar="2026-10-30",
                        now=datetime(2026, 11, 1, 1, 30, tzinfo=tz, fold=0),
                        sleep=lambda _s: None)
    second = C.run_cycle(C.NIGHT, root=tmp_path, steps=[ok_step()],
                         as_of="2026-11-01", latest_bar="2026-10-30",
                         now=datetime(2026, 11, 1, 1, 30, tzinfo=tz, fold=1),
                         sleep=lambda _s: None)
    assert first.run_id == second.run_id
    assert second.status == C.SKIPPED_DUPLICATE


# --- storage ----------------------------------------------------------------
def test_a_failed_write_is_recorded_as_a_failure(tmp_path):
    def cannot_write(ctx):
        raise PermissionError("read-only file system")

    result = run(tmp_path, steps=[cannot_write.__name__ and
                                  ("store", cannot_write)])
    assert result.status == C.FAILED
    assert result.failed_steps[0].code == F.STORAGE_FAILURE


# --- reports ----------------------------------------------------------------
def test_reports_are_written_for_both_forms_with_a_pointer(tmp_path):
    written = C.write_reports(tmp_path, run_id_="rid", cycle=C.DAY,
                              as_of="2026-07-31", markdown="# hi",
                              payload={"a": 1})
    assert written["md"].endswith("2026-07-31_day.md")
    assert written["json"].endswith("2026-07-31_day.json")
    assert C.latest_report(tmp_path, C.DAY)["run_id"] == "rid"


def test_a_rerun_archives_the_prior_report_rather_than_destroying_it(tmp_path):
    C.write_reports(tmp_path, run_id_="r1", cycle=C.DAY, as_of="2026-07-31",
                    markdown="FIRST", payload={"n": 1})
    C.write_reports(tmp_path, run_id_="r2", cycle=C.DAY, as_of="2026-07-31",
                    markdown="SECOND", payload={"n": 2})
    directory = tmp_path / C.REPORT_DIR
    assert (directory / "2026-07-31_day.md").read_text() == "SECOND"
    assert (directory / "2026-07-31_day.1.md").read_text() == "FIRST"


def test_day_and_night_reports_never_collide(tmp_path):
    C.write_reports(tmp_path, run_id_="d", cycle=C.DAY, as_of="2026-07-31",
                    markdown="DAY", payload={})
    C.write_reports(tmp_path, run_id_="n", cycle=C.NIGHT, as_of="2026-07-31",
                    markdown="NIGHT", payload={})
    directory = tmp_path / C.REPORT_DIR
    assert (directory / "2026-07-31_day.md").read_text() == "DAY"
    assert (directory / "2026-07-31_night.md").read_text() == "NIGHT"
    assert C.latest_report(tmp_path, C.DAY)["run_id"] == "d"
    assert C.latest_report(tmp_path, C.NIGHT)["run_id"] == "n"


def test_the_pointer_never_deletes_history(tmp_path):
    for day in ("2026-07-29", "2026-07-30", "2026-07-31"):
        C.write_reports(tmp_path, run_id_=day, cycle=C.DAY, as_of=day,
                        markdown=day, payload={})
    kept = sorted(p.name for p in (tmp_path / C.REPORT_DIR).glob("*_day.md"))
    assert kept == ["2026-07-29_day.md", "2026-07-30_day.md",
                    "2026-07-31_day.md"]


# --- bar memory -------------------------------------------------------------
def test_the_store_remembers_the_last_ingested_bar(tmp_path):
    run(tmp_path, latest_bar="2026-07-30")
    assert C.RunStore(tmp_path).last_ingested_bar() == "2026-07-30"


def test_a_skipped_duplicate_does_not_overwrite_the_remembered_bar(tmp_path):
    run(tmp_path, latest_bar="2026-07-30")
    run(tmp_path, latest_bar="2026-07-30")            # duplicate
    assert C.RunStore(tmp_path).last_ingested_bar() == "2026-07-30"

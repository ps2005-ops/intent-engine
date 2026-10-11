"""A cycle that never ran must not be invisible.

The engine recorded what DID run and measured the steps of cycles that ran, so
a missed cycle left no trace in any surface. Measured on the real ledger when
this module was written: 20 of 145 due slots did no work, and every monitor
reported healthy throughout.
"""
import datetime as _dt

import pytest

from intent_engine.market import cycle as C
from intent_engine.market import schedule_audit as SA


def _row(as_of, which, status, reason="", catch_up=False, dry_run=False):
    return {"as_of": as_of, "cycle": which, "status": status,
            "reason": reason, "catch_up": catch_up, "dry_run": dry_run,
            "run_id": f"{as_of}:{which}:America/Toronto"}


class Store:
    """Stands in for `C.RunStore`, which is the only thing audit() reads."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


@pytest.fixture
def patched(monkeypatch):
    def install(rows):
        monkeypatch.setattr(C, "RunStore", lambda root: Store(rows))
    return install


NOON = _dt.datetime(2026, 10, 11, 12, 0, 0)


# ===========================================================================
# Legacy records: SKIPPED_DUPLICATE meant four different things
# ===========================================================================
def test_legacy_duplicate_with_a_window_reason_reads_as_an_early_fire():
    row = _row("2026-10-11", "night", "SKIPPED_DUPLICATE",
               "fired at 06:09 EDT, outside the 20:30 window — not running")
    assert SA.normalise_status(row) == C.SKIPPED_OUTSIDE_WINDOW


def test_legacy_duplicate_with_a_lock_reason_reads_as_contention():
    row = _row("2026-10-08", "day", "SKIPPED_DUPLICATE",
               "another cycle holds the lock")
    assert SA.normalise_status(row) == C.SKIPPED_LOCK_CONTENTION


def test_a_genuine_duplicate_still_reads_as_a_duplicate():
    row = _row("2026-07-31", "night", "SKIPPED_DUPLICATE",
               "2026-07-31:night:America/Toronto already completed")
    assert SA.normalise_status(row) == C.SKIPPED_DUPLICATE


def test_a_non_duplicate_status_is_returned_unchanged():
    assert SA.normalise_status(_row("x", "day", C.COMPLETED)) == C.COMPLETED


def test_normalising_does_not_mutate_the_stored_row():
    """History is read, never rewritten."""
    row = _row("2026-10-08", "day", "SKIPPED_DUPLICATE",
               "another cycle holds the lock")
    before = dict(row)
    SA.normalise_status(row)
    assert row == before


# ===========================================================================
# Expected slots
# ===========================================================================
def test_both_cycles_are_expected_every_day_including_weekends():
    slots = SA.expected_slots("2026-10-10", "2026-10-11")   # Sat + Sun
    assert slots == (("2026-10-10", "day"), ("2026-10-10", "night"),
                     ("2026-10-11", "day"), ("2026-10-11", "night"))


def test_a_single_day_range_is_two_slots():
    assert len(SA.expected_slots("2026-10-11", "2026-10-11")) == 2


# ===========================================================================
# Classification
# ===========================================================================
def test_a_slot_with_no_record_at_all_is_never_invoked(patched):
    patched([])
    got = SA.audit(root="x", start="2026-10-01", end="2026-10-01", now=NOON)
    assert got["by_outcome"][SA.MISSED_NEVER_INVOKED] == 2
    assert got["slots_lost"] == 2


def test_lock_contention_is_a_loss_not_a_skip(patched):
    patched([_row("2026-10-08", "day", "SKIPPED_DUPLICATE",
                  "another cycle holds the lock")])
    got = SA.audit(root="x", start="2026-10-08", end="2026-10-08", now=NOON)
    lost = {s["cycle"]: s["outcome"] for s in got["lost"]}
    assert lost["day"] == SA.MISSED_LOCK_CONTENTION


def test_no_new_market_session_is_work_done_not_a_loss(patched):
    """It ran every step and reported an honest absence. Weekends live here."""
    patched([_row("2026-10-10", "day", C.SKIPPED_NO_NEW_MARKET_SESSION)])
    got = SA.audit(root="x", start="2026-10-10", end="2026-10-10", now=NOON)
    outcomes = {s[0]: s[1] for s in [(x["cycle"], x["outcome"])
                                     for x in got["lost"]]}
    assert "day" not in outcomes
    assert got["by_outcome"][SA.RAN_NO_NEW_SESSION] == 1


def test_a_slot_that_ever_completed_is_not_a_loss(patched):
    """A later duplicate skip is duplicate protection working."""
    patched([_row("2026-10-09", "day", C.COMPLETED),
             _row("2026-10-09", "day", "SKIPPED_DUPLICATE",
                  "already completed")])
    got = SA.audit(root="x", start="2026-10-09", end="2026-10-09", now=NOON)
    assert got["by_outcome"][SA.RAN_COMPLETED] == 1
    assert all(s["cycle"] != "day" for s in got["lost"])


def test_a_dry_run_never_satisfies_a_slot(patched):
    """A rehearsal is not an operating cycle."""
    patched([_row("2026-10-09", "day", C.COMPLETED, dry_run=True)])
    got = SA.audit(root="x", start="2026-10-09", end="2026-10-09", now=NOON)
    assert got["by_outcome"][SA.MISSED_NEVER_INVOKED] == 2


# ===========================================================================
# NOT_YET_DUE is decided by the clock alone
# ===========================================================================
def test_a_future_slot_is_not_yet_due_even_with_an_early_fire_record(patched):
    """The bug this pins, found on live data.

    A wake-time coalesced launch leaves a SKIPPED_OUTSIDE_WINDOW record for a
    slot whose real moment is still hours away. Classifying on the record
    called tonight's 20:30 cycle a recoverable miss at breakfast and put it in
    the catch-up plan.
    """
    patched([_row("2026-10-11", "night", "SKIPPED_DUPLICATE",
                  "fired at 06:09 EDT, outside the 20:30 window")])
    got = SA.audit(root="x", start="2026-10-11", end="2026-10-11",
                   now=_dt.datetime(2026, 10, 11, 8, 0, 0))
    assert got["by_outcome"][SA.NOT_YET_DUE] == 1
    assert all(s["cycle"] != "night" for s in got["lost"])
    assert got["slots_due"] == 1


def test_the_same_slot_is_a_loss_once_its_moment_has_passed(patched):
    patched([_row("2026-10-11", "night", "SKIPPED_DUPLICATE",
                  "fired at 06:09 EDT, outside the 20:30 window")])
    got = SA.audit(root="x", start="2026-10-11", end="2026-10-11",
                   now=_dt.datetime(2026, 10, 11, 23, 0, 0))
    assert got["by_outcome"][SA.MISSED_EARLY_FIRE] == 1


def test_a_not_yet_due_slot_is_excluded_from_the_denominator(patched):
    patched([_row("2026-10-11", "day", C.COMPLETED)])
    got = SA.audit(root="x", start="2026-10-11", end="2026-10-11",
                   now=_dt.datetime(2026, 10, 11, 8, 0, 0))
    assert got["slots_expected"] == 2 and got["slots_due"] == 1
    assert got["reliability"] == 1.0


# ===========================================================================
# Recoverability
# ===========================================================================
def test_a_recent_loss_is_recoverable_and_an_old_one_is_not(patched):
    patched([])
    got = SA.audit(root="x", start="2026-10-01", end="2026-10-11", now=NOON)
    rec = {(s["as_of"], s["cycle"]) for s in got["recoverable"]}
    old = {(s["as_of"], s["cycle"]) for s in got["unrecoverable"]}
    assert ("2026-10-10", "day") in rec
    assert ("2026-10-01", "day") in old
    assert not (rec & old)


def test_the_lookback_boundary_is_inclusive(patched):
    patched([])
    got = SA.audit(root="x", start="2026-10-04", end="2026-10-11", now=NOON,
                   lookback_days=7)
    rec = {s["as_of"] for s in got["recoverable"]}
    assert "2026-10-04" in rec          # exactly 7 days old
    got2 = SA.audit(root="x", start="2026-10-03", end="2026-10-11", now=NOON,
                    lookback_days=7)
    old = {s["as_of"] for s in got2["unrecoverable"]}
    assert "2026-10-03" in old          # 8 days old


# ===========================================================================
# A catch-up must not be able to flatter the schedule
# ===========================================================================
def test_a_replay_raises_coverage_but_never_reliability(patched):
    patched([_row("2026-10-10", "day", C.COMPLETED, catch_up=True),
             _row("2026-10-10", "night", C.COMPLETED)])
    got = SA.audit(root="x", start="2026-10-10", end="2026-10-10", now=NOON)
    assert got["slots_worked"] == 2
    assert got["slots_worked_on_time"] == 1
    assert got["slots_worked_by_catch_up"] == 1
    assert got["coverage"] == 1.0
    assert got["reliability"] == 0.5


def test_an_all_replay_window_reports_zero_reliability(patched):
    """A chronically sleeping host must not reach 100% on its catch-ups."""
    patched([_row("2026-10-10", "day", C.COMPLETED, catch_up=True),
             _row("2026-10-10", "night", C.COMPLETED, catch_up=True)])
    got = SA.audit(root="x", start="2026-10-10", end="2026-10-10", now=NOON)
    assert got["coverage"] == 1.0
    assert got["reliability"] == 0.0


# ===========================================================================
# The catch-up driver
# ===========================================================================
def test_catch_up_replays_oldest_first_with_the_missed_slots_own_date(patched):
    """Identity comes from `as_of`; a replay dated today fixes nothing."""
    patched([])
    seen = []

    class Ok:
        status = C.COMPLETED

    def runner(which, as_of):
        seen.append((as_of, which))
        return Ok()

    SA.catch_up(root="x", runner=runner, now=NOON, limit=3)
    assert len(seen) == 3
    # oldest first, and `day` before `night` within a day
    assert seen == sorted(seen, key=lambda p: (p[0], C.CYCLES.index(p[1])))
    # the window starts lookback days before today, so the first replay is the
    # oldest still-recoverable slot -- NOT today's
    assert seen[0][0] == "2026-10-04"
    assert seen[0][1] == "day"


def test_catch_up_stops_at_the_first_slot_that_does_no_work(patched):
    patched([])
    calls = []

    class Blocked:
        status = C.SKIPPED_LOCK_CONTENTION

    def runner(which, as_of):
        calls.append((as_of, which))
        return Blocked()

    got = SA.catch_up(root="x", runner=runner, now=NOON)
    assert len(calls) == 1, "a contended replay must not queue more"
    assert got["attempted"] == 1
    assert len(got["refused"]) == 1
    assert got["replayed"] == ()


def test_catch_up_honours_the_limit(patched):
    patched([])

    class Ok:
        status = C.COMPLETED

    calls = []

    def runner(which, as_of):
        calls.append(as_of)
        return Ok()

    SA.catch_up(root="x", runner=runner, now=NOON, limit=2)
    assert len(calls) == 2


def test_catch_up_with_nothing_to_do_runs_nothing(patched):
    # The whole recoverable window must be populated: `catch_up` audits
    # `today - RECOVERY_LOOKBACK_DAYS .. today`, so a fixture covering only
    # the last two days leaves real gaps it would correctly offer to replay.
    rows = []
    day = _dt.date(2026, 10, 4)
    while day <= _dt.date(2026, 10, 11):
        for which in ("day", "night"):
            rows.append(_row(day.isoformat(), which, C.COMPLETED))
        day += _dt.timedelta(days=1)
    patched(rows)
    called = []
    got = SA.catch_up(root="x", runner=lambda c, a: called.append(a),
                      now=NOON)
    assert called == []
    assert got["attempted"] == 0


# ===========================================================================
# Rendering
# ===========================================================================
def test_render_says_so_when_nothing_was_lost(patched):
    patched([_row("2026-10-10", "day", C.COMPLETED),
             _row("2026-10-10", "night", C.COMPLETED)])
    got = SA.audit(root="x", start="2026-10-10", end="2026-10-10", now=NOON)
    body = "\n".join(SA.render(got))
    assert "No cycle has been lost" in body
    assert "|" not in body


def test_render_lists_every_lost_slot(patched):
    patched([])
    got = SA.audit(root="x", start="2026-10-10", end="2026-10-10", now=NOON)
    body = "\n".join(SA.render(got))
    assert "2026-10-10" in body and "MISSED_NEVER_INVOKED" in body


# ===========================================================================
# The alert must reach the operator, and must not need cycles to have run
# ===========================================================================
def _health(schedule):
    from intent_engine.market import learning_health as LH
    h = LH.LearningHealth(as_of="2026-10-11")
    h.schedule = schedule
    return h


def test_missed_cycles_alert_fires_with_no_observations_at_all():
    """The gate that made the engine quietest when it was most broken.

    Every other alert needs MIN_CYCLES_FOR_ALERT observations, and an
    observation only exists for a cycle that RAN. So the more cycles were
    lost, the fewer alerts could fire. The schedule alert is read from the
    run ledger, which exists either way, so it must sit above that gate.
    """
    from intent_engine.market import learning_health as LH
    got = LH.alerts([], _health({"slots_lost": 20, "reliability": 0.862,
                                 "recoverable": ({"as_of": "x"},)}))
    names = {a["alert"] for a in got}
    assert LH.CYCLES_MISSED in names
    assert LH.SCHEDULE_RELIABILITY_LOW in names


def test_a_recoverable_miss_is_critical_because_it_is_actionable():
    from intent_engine.market import learning_health as LH
    got = LH.alerts([], _health({"slots_lost": 3, "reliability": 1.0,
                                 "recoverable": ({"as_of": "x"},)}))
    missed = [a for a in got if a["alert"] == LH.CYCLES_MISSED][0]
    assert missed["severity"] == "CRITICAL"
    assert "recoverable" in missed["detail"]


def test_an_unrecoverable_only_miss_warns_rather_than_pages():
    from intent_engine.market import learning_health as LH
    got = LH.alerts([], _health({"slots_lost": 3, "reliability": 1.0,
                                 "recoverable": ()}))
    missed = [a for a in got if a["alert"] == LH.CYCLES_MISSED][0]
    assert missed["severity"] == "WARN"


def test_no_schedule_alert_when_nothing_was_lost():
    from intent_engine.market import learning_health as LH
    got = LH.alerts([], _health({"slots_lost": 0, "reliability": 1.0,
                                 "recoverable": ()}))
    names = {a["alert"] for a in got}
    assert LH.CYCLES_MISSED not in names
    assert LH.SCHEDULE_RELIABILITY_LOW not in names


def test_reliability_floor_is_read_from_the_constant():
    from intent_engine.market import learning_health as LH
    below = LH.alerts([], _health(
        {"slots_lost": 0, "reliability": LH.MIN_SCHEDULE_RELIABILITY - 0.01,
         "recoverable": ()}))
    at = LH.alerts([], _health(
        {"slots_lost": 0, "reliability": LH.MIN_SCHEDULE_RELIABILITY,
         "recoverable": ()}))
    assert LH.SCHEDULE_RELIABILITY_LOW in {a["alert"] for a in below}
    assert LH.SCHEDULE_RELIABILITY_LOW not in {a["alert"] for a in at}


def test_an_unmeasurable_reliability_does_not_fire():
    """No due slots yet is not a reliability failure."""
    from intent_engine.market import learning_health as LH
    got = LH.alerts([], _health({"slots_lost": 0, "reliability": None,
                                 "recoverable": ()}))
    assert LH.SCHEDULE_RELIABILITY_LOW not in {a["alert"] for a in got}


def test_assess_populates_schedule_before_alerts_consume_it():
    """Pins the ordering: a schedule computed after alerts() is inert."""
    import inspect
    from intent_engine.market import learning_health as LH
    src = inspect.getsource(LH.assess)
    code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    assert "health.schedule" in code
    assert code.index("health.schedule") < code.index("health.alerts = alerts(")


# ===========================================================================
# Catch-up must never cost the schedule a live cycle
# ===========================================================================
def test_minutes_to_next_slot_picks_the_nearer_of_the_two():
    assert SA.minutes_to_next_slot(_dt.datetime(2026, 10, 11, 6, 0)) == 30
    assert SA.minutes_to_next_slot(_dt.datetime(2026, 10, 11, 20, 0)) == 30
    assert SA.minutes_to_next_slot(_dt.datetime(2026, 10, 11, 12, 0)) == 510


def test_a_slot_already_passed_rolls_to_tomorrow():
    """06:31 is 13h59m from the 20:30 slot, not minus one minute."""
    got = SA.minutes_to_next_slot(_dt.datetime(2026, 10, 11, 6, 31))
    assert got == pytest.approx(839.0)


def test_catch_up_yields_rather_than_blocking_the_live_cycle(patched):
    """The repair must not recreate the defect.

    A replay holds the shared lock for about a cycle's length. Starting one at
    06:00 would lose the real 06:30 cycle to contention, which is precisely
    what catch-up exists to repair.
    """
    patched([])
    calls = []
    got = SA.catch_up(root="x", runner=lambda c, a: calls.append(a),
                      now=_dt.datetime(2026, 10, 11, 6, 0))
    assert calls == []
    assert got["attempted"] == 0
    assert got["yielded_to_schedule"]["reason"] == "YIELDED_TO_SCHEDULE"
    assert got["yielded_to_schedule"]["minutes_to_next_slot"] == 30.0


def test_catch_up_proceeds_when_the_next_slot_is_far_off(patched):
    patched([])

    class Ok:
        status = C.COMPLETED

    calls = []

    def runner(which, as_of):
        calls.append(as_of)
        return Ok()

    got = SA.catch_up(root="x", runner=runner, limit=1,
                      now=_dt.datetime(2026, 10, 11, 12, 0))
    assert len(calls) == 1
    assert got["yielded_to_schedule"] is None


def test_the_yield_window_is_longer_than_a_cycle_takes():
    """A window shorter than a cycle would not actually protect the slot."""
    assert SA.YIELD_TO_SCHEDULE_MINUTES >= 30


def test_catch_up_names_the_window_its_figures_describe(patched):
    """53.3% over eight days is not a regression from 86.2% over ten weeks."""
    patched([])
    got = SA.catch_up(root="x", runner=lambda c, a: None, limit=0,
                      now=_dt.datetime(2026, 10, 11, 12, 0))
    assert got["window_end"] == "2026-10-11"
    assert got["window_start"] == "2026-10-04"

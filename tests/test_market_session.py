"""Market session awareness.

The defect these exist to prevent is quiet: re-reading Friday's close on
Saturday and Sunday, counting it three times, and narrowing every confidence
interval on data that does not exist.
"""
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from intent_engine.market import session as S


# --- calendar ---------------------------------------------------------------
def test_a_weekday_is_a_trading_day():
    assert S.session_state(date(2026, 7, 30)) == S.TRADING_DAY   # Thursday


def test_weekend_is_distinguished_from_holiday():
    """Different facts. A report that says only "closed" cannot tell you the
    holiday calendar is wrong."""
    assert S.session_state(date(2026, 8, 1)) == S.WEEKEND        # Saturday
    assert S.session_state(date(2026, 8, 2)) == S.WEEKEND        # Sunday
    assert S.session_state(date(2026, 7, 3)) == S.HOLIDAY        # Independence


def test_early_close_is_its_own_state():
    assert S.session_state(date(2026, 11, 27)) == S.EARLY_CLOSE
    assert S.is_early_close(date(2026, 12, 24))


def test_an_uncovered_year_degrades_to_a_full_day_never_crashes():
    """Curated sets go stale. The failure must be a mildly wrong label, never
    an exception that takes an unattended cycle down."""
    assert S.session_state(date(2031, 6, 10)) == S.TRADING_DAY


# --- expected bar -----------------------------------------------------------
def test_on_a_trading_day_the_newest_completed_bar_is_the_previous_session():
    """A 06:30 pre-market cycle must not expect today's close: the market has
    not printed it."""
    assert S.expected_bar_date(date(2026, 7, 30)).isoformat() == "2026-07-29"


def test_on_a_weekend_the_expected_bar_is_fridays():
    assert S.expected_bar_date(date(2026, 8, 1)).isoformat() == "2026-07-31"
    assert S.expected_bar_date(date(2026, 8, 2)).isoformat() == "2026-07-31"


def test_after_a_holiday_the_expected_bar_skips_the_closure():
    #  2026-07-03 is the observed Independence Day holiday.
    assert S.expected_bar_date(date(2026, 7, 4)).isoformat() == "2026-07-02"


# --- bar state: THE anti-double-count guard ---------------------------------
def test_the_same_bar_seen_twice_is_not_a_new_observation():
    """The single highest-value assertion in this file."""
    state = S.bar_state(latest_bar="2026-07-31", day=date(2026, 8, 1),
                        previous_cycle_bar="2026-07-31")
    assert state == S.BAR_UNCHANGED


def test_a_weekend_cycle_does_not_count_fridays_close_as_a_market_session():
    friday = S.classify(date(2026, 7, 31), latest_bar="2026-07-31")
    assert friday.has_new_market_observation

    saturday = S.classify(date(2026, 8, 1), latest_bar="2026-07-31",
                          previous_cycle_bar="2026-07-31")
    sunday = S.classify(date(2026, 8, 2), latest_bar="2026-07-31",
                        previous_cycle_bar="2026-07-31")
    assert not saturday.has_new_market_observation
    assert not sunday.has_new_market_observation
    # ... and it says WHY, rather than merely returning False.
    assert "already ingested" in saturday.reason


def test_a_missing_bar_is_reported_missing_never_carried_forward():
    session = S.classify(date(2026, 7, 30), latest_bar=None)
    assert session.bar == S.BAR_UNAVAILABLE
    assert session.latest_bar is None
    assert not session.has_new_market_observation


def test_a_badly_lagging_bar_is_stale():
    state = S.bar_state(latest_bar="2026-07-01", day=date(2026, 7, 30),
                        hour=22)
    assert state == S.BAR_STALE


def test_a_bar_one_session_behind_early_in_the_day_is_late_not_stale():
    state = S.bar_state(latest_bar="2026-07-28", day=date(2026, 7, 30), hour=6)
    assert state == S.BAR_NOT_YET_PUBLISHED


def test_evidence_work_is_never_gated_on_the_market_being_open():
    """Weekend and holiday cycles are valid research cycles. Only STATISTICS
    are gated."""
    weekend = S.classify(date(2026, 8, 1), latest_bar="2026-07-31")
    assert not weekend.is_open_session
    assert weekend.state == S.WEEKEND
    # the session object never says "do not run" -- only "do not count"
    assert "evidence and research cycle" in weekend.reason


# --- timezone / DST ---------------------------------------------------------
def test_the_operating_timezone_is_explicit_not_the_machines():
    assert S.TIMEZONE == "America/Toronto"
    assert S.now_local().tzinfo is not None


def test_the_window_accepts_the_scheduled_time_and_anything_after_it_today():
    """At or after the scheduled time, same operating day."""
    tz = ZoneInfo(S.TIMEZONE)
    assert S.within_window(datetime(2026, 7, 31, 6, 30, tzinfo=tz), 6, 30)
    assert S.within_window(datetime(2026, 7, 31, 6, 35, tzinfo=tz), 6, 30)


def test_a_laptop_that_wakes_hours_late_still_runs_its_cycle():
    """THE reason the symmetric +/-90 minute window was wrong. launchd runs a
    missed calendar job on wake; a narrow window would reject it and silently
    skip the cycle every time the machine was closed at the scheduled minute.
    On a personal laptop that is most days."""
    tz = ZoneInfo(S.TIMEZONE)
    woke_late = datetime(2026, 7, 31, 23, 10, tzinfo=tz)
    assert S.within_window(woke_late, 20, 30)


def test_an_early_fire_is_still_rejected():
    """A wrong-timezone machine, or a clock hours behind, has not reached the
    scheduled time and must not run."""
    tz = ZoneInfo(S.TIMEZONE)
    assert not S.within_window(datetime(2026, 7, 31, 3, 30, tzinfo=tz), 20, 30)
    assert not S.within_window(datetime(2026, 7, 31, 5, 0, tzinfo=tz), 6, 30)


def test_the_next_operating_day_gets_its_own_identity_not_a_late_window():
    """A night fire at 00:30 is a NEW operating day whose 20:30 has not
    arrived, so it is rejected -- the date rolling over is the guard."""
    tz = ZoneInfo(S.TIMEZONE)
    assert not S.within_window(datetime(2026, 8, 1, 0, 30, tzinfo=tz), 20, 30)


def test_dst_spring_forward_still_accepts_the_scheduled_time():
    now = datetime(2026, 3, 8, 6, 30, tzinfo=ZoneInfo(S.TIMEZONE))
    assert S.within_window(now, 6, 30)


def test_dst_fall_back_repeated_hour_cannot_produce_two_operating_days():
    """1:30am occurs twice on 2026-11-01. Both instants belong to the SAME
    operating day, which is what makes the run identity a duplicate guard."""
    tz = ZoneInfo(S.TIMEZONE)
    first = datetime(2026, 11, 1, 1, 30, tzinfo=tz, fold=0)
    second = datetime(2026, 11, 1, 1, 30, tzinfo=tz, fold=1)
    assert first.date() == second.date()
    assert first.utcoffset() != second.utcoffset()   # genuinely two instants


def test_a_machine_in_another_timezone_does_not_shift_the_operating_day():
    """The whole reason `now_local` exists rather than `datetime.now()`."""
    utc = datetime(2026, 7, 31, 2, 0, tzinfo=ZoneInfo("UTC"))
    toronto = utc.astimezone(ZoneInfo(S.TIMEZONE))
    assert utc.date().isoformat() == "2026-07-31"
    assert toronto.date().isoformat() == "2026-07-30"   # different day


# --- the leakage cutoff: a MEASURED production bug, fixed Day 17 -------------
def test_replay_keeps_a_strict_cutoff():
    """The path where lookahead could flatter a result is untouched."""
    assert S.leakage_cutoff("2020-01-15", utc_today="2026-08-01") == "2020-01-15"
    assert S.leakage_cutoff("2026-07-30", utc_today="2026-08-01") == "2026-07-30"


def test_a_live_run_late_in_the_evening_does_not_discard_todays_evidence():
    """THE BUG. Between 20:00 and midnight in America/Toronto, UTC has rolled
    over. Ingestion stamps retrieval time in UTC; `as_of` is the operating day.
    A naive comparison dropped EVERY freshly-retrieved observation and reported
    it as `evidence: 0` -- a number indistinguishable from "nothing was
    published today". The 20:30 night cycle sits inside that window nightly."""
    today = S.today_local().isoformat()
    tomorrow_in_utc = (S.today_local() + timedelta(days=1)).isoformat()
    assert S.leakage_cutoff(today, utc_today=tomorrow_in_utc) == tomorrow_in_utc


def test_a_live_run_when_the_zones_agree_is_unchanged():
    today = S.today_local().isoformat()
    assert S.leakage_cutoff(today, utc_today=today) == today


def test_the_cutoff_never_moves_backwards():
    """max(), not a replacement: a UTC date BEHIND the operating day must not
    shrink the window."""
    today = S.today_local().isoformat()
    behind = (S.today_local() - timedelta(days=1)).isoformat()
    assert S.leakage_cutoff(today, utc_today=behind) == today


def test_the_cutoff_extends_by_at_most_one_day():
    """A guard that could extend arbitrarily would be a lookahead hole."""
    today = S.today_local()
    cutoff = S.leakage_cutoff(today.isoformat())
    assert cutoff <= (today + timedelta(days=1)).isoformat()

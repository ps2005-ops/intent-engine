"""Bars for the 2026-07-18 FRED '.'-guard amendment (user-approved
deterministic rule; see macro_data.py module docstring for the rule text).

Bar (a): weekend/holiday placeholders in business-daily series drop
silently, no gap recorded, series parses.
Bar (b): >=3 consecutive weekday '.'s (business-daily) and ANY '.' in a
non-daily series are genuine gaps: excluded, recorded in .gaps, warned.
Bar (c): strictness NOT weakened -- None, unparseable values, and
empty-after-drops still raise.
Bar (d): a long-lookback business-daily fixture with sprinkled holidays
(the exact shape that permanently failed before) now parses.
Bar (e): genuine gaps surface loudly in the rendered report section.

NOTE, recorded deliberately: tests/test_macro_data.py's original
`test_parse_response_raises_on_nan_observation` asserted that VIXCLS's
real New-Year's-Day '.' raises. Under the amendment that exact case is the
documented holiday-drop (rule 2) -- that test is updated in place, as a
user-approved bar change, not silently."""

from datetime import date, timedelta

import pytest

from intent_engine.core.macro_data import (
    BUSINESS_DAILY_SERIES,
    HOLIDAY_RUN_MAX,
    _parse_response,
)
from intent_engine.core.regime_report import render_data_gaps_section


def _raw(series_id_values):  # [(date, value_str)] -> FRED response shape
    return {
        "realtime_start": "2026-07-18",
        "observations": [
            {"date": d, "value": v, "realtime_start": "2026-07-18"} for d, v in series_id_values
        ],
    }


def _weekdays(start: date, n: int):
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


# --- bar (a): placeholders drop silently ------------------------------------

def test_weekend_placeholder_dropped_silently():
    assert "T10Y2Y" in BUSINESS_DAILY_SERIES
    rows = [("2026-07-17", "0.45"), ("2026-07-18", "."), ("2026-07-19", "."), ("2026-07-20", "0.46")]
    series = _parse_response(_raw(rows), "T10Y2Y")
    assert series.observations == [("2026-07-17", 0.45), ("2026-07-20", 0.46)]
    assert series.gaps == []


def test_single_weekday_holiday_dropped_silently():
    # 2026-01-01 is a Thursday -- New Year's Day, the real VIXCLS quirk shape.
    rows = [("2025-12-31", "17.2"), ("2026-01-01", "."), ("2026-01-02", "17.5")]
    series = _parse_response(_raw(rows), "VIXCLS")
    assert series.observations == [("2025-12-31", 17.2), ("2026-01-02", 17.5)]
    assert series.gaps == []


def test_two_consecutive_weekday_dots_still_holiday():
    days = _weekdays(date(2026, 3, 2), 4)  # Mon-Thu
    rows = [(days[0], "1.0"), (days[1], "."), (days[2], "."), (days[3], "1.1")]
    series = _parse_response(_raw(rows), "T10Y2Y")
    assert len(series.observations) == 2
    assert series.gaps == []
    assert HOLIDAY_RUN_MAX == 2


# --- bar (b): genuine gaps recorded + warned --------------------------------

def test_three_consecutive_weekday_dots_are_a_gap(capsys):
    days = _weekdays(date(2026, 3, 2), 5)
    rows = [(days[0], "1.0")] + [(d, ".") for d in days[1:4]] + [(days[4], "1.1")]
    series = _parse_response(_raw(rows), "T10Y2Y")
    assert series.observations == [(days[0], 1.0), (days[4], 1.1)]
    assert series.gaps == days[1:4]
    assert "GENUINE-GAP" in capsys.readouterr().out


def test_trailing_long_dot_run_is_a_gap():
    days = _weekdays(date(2026, 3, 2), 4)
    rows = [(days[0], "1.0")] + [(d, ".") for d in days[1:]]
    series = _parse_response(_raw(rows), "BAMLH0A0HYM2")
    assert series.gaps == days[1:]


def test_any_dot_in_monthly_series_is_a_gap(capsys):
    # The Oct-2025 shutdown shape: one month of '.' inside a monthly series.
    rows = [("2025-09-01", "4.3"), ("2025-10-01", "."), ("2025-11-01", "4.4")]
    series = _parse_response(_raw(rows), "UNRATE")
    assert series.observations == [("2025-09-01", 4.3), ("2025-11-01", 4.4)]
    assert series.gaps == ["2025-10-01"]
    assert "GENUINE-GAP" in capsys.readouterr().out


# --- bar (c): strictness not weakened ---------------------------------------

def test_none_value_still_raises():
    with pytest.raises(ValueError, match="None observation"):
        _parse_response(_raw([("2026-07-17", None)]), "T10Y2Y")


def test_unparseable_value_still_raises():
    with pytest.raises(ValueError, match="unparseable"):
        _parse_response(_raw([("2026-07-17", "not-a-number")]), "UNRATE")


def test_all_dots_series_still_raises():
    days = _weekdays(date(2026, 3, 2), 3)
    with pytest.raises(ValueError, match="no usable observations"):
        _parse_response(_raw([(d, ".") for d in days]), "T10Y2Y")


def test_empty_observations_still_raises():
    with pytest.raises(ValueError, match="no observations"):
        _parse_response({"observations": []}, "T10Y2Y")


# --- bar (d): the permanently-failing shape now parses ----------------------

def test_long_lookback_with_sprinkled_holidays_parses():
    start = date(2016, 7, 18)
    rows = []
    d = start
    holiday_countdown = 60  # a single-day '.' roughly every 60 business days
    while d <= date(2026, 7, 17):
        if d.weekday() < 5:
            holiday_countdown -= 1
            rows.append((d.isoformat(), "." if holiday_countdown == 0 else "3.50"))
            if holiday_countdown == 0:
                holiday_countdown = 60
        else:
            rows.append((d.isoformat(), "."))  # weekends as FRED renders them
        d += timedelta(days=1)
    series = _parse_response(_raw(rows), "BAMLH0A0HYM2")
    assert series.gaps == []
    assert len(series.observations) > 2500  # ~10y of business days minus holidays


# --- bar (e): loud surfacing in the report ----------------------------------

def test_render_data_gaps_section_loud_and_empty_cases():
    clean = _parse_response(_raw([("2026-07-17", "0.45")]), "T10Y2Y")
    assert render_data_gaps_section({"T10Y2Y": clean}) == ""

    gappy = _parse_response(
        _raw([("2025-09-01", "4.3"), ("2025-10-01", "."), ("2025-11-01", "4.4")]), "UNRATE")
    block = render_data_gaps_section({"UNRATE": gappy, "T10Y2Y": clean})
    assert "!! DATA GAPS DETECTED" in block
    assert "UNRATE: 1 missing observation(s) (2025-10-01)" in block
    assert "T10Y2Y" not in block.split("\n", 2)[2]  # clean series not listed

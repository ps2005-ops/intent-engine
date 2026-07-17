"""Tests for core/regime_engine.py (Task M2, market-engine-execution-plan.md).

Every arithmetic assertion below is hand-derived (shown in each test's
comments) against a small constructed fixture window -- per A-M3, nothing
here asserts a "did it call the crisis" outcome; every fixture is a plain
synthetic number sequence, not a real historical episode.
"""

import pytest

from intent_engine.core.macro_data import FredSeries
from intent_engine.core.regime_engine import (
    credit_spread_percentile,
    curve_inversion,
    drawdown_state,
    inflation_trend,
    regime_snapshot,
    unemployment_momentum,
)


def _monthly_dates(n: int, start_year: int = 2022, start_month: int = 1) -> list:
    dates = []
    y, m = start_year, start_month
    for _ in range(n):
        dates.append(f"{y:04d}-{m:02d}-01")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return dates


# --- curve_inversion ---------------------------------------------------------


def test_curve_inversion_true_when_latest_spread_negative():
    obs = [("2024-01-01", 0.5), ("2024-02-01", -0.30)]
    result = curve_inversion(obs)
    assert result.inverted is True
    assert result.depth == pytest.approx(0.30)
    assert result.provenance.series_id == "T10Y2Y"
    assert result.provenance.observation_date == "2024-02-01"


def test_curve_inversion_false_and_zero_depth_when_latest_spread_positive():
    obs = [("2024-01-01", -0.5), ("2024-02-01", 0.20)]
    result = curve_inversion(obs)
    assert result.inverted is False
    assert result.depth == 0.0


# --- credit_spread_percentile ------------------------------------------------


def test_credit_spread_percentile_hand_computed():
    """10 points, values 1..10 in some order, latest=7. Values <= 7:
    {1,2,3,4,5,6,7} = 7 of 10 -> 70.0%."""
    dates = _monthly_dates(10)
    values = [1, 2, 3, 4, 5, 6, 8, 9, 10, 7]  # latest (last date) = 7
    obs = list(zip(dates, [float(v) for v in values]))
    result = credit_spread_percentile(obs, lookback_years=10)
    assert result.percentile == pytest.approx(70.0)
    assert result.window_size == 10
    assert result.provenance.series_id == "BAMLH0A0HYM2"


def test_credit_spread_percentile_excludes_observations_outside_the_lookback_window():
    """An 11th, much-older point (12 years back) sits outside a 10-year
    lookback and must not affect the percentile."""
    dates = _monthly_dates(10)
    values = [1, 2, 3, 4, 5, 6, 8, 9, 10, 7]
    obs = [("2010-01-01", 0.5)] + list(zip(dates, [float(v) for v in values]))
    result = credit_spread_percentile(obs, lookback_years=10)
    assert result.window_size == 10  # the 2010 point excluded
    assert result.percentile == pytest.approx(70.0)


# --- inflation_trend ----------------------------------------------------------


def test_inflation_trend_rising_hand_computed():
    """24 months: first 12 flat at 100 (the YoY base year). Next 9 months at
    102 (YoY = 2.0% each, since base=100), last 3 months at 106 (YoY=6.0%
    each). 12m avg YoY = (9*2.0 + 3*6.0)/12 = 3.0%. 3m avg YoY (last 3) =
    6.0%. 6.0 > 3.0 -> rising."""
    dates = _monthly_dates(24)
    values = [100.0] * 12 + [102.0] * 9 + [106.0] * 3
    obs = list(zip(dates, values))
    result = inflation_trend(obs)
    assert result.trend == "rising"
    assert result.yoy_3m_avg == pytest.approx(6.0)
    assert result.yoy_12m_avg == pytest.approx(3.0)


def test_inflation_trend_falling_hand_computed():
    """Mirror of the rising case: 9 months at 106 (YoY=6.0%), last 3 at 102
    (YoY=2.0%). 12m avg = (9*6.0+3*2.0)/12 = 5.0%. 3m avg = 2.0%.
    2.0 < 5.0 -> falling."""
    dates = _monthly_dates(24)
    values = [100.0] * 12 + [106.0] * 9 + [102.0] * 3
    obs = list(zip(dates, values))
    result = inflation_trend(obs)
    assert result.trend == "falling"
    assert result.yoy_3m_avg == pytest.approx(2.0)
    assert result.yoy_12m_avg == pytest.approx(5.0)


def test_inflation_trend_stable_hand_computed():
    """All 12 months of year 2 at a constant 103 -> YoY = 3.0% every month,
    identical 3m and 12m averages -> stable."""
    dates = _monthly_dates(24)
    values = [100.0] * 12 + [103.0] * 12
    obs = list(zip(dates, values))
    result = inflation_trend(obs)
    assert result.trend == "stable"
    assert result.yoy_3m_avg == pytest.approx(3.0)
    assert result.yoy_12m_avg == pytest.approx(3.0)


def test_inflation_trend_raises_on_insufficient_history():
    obs = list(zip(_monthly_dates(23), [100.0] * 23))
    with pytest.raises(ValueError, match="at least 24"):
        inflation_trend(obs)


# --- unemployment_momentum -----------------------------------------------------


def test_unemployment_momentum_triggered_hand_computed():
    """15 months flat at 4.0, then a genuine recent rise: 4.2, 4.5, 5.0.
    Current 3m avg = (4.2+4.5+5.0)/3 = 4.5667. The 12 prior 3-month
    averages (ending at each of the 12 months before current) are all
    exactly 4.0 until the rise starts leaking in near the end, so their
    minimum is 4.0. delta = 4.5667 - 4.0 = 0.5667 >= 0.50 -> triggered."""
    dates = _monthly_dates(15)
    values = [4.0] * 12 + [4.2, 4.5, 5.0]
    obs = list(zip(dates, values))
    result = unemployment_momentum(obs)
    assert result.delta == pytest.approx(0.5667, abs=1e-3)
    assert result.triggered is True
    assert result.provenance.series_id == "UNRATE"


def test_unemployment_momentum_not_triggered_when_flat():
    dates = _monthly_dates(15)
    values = [4.0] * 15
    obs = list(zip(dates, values))
    result = unemployment_momentum(obs)
    assert result.delta == pytest.approx(0.0)
    assert result.triggered is False


def test_unemployment_momentum_raises_on_insufficient_history():
    obs = list(zip(_monthly_dates(14), [4.0] * 14))
    with pytest.raises(ValueError, match="at least 15"):
        unemployment_momentum(obs)


# --- drawdown_state -------------------------------------------------------------


def test_drawdown_state_hand_computed():
    """Running high = 110 (2nd point). Latest = 90.
    (90-110)/110*100 = -18.1818...%."""
    obs = [("2024-01-01", 100.0), ("2024-02-01", 110.0), ("2024-03-01", 105.0), ("2024-04-01", 90.0)]
    result = drawdown_state(obs, series_id="TEST_PRICE")
    assert result.pct_off_high == pytest.approx(-18.1818, abs=1e-3)
    assert result.provenance.series_id == "TEST_PRICE"


def test_drawdown_state_zero_at_a_new_high():
    obs = [("2024-01-01", 100.0), ("2024-02-01", 110.0)]
    result = drawdown_state(obs, series_id="TEST_PRICE")
    assert result.pct_off_high == pytest.approx(0.0)


# --- regime_snapshot: assembly, provenance, missing-series handling ------------


def _fred_series(series_id: str, dates: list, values: list) -> FredSeries:
    return FredSeries(series_id=series_id, realtime_date=dates[-1], observations=list(zip(dates, values)))


def test_regime_snapshot_fully_populated_with_provenance_when_all_series_present():
    cpi_dates = _monthly_dates(24, start_year=2022, start_month=1)
    cpi_values = [100.0] * 12 + [102.0] * 9 + [106.0] * 3
    unrate_dates = _monthly_dates(15, start_year=2022, start_month=10)
    unrate_values = [4.0] * 12 + [4.2, 4.5, 5.0]

    series_data = {
        "T10Y2Y": _fred_series("T10Y2Y", ["2023-11-01", "2023-12-01"], [0.5, -0.3]),
        "BAMLH0A0HYM2": _fred_series(
            "BAMLH0A0HYM2", _monthly_dates(10, start_year=2023, start_month=3),
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 9.0, 10.0, 7.0],
        ),
        "CPIAUCSL": _fred_series("CPIAUCSL", cpi_dates, cpi_values),
        "UNRATE": _fred_series("UNRATE", unrate_dates, unrate_values),
    }
    snapshot = regime_snapshot("2023-12-31", series_data)

    assert snapshot["snapshot_date"] == "2023-12-31"
    assert snapshot["curve_inversion"].inverted is True
    assert snapshot["credit_spread_percentile"].percentile == pytest.approx(70.0)
    assert snapshot["inflation_trend"].trend == "rising"
    assert snapshot["unemployment_momentum"].triggered is True
    # No price series supplied -- honestly unavailable, not fabricated.
    assert snapshot["drawdown_state"] == "unavailable"

    # Every non-unavailable field carries real provenance.
    for key in ("curve_inversion", "credit_spread_percentile", "inflation_trend", "unemployment_momentum"):
        assert snapshot[key].provenance.series_id
        assert snapshot[key].provenance.observation_date


def test_regime_snapshot_marks_missing_series_unavailable_not_a_silent_default():
    series_data = {
        "T10Y2Y": _fred_series("T10Y2Y", ["2023-12-01"], [-0.3]),
        # BAMLH0A0HYM2, CPIAUCSL, UNRATE all absent entirely.
    }
    snapshot = regime_snapshot("2023-12-31", series_data)
    assert snapshot["credit_spread_percentile"] == "unavailable"
    assert snapshot["inflation_trend"] == "unavailable"
    assert snapshot["unemployment_momentum"] == "unavailable"
    assert snapshot["drawdown_state"] == "unavailable"
    assert snapshot["curve_inversion"] != "unavailable"  # the one series that WAS present


def test_regime_snapshot_marks_insufficient_history_unavailable_not_a_crash():
    """CPIAUCSL present but with only 5 months -- not enough for a YoY
    calculation. Must resolve to "unavailable" for that field, and must
    NOT raise or abort the rest of the snapshot."""
    series_data = {
        "CPIAUCSL": _fred_series("CPIAUCSL", _monthly_dates(5), [100.0] * 5),
        "T10Y2Y": _fred_series("T10Y2Y", ["2023-12-01"], [0.4]),
    }
    snapshot = regime_snapshot("2023-12-31", series_data)
    assert snapshot["inflation_trend"] == "unavailable"
    assert snapshot["curve_inversion"] != "unavailable"


def test_regime_snapshot_never_uses_data_after_the_snapshot_date():
    """A future-dated observation must be excluded, not just the latest
    real one -- proves the filter is a real date cutoff, not an
    off-by-one/last-N-items slice."""
    dates = ["2023-10-01", "2023-11-01", "2023-12-01", "2024-06-01"]
    values = [0.4, 0.2, -0.3, 999.0]  # the 2024-06 point would flip everything if leaked in
    series_data = {"T10Y2Y": _fred_series("T10Y2Y", dates, values)}
    snapshot = regime_snapshot("2023-12-31", series_data)
    assert snapshot["curve_inversion"].provenance.observation_date == "2023-12-01"
    assert snapshot["curve_inversion"].depth == pytest.approx(0.3)


def test_regime_snapshot_price_series_populates_drawdown_when_supplied():
    series_data = {}
    price_obs = [("2023-10-01", 100.0), ("2023-11-01", 110.0), ("2023-12-01", 90.0)]
    snapshot = regime_snapshot("2023-12-31", series_data, price_series=("TEST_PRICE", price_obs))
    assert snapshot["drawdown_state"] != "unavailable"
    assert snapshot["drawdown_state"].pct_off_high == pytest.approx(-18.1818, abs=1e-3)
    assert snapshot["drawdown_state"].provenance.series_id == "TEST_PRICE"

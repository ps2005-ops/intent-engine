"""Expectations, surprises, and the wall that keeps them apart from answers."""
from __future__ import annotations

import pytest

from intent_engine.market import macro_expectation as ME
from intent_engine.market import macro_state as MS


def series(values, *, series_id="S", start_month=1, lag_days=30,
           kind=MS.INFLATION, area=MS.CA):
    """A monthly series whose figures publish `lag_days` after period end."""
    import datetime
    out = []
    for i, v in enumerate(values):
        month = start_month + i
        year, m = 2025 + (month - 1) // 12, (month - 1) % 12 + 1
        period = f"{year}-{m:02d}-01"
        pub = (datetime.date.fromisoformat(period)
               + datetime.timedelta(days=lag_days)).isoformat()
        out.append(MS.MacroObservation(
            state_kind=kind, area=area, series_id=series_id, label="x",
            value=float(v), unit="index", reference_period=period,
            published_at=pub, publication_basis=MS.ASSUMED_LAG,
            source="test"))
    return out


# --- the temporal wall ------------------------------------------------------

def test_a_forecast_cannot_read_the_period_it_forecasts():
    obs = series([1, 2, 3, 4])
    exp = ME.forecast(obs, series_id="S", target_period="2025-04-01",
                      made_at="2025-12-31", method=ME.RANDOM_WALK)
    # Every figure is public by then, but the target period is still excluded.
    assert exp.value == 3.0
    assert exp.observations_used == 3


def test_a_forecast_cannot_read_a_figure_published_after_it_was_made():
    obs = series([1, 2, 3, 4])
    exp = ME.forecast(obs, series_id="S", target_period="2025-04-01",
                      made_at="2025-03-15", method=ME.RANDOM_WALK)
    # February's figure publishes 2025-03-03; March's not until 2025-03-31.
    assert exp.observations_used == 2
    assert exp.value == 2.0


def test_scoring_a_forecast_against_an_already_public_figure_is_refused():
    """Otherwise every method is perfect and the comparison is noise."""
    obs = series([1, 2, 3, 4])
    exp = ME.forecast(obs, series_id="S", target_period="2025-03-01",
                      made_at="2025-12-31", method=ME.RANDOM_WALK)
    with pytest.raises(ME.Foresight) as err:
        ME.reconcile(exp, obs, as_of="2026-01-01")
    assert "lookup, not a prediction" in str(err.value)


def test_an_undated_expectation_is_refused():
    with pytest.raises(ME.ExpectationRejected):
        ME.Expectation(series_id="S", state_kind=MS.INFLATION, area=MS.CA,
                       target_period="2025-04-01", method=ME.RANDOM_WALK,
                       value=1.0, made_at="")


# --- the methods ------------------------------------------------------------

def test_random_walk_is_the_last_visible_value():
    obs = series([10, 11, 12])
    exp = ME.forecast(obs, series_id="S", target_period="2025-04-01",
                      made_at="2025-12-31", method=ME.RANDOM_WALK)
    assert exp.value == 12.0


def test_drift_adds_the_average_step():
    obs = series([10, 12, 14])
    exp = ME.forecast(obs, series_id="S", target_period="2025-04-01",
                      made_at="2025-12-31", method=ME.DRIFT)
    assert exp.value == 16.0


def test_seasonal_naive_needs_a_year_before_it_will_answer():
    obs = series([1] * 6)
    assert ME.forecast(obs, series_id="S", target_period="2025-07-01",
                       made_at="2026-12-31",
                       method=ME.SEASONAL_NAIVE) is None


def test_ar1_refuses_a_history_too_short_to_fit():
    obs = series([1, 2])
    assert ME.forecast(obs, series_id="S", target_period="2025-03-01",
                       made_at="2026-12-31", method=ME.AR1) is None


def test_a_missing_history_is_no_forecast_rather_than_a_zero():
    assert ME.forecast([], series_id="S", target_period="2025-04-01",
                       made_at="2025-12-31") is None


def test_an_unknown_method_is_refused():
    with pytest.raises(ME.ExpectationRejected):
        ME.forecast(series([1, 2, 3]), series_id="S",
                    target_period="2025-04-01", made_at="2025-12-31",
                    method="DEEP_LEARNING")


# --- surprise ---------------------------------------------------------------

def test_a_move_inside_one_sigma_is_not_a_surprise():
    obs = series([10, 10.1, 9.9, 10.2, 9.8, 10.0, 10.1])
    exp = ME.forecast(obs, series_id="S", target_period="2025-07-01",
                      made_at="2025-07-05", method=ME.RANDOM_WALK)
    got = ME.reconcile(exp, obs, as_of="2026-01-01")
    assert got.direction == ME.IN_LINE
    assert got.covered is True


def test_a_large_miss_is_reported_with_its_direction():
    obs = series([10, 10.1, 9.9, 10.2, 9.8, 10.0, 25.0])
    exp = ME.forecast(obs, series_id="S", target_period="2025-07-01",
                      made_at="2025-07-05", method=ME.RANDOM_WALK)
    got = ME.reconcile(exp, obs, as_of="2026-01-01")
    assert got.direction == ME.ABOVE
    assert got.surprise > 14
    assert got.covered is False


def test_an_unmeasurable_dispersion_is_not_a_small_surprise():
    """None must never be read as zero sigma."""
    obs = series([10, 12, 15])
    exp = ME.forecast(obs, series_id="S", target_period="2025-03-01",
                      made_at="2025-03-05", method=ME.RANDOM_WALK)
    # Two visible points leave one residual, which is not a dispersion.
    assert exp.observations_used == 2 and exp.sigma is None
    got = ME.reconcile(exp, obs, as_of="2026-01-01")
    assert got.standardised is None
    assert got.covered is None


def test_a_surprise_makes_no_claim_about_a_company():
    got = ME.summarise([])
    assert "not a claim about any company" in got["note"]


def test_reconciling_an_unpublished_period_yields_nothing():
    obs = series([1, 2, 3])
    exp = ME.forecast(obs, series_id="S", target_period="2025-09-01",
                      made_at="2025-08-01", method=ME.RANDOM_WALK)
    assert ME.reconcile(exp, obs, as_of="2025-08-15") is None


# --- benchmarking -----------------------------------------------------------

def test_skill_is_measured_against_the_random_walk():
    obs = series([float(i) for i in range(1, 25)])
    got = ME.backtest(obs, series_id="S", min_history=6)
    assert got["benchmark"] == ME.RANDOM_WALK
    walk = next(s for s in got["scores"] if s["method"] == ME.RANDOM_WALK)
    assert walk["skill_vs_benchmark"] == 1.0


def test_a_perfectly_trending_series_is_beaten_by_drift():
    obs = series([float(i) for i in range(1, 25)])
    got = ME.backtest(obs, series_id="S", min_history=6)
    assert got["best"] == ME.DRIFT
    assert got["best_beats_benchmark"] is True
    drift = next(s for s in got["scores"] if s["method"] == ME.DRIFT)
    assert drift["rmse"] < 1e-9


def test_a_short_series_is_reported_as_unscoreable_not_as_a_good_score():
    got = ME.backtest(series([1, 2, 3]), series_id="S", min_history=6)
    assert got["scored"] == 0
    assert got["scores"] == []
    assert "not enough history" in got["note"]


def test_a_method_that_loses_is_reported_rather_than_dropped():
    obs = series([float(i) for i in range(1, 25)])
    got = ME.backtest(obs, series_id="S", min_history=6)
    losers = [s for s in got["scores"] if not s["beats_benchmark"]]
    assert losers, "every method beating the benchmark would be the bug"
    assert all(s["skill_vs_benchmark"] >= 1.0 for s in losers)

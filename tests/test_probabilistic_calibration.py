"""Proper scoring, and the break proofs for the defect it replaced.

The central property under test is that a hit rate and a calibration are
different measurements. Every test here that looks redundant is pinning one
way the two were previously allowed to be confused.
"""
import math

import pytest

from intent_engine.market import probabilistic_calibration as PC


def _pairs(spec):
    """(probability, outcome) pairs from a compact [(p, n_ones, n_zeros)] spec."""
    out = []
    for p, ones, zeros in spec:
        out += [(p, 1)] * ones + [(p, 0)] * zeros
    return out


# ===========================================================================
# BREAK PROOF 10 — a hit rate must not be reportable as a calibration
# ===========================================================================
def test_perfect_hit_rate_can_have_negative_calibration_skill():
    """Right every time, and the probabilities still carry no information.

    Twenty-five forecasts of 0.55 that all come true: the hit rate is 1.00 and
    the model is badly calibrated -- it said 55% and observed 100%. If these
    two were ever the same number this assertion fails.
    """
    pairs = _pairs([(0.55, 25, 0)])
    result = PC.score(pairs)
    hit_rate = sum(o for _, o in pairs) / len(pairs)
    assert hit_rate == 1.0
    # Climatology here predicts 1.0 and is perfect, so the engine's 0.55
    # cannot beat it. A perfect hit rate buys no skill at all.
    assert result["beats_climatology"] is False
    assert result["brier"] > result["brier_climatology"]
    # Climatology is perfect here, so there is no finite skill ratio. The one
    # answer that must never appear is 0.0 -- that reads as "no worse than the
    # baseline" for a model that is strictly worse.
    assert (result["brier_skill_vs_climatology"]
            == PC.UNDEFINED_PERFECT_BASELINE)


def test_the_live_shaped_case_reproduces_negative_skill():
    """The measured live case: ~0.72 base rate, forecasts in a 0.09 band.

    Pinned because this is the exact shape that was being reported as a
    healthy 0.72 'calibration'.
    """
    pairs = _pairs([(0.586, 14, 5), (0.60, 2, 1), (0.62, 2, 0),
                    (0.58, 1, 3), (0.64, 1, 0), (0.65, 1, 0),
                    (0.63, 1, 0), (0.564, 1, 0)])
    result = PC.score(pairs)
    assert result["n"] == 32
    assert result["base_rate"] == pytest.approx(0.71875, abs=1e-4)
    assert result["beats_climatology"] is False
    assert result["brier_skill_vs_climatology"] < 0
    # And the reason the curve is useless is reported, not hidden.
    assert result["forecast_spread_sd"] < 0.05


# ===========================================================================
# The two refusals are different findings
# ===========================================================================
def test_too_few_outcomes_is_pre_calibration_not_a_number():
    result = PC.score(_pairs([(0.6, 3, 2)]))
    assert result["status"] == PC.PRE_CALIBRATION
    assert result["n"] == 5
    assert "brier" not in result
    assert str(PC.MIN_RESOLVED_FOR_PROPER_SCORE) in result["because"]


def test_near_constant_forecasts_report_no_discrimination_but_keep_the_score():
    """A one-bin reliability curve is not a curve -- but Brier is still valid."""
    result = PC.score(_pairs([(0.60, 15, 5), (0.601, 5, 0)]))
    assert result["status"] == PC.NO_DISCRIMINATION
    # The score survives the refusal; it is the diagram that does not.
    assert "brier" in result
    assert result["forecast_spread_sd"] < PC.MIN_FORECAST_SPREAD


def test_pre_calibration_and_no_discrimination_are_not_the_same_status():
    few = PC.score(_pairs([(0.6, 3, 2)]))
    flat = PC.score(_pairs([(0.60, 15, 5), (0.601, 5, 0)]))
    assert few["status"] != flat["status"]


# ===========================================================================
# A genuinely informative forecaster must be able to score positively,
# or the metric cannot distinguish a good model from a bad one.
# ===========================================================================
def test_a_discriminating_forecaster_beats_climatology():
    """Confident-and-correct at both ends: real skill, positive score."""
    pairs = _pairs([(0.95, 19, 1), (0.05, 1, 19)])
    result = PC.score(pairs)
    assert result["status"] == PC.MEASURED
    assert result["beats_climatology"] is True
    assert result["brier_skill_vs_climatology"] > 0.5
    assert result["log_loss_skill_vs_climatology"] > 0


def test_a_well_calibrated_forecast_has_small_reliability_gaps():
    pairs = _pairs([(0.9, 18, 2), (0.1, 2, 18)])
    result = PC.score(pairs)
    for row in result["reliability"]:
        assert abs(row["gap"]) < 0.05


# ===========================================================================
# Inputs are read, never invented
# ===========================================================================
def test_a_row_without_a_prior_is_skipped_not_defaulted():
    """Scoring a missing prior as 0.5 would invent a forecast."""
    rows = [
        {"prior": 0.6, "direction": "STRENGTHENED"},
        {"direction": "STRENGTHENED"},            # no prior
        {"prior": None, "direction": "WEAKENED"},  # null prior
        {"prior": 0.4, "direction": "WEAKENED"},
    ]
    assert PC.pairs_from_updates(rows) == ((0.6, 1), (0.4, 0))


def test_an_unreadable_direction_is_skipped():
    rows = [
        {"prior": 0.6, "direction": "STRENGTHENED"},
        {"prior": 0.6, "direction": "UNCHANGED"},
        {"prior": 0.6, "direction": None},
    ]
    assert PC.pairs_from_updates(rows) == ((0.6, 1),)


def test_direction_maps_to_the_outcome_both_ways():
    rows = [{"prior": 0.7, "direction": "STRENGTHENED"},
            {"prior": 0.3, "direction": "WEAKENED"}]
    assert PC.pairs_from_updates(rows) == ((0.7, 1), (0.3, 0))


# ===========================================================================
# Reliability bins
# ===========================================================================
def test_empty_bins_are_omitted_not_reported_as_zero():
    """An absent forecast range is not a wrong forecast."""
    result = PC.score(_pairs([(0.95, 10, 10), (0.05, 10, 10)]))
    lowers = [row["bin_lower"] for row in result["reliability"]]
    assert lowers == [0.0, 0.9]
    assert len(result["reliability"]) == 2


def test_probability_of_exactly_one_lands_in_the_last_bin():
    """Guards an off-by-one that would create an 11th bin."""
    result = PC.score(_pairs([(1.0, 20, 0)]))
    assert all(row["bin_upper"] <= 1.0 for row in result["reliability"])
    assert result["reliability"][-1]["bin_lower"] == 0.9


# ===========================================================================
# Rendering must not show what the status refused
# ===========================================================================
def test_render_of_pre_calibration_shows_no_curve_and_no_brier():
    lines = PC.render(PC.score(_pairs([(0.6, 3, 2)])))
    body = "\n".join(lines)
    assert PC.PRE_CALIBRATION in body
    assert "Brier" not in body
    assert "|" not in body


def test_render_of_no_discrimination_shows_the_score_but_no_table():
    lines = PC.render(PC.score(_pairs([(0.60, 15, 5), (0.601, 5, 0)])))
    body = "\n".join(lines)
    assert "Brier" in body
    assert PC.NO_DISCRIMINATION in body
    assert "| forecast |" not in body


def test_render_names_the_verdict_when_worse_than_climatology():
    lines = PC.render(PC.score(_pairs([(0.55, 25, 0)])))
    assert any("WORSE than climatology" in ln for ln in lines)


def test_render_shows_a_table_when_discrimination_is_real():
    lines = PC.render(PC.score(_pairs([(0.95, 19, 1), (0.05, 1, 19)])))
    assert any("| forecast |" in ln for ln in lines)


# ===========================================================================
# Arithmetic sanity
# ===========================================================================
def test_brier_matches_the_definition():
    pairs = _pairs([(0.8, 15, 5), (0.2, 2, 8)])
    expected = sum((p - o) ** 2 for p, o in pairs) / len(pairs)
    assert PC.score(pairs)["brier"] == pytest.approx(expected, abs=1e-4)


def test_log_loss_matches_the_definition():
    pairs = _pairs([(0.8, 15, 5), (0.2, 2, 8)])
    expected = -sum(o * math.log(p) + (1 - o) * math.log(1 - p)
                    for p, o in pairs) / len(pairs)
    assert PC.score(pairs)["log_loss"] == pytest.approx(expected, abs=1e-4)


def test_climatology_is_the_base_rate_and_scores_zero_skill_against_itself():
    pairs = _pairs([(0.75, 15, 5)])
    result = PC.score(pairs)
    assert result["base_rate"] == pytest.approx(0.75)
    # The engine forecast IS the base rate here, so skill is exactly zero.
    assert result["brier_skill_vs_climatology"] == pytest.approx(0.0, abs=1e-9)


def test_a_perfect_baseline_never_reports_zero_skill():
    """Division by zero must not be laundered into "as good as the baseline"."""
    result = PC.score(_pairs([(0.55, 25, 0)]))
    assert result["brier_skill_vs_climatology"] != 0.0
    assert result["log_loss_skill_vs_climatology"] != 0.0
    # And it must still render without raising on the sentinel.
    assert any("WORSE" in ln for ln in PC.render(result))

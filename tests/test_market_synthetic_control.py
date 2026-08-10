"""A-SCM-001. The estimator, its refusals, and the leakage it must not permit.

The negative controls are the point of this file. A synthetic control that
always fits is worthless, so most of what is asserted here is that the fit
REFUSES — and refuses for the specific reason, because "your pool is too small"
and "your pool is fine and does not resemble you" lead to different actions.
"""
from __future__ import annotations

import dataclasses

import pytest

from intent_engine.market import synthetic_control as SC


# --- a panel whose answer is known ---------------------------------------------
#
# `treated` IS 0.6*alpha + 0.4*beta in the pre-period, exactly, plus a known
# jump of 3.0 afterwards. Nothing about the method is being trusted: the right
# answer is arithmetic and the test checks the method recovers it.

ALPHA = [10, 11, 13, 12, 14, 16, 15, 17, 19, 18, 20, 22]
BETA = [5, 7, 6, 9, 8, 11, 10, 13, 12, 15, 14, 17]
#: A donor on a different scale moving the other way. It should end up with
#: essentially no weight, and a test asserts that rather than hoping for it.
GAMMA = [100, 98, 102, 97, 103, 96, 104, 95, 105, 94, 106, 93]

TREATMENT = 8
EFFECT = 3.0


def _panel(effect=EFFECT):
    treated = []
    for t in range(len(ALPHA)):
        base = 0.6 * ALPHA[t] + 0.4 * BETA[t]
        treated.append(base + (effect if t >= TREATMENT else 0.0))
    return treated, {"alpha": ALPHA, "beta": BETA, "gamma": GAMMA}


def _fit(**kwargs):
    treated, donors = _panel()
    return SC.fit(treated, donors, treatment_index=TREATMENT,
                  treated_unit="subject", as_of="2026-08-10", **kwargs)


# --- it recovers a known answer ------------------------------------------------

def test_recovers_the_weights_that_generated_the_series():
    got = _fit()
    assert got.fitted, got.refusal_detail
    weights = {w.unit: w.weight for w in got.weights}
    # Tight on purpose. The target IS a convex combination of two donors,
    # so the optimum is exact and a loose tolerance here would hide a
    # solver regression — the first version of this solver returned
    # 0.547/0.431 and passed at abs=0.05 nowhere near it.
    assert weights["alpha"] == pytest.approx(0.6, abs=1e-6)
    assert weights["beta"] == pytest.approx(0.4, abs=1e-6)
    assert weights["gamma"] == pytest.approx(0.0, abs=1e-9)


def test_recovers_the_known_effect():
    got = _fit()
    assert got.average_effect == pytest.approx(EFFECT, abs=1e-6)


def test_weights_are_a_simplex():
    got = _fit()
    assert all(w.weight >= 0 for w in got.weights)
    assert sum(w.weight for w in got.weights) == pytest.approx(1.0, abs=1e-9)


def test_pre_period_fit_is_near_exact_when_the_unit_is_in_the_donor_hull():
    got = _fit()
    assert got.pre_fit_ratio == pytest.approx(0.0, abs=1e-9)


def test_contributing_donors_excludes_the_ones_that_are_not_in_it():
    got = _fit()
    units = {w.unit for w in got.contributing_donors}
    assert "gamma" not in units
    assert {"alpha", "beta"} <= units


def test_the_solver_is_deterministic():
    """Persisted weights are later compared against a reload."""
    first = [w.weight for w in _fit().weights]
    second = [w.weight for w in _fit().weights]
    assert first == second


# --- the leakage control -------------------------------------------------------

def test_post_treatment_values_cannot_change_the_fit():
    """The single most important assertion in this file.

    A fit that saw the outcome it predicts scores BETTER on every downstream
    diagnostic, so no later check can catch it. If moving the post-treatment
    observations changes one weight, the objective is reading them.
    """
    treated, donors = _panel()
    baseline = SC.fit(treated, donors, treatment_index=TREATMENT)

    wrecked = list(treated)
    for t in range(TREATMENT, len(wrecked)):
        wrecked[t] = wrecked[t] * 1000 - 5000
    moved_donors = {name: list(series) for name, series in donors.items()}
    for series in moved_donors.values():
        for t in range(TREATMENT, len(series)):
            series[t] = -series[t] * 7
    after = SC.fit(wrecked, moved_donors, treatment_index=TREATMENT)

    assert [w.weight for w in baseline.weights] == \
        [w.weight for w in after.weights]
    assert baseline.pre_rmspe == after.pre_rmspe
    # ... and the estimate DID move, which is what makes the assertion above
    # meaningful rather than a comparison of two things that never differ.
    assert baseline.average_effect != after.average_effect


def test_the_objective_guard_rejects_a_treated_slice_that_runs_long():
    with pytest.raises(SC.LeakageError) as caught:
        SC.assert_pre_treatment_only(ALPHA[:TREATMENT + 1],
                                     [BETA[:TREATMENT]], TREATMENT)
    assert "predict" in str(caught.value)


def test_the_objective_guard_rejects_a_donor_slice_that_runs_long():
    with pytest.raises(SC.LeakageError) as caught:
        SC.assert_pre_treatment_only(ALPHA[:TREATMENT],
                                     [BETA[:TREATMENT],
                                      GAMMA[:TREATMENT + 2]], TREATMENT)
    assert "donor 1" in str(caught.value)


def test_the_objective_guard_passes_a_correctly_sliced_panel():
    """The negative control for the guard itself.

    Without this, a guard that raised on everything would satisfy both tests
    above and nothing would notice.
    """
    SC.assert_pre_treatment_only(ALPHA[:TREATMENT],
                                 [BETA[:TREATMENT], GAMMA[:TREATMENT]],
                                 TREATMENT)


# --- the refusals, each for its own reason -------------------------------------

def test_no_donors_is_refused_and_named():
    treated, _ = _panel()
    got = SC.fit(treated, {}, treatment_index=TREATMENT)
    assert got.status == SC.REFUSED_NO_DONORS
    assert not got.fitted


def test_a_ragged_panel_is_refused_rather_than_truncated():
    treated, donors = _panel()
    donors = dict(donors)
    donors["alpha"] = ALPHA[:-2]
    got = SC.fit(treated, donors, treatment_index=TREATMENT)
    assert got.status == SC.REFUSED_RAGGED_PANEL
    assert "alpha" in got.refusal_detail


def test_a_short_pre_period_is_refused_with_the_shortfall():
    treated, donors = _panel()
    got = SC.fit(treated, donors, treatment_index=3)
    assert got.status == SC.REFUSED_SHORT_PRE_PERIOD
    assert "3" in got.refusal_detail


def test_no_post_period_is_refused():
    treated, donors = _panel()
    got = SC.fit(treated, donors, treatment_index=len(treated))
    assert got.status == SC.REFUSED_SHORT_PRE_PERIOD


def test_a_pool_that_cannot_reproduce_the_unit_is_refused():
    """The donors are fine; they are simply not like this unit."""
    treated = [1, 9, 2, 8, 3, 7, 4, 6, 5, 5, 6, 4]
    donors = {"flat_a": [50] * 12, "flat_b": [51] * 12, "flat_c": [49] * 12}
    got = SC.fit(treated, donors, treatment_index=TREATMENT)
    assert got.status == SC.REFUSED_POOR_PRE_FIT
    # The weights are still reported: a reader has to be able to see WHICH
    # donors the failed fit reached for.
    assert got.weights
    assert got.pre_fit_ratio > SC.MAXIMUM_PRE_RMSPE_RATIO
    assert got.average_effect is None


def test_a_single_donor_carrying_the_weight_is_refused():
    treated, _ = _panel()
    donors = {"twin": [v - (EFFECT if i >= TREATMENT else 0)
                       for i, v in enumerate(treated)],
              "unrelated": GAMMA}
    got = SC.fit(treated, donors, treatment_index=TREATMENT)
    assert got.status == SC.REFUSED_DEGENERATE_WEIGHTS
    assert "twin" in got.refusal_detail
    assert got.concentration >= SC.CONCENTRATION_REFUSE


def test_a_flat_treated_unit_is_refused_rather_than_divided_by_zero():
    treated = [7.0] * 12
    donors = {"a": ALPHA, "b": BETA}
    got = SC.fit(treated, donors, treatment_index=TREATMENT)
    assert got.status == SC.REFUSED_NO_DONOR_SUPPORT


def test_a_refusal_reports_no_effect_rather_than_a_zero_effect():
    treated, _ = _panel()
    got = SC.fit(treated, {}, treatment_index=TREATMENT)
    assert got.average_effect is None
    assert got.effect_path == ()
    assert got.concentration is None


def test_the_estimator_returns_none_on_a_refusal():
    treated, _ = _panel()
    assert SC.estimator(treated, {}, treatment_index=TREATMENT) is None
    treated, donors = _panel()
    assert SC.estimator(treated, donors, treatment_index=TREATMENT) == \
        pytest.approx(EFFECT, abs=1e-6)


# --- three shapes: object, persisted row, transported object -------------------

def test_round_trips_through_its_persisted_row():
    got = _fit()
    row = got.as_dict()
    back = SC.load_estimate(row)
    assert back.status == got.status
    assert back.treated_unit == got.treated_unit
    assert back.treatment_index == got.treatment_index
    assert [(w.unit, w.weight) for w in back.weights] == \
        [(w.unit, round(w.weight, 6)) for w in got.weights]
    assert back.fit_id == got.fit_id


def test_the_persisted_row_carries_its_record_and_contract():
    row = _fit().as_dict()
    assert row["contract"] == SC.CONTRACT
    assert row["record"] == "causal_estimate"
    assert row["fitted"] is True
    assert isinstance(row["weights"], list)
    assert isinstance(row["weights"][0], dict)


def test_a_row_missing_optional_fields_reloads_without_inventing_them():
    row = _fit().as_dict()
    for key in ("pre_rmspe", "treated_pre_variation", "pre_fit_ratio"):
        row.pop(key)
    back = SC.load_estimate(row)
    assert back.pre_rmspe is None
    assert back.pre_fit_ratio is None


def test_an_empty_weight_list_reloads_as_no_fit_not_as_a_fit():
    row = _fit().as_dict()
    row["weights"] = []
    back = SC.load_estimate(row)
    assert back.weights == ()
    assert back.concentration is None


def test_an_explicit_null_is_not_a_zero():
    row = _fit().as_dict()
    row["average_effect"] = None
    row["effect_path"] = None
    back = SC.load_estimate(row)
    assert back.average_effect is None
    assert back.effect_path == ()


def test_a_row_from_a_later_producer_version_is_ignored_not_fatal():
    """A field this version does not know must not break the reader."""
    row = _fit().as_dict()
    row["placebo_rank"] = 3
    row["contract"] = "synthetic_control.v99"
    back = SC.load_estimate(row)
    assert back.fitted


# --- telemetry that can report a negative --------------------------------------

def test_summary_names_every_refusal_reason_even_at_zero():
    treated, donors = _panel()
    fits = [SC.fit(treated, donors, treatment_index=TREATMENT),
            SC.fit(treated, {}, treatment_index=TREATMENT)]
    got = SC.summarise(fits)
    assert got["attempted"] == 2
    assert got["fitted"] == 1
    assert got["refused"] == 1
    for reason in SC.REFUSALS:
        assert reason in got["by_status"]
    assert got["by_status"][SC.REFUSED_POOR_PRE_FIT] == 0
    assert got["by_status"][SC.REFUSED_NO_DONORS] == 1


def test_summary_of_nothing_is_zero_of_every_known_reason():
    got = SC.summarise([])
    assert got["attempted"] == 0
    assert set(got["by_status"]) == {SC.FITTED} | set(SC.REFUSALS)
    assert all(v == 0 for v in got["by_status"].values())

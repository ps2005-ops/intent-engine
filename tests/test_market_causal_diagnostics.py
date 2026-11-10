"""A-DIAG-001. The ten attacks, and the proof each one can also pass.

Every failing case here is paired with a passing one. A diagnostic that fails
everything satisfies an adversarial test suite perfectly and is worth nothing,
which is the specific way a metric ends up unable to report a negative.
"""
from __future__ import annotations

import pytest

from intent_engine.market import causal_diagnostics as CD
from intent_engine.market import economic_method as EM
from intent_engine.market import synthetic_control as SC


TREATMENT = 10
LENGTH = 20


def _wave(seed, n=LENGTH, level=20.0, amplitude=3.0):
    """A deterministic, non-monotonic series.

    Non-monotonic on purpose: a panel of straight lines makes every donor a
    perfect substitute for every other and every diagnostic vacuous.
    """
    out = []
    value = level + seed
    for t in range(n):
        value += amplitude * ((seed * 7 + t * 13) % 5 - 2) / 2.0
        out.append(round(value, 4))
    return out


#: THREE LATENT FACTORS, AND WHY THE POOL IS BUILT FROM THEM.
#:
#: The first version of this fixture generated eight independent waves. Every
#: donor was then outside the convex hull of the other seven, so every in-space
#: placebo was refused for poor pre-fit and the diagnostic returned UNTESTED
#: with nothing to rank — a placebo test that could never run.
#:
#: A donor pool worth having is one whose members are driven by shared
#: structure, which is also the only situation in which a synthetic control is
#: the right method. So the donors are convex combinations of three factors:
#: any one of them is reproducible from the others, placebo fits succeed, and
#: the distribution the treated unit is ranked against actually exists.
_FACTORS = [_wave(1, amplitude=3.0), _wave(4, amplitude=2.0),
            _wave(9, amplitude=4.0)]

#: How much of each donor is its own, rather than the shared factors. This
#: number was calibrated by measurement, not chosen: at zero, every donor is
#: exactly reproducible from the others, the placebo pre-period error is
#: arithmetic noise, `effect_ratio` correctly returns None, and every placebo
#: is EXCLUDED — a distribution of nothing. Too large and the donors stop
#: resembling each other and the fits are refused instead. 0.05 leaves zero
#: exclusions on a pool of sixteen.
IDIOSYNCRATIC = 0.05

#: Sixteen donors, because the placebo threshold of 10% cannot be reached with
#: fewer than nine FITTED placebos — a rank of 1 out of 8 is 12.5%.
PLACEBO_POOL = 16


def _pool(count=PLACEBO_POOL):
    """A pool driven by three shared factors plus a little of its own.

    Loadings cluster near the centroid of the factor simplex so that each
    donor lies INSIDE the hull of the others: a donor at a vertex cannot be
    reproduced by the rest, its placebo fit is refused, and it leaves the
    distribution silently. The first version of this fixture generated eight
    independent waves and every single placebo was refused.
    """
    out = {}
    for i in range(count):
        a = 1 / 3 + 0.10 * ((i * 5 % 7) - 3) / 3
        b = 1 / 3 + 0.10 * ((i * 3 % 5) - 2) / 2
        c = 1.0 - a - b
        own = _wave(i + 41, amplitude=1.0)
        out[f"donor_{i}"] = [
            round(a * _FACTORS[0][t] + b * _FACTORS[1][t]
                  + c * _FACTORS[2][t] + IDIOSYNCRATIC * own[t], 6)
            for t in range(LENGTH)]
    return out


def _treated_from(donors, weights, *, effect=0.0, treatment=TREATMENT):
    names = sorted(donors)
    out = []
    for t in range(LENGTH):
        value = sum(weights.get(n, 0.0) * donors[n][t] for n in names)
        out.append(value + (effect if t >= treatment else 0.0))
    return out


def _panel(effect=0.0, count=PLACEBO_POOL):
    donors = _pool(count)
    weights = {"donor_0": 0.5, "donor_1": 0.3, "donor_2": 0.2}
    return _treated_from(donors, weights, effect=effect), donors


#: A treated unit that is EXACTLY a convex combination of its donors fits with
#: zero pre-period error, which makes the post-over-pre ratio undefined and
#: every placebo test vacuous. No real unit is exactly in the hull of its
#: comparisons, so the fixtures that exercise the placebo machinery add a
#: small deterministic wobble instead. 0.1 against a pre-period variation of
#: 0.64 leaves the fit comfortably inside MAXIMUM_PRE_RMSPE_RATIO at 0.155.
JITTER = 0.1


def _jitter(series, size=JITTER):
    return [v + (size if i % 2 else -size) for i, v in enumerate(series)]


def _fit(effect=0.0, count=PLACEBO_POOL):
    treated, donors = _panel(effect=effect, count=count)
    return SC.fit(treated, donors, treatment_index=TREATMENT,
                  treated_unit="subject", as_of="2026-08-10"), treated, donors


# --- the statistic -------------------------------------------------------------

def test_effect_ratio_is_none_when_the_pre_period_is_perfect():
    """Undefined, not infinite. Infinity would rank first automatically."""
    fit, _, _ = _fit(effect=5.0)
    assert fit.fitted
    assert CD.effect_ratio(fit) is None


def test_effect_ratio_is_a_number_when_the_pre_fit_is_imperfect():
    treated, donors = _panel(effect=5.0)
    treated = _jitter(treated)
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    assert fit.fitted
    ratio = CD.effect_ratio(fit)
    assert ratio is not None and ratio > 1.0


# --- attack 1 and 2: placebo in space, both directions -------------------------

def test_a_real_effect_ranks_at_the_top_of_the_placebo_distribution():
    treated, donors = _panel(effect=25.0)
    treated = _jitter(treated)
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    got = CD.in_space_placebo(treated, donors, treatment_index=TREATMENT,
                              fit=fit)
    assert got.result == EM.PASSED, got.evidence
    assert got.statistic <= CD.PLACEBO_RANK_SHARE


def test_no_effect_at_all_does_not_survive_the_placebo_distribution():
    """The negative control. A gap of zero must not rank as a finding."""
    treated, donors = _panel(effect=0.0)
    treated = _jitter(treated)
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    got = CD.in_space_placebo(treated, donors, treatment_index=TREATMENT,
                              fit=fit)
    assert got.result == EM.FAILED, got.evidence


def test_too_few_donors_is_untested_not_passed():
    donors = _pool(2)
    treated = _jitter(_treated_from(donors, {"donor_0": 0.6, "donor_1": 0.4},
                                    effect=25.0))
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    got = CD.in_space_placebo(treated, donors, treatment_index=TREATMENT,
                              fit=fit)
    assert got.result == EM.UNTESTED
    assert "distribution" in got.evidence


def test_placebo_units_that_could_not_be_fitted_are_counted():
    treated, donors = _panel(effect=25.0)
    treated = _jitter(treated)
    donors = dict(donors)
    donors["flat"] = [42.0] * LENGTH   # refused: no donor support
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    got = CD.in_space_placebo(treated, donors, treatment_index=TREATMENT,
                              fit=fit)
    assert got.excluded >= 1


# --- attack 3: placebo in time -------------------------------------------------

def test_a_sham_date_in_the_quiet_period_produces_little_effect():
    treated, donors = _panel(effect=25.0)
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    got = CD.in_time_placebo(treated, donors, treatment_index=TREATMENT,
                             fit=fit)
    assert got.result in (EM.PASSED, EM.UNTESTED), got.evidence
    if got.result == EM.PASSED:
        assert got.statistic < CD.SHAM_EFFECT_RATIO


def test_a_pre_period_that_already_diverged_fails_the_in_time_placebo():
    """A unit drifting away before treatment shows the same gap at a sham date."""
    treated, donors = _panel(effect=0.0)
    treated = [v + 0.9 * t for t, v in enumerate(treated)]
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    if not fit.fitted:
        pytest.skip("the drift is large enough that the fit refuses first, "
                    "which is a stronger answer than the diagnostic's")
    got = CD.in_time_placebo(treated, donors, treatment_index=TREATMENT,
                             fit=fit)
    assert got.result == EM.FAILED, got.evidence


def test_a_pre_period_too_short_to_split_is_untested():
    treated, donors = _panel(effect=5.0)
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    got = CD.in_time_placebo(treated, donors, treatment_index=9, fit=fit)
    assert got.result == EM.UNTESTED
    assert "floor" in got.evidence


# --- attack 4: pre-trend -------------------------------------------------------

def test_a_clean_pre_period_passes_the_pre_trend_test():
    fit, treated, donors = _fit(effect=5.0)
    got = CD.pre_trend(fit)
    assert got.result in (EM.PASSED, EM.UNTESTED), got.evidence


def test_residuals_marching_in_one_direction_fail_the_pre_trend_test():
    treated, donors = _panel(effect=0.0)
    # A gentle ramp: small enough that the fit still succeeds, systematic
    # enough that the errors all point the same way and grow.
    treated = [v + 0.10 * t for t, v in enumerate(treated)]
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    if not fit.fitted:
        pytest.skip("the fit refused before the diagnostic could run")
    got = CD.pre_trend(fit)
    assert got.result == EM.FAILED, got.evidence
    assert abs(got.statistic) > CD.PRE_TREND_CORRELATION


# --- attack 5: weight concentration --------------------------------------------

def test_a_spread_synthetic_unit_passes_the_concentration_test():
    fit, _, _ = _fit(effect=5.0)
    got = CD.weight_concentration(fit)
    assert got.result == EM.PASSED, got.evidence


def test_one_donor_carrying_most_of_the_weight_fails_it():
    donors = _pool()
    treated = _treated_from(donors, {"donor_0": 0.88, "donor_1": 0.12})
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    if not fit.fitted:
        pytest.skip("refused at the harder CONCENTRATION_REFUSE bar first")
    got = CD.weight_concentration(fit)
    assert got.result == EM.FAILED
    assert "donor_0" in got.evidence


# --- attack 6: a common shock --------------------------------------------------

def test_a_panel_wide_shock_is_reported():
    donors = _pool()
    shocked = {}
    for name, series in donors.items():
        shocked[name] = [v + (12.0 if t >= TREATMENT else 0.0)
                         for t, v in enumerate(series)]
    got = CD.common_shock(shocked, treatment_index=TREATMENT)
    assert got.result == EM.FAILED, got.evidence


def test_donors_moving_independently_pass():
    """The negative control for the shock test."""
    donors = {f"d{i}": [10.0 + (1 if (i + t) % 2 else -1) * t
                        for t in range(LENGTH)] for i in range(6)}
    got = CD.common_shock(donors, treatment_index=TREATMENT)
    assert got.result == EM.PASSED, got.evidence


# --- attack 7: leakage, and attacks 8-10, which cannot be tested here ----------

def test_a_post_treatment_observation_cannot_reach_the_objective():
    """Attack 7. Enforced upstream and asserted here as a property."""
    with pytest.raises(SC.LeakageError):
        SC.assert_pre_treatment_only([1.0] * (TREATMENT + 1),
                                     [[1.0] * TREATMENT], TREATMENT)


def test_the_untestable_assumptions_are_untested_not_passed():
    """Attacks 8, 9 and 10: chosen-after-the-fact dates and revised outcomes.

    No arrangement of the numbers can settle these. What matters is that they
    are present and UNTESTED rather than absent, because an assumption nobody
    listed reads as one that holds.
    """
    fit, treated, donors = _fit(effect=25.0)
    got = CD.stress(fit, treated, donors, as_of="2026-08-10")
    untested = [c for c in got["checks"]
                if c["result"] == EM.UNTESTED and c["severity"] == EM.CRITICAL]
    assumptions = {c["assumption"] for c in untested}
    assert "the treatment date was chosen before the effect was seen" in \
        assumptions
    assert "the outcome was not revised after the analysis date" in assumptions
    assert got["untestable_here"] == 2


def test_an_untested_critical_assumption_forbids_a_causal_reading():
    """The uncomfortable, correct consequence.

    A synthetic control cannot reach USEFUL on statistics alone, because two
    of its critical assumptions are facts about the study rather than the
    series. This is the ceiling working, not a bug to be tuned away.
    """
    fit, treated, donors = _fit(effect=25.0)
    got = CD.stress(fit, treated, donors)
    assert got["causal_reading_allowed"] is False
    assert got["standing"] in (EM.BOUNDED, EM.REFUSED)


# --- the verdict comes from interpret, not from here ---------------------------

def test_a_refused_fit_is_insufficient_for_diagnosis_not_refuted():
    treated, _ = _panel(effect=5.0)
    fit = SC.fit(treated, {}, treatment_index=TREATMENT)
    got = CD.stress(fit, treated, {})
    assert got["status"] == CD.INSUFFICIENT_FOR_DIAGNOSIS
    assert got["diagnostics"] == []
    assert got["causal_reading_allowed"] is False


def test_the_standing_is_economic_methods_and_not_a_second_vocabulary():
    fit, treated, donors = _fit(effect=25.0)
    got = CD.stress(fit, treated, donors)
    assert got["standing"] in EM.STANDINGS


def test_every_check_is_a_method_assumption_check_row():
    fit, treated, donors = _fit(effect=25.0)
    got = CD.stress(fit, treated, donors)
    for row in got["checks"]:
        assert row["record"] == "method_assumption_check"
        assert row["result"] in EM.ASSUMPTION_RESULTS
        assert row["severity"] in EM.SEVERITIES
        assert row["evidence"].strip()


def test_a_failed_critical_diagnostic_refuses_the_reading():
    """A pre-trend failure is CRITICAL and must take the standing to REFUSED."""
    treated, donors = _panel(effect=0.0)
    treated = [v + 0.10 * t for t, v in enumerate(treated)]
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    if not fit.fitted:
        pytest.skip("the fit refused before the diagnostic could run")
    got = CD.stress(fit, treated, donors)
    assert got["standing"] == EM.REFUSED
    assert "critical assumption failed" in got["why"]


# --- coverage is a number ------------------------------------------------------

def test_every_declared_assumption_is_either_tested_or_named_untestable():
    got = CD.assumption_coverage()
    assert got["uncovered"] == []
    assert got["orphaned_mappings"] == []
    assert got["declared"] == \
        got["tested_by_a_diagnostic"] + got["untestable_here"]


def test_coverage_notices_an_assumption_with_no_branch(monkeypatch):
    """The negative control for the coverage report itself."""
    method = EM.METHODS[SC.SYNTHETIC_CONTROL]
    widened = dataclasses_replace(method, assumptions=method.assumptions
                                  + ("nobody has written a check for this",))
    monkeypatch.setitem(EM.METHODS, SC.SYNTHETIC_CONTROL, widened)
    got = CD.assumption_coverage()
    assert got["uncovered"] == ["nobody has written a check for this"]


def dataclasses_replace(obj, **kwargs):
    import dataclasses

    return dataclasses.replace(obj, **kwargs)


# --- telemetry that can report a negative --------------------------------------

def test_summary_names_every_standing_even_at_zero():
    fit, treated, donors = _fit(effect=25.0)
    results = [CD.stress(fit, treated, donors),
               CD.stress(SC.fit(treated, {}, treatment_index=TREATMENT),
                         treated, {})]
    got = CD.summarise(results)
    assert got["diagnosed"] == 2
    for standing in EM.STANDINGS:
        assert standing in got["by_standing"]
    assert got["by_standing"][CD.INSUFFICIENT_FOR_DIAGNOSIS] == 1
    assert got["by_standing"][EM.USEFUL] == 0


def test_summary_of_nothing_is_zero_of_every_standing():
    got = CD.summarise([])
    assert got["diagnosed"] == 0
    assert all(v == 0 for v in got["by_standing"].values())


def test_a_pool_too_small_to_reach_the_threshold_is_untested_not_failed():
    """The branch a break proof found untested.

    With n fitted placebos the most extreme achievable rank is 1/(n+1), so a
    pool of four cannot reach a 10% threshold for ANY unit — including one
    with a thirty-fold effect. Reporting FAILED there reads as "the effect is
    not unusual" when what happened is that the panel cannot demonstrate it
    either way. This branch shipped in the same commit that added it and no
    test exercised it; disabling it left the suite green.
    """
    donors = _pool(5)
    treated = _jitter(_treated_from(
        donors, {"donor_0": 0.5, "donor_1": 0.3, "donor_2": 0.2},
        effect=40.0))
    fit = SC.fit(treated, donors, treatment_index=TREATMENT)
    assert fit.fitted, fit.refusal_detail
    got = CD.in_space_placebo(treated, donors, treatment_index=TREATMENT,
                              fit=fit)
    assert got.result == EM.UNTESTED, got.evidence
    assert "cannot demonstrate the effect either way" in got.evidence
    # ... and the effect really is large, which is what makes UNTESTED the
    # interesting answer rather than a technicality.
    assert abs(fit.average_effect) > 10

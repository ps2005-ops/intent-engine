"""A registry entry is not an implementation, and in-sample is not a score."""
from __future__ import annotations

import pytest

from intent_engine.market import economic_method as EM


# --- the registry refuses rather than substituting ---------------------------

def test_a_declared_but_unimplemented_method_is_refused_not_downgraded():
    with pytest.raises(EM.MethodRefused) as err:
        EM.require(EM.DIFFERENCE_IN_DIFFERENCES, EM.EFFECT_OF_POLICY, 100)
    assert "misreport what was run" in str(err.value)


def test_a_method_asked_the_wrong_question_is_refused():
    with pytest.raises(EM.MethodRefused) as err:
        EM.require(EM.AR1, EM.EFFECT_OF_POLICY, 100)
    assert "answers" in str(err.value)


def test_a_method_below_its_minimum_sample_is_refused():
    with pytest.raises(EM.MethodRefused) as err:
        EM.require(EM.AR1, EM.FORECAST_LEVEL, 3)
    assert "needs 8 observations, got 3" in str(err.value)


def test_every_declared_method_states_its_assumptions_and_failures():
    for name, method in EM.METHODS.items():
        if method.is_baseline:
            continue
        assert method.assumptions, f"{name} declares no assumptions"
        assert method.failure_modes, f"{name} declares no failure modes"


def test_the_summary_separates_implemented_from_declared():
    """Three forecasters plus one effect estimator.

    The count moved from three to four when A-SCM-001 gave SYNTHETIC_CONTROL a
    real estimator. Kept as a literal rather than derived from the registry:
    the number is here to catch a method quietly acquiring or losing an
    implementation, and a count computed from the same registry it is checking
    cannot do that.
    """
    got = EM.summarise()
    assert got["implemented"] == 4
    assert got["declared_only"] == len(EM.METHODS) - 4


def test_a_method_can_be_implemented_for_effects_and_not_for_forecasts():
    """Implemented is not one property. SYNTHETIC_CONTROL answers one job."""
    scm = EM.METHODS[EM.SYNTHETIC_CONTROL]
    assert scm.implemented
    assert scm.estimates_effects
    assert not scm.forecasts


def test_eligible_reports_appropriate_methods_that_are_unavailable():
    """'Right method, not built' differs from 'wrong method'."""
    got = EM.eligible(EM.EFFECT_OF_POLICY, 100)
    names = {m.name for m in got}
    assert names >= {EM.DIFFERENCE_IN_DIFFERENCES, EM.SYNTHETIC_CONTROL}
    # DiD remains declared-only, and `eligible` still surfaces it: a caller
    # must be able to see that the right method for the question exists and
    # has not been built.
    assert not EM.METHODS[EM.DIFFERENCE_IN_DIFFERENCES].implemented
    assert EM.METHODS[EM.INTERRUPTED_TIME_SERIES].implemented is False


def test_declaring_a_question_type_you_cannot_answer_is_refused(monkeypatch):
    """The seam that made a second estimator field necessary.

    No entry in the registry today declares both a forecast type and an effect
    type, so this cannot be provoked through METHODS as it stands — testing it
    against SYNTHETIC_CONTROL only re-tests the question-type guard, which
    answers first. The invariant is about the NEXT method: local projection or
    interrupted time series could each plausibly be declared for both jobs, and
    a method that passes `require` for a job it has no estimator for hands
    `walk_forward` a None to call, several frames from the mistake.
    """
    hybrid = EM.EconomicMethod(
        name="HYBRID", question_types=(EM.FORECAST_LEVEL, EM.EFFECT_OF_POLICY),
        minimum_sample=1, effect_estimator=lambda *a, **k: 1.0,
        assumptions=("declared for two jobs, built for one",),
        failure_modes=("asked for the job it cannot do",))
    monkeypatch.setitem(EM.METHODS, "HYBRID", hybrid)

    assert EM.require("HYBRID", EM.EFFECT_OF_POLICY, 10) is hybrid
    with pytest.raises(EM.MethodRefused) as caught:
        EM.require("HYBRID", EM.FORECAST_LEVEL, 10)
    assert "not forecasts" in str(caught.value)


def test_the_reverse_direction_is_refused_too(monkeypatch):
    hybrid = EM.EconomicMethod(
        name="HYBRID2",
        question_types=(EM.FORECAST_LEVEL, EM.EFFECT_OF_POLICY),
        minimum_sample=1, estimator=lambda history: history[-1],
        assumptions=("declared for two jobs, built for the other one",),
        failure_modes=("asked for the job it cannot do",))
    monkeypatch.setitem(EM.METHODS, "HYBRID2", hybrid)

    assert EM.require("HYBRID2", EM.FORECAST_LEVEL, 10) is hybrid
    with pytest.raises(EM.MethodRefused) as caught:
        EM.require("HYBRID2", EM.EFFECT_OF_POLICY, 10)
    assert "no effect estimator" in str(caught.value)


def test_an_effect_method_still_refuses_a_forecast_at_the_question_guard():
    with pytest.raises(EM.MethodRefused) as caught:
        EM.require(EM.SYNTHETIC_CONTROL, EM.FORECAST_LEVEL, 100)
    assert "answers ['EFFECT_OF_POLICY']" in str(caught.value)


# --- walk-forward is enforced, not requested ---------------------------------

def test_no_prediction_uses_its_own_observation():
    series = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    method = EM.METHODS[EM.PERSISTENCE]
    predicted, actual = EM.walk_forward(series, method, minimum_train=1)
    # persistence predicts the previous value; if any prediction equalled its
    # own actual on a strictly increasing series, it saw the answer.
    assert all(p != a for p, a in zip(predicted, actual))
    assert predicted == series[:-1]


def test_a_constant_series_does_not_produce_a_fabricated_slope():
    """AR1 with no regressor variance must fall back, not invent a coefficient."""
    assert EM._ar1([5.0] * 12) == 5.0


def test_drift_extrapolates_the_average_step():
    assert EM._drift([1.0, 2.0, 3.0]) == 4.0


def test_persistence_is_the_last_value():
    assert EM._persistence([7.0, 9.0, 4.0]) == 4.0


# --- comparison is like-for-like ---------------------------------------------

def test_all_methods_are_scored_on_one_training_window():
    series = [float(i) for i in range(40)]
    got = EM.compare(series, series_name="ramp")
    counts = {r["method"]: r["predictions"] for r in got["results"]}
    assert len(set(counts.values())) == 1, (
        f"methods were scored on different numbers of predictions: {counts}; "
        "a method needing less history would get more and easier ones")
    # Equality alone does not pin the window: taking the MINIMUM minimum_sample
    # also gives every method the same count, while scoring AR1 from one point
    # of history — below the eight it declares it needs. The window has to be
    # large enough for the hungriest method in the comparison.
    needed = max(EM.METHODS[m].minimum_sample for m in counts)
    assert got["training_window"] >= needed, (
        f"training window {got['training_window']} is below the "
        f"{needed} observations the most demanding method declares; it would "
        "be scored on a history it says is too short to fit")


def test_drift_beats_persistence_on_a_pure_trend():
    series = [float(i) for i in range(40)]
    got = EM.compare(series, series_name="ramp")
    assert got["best"] == EM.DRIFT
    assert EM.DRIFT in got["beat_persistence"]


def test_persistence_usually_wins_on_a_random_walk():
    """Asserted across seeds, because one walk proves nothing either way.

    A finite random walk has a realized drift, and DRIFT is entitled to pick
    it up — on seed 11 it wins outright. Pinning a single seed would make this
    a coin flip dressed as a guard. Measured over 60 walks: persistence wins
    51, drift's mean skill is -1.3%, and drift is ahead on 8. The claim worth
    defending is the tendency, not the instance.
    """
    import random

    wins = 0
    for seed in range(30):
        rng = random.Random(seed)
        value, series = 100.0, []
        for _ in range(120):
            value += rng.gauss(0, 1)
            series.append(value)
        if EM.compare(series)["best"] == EM.PERSISTENCE:
            wins += 1
    assert wins >= 20, (
        f"persistence won only {wins}/30 random walks; on a driftless walk it "
        "should usually win, and a method beating it consistently means the "
        "walk-forward split is leaking")


def test_a_refused_method_is_reported_rather_than_dropped():
    got = EM.compare([1.0, 2.0], names=[EM.PERSISTENCE, EM.AR1])
    assert EM.AR1 in got["refused"]
    assert "needs 8 observations" in got["refused"][EM.AR1]


def test_a_series_no_method_can_take_returns_no_result_not_a_guess():
    got = EM.compare([], names=[EM.AR1])
    assert got["results"] == []
    assert got["best"] == ""


def test_skill_is_none_when_persistence_could_not_be_scored():
    series = [float(i) for i in range(40)]
    got = EM.compare(series, names=[EM.DRIFT], series_name="ramp")
    assert all(r["skill_vs_persistence"] is None for r in got["results"])
    assert all(r["beat_baseline"] is None for r in got["results"]), (
        "without the baseline in the comparison, 'beat the baseline' has no "
        "answer and must not default to False")

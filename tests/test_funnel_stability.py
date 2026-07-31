"""Funnel stability — the rule that replaced calendar time with confidence.

Day 12 ranked a bottleneck from one cycle. Day 13 required three days, which is
better and still wrong: 3%, 8%, 4% satisfies "three days" and establishes
nothing. The test is dispersion, not duration.
"""
from intent_engine.market.funnel import (
    INSUFFICIENT, MAX_STABLE_CV, MIN_OBSERVATIONS, STABLE, UNSTABLE,
    promote_bottleneck, stage_stability, stability_report,
)


def _day(rate, stage="strategic_view", loss=True):
    return {"as_of": f"d{rate}", "rates": {stage: rate},
            "largest_loss": {"stage": stage, "lost": 1, "from": 2,
                             "rate": rate} if loss else None}


def _history(rates, stage="strategic_view"):
    return [_day(r, stage) for r in rates]


# --- calendar time is not evidence -------------------------------------------
def test_three_noisy_days_do_not_establish_a_bottleneck():
    """The exact case that motivated replacing the calendar rule."""
    verdict = promote_bottleneck(_history([0.03, 0.08, 0.04]))
    assert verdict["verdict"] == "CANDIDATE BOTTLENECK"
    assert "needed" in verdict["reason"]


def test_a_high_variance_stage_is_never_promoted_however_long_the_history():
    """A stage swinging wildly is measuring conditions, not capability."""
    verdict = promote_bottleneck(_history([0.0, 0.0, 0.5, 0.1, 0.0, 0.6, 0.05]))
    assert verdict["verdict"] == "CANDIDATE BOTTLENECK"
    assert "varies too much" in verdict["reason"]
    assert verdict["stability"]["status"] == UNSTABLE


def test_a_stable_stage_with_enough_history_is_promoted():
    verdict = promote_bottleneck(_history([0.10, 0.11, 0.10, 0.12, 0.11, 0.10]))
    assert verdict["verdict"] == "BOTTLENECK"
    assert verdict["stage"] == "strategic_view"
    assert verdict["stability"]["status"] == STABLE


def test_a_stage_leading_a_minority_of_days_is_only_a_candidate():
    history = _history([0.10, 0.11, 0.10, 0.12, 0.11, 0.10])
    for day in history[:4]:
        day["largest_loss"] = {"stage": "signal_fired", "lost": 1,
                               "from": 2, "rate": 0.5}
    verdict = promote_bottleneck(history)
    assert verdict["verdict"] == "CANDIDATE BOTTLENECK"


# --- the statistics ----------------------------------------------------------
def test_below_the_observation_floor_no_dispersion_is_reported():
    s = stage_stability(_history([0.1, 0.2]), "strategic_view")
    assert s.status == INSUFFICIENT
    assert s.mean is None and s.cv is None and s.stdev is None
    assert s.observations < MIN_OBSERVATIONS


def test_stability_reports_the_full_distribution_not_just_today():
    s = stage_stability(_history([0.10, 0.11, 0.10, 0.12, 0.11]),
                        "strategic_view")
    assert s.today == 0.11
    assert s.mean and s.median and s.stdev is not None
    assert s.interval and s.interval[0] < s.mean < s.interval[1]
    assert s.cv is not None and s.cv <= MAX_STABLE_CV
    assert s.status == STABLE


def test_the_trend_is_coarse_because_a_slope_on_five_noisy_points_is_false():
    rising = stage_stability(_history([0.05, 0.06, 0.20, 0.25, 0.30]),
                             "strategic_view")
    falling = stage_stability(_history([0.30, 0.25, 0.20, 0.06, 0.05]),
                              "strategic_view")
    assert rising.trend == "rising" and falling.trend == "falling"


def test_every_stage_is_reported_even_with_no_history():
    rows = stability_report([])
    assert rows and all(r["status"] == INSUFFICIENT for r in rows)


def test_no_conversion_loss_yet_is_a_candidate_not_a_conclusion():
    verdict = promote_bottleneck([_day(0.1, loss=False)])
    assert verdict["verdict"] == "CANDIDATE BOTTLENECK"
    assert verdict["stage"] is None

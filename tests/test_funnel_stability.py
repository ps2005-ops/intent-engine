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


# --- evidence maturity -------------------------------------------------------
def test_maturity_says_how_far_away_the_answer_is_not_merely_that_it_is_away():
    """"Insufficient history" is honest and uninformative on its own: it does
    not say whether the answer is one day out or twenty."""
    from intent_engine.market.funnel import evidence_maturity
    m = evidence_maturity(_history([0.11, 0.07, 0.07]), "strategic_view")
    assert m.observations == 3 and m.required == 5
    assert m.maturity == 0.6
    assert m.days_to_earliest_promotion == 2
    assert m.candidate_streak == 3
    assert m.confidence == INSUFFICIENT
    assert not m.must_decide


def test_reaching_the_floor_obliges_a_decision():
    """Continuing to gather data purely to avoid committing is as wrong as
    committing too early -- and is the failure a cautious project develops."""
    from intent_engine.market.funnel import evidence_maturity
    m = evidence_maturity(_history([0.10, 0.11, 0.10, 0.12, 0.11]),
                          "strategic_view")
    assert m.must_decide and m.maturity == 1.0
    assert m.days_to_earliest_promotion == 0


def test_the_streak_breaks_when_another_stage_leads():
    from intent_engine.market.funnel import candidate_streak
    history = _history([0.1, 0.1, 0.1])
    history[1]["largest_loss"] = {"stage": "signal_fired", "lost": 1,
                                  "from": 2, "rate": 0.5}
    assert candidate_streak(history, "strategic_view") == 1


# --- research velocity -------------------------------------------------------
def test_a_day_that_learns_nothing_reports_zero():
    """A research system obliged to report a discovery daily will eventually
    manufacture one."""
    from intent_engine.market.funnel import ResearchVelocity
    assert ResearchVelocity().net_knowledge_gain == 0


def test_weakening_a_finding_is_negative_velocity():
    """A day that undermines a held conclusion means the project knows LESS
    than it thought. That must not read as progress."""
    from intent_engine.market.funnel import ResearchVelocity
    assert ResearchVelocity(weakened=2).net_knowledge_gain == -2
    assert ResearchVelocity(new_negative=1, weakened=3).net_knowledge_gain == -2


def test_a_stage_with_zero_variance_is_maximally_stable_not_unstable():
    """`signal_fired` flat at 0.00 for five days is the most stable
    observation available, and it says the signal has never fired. CV is
    undefined at mean 0, and falling through to UNSTABLE inverted the meaning.
    """
    s = stage_stability(_history([0.0, 0.0, 0.0, 0.0, 0.0]), "strategic_view")
    assert s.stdev == 0.0
    assert s.status == STABLE, "zero dispersion must not read as noisy"


# ---------------------------------------------------------------------------
# INTERPRETATION — Day 17. Stability is not desirability.
#
# Day 16 fixed the inverse defect (zero dispersion read as UNSTABLE) and
# created the opposite hazard: a column of green STABLE labels, one of which
# says the engine has never acted.
# ---------------------------------------------------------------------------
from intent_engine.market.funnel import (            # noqa: E402
    DEGRADED_BELOW, NOT_INTERPRETABLE, STABLE_AT_ZERO, STABLE_DEGRADED,
    STABLE_HEALTHY, interpret,
)


def test_a_flat_zero_stage_is_stable_at_zero_not_healthy():
    """`signal_fired` at 0.00 with sd 0.00 is the most stable observation in
    the report AND the most alarming. Both, simultaneously."""
    stability = stage_stability(_history([0.0] * 6, stage="signal_fired"),
                                "signal_fired")
    assert stability.status == STABLE
    assert stability.stdev == 0.0
    assert stability.interpretation == STABLE_AT_ZERO


def test_a_stable_high_conversion_is_healthy():
    stability = stage_stability(_history([0.96] * 6, stage="tradable"),
                                "tradable")
    assert stability.interpretation == STABLE_HEALTHY


def test_a_stable_low_conversion_is_degraded_not_healthy():
    """strategic_view at ~9% is statistically stable and is losing 91% of what
    reaches it. The report must say both."""
    stability = stage_stability(
        _history([0.09, 0.10, 0.08, 0.09, 0.11, 0.07]), "strategic_view")
    assert stability.status == STABLE
    assert stability.interpretation == STABLE_DEGRADED


def test_an_unstable_stage_has_no_interpretation():
    """Inventing one would be exactly the false precision this avoids."""
    stability = stage_stability(
        _history([0.0, 0.6, 0.05, 0.5, 0.0, 0.7]), "strategic_view")
    assert stability.status == UNSTABLE
    assert stability.interpretation is None


def test_an_under_observed_stage_has_no_interpretation():
    stability = stage_stability(_history([0.5, 0.5]), "strategic_view")
    assert stability.status == INSUFFICIENT
    assert stability.interpretation is None


def test_a_terminal_share_is_not_interpretable_as_good_or_bad():
    """NO_TRADE at 89% is neither healthy nor degraded — it is the shape of
    the decision mix."""
    assert interpret("no_trade", STABLE, 0.89) == NOT_INTERPRETABLE
    assert interpret("watch", STABLE, 0.11) == NOT_INTERPRETABLE


def test_the_degraded_boundary_is_explicit():
    assert interpret("strategic_view", STABLE, DEGRADED_BELOW) == STABLE_HEALTHY
    assert interpret("strategic_view", STABLE,
                     DEGRADED_BELOW - 0.001) == STABLE_DEGRADED


def test_interpretation_is_carried_in_the_serialised_report():
    rows = stability_report(_history([0.0] * 6, stage="signal_fired"))
    fired = [r for r in rows if r["stage"] == "signal_fired"][0]
    assert fired["interpretation"] == STABLE_AT_ZERO
    assert "interpretation" in rows[0]


def test_every_chain_and_terminal_and_diagnostic_stage_is_reported():
    from intent_engine.market.funnel import CHAIN, DIAGNOSTICS, TERMINALS
    rows = stability_report(_history([0.1] * 6))
    stages = {r["stage"] for r in rows}
    assert stages == set(CHAIN[1:]) | set(TERMINALS) | set(DIAGNOSTICS)

"""T018 bars: stdlib statistics and honest UNAVAILABLE."""
import json

import pytest

from intent_engine.growth.statistics import (
    MIN_FAILURES_PER_ARM, MIN_SUCCESSES_PER_ARM, PROPORTION_STAT_VERSION,
    arm_counts, difference_in_proportions,
)


def _arm(arm_id, observed, successes):
    return arm_counts(arm_id, assigned=observed, exposed=observed,
                      observed=observed, successes=successes)


def test_arm_counts_and_rate():
    a = _arm("control", 100, 20)
    assert a["rate"] == 0.2 and a["status"] == "OK"
    assert a["statistic_version"] == "arm_counts.v1"


def test_zero_denominator_is_unavailable_not_zero_rate():
    a = _arm("control", 0, 0)
    assert a["status"] == "UNAVAILABLE" and a["rate"] is None
    assert "not a rate of 0" in a["reason"]


def test_point_estimate_computed_and_interval_when_assumptions_hold():
    stat = difference_in_proportions(_arm("control", 200, 40),
                                     _arm("treatment", 200, 70))
    assert stat["status"] == "OK"
    assert stat["assumption_check"] == "passed"
    assert stat["point_estimate"] == 0.15
    assert stat["interval"] is not None
    assert stat["statistic_version"] == PROPORTION_STAT_VERSION
    assert stat["interval_excludes_zero"] is True


def test_interval_includes_zero_when_arms_are_similar():
    stat = difference_in_proportions(_arm("control", 300, 60),
                                     _arm("treatment", 300, 63))
    assert stat["status"] == "OK"
    assert stat["interval_excludes_zero"] is False


def test_failed_assumption_names_the_assumption_and_is_unavailable():
    stat = difference_in_proportions(_arm("control", 10, 1),
                                     _arm("treatment", 10, 2))
    assert stat["status"] == "UNAVAILABLE"
    assert stat["assumption_check"] == "failed"
    assert f"< {MIN_SUCCESSES_PER_ARM}" in stat["reason"]
    # the point estimate still stands; only the interval is withheld
    assert stat["point_estimate"] == 0.1
    assert stat["interval"] is None


def test_empty_arm_is_unavailable():
    stat = difference_in_proportions(_arm("control", 0, 0),
                                     _arm("treatment", 50, 10))
    assert stat["status"] == "UNAVAILABLE"
    assert "no observations" in stat["reason"]


def test_unsupported_confidence_level_is_refused_not_approximated():
    stat = difference_in_proportions(_arm("control", 200, 40),
                                     _arm("treatment", 200, 70),
                                     confidence=0.99)
    assert stat["status"] == "UNAVAILABLE"
    assert "inverse normal CDF" in stat["reason"]


def test_every_statistic_is_self_describing():
    for stat in (difference_in_proportions(_arm("c", 200, 40),
                                           _arm("t", 200, 70)),
                 difference_in_proportions(_arm("c", 5, 1),
                                           _arm("t", 5, 2))):
        for field in ("statistic_name", "statistic_version", "assumptions",
                      "assumption_check", "status"):
            assert field in stat
        assert stat["assumptions"]


def test_no_p_value_no_significance_no_bayesian_field_exists():
    stat = difference_in_proportions(_arm("control", 500, 100),
                                     _arm("treatment", 500, 150))
    blob = json.dumps(stat).lower()
    for banned in ("p_value", "p-value", "significan", "posterior",
                   "credible", "probability_better", "bayes"):
        assert banned not in blob, banned
    assert "winner" not in blob and "won" not in blob


def test_degenerate_arms_yield_no_interval():
    stat = difference_in_proportions(_arm("control", 100, 100),
                                     _arm("treatment", 100, 100))
    assert stat["status"] == "UNAVAILABLE"
    assert stat["assumption_check"] == "failed"

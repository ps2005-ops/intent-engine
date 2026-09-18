"""Learning Value, and the metric-integrity properties it has to hold.

The load-bearing tests here are the ones that stop the metric being gamed and
the ones that stop it inventing a number it cannot measure. A metric this
project ranks its own work by is exactly the thing an optimiser will attack.
"""
from intent_engine.market.learning_value import (
    UNMEASURABLE,
    assess_cycle,
    calibration_impact,
    information_gain,
    learning_value,
    novelty,
    resolution_quality,
)


def _ev(company, direction="up", source="baseline_momentum.v1", **kw):
    row = {"company_id": company, "direction": direction,
           "market_source": source, "classification": "BUY"}
    row.update(kw)
    return row


# --- the scenario the metric exists to get right ------------------------------
def test_twenty_varied_evaluations_beat_a_hundred_identical_ones():
    """The failure Learning Velocity could not see.

      A: 100 predictions, every one a momentum trade
      B:  20 predictions across four signals and both directions

    B is obviously the better engine. Counting resolvable records scores A five
    times higher, which is why counting them cannot be the objective.
    """
    a = [_ev(f"co{i}") for i in range(100)]
    b = [_ev(f"co{i}", "up" if i % 2 else "down",
             ["baseline_momentum.v1", "earnings_surprise.v1",
              "guidance_shift.v1", "macro_regime.v1"][i % 4])
         for i in range(20)]

    ra, rb = assess_cycle(a), assess_cycle(b)

    # the old headline preferred A ...
    assert ra["resolvable"] > rb["resolvable"]
    # ... and the new one prefers B
    assert rb["novelty_weighted"] > ra["novelty_weighted"]
    assert rb["distinct_shapes"] > ra["distinct_shapes"]


def test_repeating_one_trade_does_not_multiply_the_score():
    """The concrete gaming case: ten predictions about the same thing.

    Under the old metric this was worth 10. It must be worth close to 1, not
    zero — a repeat does add a calibration sample — but nowhere near ten.
    """
    result = assess_cycle([_ev("acme") for _ in range(10)])
    assert result["resolvable"] == 10
    assert 1.0 < result["novelty_weighted"] < 2.5


def test_marginal_novelty_decays_within_a_shape():
    """The fiftieth test of a rule teaches less than the fifth."""
    prior = []
    values = []
    for i in range(6):
        row = _ev(f"co{i}")
        values.append(novelty(row, list(prior)))
        prior.append(row)
    assert values[0] == 1.0
    assert values == sorted(values, reverse=True), "novelty must not increase"
    assert values[-1] < values[1] < values[0]


def test_a_new_shape_always_scores_full_novelty():
    prior = [_ev(f"co{i}") for i in range(50)]
    fresh = _ev("co0", "down", "earnings_surprise.v1")
    assert novelty(fresh, prior) == 1.0


def test_novelty_never_reaches_zero():
    """A repeated trade still adds a sample to a calibration curve."""
    prior = [_ev("acme") for _ in range(200)]
    assert novelty(_ev("acme"), prior) > 0


# --- refusing to fabricate ----------------------------------------------------
def test_unmeasurable_factors_are_not_estimated():
    """Three of four factors need resolved outcomes, a knowledge base and
    calibration data. None exist. Estimating them would produce a number its
    author controls completely — more gameable than the metric it replaced,
    because moving that one at least required a code edit."""
    assert resolution_quality(_ev("acme")) is UNMEASURABLE
    assert information_gain(_ev("acme")) is UNMEASURABLE
    assert calibration_impact(_ev("acme")) is UNMEASURABLE


def test_the_score_refuses_to_exist_while_a_factor_is_unmeasurable():
    """Returning a partial product would treat unknown as 1.0, making an
    unmeasured system score identically to a fully-understood one."""
    value = learning_value(_ev("acme"))
    assert value.score is None
    assert not value.is_measurable
    assert set(value.missing) == {"resolution_quality", "information_gain",
                                  "calibration_impact"}
    # novelty is still reported, because it IS measurable
    assert value.novelty == 1.0


def test_a_cycle_says_which_factors_it_could_not_measure():
    result = assess_cycle([_ev("acme")])
    assert result["learning_value"] is None
    assert result["unmeasurable_factors"]
    assert result["why_unscored"]


def test_resolution_quality_becomes_measurable_once_an_outcome_exists():
    """The factor is not permanently unmeasurable — it is unmeasurable *now*,
    and turns on by itself when resolution starts producing outcomes."""
    clean = resolution_quality(_ev("acme", outcome="happened"))
    dirty = resolution_quality(_ev("acme", outcome="happened",
                                   resolution_note="no_price"))
    assert clean == 1.0
    assert dirty is not UNMEASURABLE and dirty < clean


# --- non-positions are not evaluations of a prediction ------------------------
def test_watch_and_no_trade_do_not_count_as_resolvable():
    rows = [dict(_ev("a"), classification="WATCH"),
            dict(_ev("b"), classification="NO_TRADE"),
            _ev("c")]
    result = assess_cycle(rows)
    assert result["evaluations"] == 3
    assert result["resolvable"] == 1


def test_an_empty_cycle_is_zero_not_an_error():
    result = assess_cycle([])
    assert result["resolvable"] == 0 and result["novelty_weighted"] == 0

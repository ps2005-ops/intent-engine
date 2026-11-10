"""Decision Quality — the capability every other metric is a proxy for.

The load-bearing tests are the ones that stop outcome bias. Grading a
justified refusal as an error would teach the engine to take positions on
insufficient evidence whenever the coin lands well — destroying the exact
capability this is meant to measure.
"""
from intent_engine.market.decision_quality import (
    HIGH,
    LOW,
    MATERIAL_MOVE,
    MEDIUM,
    UNMEASURABLE,
    assess,
    grade,
    realised_move,
)


def _d(company, classification, gate="", direction=""):
    return {"company_id": company, "classification": classification,
            "blocked_by": [gate] if gate else [], "direction": direction}


# --- refusals are decisions, and they are 91% of them ------------------------
def test_refusals_are_graded_not_skipped():
    """Resolution as originally scoped graded BUY/SELL only — 1 of 11
    decisions. The other ten would have been ungraded forever."""
    decisions = [_d("a", "BUY", direction="up"),
                 _d("b", "WATCH", "no_market_evidence"),
                 _d("c", "NO_TRADE", "not_tradable")]
    prices = {"a": (100.0, 110.0), "b": (100.0, 101.0), "c": (100.0, 99.0)}
    result = assess(decisions, prices)
    assert result["graded"] == 3
    assert result["share_of_decisions_graded"] == 1.0
    assert result["refusal_justification_rate"]["n"] == 2


# --- outcome bias, refused --------------------------------------------------
def test_a_justified_refusal_that_missed_a_move_is_not_an_error():
    """THE guard. Marking this wrong teaches the engine to take positions on
    insufficient evidence whenever the price happens to rise."""
    g = grade(_d("a", "WATCH", "no_outside_source"),
              entry_price=100.0, exit_price=130.0)
    assert g.justified is True
    assert g.material_miss is True
    assert g.correct is None, "a refusal must not be scored as a position"
    assert "opportunity cost, not an error" in g.note


def test_correctness_and_opportunity_cost_are_never_collapsed():
    result = assess([_d("a", "WATCH", "no_outside_source")],
                    {"a": (100.0, 140.0)})
    assert result["refusal_justification_rate"]["value"] == 1.0
    assert result["material_miss_rate"]["value"] == 1.0
    # both true at once, and reported separately


def test_a_refusal_citing_an_unrecognised_reason_is_not_justified():
    """Listed gates only, so a carelessly added gate cannot silently launder a
    bad refusal into a good one."""
    g = grade(_d("a", "NO_TRADE", "because_i_felt_like_it"),
              entry_price=100.0, exit_price=101.0)
    assert g.justified is False
    result = assess([_d("a", "NO_TRADE", "because_i_felt_like_it")],
                    {"a": (100.0, 101.0)})
    assert result["unjustified_refusals"] == ["a"]


def test_an_untradable_company_forgoes_nothing():
    """There was no instrument to hold, so there is no opportunity cost to
    record — and counting one would make every private company a permanent
    miss."""
    g = grade(_d("a", "NO_TRADE", "not_tradable"),
              entry_price=100.0, exit_price=200.0)
    assert g.justified is True
    assert g.forgone_move is None and g.material_miss is False


# --- positions ---------------------------------------------------------------
def test_a_position_is_graded_on_direction():
    up_right = grade(_d("a", "BUY", direction="up"), entry_price=100.0, exit_price=110.0)
    up_wrong = grade(_d("a", "BUY", direction="up"), entry_price=100.0, exit_price=90.0)
    down_right = grade(_d("a", "SELL", direction="down"), entry_price=100.0, exit_price=90.0)
    assert up_right.correct and down_right.correct
    assert up_wrong.correct is False


# --- missing data is not a measurement ---------------------------------------
def test_a_missing_price_leaves_the_decision_ungraded():
    """Scoring a data gap as "no move" would quietly count every gap as a
    correct refusal."""
    assert realised_move(None, 100.0) is None
    assert realised_move(100.0, None) is None
    g = grade(_d("a", "WATCH", "no_market_evidence"))
    assert g.realised_move is None and g.justified is None
    result = assess([_d("a", "WATCH", "no_market_evidence")], {})
    assert result["ungraded_no_price"] == 1
    assert result["graded"] == 0


# --- metric confidence -------------------------------------------------------
def test_every_rate_carries_the_sample_size_it_rests_on():
    """A rate over three decisions and one over three hundred are not the same
    measurement, and presenting them identically is how a system talks itself
    into certainty it has not earned."""
    small = assess([_d("a", "BUY", direction="up")], {"a": (100.0, 110.0)})
    assert small["position_accuracy"]["n"] == 1
    assert small["position_accuracy"]["confidence"] == LOW

    many = assess([_d(f"c{i}", "BUY", direction="up") for i in range(30)],
                  {f"c{i}": (100.0, 110.0) for i in range(30)})
    assert many["position_accuracy"]["confidence"] == HIGH

    mid = assess([_d(f"c{i}", "BUY", direction="up") for i in range(12)],
                 {f"c{i}": (100.0, 110.0) for i in range(12)})
    assert mid["position_accuracy"]["confidence"] == MEDIUM


def test_a_rate_with_no_samples_is_unmeasurable_not_zero():
    result = assess([_d("a", "WATCH", "no_market_evidence")],
                    {"a": (100.0, 101.0)})
    assert result["position_accuracy"]["value"] is None
    assert result["position_accuracy"]["confidence"] == UNMEASURABLE


def test_a_move_below_the_material_threshold_is_not_a_miss():
    small = grade(_d("a", "WATCH", "no_market_evidence"),
                  entry_price=100.0,
                  exit_price=100.0 + MATERIAL_MOVE * 100 - 1)
    assert small.material_miss is False

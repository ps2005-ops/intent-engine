"""Execution realism, the live boundary, level-k and reflexivity.

Section 32's execution and game-theory blocks, plus Section 14's requirement
that live capital be impossible to reach by configuration.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import execution as EX
from intent_engine.econ import levelk as LK
from intent_engine.econ import reflexivity as RX
from intent_engine.econ.causal import DOWN, UP


def conditions(**kw):
    base = dict(reference_price=100.0, spread_bps=4.0, daily_volume=1_000_000,
                volatility_daily=0.02)
    base.update(kw)
    return EX.MarketConditions(**base)


# --- the live boundary ------------------------------------------------------
def test_the_live_adapter_cannot_be_constructed():
    with pytest.raises(EX.LiveExecutionRefused, match="not part of this system"):
        EX.LiveBrokerAdapter()


def test_resolving_the_live_mode_refuses_rather_than_falling_back():
    """A silent fallback to paper would be worse: it would let a caller that
    asked for live believe it got live."""
    with pytest.raises(EX.LiveExecutionRefused):
        EX.adapter_for(EX.LIVE)


def test_paper_and_shadow_resolve_and_shadow_is_not_more_optimistic():
    paper = EX.adapter_for(EX.PAPER)
    shadow = EX.adapter_for(EX.SHADOW)
    impact = EX.ImpactModel()
    p = paper.fill(side="BUY", quantity=10_000, conditions=conditions(),
                   impact=impact)
    s = shadow.fill(side="BUY", quantity=10_000, conditions=conditions(),
                    impact=impact)
    assert s.total_cost_bps >= p.total_cost_bps, (
        "the shadow adapter fills more cheaply than paper; a shadow that is "
        "more optimistic than the model is worse than useless")


# --- zero-friction baseline -------------------------------------------------
def test_a_zero_friction_fill_is_exactly_the_signal_price():
    free = EX.ImpactModel(eta=0.0, gamma=0.0, fee_bps=0.0)
    fill = EX.PaperExecutionAdapter().fill(
        side="BUY", quantity=1, conditions=conditions(spread_bps=0.0),
        impact=free)
    assert fill.executed_price == pytest.approx(100.0)
    assert fill.slippage_bps == pytest.approx(0.0)
    assert fill.total_cost_bps == pytest.approx(0.0)


# --- monotonicity -----------------------------------------------------------
def test_cost_is_monotonic_in_the_spread():
    adapter = EX.PaperExecutionAdapter()
    impact = EX.ImpactModel()
    costs = [adapter.fill(side="BUY", quantity=1000,
                          conditions=conditions(spread_bps=s),
                          impact=impact).total_cost_bps
             for s in (0.0, 2.0, 8.0, 20.0)]
    assert costs == sorted(costs) and costs[0] < costs[-1]


def test_impact_is_monotonic_in_size():
    adapter = EX.PaperExecutionAdapter()
    impact = EX.ImpactModel()
    costs = [adapter.fill(side="BUY", quantity=q, conditions=conditions(),
                          impact=impact).total_cost_bps
             for q in (100, 1_000, 10_000, 50_000)]
    assert costs == sorted(costs) and costs[0] < costs[-1]


def test_impact_is_monotonic_in_volatility():
    adapter = EX.PaperExecutionAdapter()
    impact = EX.ImpactModel()
    costs = [adapter.fill(side="BUY", quantity=10_000,
                          conditions=conditions(volatility_daily=v),
                          impact=impact).total_cost_bps
             for v in (0.005, 0.01, 0.03, 0.08)]
    assert costs == sorted(costs)


def test_costs_always_move_the_price_against_the_order():
    """The one place a sign error would silently create alpha."""
    adapter, impact = EX.PaperExecutionAdapter(), EX.ImpactModel()
    buy = adapter.fill(side="BUY", quantity=10_000, conditions=conditions(),
                       impact=impact)
    sell = adapter.fill(side="SELL", quantity=10_000, conditions=conditions(),
                        impact=impact)
    assert buy.executed_price > buy.signal_price
    assert sell.executed_price < sell.signal_price
    assert buy.slippage_bps > 0 and sell.slippage_bps > 0


# --- impossible fills -------------------------------------------------------
def test_an_order_above_the_participation_cap_is_refused():
    with pytest.raises(EX.ImpossibleFill, match="inventing liquidity"):
        EX.PaperExecutionAdapter().fill(
            side="BUY", quantity=400_000, conditions=conditions(),
            impact=EX.ImpactModel())


def test_an_instrument_with_no_volume_has_no_executable_price():
    with pytest.raises(Exception, match="inventing liquidity|no volume"):
        conditions(daily_volume=0)


# --- toxicity proxy ---------------------------------------------------------
def test_the_toxicity_proxy_is_never_ground_truth():
    got = EX.vpin([1.0] * 60, [0.01] * 60)
    assert got.ground_truth is False
    assert got.limitations and got.assumptions
    assert got.as_dict()["kind"] == "toxicity_proxy"


def test_a_small_sample_reports_no_value_rather_than_a_small_sample_one():
    got = EX.vpin([1.0] * 4, [0.01] * 4)
    assert got.value is None
    assert any("no value is reported" in l for l in got.limitations)


# --- level-k ----------------------------------------------------------------
def test_level_zero_is_every_class_doing_what_it_already_does():
    view = LK.react(quantity="vix", direction=UP, as_of="2026-08-24")
    l0 = view.at(LK.L0)
    assert {r.participant for r in l0} == set(LK.PARTICIPANTS)
    assert all(r.flow == LK.HOLD for r in l0)


def test_a_mandate_that_says_nothing_produces_no_reaction_not_a_hold():
    """The distinction: 'this rule does not speak to this shock' is not 'this
    class does nothing', and the second is a claim."""
    view = LK.react(quantity="housing", direction=UP, as_of="2026-08-24")
    assert view.at(LK.L1) == []
    assert view.net_flow(LK.L1) == LK.HOLD


def test_the_sign_control_a_volatility_spike_makes_vol_control_sell():
    view = LK.react(quantity="vix", direction=UP, as_of="2026-08-24")
    vc = [r for r in view.at(LK.L1) if r.participant == LK.VOL_CONTROL]
    assert vc and vc[0].flow == LK.SELL


def test_the_opposite_shock_does_not_produce_the_same_reaction():
    """A reaction set that is identical in both directions is not a model."""
    up = LK.react(quantity="sector_return", direction=UP, as_of="2026-08-24")
    down = LK.react(quantity="sector_return", direction=DOWN,
                    as_of="2026-08-24")
    cta_up = [r.flow for r in up.at(LK.L1) if r.participant == LK.CTA]
    cta_down = [r.flow for r in down.at(LK.L1) if r.participant == LK.CTA]
    assert cta_up == [LK.BUY] and cta_down == [LK.SELL]


def test_every_reaction_names_the_mandate_clause_it_follows():
    view = LK.react(quantity="vix", direction=UP, as_of="2026-08-24")
    for r in view.reactions:
        assert r.basis.strip()


def test_an_l2_reaction_must_name_whose_response_it_anticipates():
    with pytest.raises(Exception, match="anticipat"):
        LK.Reaction(participant=LK.DISCRETIONARY_MACRO, level=LK.L2,
                    flow=LK.SELL, basis="a view", confidence=0.3,
                    timing_days=1)


def test_l2_only_appears_when_there_is_a_mechanical_response_to_anticipate():
    quiet = LK.react(quantity="housing", direction=UP, as_of="2026-08-24")
    assert quiet.at(LK.L2) == []
    loud = LK.react(quantity="vix", direction=UP, as_of="2026-08-24")
    assert loud.at(LK.L2), "a mechanical seller existed and nobody front-ran it"
    for r in loud.at(LK.L2):
        assert r.anticipates in LK.PARTICIPANTS
        assert r.confidence < max(x.confidence for x in loud.at(LK.L1))


def test_qre_is_sensitive_to_rationality_and_sums_to_one():
    payoffs = [1.0, 0.0, -1.0]
    indifferent = LK.quantal_response(payoffs, rationality=0.0)
    sharp = LK.quantal_response(payoffs, rationality=8.0)
    assert sum(indifferent) == pytest.approx(1.0)
    assert sum(sharp) == pytest.approx(1.0)
    assert indifferent[0] == pytest.approx(1 / 3)
    assert sharp[0] > 0.9, "the rationality parameter changed nothing"


# --- reflexivity ------------------------------------------------------------
def test_an_unknown_dealer_gamma_sign_is_not_armed():
    """The loop a guess would matter most in."""
    view = LK.react(quantity="vix", direction=UP, as_of="2026-08-24")
    loops = {l.name: l for l in RX.armed_loops(view)}
    assert not loops["dealer_short_gamma"].armed
    assert "not supplied" in loops["dealer_short_gamma"].basis


def test_supplying_a_negative_gamma_arms_the_loop():
    view = LK.react(quantity="vix", direction=UP, as_of="2026-08-24")
    loops = {l.name: l for l in
             RX.armed_loops(view, dealer_gamma_negative=True)}
    assert loops["dealer_short_gamma"].armed


def test_attribution_never_claims_to_be_measured():
    view = LK.react(quantity="vix", direction=UP, as_of="2026-08-24")
    got = RX.attribution(view)
    assert got.measured is False
    assert "not a measurement" in got.sentence()


def test_more_armed_loops_shift_attribution_toward_forced_flow():
    quiet = RX.attribution(LK.react(quantity="housing", direction=UP,
                                    as_of="2026-08-24"))
    assert quiet.reflexive_share == "negligible"
    loud = RX.attribution(LK.react(quantity="vix", direction=UP,
                                   as_of="2026-08-24"),
                          dealer_gamma_negative=True)
    assert loud.reflexive_share in ("comparable", "dominant")


def test_a_reflexive_move_carries_a_warning_against_refitting_the_mechanism():
    loud = RX.attribution(LK.react(quantity="vix", direction=UP,
                                   as_of="2026-08-24"),
                          dealer_gamma_negative=True)
    warning = RX.learning_warning(loud)
    assert "may not be used to re-estimate" in warning
    quiet = RX.attribution(LK.react(quantity="housing", direction=UP,
                                    as_of="2026-08-24"))
    assert RX.learning_warning(quiet) == ""

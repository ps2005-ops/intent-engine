"""Day 18 — universe tiers, strategies, horizons, replay, competition.

The tests that matter most here are the ones asserting the system REFUSES:
refuses to rank on trade count, refuses to select a horizon after seeing
outcomes, refuses to read the holdout, refuses to count 86,301 correlated rows
as 86,301 experiments.
"""
import json
import math

import pytest

from intent_engine.market import competition as COMP
from intent_engine.market import costs as C
from intent_engine.market import experiments as EX
from intent_engine.market import horizons as H
from intent_engine.market import replay as RP
from intent_engine.market import strategy as ST
from intent_engine.market import strategy_library as LIB
from intent_engine.market import throughput as TP
from intent_engine.market import universe_tiers as UT


# ===========================================================================
# COSTS
# ===========================================================================
def test_costs_are_subtracted_from_every_return():
    assert C.DEFAULT.round_trip_bps == 10.0
    assert C.DEFAULT.net_return(0.0) == pytest.approx(-0.001)


def test_a_short_is_the_negation_of_the_price_move():
    """Getting this backwards produces a beautifully profitable strategy that
    is exactly wrong."""
    long_ = C.DEFAULT.apply(entry=100, exit_=110, direction="long")
    short = C.DEFAULT.apply(entry=100, exit_=110, direction="short")
    assert long_["gross_return"] == pytest.approx(0.1)
    assert short["gross_return"] == pytest.approx(-0.1)
    assert long_["net_return"] < long_["gross_return"]
    assert short["net_return"] < short["gross_return"]


def test_an_edge_smaller_than_costs_does_not_survive():
    assert not C.survives_costs(0.0005)      # 5 bps < 10 bps round trip
    assert C.survives_costs(0.002)


def test_the_cost_model_is_versioned():
    assert C.DEFAULT.version == "cost.v1"


# ===========================================================================
# UNIVERSE
# ===========================================================================
def test_tier_1_is_larger_than_the_evidence_universe_and_has_etfs():
    t0 = UT.universe_for(UT.TIER_0)
    t1 = UT.universe_for(UT.TIER_1)
    assert len(t1) > len(t0) > 20
    kinds = {s.security_type for s in t1}
    assert UT.SECTOR_ETF in kinds and UT.BROAD_ETF in kinds


def test_tiers_are_cumulative_and_deduplicated():
    """SHOP is in both universes; counting it twice would inflate every
    denominator."""
    t1 = UT.universe_for(UT.TIER_1)
    symbols = [s.symbol for s in t1]
    assert len(symbols) == len(set(symbols))


def test_an_unpopulated_tier_is_reported_never_substituted():
    with pytest.raises(UT.UniverseError) as exc:
        UT.universe_for(UT.TIER_2)
    assert "not populated" in str(exc.value)


@pytest.mark.parametrize("bad", ["leveraged_etf", "inverse_etf", "warrant",
                                 "right"])
def test_unsupported_security_types_are_refused_with_a_reason(bad):
    with pytest.raises(UT.UniverseError) as exc:
        UT.Security(symbol="X", security_type=bad)
    assert UT.UNSUPPORTED_TYPES[bad][:20] in str(exc.value)


# --- survivorship ----------------------------------------------------------
def test_a_delisted_security_is_retained_not_dropped():
    """Running today's symbol list across ten years is the classic way to
    manufacture a backtest."""
    t1 = UT.universe_for(UT.TIER_1)
    delisted = [s for s in t1 if s.is_delisted]
    assert delisted, "the universe must retain known failures"
    assert {"SIVB", "FRC"} <= {s.symbol for s in delisted}
    for s in delisted:
        assert s.delisting_reason


def test_a_failed_bank_is_still_eligible_before_it_failed():
    """THE survivorship test. SIVB must be in the sample for every date before
    2023-03-17 and out of it after."""
    sivb = [s for s in UT.universe_for(UT.TIER_1) if s.symbol == "SIVB"][0]
    assert sivb.eligible_on("2022-06-01")
    assert sivb.eligible_on("2023-03-16")
    assert not sivb.eligible_on("2023-06-01")


def test_a_security_is_not_eligible_before_it_listed():
    s = UT.Security(symbol="NEW", security_type=UT.EQUITY,
                    listed_at="2021-01-01")
    assert not s.eligible_on("2019-05-05")
    assert s.eligible_on("2021-06-01")


def test_the_survivorship_limitation_is_stated_in_every_composition():
    comp = UT.composition(UT.universe_for(UT.TIER_1))
    assert "survivorship" in comp["survivorship_limitation"].lower()
    assert comp["delisted_retained"] >= 2


def test_eligibility_rules_return_reasons_not_a_boolean():
    fails = UT.check_eligibility(symbol="X", price=2.0,
                                 median_dollar_volume=1e3, history_days=10,
                                 missing_rate=0.5)
    assert "price_below_5.0" in fails
    assert "illiquid" in fails
    assert "insufficient_history" in fails
    assert "excessive_missing_data" in fails
    assert UT.check_eligibility(symbol="X", price=100.0,
                                median_dollar_volume=1e9, history_days=900,
                                missing_rate=0.0) == []


def test_tier_promotion_is_measured_not_assumed():
    bad = UT.check_promotion(UT.TIER_1, {"data_completeness": 0.5,
                                         "integrity_failures": 3})
    assert not bad.promoted
    good = UT.check_promotion(UT.TIER_1, {
        "data_completeness": 0.99, "source_success_rate": 0.99,
        "max_cycle_seconds": 600, "integrity_failures": 0,
        "min_effective_observations": 500})
    assert good.promoted


def test_an_unmeasured_promotion_criterion_fails_rather_than_passes():
    check = UT.check_promotion(UT.TIER_1, {})
    assert not check.promoted
    assert all("UNMEASURED" in f for f in check.failed)


# ===========================================================================
# HORIZONS
# ===========================================================================
def test_trading_days_skip_weekends():
    """A 5-day horizon is five SESSIONS. Calendar counting would silently
    shorten every horizon spanning a weekend."""
    # 2026-07-31 is a Friday
    assert H.trading_days_after("2026-07-31", 1) == "2026-08-03"   # Monday
    assert H.trading_days_after("2026-07-31", 5) == "2026-08-07"


def test_trading_days_skip_holidays():
    # 2026-07-03 is the observed Independence Day holiday
    assert H.trading_days_after("2026-07-02", 1) == "2026-07-06"


def test_a_strategy_cannot_use_a_horizon_it_did_not_preregister():
    hs = H.HorizonSet("s.v1", (5, 10), "2026-08-01")
    assert hs.assert_preregistered(5) == 5
    with pytest.raises(H.HorizonError) as exc:
        hs.assert_preregistered(60)
    assert "hindsight" in str(exc.value)


def test_the_best_horizon_is_never_selected_after_the_outcome():
    """The most natural thing in the world to do, and it is hindsight."""
    results = [{"horizon": 5, "net": -0.01}, {"horizon": 20, "net": 0.04}]
    out = H.best_horizon_is_not_a_decision(results)
    assert out["selected"] is None
    assert out["correlated"] is True
    assert "hindsight" in out["reason"]


def test_horizons_of_one_entry_share_a_cluster_key():
    """Six horizons of one decision are one decision."""
    a = H.horizon_cluster_key("AAPL", "2026-07-31")
    b = H.horizon_cluster_key("AAPL", "2026-07-31")
    assert a == b
    assert a != H.horizon_cluster_key("MSFT", "2026-07-31")


def test_an_unsupported_horizon_is_rejected():
    with pytest.raises(H.HorizonError):
        H.HorizonSet("s.v1", (7,), "2026-08-01")
    with pytest.raises(H.HorizonError):
        H.HorizonSet("s.v1", (), "2026-08-01")


# ===========================================================================
# STRATEGIES
# ===========================================================================
def _series(n=80, start=100.0, step=0.0, start_date="2026-01-01"):
    from datetime import date, timedelta
    d = date.fromisoformat(start_date)
    return {(d + timedelta(days=i)).isoformat(): start + step * i
            for i in range(n)}


@pytest.mark.parametrize("name,fn", sorted(LIB.SIGNALS.items()))
def test_no_signal_can_see_the_future(name, fn):
    """THE property that makes every replay result mean anything."""
    past = _series(80, 100.0, 0.5)
    future = dict(past)
    future.update(_series(40, 9999.0, -50.0, "2026-06-01"))
    as_of = "2026-03-01"
    assert fn(past, security="X", as_of=as_of).as_dict() == \
        fn(future, security="X", as_of=as_of).as_dict()


@pytest.mark.parametrize("name,fn", sorted(LIB.SIGNALS.items()))
def test_every_signal_is_deterministic(name, fn):
    s = _series(80, 100.0, 0.4)
    assert fn(s, security="X", as_of="2026-03-01").as_dict() == \
        fn(s, security="X", as_of="2026-03-01").as_dict()


@pytest.mark.parametrize("name,fn", sorted(LIB.SIGNALS.items()))
def test_every_signal_refuses_on_missing_data(name, fn):
    assert not fn({}, security="X", as_of="2026-03-01").fired
    assert not fn(_series(5), security="X", as_of="2026-03-01").fired


def test_momentum_and_mean_reversion_disagree_by_construction():
    """If they agreed they would be one strategy under two names, and the
    overlap machinery would be measuring a re-parameterisation."""
    rising = _series(60, 100.0, 1.0)
    as_of = sorted(rising)[-1]
    mom = LIB.baseline_momentum(rising, security="X", as_of=as_of)
    rev = LIB.mean_reversion(rising, security="X", as_of=as_of)
    if mom.fired and rev.fired:
        assert mom.direction != rev.direction


def test_breakout_requires_clearing_the_range_not_touching_it():
    flat = _series(40, 100.0, 0.0)
    as_of = sorted(flat)[-1]
    assert not LIB.volatility_breakout(flat, security="X",
                                       as_of=as_of).fired


def test_refused_strategies_are_recorded_as_findings_not_omitted():
    assert set(LIB.REFUSED) == {"earnings_revision", "sector_relative_strength"}
    for name, row in LIB.REFUSED.items():
        assert row["passed"] is False
        assert row["gate"] == "GATE_1_DATA_AVAILABILITY"
        assert "lookahead" in row["reason"] or "point-in-time" in row["reason"]


def test_every_spec_declares_horizons_and_an_economic_hypothesis():
    for spec in LIB.specs():
        assert spec.horizons.horizons
        assert len(spec.economic_hypothesis) > 40
        assert spec.retirement_rules
        assert spec.cost_model.round_trip_bps > 0


# ===========================================================================
# REGISTRY / ISOLATION / LIFECYCLE
# ===========================================================================
@pytest.fixture
def registry(tmp_path):
    return ST.StrategyRegistry(tmp_path / "strategies.jsonl")


def _spec(sid="s", version="v1"):
    return ST.StrategySpec(
        strategy_id=sid, family="f", version=version,
        economic_hypothesis="h" * 50, required_data=("daily_closes",),
        signal_direction="long_short", thresholds={"a": 1},
        entry_timing="close", exit_timing="close",
        horizons=H.HorizonSet(f"{sid}.{version}", (5,), "2026-08-01"),
        invalidation="none", universe_tier=UT.TIER_1)


def test_a_registered_strategy_starts_at_research(registry):
    registry.register(_spec())
    assert registry.state_of("s.v1") == ST.RESEARCH


def test_registering_the_same_version_twice_is_refused(registry):
    registry.register(_spec())
    with pytest.raises(ST.StrategyError):
        registry.register(_spec())


def test_a_live_strategy_specification_is_frozen(registry):
    spec = registry.register(_spec())
    registry.transition("s.v1", ST.REPLAY_ELIGIBLE, "replay ok")
    registry.transition("s.v1", ST.PAPER_CHALLENGER, "gates passed")
    with pytest.raises(ST.StrategyError) as exc:
        spec.thresholds = {"a": 999}
    assert "frozen" in str(exc.value)


def test_a_retired_strategy_is_never_reactivated(registry):
    registry.register(_spec())
    registry.transition("s.v1", ST.RETIRED, "no edge")
    with pytest.raises(ST.StrategyError) as exc:
        registry.transition("s.v1", ST.PAPER_CHALLENGER, "second thoughts")
    assert "never reactivated" in str(exc.value)


def test_illegal_transitions_are_refused(registry):
    registry.register(_spec())
    with pytest.raises(ST.StrategyError):
        registry.transition("s.v1", ST.PAPER_CHAMPION, "skip the queue")


def test_a_transition_must_state_a_reason(registry):
    registry.register(_spec())
    with pytest.raises(ST.StrategyError):
        registry.transition("s.v1", ST.REPLAY_ELIGIBLE, "")


def test_a_challenger_requires_every_gate(registry):
    registry.register(_spec())
    registry.transition("s.v1", ST.REPLAY_ELIGIBLE, "ok")
    gates = {g: {"passed": True} for g in ST.GATES}
    gates["GATE_5_COST_ROBUSTNESS"] = {"passed": False,
                                       "reason": "edge below costs"}
    with pytest.raises(ST.StrategyError) as exc:
        registry.qualify_challenger("s.v1", gates)
    assert "GATE_5_COST_ROBUSTNESS" in str(exc.value)


def test_lifecycle_history_is_append_only(registry):
    registry.register(_spec())
    registry.transition("s.v1", ST.REPLAY_ELIGIBLE, "a")
    registry.transition("s.v1", ST.UNDER_REVIEW, "b")
    states = [e["state"] for e in registry.history("s.v1")]
    assert states == [ST.RESEARCH, ST.REPLAY_ELIGIBLE, ST.UNDER_REVIEW]


def test_strategy_books_are_isolated():
    a = ST.StrategyBook("a.v1")
    b = ST.StrategyBook("b.v1")
    a.record(security="X", as_of="2026-01-01", net_return=0.01)
    b.record(security="X", as_of="2026-01-01", net_return=-0.01)
    ST.assert_isolated([a, b])
    a.observations.append({"strategy_key": "b.v1", "net_return": 9.0})
    with pytest.raises(ST.IsolationError):
        ST.assert_isolated([a, b])


def test_overlap_detects_two_strategies_running_the_same_experiment():
    a, b = ST.StrategyBook("a.v1"), ST.StrategyBook("b.v1")
    for book in (a, b):
        book.record(security="AAPL", as_of="2026-01-05", net_return=0.0)
    same = ST.overlap(a, b)
    assert same["shared_decisions"] == 1
    assert same["independent"] is False

    c = ST.StrategyBook("c.v1")
    c.record(security="MSFT", as_of="2026-02-02", net_return=0.0)
    assert ST.overlap(a, c)["independent"] is True


# ===========================================================================
# EFFECTIVE SAMPLE SIZE
# ===========================================================================
def _obs(security, as_of, horizon, resolved_at, sector="Tech", net=0.001):
    return {"security": security, "as_of": as_of, "horizon": horizon,
            "resolved_at": resolved_at, "sector": sector, "net_return": net}


def test_six_horizons_of_one_entry_are_not_six_experiments():
    obs = [_obs("AAPL", "2026-01-05", h, "2026-02-05") for h in (1, 3, 5, 10)]
    sample = EX.effective_sample(obs)
    assert sample.n_raw == 4
    assert sample.n_effective == 1
    assert sample.design_effect == 4.0


def test_overlapping_windows_within_one_security_collapse():
    obs = [_obs("AAPL", f"2026-01-{d:02d}", 20, f"2026-02-{d:02d}")
           for d in range(5, 15)]
    sample = EX.effective_sample(obs)
    assert sample.n_raw == 10
    assert sample.n_effective < 10


def test_different_securities_are_not_collapsed_into_one_window():
    """The bug the pilot found: pooling every security's windows made the union
    one continuous interval and n_eff came back as 1."""
    obs = [_obs(sym, "2026-01-05", 20, "2026-02-05", sector=sec)
           for sym, sec in (("AAPL", "Tech"), ("XOM", "Energy"),
                            ("JPM", "Fin"), ("PG", "Staples"))]
    sample = EX.effective_sample(obs)
    assert sample.n_effective > 1, "distinct securities are distinct evidence"


def test_effective_is_the_minimum_dimension_not_a_blend():
    obs = [_obs("AAPL", f"2026-0{m}-05", 5, f"2026-0{m}-12")
           for m in range(1, 8)]
    sample = EX.effective_sample(obs)
    assert sample.n_effective == min(sample.n_by_dimension.values())
    assert sample.binding in sample.n_by_dimension


def test_no_observations_is_zero_not_an_error():
    s = EX.effective_sample([])
    assert s.n_raw == 0 and s.n_effective == 0


# ===========================================================================
# SIGNIFICANCE + FDR
# ===========================================================================
def test_a_claim_below_the_effective_floor_is_unmeasurable():
    sample = EX.EffectiveSample(5000, {"security": 5}, 5, "security")
    result = EX.test_edge("s", [0.01] * 50 + [-0.005] * 50, sample)
    assert not result.measurable
    assert "UNMEASURABLE" in result.reason
    assert result.p_value is None


def test_significance_uses_effective_not_raw_n():
    """Using n_raw here is the most common way a backtest manufactures
    significance."""
    values = [0.001 + (0.02 if i % 2 else -0.02) for i in range(4000)]
    big = EX.test_edge("s", values,
                       EX.EffectiveSample(4000, {"security": 4000}, 4000, "s"))
    small = EX.test_edge("s", values,
                         EX.EffectiveSample(4000, {"security": 40}, 40, "s"))
    assert big.p_value < small.p_value


def test_benjamini_hochberg_rejects_when_nothing_is_significant():
    tests = [EX.TestResult(f"t{i}", 0.0001, 1000, 100, 0.02, 0.5, 0.6, True)
             for i in range(7)]
    out = EX.benjamini_hochberg(tests)
    assert out["discoveries"] == []
    assert out["tests"] == 7
    assert "no strategy survives" in out["note"]


def test_benjamini_hochberg_finds_a_real_effect():
    tests = [EX.TestResult("real", 0.05, 1000, 100, 0.02, 9.0, 1e-9, True)]
    tests += [EX.TestResult(f"n{i}", 0.0, 1000, 100, 0.02, 0.1, 0.9, True)
              for i in range(5)]
    out = EX.benjamini_hochberg(tests)
    assert "real" in out["discoveries"]


def test_unmeasurable_tests_do_not_inflate_the_fdr_denominator():
    tests = [EX.TestResult("a", 0.0, 10, 3, 0.01, None, None, False, "small"),
             EX.TestResult("b", 0.05, 1000, 100, 0.02, 9.0, 1e-9, True)]
    assert EX.benjamini_hochberg(tests)["tests"] == 1


def test_the_experiment_registry_only_grows(tmp_path):
    reg = EX.ExperimentRegistry(tmp_path / "e.jsonl")
    for i in range(3):
        reg.record(EX.Experiment(f"e{i}", "now", "s.v1", 5, "research", 1, 10,
                                 100, 20, 0.0, 0.5, True))
    assert reg.count()["experiments_total"] == 3
    reg2 = EX.ExperimentRegistry(tmp_path / "e.jsonl")
    assert reg2.count()["experiments_total"] == 3


# --- holdout ---------------------------------------------------------------
def test_the_holdout_cannot_be_read_by_a_research_run():
    with pytest.raises(EX.HoldoutViolation):
        EX.assert_not_holdout("research", "2025-06-01")
    with pytest.raises(EX.HoldoutViolation):
        EX.assert_not_holdout("validation", "2026-01-01")
    EX.assert_not_holdout("research", "2022-12-31")     # fine


# ===========================================================================
# REPLAY
# ===========================================================================
def _sec(symbol="AAPL", sector="Tech", **kw):
    return UT.Security(symbol=symbol, security_type=UT.EQUITY, sector=sector,
                       **kw)


def _rising(n=120, start="2022-01-03"):
    from datetime import date, timedelta
    d = date.fromisoformat(start)
    out, day = {}, d
    i = 0
    while len(out) < n:
        if day.weekday() < 5:
            out[day.isoformat()] = 100.0 + i * 0.7
            i += 1
        day += timedelta(days=1)
    return out


def test_replay_is_deterministic_and_id_stable():
    assert RP.job_id("s.v1", 1, "2020-01-01", "2020-12-31", "research") == \
        RP.job_id("s.v1", 1, "2020-01-01", "2020-12-31", "research")


def test_replay_produces_net_returns_with_costs(tmp_path):
    closes = _rising()
    out = RP.run_replay(
        strategy_key="baseline_momentum.v1", signal_fn=LIB.baseline_momentum,
        horizons=(5,), securities=[_sec()], series_for=lambda s: closes,
        start="2022-01-01", end="2022-06-30", window="research", tier=1,
        root=str(tmp_path))
    assert out.observations
    for o in out.observations:
        assert o["net_return"] < o["gross_return"]
        assert o["cost_model"] == "cost.v1"


def test_replay_refuses_the_holdout(tmp_path):
    with pytest.raises(EX.HoldoutViolation):
        RP.run_replay(
            strategy_key="s", signal_fn=LIB.baseline_momentum, horizons=(5,),
            securities=[_sec()], series_for=lambda s: _rising(),
            start="2025-01-01", end="2025-12-31", window="research", tier=1,
            root=str(tmp_path))


def test_replay_respects_the_budget_and_stays_resumable(tmp_path):
    out = RP.run_replay(
        strategy_key="s", signal_fn=LIB.baseline_momentum, horizons=(5,),
        securities=[_sec()], series_for=lambda s: _rising(400),
        start="2022-01-01", end="2023-12-31", window="research", tier=1,
        budget=RP.Budget(max_observations=5), root=str(tmp_path))
    assert out.status == "exhausted_budget"
    assert out.resumable
    assert len(out.observations) <= 6


def test_a_resumed_replay_does_not_duplicate_work(tmp_path):
    kw = dict(strategy_key="s", signal_fn=LIB.baseline_momentum, horizons=(5,),
              securities=[_sec()], series_for=lambda s: _rising(),
              start="2022-01-01", end="2022-06-30", window="research", tier=1,
              root=str(tmp_path))
    first = RP.run_replay(**kw)
    second = RP.run_replay(**kw)
    assert first.observations
    assert second.observations == []
    assert second.skipped.get("already_done", 0) > 0


def test_replay_skips_dates_outside_the_listing_window(tmp_path):
    """A delisted name stays in the sample up to its delisting and not after."""
    failed = _sec("SIVB", "Fin", delisted_at="2022-03-01",
                  delisting_reason="failure")
    out = RP.run_replay(
        strategy_key="s", signal_fn=LIB.baseline_momentum, horizons=(5,),
        securities=[failed], series_for=lambda s: _rising(),
        start="2022-01-01", end="2022-06-30", window="research", tier=1,
        root=str(tmp_path))
    assert out.skipped.get("outside_listing_window", 0) > 0
    assert all(o["as_of"] <= "2022-03-01" for o in out.observations)


def test_a_missing_exit_price_is_unresolved_never_filled(tmp_path):
    closes = _rising(60)
    out = RP.run_replay(
        strategy_key="s", signal_fn=LIB.baseline_momentum, horizons=(60,),
        securities=[_sec()], series_for=lambda s: closes,
        start="2022-01-01", end="2022-03-31", window="research", tier=1,
        root=str(tmp_path))
    assert out.skipped.get("unresolved_horizon", 0) > 0


def test_replay_isolates_a_dead_price_source(tmp_path):
    def dead(_s):
        return {}
    out = RP.run_replay(
        strategy_key="s", signal_fn=LIB.baseline_momentum, horizons=(5,),
        securities=[_sec(), _sec("MSFT")], series_for=dead,
        start="2022-01-01", end="2022-06-30", window="research", tier=1,
        root=str(tmp_path))
    assert out.status == "completed"
    assert out.skipped["no_price_data"] == 2


# ===========================================================================
# COMPETITION
# ===========================================================================
def _perf(key, mean, n_eff, n_raw=1000, interval=None):
    return COMP.Performance(key, "REPLAY_ELIGIBLE", n_raw, n_eff, None, 0.5,
                            mean, 1.0, 0.1, 0.1, -0.1, 10, mean, 0.5,
                            interval, n_eff >= 30)


def test_a_leaderboard_refuses_to_rank_on_overlapping_intervals():
    board = COMP.leaderboard([_perf("a", 0.001, 50, interval=(-0.01, 0.012)),
                              _perf("b", 0.0005, 50, interval=(-0.01, 0.011))])
    assert board["ranked"] is False
    assert "overlap" in board["reason"]


def test_a_leaderboard_ranks_only_on_a_clear_separation():
    board = COMP.leaderboard([_perf("a", 0.05, 50, interval=(0.04, 0.06)),
                              _perf("b", 0.001, 50, interval=(-0.001, 0.002))])
    assert board["ranked"] is True


def test_strategies_without_evidence_are_unmeasurable_not_last():
    board = COMP.leaderboard([_perf("a", 0.01, 5), _perf("b", 0.02, 3)])
    assert board["measurable"] == 0
    assert board["ranked"] is False
    assert all(not r["measurable"] for r in board["rows"])


def test_trade_count_never_promotes_a_strategy():
    perfs = [_perf("high_freq", -0.002, 50, n_raw=90000),
             _perf("low_freq", 0.001, 50, n_raw=200),
             _perf("mid", 0.0005, 50, n_raw=1000)]
    check = COMP.no_promotion_on_trade_count(perfs)
    assert check["checked"]
    assert "never promotes" in check["rule"]
    board = COMP.leaderboard(perfs)
    assert board["rows"][0]["strategy_key"] != "high_freq"


def test_no_fdr_survivor_means_no_challenger():
    board = COMP.leaderboard([_perf("a", 0.001, 50)],
                             {"discoveries": [], "tests": 7})
    assert board["surviving_fdr"] == []
    assert "no strategy survives" in board["note"]


def test_retirement_fires_only_on_measurable_evidence():
    weak = _perf("a", -0.002, 5)          # not measurable
    assert COMP.retirement_check(weak, ("rule",)) is None
    strong = _perf("a", -0.002, 100)
    out = COMP.retirement_check(strong, ("negative expectancy",))
    assert out and out["state"] == ST.UNDER_REVIEW


def test_metrics_needing_independence_are_withheld_below_the_floor():
    sample = EX.EffectiveSample(1000, {"security": 4}, 4, "security")
    test = EX.test_edge("s", [0.01, -0.01] * 50, sample)
    perf = COMP.evaluate("s.v1", "RESEARCH",
                         [_obs("A", "2026-01-01", 5, "2026-01-08")], sample,
                         test)
    assert perf.sharpe is None and perf.sortino is None
    assert not perf.measurable


# ===========================================================================
# LEARNING THROUGHPUT
# ===========================================================================
def test_throughput_is_zero_when_nothing_was_learned():
    t = TP.LearningThroughput()
    assert t.score == 0
    assert "NO NEW KNOWLEDGE" in t.render()


def test_weakened_assets_reduce_throughput():
    assert TP.LearningThroughput(assets_weakened=2).score == -2
    assert TP.LearningThroughput(resolved_effective=3,
                                 assets_weakened=1).score == 2


def test_raw_observations_do_not_raise_throughput():
    """A metric that counted rows would rise every time a threshold loosened."""
    a = TP.LearningThroughput(resolved_raw=100000, resolved_effective=10)
    b = TP.LearningThroughput(resolved_raw=10, resolved_effective=10)
    assert a.score == b.score
    assert a.design_effect == 10000.0


def test_live_and_replay_learning_are_reported_separately():
    live = TP.LiveLearningRate(securities_evaluated=28, positions_opened=0)
    assert "never averaged" in live.as_dict()["note"]


def test_the_limiting_factor_names_the_live_gate_when_replay_works():
    out = TP.limiting_factor(TP.LiveLearningRate(positions_opened=0),
                             TP.LearningThroughput(resolved_effective=77))
    assert out["factor"] == "live path produces no positions"
    assert "not by universe size" in out["detail"]


def test_the_limiting_factor_reports_dependence_when_it_dominates():
    out = TP.limiting_factor(TP.LiveLearningRate(positions_opened=1),
                             TP.LearningThroughput(resolved_raw=100000,
                                                   resolved_effective=77))
    assert out["factor"] == "observation dependence"


# ===========================================================================
# SAFETY
# ===========================================================================
def test_no_brokerage_code_was_added():
    """The boundary this whole project rests on, re-asserted over the new
    modules."""
    import inspect

    from intent_engine.market import (competition, costs, experiments, replay,
                                      strategy, strategy_library, throughput,
                                      universe_tiers)
    forbidden = ("alpaca", "interactive_brokers", "ibkr", "submit_order",
                 "place_order", "broker_connect", "api_secret", "live_trade",
                 "account_funding")
    for module in (competition, costs, experiments, replay, strategy,
                   strategy_library, throughput, universe_tiers):
        src = inspect.getsource(module).lower()
        for word in forbidden:
            assert word not in src, f"{module.__name__} references {word}"


def test_paper_mode_is_still_enforced_and_fails_closed():
    from intent_engine.market import trading_mode as TM
    assert TM.resolve({})["mode"] == "PAPER"
    with pytest.raises(TM.TradingModeError):
        TM.resolve({"TRADING_MODE": "LIVE"})


def test_the_narrative_gates_are_untouched_for_fundamental_claims():
    """The price path adds a route; it removes nothing. A customer-adoption
    claim still needs customer or industry evidence."""
    from intent_engine.market.corroboration import REQUIREMENTS
    assert REQUIREMENTS["customer_adoption"].required
    assert REQUIREMENTS["governance"].required
    assert REQUIREMENTS["macro_sensitivity"].required
    # and price_behaviour still requires none -- unchanged since day 11
    assert REQUIREMENTS["price_behaviour"].required == frozenset()

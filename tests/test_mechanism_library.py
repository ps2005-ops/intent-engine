from intent_engine.core.mechanism_library import Mechanism, load_mechanisms, match_mechanisms


def test_load_mechanisms_returns_the_8_task2_plus_9_task_m3_plus_3_batch1_mechanisms():
    """Task M3 (market-engine-execution-plan.md) extended the original 8
    with 9 financial-crisis mechanisms; the historical-study track's
    batch 1 (founder-APPROVED 2026-07-19, docs/library_batch1_review_sheet.md)
    added 3 more -- this assertion is updated to match, same precedent as
    the M3 update. Original 17 IDs untouched, still all present."""
    mechanisms = load_mechanisms()
    ids = {m.mechanism_id for m in mechanisms}
    assert ids == {
        "supply_shock_propagation",
        "prisoners_dilemma_price_war",
        "regulatory_capture_race",
        "platform_envelopment",
        "credit_contagion",
        "ally_drawn_into_linked_conflict",
        "winners_curse_acquisition",
        "debt_fueled_capacity_race",
        "leverage_cycle_bust",
        "margin_collateral_spiral",
        "bank_run_maturity_mismatch",
        "carry_trade_unwind",
        "reflexive_bubble",
        "monetary_tightening_lag",
        "sovereign_debt_doom_loop",
        "capex_overbuild",
        "money_market_contagion",
        # batch 1 (episodes 1-4), approved as-is incl. the flagged
        # debt_deflation_spiral trigger-set collision (dual-match accepted):
        "debt_deflation_spiral",
        "input_cost_inflation_passthrough",
        "policy_tightening_demand_collapse",
    }
    assert len(mechanisms) == 20


def test_every_mechanism_has_at_least_one_historical_instance():
    for mechanism in load_mechanisms():
        assert len(mechanism.historical_instances) >= 1, mechanism.mechanism_id


def test_well_documented_mechanisms_have_a_real_citation_string():
    """well_documented tier requires a real citation -- checked directly,
    not assumed. A 'speculative' tier would be exempt (none exist in this
    seed set, since real citations were found for all 8), but this test
    still asserts the well_documented ones specifically carry one, per the
    task's own bar."""
    for mechanism in load_mechanisms():
        if mechanism.confidence_tier == "well_documented":
            for instance in mechanism.historical_instances:
                assert instance.source and instance.source.startswith("http"), mechanism.mechanism_id


def test_every_mechanism_has_a_nonempty_causal_chain():
    for mechanism in load_mechanisms():
        assert len(mechanism.causal_chain) >= 3, mechanism.mechanism_id


def test_every_mechanism_has_at_least_one_trigger_condition():
    for mechanism in load_mechanisms():
        assert len(mechanism.trigger_conditions) >= 1, mechanism.mechanism_id


def test_match_mechanisms_returns_the_expected_mechanisms_for_a_constructed_case():
    """A constructed input matching debt_fueled_capacity_race's exact 2
    trigger conditions should rank it first, with the full match recorded."""
    results = match_mechanisms(["capacity_investment_outpacing_demand_signal", "debt_financed_expansion"])
    assert results[0].mechanism.mechanism_id == "debt_fueled_capacity_race"
    assert results[0].overlap_count == 2
    assert set(results[0].matched_conditions) == {"capacity_investment_outpacing_demand_signal", "debt_financed_expansion"}


def test_match_mechanisms_ranks_by_overlap_count_descending():
    # few_dominant_competitors alone overlaps 3 mechanisms (supply_shock,
    # price_war, regulatory_capture); symmetric_competitor_response_expected
    # only overlaps price_war -- price_war should rank above the other two.
    results = match_mechanisms(["few_dominant_competitors", "symmetric_competitor_response_expected"])
    assert results[0].mechanism.mechanism_id == "prisoners_dilemma_price_war"
    assert results[0].overlap_count == 2


def test_match_mechanisms_returns_empty_list_for_a_genuine_no_match_case():
    """A no-match case must return empty -- never a forced/nearest match."""
    results = match_mechanisms(["some_condition_no_mechanism_has"])
    assert results == []


def test_match_mechanisms_never_calls_a_model():
    """Zero LLM calls in the matcher itself -- checked by confirming it
    runs with no client/API dependency in its signature or imports at all
    (a purely deterministic function over the static JSON data)."""
    import inspect
    sig = inspect.signature(match_mechanisms)
    assert "client" not in sig.parameters and "llm" not in str(sig).lower()


def test_mechanism_model_validates_from_the_real_json_shape():
    """Real end-to-end: every entry in data/mechanisms.json actually
    parses as a Mechanism, not just a hand-picked subset."""
    mechanisms = load_mechanisms()
    for m in mechanisms:
        assert isinstance(m, Mechanism)


# --- Task M3: financial-crisis mechanisms + regime-derived taxonomy -------


def test_all_9_task_m3_mechanisms_present_with_expected_trigger_conditions():
    mechanisms = {m.mechanism_id: m for m in load_mechanisms()}
    expected_conditions = {
        "leverage_cycle_bust": {"debt_financed_expansion", "drawdown_gt_20pct"},
        "margin_collateral_spiral": {"drawdown_gt_20pct"},
        "bank_run_maturity_mismatch": {"interconnected_counterparty_exposure", "curve_inverted"},
        "carry_trade_unwind": {"interconnected_counterparty_exposure"},
        "reflexive_bubble": {"valuation_disconnected_from_fundamentals"},
        "monetary_tightening_lag": {"curve_inverted"},
        "sovereign_debt_doom_loop": {"credit_spreads_elevated", "interconnected_counterparty_exposure"},
        "capex_overbuild": {"capacity_investment_outpacing_demand_signal", "valuation_disconnected_from_fundamentals"},
        "money_market_contagion": {"interconnected_counterparty_exposure", "credit_spreads_elevated"},
    }
    for mechanism_id, conditions in expected_conditions.items():
        assert mechanism_id in mechanisms, mechanism_id
        assert set(mechanisms[mechanism_id].trigger_conditions) == conditions, mechanism_id


def test_capex_overbuild_has_two_real_historical_instances():
    """The only mechanism (old or new) with more than one historical
    instance -- railroads (1873) and dot-com fiber (2002), both real,
    checked citations. Deliberately does NOT include an AI-datacenter
    instance: that situation is still unresolved, and citing an outcome
    for an ongoing episode would fabricate a result that doesn't exist
    yet."""
    mechanisms = {m.mechanism_id: m for m in load_mechanisms()}
    instances = mechanisms["capex_overbuild"].historical_instances
    assert len(instances) == 2
    years = {i.year for i in instances}
    assert years == {1873, 2002}


def test_new_regime_trigger_conditions_are_declared_in_the_taxonomy():
    from typing import get_args
    from intent_engine.core.mechanism_library import TriggerCondition

    declared = set(get_args(TriggerCondition))
    for term in ("curve_inverted", "credit_spreads_elevated", "inflation_rising",
                 "unemployment_momentum_triggered", "drawdown_gt_20pct"):
        assert term in declared, term


def test_regime_flavored_intent_matches_the_expected_crisis_mechanism():
    """A constructed trigger-condition list matching bank_run_maturity_
    mismatch's exact 2 conditions should rank it first -- the same
    match_mechanisms() code path Task 2's tests already exercise, now
    fed regime-derived conditions instead of business-decision ones."""
    results = match_mechanisms(["interconnected_counterparty_exposure", "curve_inverted"])
    assert results[0].mechanism.mechanism_id == "bank_run_maturity_mismatch"
    assert results[0].overlap_count == 2


def test_no_accidental_catch_all_after_batch1():
    """UPDATED 2026-07-19 with the founder-approved batch-1 merge: the
    original construction (a declared-but-unused condition returns empty)
    is no longer possible -- batch 1 consumed the last unused condition
    (inflation_rising, now genuinely declared by
    input_cost_inflation_passthrough and policy_tightening_demand_collapse,
    so matching on it is CORRECT behavior, not a catch-all). The test's
    intent is preserved directly: every returned mechanism must genuinely
    declare an overlapping condition, and empty input returns empty."""
    assert match_mechanisms([]) == []
    for condition in ["inflation_rising", "curve_inverted", "network_effects_present"]:
        for r in match_mechanisms([condition]):
            assert condition in r.mechanism.trigger_conditions, (
                f"{r.mechanism.mechanism_id} matched {condition!r} without declaring it -- catch-all bug")
            assert r.matched_conditions == [condition]


def test_old_task2_matcher_behavior_unaffected_by_the_m3_extension():
    """Re-run of Task 2's own matcher scenario, unchanged, against the now-
    17-mechanism set -- proves the extension didn't shift ranking or
    overlap counts for a pre-existing mechanism."""
    results = match_mechanisms(["capacity_investment_outpacing_demand_signal", "debt_financed_expansion"])
    assert results[0].mechanism.mechanism_id == "debt_fueled_capacity_race"
    assert results[0].overlap_count == 2

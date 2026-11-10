"""The forward evidence engine and the economic world model.

Every test names the failure it prevents. The forward record is the only
evidence stream nobody can fit after the fact, and the machinery around it has
to be right BEFORE the first expectation comes due -- fixing a resolver on the
day the answer arrives destroys the property that makes the record worth
having.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import forward_engine as FE
from intent_engine.econ import forward_ledger as FL
from intent_engine.econ import panel as PN
from intent_engine.econ import worldmodel as WM


def _rec(**kw):
    base = {"expectation_id": "ex-t", "information_cutoff": "2026-01-01",
            "horizon_days": 180, "expires_at": "2026-06-30",
            "resolution_rule": "r", "confidence": 0.5, "quantity": "q",
            "expected_direction": "UP", "outcome": FE.OPEN}
    base.update(kw)
    return base


def _panel():
    p = PN.Panel()
    p.add(PN.Cell(series_id="X", observed_at="2020-01-01",
                  vintage_at="2020-02-01", value=50.0))
    p.add(PN.Cell(series_id="X", observed_at="2020-02-01",
                  vintage_at="2020-03-01", value=100.0))
    p.add(PN.Cell(series_id="X", observed_at="2020-02-01",
                  vintage_at="2020-09-01", value=200.0))
    return p.finalise()


def _con(policy):
    return FE.ResolutionContract(
        series_id="X", baseline_period="2020-01-01", direction="UP",
        horizon_days=30, vintage_policy=policy,
        resolves_from="2020-03-01").as_dict()


# =============================================================================
# §4/§5 THE STATE MACHINE AND THE RESOLVER
# =============================================================================

def test_nothing_resolves_before_its_horizon():
    p = _panel()
    r = _rec(resolution_contract=_con(FE.LATEST_REVISION),
             expires_at="2027-01-01")
    assert FE.state_of(r, at="2026-03-01", panel=p) == FE.OPEN
    assert FE.resolve_one(r, panel=p, at="2026-03-01") is None


def test_a_missing_publication_is_blocked_not_wrong():
    """'the publisher has not released' must never be recorded as 'we were
    wrong'."""
    p = _panel()
    r = _rec(resolution_contract=FE.ResolutionContract(
        series_id="ABSENT", baseline_period="2020-01-01", direction="UP",
        horizon_days=30, vintage_policy=FE.LATEST_REVISION,
        resolves_from="2020-03-01").as_dict(), expires_at="2020-03-01")
    assert FE.state_of(r, at="2020-04-01", panel=p) == FE.BLOCKED


def test_a_publication_that_never_arrives_expires_rather_than_vanishing():
    p = _panel()
    r = _rec(resolution_contract=FE.ResolutionContract(
        series_id="ABSENT", baseline_period="2020-01-01", direction="UP",
        horizon_days=30, vintage_policy=FE.LATEST_REVISION,
        resolves_from="2020-03-01").as_dict(), expires_at="2020-03-01")
    assert FE.state_of(r, at="2021-06-01", panel=p) == FE.EXPIRED


def test_a_first_release_contract_reads_the_first_print():
    """The forward twin of the leak that cost a whole panel: a prediction
    about what the world would PRINT is not answered by a later revision."""
    p = _panel()
    first = FE.ResolutionContract(**_con(FE.FIRST_RELEASE))
    latest = FE.ResolutionContract(**_con(FE.LATEST_REVISION))
    assert FE._readable(p, first, "2021-01-01") == 100.0
    assert FE._readable(p, latest, "2021-01-01") == 200.0


def test_a_resolved_expectation_is_terminal():
    FE.assert_transition(FE.ELIGIBLE, FE.RESOLVED)
    for bad in (FE.OPEN, FE.ELIGIBLE, FE.EXPIRED):
        with pytest.raises(FE.ResolutionRefused):
            FE.assert_transition(FE.RESOLVED, bad)


def test_resolution_scores_against_the_stated_direction():
    p = _panel()
    r = _rec(resolution_contract=_con(FE.LATEST_REVISION),
             expires_at="2020-03-01", confidence=0.8)
    got = FE.resolve_one(r, panel=p, at="2021-01-01")
    assert got["correct"] is True          # 200 > 50
    assert got["squared_error"] == pytest.approx((0.8 - 1.0) ** 2)
    assert got["outcome"] == FE.RESOLVED


# =============================================================================
# §7 THE FORWARD SAMPLE-QUALITY WALL
# =============================================================================

def test_twenty_predictions_from_one_origin_are_not_twenty_observations():
    recs = [_rec(expectation_id=f"e{i}", information_cutoff="2026-01-01")
            for i in range(20)]
    s = FE.forward_sample(recs)
    assert s.raw_predictions == 20
    assert s.unique_origins == 1
    for word in ("origins", "families", "episodes"):
        assert word in s.headline()


# =============================================================================
# §8 THE CALIBRATION LADDER
# =============================================================================

def test_unresolved_predictions_never_move_the_ladder():
    recs = [_rec(expectation_id=f"e{i}", family=f"f{i % 4}",
                 information_cutoff=f"2026-{i % 12 + 1:02d}-01")
            for i in range(50)]
    s = FE.ladder_stage(recs)
    assert s["stage"] == FE.PRE_CALIBRATION
    assert s["resolved"] == 0


def test_the_ladder_thresholds_were_fixed_before_any_resolution():
    for stage in (FE.EARLY_CALIBRATION, FE.CALIBRATION_ESTABLISHING,
                  FE.CALIBRATED):
        need = FE.LADDER_REQUIREMENTS[stage]
        for k in ("resolved", "origins", "families", "episodes", "reports"):
            assert k in need
    assert (FE.LADDER_REQUIREMENTS[FE.CALIBRATED]["resolved"]
            > FE.LADDER_REQUIREMENTS[FE.EARLY_CALIBRATION]["resolved"])


def test_a_ladder_rung_states_what_it_may_report():
    s = FE.ladder_stage([])
    assert "count" in s["may_report"].lower()
    assert s["stage"] == FE.PRE_CALIBRATION


# =============================================================================
# §6 THE TOURNAMENT
# =============================================================================

def test_a_tournament_with_no_resolved_pair_has_no_result():
    recs = [_rec(expectation_id="a", model="BASE", family="f"),
            _rec(expectation_id="b", model="AUGMENTED", family="f")]
    t = FE.tournament(recs)
    assert t["pairs"] == 1
    assert t["resolved_pairs"] == 0
    assert t["verdict"] == "AWAITING_RESOLUTION"
    assert "base" not in t


def test_only_matched_pairs_are_scored():
    recs = [_rec(expectation_id="a", model="BASE", family="f"),
            _rec(expectation_id="c", model="BASE", family="g")]
    t = FE.tournament(recs)
    assert t["pairs"] == 0
    assert t["unmatched"] == 2


# =============================================================================
# §11-§22 THE WORLD MODEL
# =============================================================================

def test_an_unmeasured_dimension_stays_in_the_denominator():
    a = WM.DimensionAudit(dimension="fx", producer="", source="",
                          frequency="", as_of="", freshness_days=None,
                          persisted=False, consumer=(), standing=WM.UNKNOWN)
    assert a.status == "BLOCKED"
    assert not a.live


def test_gaps_rank_by_decision_impact_not_by_ease():
    audit = {
        "positioning": WM.DimensionAudit(
            dimension="positioning", producer="", source="", frequency="",
            as_of="", freshness_days=None, persisted=False, consumer=(),
            standing=WM.UNKNOWN),
        "credit": WM.DimensionAudit(
            dimension="credit", producer="", source="", frequency="",
            as_of="", freshness_days=None, persisted=False, consumer=(),
            standing=WM.UNKNOWN)}
    ranked = WM.rank_gaps(audit)
    assert ranked[0]["dimension"] == "credit"


def test_a_transmission_path_refuses_a_broken_chain():
    a = WM.Relation(driver="A", effect="B", sign=1, mechanism="m",
                    lag_days=30, uncertainty="LOW", regime="ALL",
                    falsifier="f", evidence="e")
    c = WM.Relation(driver="C", effect="D", sign=1, mechanism="m",
                    lag_days=30, uncertainty="LOW", regime="ALL",
                    falsifier="f", evidence="e")
    with pytest.raises(WM.WorldModelDefect):
        WM.TransmissionPath(name="broken", shock="s", steps=(a, c))


def test_a_relation_that_cannot_be_wrong_is_refused():
    with pytest.raises(Exception):
        WM.Relation(driver="A", effect="B", sign=1, mechanism="m",
                    lag_days=30, uncertainty="LOW", regime="ALL",
                    falsifier="  ", evidence="e")


def test_a_bleed_is_a_candidate_and_may_not_be_rendered_as_a_cause():
    b = WM.Bleed(source="a", expected_target="b", expected_timing_days=30,
                 expected_direction="UP", actual_direction="DOWN",
                 transmission_gap=0.1, candidate_explanation="c",
                 evidence="e", uncertainty="HIGH", controllability="LOW",
                 decision_impact=3)
    assert b.as_dict()["status"] == "CANDIDATE_NOT_PROVEN"
    assert "NOT a demonstrated cause" in b.statement()
    WM.assert_bleed_not_proven(b.as_dict())
    with pytest.raises(WM.WorldModelDefect):
        WM.assert_bleed_not_proven({**b.as_dict(), "status": "PROVEN"})


def test_six_companies_may_not_share_one_channel():
    same = [WM.CompanyImplication(
        company_id=c, driver="d", channel="consumer demand", mechanism="m",
        direction="DOWN", magnitude="LOW", confidence=0.5, falsifier="f")
        for c in "abcdef"]
    with pytest.raises(WM.WorldModelDefect):
        WM.assert_company_specific(same)
    distinct = [WM.CompanyImplication(
        company_id=c, driver="d", channel=f"channel {c}", mechanism="m",
        direction="DOWN", magnitude="LOW", confidence=0.5, falsifier="f")
        for c in "abcdef"]
    r = WM.assert_company_specific(distinct)
    assert r["distinct_channels"] == 6


def test_an_implication_without_a_channel_is_refused():
    with pytest.raises(Exception):
        WM.CompanyImplication(
            company_id="c", driver="d", channel="  ", mechanism="m",
            direction="DOWN", magnitude="LOW", confidence=0.5, falsifier="f")


def test_a_decision_delta_of_zero_is_a_result_not_a_bug():
    same = {"priority": "p", "recommendation": "r", "risk": "k",
            "scenario": "s", "information_request": "i", "confidence": "c"}
    d = WM.DecisionDelta(company_id="c", without_world_model=same,
                         with_world_model=dict(same))
    assert not d.nonzero
    assert "added no decision value" in d.as_dict()["reading"]


def test_a_derived_aggregate_cannot_corroborate_its_own_input():
    lineage = {"agg": ["co_a"], "co_a": ["node1"]}
    WM.assert_no_double_count("agg", lineage, ["node2"])
    with pytest.raises(WM.WorldModelDefect):
        WM.assert_no_double_count("agg", lineage, ["node1"])


# =============================================================================
# V5: THE A/B DECISION-VALUE FRAMEWORK AND THE META-GUARD
# =============================================================================

def _an(FA, variant, **kw):
    base = {"company_id": "c", "as_of": "2026-01-01", "variant": variant,
            "top_priority": "ch", "action": FA.MONITOR,
            "risks": (FA.Risk(risk_id="r1", severity="LOW", channel="ch",
                              mechanism="m", standing=FA.INFERRED,
                              evidence=("e1",)),),
            "information_requests": ("q",), "evidence": ("e1",)}
    base.update(kw)
    return FA.Analysis(**base)


def test_a_wording_change_is_not_a_decision_delta():
    """The whole reason the decision fields are enums."""
    from intent_engine.econ import founder_ab as FA
    a = _an(FA, "A", prose="alpha")
    b = _an(FA, "B", prose="beta and a long macro paragraph")
    d = FA.compare(a, b, regime="t")
    assert not d.is_material
    assert d.verdict == "NO_MATERIAL_ECONOMIC_DELTA"
    assert any(f.field == "prose" and not f.material for f in d.fields)


def test_a_structured_field_change_is_material():
    from intent_engine.econ import founder_ab as FA
    a = _an(FA, "A")
    b = _an(FA, "B", action=FA.PREPARE)
    d = FA.compare(a, b, regime="t")
    assert d.is_material and "action" in d.material_fields


def test_a_material_delta_without_a_trigger_is_not_credited():
    """§13: no attribution, no credited improvement."""
    from intent_engine.econ import founder_ab as FA
    a = _an(FA, "A")
    b = _an(FA, "B", action=FA.PREPARE)
    assert not FA.compare(a, b, regime="t").attributable
    d = FA.compare(a, b, regime="t",
                   triggers={"action": ("driver moved", "mechanism",
                                        ("panel:X@2026-01-01",))})
    assert d.attributable and d.verdict == "MATERIAL_AND_ATTRIBUTED"


def test_a_baseline_with_no_risks_is_refused():
    """Two of the seven material fields are computed FROM the risks, so an A
    with none concedes them before the comparison starts."""
    from intent_engine.econ import founder_ab as FA
    with pytest.raises(FA.AnalysisDefect):
        FA.assert_baseline_is_real(_an(FA, "A", risks=()))
    FA.assert_baseline_is_real(_an(FA, "A"))


def test_baseline_a_may_not_have_seen_the_economic_state():
    from intent_engine.econ import founder_ab as FA
    with pytest.raises(FA.AnalysisDefect):
        FA.assert_baseline_is_real(_an(FA, "A", economic_inputs=("x",)))


def test_a_and_b_must_share_an_evidence_cutoff():
    """Otherwise the treatment is 'more recent data', not 'the world model'."""
    from intent_engine.econ import founder_ab as FA
    a = _an(FA, "A")
    b = _an(FA, "B", as_of="2026-06-01")
    with pytest.raises(Exception):
        FA.compare(a, b, regime="t")


def test_confidence_rising_on_no_new_grounded_observation_is_damage():
    from intent_engine.econ import founder_ab as FA
    a = _an(FA, "A", confidence="LOW",
            risks=(FA.Risk(risk_id="r", severity="LOW", channel="ch",
                           mechanism="m", standing=FA.OBSERVED,
                           evidence=("e",)),))
    b = _an(FA, "B", confidence="HIGH",
            risks=(FA.Risk(risk_id="r", severity="LOW", channel="ch",
                           mechanism="m", standing=FA.INFERRED,
                           evidence=()),))
    kinds = [d.kind for d in FA.detect_damage(a, b, regime="t")]
    assert "EXCESSIVE_CONFIDENCE" in kinds


def test_the_rubric_is_frozen():
    from intent_engine.econ import founder_ab as FA
    assert FA.rubric_hash() == "15f463e9e671cb03"
    with pytest.raises(FA.AnalysisDefect):
        FA.assert_rubric_unchanged("0000000000000000")


def test_a_relation_whose_lag_has_not_elapsed_has_not_failed():
    """§18. The previous run reported 4 of 6 relations as non-firing with no
    lag check at all."""
    from intent_engine.econ import worldmodel as WM
    pending = WM.RelationCheck(
        relation="r", source_moved=True, source_move=0.1, lag_elapsed=False,
        days_since_source_move=10, lag_days=180, target_moved=False,
        target_move=0.0, direction_correct=False, magnitude_plausible=False,
        regime_applicable=True)
    assert pending.state == WM.REL_PENDING
    WM.assert_lag_respected(pending)


def test_a_live_dimension_is_not_automatically_useful():
    from intent_engine.econ import worldmodel as WM
    live = WM.DimensionAudit(
        dimension="d", producer="p", source="s", frequency="m",
        as_of="2026-08-01", freshness_days=10, persisted=True,
        consumer=("x",), standing=WM.OBSERVED)
    assert WM.classify_dimension(live, deltas_produced=0,
                                 relations_supported=0,
                                 company_consumers=0) == WM.LIVE_UNPROVEN_VALUE
    assert WM.classify_dimension(live, deltas_produced=2,
                                 relations_supported=0,
                                 company_consumers=1) == WM.LIVE_DECISION_RELEVANT


def test_stagnation_v2_separates_legitimate_stability_from_broken_learning():
    from intent_engine.econ import worldmodel as WM
    broken = WM.detect_stagnation(
        unique_evidence=0, duplicate_evidence=50, drivers_moved=0,
        drivers_total=10, belief_updates=0, expectations_opened=0,
        expectations_due=5, resolutions=0, material_deltas=0, comparisons=60)
    kinds = {a.kind for a in broken}
    assert WM.DUPLICATE_INPUT in kinds and WM.PRODUCER_STAG in kinds
    assert WM.LEGITIMATE not in kinds
    for a in broken:
        assert a.next_diagnostic.strip()
    healthy = WM.detect_stagnation(
        unique_evidence=10, duplicate_evidence=2, drivers_moved=6,
        drivers_total=10, belief_updates=3, expectations_opened=2,
        expectations_due=0, resolutions=0, material_deltas=24, comparisons=60)
    assert [a.kind for a in healthy] == [WM.LEGITIMATE]


def test_an_alert_without_a_next_diagnostic_is_refused():
    from intent_engine.econ import worldmodel as WM
    with pytest.raises(Exception):
        WM.StagnationAlert(kind=WM.BELIEF_STAG, reason="r", evidence="e",
                           next_diagnostic="  ")


# --- §36 the meta-guard -----------------------------------------------------

def test_a_proof_that_mutates_its_own_guard_is_refused():
    """The mistake this project made thirteen times across three runs."""
    from intent_engine.econ import breakproof as BP
    bad = BP.Proof(name="t", description="d", target_kind=BP.PRODUCER,
                   mutated_file="f", mutated_symbol="WM.assert_no_double_count",
                   guard_under_test="assert_no_double_count",
                   production_call_path="scripts/run_world_model.py")
    with pytest.raises(BP.TautologicalProof):
        bad.validate()


def test_a_proof_may_test_guard_integrity_when_it_says_so():
    from intent_engine.econ import breakproof as BP
    ok = BP.Proof(name="t", description="d", target_kind=BP.PRODUCER,
                  mutated_file="f", mutated_symbol="assert_x",
                  guard_under_test="assert_x",
                  production_call_path="scripts/run_world_model.py",
                  tests_guard_integrity=True)
    ok.validate()
    s = BP.summarise([ok])
    assert s["guard_integrity_proofs"] == ["t"]
    assert s["defect_coverage_proofs"] == 0


def test_a_proof_must_name_a_production_call_path():
    from intent_engine.econ import breakproof as BP
    with pytest.raises(Exception):
        BP.Proof(name="t", description="d", target_kind=BP.PRODUCER,
                 mutated_file="f", mutated_symbol="a",
                 guard_under_test="b", production_call_path="  ").validate()


def test_a_no_op_mutation_is_refused():
    from intent_engine.econ import breakproof as BP
    p = BP.Proof(name="t", description="d", target_kind=BP.PRODUCER,
                 mutated_file="f", mutated_symbol="a", guard_under_test="b",
                 production_call_path="p", bytes_before=10, bytes_after=10)
    with pytest.raises(BP.TautologicalProof):
        p.assert_mutation_landed()


def test_the_meta_guard_sees_through_a_module_prefix():
    from intent_engine.econ import breakproof as BP
    assert BP._same_symbol("WM.assert_x", "assert_x")
    assert BP._same_symbol("assert_x", "  ASSERT_X  ")
    assert not BP._same_symbol("build_rows", "assert_x")

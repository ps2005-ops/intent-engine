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

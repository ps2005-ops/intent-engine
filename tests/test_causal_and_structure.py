"""Causal pathways, reaction trees and market structure.

`test_break_*` names are deliberate break proofs.
"""
from __future__ import annotations

import pytest

from intent_engine.market import causal as C
from intent_engine.market import market_structure as MS
from intent_engine.market import reactions as R
from intent_engine.market import strategic_interaction as SI


def an_edge(cause="oil price", effect="producer margins", rivals=("demand",),
            lag=30):
    return C.edge(cause=cause, effect=effect, direction=C.POSITIVE,
                  mechanism="higher realised price lifts margin per barrel",
                  lag_days=lag, competing_explanations=rivals,
                  evidence_ids=["ev_1"])


# ----------------------------------------------------------------- causal
def test_edge_requires_a_mechanism():
    with pytest.raises(C.CausalError, match="mechanism"):
        C.edge(cause="a", effect="b", direction=C.POSITIVE, mechanism="")


def test_edge_is_born_hypothesized():
    assert an_edge().status == C.HYPOTHESIZED
    assert an_edge().is_asserted is False


def test_break_causal_edge_promoted_without_discriminating_evidence():
    """Repeated co-movement must never promote an edge to fact."""
    e = an_edge()
    for _ in range(100):
        e = C.observe_covariation(e, at="2026-08-01", evidence_ids=["ev_n"])
    assert e.observations == 100
    assert e.status == C.HYPOTHESIZED, "co-movement is not causation"
    with pytest.raises(C.CausalError, match="discriminates"):
        C.promote(e, at="2026-08-04", discriminating_evidence="",
                  evidence_ids=["ev_2"])


def test_break_market_movement_treated_as_causal_proof():
    """An edge with no named rival cannot be promoted at all."""
    e = C.edge(cause="share price rose", effect="strategy is working",
               direction=C.POSITIVE, mechanism="the market knows things")
    with pytest.raises(C.CausalError, match="competing explanation"):
        C.promote(e, at="2026-08-04",
                  discriminating_evidence="it went up again",
                  evidence_ids=["ev_1"])


def test_promotion_requires_cited_evidence():
    with pytest.raises(C.CausalError, match="cited evidence"):
        C.promote(an_edge(), at="2026-08-04",
                  discriminating_evidence="margins moved without a demand "
                                          "change",
                  evidence_ids=[])


def test_promotion_succeeds_on_discriminating_evidence():
    e = C.promote(an_edge(), at="2026-08-04",
                  discriminating_evidence="margins rose while volumes fell, "
                                          "which the demand story cannot "
                                          "produce",
                  evidence_ids=["ev_2"])
    assert e.status == C.SUPPORTED and e.is_asserted


def test_supported_edge_demotes_to_under_review_not_straight_out():
    e = C.promote(an_edge(), at="2026-08-04",
                  discriminating_evidence="volumes fell as margins rose",
                  evidence_ids=["ev_2"])
    after = C.contradict(e, at="2026-09-01", reason="margins fell with oil up")
    assert after.status == C.UNDER_REVIEW


def test_lag_makes_an_edge_testable_on_a_date():
    assert an_edge(lag=30).expected_effect_at("2026-08-01") == "2026-08-31"
    assert an_edge(lag=None).expected_effect_at("2026-08-01") is None


def test_pathway_requires_links_that_join():
    with pytest.raises(C.CausalError, match="does not lead into"):
        C.pathway("broken", [an_edge(cause="a", effect="b"),
                             an_edge(cause="x", effect="y")])


def test_pathway_narrates_the_full_chain():
    p = C.pathway("oil to equipment", [
        an_edge(cause="oil price", effect="producer margins"),
        an_edge(cause="producer margins", effect="capex"),
        an_edge(cause="capex", effect="equipment revenue")])
    assert p.narrate() == "oil price → producer margins → capex → equipment revenue"
    assert p.total_lag_days == 90


def test_pathway_lag_is_none_when_any_link_is_unknown():
    p = C.pathway("partial", [an_edge(cause="a", effect="b", lag=10),
                              an_edge(cause="b", effect="c", lag=None)])
    assert p.total_lag_days is None


def test_pathway_is_only_as_strong_as_its_weakest_link():
    strong = C.promote(an_edge(cause="a", effect="b"), at="2026-08-04",
                       discriminating_evidence="d", evidence_ids=["e"])
    weak = an_edge(cause="b", effect="c")
    p = C.pathway("mixed", [strong, weak])
    assert p.status == C.HYPOTHESIZED
    assert p.weakest_link.edge_id == weak.edge_id


def test_graph_downstream_tolerates_a_feedback_loop():
    g = C.CausalGraph()
    g.add(an_edge(cause="capacity", effect="price"))
    g.add(an_edge(cause="price", effect="demand"))
    g.add(an_edge(cause="demand", effect="capacity"))
    assert len(g.downstream("capacity")) == 3


def test_graph_summary_reports_added_and_asserted():
    g = C.CausalGraph()
    g.add(an_edge())
    s = g.summarise(before=())
    assert s["added"] == 1 and s["asserted"] == 0


# -------------------------------------------------------------- reactions
def rival(actions=("match price", "bundle"), name="Rival"):
    return SI.actor(name=name, kind=SI.COMPETITORS,
                    objectives=("defend share",),
                    available_actions=actions)


def test_break_infeasible_response_carried_as_a_possibility():
    """A response an actor cannot make is not a low-probability response."""
    constrained = SI.actor(name="SmallCo", kind=SI.COMPETITORS,
                           constraints=("capital constrained",),
                           available_actions=("do nothing",))
    tree = R.build_tree(
        actor="BigCo", action="cut list price 15%", action_kind="PRICE_CUT",
        at="2026-08-01",
        candidates=[{"responder": constrained, "response": "cut price 30%",
                     "rationale": "defend share"}])
    assert tree.responses == ()
    assert tree.infeasible[0].confidence == R.INFEASIBLE


def test_only_precedented_evidenced_responses_are_stated_as_predictions():
    tree = R.build_tree(
        actor="BigCo", action="cut price", action_kind="PRICE_CUT",
        at="2026-08-01",
        candidates=[
            {"responder": rival(), "response": "match price",
             "precedents": ("matched within 8 days in 2024",),
             "evidence_ids": ("ev_1",), "rationale": "has matched before"},
            {"responder": rival(name="Other"), "response": "bundle",
             "consistent_with_objective": True, "rationale": "plausible"}])
    labels = {r.response: r.confidence for r in tree.responses}
    assert labels["match price"] == R.LIKELY
    assert labels["bundle"] == R.PLAUSIBLE
    assert tree.as_dict()["stated_as_prediction"] == ["match price"]


def test_unassessed_strategic_factors_are_reported_not_hidden():
    tree = R.build_tree(actor="A", action="cut", action_kind="PRICE_CUT",
                        at="2026-08-01", candidates=[],
                        factors={"switching_costs": "low, per filings"})
    assert "switching_costs" not in tree.unassessed_factors
    assert "retaliation_capability" in tree.unassessed_factors
    assert len(tree.unassessed_factors) == len(R.STRATEGIC_FACTORS) - 1


def test_break_equilibrium_asserted_from_unmeasured_payoffs():
    tree = R.build_tree(
        actor="A", action="cut", action_kind="PRICE_CUT", at="2026-08-01",
        candidates=[], equilibrium_risk="the equilibrium is mutual matching")
    with pytest.raises(R.ReactionError, match="solved game"):
        R.assert_no_equilibrium_claim(tree)


def test_scenario_language_is_permitted():
    tree = R.build_tree(
        actor="A", action="cut", action_kind="PRICE_CUT", at="2026-08-01",
        candidates=[],
        equilibrium_risk="repeated matching could compress margins for all "
                         "participants if capacity permits")
    R.assert_no_equilibrium_claim(tree)


def test_tree_refuses_a_non_strategic_action():
    with pytest.raises(R.ReactionError, match="not a strategic action"):
        R.build_tree(actor="A", action="published a blog post",
                     action_kind="BLOG_POST", at="2026-08-01", candidates=[])


def test_candidate_must_carry_a_modelled_actor():
    with pytest.raises(R.ReactionError, match="modelled Actor"):
        R.build_tree(actor="A", action="cut", action_kind="PRICE_CUT",
                     at="2026-08-01",
                     candidates=[{"responder": "Rival", "response": "match"}])


# ------------------------------------------------------ market structure
def fact(dim="switching_costs"):
    return MS.structural_fact(
        dimension=dim, finding="multi-year contracts with migration cost",
        evidence_ids=["ev_1"])


def test_structural_claim_requires_evidence():
    with pytest.raises(MS.StructureError, match="cited evidence"):
        MS.structural_fact(dimension="entry_barriers", finding="high",
                           evidence_ids=[])


def test_break_concentration_fabricated_without_share_data():
    s = MS.build_structure(subject="X", market_definition="m",
                           strategic_job="j", facts=[fact()])
    assert s.concentration == MS.UNMEASURED
    assert "unmeasured rather than estimated" in s.concentration_note


def test_concentration_quantified_only_from_supplied_shares():
    s = MS.build_structure(subject="X", market_definition="m",
                           strategic_job="j", facts=[fact()],
                           shares={"A": 40, "B": 35, "C": 25})
    assert s.concentration == MS.QUANTIFIED
    assert "HHI" in s.concentration_note


def test_partial_share_coverage_states_the_understatement():
    s = MS.build_structure(subject="X", market_definition="m",
                           strategic_job="j", facts=[fact()],
                           shares={"A": 30, "B": 20})
    assert any("understates" in l for l in s.limitations)


def test_unassessed_dimensions_are_listed():
    s = MS.build_structure(subject="X", market_definition="m",
                           strategic_job="j", facts=[fact()])
    assert "switching_costs" in s.assessed_dimensions
    assert "network_effects" in s.unassessed_dimensions


def test_break_auction_theory_injected_into_an_unrelated_company():
    """Auction analysis must not run without evidence of auction buying."""
    a = MS.auction_analysis(subject="SelfServeSaaS")
    assert a.applies is False
    assert "not evidenced" in a.applies_because

    proposed = MS.auction_analysis(subject="SelfServeSaaS",
                                   fmt=MS.SEALED_BID, buyer_evidence=[])
    assert proposed.applies is False
    assert "no evidence shows its buyers" in proposed.applies_because


def test_auction_analysis_runs_when_procurement_is_evidenced():
    a = MS.auction_analysis(
        subject="DefenceCo", fmt=MS.SEALED_BID,
        buyer_evidence=["ev_1"],
        mechanism="agency awards multi-year contracts by sealed bid")
    assert a.applies is True and a.evidence_ids == ("ev_1",)
    assert a.limitations


def test_pricing_without_a_mechanism_is_a_textbook_entry_and_is_refused():
    p = MS.pricing_analysis(subject="X", strategy=MS.BUNDLING,
                            evidence_ids=["ev_1"], mechanism="")
    assert p.applies is False
    assert "textbook entry" in p.applies_because


def test_pricing_runs_with_strategy_evidence_and_mechanism():
    p = MS.pricing_analysis(
        subject="X", strategy=MS.BUNDLING, evidence_ids=["ev_1"],
        mechanism="the suite is priced below the sum of its parts, which "
                  "raises the cost of buying any single module elsewhere")
    assert p.applies is True


def test_entry_analysis_refuses_a_generic_barrier_claim():
    e = MS.entry_analysis(subject="X", market="m", barriers=[])
    assert e.applies is False
    assert "true everywhere" in e.applies_because


def test_entry_analysis_runs_on_evidenced_barriers():
    e = MS.entry_analysis(subject="X", market="enterprise data platforms",
                          barriers=[fact("entry_barriers")],
                          incumbent_response="incumbents bundle aggressively")
    assert e.applies is True and e.evidence_ids == ("ev_1",)

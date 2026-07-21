"""T020 deterministic multi-dimensional scoring.

Each dimension independently, UNAVAILABLE rather than zero, a composite
that names its gaps rather than imputing them, strategy that only a human
declares, four separate confidences, and cost of delay computed apart.
0 model calls. 0 network.
"""
import pytest

from intent_engine.product import ProductError, ProductService
from intent_engine.product.scoring import (
    ALIGNMENT_LEVELS, OK, SCORE_VERSIONS, UNAVAILABLE, assert_not_score_shaped,
    cost_of_delay, customer_coverage, evidence_coverage, execution_confidence,
    experiment_coverage, freshness, opportunity_confidence, opportunity_score,
    problem_confidence, proposal_confidence, research_coverage, score_block,
)

AS_OF = "2026-07-21T00:00:00+00:00"
OLD = "2025-01-01T00:00:00+00:00"
REF = [{"kind": "crm_fact", "ref_id": "crm.churned:E1", "crm_entity_id": "E1"}]


def _facts(**over):
    facts = {
        "as_of": AS_OF,
        "freshness_policy_days": 90,
        "evidence_references": list(REF),
        "affected_customers": ["E1", "E2", "E3"],
        "crm_facts": [{"crm_entity_id": "E1", "event_type": "crm.churned"}],
        "experiments": [{"experiment_id": "EXP1",
                         "label": "DIFFERENCE OBSERVED"}],
        "research": {"coverage_totals": {"covered": 2, "partially_covered": 1,
                                         "contradicted": 0, "not_covered": 0,
                                         "not_investigated": 1},
                     "stances": ["SUPPORTED", "SUPPORTED", "MIXED"]},
        "origin": {},
        "alignment": {"level": "core", "declared_by": "founder"},
        "input_timestamps": [AS_OF],
        "unknowns": ["u1"], "assumptions": ["a1"], "open_questions": ["q1"],
        "risks": ["r1"],
        "revenue_at_risk_declared": None,
        "spec": {"exists": True, "debt": [{"kind": "need_ux"}],
                 "acceptance_criteria": 2},
        "dependencies_unmet": 0,
        "decision_id": None,
    }
    facts.update(over)
    return facts


# =============================================================================
# Every dimension carries its version, inputs, formula, reasons, and status
# =============================================================================

@pytest.mark.parametrize("fn,name", [
    (evidence_coverage, "evidence_coverage"),
    (customer_coverage, "customer_coverage"),
    (experiment_coverage, "experiment_coverage"),
    (research_coverage, "research_coverage"),
    (freshness, "freshness"),
])
def test_every_dimension_carries_its_explanation(fn, name):
    block = fn(_facts())
    assert block["dimension"] == name
    assert block["score_version"] == SCORE_VERSIONS[name]
    assert block["status"] == OK
    assert block["inputs"] and block["formula"] and block["reasons"]


def test_identical_inputs_give_identical_scores():
    assert score_block(_facts()) == score_block(_facts())


def test_a_score_does_not_depend_on_when_a_proposal_was_created(tmp_path):
    """The load-bearing inputs are the evidence timestamps, never the
    proposal's own recording time."""
    svc = ProductService(tmp_path / "product.jsonl")
    problem = svc.record_problem(
        statement="Setup abandons before first value",
        evidence_references=REF, why_now="current",
        what_changes_if_ignored="repeats", first_observed_at=OLD,
        affected_customers=["E1"])
    opportunity = svc.register_opportunity(problem["problem_id"],
                                           title="A guided first run",
                                           evidence_references=REF)
    first = svc.draft_proposal(
        opportunity, candidate_solution="Add a guided first run",
        tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
        assumptions=["a"])
    second = svc.draft_proposal(
        opportunity, candidate_solution="Add a guided first run, revised",
        tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
        assumptions=["a"])
    a = svc.score_proposal(first, as_of=AS_OF, record=False)
    b = svc.score_proposal(second, as_of=AS_OF, record=False)
    assert a["dimensions"]["freshness"] == b["dimensions"]["freshness"]


# =============================================================================
# A missing input is UNAVAILABLE, never 0
# =============================================================================

@pytest.mark.parametrize("fn,key,empty", [
    (evidence_coverage, "research", {"coverage_totals": {}, "stances": []}),
    (customer_coverage, "affected_customers", []),
    (experiment_coverage, "experiments", []),
    (research_coverage, "research", {"coverage_totals": {}, "stances": []}),
    (freshness, "input_timestamps", []),
])
def test_a_dimension_with_no_recorded_input_is_unavailable(fn, key, empty):
    block = fn(_facts(**{key: empty}))
    assert block["status"] == UNAVAILABLE
    assert block["value"] is None            # not 0, not a default
    assert "no recorded input" in " ".join(block["reasons"]) \
        or "no research package" in " ".join(block["reasons"]) \
        or "no research stance" in " ".join(block["reasons"]) \
        or "no experiment is linked" in " ".join(block["reasons"]) \
        or "no affected customer" in " ".join(block["reasons"])


def test_zero_is_a_value_and_absence_is_not():
    """A recorded coverage of zero covered questions scores 0.0 with
    status OK; an absent package is UNAVAILABLE. They are different."""
    recorded = evidence_coverage(_facts(research={
        "coverage_totals": {"covered": 0, "not_covered": 3}, "stances": []}))
    assert recorded["status"] == OK and recorded["value"] == 0.0
    absent = evidence_coverage(_facts(research={"coverage_totals": {},
                                                "stances": []}))
    assert absent["status"] == UNAVAILABLE and absent["value"] is None


# =============================================================================
# Strategic alignment — human declaration only
# =============================================================================

def test_strategic_alignment_is_unavailable_without_a_human_declaration():
    from intent_engine.product.scoring import strategic_alignment
    block = strategic_alignment(_facts(alignment=None))
    assert block["status"] == UNAVAILABLE
    assert "strategy comes from a person" in " ".join(block["reasons"])


def test_strategic_alignment_reads_a_declaration_it_did_not_author():
    from intent_engine.product.scoring import strategic_alignment
    for level, expected in ALIGNMENT_LEVELS.items():
        block = strategic_alignment(_facts(
            alignment={"level": level, "declared_by": "founder"}))
        assert block["status"] == OK and block["value"] == expected


def test_an_undeclared_level_is_unavailable_rather_than_guessed():
    from intent_engine.product.scoring import strategic_alignment
    block = strategic_alignment(_facts(
        alignment={"level": "extremely important", "declared_by": "founder"}))
    assert block["status"] == UNAVAILABLE


def test_an_agent_cannot_declare_alignment(tmp_path):
    svc = ProductService(tmp_path / "product.jsonl")
    with pytest.raises(ProductError, match="human wall transition"):
        svc.declare_alignment("O1", "core", actor_id="bot", actor_type="agent")


# =============================================================================
# The composite names its gaps rather than imputing them
# =============================================================================

def test_a_composite_with_an_unavailable_dimension_is_unavailable():
    facts = _facts(alignment=None)
    block = score_block(facts)
    composite = block["opportunity_score"]
    assert composite["status"] == UNAVAILABLE
    assert composite["value"] is None
    assert any("strategic_alignment" in gap for gap in composite["gaps"])
    assert "strategic_alignment" in " ".join(composite["reasons"])


def test_the_composite_reports_which_dimensions_were_available():
    composite = score_block(_facts(experiments=[]))["opportunity_score"]
    assert "experiment_coverage" not in composite["available_dimensions"]
    assert "customer_coverage" in composite["available_dimensions"]


def test_a_full_composite_states_its_weights_and_value():
    composite = score_block(_facts())["opportunity_score"]
    assert composite["status"] == OK
    assert 0.0 <= composite["value"] <= 1.0
    assert "weight" in composite["formula"]
    assert composite["gaps"] == []


def test_an_unavailable_dimension_is_never_counted_as_zero():
    """Dropping it from the denominator would inflate the composite, so
    the composite is withheld instead."""
    full = score_block(_facts())["opportunity_score"]
    partial = score_block(_facts(experiments=[]))["opportunity_score"]
    assert full["status"] == OK
    assert partial["status"] == UNAVAILABLE
    assert partial["value"] is None


# =============================================================================
# Conflicting evidence lowers confidence and says so
# =============================================================================

def test_conflicting_research_lowers_confidence_and_names_the_conflict():
    conflicted = _facts(research={
        "coverage_totals": {"covered": 0, "contradicted": 2},
        "stances": ["CONFLICTING", "CONFLICTING"]})
    block = score_block(conflicted)
    confidence = block["confidence"]["opportunity_confidence"]
    assert confidence["value"] <= 0.4
    assert "CONFLICTING" in " ".join(confidence["reasons"])
    assert "unsettled" in " ".join(confidence["reasons"])


def test_an_unsettled_experiment_label_lowers_confidence():
    block = score_block(_facts(experiments=[{"experiment_id": "E",
                                             "label": "INCONCLUSIVE"}]))
    reasons = " ".join(
        block["confidence"]["opportunity_confidence"]["reasons"])
    assert "INCONCLUSIVE" in reasons
    assert block["confidence"]["opportunity_confidence"]["value"] <= 0.4


# =============================================================================
# Four separate confidences
# =============================================================================

def test_the_four_confidences_are_computed_separately():
    block = score_block(_facts())
    confidence = block["confidence"]
    assert set(confidence) == {"problem_confidence", "opportunity_confidence",
                               "proposal_confidence", "execution_confidence"}
    for name, item in confidence.items():
        assert item["score_version"] == SCORE_VERSIONS[name]
        assert item["formula"] and item["reasons"]


def test_unknowns_lower_proposal_confidence_without_touching_the_problem():
    few = score_block(_facts(unknowns=["u1"], open_questions=[]))
    many = score_block(_facts(unknowns=["u1", "u2", "u3", "u4"],
                              open_questions=["q1", "q2"]))
    assert (many["confidence"]["proposal_confidence"]["value"]
            < few["confidence"]["proposal_confidence"]["value"])
    assert (many["confidence"]["problem_confidence"]["value"]
            == few["confidence"]["problem_confidence"]["value"])


def test_execution_confidence_is_unavailable_without_a_spec():
    block = execution_confidence(_facts(spec={"exists": False, "debt": [],
                                              "acceptance_criteria": 0}))
    assert block["status"] == UNAVAILABLE
    assert "no spec draft" in " ".join(block["reasons"])


def test_execution_confidence_rises_with_a_linked_decision():
    without = execution_confidence(_facts())
    with_decision = execution_confidence(_facts(decision_id="D1"))
    assert with_decision["value"] > without["value"]
    assert "no Decision Record is linked" in " ".join(without["reasons"])


def test_proposal_confidence_is_unavailable_when_its_input_is():
    empty = _facts(evidence_references=[], affected_customers=[],
                   research={"coverage_totals": {}, "stances": []},
                   experiments=[])
    conf = proposal_confidence(
        empty, opportunity_confidence(empty, problem_confidence(empty), {}))
    assert conf["status"] == UNAVAILABLE


# =============================================================================
# Cost of delay — separate, and honest about the money it does not hold
# =============================================================================

def test_cost_of_delay_is_not_folded_into_the_opportunity_score():
    block = score_block(_facts())
    assert "cost_of_delay" not in block["opportunity_score"]["inputs"]
    assert block["cost_of_delay"]["score_version"] == \
        SCORE_VERSIONS["cost_of_delay"]


def test_cost_of_delay_withholds_a_composite_without_declared_revenue():
    block = cost_of_delay(_facts())
    assert block["status"] == UNAVAILABLE
    assert any("declared_revenue_at_risk" in gap for gap in block["gaps"])
    # the components it CAN compute are still reported
    assert block["components"]["customer_pain"]["status"] == OK


def test_cost_of_delay_reports_every_component_it_has():
    block = cost_of_delay(_facts(
        revenue_at_risk_declared=1000,
        crm_facts=[{"crm_entity_id": "E1", "event_type": "crm.churned"},
                   {"crm_entity_id": "E2", "event_type": "crm.customer_at_risk"}],
        experiments=[{"experiment_id": "E", "label": "GUARDRAIL BREACHED"}]))
    assert block["status"] == OK
    assert block["components"]["growth_urgency"]["value"] == 1
    assert block["components"]["customer_pain"]["value"] == 2


# =============================================================================
# Freshness labels rather than deletes
# =============================================================================

def test_an_old_input_is_labelled_needs_refresh_rather_than_dropped():
    block = freshness(_facts(input_timestamps=[OLD]))
    assert block["status"] == OK
    assert block["label"] == "NEEDS_REFRESH"
    assert block["value"] == 0.0
    assert "NEEDS_REFRESH" in " ".join(block["reasons"])


def test_a_recent_input_is_fresh():
    assert freshness(_facts())["label"] == "FRESH"


# =============================================================================
# Scores describe proposals; they do not shape them
# =============================================================================

def test_an_author_supplied_score_is_rejected():
    for field in ("priority", "score", "scores", "opportunity_score",
                  "confidence", "cost_of_delay", "strategic_alignment"):
        with pytest.raises(ProductError, match="author-supplied scoring"):
            assert_not_score_shaped({field: 9}, where="test payload")


def test_a_clean_payload_passes_the_wall():
    assert_not_score_shaped({"candidate_solution": "x", "unknown": ["y"]},
                            where="test payload")


def test_a_proposal_cannot_be_drafted_carrying_its_own_priority(tmp_path):
    svc = ProductService(tmp_path / "product.jsonl")
    problem = svc.record_problem(
        statement="Setup abandons before first value", evidence_references=REF,
        why_now="current", what_changes_if_ignored="repeats",
        first_observed_at=AS_OF)
    opportunity = svc.register_opportunity(problem["problem_id"],
                                           title="A guided first run",
                                           evidence_references=REF)
    with pytest.raises(ProductError, match="author-supplied scoring"):
        svc.draft_proposal(
            opportunity, candidate_solution="Add a guided first run",
            tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
            assumptions=["a"],
            dependencies=[{"priority": 9}])          # nested, still caught


def test_score_versions_are_declared_for_every_dimension():
    block = score_block(_facts())
    for name, item in block["dimensions"].items():
        assert item["score_version"] == SCORE_VERSIONS[name]
    assert block["score_versions"] == SCORE_VERSIONS
    assert "describe proposals" in block["policy"]
    assert "not modified in order to improve" in block["policy"]

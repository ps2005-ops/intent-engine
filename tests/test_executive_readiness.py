"""T021 readiness, impact, reversibility, context, aging, expiry, and debt.

Six independent dimensions, UNAVAILABLE never 0, financial structurally
UNAVAILABLE, decision-readiness a YES/NO, and expiry that follows a
changed input rather than a clock. 0 model calls. 0 network.
"""
import pytest

from intent_engine.executive import (
    ExecutiveError, aggregate_reversibility, assert_not_readiness_shaped,
    build_context, decision_age, decision_impact, derive_decision_debt,
    expiry_check, readiness_block,
)
from intent_engine.executive.readiness import (
    OK, UNAVAILABLE, READINESS_VERSIONS,
)

NOW = "2026-07-21T00:00:00+00:00"
LATER = "2027-07-21T00:00:00+00:00"


def _facts(**over):
    facts = {
        "research": {"stances": ["SUPPORTED", "SUPPORTED"]},
        "references": [{"kind": "research_package", "ref_id": "R1"}],
        "experiments": [{"experiment_id": "E1", "label": "DIFFERENCE OBSERVED"}],
        "product": {"spec_present": True, "spec_debt_count": 1,
                    "proposal_status": "accepted"},
        "alignment": {"level": "core", "declared_by": "founder"},
        "budget": {"amount_available": 1000, "declared_by": "founder"},
        "owner": "founder", "unmet_dependencies": [], "open_debt": [],
        "affected_customers": ["E1", "E2", "E3"],
        "downstream_decisions": [], "initiatives": ["I1"],
        "needs_budget": True, "decision_class": "product",
    }
    facts.update(over)
    return facts


# =============================================================================
# The six dimensions
# =============================================================================

def test_all_six_dimensions_carry_their_explanation():
    block = readiness_block(_facts())
    for name, item in block["dimensions"].items():
        assert item["readiness_version"] == READINESS_VERSIONS[name]
        assert item["formula"] and item["reasons"]


def test_there_is_no_overall_score():
    block = readiness_block(_facts())
    assert "overall" not in block
    assert "composite" not in block
    assert "score" not in block


def test_identical_inputs_give_identical_readiness():
    assert readiness_block(_facts()) == readiness_block(_facts())


@pytest.mark.parametrize("dimension,killer", [
    ("evidence_readiness", {"research": {"stances": []}}),
    ("execution_readiness", {"product": {}}),
    ("strategic_readiness", {"alignment": None}),
])
def test_a_dimension_with_no_input_is_unavailable_not_zero(dimension, killer):
    block = readiness_block(_facts(**killer))
    dim = block["dimensions"][dimension]
    assert dim["status"] == UNAVAILABLE
    assert dim["value"] is None


def test_financial_readiness_is_unavailable_without_a_declaration():
    block = readiness_block(_facts(budget=None))
    fin = block["dimensions"]["financial_readiness"]
    assert fin["status"] == UNAVAILABLE
    assert "no financial data" in " ".join(fin["reasons"]) \
        or "no budget declaration" in " ".join(fin["reasons"])


def test_financial_readiness_reads_a_human_declaration():
    block = readiness_block(_facts())
    assert block["dimensions"]["financial_readiness"]["status"] == OK


def test_strategic_readiness_needs_a_human_declaration():
    without = readiness_block(_facts(alignment=None))
    assert without["dimensions"]["strategic_readiness"]["status"] == UNAVAILABLE


# =============================================================================
# Decision readiness is a YES/NO, not a confidence
# =============================================================================

def test_decision_readiness_is_a_boolean_with_reasons():
    ready = readiness_block(_facts())["dimensions"]["decision_readiness"]
    assert isinstance(ready["value"], bool)
    assert ready["reasons"]


def test_decision_readiness_names_every_gap():
    block = readiness_block(_facts(
        alignment=None, owner=None,
        open_debt=[{"kind": "need_experiment"}]))
    ready = block["dimensions"]["decision_readiness"]
    assert ready["value"] is False
    joined = " ".join(ready["reasons"])
    assert "missing strategy" in joined
    assert "missing experiment" in joined


def test_a_fully_supported_decision_can_be_ready():
    block = readiness_block(_facts(needs_budget=False))
    assert block["dimensions"]["decision_readiness"]["value"] is True


# =============================================================================
# Impact — from recorded scope
# =============================================================================

def test_impact_is_computed_from_scope():
    small = decision_impact({"affected_customers": ["E1"],
                             "downstream_decisions": [], "initiatives": []})
    large = decision_impact({"affected_customers": [f"E{i}" for i in range(8)],
                             "downstream_decisions": ["D1", "D2"],
                             "initiatives": ["I1", "I2"]})
    assert small["value"] == "small"
    assert large["value"] in ("large", "transformational")


def test_impact_is_unavailable_without_scope():
    assert decision_impact({})["status"] == UNAVAILABLE


def test_an_irreversible_decision_is_raised_one_impact_level():
    base = decision_impact({"affected_customers": ["E1", "E2", "E3"],
                            "downstream_decisions": [], "initiatives": []})
    raised = decision_impact({"affected_customers": ["E1", "E2", "E3"],
                              "downstream_decisions": [], "initiatives": [],
                              "reversibility": "irreversible"})
    order = ["small", "medium", "large", "transformational"]
    assert order.index(raised["value"]) == order.index(base["value"]) + 1


# =============================================================================
# Reversibility — declared, aggregated to the worst
# =============================================================================

def test_reversibility_takes_the_least_reversible_option():
    block = aggregate_reversibility([{"reversibility": "easy"},
                                     {"reversibility": "hard"},
                                     {"reversibility": "moderate"}])
    assert block["value"] == "hard"


def test_reversibility_is_unavailable_when_no_option_declares_one():
    block = aggregate_reversibility([{}, {}])
    assert block["status"] == UNAVAILABLE
    assert "declared, not inferred" in " ".join(block["reasons"])


# =============================================================================
# The no-shaping wall
# =============================================================================

def test_an_author_supplied_readiness_is_rejected():
    for field in ("decision_readiness", "readiness", "impact", "reversibility",
                  "priority", "escalation"):
        with pytest.raises(ExecutiveError, match="author-supplied readiness"):
            assert_not_readiness_shaped({field: 1}, where="test")


def test_a_clean_payload_passes_the_wall():
    assert_not_readiness_shaped({"decision_question": "q", "unknowns": ["u"]},
                                where="test")


# =============================================================================
# Aging — reported, and separate from readiness
# =============================================================================

def test_aging_is_reported_and_does_not_feed_readiness():
    age = decision_age(NOW, LATER)
    assert age["age_days"] > 300
    assert age["feeds_readiness"] is False


# =============================================================================
# Context and expiry
# =============================================================================

def test_a_context_records_which_inputs_changed():
    first = build_context(
        candidate_id="C1", decision_horizon="short_term",
        decision_class="product",
        resolved_inputs={"crm:E1": {"category": "AT_RISK"},
                         "research:R1": {"stances": ["CONFLICTING"]}})
    second = build_context(
        candidate_id="C1", decision_horizon="short_term",
        decision_class="product",
        resolved_inputs={"crm:E1": {"category": "AT_RISK"},
                         "research:R1": {"stances": ["SUPPORTED"]}},
        prior_fingerprints=first["input_fingerprints"])
    assert second["changed_inputs"]["changed"] == ["research:R1"]
    assert any("research:R1" in c for c in second["recent_changes"])


def test_expiry_follows_a_changed_input_not_a_clock():
    fingerprints = {"research:R1": "abc", "crm:E1": "def"}
    unchanged = expiry_check(recorded_fingerprints=fingerprints,
                             current_fingerprints=fingerprints, as_of=LATER)
    assert unchanged["expired"] is False
    assert "elapsed time" in unchanged["rule"]
    changed = expiry_check(
        recorded_fingerprints=fingerprints,
        current_fingerprints={**fingerprints, "research:R1": "xyz"},
        as_of=NOW)
    assert changed["expired"] is True
    assert any("research:R1" in r for r in changed["reasons"])


def test_a_context_rejects_an_unknown_horizon_or_class():
    with pytest.raises(ExecutiveError, match="horizon"):
        build_context(candidate_id="C1", decision_horizon="whenever",
                      decision_class="product", resolved_inputs={})
    with pytest.raises(ExecutiveError, match="class"):
        build_context(candidate_id="C1", decision_horizon="short_term",
                      decision_class="vibes", resolved_inputs={})


# =============================================================================
# Decision debt
# =============================================================================

def test_decision_debt_is_derived_deterministically():
    facts = {"research": {"stances": ["INSUFFICIENT"]},
             "experiments": [{"experiment_id": "E1", "label": "INCONCLUSIVE"}],
             "crm": {"category": "AT_RISK"},
             "needs_budget": True, "budget_declared": False}
    first = derive_decision_debt(facts)
    assert first == derive_decision_debt(facts)
    kinds = {i["kind"] for i in first}
    assert {"need_research", "need_experiment", "need_customer_validation",
            "need_budget"} <= kinds


def test_every_debt_item_states_what_would_clear_it():
    debt = derive_decision_debt({"needs_budget": True,
                                 "budget_declared": False})
    for item in debt:
        assert item["clears_when"]

"""T020 problem-first enforcement, the Problem Index, and the Opportunity
Index.

Evidence before problem, problem before solution, and both indexes
rebuilt deterministically from append-only rows and never written by a
model. 0 model calls. 0 network.
"""
import pytest

from intent_engine.product import (
    ProductError, ProductService, build_index, build_problem_statement,
    problem_dedup_key,
)
from intent_engine.product.problems import assert_solution_free

AS_OF = "2026-07-21T00:00:00+00:00"
REF = [{"kind": "crm_fact", "ref_id": "crm.churned:E1", "crm_entity_id": "E1"}]
STATEMENT = "Customers stop using the product before reaching first value"


@pytest.fixture()
def svc(tmp_path):
    return ProductService(tmp_path / "product.jsonl")


def _problem(svc, statement=STATEMENT, **over):
    kwargs = dict(statement=statement, evidence_references=REF,
                  why_now="three entities carry a churn fact this quarter",
                  what_changes_if_ignored="the pattern repeats at a higher cost",
                  first_observed_at=AS_OF, affected_customers=["E1", "E2"])
    kwargs.update(over)
    return svc.record_problem(**kwargs)


# =============================================================================
# Problem-first
# =============================================================================

def test_a_problem_with_zero_evidence_references_is_rejected(svc):
    with pytest.raises(ProductError, match="zero evidence references"):
        _problem(svc, evidence_references=[])


def test_why_now_is_mandatory(svc):
    with pytest.raises(ProductError, match="why_now is a required part"):
        _problem(svc, why_now="   ")


def test_what_changes_if_ignored_is_mandatory(svc):
    with pytest.raises(ProductError,
                       match="what_changes_if_ignored is a required part"):
        _problem(svc, what_changes_if_ignored="")


def test_a_problem_phrased_as_its_solution_is_rejected(svc):
    with pytest.raises(ProductError, match="phrased as a solution"):
        _problem(svc, statement="We should build a guided walkthrough")


def test_assert_solution_free_names_the_tell():
    with pytest.raises(ProductError, match="add a button"):
        assert_solution_free("add a button to the settings page")


def test_an_unknown_reference_kind_is_rejected(svc):
    with pytest.raises(ProductError, match="unknown evidence reference kind"):
        _problem(svc, evidence_references=[{"kind": "vibes", "ref_id": "x"}])


def test_a_reference_without_a_ref_id_is_rejected(svc):
    with pytest.raises(ProductError, match="non-empty ref_id"):
        _problem(svc, evidence_references=[{"kind": "crm_fact"}])


def test_identical_dedup_key_returns_the_prior_problem(svc):
    first = _problem(svc)
    second = _problem(svc)
    assert second["reused"] is True
    assert second["problem_id"] == first["problem_id"]
    assert second["dedup_key"] == first["dedup_key"]


def test_dedup_is_exact_match_never_fuzzy(svc):
    first = _problem(svc)
    near = _problem(svc, statement=STATEMENT + " in the EU region")
    assert near["reused"] is False
    assert near["problem_id"] != first["problem_id"]


def test_dedup_key_is_scope_sensitive():
    a = problem_dedup_key(STATEMENT, "eu")
    b = problem_dedup_key(STATEMENT, "us")
    assert a != b
    assert problem_dedup_key(STATEMENT, "eu") == a       # deterministic


def test_build_problem_statement_records_every_required_part():
    body = build_problem_statement(
        statement=STATEMENT, evidence_references=REF, why_now="now",
        what_changes_if_ignored="cost", affected_customers=["E2", "E1", "E1"],
        first_observed_at=AS_OF)
    assert body["affected_customers"] == ["E1", "E2"]     # deduplicated
    assert body["evidence_references"][0]["kind"] == "crm_fact"
    assert body["why_now"] and body["what_changes_if_ignored"]


def test_a_problem_statement_carrying_banned_language_is_rejected():
    with pytest.raises(ProductError, match="overclaims"):
        build_problem_statement(
            statement="Onboarding is obviously broken", evidence_references=REF,
            why_now="now", what_changes_if_ignored="cost",
            first_observed_at=AS_OF)


# =============================================================================
# Problem evolution — problems are not static
# =============================================================================

def test_a_problem_splits_into_children_and_keeps_its_history(svc):
    parent = _problem(svc)["problem_id"]
    child_a = _problem(svc, statement="Setup emails bounce")["problem_id"]
    child_b = _problem(svc, statement="Setup docs are stale")["problem_id"]
    svc.split_problem(parent, [child_a, child_b], reason="two distinct causes")
    index = svc.get_index()
    assert index.problem_index.problems[parent]["state"] == "split"
    assert index.problem_index.lineage_of(child_a)["ancestors"] == [parent]
    # history is retained: the original recording row is still there
    assert any(r.event_type == "product.problem_recorded"
               for r in svc.store.for_problem(parent))


def test_a_merged_problem_records_its_successor(svc):
    a = _problem(svc)["problem_id"]
    b = _problem(svc, statement="Setup docs are stale")["problem_id"]
    svc.merge_problem(a, b, reason="the same underlying cause")
    problems = svc.get_index().problem_index.problems
    assert problems[a]["state"] == "merged"
    assert problems[a]["successor"] == b


def test_a_superseded_problem_records_its_successor(svc):
    a = _problem(svc)["problem_id"]
    b = _problem(svc, statement="Setup docs are stale")["problem_id"]
    svc.supersede_problem(a, b, reason="restated more precisely")
    assert svc.get_index().problem_index.problems[a]["state"] == "superseded"


def test_retiring_a_problem_is_human_only(svc):
    problem = _problem(svc)["problem_id"]
    with pytest.raises(ProductError, match="human wall transition"):
        svc.retire_problem(problem, reason="resolved", actor_id="bot",
                           actor_type="agent")
    svc.retire_problem(problem, reason="resolved", actor_id="founder")
    assert svc.get_index().problem_index.problems[problem]["state"] == "retired"


def test_a_closed_problem_accepts_no_new_opportunity(svc):
    problem = _problem(svc)["problem_id"]
    svc.retire_problem(problem, reason="resolved", actor_id="founder")
    with pytest.raises(ProductError, match="the problem is retired"):
        svc.register_opportunity(problem, title="A walkthrough",
                                 evidence_references=REF)


def test_active_lists_only_active_problems(svc):
    active = _problem(svc)["problem_id"]
    retired = _problem(svc, statement="Setup docs are stale")["problem_id"]
    svc.retire_problem(retired, reason="resolved", actor_id="founder")
    ids = [p["problem_id"] for p in svc.get_index().problem_index.active()]
    assert ids == [active]


# =============================================================================
# One problem, many opportunities — the fan-out the separation exists for
# =============================================================================

def test_one_problem_carries_several_opportunities(svc):
    problem = _problem(svc)["problem_id"]
    a = svc.register_opportunity(problem, title="An interactive walkthrough",
                                 evidence_references=REF)
    b = svc.register_opportunity(problem, title="A lifecycle email sequence",
                                 evidence_references=REF)
    c = svc.register_opportunity(problem, title="A pricing page change",
                                 evidence_references=REF)
    index = svc.get_index()
    found = [o["opportunity_id"]
             for o in index.opportunities_for_problem(problem)]
    assert sorted(found) == sorted([a, b, c])


# =============================================================================
# The Opportunity Index
# =============================================================================

def test_an_opportunity_with_no_evidence_reference_is_rejected(svc):
    problem = _problem(svc)["problem_id"]
    with pytest.raises(ProductError, match="no evidence reference"):
        svc.register_opportunity(problem, title="A walkthrough",
                                 evidence_references=[])


def test_the_index_rebuilds_deterministically_from_rows(svc):
    problem = _problem(svc)["problem_id"]
    svc.register_opportunity(problem, title="A walkthrough",
                             evidence_references=REF)
    rows = svc.store.read_all()
    first = build_index(rows)
    second = build_index(rows)
    assert first.opportunities == second.opportunities
    assert first.problem_index.problems == second.problem_index.problems
    assert first.assert_invariants() == second.assert_invariants()


def test_the_index_rejects_an_orphan_opportunity(svc, tmp_path):
    problem = _problem(svc)["problem_id"]
    opportunity = svc.register_opportunity(problem, title="A walkthrough",
                                           evidence_references=REF)
    index = svc.get_index()
    broken = index.opportunities[opportunity].copy()
    broken["evidence_references"] = []
    object.__setattr__(index, "opportunities", {opportunity: broken})
    with pytest.raises(ProductError, match="no evidence reference"):
        index.assert_invariants()


def test_the_index_rejects_an_opportunity_whose_problem_is_absent(svc):
    problem = _problem(svc)["problem_id"]
    opportunity = svc.register_opportunity(problem, title="A walkthrough",
                                           evidence_references=REF)
    index = svc.get_index()
    object.__setattr__(index.problem_index, "problems", {})
    with pytest.raises(ProductError, match="references unrecorded problem"):
        index.assert_invariants()


def test_a_resolver_catches_a_reference_the_owning_subsystem_lacks(svc):
    problem = _problem(svc)["problem_id"]
    svc.register_opportunity(problem, title="A walkthrough",
                             evidence_references=REF)
    index = svc.get_index()
    index.assert_invariants(resolver=lambda ref: True)
    with pytest.raises(ProductError, match="which the owning subsystem does "
                                           "not hold"):
        index.assert_invariants(resolver=lambda ref: False)


def test_lineage_answers_proposal_to_opportunity_to_problem_to_evidence(svc):
    problem = _problem(svc)["problem_id"]
    opportunity = svc.register_opportunity(problem, title="A walkthrough",
                                           evidence_references=REF)
    proposal = svc.draft_proposal(
        opportunity, candidate_solution="Add a guided first run",
        tradeoffs=["adds a surface to maintain"], risks=["users skip it"],
        known=["two entities churned"], unknown=["whether guidance is causal"],
        assumptions=["time to first value drives retention"])
    lineage = svc.lineage(proposal)
    assert lineage["proposal_id"] == proposal
    assert lineage["opportunity_id"] == opportunity
    assert lineage["problem_id"] == problem
    assert lineage["affected_customers"] == ["E1", "E2"]
    assert lineage["evidence"][0]["reference"]["kind"] == "crm_fact"


def test_lineage_marks_an_unresolved_hop_rather_than_hiding_it(svc):
    problem = _problem(svc)["problem_id"]
    opportunity = svc.register_opportunity(problem, title="A walkthrough",
                                           evidence_references=REF)
    proposal = svc.draft_proposal(
        opportunity, candidate_solution="Add a guided first run",
        tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
        assumptions=["a"])
    index = svc.get_index()
    lineage = index.lineage(proposal)          # no resolver supplied
    assert lineage["evidence"][0]["resolution"].startswith("unresolved")


def test_the_index_is_never_written_by_a_model(svc):
    """Only deterministic code produces an index entry. Checked over the
    parsed CODE rather than the file text, so a docstring explaining the
    rule does not accidentally satisfy or break it."""
    import ast
    import inspect

    from intent_engine.product import index as index_module

    tree = ast.parse(inspect.getsource(index_module))
    identifiers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr.lower())
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            identifiers.add(module.lower())
            identifiers.update(alias.name.lower() for alias in node.names)

    for banned in ("llm_client", "call_tool", "prompt_version",
                   "model_version", "anthropic", "draft_with_model"):
        assert banned not in identifiers, banned

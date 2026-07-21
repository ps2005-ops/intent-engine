"""T020 proposals, solution sets, spec drafts, and the proposal graph.

Known / unknown / assumptions are mandatory; specs are bounded to nine
sections with checkable criteria; the graph carries eight typed edges
with no cycles and no orphans.
0 model calls. 0 network.
"""
import pytest

from intent_engine.product import (
    PROPOSAL_EDGES, ProductError, ProductService, SPEC_SECTIONS,
    assert_graph_invariants, build_proposal, build_spec_draft, detect_cycles,
    sequence, spec_debt_report,
)
from intent_engine.product.specs import assert_checkable
from intent_engine.product.records import STATUS_RETIRED

AS_OF = "2026-07-21T00:00:00+00:00"
REF = [{"kind": "crm_fact", "ref_id": "crm.churned:E1", "crm_entity_id": "E1"}]

GOOD_SPEC = {
    "goals": ["reduce the time to first value"],
    "non_goals": ["redesigning pricing"],
    "requirements": ["the walkthrough is skippable"],
    "constraints": ["no change to the signup flow"],
    "acceptance_criteria": [
        "the walkthrough records a completion event for at least 1 account",
        "the skip control emits a skip event"],
    "unknowns": ["the UX of the walkthrough is undecided"],
    "dependencies": [], "risks": ["users skip it"],
    "open_questions": ["how many steps"],
}


@pytest.fixture()
def rig(tmp_path):
    svc = ProductService(tmp_path / "product.jsonl")
    problem = svc.record_problem(
        statement="Customers stop before reaching first value",
        evidence_references=REF, why_now="the facts are current",
        what_changes_if_ignored="the pattern repeats",
        first_observed_at=AS_OF, affected_customers=["E1", "E2"])
    opportunity = svc.register_opportunity(
        problem["problem_id"], title="A guided first run",
        evidence_references=REF, work_category="customer_work")
    return svc, problem["problem_id"], opportunity


def _draft(svc, opportunity, solution="Add a guided first run", **over):
    kwargs = dict(candidate_solution=solution,
                  tradeoffs=["adds a surface to maintain"],
                  risks=["users skip it"], known=["two entities churned"],
                  unknown=["whether guidance is causal"],
                  assumptions=["time to first value drives retention"],
                  open_questions=["what counts as first value"])
    kwargs.update(over)
    return svc.draft_proposal(opportunity, **kwargs)


# =============================================================================
# Proposals — known / unknown / assumptions all mandatory
# =============================================================================

@pytest.mark.parametrize("missing", ["known", "unknown", "assumptions"])
def test_known_unknown_and_assumptions_are_each_mandatory(missing):
    kwargs = dict(candidate_solution="do the thing", tradeoffs=["t"],
                  risks=["r"], known=["k"], unknown=["u"], assumptions=["a"])
    kwargs[missing] = []
    with pytest.raises(ProductError,
                       match=f"{missing} is mandatory and separately stored"):
        build_proposal(**kwargs)


def test_a_proposal_claiming_no_unknowns_is_rejected():
    with pytest.raises(ProductError, match="hiding them"):
        build_proposal(candidate_solution="do the thing", tradeoffs=["t"],
                       risks=["r"], known=["k"], unknown=[], assumptions=["a"])


@pytest.mark.parametrize("missing", ["tradeoffs", "risks"])
def test_tradeoffs_and_risks_are_mandatory(missing):
    kwargs = dict(candidate_solution="do the thing", tradeoffs=["t"],
                  risks=["r"], known=["k"], unknown=["u"], assumptions=["a"])
    kwargs[missing] = []
    with pytest.raises(ProductError, match=f"{missing} is mandatory"):
        build_proposal(**kwargs)


def test_the_three_are_stored_separately_not_merged():
    body = build_proposal(candidate_solution="do the thing", tradeoffs=["t"],
                          risks=["r"], known=["k1"], unknown=["u1"],
                          assumptions=["a1"])
    assert body["known"] == ["k1"]
    assert body["unknown"] == ["u1"]
    assert body["assumptions"] == ["a1"]
    assert body["candidate"] is True


def test_a_proposal_carrying_banned_language_is_rejected():
    with pytest.raises(ProductError, match="overclaims"):
        build_proposal(candidate_solution="This is clearly the best approach",
                       tradeoffs=["t"], risks=["r"], known=["k"],
                       unknown=["u"], assumptions=["a"])


def test_certainty_language_is_blocked_where_the_evidence_is_conflicting():
    with pytest.raises(ProductError, match="certainty language"):
        build_proposal(candidate_solution="This will certainly fix retention",
                       tradeoffs=["t"], risks=["r"], known=["k"],
                       unknown=["u"], assumptions=["a"],
                       evidence_label="CONFLICTING")


def test_an_unknown_work_category_is_rejected():
    with pytest.raises(ProductError, match="unknown work_category"):
        build_proposal(candidate_solution="x", tradeoffs=["t"], risks=["r"],
                       known=["k"], unknown=["u"], assumptions=["a"],
                       work_category="vibes")


# =============================================================================
# Versions and solution sets
# =============================================================================

def test_a_revision_is_a_new_version_and_prior_versions_stay_retrievable(rig):
    svc, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    version = svc.revise_proposal(
        proposal, candidate_solution="Add a shorter guided first run",
        tradeoffs=["fewer steps"], risks=["less context"], known=["k"],
        unknown=["u"], assumptions=["a"], reason="narrowed the scope")
    assert version == 2
    assert svc.get_proposal(proposal, 1)["candidate_solution"] \
        == "Add a guided first run"
    assert svc.get_proposal(proposal, 2)["candidate_solution"] \
        == "Add a shorter guided first run"
    assert svc.get_proposal(proposal)["proposal_version"] == 2


def test_one_problem_carries_a_solution_set_of_competing_proposals(rig):
    svc, problem, opportunity = rig
    solution_set = svc.open_solution_set(problem, name="first-value")
    a = _draft(svc, opportunity, "Add a guided first run",
               solution_set_id=solution_set)
    b = _draft(svc, opportunity, "Send a lifecycle email sequence",
               solution_set_id=solution_set)
    svc.record_alternative(a, b, reason="two routes to the same problem")
    state = svc.get_state()
    assert sorted(state.solution_sets[solution_set]["proposal_ids"]) \
        == sorted([a, b])
    from intent_engine.product import solution_set_report
    report = solution_set_report(svc.get_index(), problem)
    assert report["proposal_count"] == 2


# =============================================================================
# Retirement is not rejection
# =============================================================================

@pytest.mark.parametrize("reason", ["invalidated", "outdated", "replaced"])
def test_a_proposal_can_be_retired_for_a_recorded_reason(rig, reason):
    svc, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    svc.retire_proposal(proposal, reason=reason, detail="superseded by data")
    proposal_state = svc.get_state().proposals[proposal]
    assert proposal_state["status"] == STATUS_RETIRED
    assert proposal_state["retired_reason"] == reason
    # history is retained
    assert any(r.event_type == "product.proposal_drafted"
               for r in svc.store.for_proposal(proposal))


def test_an_unrecognised_retirement_reason_is_refused(rig):
    svc, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    with pytest.raises(ProductError, match="retirement reason is one of"):
        svc.retire_proposal(proposal, reason="we changed our minds")


# =============================================================================
# Spec drafts — bounded on purpose
# =============================================================================

def test_a_spec_draft_holds_only_the_nine_permitted_sections():
    draft = build_spec_draft(GOOD_SPEC)
    assert set(SPEC_SECTIONS) <= set(draft)
    assert len(SPEC_SECTIONS) == 9


@pytest.mark.parametrize("field", ["implementation", "estimate", "assignee",
                                   "file_paths", "code", "schema", "due_date",
                                   "story_points", "timeline"])
def test_an_execution_field_is_rejected_structurally(field):
    sections = dict(GOOD_SPEC)
    sections[field] = ["something"]
    with pytest.raises(ProductError, match="is rejected"):
        build_spec_draft(sections)


def test_a_section_outside_the_boundary_is_rejected():
    sections = dict(GOOD_SPEC)
    sections["marketing_plan"] = ["x"]
    with pytest.raises(ProductError, match="outside that boundary"):
        build_spec_draft(sections)


@pytest.mark.parametrize("criterion", [
    "the feature works well",
    "the page is fast",
    "the flow is intuitive",
    "it is user-friendly",
    "the result feels right",
])
def test_an_unfalsifiable_acceptance_criterion_is_rejected(criterion):
    with pytest.raises(ProductError, match="states a feeling"):
        assert_checkable(criterion)


def test_a_criterion_with_no_checkable_condition_is_rejected():
    with pytest.raises(ProductError, match="no checkable condition"):
        assert_checkable("the onboarding flow gets better over time")


def test_a_checkable_criterion_is_accepted():
    assert_checkable("the endpoint returns exit code 0 for a valid payload")
    assert_checkable("the log contains at least 1 completion event")


def test_a_spec_requires_goals_criteria_and_unknowns():
    for missing in ("goals", "acceptance_criteria", "unknowns"):
        sections = dict(GOOD_SPEC)
        sections[missing] = []
        with pytest.raises(ProductError):
            build_spec_draft(sections)


# =============================================================================
# Spec debt
# =============================================================================

def test_spec_debt_is_derived_from_unknowns_deterministically():
    sections = dict(GOOD_SPEC)
    sections["unknowns"] = [
        "the UX of the walkthrough is undecided",
        "the data model for progress is undecided",
        "whether an experiment settles the step count",
        "whether customers want this at all",
        "something nobody has classified"]
    report = spec_debt_report(build_spec_draft(sections))
    assert report["total"] == 5
    assert set(report["by_kind"]) == {"need_ux", "need_architecture",
                                      "need_experiment",
                                      "need_customer_validation",
                                      "need_research"}
    assert report == spec_debt_report(build_spec_draft(sections))


def test_spec_debt_travels_with_the_spec_into_the_log(rig):
    svc, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    spec = svc.draft_spec(proposal, GOOD_SPEC)
    recorded = [r for r in svc.store.read_all()
                if r.event_type == "product.spec_debt_recorded"]
    assert recorded and recorded[0].payload["kind"] == "need_ux"
    assert svc.get_spec_debt(spec)["total"] == 1


# =============================================================================
# The proposal graph
# =============================================================================

def test_all_eight_edge_types_are_declared():
    assert PROPOSAL_EDGES >= {"addresses", "supports", "depends_on", "blocks",
                              "alternative_to", "implements", "supported_by",
                              "supersedes"}


def test_derived_edges_cannot_be_recorded_separately(rig):
    svc, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    svc.record_edge("addresses", proposal, "P-other")
    with pytest.raises(ProductError, match="derived edge"):
        svc.get_index()


def test_every_proposal_addresses_exactly_one_problem(rig):
    svc, problem, opportunity = rig
    proposal = _draft(svc, opportunity)
    graph = svc.get_index().graph
    addressed = graph.out_edges(proposal, "addresses")
    assert len(addressed) == 1 and addressed[0]["to"] == problem


def test_every_opportunity_has_at_least_one_evidence_edge(rig):
    svc, _, opportunity = rig
    _draft(svc, opportunity)
    graph = svc.get_index().graph
    assert graph.out_edges(opportunity, "supported_by")


def test_a_dependency_cycle_is_detected(rig):
    svc, _, opportunity = rig
    a = _draft(svc, opportunity, "Add a guided first run")
    b = _draft(svc, opportunity, "Send a lifecycle email sequence")
    svc.record_edge("depends_on", a, b)
    svc.record_edge("depends_on", b, a)
    with pytest.raises(ProductError, match="dependency cycles"):
        svc.get_index().assert_invariants()


def test_detect_cycles_is_deterministic():
    edges = [{"edge": "depends_on", "from": "A", "to": "B"},
             {"edge": "depends_on", "from": "B", "to": "C"},
             {"edge": "depends_on", "from": "C", "to": "A"}]
    assert detect_cycles(edges) == detect_cycles(edges)
    assert detect_cycles(edges)


def test_alternative_to_is_symmetric(rig):
    svc, _, opportunity = rig
    a = _draft(svc, opportunity, "Add a guided first run")
    b = _draft(svc, opportunity, "Send a lifecycle email sequence")
    svc.record_edge("alternative_to", a, b)      # one direction only
    with pytest.raises(ProductError, match="relation is symmetric"):
        svc.get_index().assert_invariants()
    svc.record_edge("alternative_to", b, a)
    assert svc.get_index().assert_invariants()["invariants"] == "ok"


def test_alternative_to_is_never_combined_with_a_dependency(rig):
    svc, _, opportunity = rig
    a = _draft(svc, opportunity, "Add a guided first run")
    b = _draft(svc, opportunity, "Send a lifecycle email sequence")
    svc.record_alternative(a, b)
    svc.record_edge("depends_on", a, b)
    with pytest.raises(ProductError, match="both alternatives and"):
        svc.get_index().assert_invariants()


def test_a_superseded_proposal_keeps_its_history_and_its_edges(rig):
    svc, _, opportunity = rig
    a = _draft(svc, opportunity, "Add a guided first run")
    b = _draft(svc, opportunity, "Add a shorter guided first run")
    svc.record_edge("supersedes", b, a)
    svc.retire_proposal(a, reason="replaced", detail="superseded by b")
    index = svc.get_index()
    assert index.assert_invariants()["invariants"] == "ok"
    assert index.graph.in_edges(a, "supersedes")
    assert index.proposals[a]["status"] == STATUS_RETIRED
    assert svc.get_proposal(a, 1)["candidate_solution"] \
        == "Add a guided first run"


def test_an_implements_edge_points_at_a_knowledge_item(rig):
    svc, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    svc.record_edge("implements", proposal, "K-mechanism-1")
    index = svc.get_index()
    assert index.graph.nodes["K-mechanism-1"]["type"] == "knowledge_item"
    assert index.assert_invariants()["invariants"] == "ok"


def test_sequence_respects_dependencies_and_is_deterministic(rig):
    svc, _, opportunity = rig
    a = _draft(svc, opportunity, "First")
    b = _draft(svc, opportunity, "Second")
    c = _draft(svc, opportunity, "Third")
    svc.record_edge("depends_on", c, b)
    svc.record_edge("depends_on", b, a)
    graph = svc.get_index().graph
    order = sequence(graph, [a, b, c])
    assert order.index(a) < order.index(b) < order.index(c)
    assert order == sequence(graph, [c, b, a])


def test_a_graph_with_no_orphans_passes_its_invariants(rig):
    svc, _, opportunity = rig
    _draft(svc, opportunity)
    report = assert_graph_invariants(svc.get_index().graph)
    assert report["invariants"] == "ok"
    assert report["proposals"] == 1

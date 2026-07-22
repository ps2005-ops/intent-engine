"""T021 Decision Index, decision graph, and the DecisionService resolver
boundary.

The index folds from the executive log alone, resolves decision state
through DecisionService, and mirrors nothing. 0 model calls. 0 network.
"""
import ast
import inspect
from pathlib import Path

import pytest

from intent_engine.executive import (
    ExecutiveError, ExecutiveService, build_index, detect_cycles,
    order_by_dependency,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REF = [{"kind": "product_proposal", "ref_id": "P1"}]


@pytest.fixture()
def svc(tmp_path):
    return ExecutiveService(tmp_path / "executive.jsonl")


def _candidate(svc, origin_id="o1", references=None):
    return svc.register_candidate(
        references=references or REF,
        origin={"kind": "manual", "origin_id": origin_id})


def _full_package(svc, candidate, *, decision_id=None):
    svc.build_context(candidate, decision_horizon="short_term",
                      decision_class="product",
                      resolved_inputs={"crm:E1": {"category": "AT_RISK"}})
    package = svc.draft_package(candidate, decision_question="commit?",
                                references=REF, unknowns=["u"])
    svc.add_option(package, label="A", benefits=["b"], costs=["c"],
                   risks=["r"], unknowns=["u"], reversibility="easy")
    svc.add_option(package, label="B", benefits=["b"], costs=["c"],
                   risks=["r"], unknowns=["u"], reversibility="moderate")
    return package


# =============================================================================
# Determinism, orphans, invariants
# =============================================================================

def test_the_index_rebuilds_deterministically(svc):
    candidate = _candidate(svc, "o1")
    _full_package(svc, candidate)
    rows = svc.store.read_all()
    first, second = build_index(rows), build_index(rows)
    assert first.candidates == second.candidates
    assert first.packages == second.packages
    assert first.assert_invariants() == second.assert_invariants()


def test_the_index_is_never_written_by_a_model(svc):
    """Checked over the parsed CODE, so a docstring cannot satisfy or break
    it."""
    from intent_engine.executive import index as index_module
    tree = ast.parse(inspect.getsource(index_module))
    identifiers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr.lower())
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            identifiers.add((getattr(node, "module", "") or "").lower())
            identifiers.update(a.name.lower() for a in node.names)
    for banned in ("llm_client", "call_tool", "prompt_version",
                   "model_version", "anthropic", "draft_with_model"):
        assert banned not in identifiers, banned


def test_a_candidate_with_no_reference_is_an_orphan(svc):
    candidate = _candidate(svc, "o1")
    index = svc.get_index()
    broken = dict(index.candidates[candidate])
    broken["references"] = []
    object.__setattr__(index, "candidates", {candidate: broken})
    with pytest.raises(ExecutiveError, match="resolves to nothing"):
        index.assert_invariants()


def test_a_resolver_catches_a_reference_the_owner_lacks(svc):
    candidate = _candidate(svc, "o1")
    index = svc.get_index()
    index.assert_invariants(reference_resolver=lambda ref: True)
    with pytest.raises(ExecutiveError, match="the owning subsystem does not "
                                            "hold"):
        index.assert_invariants(reference_resolver=lambda ref: False)


def test_full_reasoning_chain_lineage(svc):
    candidate = _candidate(svc, "o1", references=[
        {"kind": "product_proposal", "ref_id": "P1"},
        {"kind": "research_package", "ref_id": "R1", "request_id": "REQ1"}])
    package = _full_package(svc, candidate)
    lineage = svc.lineage(package)
    assert lineage["candidate_id"] == candidate
    assert lineage["package_id"] == package
    kinds = {e["reference"]["kind"] for e in lineage["references"]}
    assert kinds == {"product_proposal", "research_package"}


# =============================================================================
# The DecisionService resolver boundary — the load-bearing design decision
# =============================================================================

def test_the_index_folds_from_the_executive_log_alone(svc):
    """No executive index code reads another store: build_index takes rows
    and resolves decision state only through an injected resolver."""
    candidate = _candidate(svc, "o1")
    _full_package(svc, candidate)
    # build_index over rows produces a complete index with no services
    rows = svc.store.read_all()
    index = build_index(rows)
    assert index.assert_invariants()["invariants"] == "ok"
    # lineage without a resolver marks the decision hop unresolved rather
    # than reading a store
    package_id = list(index.packages)[0]
    lineage = index.lineage(package_id)
    assert "unresolved" in str(lineage["decision"]).lower() \
        or lineage["decision"] == "unresolved: no decision is linked yet"


def test_no_executive_module_writes_or_mirrors_decision_state():
    """Refusal C: prove no executive code writes decisions.db or
    materializes decision state into its own log."""
    package = REPO_ROOT / "src/intent_engine/executive"
    for source_file in sorted(package.glob("*.py")):
        text = source_file.read_text()
        assert "decisions.db" not in text, source_file.name
        # the only decision writes permitted are REFERENCES: an
        # executive.decision_linked event stores a decision_id, never a
        # decision's status/owner/execution fields
        assert "DecisionCreated" not in text, source_file.name
        assert "record_event(" not in text, source_file.name
        assert ".create_decision(" not in text, source_file.name


def test_decision_state_is_resolved_not_stored(tmp_path):
    """The index carries a decision_id; status is fetched from
    DecisionService at read time, so it is never a stored copy that can
    drift."""
    from intent_engine.core.decision_record import DecisionService
    decisions = DecisionService(str(tmp_path / "decisions.db"))
    svc = ExecutiveService(tmp_path / "executive.jsonl",
                           decision_service=decisions)
    candidate = _candidate(svc, "o1")
    package = _full_package(svc, candidate)
    svc.request_review(package)
    svc.record_review(package, disposition="accepted", actor_id="founder",
                      chosen_option_id="A")
    decision = decisions.create_decision("founder", idempotency_key="d1")
    svc.link_decision(package, decision.decision_id, actor_id="founder")

    # the executive log stores the id only — not the status
    rows = svc.store.for_package(package)
    linked = [r for r in rows if r.event_type == "executive.decision_linked"]
    assert linked[0].payload == {"decision_id": decision.decision_id}
    # lineage resolves status live through DecisionService
    lineage = svc.lineage(package)
    assert lineage["decision"]["resolved_by"] == \
        "decision_service.get_current_state"
    assert lineage["decision"]["decision_id"] == decision.decision_id


# =============================================================================
# The decision graph
# =============================================================================

def test_derived_edges_cannot_be_recorded(svc):
    candidate = _candidate(svc, "o1")
    with pytest.raises(ExecutiveError, match="unknown recorded edge type"):
        svc.record_edge("renders", "a", "b")


def test_a_dependency_cycle_is_detected(svc):
    a = _candidate(svc, "o1")
    b = _candidate(svc, "o2")
    svc.record_edge("depends_on", a, b)
    svc.record_edge("depends_on", b, a)
    with pytest.raises(ExecutiveError, match="dependency cycles"):
        svc.get_index().assert_invariants()


def test_a_pair_cannot_both_depend_and_invalidate(svc):
    a = _candidate(svc, "o1")
    b = _candidate(svc, "o2")
    svc.record_edge("depends_on", a, b)
    svc.record_edge("invalidates", a, b)
    with pytest.raises(ExecutiveError, match="dependency-linked and "
                                            "invalidating"):
        svc.get_index().assert_invariants()


def test_the_cascade_is_reported_not_applied(svc):
    a = _candidate(svc, "o1")
    b = _candidate(svc, "o2")
    c = _candidate(svc, "o3")
    svc.record_edge("invalidates", a, b)
    svc.record_edge("enables", a, c)
    cascade = svc.get_index().graph.cascade_from(a)
    assert cascade["would_invalidate"] == [b]
    assert cascade["would_enable"] == [c]
    assert "not an applied one" in cascade["note"]


def test_detect_cycles_is_deterministic():
    edges = [{"edge": "depends_on", "from": "A", "to": "B"},
             {"edge": "depends_on", "from": "B", "to": "A"}]
    assert detect_cycles(edges) == detect_cycles(edges)
    assert detect_cycles(edges)


def test_order_by_dependency_respects_edges(svc):
    a = _candidate(svc, "o1")
    b = _candidate(svc, "o2")
    svc.record_edge("depends_on", b, a)
    graph = svc.get_index().graph
    order = order_by_dependency(graph, [a, b])
    assert order.index(a) < order.index(b)
    assert order == order_by_dependency(graph, [b, a])

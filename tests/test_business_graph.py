"""The substrate has to refuse dishonest shapes, not just store honest ones.

The business graph exists so one question can be answered: what did this
decision rest on, and did the outcome bear it out? These tests drive that
question end to end, and then check the refusals -- because a graph that will
hold a node with no provenance, or quietly drop contradicting evidence, is
worse than no graph. It would make an unsourced guess and a filed fact
indistinguishable six months later.
"""
import pytest

from intent_engine.business_graph import (
    ACTION,
    ASSUMES,
    ASSUMPTION,
    CALIBRATES,
    CONTRADICTS,
    DECIDES,
    DECISION,
    EVIDENCE,
    HYPOTHESIS,
    INFORMS,
    OUTCOME,
    PRODUCES,
    SUPERSEDES,
    SUPPORTS,
    BusinessGraph,
    Edge,
    GraphError,
    Node,
    assert_graph_invariants,
    detect_cycles,
)


def _n(node_id, kind, label="x", source="test-fixture"):
    return Node(node_id=node_id, kind=kind, label=label, source=source)


@pytest.fixture
def hiring_decision():
    """A hiring decision with evidence on both sides, and an outcome.

    Modelled on the question the assistant must answer -- "should we hire?" --
    because a substrate that cannot carry that question is not the substrate
    this product needs.
    """
    graph = BusinessGraph()
    for node_id, kind in [
            ("ev-pipeline", EVIDENCE), ("ev-churn", EVIDENCE),
            ("as-demand-holds", ASSUMPTION), ("hy-scale-sales", HYPOTHESIS),
            ("dec-hire-5", DECISION), ("act-open-reqs", ACTION),
            ("out-q3-attainment", OUTCOME)]:
        graph.add_node(_n(node_id, kind))

    graph.add_edge(Edge("ev-pipeline", "as-demand-holds", SUPPORTS, True))
    # The contradicting side is present ON PURPOSE.
    graph.add_edge(Edge("ev-churn", "as-demand-holds", CONTRADICTS, True))
    graph.add_edge(Edge("hy-scale-sales", "as-demand-holds", ASSUMES, True))
    graph.add_edge(Edge("hy-scale-sales", "dec-hire-5", INFORMS, True))
    graph.add_edge(Edge("dec-hire-5", "act-open-reqs", DECIDES, True))
    graph.add_edge(Edge("act-open-reqs", "out-q3-attainment", PRODUCES, True))
    graph.add_edge(Edge("out-q3-attainment", "as-demand-holds", CALIBRATES,
                        True))
    return graph


def test_a_decision_can_name_everything_it_rests_on(hiring_decision):
    """The query no single subsystem could answer before this existed."""
    prov = hiring_decision.provenance_of("dec-hire-5")
    assert prov["hypotheses"] == ["hy-scale-sales"]
    assert prov["assumptions"] == ["as-demand-holds"]
    assert prov["supporting_evidence"] == ["ev-pipeline"]
    assert prov["actions"] == ["act-open-reqs"]
    assert prov["outcomes"] == ["out-q3-attainment"]
    assert prov["calibrates"] == ["as-demand-holds"]


def test_contradicting_evidence_is_returned_beside_the_supporting_kind(
        hiring_decision):
    """Never hide contradictions. Filtering these would be the most damaging
    thing this structure could do."""
    prov = hiring_decision.provenance_of("dec-hire-5")
    assert prov["contradicting_evidence"] == ["ev-churn"]


def test_a_node_with_evidence_on_both_sides_is_reported_as_contested(
        hiring_decision):
    assert [n.node_id for n in hiring_decision.contested()] == [
        "as-demand-holds"]


def test_an_assumption_nobody_checked_is_surfaced_not_assumed_true():
    graph = BusinessGraph()
    graph.add_node(_n("as-market-grows", ASSUMPTION))
    assert [n.node_id for n in graph.unsupported(ASSUMPTION)] == [
        "as-market-grows"]


# --- the refusals -----------------------------------------------------------

def test_a_node_without_provenance_cannot_be_built():
    """"Never fake evidence" is unenforceable if an unsourced node can exist."""
    with pytest.raises(GraphError, match="where it came from"):
        Node(node_id="ev-1", kind=EVIDENCE, label="something", source="")


def test_a_recorded_edge_needs_an_author_but_a_derived_one_does_not():
    """Recorded edges are judgments; judgments have authors. Derived edges are
    recomputed from their source rows, so they cannot drift and need none."""
    Edge("a", "b", SUPPORTS, derived=True)                    # fine
    with pytest.raises(GraphError, match="no source"):
        Edge("a", "b", SUPPORTS, derived=False)
    Edge("a", "b", SUPPORTS, derived=False, source="analyst-2026-08")


def test_an_unknown_kind_is_refused_rather_than_stored():
    with pytest.raises(GraphError, match="unknown node kind"):
        Node(node_id="x", kind="salesforce_opportunity", label="x",
             source="crm")
    with pytest.raises(GraphError, match="unknown edge kind"):
        Edge("a", "b", "pinged_about", derived=True)


def test_an_edge_to_a_node_that_does_not_exist_is_refused():
    """A dangling edge renders as a real relationship and resolves to nothing."""
    graph = BusinessGraph()
    graph.add_node(_n("dec-1", DECISION))
    with pytest.raises(GraphError, match="unknown node"):
        graph.add_edge(Edge("dec-1", "act-missing", DECIDES, True))


def test_one_id_cannot_be_two_different_things():
    graph = BusinessGraph()
    graph.add_node(_n("thing", DECISION))
    with pytest.raises(GraphError, match="already a decision"):
        graph.add_node(_n("thing", OUTCOME))


def test_a_causal_cycle_is_refused():
    """Time only runs one way. A decision that supersedes the decision which
    supersedes it is a modelling error nothing downstream can render."""
    graph = BusinessGraph()
    graph.add_node(_n("dec-a", DECISION))
    graph.add_node(_n("dec-b", DECISION))
    graph.add_edge(Edge("dec-a", "dec-b", SUPERSEDES, True))
    graph.add_edge(Edge("dec-b", "dec-a", SUPERSEDES, True))
    with pytest.raises(GraphError, match="causal cycles"):
        assert_graph_invariants(graph)


def test_invariants_report_the_shape_without_raising(hiring_decision):
    report = assert_graph_invariants(hiring_decision)
    assert report["nodes"] == 7
    assert report["derived_edges"] == 7
    assert report["recorded_edges"] == 0
    assert report["contested_nodes"] == ["as-demand-holds"]


def test_detect_cycles_matches_the_graphs_this_generalises():
    edges = [Edge("a", "b", ASSUMES, True), Edge("b", "c", ASSUMES, True),
             Edge("c", "a", ASSUMES, True)]
    found = detect_cycles(edges, ASSUMES)
    assert found and found[0][0] == found[0][-1]

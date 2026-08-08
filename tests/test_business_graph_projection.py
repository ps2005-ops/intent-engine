"""A real subsystem writes into the graph, or the graph is a fourth truth.

The business graph shipped with no producers: nothing in `src/` imported it
except its own test. That is worse than not having built it, because from the
outside it looks like integration. This drives the first real projection --
a company-ingestion run -- and asserts the properties that stop the graph
becoming another place where facts live.
"""
import pytest

from intent_engine.business_graph import (
    ASSUMPTION,
    DECISION,
    CONTRADICTS,
    DOCUMENT,
    EVIDENCE,
    HYPOTHESIS,
    INFORMS,
    SUPPORTS,
    Node,
    assert_graph_invariants,
)
from intent_engine.business_graph.projections import (
    from_ingestion_run,
    link_decision,
)

RUN = "run-001"

RETRIEVED = [
    {"source_id": "src-a", "final_url": "https://acme.example/investors",
     "title": "Acme investor relations", "source_class": "investor",
     "retrieval_status": "OK"},
    {"source_id": "src-b", "final_url": "https://acme.example/press",
     "title": "Acme press", "source_class": "company_owned",
     "retrieval_status": "OK"},
]

REPORT = {
    "observations": [
        {"observation_id": "obs-src-a", "excerpt": "Enterprise deals grew.",
         "source_url": "https://acme.example/investors", "date": "2026-05-01",
         "source_class": "investor"},
        {"observation_id": "obs-src-b", "excerpt": "Self-serve is the focus.",
         "source_url": "https://acme.example/press", "date": "2026-04-02",
         "source_class": "company_owned"},
    ],
    "hypotheses": [
        {"hypothesis_id": "hyp-upmarket", "statement": "Acme is moving upmarket.",
         "confidence": "low", "supporting_observation_ids": ["obs-src-a"]},
    ],
    "blind_spots": [
        {"blind_spot_id": "blind-enterprise-vs-smb",
         "observed_tension": "An enterprise push runs alongside a self-serve "
                             "promise.",
         "why_it_may_matter": "Complexity that wins enterprise erodes the "
                              "ease that won the base.",
         "supporting_observation_ids": ["obs-src-b"]},
    ],
}


@pytest.fixture
def graph():
    return from_ingestion_run(run_id=RUN, retrieved=RETRIEVED, report=REPORT)


def test_a_run_becomes_documents_evidence_hypotheses_and_assumptions(graph):
    assert len(graph.of_kind(DOCUMENT)) == 2
    assert len(graph.of_kind(EVIDENCE)) == 2
    assert len(graph.of_kind(HYPOTHESIS)) == 1
    assert len(graph.of_kind(ASSUMPTION)) == 1


def test_evidence_under_a_blind_spot_contradicts_rather_than_supports(graph):
    """A blind spot exists to surface the uncomfortable reading. Filing its
    evidence as support would bury the only thing it is for."""
    edges = graph.in_edges("blind-enterprise-vs-smb", CONTRADICTS)
    assert [e.src for e in edges] == ["obs-src-b"]
    assert not graph.in_edges("blind-enterprise-vs-smb", SUPPORTS)


def test_the_hypothesis_is_linked_to_the_evidence_that_was_cited(graph):
    assert [e.src for e in graph.in_edges("hyp-upmarket", SUPPORTS)] == [
        "obs-src-a"]


def test_a_citation_to_evidence_the_run_never_retrieved_is_dropped():
    """A dangling claim is not a link. It renders as a real relationship and
    resolves to nothing, so the projection refuses to draw it."""
    report = dict(REPORT, hypotheses=[
        {"hypothesis_id": "hyp-x", "statement": "Claim.",
         "supporting_observation_ids": ["obs-does-not-exist"]}])
    graph = from_ingestion_run(run_id=RUN, retrieved=RETRIEVED, report=report)
    assert graph.in_edges("hyp-x", SUPPORTS) == []
    assert_graph_invariants(graph)          # and it is still structurally sound


def test_projection_is_a_pure_function_of_its_inputs():
    """Run twice, get the same graph. This is what keeps the projection from
    becoming a source of truth that can disagree with the log."""
    a = from_ingestion_run(run_id=RUN, retrieved=RETRIEVED, report=REPORT)
    b = from_ingestion_run(run_id=RUN, retrieved=RETRIEVED, report=REPORT)
    assert {n.node_id for n in a.nodes} == {n.node_id for n in b.nodes}
    assert {e.key() for e in a.edges} == {e.key() for e in b.edges}


def test_a_bounded_run_still_projects_its_documents():
    """A run that never cleared the evidence bar has real documents, and the
    absence of hypotheses above them is exactly what a founder should see."""
    graph = from_ingestion_run(run_id=RUN, retrieved=RETRIEVED, report=None)
    assert len(graph.of_kind(DOCUMENT)) == 2
    assert graph.of_kind(HYPOTHESIS) == []


def test_every_projected_edge_is_derived(graph):
    """Nothing in a retrieval log is a judgment, so nothing here may claim to
    be one."""
    assert all(e.derived for e in graph.edges)
    report = assert_graph_invariants(graph)
    assert report["recorded_edges"] == 0


def test_a_decision_link_is_recorded_and_needs_an_author(graph):
    """The opposite case: no evidence implies a founder decided anything, so
    this one IS a judgment and carries its author."""
    graph.add_node(Node(node_id="dec-1", kind=DECISION,
                        label="Move upmarket", source="founder"))
    link_decision(graph, decision_id="dec-1",
                  hypothesis_ids=["hyp-upmarket"], author="founder:pratham")
    edge = graph.in_edges("dec-1", INFORMS)[0]
    assert edge.derived is False
    assert edge.source == "founder:pratham"

    with pytest.raises(ValueError, match="needs an author"):
        link_decision(graph, decision_id="dec-1",
                      hypothesis_ids=["hyp-upmarket"], author="")


def test_the_projected_run_answers_the_provenance_question(graph):
    """The question no subsystem could answer alone."""
    graph.add_node(Node(node_id="dec-1", kind=DECISION, label="Move upmarket",
                        source="founder"))
    link_decision(graph, decision_id="dec-1",
                  hypothesis_ids=["hyp-upmarket"], author="founder:pratham")
    prov = graph.provenance_of("dec-1")
    assert prov["hypotheses"] == ["hyp-upmarket"]
    assert prov["assumptions"] == ["blind-enterprise-vs-smb"]
    assert prov["supporting_evidence"] == ["obs-src-a"]
    assert prov["contradicting_evidence"] == ["obs-src-b"]

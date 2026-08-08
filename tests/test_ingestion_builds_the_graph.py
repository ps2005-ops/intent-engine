"""Ingestion must actually build the graph, not merely be able to.

The previous cycle shipped a projection function and claimed A1 was closed.
It was not: `grep business_graph src/` returned nothing outside the graph
package, because the only caller was the projection's own test. A producer
with no callers is integration in appearance only.

So this test does not call the projection. It drives a REAL ingestion run --
discovery, approval, fetch, compose -- and then asks the service for its
graph. If ingestion ever stops building one, this fails, which is the whole
point: the previous claim passed every test in the suite while being false.
"""
import pytest

from intent_engine.business_graph import DOCUMENT, EVIDENCE, HYPOTHESIS
from intent_engine.business_graph.model import assert_graph_invariants
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import (
    FounderIntelligenceService,
)
from tests.test_strategic_intelligence import _live_transport


@pytest.fixture
def finished_run(tmp_path):
    """A real run, composed the way the product composes one."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=_live_transport, resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Acme", website="https://acme.example",
                        user_id="user-1", as_of="2026-07-24T00:00:00+00:00")
    run_id = run["run_id"]
    candidates = ci.discover(run_id)
    picked, seen = [], set()
    for candidate in candidates:
        cls = candidate.get("source_class")
        if cls not in seen:
            seen.add(cls)
            picked.append(candidate["candidate_id"])
    ci.approve(run_id, user_id="user-1", approved_ids=picked, rejected_ids=[])
    ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi)
    return ci, run_id, result


def test_a_real_run_produces_a_populated_graph(finished_run):
    """THE GATE. Not "the projection works" -- "ingestion builds it"."""
    ci, run_id, result = finished_run
    graph = ci.business_graph(run_id, result)
    assert graph.of_kind(DOCUMENT), "no documents reached the graph"
    assert graph.nodes, "ingestion produced an empty graph"


def test_the_graph_carries_the_evidence_the_report_cited(finished_run):
    ci, run_id, result = finished_run
    report = result.get("strategic_report") or {}
    cited = {o["observation_id"] for o in (report.get("observations") or ())
             if isinstance(o, dict) and o.get("observation_id")}
    if not cited:
        pytest.skip("this fixture composed no observations to check")
    graph = ci.business_graph(run_id, result)
    assert {n.node_id for n in graph.of_kind(EVIDENCE)} >= cited


def test_the_graph_is_structurally_sound(finished_run):
    ci, run_id, result = finished_run
    report = assert_graph_invariants(ci.business_graph(run_id, result))
    # Everything ingestion derives is derived; nothing here is a judgment.
    assert report["recorded_edges"] == 0


def test_rebuilding_gives_the_same_graph(finished_run):
    """A projection, not a second store. Two calls cannot disagree."""
    ci, run_id, result = finished_run
    a, b = ci.business_graph(run_id, result), ci.business_graph(run_id, result)
    assert {n.node_id for n in a.nodes} == {n.node_id for n in b.nodes}
    assert {e.key() for e in a.edges} == {e.key() for e in b.edges}


def test_a_run_with_no_report_still_yields_its_documents(finished_run):
    """A bounded run has real documents. Their presence, with no hypotheses
    above them, is exactly what a founder should be able to see."""
    ci, run_id, _ = finished_run
    graph = ci.business_graph(run_id, {"strategic_report": None})
    assert graph.of_kind(DOCUMENT)
    assert graph.of_kind(HYPOTHESIS) == []


def test_the_service_is_a_real_caller_of_the_graph_package():
    """A1 in one assertion: something outside the graph package imports it.

    This is the check the previous cycle would have failed while reporting
    success.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    callers = [p for p in root.rglob("*.py")
               if "business_graph" in p.read_text()
               and "business_graph" not in str(p)]
    assert callers, "no subsystem outside the graph package uses it"

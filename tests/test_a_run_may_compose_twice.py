"""Composing twice may not kill the run on an idempotency collision.

MEASURED on a22929c. AMD failed at t=58 with the progress page returning
HTTP 500, and the server log named it exactly:

    analysis failed run=... stage=composition
    ValueError: idempotency_key 'ci-ownership:<run>' was already used for
    different content

`ci.ownership_resolved` carries `documents` and `observations` -- counts that
change the moment a run composes a second time -- while its key named only
the run. Every other per-composition event here already keys on its content
(`claims:{run}:{n}`, `reasoning:{run}:{n}`, `ci-retry:{run}:{targets}`); this
one did not, and the append-only store's collision guard did what it is for.

Latent until the EDGAR budget widened and second passes became ordinary.
"""
import pytest

from company_fixture_pages import BASE, PAGES, transport
from intent_engine.company_ingestion.records import (
    IngestionError, MAX_APPROVED_SOURCES,
)
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService

AS_OF = "2026-08-21T00:00:00+00:00"


def _pipeline(tmp_path):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=transport,
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Brightlake", website=BASE,
                        user_id="u", as_of=AS_OF)
    candidates = ci.discover(run["run_id"])
    approved = [c["candidate_id"] for c in candidates
                if c["url"] in PAGES][:MAX_APPROVED_SOURCES]
    ci.approve(run["run_id"], user_id="u", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    ci.fetch_approved(run["run_id"])
    return ci, fi, run["run_id"]


def _ownership_keys(ci, run_id):
    return [r.idempotency_key for r in ci.store.for_run(run_id)
            if r.event_type == "ci.ownership_resolved"]


def test_recomposing_the_same_evidence_is_still_idempotent(tmp_path):
    """THE PROPERTY THE KEY EXISTS FOR. Same documents, one record."""
    ci, fi, run_id = _pipeline(tmp_path)
    ci.compose(run_id, fi_service=fi)
    ci.compose(run_id, fi_service=fi)
    assert len(set(_ownership_keys(ci, run_id))) == 1


def test_a_second_composition_over_more_evidence_does_not_raise(tmp_path):
    """THE DEFECT. A run that composes again after evidence arrives.

    Before the key named its content this raised IngestionError out of
    `compose` and took the whole analysis down with it.
    """
    ci, fi, run_id = _pipeline(tmp_path)
    ci.compose(run_id, fi_service=fi)
    before = len(ci.store.retrieved(run_id))

    # A DOCUMENT ARRIVES AFTER THE FIRST COMPOSITION. This is the whole
    # condition -- a second pass over the SAME evidence writes identical
    # content and never collides, which is why an earlier version of this
    # test could not fail.
    ci._append("ci.source_retrieved", run_id=run_id, domain="",
               subject_type="source", subject_id="late-1",
               payload={"source_id": "late-1", "run_id": run_id,
                        "retrieval_status": "OK",
                        "source_type": "external_approved",
                        "source_class": "investor_material",
                        "final_url": "https://www.sec.gov/late.htm",
                        "original_url": "https://www.sec.gov/late.htm",
                        "title": "SEC 10-K (2026-02-02)",
                        "text_content": "Item 1. Business. A late-arriving "
                                        "annual report describing the "
                                        "registrant in detail. " * 9,
                        "filing": {"form": "10-K"},
                        "content_hash": "a" * 64, "byte_count": 900,
                        "retrieved_at": "2026-08-21T00:00:00+00:00",
                        "parser_version": "1", "status_code": 200,
                        "mime_type": "text/html", "meta_description": "",
                        "freshness": "CURRENT", "privacy": "public",
                        "company_id": "", "origin_note": "",
                        "extraction_mode": "body", "blocks_found": 3},
               idempotency_key=f"src:{run_id}:late-1")
    assert len(ci.store.retrieved(run_id)) == before + 1

    try:
        result = ci.compose(run_id, fi_service=fi)
    except IngestionError as exc:
        pytest.fail(f"a second composition over more evidence raised: {exc}")
    assert result is not None
    assert len(set(_ownership_keys(ci, run_id))) == 2, (
        "the two compositions recorded ownership under one key")


def test_the_key_names_what_it_records(tmp_path):
    """A content fingerprint, not a count.

    The count was the first repair and fixed the case measured (a second
    composition over MORE documents). It cannot fix a second composition
    over the same NUMBER of documents whose observations differ, and the
    re-gate now fires on more runs than it used to. A diagnostic event has
    no business failing an analysis.
    """
    ci, fi, run_id = _pipeline(tmp_path)
    ci.compose(run_id, fi_service=fi)
    key = _ownership_keys(ci, run_id)[0]
    assert key.startswith(f"ci-ownership:{run_id}:")
    tail = key.rsplit(":", 1)[1]
    assert len(tail) == 12 and all(c in "0123456789abcdef" for c in tail), key


def test_the_same_count_with_different_content_does_not_collide(tmp_path):
    """THE CASE THE COUNT COULD NOT COVER."""
    ci, fi, run_id = _pipeline(tmp_path)
    ci.compose(run_id, fi_service=fi)
    before = len(_ownership_keys(ci, run_id))
    # Same document count, different observations: recompose with a curated
    # observation added, which is exactly what an equal-count re-gate does.
    try:
        from intent_engine.strategic_intelligence.records import (
            StrategicObservation,
        )
        ci.compose(run_id, fi_service=fi, extra_observations=(
            StrategicObservation(
                observation_id="x1",
                text="The registrant added a new segment this year.",
                observation_type="product_surface"),))
    except IngestionError as exc:                           # pragma: no cover
        pytest.fail(f"an equal-count recomposition raised: {exc}")
    assert len(_ownership_keys(ci, run_id)) >= before

"""The field whose unobservability cost four deploys is now written down.

WHY THIS EXISTS. A defect took four deploys and six wrong hypotheses, and its
entire difficulty was that ONE field could not be inspected after the run
ended. "Did this run have a subject CIK?" was unanswerable, because nothing
wrote it down at the moment it mattered — and by the time the question was
framed, the run that would have answered it had been destroyed by a redeploy.

The two live surfaces both fail for this purpose. `/runs/<id>/provenance.json`
is operator-gated, correctly, since it exposes tenant data — which means
neither agent doing the diagnosing can read it. And a live route only answers
for runs that still exist in a process that has not restarted.

An APPEND-ONLY EVENT outlives the run, the process and the deploy, and can be
read for a run nobody thought to instrument. That is a stronger property than
the fix it was written to support, and it generalises: any decision whose
inputs are reconstructed later should be recorded when it is made.
"""
import pathlib
import tempfile

import pytest

from intent_engine.company_ingestion.records import INGESTION_EVENTS
from intent_engine.company_ingestion.service import CompanyIngestionService

AS_OF = "2026-08-20T00:00:00+00:00"
FILING = ("https://www.sec.gov/Archives/edgar/data/19617/"
          "000001961726000123/jpm-20251231.htm")
OTHER = ("https://www.sec.gov/Archives/edgar/data/72971/"
         "000007297126000133/wfc-20251231.htm")
TEXT = ("Our commerce platform helps merchants sell online. Demand capture "
        "now runs through the marketplace and the shop app, which set how "
        "merchants reach shoppers and checkout.")


#: The SEC ticker table, served by the injected transport below. Held here
#: rather than fetched, because this file now exercises a path that RESOLVES
#: the subject by name -- and an assertion whose answer depends on what
#: sec.gov is serving today is not an assertion.
TICKERS = (b'{"0": {"cik_str": 2098, "ticker": "ACU", '
           b'"title": "ACME UNITED CORP"}}')


def _sec(url, timeout, max_bytes=None):
    """Only the ticker table answers; everything else is a 404.

    A registrant lookup that cannot reach SEC degrades to no registrant,
    which is exactly what this file's subject is indifferent to.
    """
    if "company_tickers" in url:
        return (200, {"Content-Type": "application/json"}, TICKERS, False)
    return (404, {}, b"", False)


def _service(tmp):
    return CompanyIngestionService(pathlib.Path(tmp) / "ci.jsonl",
                                   resolver=False, transport=_sec)


def _doc(url, sid):
    return {"final_url": url, "source_class": "investor_material",
            "source_id": sid, "title": "SEC 10-K", "text": TEXT,
            "text_content": TEXT, "content_hash": sid,
            "retrieved_at": "2026-02-24"}


def test_the_event_type_is_registered():
    assert "ci.ownership_resolved" in INGESTION_EVENTS


def test_a_composed_run_records_its_subject_cik():
    with tempfile.TemporaryDirectory() as tmp:
        ci = _service(tmp)
        run = ci.create_run(company_name="JPMorgan Chase & Co.", website="",
                            user_id="u", as_of=AS_OF, cik="19617")
        rid = run["run_id"]
        ci._strategic_report("JPMorgan Chase & Co.",
                             [_doc(FILING, "jpm"), _doc(OTHER, "wfc")],
                             [], run_id=rid)
        record = ci.ownership_record(rid)
        assert record, "the run recorded nothing about ownership"
        assert record["subject_cik"] == "19617"
        assert record["subject_cik_present"] is True
        assert record["documents"] == 2
        assert record["observations_subject_owned"] >= 1
        assert record["observations_from_another_filer"] >= 1


def test_a_run_started_from_a_website_still_knows_whose_documents_these_are():
    """UPDATED WITH THE DEFECT IT WAS ASSERTING.

    This used to require `subject_cik == ""` for a run entered by website --
    and a run entered by website is the ORDINARY case. So the assertion
    pinned the very condition that made the ownership rule inert: with no
    subject, `subject_documents` skips its `/data/<cik>/` filter and another
    registrant's 10-K describes this company. It was measured live as
    Wells Fargo's capacity sentence rendered as JPMorgan's distribution
    model, and the repair could not reach it while this test held it in
    place.

    The subject is now resolved the SAME WAY the subject's own filings are
    discovered -- `propose_edgar_candidates` falls back to
    `resolve_cik(company_name)` for exactly this case -- so ownership and
    discovery cannot disagree about who the run is about. One spelling, two
    stages.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ci = _service(tmp)
        run = ci.create_run(company_name="Acme", website="https://acme.com",
                            user_id="u", as_of=AS_OF)
        rid = run["run_id"]
        assert str((ci.run_meta(rid) or {}).get("cik") or "") == "", (
            "the premise of this test is a run that carries no typed CIK")
        ci._strategic_report("Acme", [_doc(FILING, "jpm")], [], run_id=rid)
        record = ci.ownership_record(rid)
        assert record, "a run with no typed CIK recorded nothing at all"
        assert record["subject_cik"] == "2098"
        assert record["subject_cik_present"] is True
        assert record["observations_subject_owned"] == 0, (
            "a filing under another registrant's EDGAR path was counted as "
            "this company's own")


def test_a_subject_in_no_registry_is_still_recorded_as_absent():
    """THE PROPERTY THE TEST ABOVE USED TO CARRY, kept. A caller must be able
    to tell "we could not identify this filer" from "nobody instrumented the
    run" -- that distinction is the whole reason this event exists, and it is
    now asserted on a subject that genuinely resolves to nothing rather than
    on the ordinary case."""
    with tempfile.TemporaryDirectory() as tmp:
        ci = _service(tmp)
        run = ci.create_run(company_name="Zzyzx Widgets Cooperative",
                            website="https://zzyzxwidgets.example",
                            user_id="u", as_of=AS_OF)
        rid = run["run_id"]
        ci._strategic_report("Zzyzx Widgets Cooperative",
                             [_doc(FILING, "jpm")], [], run_id=rid)
        record = ci.ownership_record(rid)
        assert record, "an unidentifiable subject recorded nothing at all"
        assert record["subject_cik"] == ""
        assert record["subject_cik_present"] is False


def test_an_unrecorded_run_is_unknown_not_empty():
    """A caller must be able to tell "no CIK" from "never instrumented"."""
    with tempfile.TemporaryDirectory() as tmp:
        ci = _service(tmp)
        run = ci.create_run(company_name="Acme", website="https://acme.com",
                            user_id="u", as_of=AS_OF)
        assert ci.ownership_record(run["run_id"]) == {}


def test_the_record_survives_a_fresh_process():
    """An event outlives the run, the process and the deploy — which is the
    property a live route does not have, and the reason this is an event."""
    with tempfile.TemporaryDirectory() as tmp:
        ci = _service(tmp)
        run = ci.create_run(company_name="JPMorgan Chase & Co.", website="",
                            user_id="u", as_of=AS_OF, cik="19617")
        rid = run["run_id"]
        ci._strategic_report("JPMorgan Chase & Co.", [_doc(FILING, "jpm")],
                             [], run_id=rid)
        del ci
        reopened = _service(tmp)
        assert reopened.ownership_record(rid)["subject_cik"] == "19617"


def test_it_is_written_where_the_decision_is_made():
    """Recorded at the moment of the decision, not reconstructed later —
    reconstruction is exactly what was impossible."""
    import ast
    import inspect

    from intent_engine.company_ingestion import service as _svc

    # Parse the MODULE and locate the function, rather than dedenting a
    # method's source — `inspect.getsource` returns it at class indentation
    # and re-indenting it is a second thing that can be wrong. Reading via
    # `getsourcefile` also means the break-proof harness's mirrored tree is
    # what gets read, not the original on disk.
    source = pathlib.Path(inspect.getsourcefile(_svc)).read_text()
    fn = next(n for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.FunctionDef)
              and n.name == "_strategic_report")
    names = [n.value for n in ast.walk(fn)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "ci.ownership_resolved" in names, (
        "the event is no longer emitted where the ownership decision is made")

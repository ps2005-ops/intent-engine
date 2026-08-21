"""Evidence arriving after a gate saw NOTHING must still be judged.

MEASURED live on 5e1218e, Meta Platforms, Inc.:

    compose=?  stored=9  regated=no   ->  TRUE_EVIDENCE_SCARCITY

Nine documents in the store and a gate that judged none of them. The re-gate
exists for exactly this and did not run, because its precondition was

    seen = readiness_inputs.get("documents_at_compose")
    if isinstance(seen, int):

and `readiness_inputs` is absent precisely when `compose` takes its early
"no approved source could be retrieved" return -- that path returns before
the field is recorded. A guard keyed on the presence of an instrument is not
a guard: it is switched off by the failure it was written for.
"""
import threading

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from company_fixture_pages import BASE, PAGES, transport


def _app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=transport, resolver=False)


def _run_with_documents(app, n):
    """A run whose store holds `n` retrieved documents."""
    run = app.ci.create_run(company_name="Brightlake", website=BASE,
                            user_id="u", as_of="2026-08-21T00:00:00+00:00")
    rid = run["run_id"]
    for i in range(n):
        app.ci._append(
            "ci.source_retrieved", run_id=rid, domain="brightlake-example.com",
            subject_type="source", subject_id=f"s{i}",
            payload={"source_id": f"s{i}", "run_id": rid,
                     "retrieval_status": "OK",
                     "source_type": "external_approved",
                     "source_class": "investor_material",
                     "final_url": f"https://www.sec.gov/{i}.htm",
                     "original_url": f"https://www.sec.gov/{i}.htm",
                     "title": f"SEC 10-K ({i})",
                     "text_content": f"Item 1. Business. Filing {i} describes "
                                     f"the registrant's operations. " * 9,
                     "filing": {"form": "10-K"},
                     "content_hash": f"{i:064d}", "byte_count": 900,
                     "retrieved_at": "2026-08-21T00:00:00+00:00",
                     "parser_version": "1", "status_code": 200,
                     "mime_type": "text/html", "meta_description": "",
                     "freshness": "CURRENT", "privacy": "public",
                     "company_id": "", "origin_note": "",
                     "extraction_mode": "body", "blocks_found": 3},
            idempotency_key=f"src:{rid}:s{i}")
    return rid


def _regate(app, rid, result):
    """Drive only the re-gate branch of `_compose`, with its inputs."""
    seen = (result.get("readiness_inputs") or {}).get("documents_at_compose")
    if seen is None:
        seen = 0
    stored = len(app.ci.store.retrieved(rid))
    return isinstance(seen, int) and stored > seen


def _regated(app, rid, early_result):
    """Run the REAL re-gate branch of `_compose` and say whether it fired.

    Drives `WebApp._compose` with `compose_with_quality` returning the early
    "no approved source could be retrieved" dict -- the exact shape that has
    no `readiness_inputs`. Asserting against a copy of the branch's logic in
    this file is what let an earlier version of this test stay green while
    the branch was switched off.
    """
    app.ci.compose_with_quality = lambda rid_, **kw: dict(early_result)
    result = app._compose(rid)
    return "regated_from" in (result.get("readiness_inputs") or {})


def test_a_gate_that_recorded_nothing_is_still_re_gated(tmp_path):
    """THE DEFECT. No `readiness_inputs`, nine documents, and it must look."""
    app = _app(tmp_path)
    rid = _run_with_documents(app, 9)
    assert _regated(app, rid, {
        "status": "FAILED",
        "reason": "no approved source could be retrieved"}) is True


def test_an_empty_store_does_not_trigger_a_pointless_pass(tmp_path):
    """THE CONTROL. Nothing arrived, so there is nothing new to judge."""
    app = _app(tmp_path)
    rid = _run_with_documents(app, 0)
    assert _regated(app, rid, {
        "status": "FAILED", "reason": "no approved source"}) is False


def test_a_gate_that_already_saw_everything_is_not_re_gated(tmp_path):
    app = _app(tmp_path)
    rid = _run_with_documents(app, 9)
    assert _regated(app, rid, {
        "readiness_inputs": {"documents_at_compose": 9}}) is False


def test_a_gate_that_saw_some_is_re_gated_as_before(tmp_path):
    app = _app(tmp_path)
    rid = _run_with_documents(app, 9)
    assert _regated(app, rid, {
        "readiness_inputs": {"documents_at_compose": 1}}) is True


def test_the_running_code_treats_a_missing_field_as_zero(tmp_path):
    """READ THE DEPLOYED SOURCE, so a normalisation that moves is noticed."""
    import inspect
    src = inspect.getsource(WebApp._compose)
    assert "if seen is None:" in src, "the re-gate no longer normalises"
    assert "seen = 0" in src

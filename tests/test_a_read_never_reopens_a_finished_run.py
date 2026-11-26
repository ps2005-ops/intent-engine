"""A finished run stays finished when it is read, or recomposed, again.

MEASURED on the prospect-100 store (Nov 9): Matillion's run reached PARTIAL at
21:02:57. A page read at 22:25:55, in a fresh process, recomposed it through
the quality gate, whose retry loop appended two `-> DISCOVERING_SOURCES`
transitions -- and nothing writes a terminal state after a recompose, because
the analysis worker is what does that and a read has no worker. 8 of 95 runs
read as "discovering sources" for good, and their decks redirected forever.

Two repairs, each pinned at its caller (a guard must mutate the caller):
  * a READ composes with no retry passes: it neither fetches nor transitions;
  * the ledger does not let a retry pass recorded after the answer reopen it
    (records already on disk, and the retry button's synchronous recompose).
Positive controls beside each: retries still run, and still count, on the
first live pass.
"""
from __future__ import annotations

from test_golden_demo_companies import GOLDEN, _http_error
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService

AS_OF = "2026-07-27T00:00:00+00:00"


def _filings_only_run(tmp_path):
    """A run approved on filings only, so the gate has families to chase."""
    company = GOLDEN[0]
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=company.transport(), resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name=company.name, website=company.base,
                           user_id="u1", as_of=AS_OF)["run_id"]
    candidates = ci.discover(run_id)
    filings = [c["candidate_id"] for c in candidates
               if c.get("source_class") == "investor_material"]
    ci.approve(run_id, user_id="u1", approved_ids=filings, rejected_ids=[])
    ci.fetch_approved(run_id)
    return ci, fi, run_id


def _transitions(ci, run_id):
    return [r.payload for r in ci.store.for_run(run_id)
            if r.event_type == "ci.run_transitioned"]


def test_a_retry_pass_after_the_answer_does_not_reopen_the_run(tmp_path):
    """The exact Nov 9 sequence: the live compose writes PARTIAL under an
    idempotent key; a recompose's retry rows are new, its PARTIAL is refused
    as a duplicate, so the retries land AFTER the answer and nothing follows."""
    ci, fi, run_id = _filings_only_run(tmp_path)
    ci.compose_with_quality(run_id, fi_service=fi)          # the live pass
    assert ci.store.run_state(run_id) == "PARTIAL"
    n = len(_transitions(ci, run_id))
    # Force new retry targets the way a later recompose plans them.
    domain = ci.run_meta(run_id)["domain"]
    ci._append("ci.run_transitioned", run_id=run_id, domain=domain,
               payload={"to": "DISCOVERING_SOURCES", "retry_pass": 1,
                        "reason": "missing evidence families: customers",
                        "targets": ["cand-later"]},
               idempotency_key=f"t-late-retry:{run_id}")
    rows = _transitions(ci, run_id)
    assert len(rows) == n + 1 and rows[-1]["to"] == "DISCOVERING_SOURCES"
    assert ci.store.run_state(run_id) == "PARTIAL"


def test_a_retry_pass_before_the_answer_still_counts(tmp_path):
    """POSITIVE CONTROL: on the live first pass a retry IS the run's state."""
    ci, fi, run_id = _filings_only_run(tmp_path)
    domain = ci.run_meta(run_id)["domain"]
    ci._append("ci.run_transitioned", run_id=run_id, domain=domain,
               payload={"to": "DISCOVERING_SOURCES", "retry_pass": 1,
                        "reason": "missing evidence families: product",
                        "targets": ["cand-x"]},
               idempotency_key=f"t-retry:{run_id}")
    assert ci.store.run_state(run_id) == "DISCOVERING_SOURCES"


def test_a_non_retry_transition_after_the_answer_still_applies(tmp_path):
    """POSITIVE CONTROL: only a retry annotation is ignored; a real state
    change recorded after a terminal state is still the run's state."""
    ci, fi, run_id = _filings_only_run(tmp_path)
    domain = ci.run_meta(run_id)["domain"]
    ci._transition(run_id, domain, "PARTIAL")
    ci._transition(run_id, domain, "FAILED")
    assert ci.store.run_state(run_id) == "FAILED"


def _app(tmp_path):
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=GOLDEN[0].transport(), resolver=False)


def _record_compose_calls(app, monkeypatch):
    seen = []

    def fake(run_id, **kwargs):
        seen.append(kwargs)
        return {"strategic_report": None}
    monkeypatch.setattr(app.ci, "compose_with_quality", fake)
    return seen


def test_the_reader_recompose_asks_for_no_retry_passes(tmp_path, monkeypatch):
    """THE CALLER: `_recompose_for_reader` -- the path every page read takes
    on a cache miss -- must tell the gate it may not gather."""
    app = _app(tmp_path)
    seen = _record_compose_calls(app, monkeypatch)
    app._recompose_for_reader("01RUN")
    assert seen and seen[-1].get("max_passes") == 0


def test_the_analysis_worker_keeps_its_retry_budget(tmp_path, monkeypatch):
    """POSITIVE CONTROL: the live composition is not bounded to zero."""
    app = _app(tmp_path)
    seen = _record_compose_calls(app, monkeypatch)
    app._compose("01RUN")
    assert seen and "max_passes" not in seen[-1]


def test_a_reader_compose_writes_no_transition_and_fetches_nothing(tmp_path):
    """END TO END on the service: composing with the reader's budget leaves
    the ledger's transitions exactly as they were and calls no transport."""
    company = GOLDEN[0]
    calls = []
    real = company.transport()

    def counting(url, timeout):
        calls.append(url)
        return real(url, timeout)
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=counting,
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name=company.name, website=company.base,
                           user_id="u1", as_of=AS_OF)["run_id"]
    candidates = ci.discover(run_id)
    filings = [c["candidate_id"] for c in candidates
               if c.get("source_class") == "investor_material"]
    ci.approve(run_id, user_id="u1", approved_ids=filings, rejected_ids=[])
    ci.fetch_approved(run_id)
    ci.compose_with_quality(run_id, fi_service=fi)          # the live pass
    assert ci.store.run_state(run_id) == "PARTIAL"
    before, fetched = len(_transitions(ci, run_id)), len(calls)
    ci.compose_with_quality(run_id, fi_service=fi, max_passes=0)
    assert len(_transitions(ci, run_id)) == before
    assert len(calls) == fetched
    assert ci.store.run_state(run_id) == "PARTIAL"

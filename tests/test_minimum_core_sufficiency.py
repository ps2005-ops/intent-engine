"""§5/§7/§8: CORE stops blocking when the evidence contract is met.

Every test here asserts that the EXPENSIVE WORK DID NOT HAPPEN, not that a
status field says it did not. A test asserting `sufficiency is not None` would
pass while acquisition fetched every source — which is exactly how a warm path
shipped 48% faster this session while composing no report at all.
"""
from __future__ import annotations

import datetime as dt

import pytest

from intent_engine.company_ingestion import sufficiency
from intent_engine.company_ingestion.readiness import READY_FOR_FULL_REPORT
from intent_engine.company_ingestion.service import CompanyIngestionService


ENGLISH = ("The company reported revenue growth in the quarter ending "
           "March 2026 and described its operating segments in detail. ")


def _doc(url, source_type, text=None, *, status="OK",
         source_class="company_owned"):
    """A retrieved document. Text is made UNIQUE per URL on purpose:
    `readiness.usable_documents` dedupes on the text itself, so identical
    bodies would collapse six documents into one and the test would be
    measuring the fixture."""
    body = (text or ENGLISH) + f" This page is {url}. " + ENGLISH * 4
    # `original_url`, and DELIBERATELY NO `url` KEY. `retrieved_record` writes
    # `original_url`/`final_url` and never `url`; a fixture carrying `url` let
    # `_subject_filing_present` pass here while returning False on every real
    # document in production.
    return {"original_url": url, "final_url": url, "retrieval_status": status,
            "text_content": body, "source_type": source_type,
            "source_class": source_class, "freshness": "CURRENT",
            "title": source_type, "modified_date": "2026-06-01"}


class _Recorder:
    """A transport that records every URL it is asked for."""

    def __init__(self, body=b"<html><body><p>" + ENGLISH.encode() + b"</p></body></html>"):
        self.urls = []
        self.body = body

    def __call__(self, url, timeout, max_bytes=2_000_000):
        self.urls.append(url)
        return (200, {"content-type": "text/html"}, self.body, False)


def _service(tmp_path, transport):
    return CompanyIngestionService(tmp_path / "ci.jsonl", transport=transport,
                                   resolver=False)


def _run_with_candidates(ci, n):
    run = ci.create_run(company_name="Widget Co", website="https://widget.example",
                        user_id="u", as_of=dt.date.today().isoformat())
    run_id = run["run_id"] if isinstance(run, dict) else run
    ids = []
    for i in range(n):
        url = f"https://widget.example/page-{i}"
        candidate_id = f"cand-{i:012d}"
        ci._append("ci.candidate_discovered", run_id=run_id,
                   domain=ci.run_meta(run_id)["domain"],
                   subject_type="candidate", subject_id=candidate_id,
                   payload={"candidate_id": candidate_id, "url": url,
                            "source_type": ["identity", "product", "investor",
                                            "customers", "strategy",
                                            "independent", "commercial",
                                            "talent"][i % 8],
                            "source_class": "company_owned",
                            "discovery_method": "known_path",
                            "company_id": ci.run_meta(run_id)["domain"],
                            "rank": i, "availability": "PROPOSED",
                            "same_domain": True,
                            "why_relevant": "test evidence"},
                   idempotency_key=f"cand:{run_id}:{candidate_id}")
        ids.append(candidate_id)
    ci.approve(run_id, user_id="u", approved_ids=ids, rejected_ids=[])
    return run_id, ids


def test_a_satisfied_probe_stops_the_network(tmp_path):
    """THE POINT OF THE CHANGE: fewer URLs are actually requested."""
    transport = _Recorder()
    ci = _service(tmp_path, transport)
    run_id, ids = _run_with_candidates(ci, 14)

    calls = {"n": 0}

    def probe(documents):
        calls["n"] += 1
        return {"sufficient": True, "reason": "test contract met",
                "documents": len(documents)}

    result = ci.fetch_approved(run_id, sufficiency_probe=probe)

    assert calls["n"] >= 1, "the probe was never consulted"
    assert result["deferred"], "nothing was deferred"
    # THE ASSERTION THAT MATTERS. Not the status field: the request ledger.
    assert len(transport.urls) < 14, (
        f"acquisition still requested {len(transport.urls)} URLs after the "
        f"contract was satisfied")
    assert len(result["ok"]) + len(result["deferred"]) + \
        len(result["failed"]) == 14


def test_without_a_probe_every_source_is_still_fetched(tmp_path):
    """The batch path and every existing caller are untouched."""
    transport = _Recorder()
    ci = _service(tmp_path, transport)
    run_id, ids = _run_with_candidates(ci, 14)
    result = ci.fetch_approved(run_id)
    assert len(transport.urls) == 14
    assert result["deferred"] == []
    assert result["sufficiency"] is None


def test_an_unsatisfied_probe_fetches_everything(tmp_path):
    """A sparse company keeps acquiring: the stop is the contract, not a count."""
    transport = _Recorder()
    ci = _service(tmp_path, transport)
    run_id, ids = _run_with_candidates(ci, 14)
    result = ci.fetch_approved(
        run_id, sufficiency_probe=lambda docs: {"sufficient": False,
                                                "reason": "still thin"})
    assert len(transport.urls) == 14
    assert result["deferred"] == []


def test_deferred_sources_are_not_failures(tmp_path):
    """A deferred source is queued work, never a finding about the company."""
    transport = _Recorder()
    ci = _service(tmp_path, transport)
    run_id, ids = _run_with_candidates(ci, 14)
    result = ci.fetch_approved(
        run_id, sufficiency_probe=lambda docs: {"sufficient": True,
                                                "reason": "met"})
    failed_ids = {f.get("candidate_id") for f in result["failed"]}
    assert not (set(result["deferred"]) & failed_ids)
    assert not ci.store.failures(run_id), (
        "deferral recorded a retrieval failure, which would count against the "
        "company's source health for evidence we simply have not asked for yet")


def test_the_probe_uses_the_published_readiness_contract():
    """One definition of 'enough evidence', not two.

    BOTH DIRECTIONS. The first version of this test asserted only that a
    SATISFIED contract yields `sufficient`, so deleting the contract check
    entirely left it green — the mutation reported NOT_CAUGHT and was right
    to. What the contract is for is refusing, so the refusing case is the one
    that has to be pinned.
    """
    from intent_engine.company_ingestion.readiness import assess_readiness

    # Enough documents to clear the floor, and NOT enough evidence to pass:
    # five product pages are one family wearing five hats.
    thin = [_doc(f"https://x.example/p{i}", "product") for i in range(5)]
    assert assess_readiness(
        documents=thin,
        identity={"entity_resolved": True, "confidence": "HIGH",
                  "company_name": "X", "_profile": {}}
    )["state"] != READY_FOR_FULL_REPORT
    refused = sufficiency.evaluate(
        thin, identity={"entity_resolved": True, "confidence": "HIGH",
                        "company_name": "X", "_profile": {}})
    assert refused["sufficient"] is False, (
        "acquisition would have stopped on evidence the report gate refuses")
    assert refused["state"] != READY_FOR_FULL_REPORT

    documents = [
        _doc("https://x.example/about", "about"),
        _doc("https://x.example/products", "product"),
        _doc("https://x.example/investors", "blog"),
        _doc("https://x.example/customers", "customers"),
        _doc("https://x.example/pricing", "pricing"),
    ]
    identity = {"entity_resolved": True, "confidence": "HIGH",
                "company_name": "X", "_profile": {}}
    verdict = sufficiency.evaluate(documents, identity=identity)
    contract = assess_readiness(documents=documents, identity=identity)
    assert contract["state"] == READY_FOR_FULL_REPORT, "fixture is not the "\
        "satisfied case it claims to be"
    assert verdict["sufficient"] is (
        contract["state"] == READY_FOR_FULL_REPORT)


def test_the_floor_refuses_to_stop_on_almost_nothing():
    """A contract satisfied on two documents still does not stop acquisition."""
    identity = {"entity_resolved": True, "confidence": "HIGH",
                "company_name": "X", "_profile": {}}
    verdict = sufficiency.evaluate(
        [_doc("https://x.example/a", "about")],
        identity=identity)
    assert verdict["sufficient"] is False
    assert str(sufficiency.MIN_CORE_DOCUMENTS) in verdict["reason"]


def test_a_filer_waits_for_its_own_filing():
    """A third party's mention of the subject is not the subject's filing."""
    identity = {"entity_resolved": True, "confidence": "HIGH",
                "company_name": "X", "_profile": {}}
    documents = [
        _doc("https://x.example/about", "about"),
        _doc("https://x.example/products", "product"),
        _doc("https://x.example/customers", "customers"),
        _doc("https://x.example/pricing", "pricing"),
        _doc("https://x.example/investors", "blog"),
        _doc("https://www.sec.gov/Archives/edgar/data/999999/other.htm",
             "product", source_class="competitor"),
    ]
    # The readiness contract itself is satisfied here -- that is the point.
    # The only thing standing between this run and "sufficient" is that the
    # regulator holds a document in the SUBJECT'S name that nobody has read.
    from intent_engine.company_ingestion.readiness import assess_readiness
    assert assess_readiness(documents=documents,
                            identity=identity)["state"] == \
        READY_FOR_FULL_REPORT
    without = sufficiency.evaluate(documents, identity=identity,
                                   subject_cik="0000320193")
    assert without["sufficient"] is False
    assert "own EDGAR filing" in without["reason"]

    documents.append(_doc(
        "https://www.sec.gov/Archives/edgar/data/320193/aapl-10q.htm",
        "investor", ENGLISH))
    with_own = sufficiency.evaluate(documents, identity=identity,
                                    subject_cik="0000320193")
    assert with_own["sufficient"] is True


# ---------------------------------------------------------------------------
# §24: what happens to evidence CORE did not wait for.
# ---------------------------------------------------------------------------
def test_the_continuation_gets_a_fresh_budget_not_the_spent_one():
    """Deferral may not become deletion wearing a retrieval failure.

    `budget_for` returns 0.0 below MIN_USEFUL_FETCH_S, so a continuation
    handed the already-spent interactive deadline would refuse every deferred
    source as `deadline_exceeded` — recording a failure against the company
    for evidence nobody had asked for yet.
    """
    import time as _time

    from intent_engine.company_ingestion.deadline import (
        MIN_USEFUL_FETCH_S, Deadline,
    )
    from intent_engine.company_ingestion.records import CONNECT_TIMEOUT_S
    spent = Deadline.for_tier("tier1")
    spent.started_at = _time.monotonic() - 59.0        # 1s left of 60
    assert spent.budget_for(CONNECT_TIMEOUT_S) == 0.0

    fresh = Deadline.for_continuation("tier1")
    assert fresh.budget_for(CONNECT_TIMEOUT_S) >= MIN_USEFUL_FETCH_S
    # NOT unbounded: a continuation that never ends holds a worker on a
    # single-share instance for as long as a dead host cares to stall.
    assert fresh.total_s != float("inf")


def test_the_analysis_updated_event_is_registered(tmp_path):
    """The last new event type added to a producer and not to the registry
    made `_append` raise, a broad `except` swallow it, and every warm run
    silently perform full cold discovery."""
    from intent_engine.company_ingestion.records import INGESTION_EVENTS
    assert "ci.analysis_updated" in INGESTION_EVENTS

    ci = CompanyIngestionService(tmp_path / "ci.jsonl", resolver=False)
    run = ci.create_run(company_name="Widget Co",
                        website="https://widget.example", user_id="u",
                        as_of=dt.date.today().isoformat())
    run_id = run["run_id"] if isinstance(run, dict) else run
    ci.record_analysis_updated(run_id, fields=["thesis"], new_documents=3,
                               reason="later evidence")
    updates = ci.analysis_updates(run_id)
    assert updates and updates[0]["fields_changed"] == ["thesis"]
    assert updates[0]["new_documents"] == 3


def test_the_probe_resolves_a_cik_where_run_meta_has_none():
    """A run started from a website carries NO CIK, which is the ordinary case.

    Reading `meta["cik"]` made "wait for the subject's own filing" return True
    for every domain-entry run, so the condition never fired once. This pins
    the accessor the probe must use, by driving `_sufficiency_probe` and
    watching what it hands to `sufficiency.evaluate`.
    """
    from intent_engine.company_ingestion import sufficiency as _suff
    from intent_engine.webapp.app import WebApp

    seen = {}

    class _CI:
        def run_meta(self, _run_id):
            return {"domain": "apple.com", "company_name": "Apple Inc.",
                    "cik": ""}                     # the ordinary case

        def subject_cik(self, _meta):
            return "320193"                        # resolved by name

        def entity_identity(self, _run_id):
            return {"entity_resolved": True, "confidence": "HIGH",
                    "_profile": {}}

        class store:
            @staticmethod
            def failures(_run_id):
                return []

    app = WebApp.__new__(WebApp)
    app.ci = _CI()

    def _capture(documents, *, identity=None, failures=(), subject_cik="",
                 pending=0):
        seen["cik"] = subject_cik
        return {"sufficient": False, "reason": "captured"}

    original = _suff.evaluate
    _suff.evaluate = _capture
    try:
        app._sufficiency_probe("r1")([])
    finally:
        _suff.evaluate = original

    assert seen["cik"] == "320193", (
        f"the probe was handed {seen['cik']!r}; a guard that always sees an "
        f"empty CIK can never fire")


def test_every_deferred_source_is_retrieved_or_recorded_as_failed(tmp_path):
    """"Nothing is dropped" means ACCOUNTING, and only within one run.

    Comparing a CORE run against a separate FULL run cannot answer this: a
    host that answers once and refuses once is indistinguishable from
    deferral losing a source. MEASURED on Amazon — the cross-run comparison
    reported a lost family, and the within-run audit found all six deferred
    candidates accounted for, three retrieved and three recorded as
    `http_status`. A later run had the FULL path retrieve FEWER documents
    than the CORE path, which settles which instrument is measuring what.

    So the property is: after the continuation, every deferred candidate is
    either retrieved or carries a recorded failure. Neither is a silent drop.
    """
    transport = _Recorder()
    ci = _service(tmp_path, transport)
    run_id, ids = _run_with_candidates(ci, 14)

    stopped = {"yet": False}

    def probe(documents):
        if len(documents) >= 6:
            stopped["yet"] = True
            return {"sufficient": True, "reason": "contract met"}
        return {"sufficient": False, "reason": "thin"}

    first = ci.fetch_approved(run_id, sufficiency_probe=probe)
    deferred = list(first["deferred"])
    assert stopped["yet"] and deferred

    from intent_engine.company_ingestion.deadline import Deadline
    ci.fetch_approved(run_id, candidate_ids=deferred,
                      deadline=Deadline.for_continuation("tier1"))

    retrieved = {r["source_id"] for r in ci.store.retrieved(run_id)}
    failed = {f.get("candidate_id") for f in ci.store.failures(run_id)}
    dropped = [c for c in deferred
               if f"src-{c[5:]}" not in retrieved and c not in failed]
    assert not dropped, (
        f"{len(dropped)} deferred source(s) were neither retrieved nor "
        f"recorded as failed — deferral became deletion: {dropped}")
    # And the run ends holding everything the un-deferred path would have.
    assert len(retrieved) == 14

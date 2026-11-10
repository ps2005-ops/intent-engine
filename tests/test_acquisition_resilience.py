"""Break proofs for the evidence-acquisition layer.

Every proof drives a PRODUCTION call site -- `fetch_approved`,
`_recommended_candidate_ids`, `plan_retry`, `evidence_gaps` -- rather than a
helper written for the test. A proof that exercises only a helper cannot tell
the difference between a repair and a repair with no caller, which this
codebase has shipped before.
"""
from __future__ import annotations

import datetime
import urllib.error

import pytest

from intent_engine.company_ingestion import acquisition_memory as AM
from intent_engine.company_ingestion.acquisition_memory import (
    ALLOW, AcquisitionMemory, SKIP_HOST_OPEN, SKIP_KNOWN_FAILURE,
    classify_outcome,
)
from intent_engine.company_ingestion.quality import evidence_gaps
from intent_engine.company_ingestion.retry import plan_retry
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.webapp.app import WebApp


# --- helpers ----------------------------------------------------------------

def _service(tmp_path, transport, memory=None):
    """A service on the real production class with an injected transport."""
    return CompanyIngestionService(
        tmp_path / "ci.jsonl", transport=transport, resolver=False,
        acquisition_memory=(memory if memory is not None
                            else AcquisitionMemory(tmp_path / "mem")))


def _run(ci, name="Acme", site="https://acme.example"):
    run = ci.create_run(company_name=name, website=site, user_id="u",
                        as_of=datetime.date.today().isoformat())
    return run["run_id"]


def _candidate(ci, run_id, url, **kw):
    """Register one candidate through the store the service reads."""
    payload = {"candidate_id": f"cand-{abs(hash(url)) % 10**9}",
               "run_id": run_id, "url": url,
               "source_type": kw.get("source_type", "product"),
               "source_class": kw.get("source_class", "company_owned"),
               "discovery_method": kw.get("discovery_method", "known_path"),
               "same_domain": True, "availability": "UNVERIFIED",
               "title": kw.get("title", "t"), "why_useful": "u",
               "why_relevant": kw.get("why_relevant", "r")}
    payload.update({k: v for k, v in kw.items() if k not in payload})
    ci._append("ci.candidate_discovered", run_id=run_id,
               domain=ci.run_meta(run_id)["domain"], subject_type="candidate",
               subject_id=payload["candidate_id"], payload=payload,
               idempotency_key=f"c:{run_id}:{payload['candidate_id']}")
    return payload["candidate_id"]


def _html(body="<html><body><p>" + "word " * 80 + "</p></body></html>"):
    return (200, {"content-type": "text/html"}, body.encode(), False)


def _http_error(code):
    def _t(url, timeout, max_bytes=None):
        raise urllib.error.HTTPError(url, code, f"HTTP {code}", {}, None)
    return _t


# =============================================================================
# 1-2. transient vs permanent classification
# =============================================================================

def test_1_rate_limit_is_never_remembered_as_permanent():
    """429 means 'not now'. Remembering it would suppress a good host."""
    assert classify_outcome(ok=False, status=429,
                            failure_type="http_status") == (None, 0)
    for code in (500, 502, 503, 504):
        assert classify_outcome(ok=False, status=code,
                                failure_type="http_status")[0] is None


def test_2_transient_transport_failure_is_not_remembered():
    for kind in ("timeout", "connection", "host_unreachable",
                 "deadline_exceeded"):
        assert classify_outcome(ok=False, failure_type=kind) == (None, 0)


# =============================================================================
# 3. a blocked homepage must not stop SEC from being read
# =============================================================================

def test_3_blocked_company_host_does_not_stop_an_independent_host(tmp_path):
    def transport(url, timeout, max_bytes=None):
        if "acme.example" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        return _html()

    ci = _service(tmp_path, transport)
    run_id = _run(ci)
    blocked = _candidate(ci, run_id, "https://acme.example/about")
    other = _candidate(ci, run_id, "https://www.sec.gov/Archives/x.htm",
                       source_class="investor_material")
    ci.approve(run_id, user_id="u", approved_ids=[blocked, other],
               rejected_ids=[])
    out = ci.fetch_approved(run_id)
    urls = {r["original_url"] for r in out["ok"]}
    assert "https://www.sec.gov/Archives/x.htm" in urls
    assert out["status"] == "PARTIAL"


# =============================================================================
# 4-6. the memory frees a SLOT, not merely a request
# =============================================================================

def test_4_known_failure_is_not_requested_again(tmp_path):
    calls = []

    def transport(url, timeout, max_bytes=None):
        calls.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    memory = AcquisitionMemory(tmp_path / "mem")
    ci = _service(tmp_path, transport, memory=memory)
    run_id = _run(ci)
    dead = _candidate(ci, run_id, "https://acme.example/docs")
    ci.approve(run_id, user_id="u", approved_ids=[dead], rejected_ids=[])
    ci.fetch_approved(run_id)
    assert len(calls) == 1

    ci2 = _service(tmp_path, transport, memory=AcquisitionMemory(tmp_path / "mem"))
    run2 = _run(ci2, site="https://acme.example")
    dead2 = _candidate(ci2, run2, "https://acme.example/docs")
    ci2.approve(run2, user_id="u", approved_ids=[dead2], rejected_ids=[])
    out = ci2.fetch_approved(run2)
    assert len(calls) == 1, "a remembered 404 was requested again"
    assert out["failed"], "the skip must be recorded as an honest gap"
    assert "404" in out["failed"][0]["safe_message"]


def test_5_a_remembered_failure_frees_an_approved_slot(tmp_path):
    """THE POINT OF THE MEMORY. The slot is the scarce resource."""
    memory = AcquisitionMemory(tmp_path / "mem")
    candidates = [
        {"candidate_id": "cand-dead", "url": "https://acme.example/docs",
         "source_type": "product", "source_class": "company_owned",
         "discovery_method": "known_path", "why_relevant": ""},
        {"candidate_id": "cand-live", "url": "https://acme.example/platform",
         "source_type": "product", "source_class": "company_owned",
         "discovery_method": "known_path", "why_relevant": ""},
    ]
    before = WebApp._recommended_candidate_ids(candidates, memory=memory)
    assert set(before) == {"cand-dead", "cand-live"}
    memory.record("https://acme.example/docs", ok=False, status=404,
                  failure_type="http_status")
    after = WebApp._recommended_candidate_ids(candidates, memory=memory)
    assert "cand-dead" not in after
    assert "cand-live" in after


def test_6_memory_never_empties_the_candidate_pool(tmp_path):
    """With nothing else left the run still tries, and still fails honestly."""
    memory = AcquisitionMemory(tmp_path / "mem")
    candidates = [{"candidate_id": "cand-only",
                   "url": "https://acme.example/docs",
                   "source_type": "product", "source_class": "company_owned",
                   "discovery_method": "known_path", "why_relevant": ""}]
    memory.record("https://acme.example/docs", ok=False, status=404,
                  failure_type="http_status")
    assert WebApp._recommended_candidate_ids(candidates, memory=memory) == \
        ["cand-only"]


# =============================================================================
# 7-9. the circuit is about SILENCE, never about a path
# =============================================================================

def test_7_repeated_404s_never_open_a_host(tmp_path):
    memory = AcquisitionMemory(tmp_path / "mem")
    for i in range(20):
        memory.record(f"https://acme.example/{i}", ok=False, status=404,
                      failure_type="http_status")
    assert memory.circuit_state("acme.example") == AM.CLOSED


def test_8_repeated_403s_never_open_a_host(tmp_path):
    """MEASURED: seven 403s opened oracle.com and cost the run every one of
    the company's own pages. A refusal is a fact about a request."""
    memory = AcquisitionMemory(tmp_path / "mem")
    for i in range(20):
        memory.record(f"https://acme.example/{i}", ok=False, status=403,
                      failure_type="http_status")
    assert memory.circuit_state("acme.example") == AM.CLOSED
    assert memory.verdict("https://acme.example/9")["verdict"] == \
        SKIP_KNOWN_FAILURE, "the per-URL refusal is still remembered"


def test_9_silence_opens_the_host_and_one_probe_reopens_it(tmp_path):
    clock = {"t": 1000.0}
    memory = AcquisitionMemory(tmp_path / "mem", clock=lambda: clock["t"])
    for i in range(AM.HOST_OPEN_AFTER):
        memory.record(f"https://silent.example/{i}", ok=False,
                      failure_type="timeout")
    assert memory.circuit_state("silent.example") == AM.OPEN
    assert memory.verdict("https://silent.example/x")["verdict"] == \
        SKIP_HOST_OPEN
    clock["t"] += AM.HOST_OPEN_S + 1
    assert memory.verdict("https://silent.example/a")["verdict"] == ALLOW
    assert memory.verdict("https://silent.example/b")["verdict"] == \
        SKIP_HOST_OPEN, "only ONE probe may cross an open circuit"


# =============================================================================
# 10-11. budget-dependent outcomes may never be remembered
# =============================================================================

def test_10_too_large_is_not_a_permanent_verdict():
    """`max_bytes` and `accept_truncated` are chosen by the CALL SITE: the
    EDGAR path retrieves filings the default path refuses."""
    assert classify_outcome(ok=False, failure_type="too_large") == (None, 0)


def test_11_bad_mime_is_not_a_permanent_verdict():
    """Sitemap discovery accepts XML; the default path does not."""
    assert classify_outcome(ok=False, failure_type="bad_mime") == (None, 0)


# =============================================================================
# 12. a URL that starts working again stops being skipped
# =============================================================================

def test_12_success_forgets_a_stale_failure(tmp_path):
    memory = AcquisitionMemory(tmp_path / "mem")
    memory.record("https://acme.example/a", ok=False, status=404,
                  failure_type="http_status")
    assert memory.verdict("https://acme.example/a")["verdict"] == \
        SKIP_KNOWN_FAILURE
    memory.record("https://acme.example/a", ok=True, status=200)
    assert memory.verdict("https://acme.example/a")["verdict"] == ALLOW


# =============================================================================
# 13-14. cross-company isolation
# =============================================================================

def test_13_the_memory_key_carries_no_company_or_tenant(tmp_path):
    memory = AcquisitionMemory(tmp_path / "mem")
    memory.record("https://shared.example/p", ok=False, status=404,
                  failure_type="http_status")
    written = [p for p in (tmp_path / "mem").rglob("*.json")]
    assert written, "nothing was persisted"
    for path in written:
        text = path.read_text("utf-8")
        for secret in ("run-", "tenant", "user_id", "Acme"):
            assert secret not in text


def test_14_one_companys_evidence_never_reaches_another(tmp_path):
    def transport(url, timeout, max_bytes=None):
        return _html(f"<html><body><p>{url} " + "word " * 80 +
                     "</p></body></html>")

    memory = AcquisitionMemory(tmp_path / "mem")
    ci = _service(tmp_path, transport, memory=memory)
    a = _run(ci, name="Alpha", site="https://alpha.example")
    b = _run(ci, name="Beta", site="https://beta.example")
    ca = _candidate(ci, a, "https://alpha.example/x")
    cb = _candidate(ci, b, "https://beta.example/y")
    ci.approve(a, user_id="u", approved_ids=[ca], rejected_ids=[])
    ci.approve(b, user_id="u", approved_ids=[cb], rejected_ids=[])
    ci.fetch_approved(a)
    ci.fetch_approved(b)
    for record in ci.store.retrieved(a):
        assert "beta.example" not in record["original_url"]
    for record in ci.store.retrieved(b):
        assert "alpha.example" not in record["original_url"]


# =============================================================================
# 15-16. the role-preserving fallback graph
# =============================================================================

def test_15_the_annual_report_can_fill_the_identity_role():
    """When the company's own site refuses, the regulator still holds its
    account of itself. Before this, every `identity` matcher looked for a
    page on the subject's own domain."""
    candidates = [
        {"candidate_id": "cand-10k",
         "url": "https://www.sec.gov/Archives/edgar/data/1/2/x.htm",
         "source_type": "external_approved",
         "source_class": "investor_material", "form": "10-K",
         "discovery_method": "external_proposed",
         "why_relevant": "official 10-K filing from SEC EDGAR"},
    ]
    chosen = plan_retry(missing_families=["identity"], candidates=candidates,
                        already_approved=set(), failed_urls=set())
    assert chosen == ["cand-10k"]


def test_16_a_third_party_filing_can_fill_the_market_role():
    """`FAMILY_TARGETS["independent"]` was unreachable: `evidence_gaps` never
    emits that family name, so the only matcher able to select an attested
    third-party filing could never run."""
    candidates = [
        {"candidate_id": "cand-tpf",
         "url": "https://www.sec.gov/Archives/edgar/data/9/9/y.htm",
         "source_type": "external_approved",
         "source_class": "independent_reporting", "form": "10-K",
         "discovery_method": "third_party_filing",
         "why_relevant": "another registrant names this company"},
    ]
    chosen = plan_retry(missing_families=["customers"], candidates=candidates,
                        already_approved=set(), failed_urls=set())
    assert chosen == ["cand-tpf"]


def test_17_the_retry_planner_does_not_re_request_a_remembered_failure(tmp_path):
    memory = AcquisitionMemory(tmp_path / "mem")
    candidates = [{"candidate_id": "cand-dead",
                   "url": "https://acme.example/customers",
                   "source_type": "customers",
                   "source_class": "company_owned",
                   "discovery_method": "known_path", "why_relevant": ""}]
    assert plan_retry(missing_families=["customers"], candidates=candidates,
                      already_approved=set(), failed_urls=set(),
                      memory=memory) == ["cand-dead"]
    memory.record("https://acme.example/customers", ok=False, status=403,
                  failure_type="http_status")
    assert plan_retry(missing_families=["customers"], candidates=candidates,
                      already_approved=set(), failed_urls=set(),
                      memory=memory) == []


# =============================================================================
# 18. the stopping condition did NOT loosen
# =============================================================================

def test_18_role_awareness_did_not_weaken_the_stopping_condition():
    """`sufficient` decides how many acquisition passes run. Loosening it
    would make the product fetch LESS, which is the opposite of the repair."""
    documents = [{"retrieval_status": "OK", "text_content": "x",
                  "source_type": "external_approved",
                  "source_class": "investor_material",
                  "filing": {"form": "10-K"}}]
    gaps = evidence_gaps(documents)
    assert gaps["sufficient"] is False
    # The 10-K reads as `identity` by role, so the ROLE hunt no longer spends
    # the budget on it -- but the venue view still reports it missing, and
    # that is what keeps acquisition running.
    assert "identity" in gaps["venue_missing"]
    assert gaps["missing_families"][0] != "identity"


def test_19_a_rejected_document_costs_one_source_not_the_run(tmp_path):
    """The credential detector is blunt by design; SEC filings concatenate
    commission file numbers into card-number shapes. An NVIDIA run died
    outright on exactly this, raised from `_append` rather than
    `_build_record`, which the existing guard did not cover."""
    secret = " ".join(["4111111111111111"] * 3)

    def transport(url, timeout, max_bytes=None):
        if "bad" in url:
            return _html(f"<html><body><p>{secret} " + "word " * 80 +
                         "</p></body></html>")
        return _html()

    ci = _service(tmp_path, transport)
    run_id = _run(ci)
    bad = _candidate(ci, run_id, "https://acme.example/bad")
    good = _candidate(ci, run_id, "https://acme.example/good")
    ci.approve(run_id, user_id="u", approved_ids=[bad, good], rejected_ids=[])
    out = ci.fetch_approved(run_id)          # must not raise
    assert any("good" in r["original_url"] for r in out["ok"])
    assert out["failed"], "the rejected source must be recorded"


def test_20_an_injected_transport_disables_the_memory(tmp_path):
    """A test double defines its own outcomes; a memory written by one test
    must never decide another."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=lambda *a, **k: _html())
    assert ci.acquisition_memory.enabled is False
    assert ci.acquisition_memory.verdict("https://x.example")["verdict"] == \
        ALLOW


# =============================================================================
# 21-25. observability: source health, evidence roles, abstention taxonomy
# =============================================================================

def test_21_source_health_attributes_failures_by_cause_and_host(tmp_path):
    def transport(url, timeout, max_bytes=None):
        if "refused" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        if "missing" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return _html()

    ci = _service(tmp_path, transport)
    run_id = _run(ci)
    ids = [_candidate(ci, run_id, "https://acme.example/refused"),
           _candidate(ci, run_id, "https://acme.example/missing"),
           _candidate(ci, run_id, "https://acme.example/ok")]
    ci.approve(run_id, user_id="u", approved_ids=ids, rejected_ids=[])
    ci.fetch_approved(run_id)
    health = ci.source_health(run_id)
    assert health["retrieved"] == 1
    assert health["by_cause"]["refused"] == 1
    assert health["by_cause"]["not_found"] == 1
    assert health["by_host"]["acme.example"] == 2


def test_22_evidence_roles_are_reported_not_document_counts(tmp_path):
    """Ten copies of one narrative is weaker than three roles filled."""
    def transport(url, timeout, max_bytes=None):
        return _html()

    ci = _service(tmp_path, transport)
    run_id = _run(ci)
    ids = [_candidate(ci, run_id, f"https://acme.example/p{i}",
                      source_type="product") for i in range(5)]
    ci.approve(run_id, user_id="u", approved_ids=ids, rejected_ids=[])
    ci.fetch_approved(run_id)
    roles = ci.evidence_role_coverage(run_id)
    assert roles["documents"] == 5
    assert "identity_or_product" in roles["filled"]
    assert "market" in roles["missing"]
    assert "direction" in roles["missing"]


def test_23_abstention_reason_separates_refusal_from_thin_evidence(tmp_path):
    from intent_engine.company_ingestion import abstention as AB
    refused = AB.classify(
        readiness_state="INSUFFICIENT_EVIDENCE", documents=[{}],
        failures=[{"failure_type": "http_status",
                   "safe_message": "HTTP 403"}] * 4)
    assert refused["reason"] == AB.EXTERNAL_ACCESS_REFUSED
    thin = AB.classify(readiness_state="RETRYABLE_EVIDENCE_GAP",
                       documents=[{}] * 9, unmet_checks=["market_source"])
    assert thin["reason"] == AB.SOURCE_DIVERSITY_INSUFFICIENT


def test_24_an_external_cause_that_removed_nothing_is_not_the_reason():
    """A run holding nine documents did not abstain because two sources
    were rate limited. Precedence is the whole design."""
    from intent_engine.company_ingestion import abstention as AB
    verdict = AB.classify(
        readiness_state="RETRYABLE_EVIDENCE_GAP", documents=[{}] * 9,
        unmet_checks=["market_source"],
        failures=[{"failure_type": "http_status",
                   "safe_message": "HTTP 429"}] * 2)
    assert verdict["reason"] == AB.SOURCE_DIVERSITY_INSUFFICIENT


def test_25_a_full_report_is_never_labelled_an_abstention():
    from intent_engine.company_ingestion import abstention as AB
    assert AB.classify(readiness_state="READY_FOR_FULL_REPORT",
                       documents=[{}] * 9)["reason"] == AB.NOT_ABSTAINED


def test_26_telemetry_carries_every_acquisition_surface(tmp_path):
    """IMPLEMENTED IS NOT INSTRUMENTED. Each of these has a producer; this
    asserts the production read model actually returns them."""
    ci = _service(tmp_path, lambda *a, **k: _html())
    run_id = _run(ci)
    telemetry = ci.retrieval_telemetry(run_id)
    for key in ("retry", "filing_cache", "acquisition_memory", "sources",
                "evidence_roles", "abstention"):
        assert key in telemetry, f"telemetry is missing {key}"


# =============================================================================
# 27-28. the telemetry is REACHABLE, not merely produced
# =============================================================================

def _web_app(tmp_path):
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    from tests.test_strategic_intelligence import _live_transport
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            autorun_sources=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "fi.jsonl",
                            ci_store_path=tmp_path / "ci.jsonl"),
                  transport=_live_transport, resolver=False)


def _finished_run(app):
    from tests.test_measurement_is_canonical import _Client
    client = _Client(app)
    client.request("POST", "/demo")
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name=Acme"
        f"&website=https://acme.example")
    assert status.startswith("303"), status
    return client, headers["Location"].split("/runs/")[1].split("/")[0]


def test_27_the_telemetry_route_serves_every_acquisition_surface(tmp_path):
    """IMPLEMENTED IS NOT INSTRUMENTED. `source_health`,
    `evidence_role_coverage` and `abstention_reason` each had a producer and
    no route, which in this codebase has repeatedly meant built, green, and
    never once read in production."""
    import json
    app = _web_app(tmp_path)
    client, run_id = _finished_run(app)
    status, _headers, body = client.request("GET", f"/runs/{run_id}/telemetry")
    assert status.startswith("200"), status
    data = json.loads(body)
    for key in ("sources", "evidence_roles", "abstention",
                "acquisition_memory", "retry", "filing_cache"):
        assert key in data, f"the route does not serve {key}"
    assert data["run_id"] == run_id


def test_28_the_telemetry_route_is_owner_gated(tmp_path):
    """It names the hosts this run contacted, so it is not public."""
    from tests.test_measurement_is_canonical import _Client
    app = _web_app(tmp_path)
    _client, run_id = _finished_run(app)
    stranger = _Client(app)
    stranger.request("POST", "/demo")
    status, _headers, _body = stranger.request(
        "GET", f"/runs/{run_id}/telemetry")
    assert not status.startswith("200"), \
        "another session could read this run's telemetry"

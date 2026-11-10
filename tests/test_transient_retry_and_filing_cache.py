"""A 429 is 'not now'; a 403 is 'not this'. And a filing is read once.

These two repairs are tested together because they are the same defect seen
twice: the product treated a fact about ITS OWN request — throttled, or
already-retrieved — as a fact about the company, and told a Chief Strategy
Officer that no source could be retrieved.
"""
import json
import urllib.error

import pytest

from intent_engine.company_ingestion.fetch import safe_fetch
from intent_engine.company_ingestion.filing_cache import (
    CACHE_BYPASS, CACHE_HIT, CACHE_INVALID, CACHE_MISS, FilingCache,
    filing_identity,
)
from intent_engine.company_ingestion.transient import (
    DETERMINISTIC_POLICY, TRANSPORT_RETRY_POLICY, RetryLedger, RetryPolicy,
    backoff_delay, call_with_retry, classify_failure,
)

FILING_URL = ("https://www.sec.gov/Archives/edgar/data/19617/"
              "000001961726000123/jpm-20251231.htm")
OTHER_ACCESSION = ("https://www.sec.gov/Archives/edgar/data/19617/"
                   "000001961726000999/jpm-20251231.htm")


class Recorder:
    """A sleeper that records instead of sleeping. Deterministic timing."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(round(seconds, 4))


def http_error(code, url="https://www.sec.gov/x", headers=None):
    return urllib.error.HTTPError(url, code, f"HTTP {code}",
                                  headers or {}, None)


def scripted_transport(script):
    """A transport that plays `script` in order: exceptions raise, else
    a normal (status, headers, body, exceeded) tuple is returned."""
    calls = {"n": 0}

    def transport(url, timeout, max_bytes=None):
        item = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return item

    transport.calls = calls
    return transport


OK = (200, {"content-type": "text/html"}, b"<html>body</html>", False)


# --- retry: transient failures ------------------------------------------

def test_429_then_success_on_attempt_two():
    sleeper = Recorder()
    ledger = RetryLedger(DETERMINISTIC_POLICY)
    tx = scripted_transport([http_error(429), OK])
    result = safe_fetch("https://www.sec.gov/x", transport=tx, resolver=False,
                        retry_policy=DETERMINISTIC_POLICY,
                        retry_ledger=ledger, sleeper=sleeper)
    assert result["ok"] is True
    assert tx.calls["n"] == 2
    assert sleeper.delays == [1.0]
    assert ledger.events[-1]["attempt_count"] == 2
    assert ledger.events[-1]["final_status"] == "ok"
    assert ledger.events[-1]["retry_exhausted"] is False


def test_429_429_then_success():
    sleeper = Recorder()
    policy = RetryPolicy(max_attempts=3, jitter=0.0)
    tx = scripted_transport([http_error(429), http_error(429), OK])
    result = safe_fetch("https://www.sec.gov/x", transport=tx, resolver=False,
                        retry_policy=policy, sleeper=sleeper)
    assert result["ok"] is True
    assert tx.calls["n"] == 3
    assert sleeper.delays == [1.0, 2.0]      # exponential, not flat


def test_429_exhausts_and_reports_honestly():
    sleeper = Recorder()
    ledger = RetryLedger(DETERMINISTIC_POLICY)
    tx = scripted_transport([http_error(429)])
    result = safe_fetch("https://www.sec.gov/x", transport=tx, resolver=False,
                        retry_policy=DETERMINISTIC_POLICY,
                        retry_ledger=ledger, sleeper=sleeper)
    assert result["ok"] is False
    assert result["status_code"] == 429
    assert tx.calls["n"] == DETERMINISTIC_POLICY.max_attempts
    assert ledger.events[-1]["retry_exhausted"] is True
    assert ledger.exhausted("www.sec.gov") is True


@pytest.mark.parametrize("code", [403, 404])
def test_permanent_status_is_never_retried(code):
    sleeper = Recorder()
    tx = scripted_transport([http_error(code)])
    result = safe_fetch("https://www.sec.gov/x", transport=tx, resolver=False,
                        retry_policy=DETERMINISTIC_POLICY, sleeper=sleeper)
    assert result["ok"] is False
    assert tx.calls["n"] == 1, "a refusal must not be re-asked"
    assert sleeper.delays == []


def test_retryable_timeout_is_bounded_when_a_policy_asks_for_it():
    sleeper = Recorder()
    tx = scripted_transport([TimeoutError("timed out")])
    result = safe_fetch("https://example.com/x", transport=tx, resolver=False,
                        retry_policy=TRANSPORT_RETRY_POLICY, sleeper=sleeper)
    assert result["ok"] is False
    assert result["failure_type"] == "timeout"
    assert tx.calls["n"] == TRANSPORT_RETRY_POLICY.max_attempts
    assert len(sleeper.delays) == TRANSPORT_RETRY_POLICY.max_attempts - 1


def test_the_default_policy_leaves_silence_to_the_host_breaker():
    """MEASURED REGRESSION. Retrying a host that never answers turned two
    dials into six and defeated the per-run circuit breaker, which counts
    candidates rather than attempts and so could not see the extra dials.
    A 429 says when to come back; silence says nothing, and each attempt
    costs the full connect timeout."""
    sleeper = Recorder()
    tx = scripted_transport([TimeoutError("timed out")])
    result = safe_fetch("https://example.com/x", transport=tx, resolver=False,
                        sleeper=sleeper)
    assert result["ok"] is False and result["retryable"] is True
    assert tx.calls["n"] == 1, "silence must cost one dial, not three"
    assert sleeper.delays == []


def test_ssrf_refusal_is_not_retried():
    sleeper = Recorder()
    tx = scripted_transport([OK])
    result = safe_fetch("http://127.0.0.1/", transport=tx,
                        retry_policy=DETERMINISTIC_POLICY, sleeper=sleeper)
    assert result["ok"] is False and result["retryable"] is False
    assert tx.calls["n"] == 0 and sleeper.delays == []


def test_redirect_is_control_flow_not_a_transient_failure():
    kind, transient = classify_failure(
        http_error(302, headers={"Location": "https://www.sec.gov/y"}))
    assert (kind, transient) == ("redirect", False)


# --- retry: host isolation and budget -----------------------------------

def test_throttled_host_does_not_stop_another_host():
    sleeper = Recorder()
    ledger = RetryLedger(DETERMINISTIC_POLICY)
    sec = scripted_transport([http_error(429)])
    safe_fetch("https://www.sec.gov/x", transport=sec, resolver=False,
               retry_policy=DETERMINISTIC_POLICY, retry_ledger=ledger,
               sleeper=sleeper)
    assert ledger.exhausted("www.sec.gov") is True

    other = scripted_transport([OK])
    result = safe_fetch("https://example.com/page", transport=other,
                        resolver=False, retry_policy=DETERMINISTIC_POLICY,
                        retry_ledger=ledger, sleeper=sleeper)
    assert result["ok"] is True
    assert ledger.exhausted("example.com") is False
    assert ledger.remaining("example.com") == \
        DETERMINISTIC_POLICY.total_retry_budget_s


def test_total_retry_budget_caps_a_hostile_host():
    """Many throttled documents must not multiply into unbounded wall clock."""
    sleeper = Recorder()
    policy = RetryPolicy(max_attempts=3, base_backoff_s=4.0, max_backoff_s=8.0,
                         total_retry_budget_s=10.0, jitter=0.0)
    ledger = RetryLedger(policy)
    for _ in range(6):
        safe_fetch("https://www.sec.gov/x",
                   transport=scripted_transport([http_error(503)]),
                   resolver=False, retry_policy=policy, retry_ledger=ledger,
                   sleeper=sleeper)
    assert sum(sleeper.delays) <= policy.total_retry_budget_s
    assert ledger.spent("www.sec.gov") <= policy.total_retry_budget_s


def test_backoff_is_capped_and_jitter_only_widens():
    policy = RetryPolicy(base_backoff_s=1.0, max_backoff_s=8.0, jitter=0.5)
    assert backoff_delay(9, policy, rng=lambda: 0.0) == 8.0
    assert backoff_delay(1, policy, rng=lambda: 1.0) == 1.5
    assert backoff_delay(1, policy, rng=lambda: 0.0) == 1.0


def test_ledger_snapshot_carries_the_required_telemetry():
    ledger = RetryLedger(DETERMINISTIC_POLICY)
    safe_fetch("https://www.sec.gov/x",
               transport=scripted_transport([http_error(429), OK]),
               resolver=False, retry_policy=DETERMINISTIC_POLICY,
               retry_ledger=ledger, sleeper=Recorder())
    snap = ledger.snapshot()
    for key in ("attempts_by_host", "retries_by_host",
                "retry_seconds_by_host", "exhausted_hosts", "events"):
        assert key in snap
    event = snap["events"][-1]
    for key in ("attempt_count", "final_status", "retry_exhausted",
                "elapsed_retry_time"):
        assert key in event


def test_an_injected_sleeper_cannot_buy_free_retries():
    """A zero-cost sleeper must still be charged the delay it COMMITTED to.

    Charging elapsed wall clock instead would cost microseconds under a
    recording sleeper, the budget would never bind, and the run would take
    the full attempt count against a host that is already throttling it —
    while the test that exists to prove the budget binds stayed green.

    The budget here (2.0s) funds exactly one 1.0s wait; the second would be
    2.0s and does not fit. So the call must stop after 2 attempts, well
    short of max_attempts=5.
    """
    policy = RetryPolicy(max_attempts=5, base_backoff_s=1.0,
                         total_retry_budget_s=2.0, jitter=0.0)
    ledger = RetryLedger(policy)
    sleeper = Recorder()
    with pytest.raises(urllib.error.HTTPError):
        call_with_retry(lambda: (_ for _ in ()).throw(http_error(429)),
                        url="https://www.sec.gov/x", policy=policy,
                        ledger=ledger, sleeper=sleeper)
    assert sleeper.delays == [1.0], sleeper.delays
    assert ledger.events[-1]["attempt_count"] == 2
    assert ledger.spent("www.sec.gov") >= 1.0
    assert ledger.exhausted("www.sec.gov") is True


# --- cache: identity ----------------------------------------------------

def test_identity_is_the_filing_not_the_url_string():
    assert filing_identity(FILING_URL) == (
        "19617", "000001961726000123", "jpm-20251231.htm")
    # same document, different spelling -> same identity
    assert filing_identity(FILING_URL.replace("www.sec.gov", "sec.gov")) == \
        filing_identity(FILING_URL)
    # different accession -> different identity
    assert filing_identity(OTHER_ACCESSION) != filing_identity(FILING_URL)


def test_non_edgar_url_is_bypassed_never_guessed(tmp_path):
    cache = FilingCache(tmp_path)
    outcome, entry = cache.get("https://www.meta.com/investor")
    assert (outcome, entry) == (CACHE_BYPASS, None)
    assert cache.put("https://www.meta.com/investor", body=b"x") is False


def test_a_lookalike_host_cannot_write_into_a_real_filings_slot(tmp_path):
    """THE HOST IS PART OF THE IDENTITY, and the path check alone will not
    say so. A URL that copies the EDGAR archive path onto another host has
    six well-formed segments and a valid CIK and accession — so if the host
    were not checked, a redirect or a proposed candidate on an attacker's
    domain could write bytes into the slot a real 10-K is read from, and
    every later company would read them as JPMorgan's annual report."""
    cache = FilingCache(tmp_path)
    cache.put(FILING_URL, body=b"the real annual report")
    impostor = FILING_URL.replace("www.sec.gov", "sec.gov.evil.example")
    assert filing_identity(impostor) is None
    assert cache.put(impostor, body=b"forged") is False
    assert cache.get(impostor) == (CACHE_BYPASS, None)
    assert cache.get(FILING_URL)[1]["body"] == b"the real annual report"


def test_cache_hit_returns_byte_identical_content(tmp_path):
    cache = FilingCache(tmp_path)
    body = b"<html>Item 1. Business</html>" * 100
    assert cache.put(FILING_URL, body=body, mime_type="text/html",
                     truncated=False) is True
    outcome, entry = cache.get(FILING_URL)
    assert outcome == CACHE_HIT
    assert entry["body"] == body
    assert entry["truncated"] is False
    assert entry["accession"] == "000001961726000123"


def test_same_cik_different_accession_does_not_collide(tmp_path):
    cache = FilingCache(tmp_path)
    cache.put(FILING_URL, body=b"annual report")
    cache.put(OTHER_ACCESSION, body=b"a completely different filing")
    assert cache.get(FILING_URL)[1]["body"] == b"annual report"
    assert cache.get(OTHER_ACCESSION)[1]["body"] == \
        b"a completely different filing"


def test_truncation_survives_the_cache(tmp_path):
    """A truncated filing presented as complete is the one thing the
    retrieval contract most needs to keep true."""
    cache = FilingCache(tmp_path)
    cache.put(FILING_URL, body=b"first 16MB", truncated=True)
    assert cache.get(FILING_URL)[1]["truncated"] is True


def test_corrupted_entry_reads_as_invalid_not_as_a_filing(tmp_path):
    cache = FilingCache(tmp_path)
    cache.put(FILING_URL, body=b"real bytes")
    body_path = (tmp_path / "19617" / "000001961726000123"
                 / "jpm-20251231.htm")
    body_path.write_bytes(b"tampered")
    outcome, entry = cache.get(FILING_URL)
    assert (outcome, entry) == (CACHE_INVALID, None)


def test_cache_miss_before_first_write(tmp_path):
    assert FilingCache(tmp_path).get(FILING_URL)[0] == CACHE_MISS


def test_cache_key_carries_no_run_or_company_identity(tmp_path):
    """Tenancy: the key is a public document's public address. If a run id
    or a focal company ever entered it, one tenant's cache would answer a
    question about another tenant's analysis."""
    cache = FilingCache(tmp_path)
    cache.put(FILING_URL, body=b"x")
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert written, "nothing was written"
    for path in written:
        parts = [p.lower() for p in path.relative_to(tmp_path).parts]
        assert not any("run" in p or "tenant" in p or "session" in p
                       for p in parts)
    meta = json.loads(
        (tmp_path / "19617" / "000001961726000123"
         / "jpm-20251231.htm.meta.json").read_text())
    assert set(meta) == {"cik", "accession", "document", "source_url",
                         "mime_type", "status_code", "truncated",
                         "content_hash", "bytes", "retrieved_at"}


def test_cache_stores_no_company_specific_interpretation(tmp_path):
    """The cache holds the RESPONSE. Relationship, relevance, competitor
    classification and every strategic conclusion are functions of
    (document, focal company) and must be recomputed for each."""
    cache = FilingCache(tmp_path)
    cache.put(FILING_URL, body=b"x")
    meta = json.loads(
        (tmp_path / "19617" / "000001961726000123"
         / "jpm-20251231.htm.meta.json").read_text())
    banned = {"relevance", "relationship", "competitor", "competitors",
              "focal_company", "conclusion", "signals", "beliefs",
              "relevance_score", "company_name"}
    assert not (set(meta) & banned)


def test_counters_instrument_every_outcome(tmp_path):
    cache = FilingCache(tmp_path)
    cache.get(FILING_URL)                       # MISS
    cache.get("https://example.com/a")          # BYPASS
    cache.put(FILING_URL, body=b"x")
    cache.get(FILING_URL)                       # HIT
    snap = cache.snapshot()
    assert snap[CACHE_MISS] == 1 and snap[CACHE_BYPASS] == 1
    assert snap[CACHE_HIT] == 1


def test_the_run_ceiling_binds_across_hosts_not_only_within_one():
    """A PER-HOST BUDGET STILL MULTIPLIES. Four throttled hosts would each
    spend the per-host bound, so the customer waits four times the number
    anyone reasoned about, in front of a failure page that was already
    certain. The run ceiling is what a reader actually experiences."""
    sleeper = Recorder()
    policy = RetryPolicy(max_attempts=4, base_backoff_s=2.0,
                         max_backoff_s=4.0, total_retry_budget_s=10.0,
                         run_retry_budget_s=8.0, jitter=0.0)
    ledger = RetryLedger(policy)
    for host in ("a.example.com", "b.example.com", "c.example.com",
                 "d.example.com"):
        safe_fetch(f"https://{host}/x",
                   transport=scripted_transport([http_error(429)]),
                   resolver=False, retry_policy=policy, retry_ledger=ledger,
                   sleeper=sleeper)
    assert sum(sleeper.delays) <= policy.run_retry_budget_s, sleeper.delays
    snap = ledger.snapshot()
    assert snap["total_retry_seconds"] <= policy.run_retry_budget_s
    assert snap["run_budget_exhausted"] is True
    # and the run ceiling, not the per-host one, is what stopped it
    for host in snap["retry_seconds_by_host"]:
        assert snap["retry_seconds_by_host"][host] < \
            policy.total_retry_budget_s


# --- the cache is a filesystem write path -------------------------------

@pytest.mark.parametrize("document", [
    "..", ".", "../../../../etc/passwd", "..%2f..%2fetc%2fpasswd",
    "....//....//etc/passwd", "a/../../b.htm", "~/.ssh/id_rsa",
    "\\..\\..\\windows\\system32", "a\x00.htm",
])
def test_no_document_name_can_escape_the_cache_directory(document, tmp_path):
    """THE CACHE WRITES FILES NAMED FROM A URL. The document segment is the
    only part of the key that is not digits, so it is the only part that
    could carry a path. `filing_identity` must refuse anything it cannot
    read as a plain filename rather than sanitising it — a sanitiser is a
    denylist, and this file has already recorded what happens to those.
    """
    url = ("https://www.sec.gov/Archives/edgar/data/19617/"
           f"000001961726000123/{document}")
    assert filing_identity(url) is None
    cache = FilingCache(tmp_path)
    assert cache.put(url, body=b"x") is False
    assert cache.get(url) == (CACHE_BYPASS, None)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert written == [], written


def test_every_written_path_stays_inside_the_cache_root(tmp_path):
    cache = FilingCache(tmp_path)
    assert cache.put(FILING_URL, body=b"x") is True
    root = tmp_path.resolve()
    for path in tmp_path.rglob("*"):
        assert root in path.resolve().parents or path.resolve() == root


def test_the_cache_is_not_keyed_on_anything_a_caller_supplies(tmp_path):
    """Tenancy, stated as a property of the KEY. Every component comes from
    the publisher's own address for a public document; nothing a caller
    chose can steer where bytes land or which bytes come back."""
    cache = FilingCache(tmp_path)
    cache.put(FILING_URL, body=b"real")
    # a second caller, different everything, same public document
    other = FilingCache(tmp_path)
    assert other.get(FILING_URL)[1]["body"] == b"real"
    # and a different public document is a different slot
    assert other.get(OTHER_ACCESSION)[0] == CACHE_MISS

"""§16/§17: a cold company is not a cold deployment.

"Cold" means no snapshot for THIS company. It does not mean the process must
re-download SEC's registrant table — 795,179 identical bytes — for every
analysis, twice.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.company_ingestion import edgar
from intent_engine.company_ingestion import public_metadata as PM


@pytest.fixture(autouse=True)
def _clean_cache():
    PM.STORE.clear()
    yield
    PM.STORE.clear()


def _table():
    return json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL",
                             "title": "Apple Inc."},
                       "1": {"cik_str": 789019, "ticker": "MSFT",
                             "title": "Microsoft Corporation"}}).encode()


def test_the_ticker_table_is_downloaded_once_not_per_analysis(monkeypatch):
    """THE ASSERTION IS THE REQUEST LEDGER, not a cache statistic."""
    calls = []

    def transport(url, timeout, max_bytes=2_000_000):
        calls.append(url)
        return (200, {"content-type": "application/json"}, _table(), False)

    monkeypatch.setattr(edgar, "_sec_transport", transport)
    monkeypatch.setattr(edgar, "validate_candidate_url", lambda u: u)
    monkeypatch.setattr(edgar, "resolve_public_addresses",
                        lambda *a, **k: ["93.184.216.34"])

    first = edgar.resolve_cik("Apple Inc.", resolver=False)
    second = edgar.resolve_cik("Microsoft Corporation", resolver=False)
    third = edgar.resolve_cik("Apple Inc.", resolver=False)

    assert first["cik"] == 320193 and second["cik"] == 789019
    assert third == first, "the cached table answered differently"
    assert len(calls) == 1, (
        f"the registrant table was downloaded {len(calls)} times for three "
        f"resolutions")


def test_a_filing_document_is_never_held_in_the_metadata_cache():
    """`FilingCache` owns filings. A 16MB primary document has no business in
    a process-memory cache sized for index tables — and a cached READING of a
    company would make one run's evidence another run's input."""
    assert edgar._registry_ttl(edgar.TICKERS_URL) is not None
    assert edgar._registry_ttl(
        "https://data.sec.gov/submissions/CIK0000320193.json") is not None
    assert edgar._registry_ttl(
        "https://www.sec.gov/Archives/edgar/data/320193/aapl-10k.htm") is None
    assert edgar._registry_ttl(
        "https://www.sec.gov/cgi-bin/srqsb?text=x") is None


def test_an_injected_transport_is_never_answered_by_the_cache(monkeypatch):
    """A cache in front of an injected transport answers FOR it — which in the
    suite is one test's fixture serving another test's assertion."""
    PM.STORE.put(edgar.TICKERS_URL, b'{"0":{"cik_str":1,"ticker":"X",'
                                    b'"title":"Stale Co"}}',
                 PM.TTL_REGISTRY_S)
    calls = []

    def transport(url, timeout, max_bytes=2_000_000):
        calls.append(url)
        return (200, {"content-type": "application/json"}, _table(), False)

    monkeypatch.setattr(edgar, "validate_candidate_url", lambda u: u)
    monkeypatch.setattr(edgar, "resolve_public_addresses",
                        lambda *a, **k: ["93.184.216.34"])
    found = edgar.resolve_cik("Apple Inc.", transport=transport,
                              resolver=False)
    assert calls, "the injected transport was bypassed by the cache"
    assert found["cik"] == 320193


def test_an_expired_entry_is_a_miss():
    PM.STORE.put("https://x.example/a.json", b"old", 0.0)
    assert PM.STORE.get("https://x.example/a.json") is None
    assert PM.STORE.stats["expired"] >= 1


def test_a_truncated_or_failed_response_is_never_stored(monkeypatch):
    """Serving a cut-off body again would hand a broken document to a parser
    whose failure is indistinguishable from a filer with nothing on file."""
    def transport(url, timeout, max_bytes=2_000_000):
        return (200, {"content-type": "application/json"},
                b"x" * (max_bytes + 1), True)

    monkeypatch.setattr(edgar, "_sec_transport", transport)
    monkeypatch.setattr(edgar, "validate_candidate_url", lambda u: u)
    monkeypatch.setattr(edgar, "resolve_public_addresses",
                        lambda *a, **k: ["93.184.216.34"])
    with pytest.raises(edgar.SubmissionsTruncated):
        edgar._fetch_bytes(edgar.TICKERS_URL, transport=None, resolver=False,
                           max_bytes=16)
    assert PM.STORE.get(edgar.TICKERS_URL) is None

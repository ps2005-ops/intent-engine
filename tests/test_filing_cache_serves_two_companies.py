"""One filing, read once, read differently by each focal company.

The 60-company programme reads the same statutory documents repeatedly. This
holds the seam that makes that safe: the cache stores the RESPONSE, and every
company-specific reading of that response is recomputed. If interpretation
ever moved into the cache, two companies would receive one company's answer.

The run is driven through the REAL EDGAR discovery path — submissions index,
filing index, archive document — rather than a hand-built candidate, because
a fixture invented with fields production does not carry proves nothing about
production.
"""
import json

from intent_engine.company_ingestion.filing_cache import FilingCache
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.company_ingestion.transient import RetryLedger

AS_OF = "2026-08-20T00:00:00+00:00"
CIK = "19617"
ACCESSION = "0000019617-26-000123"
NODASH = ACCESSION.replace("-", "")
DOC = "jpm-20251231.htm"
FILING_URL = (f"https://www.sec.gov/Archives/edgar/data/{CIK}/{NODASH}/{DOC}")
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{CIK.zfill(10)}.json"
INDEX_URL = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{NODASH}/index.json"

FILING_BODY = (b"<html><body><h1>Annual Report</h1><p>Item 1. Business. "
               b"The Firm competes with other banking institutions and with "
               b"payment networks across consumer and wholesale markets."
               b"</p></body></html>")

SUBMISSIONS = json.dumps({
    "cik": CIK, "name": "JPMORGAN CHASE & CO", "sic": "6021",
    "sicDescription": "National Commercial Banks",
    "tickers": ["JPM"], "exchanges": ["NYSE"],
    "filings": {"recent": {
        "form": ["10-K"], "accessionNumber": [ACCESSION],
        "primaryDocument": [DOC], "filingDate": ["2026-02-13"],
    }},
}).encode()

INDEX = json.dumps({"directory": {"item": [{"name": DOC}]}}).encode()


class CountingTransport:
    """Serves the three SEC endpoints and counts every request."""

    def __init__(self):
        self.urls = []

    def __call__(self, url, timeout, max_bytes=None):
        self.urls.append(url)
        payload = {SUBMISSIONS_URL: SUBMISSIONS, INDEX_URL: INDEX,
                   FILING_URL: FILING_BODY}.get(url)
        if payload is None:
            return (404, {"content-type": "text/html"}, b"", False)
        mime = ("application/json" if url.endswith(".json")
                else "text/html")
        return (200, {"content-type": mime}, payload, False)


def _run(tmp_path, name, transport, cache):
    ci = CompanyIngestionService(
        tmp_path / f"{name}.jsonl", transport=transport, resolver=False,
        filing_cache=cache, retry_ledger=RetryLedger())
    run_id = ci.create_run(company_name=name, website="", user_id="u",
                           as_of=AS_OF, cik=CIK)["run_id"]
    candidates = ci.discover(run_id)
    filings = [c for c in candidates if c["url"] == FILING_URL]
    assert filings, f"EDGAR discovery proposed no filing: " \
                    f"{[c['url'] for c in candidates]}"
    ci.approve(run_id, user_id="u",
               approved_ids=[filings[0]["candidate_id"]],
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["url"] != FILING_URL])
    ci.fetch_approved(run_id)
    return ci, run_id


def test_second_company_reads_the_cached_filing_without_a_second_request(
        tmp_path):
    cache = FilingCache(tmp_path / "cache")
    first_tx = CountingTransport()
    ci_a, run_a = _run(tmp_path, "first", first_tx, cache)
    assert first_tx.urls.count(FILING_URL) == 1
    assert [s for s in ci_a.store.retrieved(run_a)], "nothing retrieved"

    second_tx = CountingTransport()
    ci_b, run_b = _run(tmp_path, "second", second_tx, cache)
    # THE POINT: the network was not asked again for a document SEC will
    # never revise in place.
    assert second_tx.urls.count(FILING_URL) == 0
    assert [s for s in ci_b.store.retrieved(run_b)], "cache served nothing"
    assert cache.snapshot()["CACHE_HIT"] >= 1


def test_the_cached_bytes_are_identical_for_both_companies(tmp_path):
    cache = FilingCache(tmp_path / "cache")
    ci_a, run_a = _run(tmp_path, "alpha", CountingTransport(), cache)
    ci_b, run_b = _run(tmp_path, "beta", CountingTransport(), cache)
    hash_a = [s["content_hash"] for s in ci_a.store.retrieved(run_a)]
    hash_b = [s["content_hash"] for s in ci_b.store.retrieved(run_b)]
    assert hash_a and hash_a == hash_b


def test_each_company_reads_the_filing_for_itself(tmp_path):
    """Parsing and every downstream reading run per RUN, not per document —
    so each run holds its own source record for the same bytes, and the
    cache holds no reading of either."""
    cache = FilingCache(tmp_path / "cache")
    ci_a, run_a = _run(tmp_path, "alpha", CountingTransport(), cache)
    ci_b, run_b = _run(tmp_path, "beta", CountingTransport(), cache)
    assert run_a != run_b
    assert {s["run_id"] for s in ci_a.store.retrieved(run_a)} == {run_a}
    assert {s["run_id"] for s in ci_b.store.retrieved(run_b)} == {run_b}
    meta_files = list((tmp_path / "cache").rglob("*.meta.json"))
    assert meta_files
    for path in meta_files:
        text = path.read_text().lower()
        assert "alpha" not in text and "beta" not in text

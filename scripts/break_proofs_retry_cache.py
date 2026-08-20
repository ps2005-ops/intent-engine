#!/usr/bin/env python3
"""Break the transient-retry policy and the filing cache deliberately.

The defects these guard:

  RETRY. `safe_fetch` classified a 429 as retryable=True and then returned it,
  so the only retry the product performed was asking the customer to try
  again. Walmart and NVIDIA both dead-ended that way, and the surface reported
  it as a fact about the company.

  CACHE. The same statutory documents are read over and over by a 60-company
  programme. Caching them is safe ONLY while the cache holds the response and
  never a reading of it, and while its key is the filing's attested identity
  rather than a URL string.

Run:  PYTHONPATH=src python3 scripts/break_proofs_retry_cache.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TR = ROOT / "src/intent_engine/company_ingestion/transient.py"
FC = ROOT / "src/intent_engine/company_ingestion/filing_cache.py"
SV = ROOT / "src/intent_engine/company_ingestion/service.py"

T = "tests/test_transient_retry_and_filing_cache.py"
T2 = "tests/test_filing_cache_serves_two_companies.py"
T3 = "tests/test_retry_accounting_is_per_run.py"

PROOFS = [
    # --- A: remove the retry loop entirely ---------------------------------
    ("A. the retry loop is removed — one attempt, as before",
     TR,
     "            if not transient or attempt >= policy.max_attempts:",
     "            if True:",
     f"{T}::test_429_then_success_on_attempt_two",
     "assert"),

    # --- B: retry something that is a refusal ------------------------------
    ("B0. silence is retried again, defeating the host circuit breaker",
     TR,
     "RETRYABLE_TRANSPORT_FAILURES = frozenset()",
     "RETRYABLE_TRANSPORT_FAILURES = frozenset({\"timeout\", \"connection\"})",
     "tests/test_a_dead_host_is_dialled_twice_not_ten_times.py"
     "::test_a_silent_host_is_dialled_twice_not_ten_times",
     "dialled a silent host"),

    ("B1. a 403 becomes retryable",
     TR,
     "RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})",
     "RETRYABLE_HTTP_STATUSES = frozenset({403, 429, 500, 502, 503, 504})",
     f"{T}::test_permanent_status_is_never_retried",
     "a refusal must not be re-asked"),

    ("B2. every failure becomes retryable",
     TR,
     "        return \"http_status\", False",
     "        return \"http_status\", True",
     f"{T}::test_permanent_status_is_never_retried",
     "a refusal must not be re-asked"),

    ("B3. a redirect is retried instead of followed",
     TR,
     "            return \"redirect\", False",
     "            return \"redirect\", True",
     f"{T}::test_redirect_is_control_flow_not_a_transient_failure",
     "assert"),

    # --- C: cache identity -------------------------------------------------
    ("C1. the accession is dropped from the cache identity",
     FC,
     "        base = self.root / cik / accession",
     "        base = self.root / cik",
     f"{T}::test_same_cik_different_accession_does_not_collide",
     "assert"),

    ("C2. the identity becomes the raw URL string",
     FC,
     "    return cik.lstrip(\"0\") or \"0\", accession, document",
     "    return (url, url, url)",
     f"{T}::test_identity_is_the_filing_not_the_url_string",
     "assert"),

    ("C3. a lookalike host is accepted as an EDGAR archive path",
     FC,
     "    if host not in (\"www.sec.gov\", \"sec.gov\"):\n        return None",
     "    if host not in (\"www.sec.gov\", \"sec.gov\"):\n        pass",
     f"{T}::test_a_lookalike_host_cannot_write_into_a_real_filings_slot",
     "assert"),

    # --- D: company-specific interpretation must never be cached ----------
    ("D1. a reading of the filing is written into the cache entry",
     FC,
     '                "content_hash": digest, "bytes": len(raw),',
     '                "content_hash": digest, "bytes": len(raw),\n'
     '                "competitor": "payment networks",',
     f"{T}::test_cache_stores_no_company_specific_interpretation",
     "assert"),

    ("D2. the focal company enters the cache key surface",
     FC,
     '                "source_url": url, "mime_type": mime_type,',
     '                "source_url": url, "mime_type": mime_type,\n'
     '                "focal_company": "alpha",',
     f"{T2}::test_each_company_reads_the_filing_for_itself",
     "assert"),

    # --- E: the budget must actually bind ----------------------------------
    ("E1. the total retry budget is ignored",
     TR,
     "            if delay > budget_left:",
     "            if False:",
     f"{T}::test_total_retry_budget_caps_a_hostile_host",
     "assert"),

    ("E2. an injected sleeper is charged nothing, so retries are free",
     TR,
     "            actual = max(delay, now() - started)",
     "            actual = now() - started",
     f"{T}::test_an_injected_sleeper_cannot_buy_free_retries",
     "assert"),

    ("E3. the run ceiling is dropped, so per-host budgets stack",
     TR,
     "        return max(0.0, min(\n"
     "            self.policy.total_retry_budget_s - self.spent(host),\n"
     "            self.policy.run_retry_budget_s - self.spent_total()))",
     "        return max(0.0, "
     "self.policy.total_retry_budget_s - self.spent(host))",
     f"{T}::test_the_run_ceiling_binds_across_hosts_not_only_within_one",
     "assert"),

    # --- F: host isolation -------------------------------------------------
    ("F1. the budget becomes global instead of per host",
     TR,
     "        return self._spent.get(host or \"\", 0.0)",
     "        return sum(self._spent.values())",
     f"{T}::test_throttled_host_does_not_stop_another_host",
     "assert"),

    # --- G: the cache must not serve corrupt bytes as a filing -------------
    ("G1. the stored hash is trusted instead of checked",
     FC,
     "        if meta.get(\"content_hash\") != hashlib.sha256(raw).hexdigest():",
     "        if False:",
     f"{T}::test_corrupted_entry_reads_as_invalid_not_as_a_filing",
     "assert"),

    ("G2. truncation is dropped on the way through the cache",
     FC,
     "            \"truncated\": bool(meta.get(\"truncated\", False)),",
     "            \"truncated\": False,",
     f"{T}::test_truncation_survives_the_cache",
     "assert"),

    # --- H: the service must actually consult the cache --------------------
    ("H1. the retrieval path stops consulting the cache",
     SV,
     "            if cached is not None:",
     "            if False:",
     f"{T2}::test_second_company_reads_the_cached_filing_without_a_second_request",
     "assert"),

    ("H2. the retrieval path stops populating the cache",
     SV,
     "                if result[\"ok\"]:\n                    self.filing_cache.put(",
     "                if False:\n                    self.filing_cache.put(",
     f"{T2}::test_second_company_reads_the_cached_filing_without_a_second_request",
     "assert"),

    # --- J: one ledger per process is one budget for every customer -------
    ("J1. the ledger goes back on the service, shared by every run",
     SV,
     "        ledger = self._retry_ledgers.get(run_id)\n"
     "        if ledger is None:\n"
     "            ledger = self._retry_ledgers[run_id] = RetryLedger()",
     "        ledger = self._retry_ledgers.get(\"shared\")\n"
     "        if ledger is None:\n"
     "            ledger = self._retry_ledgers[\"shared\"] = RetryLedger()",
     f"{T3}::test_a_spent_budget_does_not_follow_the_next_run",
     "inherited the previous customer"),

    ("J2. the telemetry stops reaching the operator surface",
     SV,
     "            \"total_retries\": retries,",
     "            \"total_retries\": 0,",
     f"{T3}::test_telemetry_reaches_a_surface",
     "assert"),

    # --- I: safe_fetch must actually route through the policy -------------
    ("I1. safe_fetch stops routing the transport through the retry policy",
     ROOT / "src/intent_engine/company_ingestion/fetch.py",
     "            status, headers, body, exceeded = call_with_retry(",
     "            status, headers, body, exceeded = (lambda f, **k: f())(",
     f"{T}::test_429_then_success_on_attempt_two",
     "assert"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))

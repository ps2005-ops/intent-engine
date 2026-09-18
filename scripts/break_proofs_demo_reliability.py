#!/usr/bin/env python3
"""Break proofs for the live demo lifecycle (§45, §46).

Each mutation re-creates the failure a real first-time visitor hit on
eb18371 — "This analysis could not be completed, so there is no result to
open", printed over a run that had read five sources and held a readable
result — or one of the defaults that produced it.

A proof counts only if the source hash changes, the named test was green
before, turns RED after, and the failure text matches what the proof claims
it is about.

Run:  PYTHONPATH=src python scripts/break_proofs_demo_reliability.py
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from break_proof_harness import Proof, run_all           # noqa: E402

ROOT = HERE.parent
APP = ROOT / "src/intent_engine/webapp/app.py"
TPF = ROOT / "src/intent_engine/company_ingestion/third_party_filings.py"
RECORDS = ROOT / "src/intent_engine/founder_intelligence/records.py"
PROFILE = ROOT / "src/intent_engine/executive/company_profile.py"

T = "tests/test_demo_reliability.py"

PROOFS = [
    # --- the invariant the whole cycle exists for -------------------------
    Proof(
        label="1. a readable result no longer opens the analysis",
        path=APP,
        find='        readable = bool(avail["has_report"]\n'
             '                        or (avail["has_result"] and avail["documents"]))',
        replace='        readable = False',
        target=f"{T}::test_a_result_that_exists_is_never_reported_as_a_failure",
        expect_failure_contains="assert"),

    Proof(
        label="2. the progress page goes back to reading the run's state",
        path=APP,
        find="        if real:\n"
             "            readiness = self.result_readiness(run_id)\n"
             "            if readiness[\"opens_result\"]:\n"
             "                return self._redirect(f\"/runs/{run_id}\")\n\n"
             "        # A worker that vanished",
        replace="        if False:\n"
                "            readiness = self.result_readiness(run_id)\n"
                "            if readiness[\"opens_result\"]:\n"
                "                return self._redirect(f\"/runs/{run_id}\")\n\n"
                "        # A worker that vanished",
        target=f"{T}::test_a_result_that_exists_is_never_reported_as_a_failure",
        expect_failure_contains="assert"),

    Proof(
        label="3. a bounded reading stops counting as something to show",
        path=APP,
        find='            phase = (self.READY_RESULT if avail["has_report"]\n'
             '                     else self.READY_DEGRADED)',
        replace='            phase = self.READY_RESULT',
        target=f"{T}::test_a_degraded_result_still_opens_the_analysis",
        expect_failure_contains="assert"),

    # --- a failure that is still recoverable is not a death ----------------
    Proof(
        label="4. an interrupted run is reported as finally failed",
        path=APP,
        find='        retryable = attempts_left and (state == "INTERRUPTED" or transient)',
        replace='        retryable = False',
        target=f"{T}::test_an_interrupted_run_is_recoverable_not_dead",
        expect_failure_contains="assert"),

    Proof(
        label="5. every failed run is offered a retry, 403s included",
        path=APP,
        find='        retryable = attempts_left and (state == "INTERRUPTED" or transient)',
        replace='        retryable = attempts_left',
        target=f"{T}::"
               f"test_a_run_whose_sources_all_refused_is_not_offered_a_retry",
        expect_failure_contains="assert"),

    # --- the sentence that was never checked ------------------------------
    Proof(
        label='6. "every approved source failed" returns unchecked',
        path=APP,
        find="        read = len(self._retrieved_documents(run_id))\n"
             "        if read:",
        replace="        read = len(self._retrieved_documents(run_id))\n"
                "        if False:",
        target=f"{T}::"
               f"test_progress_never_says_every_source_failed_when_some_were_read",
        expect_failure_contains="assert"),

    # --- the defaults that produced the measured failure -------------------
    Proof(
        label="7. third-party filings lose the filing byte budget",
        path=TPF,
        find='        "max_bytes": MAX_FILING_BYTES,',
        replace='        "max_bytes": None,',
        target=f"{T}::"
               f"test_a_third_party_filing_is_fetched_against_the_filing_budget",
        expect_failure_contains="assert"),

    Proof(
        label="8. a domainless filer cannot be composed again",
        path=RECORDS,
        find='        if str(self.website or "").strip():\n'
             "            validate_public_url(self.website)      # SSRF wall",
        replace="        validate_public_url(self.website)      # SSRF wall",
        target="tests/test_domainless_filer_composes.py::"
               "test_a_filer_with_no_website_still_validates",
        expect_failure_contains="UnsafeURLRejected"),

    # --- the wrong-company / wrong-model proofs (§46) ----------------------
    Proof(
        label="9. an advertising platform is read as subscription software",
        path=PROFILE,
        find="        hinted = revenue_model_hint(evidence_text)\n"
             "        if hinted and hinted != model and hinted in _ECONOMICS:",
        replace="        hinted = revenue_model_hint(evidence_text)\n"
                "        if False:",
        target="tests/test_domainless_filer_composes.py::"
               "test_meta_is_not_read_as_a_subscription_business",
        expect_failure_contains="assert"),

    Proof(
        label="10. any mention of advertising reclassifies a company",
        path=PROFILE,
        find='    return ("ADVERTISING_PLATFORM"\n'
             '            if _ADVERTISING_REVENUE.search(text[:400_000]) else None)',
        replace='    return ("ADVERTISING_PLATFORM"\n'
                '            if "advertis" in text.lower() else None)',
        target="tests/test_domainless_filer_composes.py::"
               "test_a_subscription_filer_is_not_reclassified_by_an_ad_expense",
        expect_failure_contains="assert"),
]


if __name__ == "__main__":
    sys.exit(run_all(PROOFS))

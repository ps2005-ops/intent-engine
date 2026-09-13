#!/usr/bin/env python3
"""Break the four repairs of the pre-100 convergence wave deliberately.

Each repair below was made because a measured defect on 743df06 said it had
to be. A repair whose guard is not load-bearing is a repair that will be
undone by the next person who tidies it, so each one has to be shown to turn
its own test red for its own reason.

Run:  PYTHONPATH=src python3 scripts/break_proofs_pre100_convergence.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
COV = ROOT / "src/intent_engine/company_ingestion/coverage.py"
RDY = ROOT / "src/intent_engine/company_ingestion/readiness.py"
SVC = ROOT / "src/intent_engine/company_ingestion/service.py"
APP = ROOT / "src/intent_engine/webapp/app.py"
VER = ROOT / "src/intent_engine/pre100/verdict.py"
LOG = ROOT / "src/intent_engine/agentos/append_only.py"

TF = "tests/test_filing_family_is_the_form.py"
TA = "tests/test_attrition_counters_close.py"
TR = "tests/test_retrieval_plan_moves_the_budget.py"
TD = "tests/test_a_guess_at_a_closed_door.py"
TL = "tests/test_the_log_is_parsed_once.py"
TM = "tests/test_one_readiness_read_per_request.py"

PROOFS = [
    # --- R1. the filing family is the form, not the venue ------------------
    Proof("R1a. every filing goes back to being investor material",
          COV,
          '        return _FILING_FAMILY.get(filing_form(document), INVESTOR)',
          '        return INVESTOR',
          f"{TF}::test_the_annual_report_is_the_company_describing_itself",
          "assert"),
    Proof("R1b. the annual report stops being an identity source",
          COV,
          '    "10-K": IDENTITY, "10-K/A": IDENTITY,',
          '    "10-K": INVESTOR, "10-K/A": INVESTOR,',
          f"{TF}::test_sec_only_evidence_can_now_reach_more_than_one_family",
          "assert"),
    Proof("R1c. an unknown form is promoted instead of left alone",
          COV,
          '        return _FILING_FAMILY.get(filing_form(document), INVESTOR)',
          '        return _FILING_FAMILY.get(filing_form(document), IDENTITY)',
          f"{TF}::test_an_unknown_form_is_not_promoted",
          "assert"),

    # --- R3. the attrition counters describe ONE document set --------------
    Proof("R3a. the unexplained remainder is silently zeroed",
          RDY,
          '        inputs["dropped_unexplained"] = len(documents) - named - usable',
          '        inputs["dropped_unexplained"] = 0',
          f"{TA}::test_the_unexplained_remainder_is_reported_not_hidden",
          "assert"),
    Proof("R3b. the duplicate filter stops being counted",
          RDY,
          '        "dropped_duplicate": max(0, len(texted) - len(deduped)),',
          '        "dropped_duplicate": 0,',
          f"{TA}::test_a_duplicate_is_named_and_closes",
          "assert"),

    # --- R2. the retrieval budget moves to where it is served --------------
    Proof("R2a. a refusing site is called absent instead of blocked",
          SVC,
          '            web_plan = OFFICIAL_WEB_BLOCKED',
          '            web_plan = OFFICIAL_WEB_ABSENT',
          f"{TR}::test_a_refusing_site_is_named_as_blocked_not_as_thin_evidence",
          "assert"),
    Proof("R2b. the blocked run goes back to the ordinary EDGAR budget",
          SVC,
          '            limit=(MAX_EDGAR_CANDIDATES_WEB_BLOCKED\n'
          '                   if web_plan in (OFFICIAL_WEB_ABSENT, OFFICIAL_WEB_BLOCKED)\n'
          '                   else MAX_EDGAR_CANDIDATES),',
          '            limit=MAX_EDGAR_CANDIDATES,',
          f"{TR}::test_the_blocked_budget_is_strictly_larger_and_is_the_one_used",
          "assert"),

    # --- R4. a guess at a closed door is not worth a request ---------------
    Proof("R4a. the closed-door guesses are eligible again",
          APP,
          '        candidates = [c for c in candidates\n'
          '                      if not _is_a_guess_at_a_closed_door(c)]',
          '        candidates = list(candidates)',
          f"{TD}::test_a_guess_at_a_refusing_host_is_never_approved",
          "assert"),
    Proof("R4b. the exclusion stops sparing a curated URL",
          APP,
          '            if method in ("official_fallback", "third_party_filing"):\n'
          '                return False',
          '            if method in ("third_party_filing",):\n'
          '                return False',
          f"{TD}::test_a_curated_url_survives_the_refusal",
          "assert"),
    Proof("R4c. a subdomain of a refusing host stops counting as refused",
          APP,
          '            return any(host == bad or host.endswith("." + bad)\n'
          '                       for bad in refused)',
          '            return any(host == bad for bad in refused)',
          f"{TD}::test_a_subdomain_of_a_refusing_host_is_also_a_closed_door",
          "assert"),

    # --- R5. a 5xx may never be scored as a company that worked ------------
    Proof("R5a. the server error stops being scored",
          VER,
          '        if code >= 400:\n'
          '            failures.append(_fail("ROUTE_ERROR", f"{name}=HTTP {code}"))',
          '        if False:\n'
          '            failures.append(_fail("ROUTE_ERROR", f"{name}=HTTP {code}"))',
          "tests/test_a_500_is_never_a_pass.py::test_a_server_error_on_a_required_route_fails",
          "assert"),
    Proof("R5b. a stated success over a 5xx goes unremarked",
          VER,
          '    if stated in O.SUCCESSFUL and errored:',
          '    if False and stated in O.SUCCESSFUL and errored:',
          "tests/test_a_500_is_never_a_pass.py::test_a_success_claimed_on_a_server_error_is_a_defect",
          "assert"),

    # --- R6. the log is parsed once, not once per read ---------------------
    Proof("R6a. the whole log is re-parsed on every read again",
          LOG,
          "        if (self._cache_rows is not None and offset is not None\n"
          "                and size > offset):",
          "        if False:",
          f"{TL}::test_the_tail_is_the_only_thing_reparsed",
          "re-parsed"),
    Proof("R6b. a same-size rewrite is mistaken for growth",
          LOG,
          "        key = self._fingerprint()\n"
          "        if key is not None and key == self._cache_key:",
          "        key = self._fingerprint()\n"
          "        if key is not None and self._cache_key is not None:",
          f"{TL}::test_a_same_size_rewrite_is_parsed_again_in_full",
          "assert"),
    Proof("R6c. a shrinking file keeps rows it no longer has",
          LOG,
          "                and size > offset):",
          "                and size != offset):",
          f"{TL}::test_a_shrinking_file_is_parsed_again_in_full",
          "assert"),
    Proof("R6d. the offset read stops landing on a line boundary",
          LOG,
          "            if offset:\n                f.seek(offset)",
          "            if offset:\n                f.seek(offset + 1)",
          f"{TL}::test_multibyte_text_survives_an_offset_read",
          "assert"),

    # --- R7. one readiness read per request --------------------------------
    Proof("R7a. the memo is dropped and the page asks three times",
          APP,
          '        memo = getattr(self._request, "readiness", None)\n'
          "        if memo is not None and run_id in memo:\n"
          "            return memo[run_id]",
          "        memo = None",
          f"{TM}::test_one_request_computes_it_once",
          "assert"),
    Proof("R7b. the memo outlives the request that made it",
          APP,
          "        self._request.readiness = {}\n",
          "        self._request.readiness = getattr(\n"
          '            self._request, "readiness", {})\n',
          f"{TM}::test_the_next_request_does_not_inherit_the_answer",
          "assert"),
    Proof("R7c. one run's verdict is served for another run",
          APP,
          '        memo = getattr(self._request, "readiness", None)\n'
          "        if memo is not None and run_id in memo:\n"
          "            return memo[run_id]",
          '        memo = getattr(self._request, "readiness", None)\n'
          "        if memo:\n"
          "            return next(iter(memo.values()))",
          f"{TM}::test_a_different_run_in_the_same_request_is_its_own_answer",
          "assert"),

    # --- R8. a run may compose twice -------------------------------------
    Proof("R8a. the ownership record forgets what it is recording",
          SVC,
          'idempotency_key=f"ci-ownership:{run_id}:{len(documents)}")',
          'idempotency_key=f"ci-ownership:{run_id}")',
          "tests/test_a_run_may_compose_twice.py::"
          "test_a_second_composition_over_more_evidence_does_not_raise",
          "raised"),
    Proof("R8b. the key stops naming the document count",
          SVC,
          'idempotency_key=f"ci-ownership:{run_id}:{len(documents)}")',
          'idempotency_key=f"ci-ownership:{run_id}:x")',
          "tests/test_a_run_may_compose_twice.py::"
          "test_the_key_names_the_document_count",
          "assert"),
]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS, title=__doc__.splitlines()[0]))

#!/usr/bin/env python3
"""Break proofs for the discovery-account propagation repair (§3, §14).

Each mutation re-creates the live defect MEASURED 2026-09-11 on the deployed
preview: three re-analysed companies all reported

    Search coverage: no search was run
    No discovery run is recorded for this analysis

over source lists that a real EDGAR full-text search had produced --
ZoomInfo's at DISCOVERY_EXHAUSTED, 47 hits, 6 documents fetched.

A proof counts only if the source hash changes, the named test was green
before, turns RED after, and the failure text matches what the proof claims.

Run:  PYTHONPATH=src python scripts/break_proofs_discovery_propagation.py
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from break_proof_harness import Proof, run_all           # noqa: E402

ROOT = HERE.parent
SERVICE = ROOT / "src/intent_engine/company_ingestion/service.py"
RELEVANCE = ROOT / "src/intent_engine/company_ingestion/relevance.py"
SNAPSHOT_FDS = ROOT / "src/intent_engine/external_intel/founder_demo_snapshot.py"
APP = ROOT / "src/intent_engine/webapp/app.py"
CATALOG = ROOT / "src/intent_engine/company_ingestion/catalog.py"
HIST = ROOT / "src/intent_engine/executive/history_rewind.py"
SUGGEST = ROOT / "src/intent_engine/company_ingestion/suggest.py"
STEPS = ROOT / "src/intent_engine/founder_brief/steps.py"
L = "tests/test_level_b_is_not_one_page_for_every_company.py"
T = "tests/test_a_reused_source_list_keeps_its_search.py"

PROOFS = [
    # --- the loss itself ---------------------------------------------------
    Proof(
        label="1. the snapshot keeps the sources and drops the search",
        path=SERVICE,
        find='                    **({"discovery_coverage": dict(discovery)}\n'
             "                       if isinstance(discovery, dict) and discovery else {}),",
        replace="",
        target=f"{T}::test_the_snapshot_carries_the_search_the_cold_run_did",
        expect_failure_contains="discarded how they were found"),

    Proof(
        label="2. the writer is never given the account (optional-param trap)",
        path=SERVICE,
        find="            self._write_snapshot(run_id, meta, stored_candidates,\n"
             "                                 discovery=self.discovery_report(run_id))",
        replace="            self._write_snapshot(run_id, meta, stored_candidates)",
        target=f"{T}::test_the_snapshot_writer_is_given_the_account",
        expect_failure_contains="only caller never"),

    Proof(
        label="3. the warm branch returns without restoring the account",
        path=SERVICE,
        find="                    self._reuse_discovery_account(run_id, snap)\n",
        replace="",
        target=f"{T}::test_a_warm_run_reports_the_search_it_inherited",
        expect_failure_contains="reported NO search"),

    Proof(
        label="4. the stored-candidate short circuit loses the account",
        path=SERVICE,
        # A DELETION HERE EMPTIES THE `if` BODY, and the harness correctly
        # reported the resulting IndentationError as WRONG_REASON rather than
        # as a caught mutation. The guard is disabled by keeping the branch and
        # removing only its effect.
        find="                self._restore_discovery_for_stored(run_id)",
        replace="                pass",
        target=f"{T}::test_a_rerun_of_a_reused_run_recovers_the_account",
        expect_failure_contains="reported no search at all"),

    # --- the honesty of what is restored -----------------------------------
    Proof(
        label="5. an inherited search is presented as this run's own",
        path=SERVICE,
        find='                account["reused_from_snapshot"] = True',
        replace='                account["reused_from_snapshot"] = False',
        target=f"{T}::test_a_warm_run_says_the_search_was_not_performed_today",
        expect_failure_contains="presented as this analysis"),

    Proof(
        label="6. a reused account is restamped with today's date",
        path=SERVICE,
        find='                account = dict(stored)\n'
             '                account["reused_from_snapshot"] = True',
        replace='                account = dict(stored)\n'
                '                account["searched_on"] = "2026-09-11"\n'
                '                account["reused_from_snapshot"] = True',
        target=f"{T}::test_a_warm_run_says_the_search_was_not_performed_today",
        expect_failure_contains="restamped with today"),

    Proof(
        label="7. an unrecorded search is credited with a coverage grade",
        path=SERVICE,
        find='                    "coverage": _REL.DISCOVERY_NOT_RUN,\n'
             '                    "channels_attempted": [], "channels_successful": [],\n'
             '                    "hits_total": 0, "candidates_considered": 0,',
        replace='                    "coverage": _REL.DISCOVERY_EXHAUSTED,\n'
                '                    "channels_attempted": [], "channels_successful": [],\n'
                '                    "hits_total": 0, "candidates_considered": 0,',
        target=f"{T}::test_an_older_snapshot_says_the_account_is_OURS_to_miss",
        expect_failure_contains="coverage grade was claimed"),

    Proof(
        label="8. a cold run's lost account is filled from the snapshot",
        path=SERVICE,
        find='            if not self.discovery_report(run_id) and any(\n'
             '                    c.get("discovery_method") == "snapshot_reuse"\n'
             "                    for c in stored):",
        replace="            if not self.discovery_report(run_id):",
        target=f"{T}::test_a_cold_rerun_is_not_credited_with_a_search_it_lost",
        expect_failure_contains="silently replaced"),

    # --- the warm path must stay cheap -------------------------------------
    Proof(
        label="9. restoring the account re-runs the search it describes",
        path=SERVICE,
        find="                    self._reuse_discovery_account(run_id, snap)\n"
             "                    self._append(",
        replace="                    self._reuse_discovery_account(run_id, snap)\n"
                "                    self._third_party_filing_candidates(\n"
                "                        meta, run_id=run_id)\n"
                "                    self._append(",
        target=f"{T}::test_a_warm_run_still_does_no_discovery_work",
        expect_failure_contains="performed discovery work"),

    # --- the five states ---------------------------------------------------
    Proof(
        label="10. an unreachable channel reads as an empty record",
        path=RELEVANCE,
        find="    if attempted and not successful:\n"
             "        return SEARCH_BLOCKED",
        replace="    if False:\n"
                "        return SEARCH_BLOCKED",
        target=f"{T}::test_the_five_states_are_distinguished",
        expect_failure_contains="assert"),

    Proof(
        label="11. a spent budget is reported as never having started",
        path=RELEVANCE,
        find="    if not attempted and (report.get(\"budget_exhausted\")\n"
             "                          or SEARCH_BUDGET_SPENT in reasons):\n"
             "        return SEARCH_BUDGET_SPENT",
        replace="    if False:\n"
                "        return SEARCH_BUDGET_SPENT",
        target=f"{T}::test_all_five_states_are_reachable",
        expect_failure_contains="unreachable states"),

    Proof(
        label="12. an absent report is read as a measured zero",
        path=RELEVANCE,
        find="    if not isinstance(report, dict) or not report:\n"
             "        return SEARCH_NEVER_STARTED",
        replace="    if not isinstance(report, dict) or not report:\n"
                "        return SEARCH_RAN_WITH_NO_RESULTS",
        target=f"{T}::test_the_five_states_are_distinguished",
        expect_failure_contains="assert"),

    # --- the seam ----------------------------------------------------------
    Proof(
        label="13. the state never crosses the dossier contract",
        path=SNAPSHOT_FDS,
        find='        "search_state": _REL.search_state(discovery),',
        replace="",
        target=f"{T}::test_the_account_reaches_the_dossier_the_page_reads",
        expect_failure_contains="assert"),

    Proof(
        label="14. the reuse marker is dropped at the bridge",
        path=SNAPSHOT_FDS,
        find='        "reused_from_snapshot": bool(discovery.get("reused_from_snapshot")),',
        replace='        "reused_from_snapshot": False,',
        target=f"{T}::test_the_account_reaches_the_dossier_the_page_reads",
        expect_failure_contains="assert"),

    # --- the surface -------------------------------------------------------
    Proof(
        label="15. all five outcomes print one sentence again",
        path=APP,
        find="        if state == _REL.SEARCH_BUDGET_SPENT:",
        replace="        if False:",
        target=f"{T}::test_the_five_states_read_differently_to_a_human",
        expect_failure_contains="render the same sentence"),

    Proof(
        label="16. a reused search is printed without its date",
        path=APP,
        find="                    + (f'found on {_e(when)}' if when else 'found earlier')",
        replace="                    + 'found earlier'",
        target=f"{T}::test_a_reused_search_prints_the_date_it_ran",
        expect_failure_contains="reuse date is not shown"),

    Proof(
        label="17. a reused list with no account reads as no search at all",
        path=APP,
        find='            if (discovery or {}).get("account_unavailable"):',
        replace="            if False:",
        target=f"{T}::test_a_reused_list_without_an_account_claims_no_coverage",
        expect_failure_contains="assert"),
    # --- the identity catalog for the next forty ---------------------------
    Proof(
        label="18. Clari resolves to Clarivate again",
        path=CATALOG,
        # THE WHOLE IDENTITY, because nothing smaller is load-bearing here.
        # Removing the alias left `common_name` matching EXACTly; changing
        # `common_name` left the alias matching; changing both still left
        # `legal_name` scoring LEADING, and a registry LEADING outranks a
        # registrant LEADING anyway. The harness reported NOT_CAUGHT twice and
        # was right both times: what carries this test is that the entry
        # EXISTS under a name the customer types, so that is what is removed.
        find='        "legal_name": "Clari Inc.",\n'
             '        "common_name": "Clari",\n'
             '        "country": "United States",\n'
             '        "primary_domain": "clari.com",\n'
             '        "aliases": ("clari", "clari inc"),',
        replace='        "legal_name": "Revenue Platform Holdings Inc.",\n'
                '        "common_name": "Revenue Platform",\n'
                '        "country": "United States",\n'
                '        "primary_domain": "clari.com",\n'
                '        "aliases": ("revenue platform",),',
        target="tests/test_company_catalog_identity.py::"
               "test_a_collision_puts_us_first_and_still_offers_the_other"
               "[Clari-clari-Clarivate]",
        expect_failure_contains="before clari"),

    Proof(
        label="19. a refused host carries invented sub-paths",
        path=CATALOG,
        find='            ("https://www.6sense.com", _CORPORATE,\n'
             '             "home — refused our reader (HTTP 403)", _P),',
        replace='            ("https://www.6sense.com", _CORPORATE,\n'
                '             "home — refused our reader (HTTP 403)", _P),\n'
                '            ("https://www.6sense.com/platform", _SEGMENT,\n'
                '             "platform", _P),',
        target="tests/test_company_catalog_identity.py::"
               "test_a_host_that_refuses_us_still_records_that_we_tried"
               "[6sense]",
        expect_failure_contains="only the probed homepage is attested"),

    Proof(
        label="20. two entries claim one alias, and order decides the winner",
        path=CATALOG,
        find='        "aliases": ("dremio", "dremio corporation"),',
        replace='        "aliases": ("dremio", "dremio corporation", "denodo"),',
        target="tests/test_company_catalog_identity.py::"
               "test_no_two_entries_claim_the_same_name_or_domain",
        expect_failure_contains="both claim the alias"),

    Proof(
        label="21. FourKites points at the domain that redirects away",
        path=CATALOG,
        find='        "primary_domain": "fourkites.ai",',
        replace='        "primary_domain": "fourkites.com",',
        target="tests/test_company_catalog_identity.py::"
               "test_fourkites_points_at_the_domain_it_actually_publishes_on",
        expect_failure_contains="redirects off-domain"),

    Proof(
        label="22. a curated source may sit on any TLD sharing the name",
        path=CATALOG,
        find='            ("https://www.dremio.com/newsroom", _NEWSROOM,',
        replace='            ("https://www.dremio.io/newsroom", _NEWSROOM,',
        target="tests/test_company_catalog_identity.py::"
               "test_every_catalog_url_is_on_the_company_s_own_domain",
        expect_failure_contains="not on dremio.com"),
    # --- LEVEL B: one page per company, in its own period -------------------
    Proof(
        label="23. every company is told what it could establish",
        path=HIST,
        find="    kinds = _kinds_of(before)\n"
             "    learns = [_KNOWABLE_BY_KIND[k] for k in kinds "
             "if k in _KNOWABLE_BY_KIND]",
        replace="    kinds = _kinds_of(before)\n"
                "    learns = list(_KNOWABLE_BY_KIND.values())",
        target=f"{L}::"
               "test_what_was_knowable_depends_on_what_the_company_published",
        expect_failure_contains="no pricing page was described"),

    Proof(
        label="24. the record is a count again, not the company's own pages",
        path=HIST,
        find='    if titles:\n'
             '        bits.append(f"most recently {titles}")',
        replace="    if False:\n"
                '        bits.append("")',
        target=f"{L}::test_the_record_names_the_company_s_own_pages",
        expect_failure_contains="never quoted one of"),

    Proof(
        label="25. a later economic state is rendered as the period's own",
        path=HIST,
        find='    if as_of and as_of > when.isoformat():\n'
             "        # The reader handed back a LATER state. Refused: see above.\n"
             "        return \"\", ECON_NO_STATE_FOR_DATE",
        replace="    if False:\n"
                "        return \"\", ECON_NO_STATE_FOR_DATE",
        target=f"{L}::"
               "test_no_stop_borrows_an_economic_state_from_after_its_own_date",
        expect_failure_contains="hindsight"),

    Proof(
        label="26. an unreadable econ store breaks the whole rewind",
        path=HIST,
        find="    try:\n"
             "        context = econ_at(when.isoformat())\n"
             "    except Exception:                                      "
             "# noqa: BLE001\n"
             "        return \"\", ECON_NO_STATE_FOR_DATE",
        replace="    context = econ_at(when.isoformat())",
        target=f"{L}::test_a_raising_reader_costs_the_panel_and_not_the_page",
        expect_failure_contains="RuntimeError"),

    Proof(
        label="27. zero linked stops reads as an uneventful period",
        path=HIST,
        find='            "before any of these dates, so none of the stops is placed "\n'
             '            "beside the economic conditions of its period. That is a gap in "\n'
             '            "what this deployment has recorded, not a judgement that the "\n'
             '            "period was uneventful."),',
        replace='            "before any of these dates."),',
        target=f"{L}::test_zero_linked_stops_is_stated_not_hidden",
        expect_failure_contains="assert"),

    Proof(
        label="28. the missing economic panel is omitted silently",
        path=STEPS,
        find="        elif state == _HR.ECON_NO_STATE_FOR_DATE:",
        replace="        elif False:",
        target=f"{L}::test_the_page_says_why_a_period_has_no_economy",
        expect_failure_contains="assert"),

    Proof(
        label="29. the page stops passing a date-bound economic reader",
        path=APP,
        find="            bounded = HR.bounded_rewind(company=timeline.company or name,\n"
             "                                        records=records, econ_at=_econ_at)",
        replace="            bounded = HR.bounded_rewind(company=timeline.company or name,\n"
                "                                        records=records)",
        target=f"{L}::"
               "test_the_history_page_actually_passes_an_economic_reader",
        expect_failure_contains="without an economic reader"),
    # --- the regulator's identifier ----------------------------------------
    Proof(
        label="30. a catalogued filer reaches the customer with no CIK",
        path=SUGGEST,
        find='            cik=str(getattr(profile, "sec_cik", "") or ""),',
        replace='            cik="",',
        target="tests/test_company_catalog_identity.py::"
               "test_a_catalogued_filer_carries_its_cik_without_the_network"
               "[rubrik-0001943896-RBRK]",
        expect_failure_contains="the catalog declares"),

    Proof(
        label="31. the ticker is read from a field that does not exist",
        path=SUGGEST,
        find="    for listing in (getattr(profile, \"listings\", ()) or ()):",
        replace="    for listing in ():",
        target="tests/test_company_catalog_identity.py::"
               "test_a_canadian_issuer_carries_a_ticker_and_no_sec_cik",
        expect_failure_contains="assert"),

    Proof(
        label="32. a private company is given a CIK it does not have",
        path=SUGGEST,
        find='            cik=str(getattr(profile, "sec_cik", "") or ""),',
        replace='            cik=str(getattr(profile, "sec_cik", "") or "0000000000"),',
        target="tests/test_company_catalog_identity.py::"
               "test_a_private_company_invents_neither",
        expect_failure_contains="acquired a CIK from nowhere"),
    # --- two companies must not become one ---------------------------------
    Proof(
        label="33. the merge key strips a NAME word and fuses two companies",
        path=SUGGEST,
        find='    "n.v.", "sa", "s.a.", "ag", "se", "the", "&", "and",\n'
             "})\n"
             "\n"
             "\n"
             "def identity_key(name: str) -> str:",
        replace='    "n.v.", "sa", "s.a.", "ag", "se", "the", "&", "and",\n'
                '    "group", "holdings", "holding",\n'
                "})\n"
                "\n"
                "\n"
                "def identity_key(name: str) -> str:",
        target="tests/test_two_companies_are_not_merged_into_one.py::"
               "test_two_different_companies_do_not_share_an_identity_key"
               "[Adastra Corporation-Adastra Holdings Ltd.]",
        expect_failure_contains="both reduce to"),

    Proof(
        label="34. the merge goes back to the matcher's lossy key",
        path=SUGGEST,
        find="        key = identity_key(row.legal_name)",
        replace='        key = " ".join(_words(row.legal_name))',
        target="tests/test_two_companies_are_not_merged_into_one.py::"
               "test_the_consultancy_does_not_inherit_the_cannabis_company_s_cik",
        expect_failure_contains="belongs to"),

    Proof(
        label="35. contradicting CIKs are merged anyway",
        path=SUGGEST,
        find="        if _contradicts(held, row):",
        replace="        if False:",
        target="tests/test_two_companies_are_not_merged_into_one.py::"
               "test_rows_that_disagree_on_a_cik_are_not_merged",
        expect_failure_contains="were merged into one"),

    Proof(
        label="36. a source's own id convention splits one company in two",
        path=SUGGEST,
        find='    for field in ("cik", "domain"):',
        replace='    for field in ("cik", "domain", "entity_id"):',
        target="tests/test_two_companies_are_not_merged_into_one.py::"
               "test_a_source_s_own_id_convention_is_not_treated_as_disagreement",
        expect_failure_contains="split in two"),

    Proof(
        label="37. the merge stops merging and one company is offered twice",
        path=SUGGEST,
        find="        if _contradicts(held, row):\n"
             '            merged[f"{key}#{row.source}:'
             '{row.cik or row.domain or row.legal_name}"] = row\n'
             "            continue",
        replace='        merged[f"{key}#{row.source}"] = row\n'
                "        continue",
        target="tests/test_two_companies_are_not_merged_into_one.py::"
               "test_one_company_from_two_sources_is_still_offered_once",
        expect_failure_contains="was offered"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        PROOFS,
        title="DISCOVERY + CATALOG + LEVEL B + FILER CIK + ONE IDENTITY"))

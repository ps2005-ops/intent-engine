#!/usr/bin/env python3
"""Break proofs for the cohort-A P1 batch.

Every mutation re-creates a defect MEASURED on the live preview at
8495b00c across fourteen companies:

    P1-2  project44's evidence page said "Search coverage: no search was run"
          about a search that had been dispatched and then abandoned
    P1-3  three unrelated companies received "how the product is sold, and by
          whom" because "go-to-market" and "channel partner" are on every
          B2B page; and "support" manufactured the evidence term "port"
    P1-4  the unplaced economic note printed five times on one walk
    P1-5  the lesson printed four times on one walk, on the branches the
          earlier repair did not reach
    P1-6  Rubrik and Commvault were both given 37signals, Adobe and
          AgileBits as "Competitors", each row repeating one class sentence
    P1-7  a Python dict repr was rendered at the reader inside the economic
          sentence

A proof counts only if the source hash changes, the named test was green
before, turns RED after, and the failure text matches what the proof claims.

Run:  PYTHONPATH=src python scripts/break_proofs_cohort_a_batch.py
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from break_proof_harness import Proof, run_all           # noqa: E402

ROOT = HERE.parent
SEL = ROOT / "src/intent_engine/executive/analysis_selection.py"
REL = ROOT / "src/intent_engine/company_ingestion/relevance.py"
SVC = ROOT / "src/intent_engine/company_ingestion/service.py"
APP = ROOT / "src/intent_engine/webapp/app.py"
HIST = ROOT / "src/intent_engine/executive/history_rewind.py"
STEPS = ROOT / "src/intent_engine/founder_brief/steps.py"
XRAY = ROOT / "src/intent_engine/founder_brief/xray.py"

V = "tests/test_category_vocabulary_is_not_a_decision.py"
A = "tests/test_an_abandoned_search_is_ours_to_own.py"
S = "tests/test_a_stop_teaches_something_of_its_own.py"
P = "tests/test_peers_share_one_stated_basis.py"
FR = "tests/test_a_filing_reports_what_a_company_decides.py"
TL = "tests/test_a_timeline_walks_only_its_own_filings.py"
POST = "tests/test_posture_selects_the_decision.py"

PROOFS = [
    # --- P1-3 the evidence semantics ---------------------------------------
    Proof(
        label="1. SALES_MOTION goes back to category vocabulary",
        path=SEL,
        find='    "SALES_MOTION": ("channel conflict", "partner-led", "partner led",',
        replace='    "SALES_MOTION": ("go-to-market", "channel partner", "partner program",',
        target=f"{V}::test_an_ordinary_b2b_page_shows_no_decision_at_all",
        expect_failure_contains="SALES_MOTION"),

    Proof(
        label="2. REGULATORY_RESPONSE goes back to naming the topic",
        path=SEL,
        find='    "REGULATORY_RESPONSE": ("new regulation", "regulatory change",',
        replace='    "REGULATORY_RESPONSE": ("regulation", "compliance", "gdpr",',
        target=f"{V}::test_no_entry_in_the_table_is_bare_category_vocabulary",
        expect_failure_contains="REGULATORY_RESPONSE"),

    Proof(
        label="3. R&D_ROADMAP counts a free trial as a clinical programme",
        path=SEL,
        find='    "R&D_ROADMAP": ("research and development", "clinical trial",',
        replace='    "R&D_ROADMAP": ("research and development", "clinical", "trial",',
        target=f"{V}::test_no_entry_in_the_table_is_bare_category_vocabulary",
        expect_failure_contains="R&D_ROADMAP"),

    Proof(
        label="4. the phrase match goes back to a substring",
        path=SEL,
        find="        hit = tuple(sorted({p for p in phrases if _says(text, p)}))",
        replace="        hit = tuple(sorted({p for p in phrases if p in text}))",
        target=f"{V}::test_one_word_is_not_counted_as_two_phrases",
        expect_failure_contains="assert"),

    Proof(
        label="5. the boundary holds on the left of a phrase only",
        path=SEL,
        find='            r"(?<![0-9a-z])" + re.escape(phrase) + r"(?![0-9a-z])")',
        replace='            r"(?<![0-9a-z])" + re.escape(phrase))',
        target=f"{V}::test_says_matches_words_and_not_fragments",
        expect_failure_contains="assert"),

    Proof(
        label="6. two hits stop being required, so a coincidence reorders",
        path=SEL,
        find="_EVIDENCE_MIN_HITS = 2",
        replace="_EVIDENCE_MIN_HITS = 1",
        target=f"{V}::test_one_decision_bearing_phrase_is_still_a_coincidence",
        expect_failure_contains="one phrase must not reorder the menu"),

    Proof(
        label="28. the boundary regex runs before its substring prefilter",
        path=SEL,
        find="    if phrase not in text:\n"
             "        return False\n"
             "    pattern = _BOUNDARY.get(phrase)",
        replace="    pattern = _BOUNDARY.get(phrase)",
        target=f"{V}::test_the_word_boundary_is_prefiltered_by_a_substring_test",
        expect_failure_contains="every phrase pays for the engine"),

    # --- the legacy fixtures, after they were corrected -------------------
    #
    # The batch turned two of them red. Their PROPERTY was sound -- the
    # decision follows the company's own record -- but their TEXT was the
    # category vocabulary this batch removed, so they were demonstrating the
    # evidence path with prose that cannot distinguish one company from
    # another. The fixtures were rewritten as a company DECIDING. These two
    # proofs check that the rewrite is load-bearing rather than convenient.
    Proof(
        label="25. one mention is enough again, so a coincidence reorders",
        path=SEL,
        find="_EVIDENCE_MIN_HITS = 2",
        replace="_EVIDENCE_MIN_HITS = 1",
        target="tests/test_the_class_prior_is_not_the_decision.py"
               "::test_one_passing_mention_does_not_move_the_menu",
        expect_failure_contains="reordered the"),

    Proof(
        label="26. SALES_MOTION stops being reachable at all",
        path=SEL,
        find='    "SALES_MOTION": ("channel conflict", "partner-led", "partner led",\n                     "channel dependence", "route to market",\n                     "route-to-market", "direct sales force",\n                     "sales capacity", "sales productivity",\n                     "quota capacity", "partner concentration",\n                     "reseller margin", "reseller economics",\n                     "customer acquisition cost", "cac payback",\n                     "payback period", "land and expand",\n                     "sales cycle lengthened", "shift to direct",\n                     "shift to channel"),\n',
        replace='    "SALES_MOTION": ("zzz_unreachable_a",\n                     "zzz_unreachable_b"),\n',
        target="tests/test_the_class_prior_is_not_the_decision.py"
               "::test_the_decision_follows_the_company_s_own_record",
        expect_failure_contains="assert"),

    # --- the filing register, and the tie the alphabet was deciding -------
    Proof(
        label="29. M&A goes back to accounting-note wording",
        path=SEL,
        find='    "M&A": ("announced the acquisition", "agreed to acquire",',
        replace='    "M&A": ("acquisition of", "acquired by", "combination with",',
        target=f"{FR}::test_an_ordinary_filing_paragraph_decides_nothing",
        expect_failure_contains="M&A"),

    Proof(
        label="30. retention counts a disclosed metric as a decision",
        path=SEL,
        find='    "RETENTION": ("customer retention", "retention programme",',
        replace='    "RETENTION": ("net revenue retention", "churn", "renewal rate",',
        target=f"{FR}::test_an_ordinary_filing_paragraph_decides_nothing",
        expect_failure_contains="RETENTION"),

    Proof(
        label="31. cost structure counts a reported line item",
        path=SEL,
        find='    "COST_STRUCTURE": ("cost structure", "restructuring",\n'
             '                       "restructuring charge", "layoff",',
        replace='    "COST_STRUCTURE": ("cost structure", "gross margin",\n'
                '                       "operating leverage", "headcount",',
        target=f"{FR}::test_an_ordinary_filing_paragraph_decides_nothing",
        expect_failure_contains="COST_STRUCTURE"),

    Proof(
        label="32. capital allocation counts a mandatory disclosure",
        path=SEL,
        find='    "CAPITAL_ALLOCATION": ("capital allocation", "buyback",',
        replace='    "CAPITAL_ALLOCATION": ("capital allocation", "free cash flow",\n'
                '                           "dividend", "capital expenditure", "buyback",',
        target=f"{FR}::test_an_ordinary_filing_paragraph_decides_nothing",
        expect_failure_contains="CAPITAL_ALLOCATION"),

    Proof(
        label="33. the tie goes back to the alphabet",
        path=SEL,
        find="    order = {a: i for i, a in enumerate(menu)}\n"
             "    standing_set = set(standing)\n"
             '    rows.sort(key=lambda r: (-r["score"],\n'
             '                             0 if r["archetype"] in standing_set else 1,\n'
             '                             order.get(r["archetype"], len(menu)),\n'
             '                             r["archetype"]))',
        replace='    rows.sort(key=lambda r: (-r["score"], r["archetype"]))',
        target=f"{FR}::test_an_off_menu_archetype_that_only_ties_does_not_displace_the_prior",
        expect_failure_contains="displaced the class prior"),

    Proof(
        label="34. an off-menu archetype can no longer displace at all",
        path=SEL,
        find='    rows.sort(key=lambda r: (-r["score"],\n'
             '                             0 if r["archetype"] in standing_set else 1,',
        replace='    rows.sort(key=lambda r: (0 if r["archetype"] in standing_set else 1,\n'
                '                             -r["score"],',
        target=f"{FR}::test_an_off_menu_archetype_that_strictly_exceeds_still_wins",
        expect_failure_contains="assert"),

    Proof(
        label="35. the posture stops selecting from its own map",
        path=SEL,
        find='            if archetype in _POSTURE_FAVOURS.get(posture, ()):\n'
             "                score += _POSTURE_WEIGHT",
        replace='            if archetype in ():\n'
                "                score += _POSTURE_WEIGHT",
        target=f"{POST}::test_the_posture_selects_the_archetype",
        expect_failure_contains="does not favour at all"),

    # --- the timeline may only walk the subject's own filings -------------
    Proof(
        label="36. the timeline takes any sec.gov document again",
        path=HIST,
        find="        filer = filing_author(url)\n"
             "        if not want or not filer or filer != want:\n"
             "            continue",
        replace="        pass",
        target=f"{TL}::test_a_non_filer_gets_no_regulatory_timeline",
        expect_failure_contains="assert"),

    Proof(
        label="37. a non-filer is handed whatever was retrieved",
        path=HIST,
        find="        if not want or not filer or filer != want:",
        replace="        if filer and want and filer != want:",
        target=f"{TL}::test_a_non_filer_gets_no_regulatory_timeline",
        expect_failure_contains="assert"),

    Proof(
        label="38. the call site stops passing the subject's identity",
        path=APP,
        find="filings = HR.filings_from_documents(documents, subject_cik=cik)",
        replace="filings = HR.filings_from_documents(documents)",
        target=f"{TL}::test_the_call_site_passes_the_subject_cik",
        expect_failure_contains="without the subject's identity"),

    # --- P1-2 the discovery state -----------------------------------------
    Proof(
        label="7. a named budget cause needs an undispatched channel again",
        path=REL,
        find="    if SEARCH_BUDGET_SPENT in reasons:\n"
             "        return SEARCH_BUDGET_SPENT",
        replace="    if not attempted and SEARCH_BUDGET_SPENT in reasons:\n"
                "        return SEARCH_BUDGET_SPENT",
        target=f"{A}::test_a_named_budget_cause_wins_even_though_a_channel_was_dispatched",
        expect_failure_contains="assert"),

    Proof(
        label="8. every unreachable channel becomes a budget instead",
        path=REL,
        find="    if attempted and not successful:\n"
             "        return SEARCH_BLOCKED",
        replace="    if attempted and not successful:\n"
                "        return SEARCH_BUDGET_SPENT",
        target=f"{A}::test_a_channel_tried_and_unreachable_is_still_blocked",
        expect_failure_contains="assert"),

    Proof(
        label="9. the abandoned join stops recording an account",
        path=SVC,
        find="                if _tp is None and run_id:\n"
             "                    self._record_abandoned_discovery(",
        replace="                if False and run_id:\n"
                "                    self._record_abandoned_discovery(",
        target=f"{A}::test_the_discovery_stage_actually_records_an_abandoned_wait",
        expect_failure_contains="recorded only when the join returned nothing"),

    Proof(
        label="10. the account overwrites a real one that arrived late",
        path=SVC,
        find="        if self._discovery_reports.get(run_id):\n"
             "            return",
        replace="        if False:\n"
                "            return",
        target=f"{A}::test_an_abandoned_wait_never_overwrites_a_real_account",
        expect_failure_contains="assert"),

    Proof(
        label="11. the header goes back to printing the coverage grade",
        path=APP,
        find="        if str(coverage or \"\") == _REL.DISCOVERY_NOT_RUN and search_state:",
        replace="        if False and search_state:",
        target=f"{A}::test_the_header_never_claims_no_search_when_one_was_dispatched",
        expect_failure_contains="no search was run"),

    # --- the internal token on the same drawer ----------------------------
    Proof(
        label="23. an exception class is printed at the reader again",
        path=APP,
        find="                f\"{_e(WebApp._rejection_english(k))}: {int(v)}\"",
        replace="                f\"{_e(str(k).replace('_', ' ').lower())}: {int(v)}\"",
        target=f"{A}::test_the_drawer_lists_reasons_without_their_exception_types",
        expect_failure_contains="assert"),

    Proof(
        label="24. an unmapped reason keeps its exception type",
        path=APP,
        find="        head = raw.split(\":\", 1)[0]",
        replace="        head = raw",
        target=f"{A}::test_an_unmapped_reason_still_degrades_to_words",
        expect_failure_contains="assert"),

    Proof(
        label="27. a producer reason loses its English and reaches the reader",
        path=APP,
        find='        "SUBJECT_OWN_FILING": "filed by this company itself, so not an "\n                              "independent source",\n',
        replace='',
        target=f"{A}::test_every_reason_the_producer_can_write_has_english",
        expect_failure_contains="no English for"),

    Proof(
        label="39. the empty-provenance page prints the raw constant again",
        path=APP,
        find="f'{_e(self._plain_state(state) or \"no provenance to show\")}'",
        replace="f'{_e(state or \"PROVENANCE_UNAVAILABLE\")}'",
        target=f"{A}::test_the_evidence_page_does_not_print_the_bare_constant",
        expect_failure_contains="prints the constant instead of words"),

    Proof(
        label="40. the drawer's own test stops requiring plain words",
        path=APP,
        find="f'{_e(self._plain_state(state) or \"no provenance to show\")}'",
        replace="f'{_e(state or \"PROVENANCE_UNAVAILABLE\")}'",
        target="tests/test_evidence_drawer.py"
               "::test_an_absent_projection_is_a_state_not_no_sources",
        expect_failure_contains="printed at the reader"),

    # --- P1-7 the leaked dict ---------------------------------------------
    Proof(
        label="12. the economic condition is rendered with str() again",
        path=HIST,
        find="    named = _join([_condition_english(k, v)",
        replace="    named = _join([f\"{str(k).replace('_', ' ')} {str(v)}\"",
        target=f"{S}::test_the_economic_sentence_itself_never_carries_a_dict",
        expect_failure_contains="assert"),

    Proof(
        label="13. an unknown reading is named as though it were measured",
        path=HIST,
        find='                   if not isinstance(v, dict) or v.get("known")])',
        replace="                   ])",
        target=f"{S}::test_an_unknown_condition_is_not_named_as_a_reading",
        expect_failure_contains="assert"),

    # --- P1-5 the lesson branches, one proof per branch -------------------
    Proof(
        label="14. the gained branch stops naming how far away the material was",
        path=HIST,
        find='                     + (f" {wait} day(s) after this stop" if wait else "")',
        replace='                     + ""',
        target=f"{S}::test_two_stops_with_the_same_missing_kind_do_not_repeat",
        expect_failure_contains="assert"),

    Proof(
        label="15. the since branch stops naming what arrived",
        path=HIST,
        find='            + (f" ({which})" if which else "")\n'
             '            + f" stayed within subjects {company} was already publishing on, "',
        replace='            + ""\n'
                '            + f" stayed within subjects {company} was already publishing on, "',
        target=f"{S}::test_the_since_branch_names_what_arrived",
        expect_failure_contains="assert"),

    Proof(
        label="16. the quiet branch stops naming how long the quiet was",
        path=HIST,
        find='                 + (f" in the {gap_days} day(s) before this date"\n'
             '                    if gap_days else " new by this date")',
        replace='                 + " new by this date"',
        target=f"{S}::test_the_quiet_branch_names_how_long_the_quiet_was",
        expect_failure_contains="assert"),

    Proof(
        label="17. a whole walk goes back to repeating one lesson",
        path=HIST,
        find="        awaited = [r for r in after\n"
             "                   if _kinds_of([r]) and _kinds_of([r])[0] in gained]",
        replace="        awaited = []",
        target=f"{S}::test_no_two_stops_in_a_walk_teach_the_same_lesson",
        expect_failure_contains="assert"),

    # --- P1-4 the repeated economic note ----------------------------------
    Proof(
        label="18. the unplaced economic note is printed at every stop again",
        path=STEPS,
        find="        elif (state == _HR.ECON_NO_STATE_FOR_DATE and _any_linked\n"
             "                and not _said_no_state):\n"
             "            _said_no_state = True",
        replace="        elif state == _HR.ECON_NO_STATE_FOR_DATE and _any_linked:\n"
                "            _said_no_state = True",
        target=f"{S}::test_the_unplaced_economic_note_is_stated_once_per_walk",
        expect_failure_contains="informs once and pads thereafter"),

    # --- P1-6 the peer set -------------------------------------------------
    Proof(
        label="19. every peer gets its own row and its own copy of one reason",
        path=XRAY,
        find="        groups = {}\n"
             "        for c in peers:",
        replace="        groups = {str(id(c)): [str(c.get('name', ''))] for c in peers}\n"
                "        for c in []:",
        target=f"{P}::test_peers_that_share_a_reason_are_listed_together",
        expect_failure_contains="three rows, one reason, one row"),

    Proof(
        label="20. the group stops refusing the claim it cannot support",
        path=XRAY,
        find="ranked: no source in this analysis states that any of them ",
        replace="ranked. ",
        target=f"{P}::test_the_shared_row_refuses_the_claim_it_cannot_support",
        expect_failure_contains="assert"),

    Proof(
        label="21. a peer with its own reason is flattened into the group",
        path=XRAY,
        find="            groups.setdefault(str(c.get(\"why\", \"\")), []).append(",
        replace="            groups.setdefault(\"one\", []).append(",
        target=f"{P}::test_a_peer_with_its_own_reason_keeps_its_own_row",
        expect_failure_contains="assert"),

    Proof(
        label="22. the heading implies the set was selected by rivalry",
        path=XRAY,
        find="f'{len(d.get(\"competitors\") or ())} same-class peer(s)',",
        replace="f'{len(d.get(\"competitors\") or ())} selected',",
        target=f"{P}::test_the_heading_states_the_basis_rather_than_implying_rivalry",
        expect_failure_contains="assert"),
]


if __name__ == "__main__":
    sys.exit(run_all(PROOFS, title="COHORT A P1 BATCH"))

#!/usr/bin/env python3
"""Break proofs for minimum-evidence CORE.

Each mutation is applied to a COPY of the tree, the named tests are run
before and after, and the proof holds only when they were green before and
are red after FOR THE STATED REASON. The shared worktree is never written:
`getsource` reads files from disk, and a tree that changes mid-run yields a
result about no particular revision.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

MUTATIONS = [
    dict(
        name="M1 the probe is never consulted",
        path="src/intent_engine/company_ingestion/service.py",
        old="""            if sufficiency_probe is not None:
                verdict = sufficiency_probe(ok)
                if verdict and verdict.get("sufficient"):
                    stopped_by = dict(verdict)""",
        new="""            if False:
                verdict = sufficiency_probe(ok)
                if verdict and verdict.get("sufficient"):
                    stopped_by = dict(verdict)""",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_a_satisfied_probe_stops_the_network"],
    ),
    dict(
        name="M2 acquisition dispatches every target in one wave",
        path="src/intent_engine/company_ingestion/service.py",
        old="""            width = max(1, int(self._FETCH_CONCURRENCY))
            waves = [list(targets[i:i + width])
                     for i in range(0, len(targets), width)] or [[]]""",
        new="""            waves = [list(targets)]""",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_a_satisfied_probe_stops_the_network"],
    ),
    dict(
        name="M3 deferred targets are recorded as failures",
        path="src/intent_engine/company_ingestion/service.py",
        old="""                deferred.extend(wave)
                continue""",
        new="""                for _cid in wave:
                    failed.append(self._fail(
                        run_id, domain, _cid, "deadline_exceeded",
                        "deferred", True))
                continue""",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_deferred_sources_are_not_failures"],
    ),
    dict(
        name="M4 the document floor is removed",
        path="src/intent_engine/company_ingestion/sufficiency.py",
        old="    if len(documents) < MIN_CORE_DOCUMENTS:",
        new="    if False:",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_the_floor_refuses_to_stop_on_almost_nothing"],
    ),
    dict(
        name="M5 a filer no longer waits for its own filing",
        path="src/intent_engine/company_ingestion/sufficiency.py",
        old="    if REQUIRE_SUBJECT_FILING_WHEN_FILER and not _subject_filing_present(",
        new="    if False and not _subject_filing_present(",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_a_filer_waits_for_its_own_filing"],
    ),
    dict(
        name="M6 sufficiency uses its own rule instead of the contract",
        path="src/intent_engine/company_ingestion/sufficiency.py",
        old="""    if state != READY_FOR_FULL_REPORT:""",
        new="""    if False:""",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_the_probe_uses_the_published_readiness_contract"],
    ),
    dict(
        name="M7 sitemap children are truncated in document order again",
        path="src/intent_engine/company_ingestion/sitemap.py",
        old="""        return {"sitemaps": prefer_readable_locales(locs,
                                                    MAX_SITEMAP_CHILDREN),
                "urls": []}""",
        new="""        return {"sitemaps": locs[:MAX_SITEMAP_CHILDREN], "urls": []}""",
        tests=["tests/test_locale_partitioned_sites.py::"
               "test_an_index_of_locale_sitemaps_reaches_the_readable_one"],
    ),
    dict(
        name="M8 the same page in three languages takes three slots",
        path="src/intent_engine/company_ingestion/sitemap.py",
        old="""            key = locale_free_path(url) if partitioned else url""",
        new="""            key = url""",
        tests=["tests/test_locale_partitioned_sites.py::"
               "test_one_page_in_three_languages_takes_one_slot"],
    ),
    dict(
        name="M9 registry responses are never cached",
        path="src/intent_engine/company_ingestion/edgar.py",
        old="""        hit = PUBLIC_METADATA.STORE.get(url)
        if hit is not None:
            return hit""",
        new="""        hit = None""",
        tests=["tests/test_shared_public_intelligence.py::"
               "test_the_ticker_table_is_downloaded_once_not_per_analysis"],
    ),
    dict(
        name="M10 a filing document would be cached as registry metadata",
        path="src/intent_engine/company_ingestion/edgar.py",
        old="""    if plain.startswith("https://data.sec.gov/submissions/"):
        return PUBLIC_METADATA.TTL_SUBMISSIONS_S
    return None""",
        new="""    return PUBLIC_METADATA.TTL_SUBMISSIONS_S""",
        tests=["tests/test_shared_public_intelligence.py::"
               "test_a_filing_document_is_never_held_in_the_metadata_cache"],
    ),
    dict(
        name="M11 pooled connections are handed back undrained",
        path="src/intent_engine/company_ingestion/httppool.py",
        old="""                keep = (response.version == 11
                        and "close" not in head.get("connection", "").lower()
                        and not remainder_pending)""",
        new="""                keep = True""",
        tests=["tests/test_connection_reuse.py::"
               "test_a_connection_with_bytes_left_on_it_is_not_reused"],
    ),
    dict(
        name="M13 the continuation reuses the spent interactive budget",
        path="src/intent_engine/webapp/app.py",
        old="""                deadline=Deadline.for_continuation(self._tier_for(run_id)))""",
        new="""                deadline=self._analysis_deadlines.get(run_id))""",
        tests=["tests/test_deferred_evidence_survives.py::"
               "test_the_worker_gives_the_continuation_a_fresh_budget"],
    ),
    dict(
        name="M14 a changed answer is not reported as changed",
        path="src/intent_engine/webapp/app.py",
        old="""        changed = sorted(k for k in before if before[k] != after[k])""",
        new="""        changed = []""",
        tests=["tests/test_deferred_evidence_survives.py::"
               "test_a_changed_thesis_is_announced_not_swapped_in"],
    ),
    dict(
        name="M15 the subject-filing scan reads a key production never writes",
        path="src/intent_engine/company_ingestion/sufficiency.py",
        old="""        for key in ("original_url", "final_url", "url"):""",
        new="""        for key in ("url",):""",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_a_filer_waits_for_its_own_filing"],
    ),
    dict(
        name="M16 the probe takes the CIK from run meta, which is empty",
        path="src/intent_engine/webapp/app.py",
        old="""        subject_cik = str(self.ci.subject_cik(meta) or "")""",
        new="""        subject_cik = str(meta.get("cik") or "")""",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_the_probe_resolves_a_cik_where_run_meta_has_none"],
    ),
    dict(
        name="M17 the worker never passes the probe (the change ships inert)",
        path="src/intent_engine/webapp/app.py",
        old="""                        sufficiency_probe=self._sufficiency_probe(run_id))""",
        new="""                        )""",
        tests=["tests/test_deferred_evidence_survives.py::"
               "test_the_worker_actually_passes_the_probe_to_acquisition"],
    ),
    dict(
        name="M18 deferred evidence is acquired before core_ready",
        path="src/intent_engine/webapp/app.py",
        old="""            if deferred_ids:
                try:
                    core = self._acquire_deferred(run_id, core, deferred_ids,""",
        new="""            if deferred_ids and False:
                try:
                    core = self._acquire_deferred(run_id, core, deferred_ids,""",
        tests=["tests/test_deferred_evidence_survives.py::"
               "test_the_worker_actually_passes_the_probe_to_acquisition"],
    ),
    dict(
        name="M19 deferred targets are dropped instead of returned",
        path="src/intent_engine/company_ingestion/service.py",
        old="""                deferred.extend(wave)
                continue""",
        new="""                continue""",
        tests=["tests/test_minimum_core_sufficiency.py::"
               "test_every_deferred_source_is_retrieved_or_recorded_as_failed"],
    ),
    dict(
        name="M20 a read recomposes with the deep pass on the request thread",
        path="src/intent_engine/webapp/app.py",
        old="""        fresh = self._compose(run_id, deep=False)""",
        new="""        fresh = self._compose(run_id)""",
        tests=["tests/test_deferred_evidence_survives.py::"
               "test_a_read_never_runs_the_deep_pass_on_the_request_thread"],
    ),
    dict(
        name="M21 a failed read-recompose replaces the published result",
        path="src/intent_engine/webapp/app.py",
        old="""        if (fresh["strategic_report"].get("result_state") == "FAILED"
                and (previous.get("strategic_report") or {}).get(
                    "result_state") not in (None, "FAILED")):""",
        new="""        if False:""",
        tests=["tests/test_deferred_evidence_survives.py::"
               "test_a_failed_read_recompose_keeps_the_published_result"],
    ),
    dict(
        name="M22 the deferred recompose may publish a report-less object",
        path="src/intent_engine/webapp/app.py",
        old="""        if not (widened or {}).get("strategic_report"):""",
        new="""        if False:""",
        tests=["tests/test_deferred_evidence_survives.py::"
               "test_a_recompose_that_produced_no_report_may_not_replace_the_core"],
    ),
    dict(
        name="M23 a read recomposes on every poll instead of caching",
        path="src/intent_engine/webapp/app.py",
        old="""        if not previous:
            # Nothing to protect: whatever compose produced IS the answer for
            # this run, and it is a dict, so it can be cached and not redone.
            return fresh""",
        new="""        if not previous:
            return previous""",
        tests=["tests/test_deferred_evidence_survives.py::"
               "test_a_read_caches_its_recompose_and_never_stores_none"],
    ),
    dict(
        name="M12 a fresh connection is retried like a stale one",
        path="src/intent_engine/company_ingestion/httppool.py",
        old="""                if reused and attempt == 0:""",
        new="""                if attempt == 0:""",
        tests=["tests/test_connection_reuse.py::"
               "test_a_failure_on_a_fresh_connection_is_not_dialled_twice"],
    ),
]


def run(tests, cwd) -> tuple:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", *tests],
        cwd=cwd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)[-2500:]


def main() -> int:
    held, broke = 0, []
    for mutation in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            tree = pathlib.Path(tmp) / "tree"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                ".git", ".venv", "__pycache__", "*.pyc", "reports", "data",
                "node_modules"))
            target = tree / mutation["path"]
            text = target.read_text()
            if mutation["old"] not in text:
                broke.append((mutation["name"], "MUTATION SITE NOT FOUND"))
                continue
            before_code, before_out = run(mutation["tests"], tree)
            if before_code != 0:
                broke.append((mutation["name"],
                              f"NOT GREEN BEFORE:\n{before_out}"))
                continue
            target.write_text(text.replace(mutation["old"],
                                           mutation["new"], 1))
            after_code, after_out = run(mutation["tests"], tree)
            # RESTORED IDENTICAL, checked rather than assumed.
            target.write_text(text)
            assert target.read_text() == text
            if after_code == 0:
                broke.append((mutation["name"],
                              f"NOT_CAUGHT — still green:\n{after_out}"))
                continue
            held += 1
            print(f"HELD   {mutation['name']}")
    for name, why in broke:
        print(f"FAILED {name}\n{why}\n")
    print(f"\n{held}/{len(MUTATIONS)} mutations held")
    return 0 if held == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

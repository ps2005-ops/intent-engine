#!/usr/bin/env python3
"""Break the system-of-record guards deliberately, one at a time.

Same hardened harness as the other proof scripts: the mutation must actually
change bytes, the named test must go RED rather than error, and the restore
must be byte-exact with a bumped mtime so CPython cannot serve stale bytecode.

Every mutation here re-creates the 2026-08-12 incident in a different way. The
incident was not a crash — it was a confident, wrong answer produced by
reading the wrong store — so each proof asks whether a specific wrong answer
is still reachable.

Run:  PYTHONPATH=src python3 scripts/v5_system_of_record_break_proofs.py
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "intent_engine"
DOCS = ROOT / "docs" / "execution"

SOR = "tests/test_market_system_of_record.py"
WD = "tests/test_market_learning_watchdog.py"
PROD = "tests/test_market_acquisition_counter_populations.py"
REP = "tests/test_market_learning_report.py"
MTX = "tests/test_market_matrix.py"
IND = "tests/test_market_evidence_independence.py"
FF = "tests/test_market_founder_freshness.py"

MUTATIONS = [
    ("the legacy prediction pipeline is declared CANONICAL",
     DOCS / "MARKET_INTELLIGENCE_SYSTEM_OF_RECORD.yaml",
     "  - id: daily_market_predictions\n    status: LEGACY",
     "  - id: daily_market_predictions\n    status: CANONICAL",
     f"{SOR}::test_a_legacy_pipeline_cannot_identify_itself_as_canonical"),

    ("an undeclared pipeline is assumed canonical instead of refused",
     SRC / "market/system_of_record.py",
     "    verdict = classify(pipeline_id)\n    if verdict != CANONICAL:",
     "    verdict = classify(pipeline_id)\n    if verdict == LEGACY:",
     f"{SOR}::test_an_undeclared_pipeline_is_refused_rather_than_"
     f"assumed_canonical"),

    ("the canonical learning ledger points at the legacy database",
     DOCS / "MARKET_INTELLIGENCE_SYSTEM_OF_RECORD.yaml",
     "    learning_ledger: reports/market/learning_ledger.jsonl",
     "    learning_ledger: data/prediction_ledger.db",
     f"{SOR}::test_the_canonical_ledger_is_not_the_legacy_database"),

    ("a legacy entrypoint stops printing its banner",
     SRC / "market/system_of_record.py",
     "    return None if is_canonical(pipeline_id) else LEGACY_BANNER",
     "    return None",
     f"{SOR}::test_every_legacy_pipeline_must_print_a_banner"),

    ("a missing channel is reported as a measured zero",
     SRC / "market/learning_status.py",
     '        return {"status": NO_PRODUCER, "all_time": 0, "in_window": 0,',
     '        return {"status": RAN_NO_CHANGE, "all_time": 0, "in_window": 0,',
     f"{SOR}::test_a_channel_with_no_rows_ever_reports_no_producer_not_zero"),

    ("undatable rows are reported as no-change",
     SRC / "market/learning_status.py",
     "    if present and not datable:",
     "    if False:",
     f"{SOR}::test_rows_that_cannot_be_dated_are_not_reported_as_no_change"),

    ("research outcomes are read from a field the producer never writes",
     SRC / "market/learning_status.py",
     '    all_outcomes = collections.Counter(\n'
     '        str(r.get("status") or "UNRECORDED")\n'
     '        for r in by_type.get("research_outcome", []))',
     '    all_outcomes = collections.Counter(\n'
     '        str(r.get("outcome") or "UNRECORDED")\n'
     '        for r in by_type.get("research_outcome", []))',
     f"{SOR}::test_research_outcomes_are_read_from_the_field_the_"
     f"producer_writes"),

    ("a zero denominator produces a share of 0.0 instead of UNMEASURABLE",
     SRC / "market/learning_status.py",
     '            "changing_share": (round(len(changed) / len(effects), 4)\n'
     '                               if effects else None),',
     '            "changing_share": (round(len(changed) / len(effects), 4)\n'
     '                               if effects else 0.0),',
     f"{SOR}::test_zero_effects_reports_unmeasurable_share_not_zero"),

    # --- founder freshness (§28) ------------------------------------------
    ("a stale export is reported CURRENT",
     SRC / "market/founder_freshness.py",
     "    if consumed_digest == export[\"semantic_digest\"]:",
     "    if True:",
     f"{FF}::test_a_changed_export_is_stale_until_consumed"),

    ("a received-but-unconsumed export counts as current",
     SRC / "market/founder_freshness.py",
     '        return {"state": NOT_CONSUMED,',
     '        return {"state": CURRENT_NO_NEW_REVISION_REQUIRED,',
     f"{FF}::test_an_export_nobody_consumed_is_not_consumed_not_current"),

    ("a revision with no digest is assumed to match",
     SRC / "market/founder_freshness.py",
     '        return {"state": STALE_MARKET_INTELLIGENCE,\n'
     '                "reason": ("the Founder revision records no semantic '
     'digest, "',
     '        return {"state": CURRENT_NO_NEW_REVISION_REQUIRED,\n'
     '                "reason": ("the Founder revision records no semantic '
     'digest, "',
     f"{FF}::test_a_revision_without_a_digest_cannot_be_proven_current"),

    ("the semantic digest includes the generation timestamp",
     SRC / "market/founder_freshness.py",
     '_NON_SEMANTIC = frozenset({"generated_at", "freshness", "as_of",',
     '_NON_SEMANTIC = frozenset({"freshness", "as_of",',
     f"{FF}::test_a_regenerated_identical_export_has_the_same_digest"),

    ("a missing export is treated as an export that was not needed",
     SRC / "market/founder_freshness.py",
     '        return {"state": EXPORT_NOT_CHECKED,',
     '        return {"state": EXPORT_NOT_NEEDED,',
     f"{FF}::test_a_company_with_no_export_is_unchecked_not_up_to_date"),

    ("an empty runtime reports a 0% current share instead of none",
     SRC / "market/founder_freshness.py",
     '        "current_share": (round(current / len(companies), 4)\n'
     '                          if companies else None),',
     '        "current_share": (round(current / len(companies), 4)\n'
     '                          if companies else 0.0),',
     f"{FF}::test_an_empty_runtime_reports_no_share_rather_than_zero"),

    # --- evidence independence (§36) --------------------------------------
    ("syndicated copies are counted as independent sources",
     SRC / "market/evidence_independence.py",
     "        elif claim and claim in claim_first:",
     "        elif False:",
     f"{IND}::test_ten_syndicated_copies_do_not_become_ten_confirmations"),

    ("a different URL is treated as a different origin",
     SRC / "market/evidence_independence.py",
     '        return ".".join(labels[-2:]) if len(labels) > 2 else ".".join(labels)',
     "        return str(row.get('source') or '')",
     # REPOINTED: the role-source test never runs the URL branch.
     f"{IND}::test_many_urls_on_one_host_are_one_origin"),

    ("UNKNOWN origin is promoted to independent",
     SRC / "market/evidence_independence.py",
     '            "counts_as_independent": state == INDEPENDENT,',
     '            "counts_as_independent": state != SAME_ORIGIN,',
     # REPOINTED after NOT_CAUGHT. An UNKNOWN row has no origin_id, so the
     # origin filter in assess() already excludes it — defence in depth.
     # A DERIVED row DOES have an origin, so it is where widening
     # `counts_as_independent` actually becomes visible.
     f"{IND}::test_a_syndicated_claim_is_derived_not_a_second_source"),

    ("company-authored material becomes an outside vantage point",
     SRC / "market/evidence_independence.py",
     "        outside = vantage >= OUTSIDE_VANTAGE_FLOOR and not _self_authored(row)",
     "        outside = True",
     f"{IND}::test_company_owned_material_is_never_an_outside_vantage_point"),

    ("a long-dated expectation makes every re-read look purposeful",
     SRC / "market/evidence_independence.py",
     "        if subject and days is not None and days <= MONITORING_HORIZON_DAYS:",
     "        if subject:",
     f"{IND}::test_no_testable_expectation_makes_the_value_unmeasurable"),

    # --- reporting and temporal observability -----------------------------
    ("a row dated after the period still enters the report",
     SRC / "market/learning_report.py",
     "        if stamp and start.isoformat() <= stamp <= end.isoformat():",
     "        if stamp:",
     f"{REP}::test_a_row_after_the_period_cannot_enter_the_report"),

    # The month branch specifically. `_bounds` returns the same expression
    # for week and month, so a bare replace(…, 1) mutated the WEEK branch and
    # the month test correctly kept passing — a mutation-targeting defect,
    # not a missing guard.
    ("an incomplete month is presented as a finished one",
     SRC / "market/learning_report.py",
     "    nxt = (start + datetime.timedelta(days=32)).replace(day=1)\n"
     "    end = nxt - datetime.timedelta(days=1)\n"
     "    return start, end, end > as_of",
     "    nxt = (start + datetime.timedelta(days=32)).replace(day=1)\n"
     "    end = nxt - datetime.timedelta(days=1)\n"
     "    return start, end, False",
     f"{REP}::test_an_incomplete_month_is_marked_partial"),

    ("an incomplete week is presented as a finished one",
     SRC / "market/learning_report.py",
     "        end = start + datetime.timedelta(days=6)\n"
     "        return start, end, end > as_of",
     "        end = start + datetime.timedelta(days=6)\n"
     "        return start, end, False",
     f"{REP}::test_an_incomplete_week_is_marked_partial"),

    ("duplicate effects on one evidence row count as several learnings",
     SRC / "market/learning_report.py",
     '        "evidence_that_changed_something": len(changing_ids),',
     '        "evidence_that_changed_something": len(changed),',
     f"{REP}::test_the_same_evidence_changing_twice_is_one_changed_row"),

    ("a re-observation is counted as new information",
     SRC / "market/learning_report.py",
     '        "new_information_share": _ratio(len(fresh), len(fresh) + len(seen)),',
     '        "new_information_share": _ratio(len(fresh), len(fresh)),',
     f"{REP}::test_a_re_observation_is_not_new_information"),

    ("the expectation temporal mapping is removed",
     SRC / "market/learning_status.py",
     '    "expectation": ("preregistered_at",),',
     '    "expectation": (),',
     f"{REP}::test_preregistered_and_never_reconciled_is_a_reconciliation_"
     f"bottleneck"),

    ("the matrix stops being able to count itself",
     ROOT / "scripts/market_matrix.py",
     '    return {"axes": len(axes),',
     '    return {"axes": len(axes) + 1,',
     f"{MTX}::test_capability_counts_equal_the_number_of_axes"),

    ("an honest maturity gate is counted as a blocker",
     ROOT / "scripts/market_matrix.py",
     '            if a["capability"] in ("PARTIAL", "NOT_BUILT", "UNMEASURED")]',
     '            if a["capability"] != "PASS"]',
     f"{MTX}::test_blocking_excludes_honest_maturity_gates"),

    # --- the always-on system (Batch A closure) ---------------------------
    ("the watchdog ignores a stale cycle",
     SRC / "market/learning_watchdog.py",
     "    if age is not None and age > STALE_CYCLE_HOURS:",
     "    if False:",
     f"{WD}::test_a_stale_cycle_is_critical"),

    ("the watchdog alerts during a healthy quiet week",
     SRC / "market/learning_watchdog.py",
     "    return {\"state\": NOTHING_NEW_IN_WORLD,",
     "    return {\"state\": SUBSYSTEM_NOT_RUNNING,",
     f"{WD}::test_no_new_evidence_after_a_normal_cycle_is_not_an_outage"),

    ("a success-only RL dataset stops being flagged",
     SRC / "market/learning_watchdog.py",
     '    if not active.get("zero_result_captured"):',
     "    if False:",
     f"{WD}::test_a_success_only_policy_dataset_is_flagged"),

    ("a scheduled legacy pipeline stops being critical",
     SRC / "market/learning_watchdog.py",
     '        if legacy.get("scheduled"):',
     "        if False:",
     f"{WD}::test_a_scheduled_legacy_pipeline_is_critical"),

    ("an absent ledger still yields downstream learning verdicts",
     SRC / "market/learning_watchdog.py",
     '        return _wrap(alerts, status, {"state": SUBSYSTEM_NOT_RUNNING,\n'
     '                                      "reason": "no canonical ledger"})',
     "        pass",
     f"{WD}::test_a_missing_ledger_is_critical_and_stops_downstream_verdicts"),

    ("legacy acquisition rows are treated as a computable yield",
     SRC / "market/learning_status.py",
     '        "safe_to_compute_yield": bool(repaired) and not inverted,',
     '        "safe_to_compute_yield": True,',
     f"{SOR}::test_legacy_rows_are_excluded_from_a_yield_rather_than_rewritten"),

    ("a post-repair inversion hides behind the legacy label",
     SRC / "market/learning_status.py",
     "    if inverted:\n        state = \"POPULATION_MISMATCH\"",
     "    if False:\n        state = \"POPULATION_MISMATCH\"",
     f"{SOR}::test_a_repaired_row_that_still_inverts_is_a_regression_not_legacy"),

    ("the acquisition producer counts subjects as document attempts again",
     SRC / "market/counterparty_sources.py",
     "            report.document_attempts += len(documents)",
     "            report.document_attempts += 1",
     # REPOINTED after NOT_CAUGHT. Every test pointed here wrote a ledger
     # row by hand, so `measure()` — the only place the two populations are
     # established — had no coverage. A contract fixture cannot catch a
     # producer that miscounts.
     f"{PROD}::test_one_subject_returning_three_documents_counts_one_subject"),

    ("a legacy pipeline is marked as scheduled alongside the canonical jobs",
     DOCS / "MARKET_INTELLIGENCE_SYSTEM_OF_RECORD.yaml",
     "    scheduled: false",
     "    scheduled: true",
     f"{SOR}::test_the_declared_scheduler_targets_the_canonical_entrypoint"),
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    future = time.time() + 1
    os.utime(path, (future, future))
    for cache in path.parent.glob("__pycache__/*.pyc"):
        cache.unlink(missing_ok=True)


def run_test(node: str) -> tuple:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-x", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"),
             "PYTHONDONTWRITEBYTECODE": "1"})
    out = proc.stdout + proc.stderr
    failed = " failed" in out or "FAILED" in out
    errored = " error" in out.lower() and not failed
    return failed, errored, out.strip().splitlines()[-1] if out else ""


def main() -> int:
    results = []
    for name, path, find, repl, node in MUTATIONS:
        original = path.read_text(encoding="utf-8")
        before = sha(path)
        if find not in original:
            results.append(("NO_OP_TARGET_MISSING", name, node,
                            "the mutation target was not found in the file"))
            continue
        write(path, original.replace(find, repl, 1))
        try:
            if sha(path) == before:
                results.append(("NO_OP_HASH_UNCHANGED", name, node,
                                "the file did not change"))
                continue
            failed, errored, tail = run_test(node)
            if failed:
                results.append(("CAUGHT", name, node, tail))
            elif errored:
                results.append(("ERRORED_NOT_FAILED", name, node, tail))
            else:
                results.append(("NOT_CAUGHT", name, node, tail))
        finally:
            write(path, original)
            assert sha(path) == before, f"restore was not exact for {path}"

    width = max(len(r[0]) for r in results)
    caught = sum(1 for r in results if r[0] == "CAUGHT")
    print(f"\n{'=' * 78}\nSYSTEM-OF-RECORD BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

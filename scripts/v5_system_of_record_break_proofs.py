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

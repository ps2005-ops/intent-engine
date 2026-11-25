#!/usr/bin/env python3
"""Break the Pre-100 Batch-3 wiring deliberately, one mutation at a time.

Same hardened harness as the V5 batches: byte-changing mutation, decisive RED
for the stated reason, exact restore verified by hash, and "no tests ran" is
never read as CAUGHT.

WHAT THESE DEFEND
------------------
Two blocks the executive product could not show, and one silent zero found
while wiring them. The most dangerous mutation here is the last: it does not
remove intelligence, it makes a wiring failure look like a finding of nothing,
which is the shape this whole programme keeps catching.

Run:  PYTHONPATH=src python3 scripts/v5_pre100_break_proofs.py
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "intent_engine" / "market"
T = "tests/test_snapshot_carries_hidden_state_and_expectations.py"

MUTATIONS = [
    ("hidden states stop reaching the snapshot",
     SRC / "demo_snapshot_export.py",
     '        "hidden_state_refs": _block(hidden_states, "leading_state",\n'
     '                                    "hidden_state_id", "id"),',
     '        "hidden_state_refs": _block(None),',
     f"{T}::test_hidden_states_reach_the_snapshot_named_by_their_posture"),

    ("a block nobody ran is published as ran-and-found-nothing",
     SRC / "demo_snapshot_export.py",
     '    if rows is None:\n'
     '        return {"state": REF_UNAVAILABLE, "ids": [], "count": 0,',
     '    if False:\n'
     '        return {"state": REF_UNAVAILABLE, "ids": [], "count": 0,',
     f"{T}::test_hidden_states_not_passed_still_read_as_did_not_run"),

    # THE SILENT ZERO. Rows present, none nameable, reported as count 0 with
    # no note -- identical on the wire to "we looked and found nothing".
    ("unnameable rows are reported as zero findings again",
     SRC / "demo_snapshot_export.py",
     "    if rows and not ids:",
     "    if False:",
     f"{T}::"
     "test_rows_that_cannot_be_named_are_not_reported_as_zero_findings"),

    # The guard must not fire on real zeros either, or every empty block
    # starts claiming a wiring defect.
    ("the wiring-defect guard swallows genuine empties",
     SRC / "demo_snapshot_export.py",
     "    if rows and not ids:",
     "    if not ids:",
     f"{T}::test_a_genuine_empty_stays_a_genuine_empty"),

    ("expectations stop being filtered to their own subject",
     SRC / "strategic_publish.py",
     "        if str(subject or \"\") == str(subject_id):\n"
     "            out.append(e)",
     "        out.append(e)",
     f"{T}::test_expectations_are_filtered_to_their_own_subject"),

    # THE SEV-2 TRUTH DEFECT: a refusal republished as an absence.
    ("a causal refusal is published as did-not-run again",
     SRC / "demo_snapshot_export.py",
     '        "causal_result_refs": _causal_block(causal_results),',
     '        "causal_result_refs": _block(None),',
     f"{T}::test_a_refusal_is_published_as_the_router_having_run"),

    ("the causal block hides which states it found",
     SRC / "demo_snapshot_export.py",
     "    block[\"states\"] = states",
     "    block[\"states\"] = {}",
     f"{T}::test_mixed_states_are_all_reported_not_just_the_good_ones"),

    ("causal resolutions leak across companies",
     SRC / "strategic_publish.py",
     "        if str(company or \"\") == str(subject_id):\n"
     "            out.append(r)",
     "        out.append(r)",
     f"{T}::test_causal_resolutions_are_filtered_to_their_own_company"),
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
    ran_nothing = "no tests ran" in out
    errored = (" error" in out.lower() or ran_nothing) and not failed
    return failed, errored, out.strip().splitlines()[-1] if out else ""


def main() -> int:
    results = []
    for name, path, find, repl, node in MUTATIONS:
        original = path.read_text(encoding="utf-8")
        before = sha(path)
        if find not in original:
            results.append(("NO_OP_TARGET_MISSING", name, node,
                            "the mutation target was not found"))
            continue
        write(path, original.replace(find, repl, 1))
        try:
            if sha(path) == before:
                results.append(("NO_OP_HASH_UNCHANGED", name, node, ""))
                continue
            failed, errored, tail = run_test(node)
            results.append((("CAUGHT" if failed else
                             "ERRORED_NOT_FAILED" if errored else
                             "NOT_CAUGHT"), name, node, tail))
        finally:
            write(path, original)
            assert sha(path) == before, f"restore was not exact for {path}"

    width = max(len(r[0]) for r in results)
    caught = sum(1 for r in results if r[0] == "CAUGHT")
    print(f"\n{'=' * 78}\nV5 PRE-100 BATCH-3 BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

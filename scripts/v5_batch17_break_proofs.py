#!/usr/bin/env python3
"""Break the Batch-17 guards deliberately, one at a time.

Same hardened harness as Batches 12-16: byte-changing mutation, decisive RED
for the stated reason, exact restore verified by hash.

WHAT THESE DEFEND
------------------
Batch 17 could not run the paid wave, and found instead that the sentence the
gate had been printing for two batches -- "restore credit and these six become
evaluable" -- was FALSE for one of them. The six backend criteria were a
static tuple of titles, emitted as BLOCKED_EXTERNAL without anything being
checked, so a criterion with no producer at all was indistinguishable from one
merely waiting on money. That is criterion 10's history repeating in the exact
place the gate was written to prevent it.

Both mutations below restore a shipped defect:

  * the backend criteria stop being checked, so a missing producer reads as an
    external block and routes an ENGINEERING defect to the billing page;
  * the runtime root is created when missing, so a second iteration silently
    meets an empty store, reports FIRST_OBSERVATION for every company again,
    and a rerun that proved nothing looks exactly like one that passed.

Run:  PYTHONPATH=src python3 scripts/v5_batch17_break_proofs.py
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

GATE_TESTS = "tests/test_wave30_gate.py"
WAVE_TESTS = "tests/test_breaker_wave_measurements.py"

MUTATIONS = [
    # THE SHIPPED DEFECT: a backend criterion asserted blocked, never checked.
    ("a criterion with no producer is reported as externally blocked",
     ROOT / "scripts/v5_wave30_gate.py",
     "        if present:",
     "        if True:",
     f"{GATE_TESTS}::"
     "test_a_backend_criterion_with_no_producer_fails_and_never_blocks"),

    # The other direction: a probe that cannot run is not evidence that money
    # is the blocker. Swallowing the error turns a broken check into a block.
    ("a producer probe that raises is treated as a block",
     ROOT / "scripts/v5_wave30_gate.py",
     "            present, producer_name = False, f\"{producer_name} ({exc})\"",
     "            present, producer_name = True, f\"{producer_name} ({exc})\"",
     f"{GATE_TESTS}::"
     "test_a_producer_probe_that_raises_fails_rather_than_blocking"),

    # THE SHIPPED DEFECT: every run rooted at a fresh mkdtemp, so the second
    # iteration met its own priors as absent, for ever.
    ("a missing runtime root is created instead of refused",
     ROOT / "scripts/v5_breaker_wave.py",
     "    if not root.is_dir():\n"
     "        raise NotADirectoryError(",
     "    if not root.is_dir():\n"
     "        root.mkdir(parents=True, exist_ok=True)\n"
     "    if False:\n"
     "        raise NotADirectoryError(",
     f"{WAVE_TESTS}::test_a_missing_root_is_refused_rather_than_created"),

    # A reused root that silently reports no carried stores would make a
    # second iteration indistinguishable from a first one.
    ("a reused root reports no carried company stores",
     ROOT / "scripts/v5_breaker_wave.py",
     "    return root, sorted(p.name for p in root.iterdir() if p.is_dir())",
     "    return root, []",
     f"{WAVE_TESTS}::"
     "test_a_reused_root_carries_the_previous_passes_company_stores"),

    # The gate must keep naming a producer per criterion; a bare title cannot
    # be adjudicated, which is precisely how the old tuple hid the defect.
    ("the backend criteria lose their producer probes",
     ROOT / "scripts/v5_wave30_gate.py",
     "     _script(\"v5_learning_funnel.py\"), \"scripts/v5_learning_funnel.py\"),",
     "     None, \"scripts/v5_learning_funnel.py\"),",
     f"{GATE_TESTS}::test_every_backend_criterion_names_a_producer"),
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    # A same-length mutation restored in place can leave CPython running the
    # mutated bytecode; bump mtime and drop the caches.
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
    # "no tests ran" must never read as CAUGHT: a proof that executed nothing
    # is reporting on a test it never ran.
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
                            "the mutation target was not found in the file"))
            continue
        write(path, original.replace(find, repl, 1))
        after = sha(path)
        try:
            if after == before:
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
    print(f"\n{'=' * 78}\nV5 BATCH-17 BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

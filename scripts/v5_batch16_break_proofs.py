#!/usr/bin/env python3
"""Break the Batch-16 guards deliberately, one at a time.

Same hardened harness as Batches 12-15. Two of these matter more than usual:

  * the trading-wall mutation restores the code that ACTUALLY SHIPPED and
    refused every text naming Alphabet Inc.;
  * the gate mutations attack the GATE ITSELF. The gate is now the thing that
    decides whether Wave 30 opens, so a gate that counts an unevaluated
    criterion as met is the most expensive defect available — it would open a
    wave on the strength of checks nobody ran.

Run:  PYTHONPATH=src python3 scripts/v5_batch16_break_proofs.py
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

WALL = "tests/test_trading_wall_word_boundaries.py"
GATE = "tests/test_wave30_gate.py"

MUTATIONS = [
    # THE SHIPPED DEFECT: raw substring matching refuses "Alphabet Inc."
    ("the trading wall matches raw substrings again (dossier)",
     SRC / "demo_dossier/contracts.py",
     "        found = _BANNED_PATTERN.search(node)\n"
     "        if found:",
     "        found = next((b for b in _BANNED_SUBSTRINGS\n"
     "                      if b in node.lower()), None)\n"
     "        if found:",
     f"{WALL}::test_ordinary_text_containing_a_banned_substring_is_allowed"
     f"[Alphabet Inc. reported revenue growth-demo_dossier]"),

    ("the trading wall matches raw substrings again (strategic)",
     SRC / "external_intel/strategic_contract.py",
     "        found = _BANNED_PATTERN.search(node)\n"
     "        if found:",
     "        found = next((b for b in _BANNED_SUBSTRINGS\n"
     "                      if b in node.lower()), None)\n"
     "        if found:",
     f"{WALL}::test_ordinary_text_containing_a_banned_substring_is_allowed"
     f"[Alphabet Inc. reported revenue growth-strategic_contract]"),

    # THE WALL MUST NOT BE RELAXED IN THE OTHER DIRECTION EITHER.
    # The node id is spelled out rather than f-string-escaped: an earlier
    # version wrote `3%%` into the id, pytest matched nothing, and the harness
    # read "no tests ran" as NOT_CAUGHT — a proof reporting on a test it never
    # executed.
    ("the boundary is widened so trading alpha stops matching",
     SRC / "demo_dossier/contracts.py",
     "    r\"(?<![0-9a-z])(?:%s)(?![0-9a-z])\"",
     "    r\"(?<![0-9a-z ])(?:%s)(?![0-9a-z ])\"",
     WALL + "::test_trading_language_is_still_refused"),

    # THE GATE ITSELF: an unevaluated criterion counted as met.
    # REPOINTED at the extracted `adjudicate`. The tests previously
    # reimplemented the rule, so mutating the gate could not fail them.
    ("the gate counts BLOCKED_EXTERNAL as a pass",
     ROOT / "scripts/v5_wave30_gate.py",
     "    if any(r[\"verdict\"] == BLOCKED for r in results):\n"
     "        return BLOCKED",
     "    if False:\n"
     "        return BLOCKED",
     f"{GATE}::test_a_blocked_criterion_never_opens_the_wave"),

    # THE GATE ITSELF: a failing criterion hidden.
    ("the gate opens the wave with a failing criterion",
     ROOT / "scripts/v5_wave30_gate.py",
     "    if any(r[\"verdict\"] == FAIL for r in results):\n"
     "        return FAIL",
     "    if False:\n"
     "        return FAIL",
     f"{GATE}::test_a_failing_criterion_closes_the_wave"),
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
    print(f"\n{'=' * 78}\nV5 BATCH-16 BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

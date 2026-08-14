#!/usr/bin/env python3
"""Break the Batch-4 evidence-ownership repair deliberately.

Same hardened harness contract as the earlier batches: a byte-changing
mutation, a decisive RED for the stated reason, and an exact hash-verified
restore. "No tests ran" is never read as CAUGHT.

WHAT THESE DEFEND
------------------
One SEV1 found live: all 26 published snapshots carried the same 474 evidence
count and the same first 64 ids, because the shared market ledger was passed
through unfiltered. Johnson & Johnson's dossier cited Cloudflare's sources.

The dangerous mutations here are the last two. They do not remove evidence --
they make a wiring failure look like a finding of nothing, which is the shape
this programme keeps catching.

Run:  PYTHONPATH=src python3 scripts/v5_pre100_batch4_break_proofs.py
"""
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "intent_engine" / "market"
T = "tests/test_the_market_publishes_a_demo_snapshot.py"

MUTATIONS = [
    # The SEV1 itself: stop filtering, publish the shared ledger again.
    ("the shared ledger is published as every company's evidence",
     SRC / "demo_snapshot_export.py",
     '        "evidence_reference_ids": _evidence_block(evidence_rows, _cited),',
     '        "evidence_reference_ids": _block(evidence_rows, "evidence_id",'
     ' "id"),',
     f"{T}::test_two_companies_sharing_one_ledger_do_not_share_evidence"),

    # Only beliefs are collected -- a hidden state's or expectation's evidence
    # silently stops being this company's evidence.
    ("evidence is collected from beliefs only",
     SRC / "demo_snapshot_export.py",
     "    for _group in (beliefs, hidden_states, theses, thesis_revisions,",
     "    for _group in (beliefs,) if True else (thesis_revisions,",
     f"{T}::test_evidence_is_collected_from_every_block_not_only_beliefs"),

    # A citation the ledger cannot resolve is reported as a plain zero --
    # indistinguishable from "this company cites no evidence".
    ("unresolvable citations are reported as zero findings",
     SRC / "demo_snapshot_export.py",
     '    if not matched:\n'
     '        return {"state": REF_AVAILABLE, "ids": [], "count": 0,\n'
     '                "note": (f"{len(cited)} evidence id(s) are cited by this "',
     '    if False:\n'
     '        return {"state": REF_AVAILABLE, "ids": [], "count": 0,\n'
     '                "note": (f"{len(cited)} evidence id(s) are cited by this "',
     f"{T}::test_citing_ids_the_ledger_cannot_resolve_is_named_a_wiring_defect"),

    # An absent ledger becomes a measured zero: "we looked and this company
    # has no evidence" when in fact nothing was supplied to look at.
    ("an absent ledger is published as a measured zero",
     SRC / "demo_snapshot_export.py",
     '    if rows is None:\n'
     '        return {"state": REF_UNAVAILABLE, "ids": [], "count": 0,\n'
     '                "note": "this subsystem did not run for this snapshot"}',
     '    if rows is None:\n'
     '        return {"state": REF_AVAILABLE, "ids": [], "count": 0,\n'
     '                "note": "this subsystem did not run for this snapshot"}',
     f"{T}::test_an_absent_ledger_is_not_a_zero"),

    # The negative control: dropping evidence that was genuinely dropped must
    # still be reported, or a partial join looks complete.
    ("dropped citations are not reported",
     SRC / "demo_snapshot_export.py",
     "    unresolved = len(cited) - len(matched)",
     "    unresolved = 0",
     f"{T}::test_partially_resolvable_citations_report_what_was_dropped"),
]

PY = sys.executable


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, text):
    p.write_text(text, encoding="utf-8")
    # A same-length restore leaves CPython running the mutated bytecode.
    import os
    os.utime(p, (time.time() + 1, time.time() + 1))
    for cache in ROOT.rglob("__pycache__"):
        for f in cache.glob("demo_snapshot_export*.pyc"):
            f.unlink(missing_ok=True)


def run_test(node):
    r = subprocess.run([PY, "-m", "pytest", node, "-q", "--no-header", "-x"],
                       cwd=ROOT, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src",
                            "HOME": str(pathlib.Path.home())})
    out = (r.stdout or "") + (r.stderr or "")
    failed = " failed" in out or "FAILED" in out
    errored = " error" in out.lower() and not failed
    ran = "passed" in out or failed or errored
    return failed, (errored or not ran), out.strip().splitlines()[-1:]


def main():
    results = []
    for name, path, find, repl, node in MUTATIONS:
        original = path.read_text(encoding="utf-8")
        before = sha(path)
        # Condition 2: the test must be GREEN before the mutation.
        pre_failed, pre_bad, pre_tail = run_test(node)
        if pre_failed or pre_bad:
            results.append(("INVALID_NOT_GREEN_FIRST", name, node, pre_tail))
            continue
        if find not in original:
            results.append(("NO_OP_TARGET_MISSING", name, node,
                            ["the mutation target was not found"]))
            continue
        write(path, original.replace(find, repl, 1))
        try:
            if sha(path) == before:
                results.append(("NO_OP_HASH_UNCHANGED", name, node, []))
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
    print(f"\n{'=' * 78}\nV5 PRE-100 BATCH-4 BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

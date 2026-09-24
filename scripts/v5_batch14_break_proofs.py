#!/usr/bin/env python3
"""Break the Batch-14 guards deliberately, one at a time.

Same hardened harness as the Batch-12 and Batch-13 proof files: the mutation
must change the file, the named test must go RED rather than error, and the
restore must be byte-exact with a bumped mtime.

Two of these mutations restore the EXACT code that shipped at 46027cc, which
is the strongest form this proof takes — the defect is not hypothetical, it is
what was running.

Run:  PYTHONPATH=src python3 scripts/v5_batch14_break_proofs.py
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

CRITIC = "tests/test_critic_reads_origin_independence.py"
FUNNEL = "tests/test_learning_funnel.py"

MUTATIONS = [
    # 1. THE SHIPPED DEFECT, restored: the critic keeps its own wider copy of
    #    "independent" and counts the company's own investor material as an
    #    outside vantage point.
    ("the critic keeps a private, wider definition of independent",
     SRC / "strategic_intelligence/analyst/critic.py",
     "from intent_engine.company_ingestion.records import (  # noqa: E402\n"
     "    INDEPENDENT_CLASSES as _INDEPENDENT_CLASSES,\n"
     ")",
     '_INDEPENDENT_CLASSES = frozenset(\n'
     '    {"independent_reporting", "customer_voice", "competitor",\n'
     '     "investor_material"})',
     f"{CRITIC}::test_investor_material_is_not_an_outside_vantage_point"),

    # 2. THE SHIPPED DEFECT, restored: independence decided from per-document
    #    CLASSES, which cannot see syndication.
    ("the confidence gate counts source classes instead of origins",
     SRC / "strategic_intelligence/analyst/critic.py",
     "        independent_origins = {\n"
     "            _origin_family(getattr(o, \"origin\", \"\") or \"\")\n"
     "            for o in cited\n"
     "            if getattr(o, \"source_class\", \"\") in "
     "_INDEPENDENT_CLASSES}\n"
     "        independent_origins.discard(\"\")",
     "        independent_origins = {\n"
     "            getattr(o, \"source_class\", \"\")\n"
     "            for o in cited\n"
     "            if getattr(o, \"source_class\", \"\") in "
     "_INDEPENDENT_CLASSES}\n"
     "        independent_origins.discard(\"\")",
     # REPOINTED after NOT_CAUGHT, and the investigation is the finding.
     # The syndication test is defended twice — origins are counted AND two
     # are required — so class-counting still flags nine copies of one class
     # and the mutation is invisible there. Two independent CLASSES on ONE
     # origin is where the axes separate.
     f"{CRITIC}::test_two_independent_classes_on_one_origin_are_one_vantage_"
     f"point"),

    # 3. the gate stops distinguishing one outside account from two
    ("one independent origin is treated as corroboration",
     SRC / "strategic_intelligence/analyst/critic.py",
     "        if conf == \"high\" and \\\n"
     "                len(independent_origins) < "
     "_MIN_INDEPENDENT_FOR_CORROBORATION:",
     "        if conf == \"high\" and not independent_origins:",
     f"{CRITIC}::test_nine_syndicated_copies_are_one_vantage_point"),

    # 4. an observation with no recorded origin supplies independence
    ("unknown origin counts as an independent origin",
     SRC / "strategic_intelligence/analyst/critic.py",
     "        independent_origins.discard(\"\")",
     "        pass",
     f"{CRITIC}::test_an_observation_with_no_origin_cannot_supply_"
     f"independence"),

    # 5. the funnel collapses "nothing produces this" into "blocked upstream".
    #    REPLACED after NOT_CAUGHT: the first version added a key the module
    #    never reads, so it changed the file and not the behaviour — a no-op
    #    dressed as a mutation, which is exactly what the hash check cannot
    #    catch on its own. This one rewrites the cause the stage reports.
    ("a stage with no producer is reported as externally blocked",
     ROOT / "scripts/v5_learning_funnel.py",
     '        {"stage": "BELIEF_ELIGIBLE", "n": 0, "population": '
     'EVIDENCE_ROWS,\n'
     '         "cause": (BLOCKED_EXTERNAL\n'
     '                   if attribution == "BLOCKED_EXTERNAL_CREDITS"\n'
     '                   else NO_PRODUCER)},',
     '        {"stage": "BELIEF_ELIGIBLE", "n": 0, "population": '
     'EVIDENCE_ROWS,\n'
     '         "cause": BLOCKED_EXTERNAL},',
     f"{FUNNEL}::test_a_stage_with_no_producer_is_not_reported_as_blocked"),

    # 6. the funnel reports the LAST empty stage instead of the FIRST loss
    ("the funnel reports a later stage than the first starved one",
     ROOT / "scripts/v5_learning_funnel.py",
     "        if survived < MATERIAL_SURVIVAL:\n"
     "            return {\"transition\": f\"{prior['stage']} → "
     "{current['stage']}\",",
     "        if False:\n"
     "            return {\"transition\": f\"{prior['stage']} → "
     "{current['stage']}\",",
     f"{FUNNEL}::test_the_first_starved_transition_is_the_earliest_one"),
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
    print(f"\n{'=' * 78}\nV5 BATCH-14 BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

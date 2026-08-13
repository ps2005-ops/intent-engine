#!/usr/bin/env python3
"""Break the Batch-15 learning producer deliberately, one at a time.

Same hardened harness as Batches 12-14: the mutation must change the file, the
named test must go RED rather than error, and the restore must be byte-exact
with a bumped mtime.

Two of these restore code that ACTUALLY SHIPPED and one restores a defect this
batch introduced and caught in its own live proof — the twelve-effects-per-
cycle inflation. A mutation that reproduces a real mistake is worth more than
one that reproduces an imaginable mistake.

Run:  PYTHONPATH=src python3 scripts/v5_batch15_break_proofs.py
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

PROD = "tests/test_effect_producer.py"

MUTATIONS = [
    # A. identity keyed on the wall clock — every rerun duplicates
    ("effect identity includes the wall clock",
     SRC / "company_ingestion/learning_attribution.py",
     "        raw = \"|\".join((self.evidence_id, self.target_type, "
     "self.target_id,\n"
     "                        self.effect_type, self.before_state, "
     "self.after_state,\n"
     "                        self.created_at[:10]))",
     "        raw = \"|\".join((self.evidence_id, self.target_type, "
     "self.target_id,\n"
     "                        self.effect_type, self.before_state, "
     "self.after_state,\n"
     "                        self.created_at))",
     f"{PROD}::test_effect_identity_does_not_include_the_time_of_day"),

    # B. a first observation counted as a change
    ("first observation is treated as a changing effect",
     SRC / "company_ingestion/learning_attribution.py",
     "NON_CHANGING = frozenset({NO_CHANGE, FIRST_OBSERVATION, UNMEASURABLE, "
     "REFUSED})",
     "NON_CHANGING = frozenset({NO_CHANGE, UNMEASURABLE, REFUSED})",
     f"{PROD}::test_case_a_first_observation_is_a_baseline_not_an_improvement"),

    # C. THE SHIPPED DEFECT: two renderings of one claim grade REVERSED
    ("normalisation leaves punctuation, so a full stop reverses a claim",
     SRC / "external_intel/decision_impact.py",
     "    return \" \".join(str(text or \"\").lower().split()).strip(\n"
     "        \" \\t\\n\\r.,;:!?\\\"'()[]{}\")",
     "    return \" \".join(str(text or \"\").lower().split())",
     f"{PROD}::test_case_d_wording_only_change_produces_no_changing_effect"),

    # D. evidence-window comparability dropped
    ("an incomparable evidence window is scored instead of refused",
     SRC / "external_intel/effect_producer.py",
     "    if comparability == di.UNKNOWN_WINDOW:",
     "    if False:",
     f"{PROD}::test_case_f_an_incomparable_window_is_refused_not_scored"),

    # E. another company's prior grades this company
    ("another company's prior is accepted as this company's before",
     SRC / "external_intel/effect_producer.py",
     "    if prior_company_id and prior_company_id != company_id:",
     "    if False:",
     f"{PROD}::test_case_h_another_companys_prior_is_never_this_companys_"
     f"before"),

    # G. company self-report counted as independent (Batch-14 repair intact)
    ("the critic's independent-class set is widened again",
     SRC / "strategic_intelligence/analyst/critic.py",
     "from intent_engine.company_ingestion.records import (  # noqa: E402\n"
     "    INDEPENDENT_CLASSES as _INDEPENDENT_CLASSES,\n"
     ")",
     '_INDEPENDENT_CLASSES = frozenset(\n'
     '    {"independent_reporting", "customer_voice", "competitor",\n'
     '     "investor_material"})',
     "tests/test_critic_reads_origin_independence.py::"
     "test_investor_material_is_not_an_outside_vantage_point"),

    # H/I. the ledger stops de-duplicating, or stops reading from disk
    ("the ledger appends the same effect twice",
     SRC / "external_intel/effect_producer.py",
     "    known = {row.get(\"effect_id\") for row in load_effects(root, "
     "path=path)}",
     "    known = set()",
     f"{PROD}::test_the_same_semantic_comparison_appends_once"),

    # J. an unprovenanced change earns learning
    ("a change with no evidence behind it is credited as learning",
     SRC / "external_intel/effect_producer.py",
     "    if impact is not None and getattr(impact, \"materiality\", \"\") != "
     "\\\n"
     "            di.FIRST_OBSERVATION and not list(evidence_ids):",
     "    if False:",
     f"{PROD}::test_case_g_a_change_with_no_provenance_earns_no_learning"),

    # K. a re-read that could not test anything earns a confirmation
    ("a non-testable re-read is recorded as a confirmation",
     SRC / "external_intel/effect_producer.py",
     "        if effect_type == NO_CHANGE and not testable:",
     "        if False:",
     f"{PROD}::test_case_b2_a_reread_that_could_not_test_earns_no_"
     f"confirmation"),

    # L/M. UNMEASURABLE and REFUSED collapsed into NO_CHANGE
    ("UNMEASURABLE is collapsed into NO_CHANGE",
     SRC / "external_intel/effect_producer.py",
     "            effect_type = UNMEASURABLE\n"
     "            before = after = \"\"",
     "            effect_type = NO_CHANGE\n"
     "            before = after = \"\"",
     f"{PROD}::test_case_b2_a_reread_that_could_not_test_earns_no_"
     f"confirmation"),

    # THE INFLATION THIS BATCH CAUGHT IN ITS OWN LIVE PROOF: an effect for
    # every impact type, including the eleven that have never had content.
    ("an untouched decision component earns a confirmation",
     SRC / "external_intel/effect_producer.py",
     "        if not before and not after:\n"
     "            continue",
     "        if False:\n"
     "            continue",
     f"{PROD}::test_an_untested_component_produces_no_effect"),
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
    print(f"\n{'=' * 78}\nV5 BATCH-15 BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

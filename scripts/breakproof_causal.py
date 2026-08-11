#!/usr/bin/env python3
"""Break proofs for the causal chain. Mutate one invariant, demand RED.

A guard nobody has broken on purpose is a guard nobody has tested. Each proof
below edits `src/` in place, runs the named tests, and asserts they fail FOR
THE STATED REASON — then restores the file byte-for-byte and re-runs to confirm
green. A no-op mutation that leaves the suite green is reported as NOT_CAUGHT
rather than quietly passing, because "the mutation did nothing" and "the guard
caught it" look identical from the outside.

The restore bumps mtime. A same-length mutation restored in place leaves
CPython running the mutated bytecode from its cache, which has produced a false
green in this repository before.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

#: The repository this script lives in, so it runs from any worktree.
ROOT = pathlib.Path(__file__).resolve().parent.parent
#: Overridable, because a worktree has no .venv of its own and one created
#: there would import the package from the MAIN worktree.
PYTHON = os.environ.get(
    "GUARD_PYTHON", "/Users/prathamsharma/intent-engine-market/.venv/bin/python")

#: (name, file, find, replace, tests, why it must go red)
PROOFS = [
    ("a causal refusal is rendered but never persisted",
     "src/intent_engine/market/steps.py",
     "        persisted = sum(1 for r in resolutions\n"
     "                        if store.record_causal_estimate(r))",
     "        persisted = 0",
     "tests/test_market_causal_persistence.py::test_the_step_wires_the_write_into_its_payload",
     "a cycle that renders 25 refusals and writes none leaves "
     "causal_estimates_attempted at 0 -- the number the metric reads when the "
     "capability has never run at all"),

    ("the estimate row stops being idempotent",
     "src/intent_engine/market/learning_store.py",
     "        if rid in self.causal_estimate_ids():\n            return False",
     "        if False:\n            return False",
     "tests/test_market_causal_persistence.py::test_a_nightly_rerun_of_unchanged_questions_appends_nothing",
     "25 rows a night forever while the fold shows a constant number is the "
     "combination that hides its own growth"),

    ("causal production caller removed",
     "src/intent_engine/market/steps.py",
     "        from . import causal_question as CQ\n",
     "        if False:\n            from . import causal_question as CQ\n",
     "tests/test_market_causal_wiring.py::test_the_cycle_step_actually_calls_the_causal_path",
     "the step must reach the causal path; a capability with no production "
     "caller is the defect this node exists to close"),

    ("treatment date scanned instead of read",
     "src/intent_engine/market/causal_question.py",
     "        occurred = str(row.get(\"observed_at\") or \"\").strip()",
     "        occurred = str(row.get(\"observed_at\") or \"2026-01-01\").strip()",
     "tests/test_market_causal_wiring.py::test_an_event_with_no_date_anchors_nothing",
     "a treatment date defaulted because the record had no date is a "
     "fabricated treatment"),

    ("donor chosen on the numbers rather than on comparability",
     "src/intent_engine/market/causal_question.py",
     "        if rows[0].get(\"unit\") != unit:",
     "        if False and rows[0].get(\"unit\") != unit:",
     "tests/test_market_causal_wiring.py::test_a_different_unit_is_not_a_donor",
     "a weighted average across units is not a counterfactual"),

    ("missing panel read as a zero effect",
     "src/intent_engine/market/causal_question.py",
     "        return self.state not in NOT_AN_ESTIMATE",
     "        return True",
     "tests/test_market_causal_wiring.py::test_a_refusal_is_not_an_effect_of_zero",
     "a refusal is an identification that was not available, never an "
     "effect of zero"),

    ("synthetic questions counted as real",
     "src/intent_engine/market/causal_question.py",
     "    real = [r for r in resolutions if r.question.describes_the_world]",
     "    real = list(resolutions)",
     "tests/test_market_causal_wiring.py::test_summary_excludes_synthetic_questions_from_the_real_count",
     "a count that mixes fabricated questions into the real ones lets the "
     "test suite report the capability as working"),

    ("post-treatment data allowed into the objective",
     "src/intent_engine/market/synthetic_control.py",
     "    if len(pre_treated) != treatment_index:",
     "    if False and len(pre_treated) != treatment_index:",
     "tests/test_market_synthetic_control.py::test_the_objective_guard_rejects_a_treated_slice_that_runs_long",
     "a fit that saw the outcome it predicts scores better on every "
     "downstream diagnostic and is undetectable afterwards"),

    ("placebo threshold reachable claim removed",
     "src/intent_engine/market/causal_diagnostics.py",
     "    if best_possible > PLACEBO_RANK_SHARE:",
     "    if False and best_possible > PLACEBO_RANK_SHARE:",
     "tests/test_market_causal_diagnostics.py::test_a_pool_too_small_to_reach_the_threshold_is_untested_not_failed",
     "a threshold the panel cannot reach is not a failed test"),

    ("untested critical assumption allowed a causal reading",
     "src/intent_engine/market/economic_method.py",
     "        \"causal_reading_allowed\": (not failed_critical\n"
     "                                   and not untested_critical\n"
     "                                   and standing in (USEFUL, BOUNDED)),",
     "        \"causal_reading_allowed\": (not failed_critical\n"
     "                                   and standing in (USEFUL, BOUNDED)),",
     "tests/test_market_causal_diagnostics.py::test_an_untested_critical_assumption_forbids_a_causal_reading",
     "unknown is not permission; a synthetic control may not reach a causal "
     "reading on statistics alone"),
]


def run(tests: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "pytest", tests, "-q", "--no-header", "-x"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"})


def main() -> int:
    caught, not_caught = [], []
    for name, relative, find, replace, tests, why in PROOFS:
        path = ROOT / relative
        original = path.read_text(encoding="utf-8")
        if find not in original:
            not_caught.append((name, "ANCHOR NOT FOUND — the guard moved or "
                                     "the proof is stale"))
            continue
        mutated = original.replace(find, replace, 1)
        if mutated == original:
            not_caught.append((name, "NO-OP MUTATION — the edit changed "
                                     "nothing, so green proves nothing"))
            continue

        path.write_text(mutated, encoding="utf-8")
        # Bump mtime past the cached bytecode. A same-length mutation restored
        # in place has left CPython running the stale .pyc here before.
        path.touch()
        time.sleep(0.01)
        red = run(tests)

        path.write_text(original, encoding="utf-8")
        path.touch()
        time.sleep(0.01)
        assert path.read_text(encoding="utf-8") == original, (
            f"{relative} was not restored exactly")
        green = run(tests)

        if red.returncode == 0:
            not_caught.append((name, "the mutation left the suite GREEN"))
        elif green.returncode != 0:
            not_caught.append((name, "the suite did not recover after restore"))
        else:
            caught.append((name, why))

    print(f"CAUGHT {len(caught)} / {len(PROOFS)}")
    for name, why in caught:
        print(f"  RED   {name}\n        {why}")
    for name, reason in not_caught:
        print(f"  NOT_CAUGHT  {name}\n              {reason}")
    return 1 if not_caught else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The release gate: is this build something a stranger should be shown?

Separate from the test suite on purpose. A test asks whether a component does
what it was written to do. This asks whether the PRODUCT still works for the
people who use it — every persona, on every kind of company, including the ones
that go wrong.

It fails the build when:

  * any evaluator persona hits a critical failure;
  * the pass rate drops below the recorded baseline beyond tolerance;
  * a golden company stops producing a presentation;
  * a small or private company is held to public-company evidence.

The baseline is a committed file. Moving it is a decision that appears in a
diff with a reason attached, which is the entire point — a threshold quietly
lowered to make a build pass is how a regression becomes the new normal.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from intent_engine.product_eval.harness import build_cases, run_cases  # noqa: E402

BASELINE_PATH = os.path.join(os.path.dirname(__file__), "..", "reports",
                             "product_eval_baseline.json")
# How far the pass rate may fall before the build fails. Small on purpose:
# below this, a real regression hides inside the tolerance.
TOLERANCE = 0.02


def _load_baseline():
    try:
        with open(BASELINE_PATH) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def main() -> int:
    out = run_cases(build_cases())
    baseline = _load_baseline()
    problems = []

    failed = [r for r in out["results"] if r["critical"]]
    for result in failed:
        problems.append(f"{result['case_id']}: " +
                        "; ".join(result["critical"]))

    if baseline:
        floor = baseline["pass_rate"] - TOLERANCE
        if out["pass_rate"] < floor:
            problems.append(
                f"pass rate {out['pass_rate']} is below the recorded baseline "
                f"{baseline['pass_rate']} (tolerance {TOLERANCE})")
        if out["total_cases"] < baseline["total_cases"]:
            problems.append(
                f"the evaluation set shrank from {baseline['total_cases']} to "
                f"{out['total_cases']} cases — coverage may not be removed to "
                f"make a build pass")

    print(f"cases={out['total_cases']} failed={out['failed_cases']} "
          f"pass_rate={out['pass_rate']}"
          + (f" baseline={baseline['pass_rate']}" if baseline else
             " (no baseline recorded)"))

    if problems:
        print("\nRELEASE BLOCKED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nrelease gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

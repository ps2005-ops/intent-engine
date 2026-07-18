#!/usr/bin/env python
"""Task 3b (spun up 2026-07-17, per human decision on Task 3's PARK in
reports/overnight_trace.md): redesign the "ambiguous" case from Task 3's
gate to be genuinely uncertain on its own stated conditions, then rerun the
FULL 5x3 protocol fresh -- not just the ambiguous case. Same gating bars,
same budget ceiling as Task 3. This is a NEW, separate task script: Task 3's
own script (mechanism_extraction_reliability_gate.py) and its PARKED verdict
in the trace are untouched by this file. Per explicit instruction, Task 3
stays PARKED regardless of this script's outcome -- a human decides whether
this new evidence resolves it.

Why the original ambiguous case didn't test what it meant to: Task 3's
verdict noted the old text plainly stated its two conditions ("some
regulatory oversight," "a handful of larger companies") rather than leaving
real doubt about them -- so 5/5 unanimous, non-empty extraction was arguably
the CORRECT behavior for that text, not evidence of over-triggering. That's
a test-design flaw, not a resolved question about the extractor.

Redesign approach: the new ambiguous case below hedges the same two
candidate conditions (regulatory exposure, competitor concentration) with
language that leaves a careful reader genuinely unable to conclude the
condition is clearly present -- "not clear how many," "nothing formalized
yet, unclear how binding" -- rather than removing the signal entirely
(which would trivially yield an empty set and test nothing) or stating it
plainly (the old bug). A correct extractor should therefore show real
run-to-run variation, or consistently abstain on low confidence -- either
outcome is a genuine, non-forced signal; unanimous confident selection on
this text would be a real finding, not a test artifact.

Usage: python scripts/mechanism_extraction_reliability_gate_v2.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core.llm_client import LLMClient  # noqa: E402

# Reuse Task 3's extraction machinery verbatim (prompt, schema, run/summarize
# helpers) -- only the CASES dict's "ambiguous" entry changes. Importing
# rather than copy-pasting keeps the isolated-call discipline identical
# between the two gates, which matters for the rerun to be a fair test.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import mechanism_extraction_reliability_gate as gate_v1  # noqa: E402

FAST_MODEL = gate_v1.FAST_MODEL
run_round = gate_v1.run_round
summarize = gate_v1.summarize

CASES = {
    "clear_supply_shock": gate_v1.CASES["clear_supply_shock"],
    "clear_price_war": gate_v1.CASES["clear_price_war"],
    "ambiguous": (
        "We're evaluating whether to expand our product line into a new but related market "
        "segment. It's hard to tell how many serious players are already there versus just "
        "testing the waters -- estimates we've seen range from a couple of dominant names to a "
        "much longer tail of smaller ones, depending on how you draw the category boundary. "
        "There's talk of new rules that could apply to this space, but nothing has been "
        "formalized, and people we've talked to disagree about how binding any of it would "
        "actually end up being for a company our size. Getting started would take real capital, "
        "though we haven't nailed down how much relative to what we'd expect to earn back."
    ),
}


def main():
    client = LLMClient(model=FAST_MODEL)
    total_calls = 0

    print("=" * 90)
    print("TASK 3b ROUND 1: 5 runs x 3 cases (15 calls) -- redesigned ambiguous case, fresh run")
    print("=" * 90)
    round1 = run_round(CASES, client, runs=5)
    total_calls += 15

    summaries = {name: summarize(runs) for name, runs in round1.items()}
    print()
    for name, s in summaries.items():
        print(f"{name}: modal={s['modal']} ({s['modal_count']}/{s['total']}), distribution={s['distribution']}")

    # Bar (a): >=4/5 modal agreement on the two clear cases (unchanged from Task 3).
    supply_shock_stable = summaries["clear_supply_shock"]["modal_count"] >= 4
    price_war_stable = summaries["clear_price_war"]["modal_count"] >= 4

    # Bar (b): ambiguous case must not be confidently unanimous (5/5 identical AND non-empty).
    ambiguous_summary = summaries["ambiguous"]
    ambiguous_overconfident = ambiguous_summary["modal_count"] == 5 and len(ambiguous_summary["modal"]) > 0

    round2_summary = None
    if ambiguous_overconfident:
        print()
        print("=" * 90)
        print("Ambiguous case was STILL confidently unanimous (5/5, non-empty) even after redesign "
              "-- applying strengthened negative instruction, re-running ONLY the ambiguous case "
              "(5 more calls)")
        print("=" * 90)
        round2_runs = run_round({"ambiguous": CASES["ambiguous"]}, client, runs=5, strengthened=True)
        total_calls += 5
        round2_summary = summarize(round2_runs["ambiguous"])
        print(f"ambiguous (round 2, strengthened): modal={round2_summary['modal']} "
              f"({round2_summary['modal_count']}/{round2_summary['total']}), "
              f"distribution={round2_summary['distribution']}")
        ambiguous_overconfident = round2_summary["modal_count"] == 5 and len(round2_summary["modal"]) > 0

    print()
    print("=" * 90)
    print("VERDICT (Task 3b -- does NOT unpark Task 3; a human reviews this against Task 3's park)")
    print("=" * 90)
    print(f"Total live calls spent: {total_calls} (budget <=40, same ceiling as Task 3)")
    print(f"Bar (a) clear_supply_shock stable (>=4/5): {supply_shock_stable}")
    print(f"Bar (a) clear_price_war stable (>=4/5): {price_war_stable}")
    print(f"Bar (b) ambiguous case NOT confidently unanimous: {not ambiguous_overconfident}")

    overall_pass = supply_shock_stable and price_war_stable and not ambiguous_overconfident
    print()
    print(f"OVERALL: {'PASS' if overall_pass else 'PARK'}")
    return overall_pass


if __name__ == "__main__":
    main()

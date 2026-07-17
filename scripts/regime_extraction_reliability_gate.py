#!/usr/bin/env python
"""Task M4 (market-engine-execution-plan.md): the regime-extraction
reliability gate. TEST-ONLY scaffolding, per the task's own scope wall --
no production wiring regardless of outcome. Exactly the base-plan Task 3
pattern (scripts/mechanism_extraction_reliability_gate.py), adapted for
regime-flavored input: given real M2-shaped raw numbers plus a short set
of headlines, extract a trigger-condition profile from the FULL closed
taxonomy (the 11 original Task-2 conditions plus the 5 regime-derived
terms Task M3 added) -- isolated call, information-hiding (taxonomy
names only, no mechanism names/library, no M2's own pre-computed
booleans/labels in the prompt).

"No interpretation" (the plan's own words) is enforced deliberately: each
case's numbers below are either computed via the REAL M2 functions
(credit_spread_percentile, unemployment_momentum, inflation_trend,
drawdown_state) and only their raw numeric fields are rendered -- never
the derived boolean/label fields (triggered, trend) that would hand the
model its own answer -- or, for curve_inversion, the raw T10Y2Y spread
value itself (there is no "boolean" to strip; the spread number IS the
raw fact). The taxonomy given to the model is the bare list of condition
NAMES only, no added definitions, matching Task 3's own precedent
exactly -- "drawdown_gt_20pct" etc. are meant to be self-explanatory from
the name, the same way "concentrated_supplier_base" was.

Protocol: 5 runs x 3 constructed cases (one clearly stress-flavored, one
clearly benign, one deliberately ambiguous). Bars: (a) >=4/5 modal
agreement on the two clear cases; (b) the ambiguous case must NOT produce
confident unanimous triggers -- if it does, apply a strengthened negative
instruction once and re-run just the ambiguous case (not the full
protocol) with real distributions recorded either way; (c) real
distributions in the TRACE.

Usage: python scripts/regime_extraction_reliability_gate.py
"""

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core.llm_client import LLMClient  # noqa: E402
from intent_engine.core.mechanism_library import TriggerCondition  # noqa: E402

FAST_MODEL = "claude-haiku-4-5-20251001"

TRIGGER_CONDITIONS = list(TriggerCondition.__args__)

EXTRACTION_SYSTEM_PROMPT = f"""You are identifying which of a fixed set of structural/regime conditions are \
present, given a snapshot of raw macro/market numbers (with their source and observation date) and a short \
set of news headlines. You have no information about any historical pattern, precedent, or named phenomenon \
this might resemble -- judge ONLY what the numbers and headlines themselves state or clearly support. The \
numbers are raw facts, not pre-made judgments -- you must decide yourself whether a given number rises to the \
level each condition name describes.

The closed set of conditions you may select from (select ONLY ones the numbers or headlines actually support --\
 do not select a condition on a vague or generic resemblance):
{chr(10).join(f"- {c}" for c in TRIGGER_CONDITIONS)}

If the numbers and headlines are genuinely mixed, borderline, or don't clearly support any condition, select \
FEW or NONE -- do not force a selection to seem thorough. Confidence should track how clearly the evidence \
actually supports each condition, not how many conditions you can find a stretch for."""

EXTRACTION_SYSTEM_PROMPT_STRENGTHENED = EXTRACTION_SYSTEM_PROMPT + """

IMPORTANT: Err heavily toward selecting NOTHING or very little when the numbers/headlines are mixed, \
borderline, or could plausibly support many different readings. A confident, specific selection should only \
happen when the evidence leaves little real doubt. When in doubt, select fewer conditions, not more."""

EXTRACTION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "trigger_conditions": {
            "type": "array",
            "items": {"type": "string", "enum": TRIGGER_CONDITIONS},
            "description": "The subset of conditions the numbers/headlines actually, clearly support.",
        },
    },
    "required": ["trigger_conditions"],
}


def extract_trigger_conditions(snapshot_text: str, client: LLMClient, strengthened: bool = False) -> list:
    system = EXTRACTION_SYSTEM_PROMPT_STRENGTHENED if strengthened else EXTRACTION_SYSTEM_PROMPT
    result = client.call_tool(
        system=system,
        user_message=f"Regime snapshot:\n{snapshot_text}\n\nWhich conditions are present?",
        tool_name="record_trigger_conditions",
        tool_description="Record the identified trigger conditions.",
        input_schema=EXTRACTION_TOOL_SCHEMA,
        max_tokens=200,
    )
    return sorted(result["trigger_conditions"])


# Numbers below are real outputs of core.regime_engine's actual pure functions
# (credit_spread_percentile, unemployment_momentum, inflation_trend,
# drawdown_state) run against small constructed observation windows, rounded
# for readability -- only the RAW numeric fields are used, never the
# derived boolean/label fields (triggered, trend) those functions also
# return, so the model must independently judge whether each number rises
# to the level its matching taxonomy term describes. curve_inversion has no
# separate boolean to strip -- the T10Y2Y spread value itself is the raw fact.
CASES = {
    "clear_stress": (
        "- 10-Year minus 2-Year Treasury yield spread (T10Y2Y): -1.45 percentage points as of "
        "2026-06-30 (source: FRED, series T10Y2Y)\n"
        "- ICE BofA US High Yield Option-Adjusted Spread (BAMLH0A0HYM2): currently ranks at the "
        "60th percentile of its own trailing 10-year window as of 2024-08-01 (source: FRED, series "
        "BAMLH0A0HYM2)\n"
        "- CPI year-over-year: averaged 2.80% over the last 3 months vs. 2.88% over the last 12 "
        "months (source: FRED, series CPIAUCSL)\n"
        "- Unemployment rate: 3-month moving average currently equal to its own low over the prior "
        "12 months (delta 0.00 percentage points) (source: FRED, series UNRATE)\n"
        "- A broad equity price index is currently 4.17% below its own recent running high (source: "
        "a broad market price index)\n\n"
        "Headlines:\n"
        "- \"Retailers report steady holiday-season sales, in line with analyst expectations.\""
    ),
    "clear_benign": (
        "- 10-Year minus 2-Year Treasury yield spread (T10Y2Y): +1.35 percentage points as of "
        "2026-06-30 (source: FRED, series T10Y2Y)\n"
        "- ICE BofA US High Yield Option-Adjusted Spread (BAMLH0A0HYM2): currently ranks at the "
        "15th percentile of its own trailing 10-year window (source: FRED, series BAMLH0A0HYM2)\n"
        "- CPI year-over-year: averaged 2.10% over the last 3 months vs. 2.18% over the last 12 "
        "months (source: FRED, series CPIAUCSL)\n"
        "- Unemployment rate: 3-month moving average currently 0.03 percentage points BELOW its own "
        "low over the prior 12 months (source: FRED, series UNRATE)\n"
        "- A broad equity price index is currently at its own recent running high, 0.00% off "
        "(source: a broad market price index)\n\n"
        "Headlines:\n"
        "- \"Consumer confidence index ticks up for a third consecutive month; economists describe "
        "underlying trends as steady.\""
    ),
    "ambiguous": (
        "- 10-Year minus 2-Year Treasury yield spread (T10Y2Y): -0.04 percentage points as of "
        "2026-06-30 (source: FRED, series T10Y2Y)\n"
        "- ICE BofA US High Yield Option-Adjusted Spread (BAMLH0A0HYM2): currently ranks at the "
        "65th percentile of its own trailing 10-year window (source: FRED, series BAMLH0A0HYM2)\n"
        "- CPI year-over-year: averaged 3.40% over the last 3 months vs. 3.18% over the last 12 "
        "months (source: FRED, series CPIAUCSL)\n"
        "- Unemployment rate: 3-month moving average currently 0.20 percentage points above its own "
        "low over the prior 12 months (source: FRED, series UNRATE)\n"
        "- A broad equity price index is currently 11.82% below its own recent running high (source: "
        "a broad market price index)\n\n"
        "Headlines:\n"
        "- \"Manufacturing activity contracts for a third straight month, but services-sector growth "
        "remains resilient and consumer spending is holding up.\"\n"
        "- \"Fed officials are described as 'closely watching' incoming data but have given no signal "
        "of imminent policy action.\"\n"
        "- \"Analysts remain split on whether this represents an early warning sign or a temporary "
        "soft patch.\""
    ),
}


def run_round(case_texts: dict, client: LLMClient, runs: int = 5, strengthened: bool = False) -> dict:
    results = {}
    for case_name, text in case_texts.items():
        runs_out = []
        for i in range(runs):
            extracted = extract_trigger_conditions(text, client, strengthened=strengthened)
            runs_out.append(tuple(extracted))
            print(f"  [{case_name}] run {i + 1}/{runs}: {extracted}")
        results[case_name] = runs_out
    return results


def summarize(runs_out: list) -> dict:
    counter = Counter(runs_out)
    modal, modal_count = counter.most_common(1)[0]
    return {"modal": modal, "modal_count": modal_count, "total": len(runs_out), "distribution": dict(counter)}


def main():
    client = LLMClient(model=FAST_MODEL)
    total_calls = 0

    print("=" * 90)
    print("ROUND 1: 5 runs x 3 cases (15 calls)")
    print("=" * 90)
    round1 = run_round(CASES, client, runs=5)
    total_calls += 15

    summaries = {name: summarize(runs) for name, runs in round1.items()}
    print()
    for name, s in summaries.items():
        print(f"{name}: modal={s['modal']} ({s['modal_count']}/{s['total']}), distribution={s['distribution']}")

    # Bar (a): >=4/5 modal agreement on the two clear cases.
    stress_stable = summaries["clear_stress"]["modal_count"] >= 4
    benign_stable = summaries["clear_benign"]["modal_count"] >= 4

    # Bar (b): ambiguous case must not be confidently unanimous (5/5 identical AND non-empty).
    ambiguous_summary = summaries["ambiguous"]
    ambiguous_overconfident = ambiguous_summary["modal_count"] == 5 and len(ambiguous_summary["modal"]) > 0

    round2_summary = None
    if ambiguous_overconfident:
        print()
        print("=" * 90)
        print("Ambiguous case was confidently unanimous (5/5, non-empty) -- applying strengthened "
              "negative instruction, re-running ONLY the ambiguous case (5 more calls)")
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
    print("VERDICT")
    print("=" * 90)
    print(f"Total live calls spent: {total_calls} (budget <=40)")
    print(f"Bar (a) clear_stress stable (>=4/5): {stress_stable}")
    print(f"Bar (a) clear_benign stable (>=4/5): {benign_stable}")
    print(f"Bar (b) ambiguous case NOT confidently unanimous: {not ambiguous_overconfident}")

    overall_pass = stress_stable and benign_stable and not ambiguous_overconfident
    print()
    print(f"OVERALL: {'PASS' if overall_pass else 'PARK'}")
    return overall_pass


if __name__ == "__main__":
    main()

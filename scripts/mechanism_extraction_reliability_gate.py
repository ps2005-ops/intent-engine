#!/usr/bin/env python
"""Task 3 of the overnight execution plan (2026-07-15): the mechanism-
extraction reliability gate. TEST-ONLY scaffolding, per the task's own
scope wall -- no production wiring regardless of outcome. This script's
real output is what gates Task 4: if the bars below don't pass, Task 4 is
PARKED, not attempted with a guessed workaround.

The one new LLM capability this plan needs: extracting a decision's
trigger-condition profile (the closed taxonomy from core/mechanism_library.py)
from decision text, via an ISOLATED call. Information hiding, same
discipline as every other isolated judgment call in this project
(assess_copper_richness, the richness-call fix): the prompt shows only the
taxonomy of trigger conditions -- no mechanism names, no mechanism library,
nothing that could anchor the extraction toward a specific mechanism's
"expected" answer.

Protocol: 5 runs x 3 decision texts (one clearly matching supply-shock
triggers, one clearly matching price-war triggers, one deliberately
ambiguous). Bars: (a) >=4/5 modal agreement on the two clear cases;
(b) the ambiguous case must NOT produce confident unanimous triggers -- if
it does, apply a strengthened negative instruction once and re-run just
the ambiguous case (not the full protocol) with real distributions
recorded either way; (c) real distributions in the TRACE.

Usage: python scripts/mechanism_extraction_reliability_gate.py
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

EXTRACTION_SYSTEM_PROMPT = f"""You are identifying which of a fixed set of structural conditions are \
present in a business decision's description. You have no information about any historical \
pattern, precedent, or named phenomenon this might resemble -- judge ONLY what the text itself \
states or clearly implies.

The closed set of conditions you may select from (select ONLY ones the text actually supports --\
 do not select a condition on a vague or generic resemblance):
{chr(10).join(f"- {c}" for c in TRIGGER_CONDITIONS)}

If the text is genuinely ambiguous or doesn't clearly support any condition, select FEW or NONE \
-- do not force a selection to seem thorough. Confidence should track how clearly the text \
actually states each condition, not how many conditions you can find a stretch for."""

EXTRACTION_SYSTEM_PROMPT_STRENGTHENED = EXTRACTION_SYSTEM_PROMPT + """

IMPORTANT: Err heavily toward selecting NOTHING or very little when the text is ambiguous, \
generic, or could plausibly support many different readings. A confident, specific selection \
should only happen when the text leaves little real doubt. When in doubt, select fewer \
conditions, not more."""

EXTRACTION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "trigger_conditions": {
            "type": "array",
            "items": {"type": "string", "enum": TRIGGER_CONDITIONS},
            "description": "The subset of conditions the text actually, clearly supports.",
        },
    },
    "required": ["trigger_conditions"],
}


def extract_trigger_conditions(decision_text: str, client: LLMClient, strengthened: bool = False) -> list:
    system = EXTRACTION_SYSTEM_PROMPT_STRENGTHENED if strengthened else EXTRACTION_SYSTEM_PROMPT
    result = client.call_tool(
        system=system,
        user_message=f"Decision text:\n{decision_text}\n\nWhich conditions are present?",
        tool_name="record_trigger_conditions",
        tool_description="Record the identified trigger conditions.",
        input_schema=EXTRACTION_TOOL_SCHEMA,
        max_tokens=200,
    )
    return sorted(result["trigger_conditions"])


CASES = {
    "clear_supply_shock": (
        "We rely on a single overseas contract manufacturer for the specialized sensor chip in "
        "our product -- there is no qualified alternate supplier we could switch to within the "
        "next 6 months. A fire at their only fabrication plant last month has cut their output by "
        "60%, and we have no inventory buffer left."
    ),
    "clear_price_war": (
        "Our only two real competitors in this market both sell a functionally identical product "
        "to ours. Last week one of them cut list price by 15%. If we don't match within days we "
        "expect to lose meaningful share; if we match, our margins get wiped out. We expect they "
        "would immediately match any price increase we tried later, too."
    ),
    "ambiguous": (
        "We're evaluating whether to expand our product line into a new but related market "
        "segment. There's some regulatory oversight in this space, a handful of larger companies "
        "already operate there, and we'd need a meaningful upfront investment to get started."
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
    supply_shock_stable = summaries["clear_supply_shock"]["modal_count"] >= 4
    price_war_stable = summaries["clear_price_war"]["modal_count"] >= 4

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
    print(f"Bar (a) clear_supply_shock stable (>=4/5): {supply_shock_stable}")
    print(f"Bar (a) clear_price_war stable (>=4/5): {price_war_stable}")
    print(f"Bar (b) ambiguous case NOT confidently unanimous: {not ambiguous_overconfident}")

    overall_pass = supply_shock_stable and price_war_stable and not ambiguous_overconfident
    print()
    print(f"OVERALL: {'PASS' if overall_pass else 'PARK'}")
    return overall_pass


if __name__ == "__main__":
    main()

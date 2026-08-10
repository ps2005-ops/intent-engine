"""Break proofs for I-STA-001: five questions that can each say no.

Proof 1 is the one to read. It turns UNMEASURABLE into a comfortable zero,
which is the shape every one of this project's recorded false completions
took: a ratio nobody could compute reported beside one that came back fine.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

M = ROOT / "src/intent_engine/market"
T = "tests"
ST = f"{T}/test_market_stagnation.py"
RP = f"{T}/test_market_report_projections.py"

PROOFS = [
    ("1. an uncomputable ratio becomes a measured zero",
     M / "stagnation.py",
     "    if activity is None or produced is None:\n"
     "        return Check(name=name, outcome=UNMEASURABLE,",
     "    if activity is None or produced is None:\n"
     "        return Check(name=name, outcome=CLEAR,",
     f"{ST}::test_an_unmeasurable_check_is_not_a_passing_grade"),

    ("2. a quiet period fires as a stalled one",
     M / "stagnation.py",
     "    if activity < floor:\n"
     "        return Check(name=name, outcome=UNMEASURABLE, activity=activity,",
     "    if False:\n"
     "        return Check(name=name, outcome=UNMEASURABLE, activity=activity,",
     f"{ST}::test_a_quiet_period_is_not_a_stalled_one"),

    ("3. the check can no longer report the negative",
     M / "stagnation.py",
     "    outcome = FIRING if ratio < limit else CLEAR",
     "    outcome = FIRING",
     f"{ST}::test_a_healthy_ratio_reports_clear_rather_than_silence"),

    ("4. the five collapse to one shared activity floor",
     M / "stagnation.py",
     "MIN_ACTIVITY = {\n"
     "    EVIDENCE_WITHOUT_EFFECT: 50,\n"
     "    THESES_WITHOUT_RESOLUTION: 5,\n"
     "    SPEND_WITHOUT_VALUE: 10,\n"
     "    DISCOVERY_WITHOUT_VALIDATION: 3,\n"
     "    ANALYSIS_WITHOUT_IMPACT: 5,\n"
     "}",
     "MIN_ACTIVITY = {c: 50 for c in CHECKS}",
     f"{ST}::test_the_activity_floor_is_per_check_rather_than_shared"),

    ("5. two of the five stop meaning different things",
     M / "stagnation.py",
     '    THESES_WITHOUT_RESOLUTION:\n'
     '        "theses accumulate and none reaches a verdict; nothing is '
     'testing "\n'
     '        "the falsifiers, so the engine cannot be wrong and cannot be '
     'right",',
     '    THESES_WITHOUT_RESOLUTION:\n'
     '        "evidence is being ingested and almost none of it changes any "\n'
     '        "knowledge object; the readers are the suspect, not the corpus",',
     f"{ST}::test_there_are_five_and_each_means_something_different"),

    ("6. the summary folds unmeasurable in with clear",
     M / "stagnation.py",
     '        "unmeasurable": [c.name for c in checks\n'
     "                         if c.outcome == UNMEASURABLE],",
     '        "unmeasurable": [],',
     f"{ST}::test_the_summary_separates_unmeasurable_from_clear"),

    ("7. an unknown outcome is accepted",
     M / "stagnation.py",
     "        if self.outcome not in OUTCOMES:\n"
     "            raise ValueError(f\"unknown outcome {self.outcome!r}\")",
     "        if False:\n"
     "            raise ValueError(f\"unknown outcome {self.outcome!r}\")",
     f"{ST}::test_an_unknown_outcome_is_refused"),

    ("8. the block stops reaching the report",
     M / "report.py",
     '        "stagnation": {\n'
     '            k: (knowledge.get("stagnation") or {}).get(k)',
     '        "stagnation_unprojected": {\n'
     '            k: (knowledge.get("stagnation") or {}).get(k)',
     f"{RP}::test_every_required_key_survives_the_projection"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title=f"v4o — I-STA-001, stagnation detection: {len(PROOFS)} proofs"))

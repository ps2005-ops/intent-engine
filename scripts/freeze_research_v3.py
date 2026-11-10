"""§2/§30: freeze historical human-state research, and name the reopening gate.

WHAT IS BEING FROZEN, AND WHAT IS NOT
-------------------------------------
The INFRASTRUCTURE stays. `collective.py`, `construct.py`, `incremental.py`,
the regime classifier, the episode discovery, the equivalence tester -- all of
it remains live and is used by everything else. CollectiveHumanState remains a
CANDIDATE subsystem.

What freezes is FEATURE EXPANSION: no more searching for a behavioural series
that might make the historical result positive. Three cycles established that
the constraint is data, not method, and a fourth search would be the same
hypothesis tested again with the failures discarded.

THE RETIRED RESULT IS KEPT AT THE TOP
-------------------------------------
The most valuable thing this programme produced is not a signal. It is the
demonstration that the system retired its own best-looking finding when the
window widened. That record is written first, in full, with the numbers, so
that a later reader encounters the self-correction before the conclusion.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import evaluation_record as ER        # noqa: E402
from intent_engine.econ import preregistration as PR          # noqa: E402

OUT = pathlib.Path("reports")
CHECKPOINT = OUT / "world_model_research_v3.json"

FROZEN_CANDIDATE = "FROZEN_CANDIDATE"


def main() -> int:
    h7 = json.loads((OUT / "h7_experiment.json").read_text())
    adv = json.loads((OUT / "h7_adversary.json").read_text())
    close = json.loads((OUT / "v3_closure.json").read_text())
    equiv = json.loads((OUT / "panel/equivalence.json").read_text())
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()

    window = adv["tests"]["evaluation_window"]
    payload = {
        "checkpoint_id": "WORLD_MODEL_RESEARCH_V3",
        "supersedes": "WORLD_MODEL_RESEARCH_V2",
        "code_sha": sha,
        "status": FROZEN_CANDIDATE,

        # ---- THE THING WORTH KEEPING, FIRST -------------------------
        "the_retired_result": {
            "claim": ("consumer sentiment leads housing starts by 6-8 "
                      "months, replicated across two independent arms"),
            "reported_by": "WORLD_MODEL_RESEARCH_V2, as its one positive "
                           "finding",
            "retired_by": "H7 adversary test 7 (evaluation-window artifact)",
            "measurement": {
                "on_the_evaluation_subsample": {
                    "origins": window["HOUST"]["subsample"]["n"],
                    "lag_months": window["HOUST"]["subsample"]["best_lag"],
                    "correlation":
                        window["HOUST"]["subsample"]["best_correlation"],
                    "classification":
                        window["HOUST"]["subsample"]["classification"]},
                "on_the_full_record": {
                    "origins": window["HOUST"]["full"]["n"],
                    "lag_months": window["HOUST"]["full"]["best_lag"],
                    "correlation":
                        window["HOUST"]["full"]["best_correlation"],
                    "classification":
                        window["HOUST"]["full"]["classification"]}},
            "why_it_happened": (
                "the lag was computed from the paired-prediction file, which "
                "contains only the origins that appeared in the TEST FOLDS. "
                "Walk-forward reserves the earliest slice for training, so "
                "the measurement silently began in 1986 while the record "
                "begins in 1978. Restoring 1978-1986 -- the Volcker "
                "disinflation and the largest housing cycles in the sample "
                "-- removes the lead entirely AND RAISES the correlation "
                "from +0.298 to +0.405."),
            "the_general_lesson": (
                "a descriptive property of the data -- a temporal order, a "
                "base rate, a revision profile -- has no reason to be "
                "computed on an evaluation subsample. The paired-prediction "
                "file is a convenient source of origins and the wrong "
                "population."),
            "verdict": "RETIRE",
            "kept_because": (
                "this is the programme's most valuable output. A system that "
                "retires its own best-looking result when the window widens "
                "is the thing that eventually makes the product trustworthy; "
                "the signal never was.")},

        # ---- what was tested and what came back ---------------------
        "hypotheses": {
            "H1_GLOBAL": "NOT_PROMOTED (V1, delta -0.00948)",
            "H2_REGIME_CONDITIONAL": "INSUFFICIENT_DATA",
            "H3_GLOBAL_MONTHLY": {a: v["h3_verdict"] for a, v in
                                  json.loads((OUT / "v2_experiment.json")
                                             .read_text())["arms"].items()},
            "H4_STRESS_CONDITIONAL": {a: v["h4_verdict"] for a, v in
                                      json.loads((OUT / "v2_experiment.json")
                                                 .read_text())["arms"].items()},
            "H5_EARLY_WARNING": "NOT_SUPPORTED / INSUFFICIENT_EPISODES",
            "H6_TRANSMISSION": "NOT_SUPPORTED (both arms)",
            "H7_SENTIMENT_EARLY_WARNING": {
                "hash": PR.h7_hash(),
                "housing": "NOT SCORED — BASELINE_INVALID",
                "industrial": h7["arms"]["DEEP"]["h7_verdict"],
                "mechanism_role": adv["role"]}},
        "hypotheses_retired": ["UMCSENT->HOUST lead"],
        "hypotheses_unresolved": [
            "whether the collective block adds value in credit stress "
            "(never testable: no walled household credit series before 2012)",
            "whether sentiment has early-warning value on housing (never "
            "testable: no housing baseline beats a constant)"],
        "false_discoveries_killed": [
            "INFLATION_SHOCK +0.171 (one episode)",
            "CREDIT_STRESS +0.029 (hindsight regime labels)",
            "two SUPPORTED transmission mechanisms (scored on "
            "baseline-invalid families)",
            "'the V1 interval is too narrow' (measured; it is not)",
            "UMCSENT->HOUST 6-8 month lead (evaluation-window artifact)"],
        "constructs_promoted": 0,
        "founder_human_state_integration": "REFUSED",
        "history_rewind_human_state": "REFUSED",

        # ---- the boundary, named exactly ----------------------------
        "historical_limitations": {
            "walled_behavioural_coverage": (
                "credit and JOLTS series have no ALFRED vintage before "
                "2011-2012; underemployment now reaches 1964 through "
                "UEMP15OV and nothing else does"),
            "baseline_validity": (
                "3 of 10 preregistered families clear the baseline ladder; "
                "housing clears it at no horizon in either arm"),
            "independent_episodes": "15 on the deep arm",
            "unchecked_alternative": (
                "wealth effects — no vintage-correct household wealth series "
                "exists in this panel")},
        "remaining_external_data_gaps": close["information_priority"][:3],
        "equivalence_results": equiv["by_verdict"],

        # ---- §30 the reopening gate ---------------------------------
        "reopening_gate": {
            "state": FROZEN_CANDIDATE,
            "may_reopen_only_if": [
                "new historical data materially increases INDEPENDENT "
                "information (not rows, not origins — episodes or effective "
                "origins)",
                "REAL_FORWARD BASE/AUGMENTED results show meaningful "
                "divergence once the calibration ladder permits scoring",
                "new external evidence supports a SPECIFIC named construct"],
            "may_not_reopen_because": [
                "a new model architecture",
                "a longer series that has not passed the equivalence test",
                "a finer origin grid — measured twice, it is not the "
                "constraint",
                "a subgroup that looked promising after the fact"],
            "infrastructure_retained": True,
            "why_retained": (
                "the regime classifier, episode discovery, equivalence "
                "tester, power accounting and break-proof harness are used "
                "by every other workstream. Freezing feature expansion is "
                "not deleting the subsystem.")},
    }
    CHECKPOINT.write_text(json.dumps(payload, indent=2, sort_keys=True,
                                     default=str))

    existing = {e.evaluation_id for e in ER.load()}
    if "WORLD_MODEL_RESEARCH_V3" not in existing:
        inc = h7["arms"]["DEEP"]["incremental"]
        s = inc["sample"]
        ER.append(ER.Evaluation(
            evaluation_id="WORLD_MODEL_RESEARCH_V3",
            supersedes="WORLD_MODEL_RESEARCH_V2",
            method=ER.EPISODE_AWARE,
            reason=("H7 preregistered and resolved. The one replicated "
                    "observation from V2 was retired as an "
                    "evaluation-window artifact: the housing lead exists on "
                    "the 482 test-fold origins and not on all 584. Historical "
                    "human-state research is now FROZEN_CANDIDATE."),
            delta=inc["delta"], ci_low=(inc["episode_ci"] or inc["ci"])[0],
            ci_high=(inc["episode_ci"] or inc["ci"])[1],
            raw_rows=s["raw_rows"], unique_origins=s["unique_origins"],
            effective_origins=s["effective_origins"],
            independent_episodes=s["independent_episodes"],
            code_sha=sha,
            panel_hash=h7["panel"]["content_hash"],
            preregistration_hash=PR.h7_hash(), at="2026-08-27",
            original_method=ER.CLUSTER_BOOTSTRAP,
            original_ci=tuple(inc["ci"]), mde=inc["mde"],
            note=("industrial production only; housing was BASELINE_INVALID "
                  "and could not be scored at all.")))

    print("=== §2 WORLD_MODEL_RESEARCH_V3 — FROZEN_CANDIDATE ===")
    r = payload["the_retired_result"]
    print(f"\n  THE RETIRED RESULT (kept first, deliberately)")
    print(f"    {r['claim']}")
    for k in ("on_the_evaluation_subsample", "on_the_full_record"):
        m = r["measurement"][k]
        print(f"      {k:<32} n={m['origins']}  lag {m['lag_months']:+d}  "
              f"corr {m['correlation']:+.3f}  {m['classification']}")
    print(f"    verdict {r['verdict']} — {r['kept_because'][:80]}...")
    print(f"\n  false discoveries killed across the programme: "
          f"{len(payload['false_discoveries_killed'])}")
    print(f"  constructs promoted: {payload['constructs_promoted']}")
    print(f"  reopening gate: {payload['reopening_gate']['state']} — "
          f"{len(payload['reopening_gate']['may_reopen_only_if'])} routes in, "
          f"{len(payload['reopening_gate']['may_not_reopen_because'])} "
          f"explicitly closed")
    print(f"  infrastructure retained: "
          f"{payload['reopening_gate']['infrastructure_retained']}")
    print(f"  registry now {len(ER.load())} evaluations")
    print(f"  wrote {CHECKPOINT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

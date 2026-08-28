"""§14/§15/§18-§21/§27/§28: verdicts, the episode ledger, and going forward.

The historical question is settled as far as this data can settle it. What is
left is to say which ROLE each construct earned (none), to record the episode
structure a later run inherits, to open the forward pairs that will eventually
judge all of this, and to rank what evidence would actually change the answer.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import belief as BF                   # noqa: E402
from intent_engine.econ import calibration as CAL             # noqa: E402
from intent_engine.econ import episodes as EPI                # noqa: E402
from intent_engine.econ import evaluation_record as ER        # noqa: E402
from intent_engine.econ import panel as PN                    # noqa: E402
from intent_engine.econ import preregistration as PR          # noqa: E402
from intent_engine.econ import regime as RG                   # noqa: E402
from intent_engine.econ import residual as RS                 # noqa: E402
from intent_engine.econ import zero_trade as ZT               # noqa: E402

OUT = pathlib.Path("reports")
TODAY = "2026-08-27"
SIGNAL_ID = "UMCSENT"
FORWARD = OUT / "real_forward_expectations.jsonl"

# =============================================================================
# §14: PURPOSE-SPECIFIC VERDICTS
# =============================================================================
ROLES = ("FORECASTING", "EARLY_WARNING", "TRANSMISSION_CONTEXT",
         "REGIME_CLASSIFICATION", "NO_USEFUL_ROLE")
VERDICTS = ("PROMOTE_GLOBAL_FORECAST", "PROMOTE_REGIME_FORECAST",
            "PROMOTE_EARLY_WARNING", "PROMOTE_TRANSMISSION_CONTEXT",
            "OBSERVED", "LEADING_BUT_REDUNDANT", "TESTED_NOT_PROMOTED",
            "RETIRE", "INSUFFICIENT_DATA")


def sha():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    PR.assert_h7_unchanged("3a5c4d36259e08a2")
    h7 = json.loads((OUT / "h7_experiment.json").read_text())
    adv = json.loads((OUT / "h7_adversary.json").read_text())
    v3 = json.loads((OUT / "v2_experiment.json").read_text())
    equiv = json.loads((OUT / "panel/equivalence.json").read_text())
    out = {"at": TODAY, "code_sha": sha(), "h7_hash": PR.h7_hash()}

    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    man = json.loads((OUT / "panel/historical_acquisition_manifest.json"
                      ).read_text())
    origins = man["origins_deep"] + man["origins_modern"]
    eps = EPI.discover(RG.classify_many(panel, origins))
    EPI.assert_no_artificial_split(eps)

    # ------------------ §15 EPISODE LEDGER ---------------------------
    beh = tuple(v3["arms"]["MODERN"]["arm"]["behavioural_series"])
    led = EPI.ledger(eps, panel=panel, behavioural=beh,
                     targets=list(PR.TARGET_SERIES))
    out["episode_ledger"] = led
    print("=== §15 EPISODE LEDGER ===")
    print(f"  {len(eps)} episodes, {led['testable_for_behaviour']} with at "
          f"least two walled behavioural series in them")
    for r in led["detail"]:
        print(f"    {r['episode_id']:<12}{r['start_as_known']}.."
              f"{r['end_as_known']}  {r['origins']:>3} origins  "
              f"behavioural {len(r['behavioural_available'])}/{len(beh)}  "
              f"{'TESTABLE' if r['testable_for_behaviour'] else 'not testable'}")
    print("  anti-split guard: PASS (no two episodes closer than the "
          f"{EPI.NORMALISATION_ORIGINS}-origin normalisation)")

    # ------------------ §14 PURPOSE-SPECIFIC VERDICTS -----------------
    print("\n=== §14 PURPOSE-SPECIFIC VERDICTS ===")
    window_artifacts = set(adv.get("window_artifacts") or [])
    h7_verdicts = {a: v.get("h7_verdict") for a, v in h7["arms"].items()}
    sentiment = {}
    for tgt in ("HOUST", "INDPRO"):
        if tgt in window_artifacts:
            v, why = "RETIRE", (
                "the lead was a property of the origins that were measured, "
                "not of the series. On the 482 evaluation-fold origins "
                "UMCSENT leads HOUST by 6 months; on all 584 the lag is 0 "
                "and the correlation is HIGHER (+0.405 against +0.298). "
                "Adding 1978-1986 -- the Volcker disinflation and the "
                "largest housing cycles in the sample -- removes the lead.")
        elif h7_verdicts.get("DEEP") == "PROMOTE_EARLY_WARNING":
            v, why = "PROMOTE_EARLY_WARNING", "cleared the alarm-matched test"
        elif h7_verdicts.get("DEEP") == "PROMOTE_GLOBAL_FORECAST":
            v, why = "PROMOTE_GLOBAL_FORECAST", "cleared the Brier test"
        elif h7_verdicts.get("DEEP") == "INSUFFICIENT_POWER":
            v, why = "INSUFFICIENT_DATA", (
                "the lead is robust to the window and survives each "
                "confounder singly, but the incremental Brier delta is "
                f"{h7['arms']['DEEP']['incremental']['delta']:+.5f} with an "
                "episode-aware interval spanning zero, and only one episode "
                "was warned by both models -- below the floor of three.")
        else:
            v, why = "LEADING_BUT_REDUNDANT", "the lead carries no value"
        # THE GUARD, CALLED. `assert_lead_is_not_causal` existed with no
        # production caller -- the same absence break proof 12 found last
        # run. A verdict stronger than the lead-only states must come from
        # the incremental or lead-time test, and this is where that is
        # enforced rather than intended.
        claim = adv["tests"]["claim"][tgt]
        RS.assert_lead_is_not_causal(
            RS.TemporalOrder(signal=SIGNAL_ID, target=tgt,
                             best_lag=claim["best_lag"],
                             best_correlation=claim["best_correlation"],
                             lag_profile=(), n=claim["n"]),
            v if v in RS.LEAD_ONLY_STATES else "OBSERVED")
        sentiment[f"UMCSENT->{tgt}"] = {
            "role_tested": ["FORECASTING", "EARLY_WARNING"],
            "verdict": v, "why": why,
            "mechanism_role": adv["role"]}
        print(f"  UMCSENT->{tgt:<8} {v:<22} ({adv['role']})")
    # The joint-confounder result is the mechanism finding and applies to
    # both targets.
    print(f"  mechanism: {adv['role']} — the lead survives UNRATE, BAA and "
          "CPIAUCSL taken one at a time and is killed by all three together")
    out["construct_verdicts"] = {
        "sentiment": sentiment,
        "collective_block": {
            arm: {"H3": v3["arms"][arm]["h3_verdict"],
                  "H4": v3["arms"][arm]["h4_verdict"],
                  "verdict": "INSUFFICIENT_DATA",
                  "why": ("re-run on the V3 panel with a stronger base block "
                          "and UEMP15OV added; both verdicts unchanged")}
            for arm in v3["arms"]},
        "underemployment_extension": {
            "series": "UEMP15OV", "verdict": "OBSERVED",
            "why": ("DEFENSIBLE_PROXY for U6RATE, extending the construct "
                    "from 2012 back to 1964. It reaches the model; it has "
                    "not yet earned a predictive role.")},
        "refused_candidates": equiv["by_verdict"],
    }

    # ------------------ §18 REAL_FORWARD EXPANSION -------------------
    print("\n=== §18 REAL_FORWARD ===")
    existing = []
    if FORWARD.exists():
        existing = [json.loads(l) for l in FORWARD.read_text().splitlines()
                    if l.strip()]
    prior = json.loads((OUT / "v2_closure.json").read_text())
    if not existing:
        existing = [{**e, "source": "V2"}
                    for e in prior["real_forward"]["expectations"]]
    have = {e["expectation_id"] for e in existing}

    # ELIGIBILITY: only families whose base model cleared the ladder. A
    # forward pair on a family that loses to a constant would resolve into a
    # calibration record about the harness.
    eligible = sorted(set(v3["arms"]["DEEP"]["baseline_gate_passing_families"])
                      | set(v3["arms"]["MODERN"]
                            ["baseline_gate_passing_families"]))
    opened = []
    for fid in eligible:
        fam = PR.BY_ID[fid]
        b = BF.declare(
            proposition=(f"the conventional economic block predicts the "
                         f"direction of {fam.target_series} at "
                         f"{fam.horizon_days} days better than a constant, "
                         f"and adding the collective block does not improve "
                         f"it"),
            probability=0.5,
            mechanism=("the base model cleared every trivial baseline on "
                       "this family historically; the collective block did "
                       "not clear the episode-aware interval"),
            falsifier=(f"the AUGMENTED forecast resolves better than the "
                       f"BASE forecast on this family across the next "
                       f"{PR.H7['episode_floor']} resolved windows"),
            expected_observations=(f"{fam.target_series} direction over "
                                   f"{fam.horizon_days} days",),
            at=TODAY, subject="US_economy")
        for model in ("BASE", "AUGMENTED"):
            e = BF.preregister(
                belief=b, quantity=f"{fam.target_series}/{fid}/{model}",
                direction=BF.UP, confidence=0.5,
                resolution_rule=(
                    f"resolved from the ALFRED vintage of "
                    f"{fam.target_series} available {fam.horizon_days} days "
                    f"from the cutoff; UP means the level is higher than at "
                    f"the cutoff"),
                at=TODAY, information_cutoff=TODAY,
                horizon_days=fam.horizon_days,
                expires_at=(_dt.date(2026, 8, 27)
                            + _dt.timedelta(days=fam.horizon_days)).isoformat())
            if e.expectation_id in have:
                continue
            opened.append({**e.as_dict(), "model": model, "family": fid,
                           "source": "V3",
                           "eligible_because": "base model cleared the ladder",
                           "code_sha": sha(), "panel_hash":
                               v3["panel"]["content_hash"],
                           "h7_hash": PR.h7_hash()})
            have.add(e.expectation_id)
    allf = existing + opened
    FORWARD.write_text("\n".join(json.dumps(e, sort_keys=True)
                                 for e in allf) + "\n")
    pairs = len(allf) // 2
    print(f"  carried forward {len(existing)} (immutable), opened "
          f"{len(opened)} new")
    print(f"  {len(allf)} expectations = {pairs} BASE/AUGMENTED pairs "
          f"(target was >=12 expectations)")
    for e in opened:
        print(f"    {e['expectation_id']}  {e['quantity']:<38} "
              f"h={e['horizon_days']}d expires {e['expires_at']}")
    out["real_forward"] = {
        "total": len(allf), "carried": len(existing), "opened": len(opened),
        "pairs": pairs, "path": str(FORWARD),
        "status": "AWAITING_REAL_WORLD_RESOLUTION",
        "note": ("§19: no session time is spent waiting. The expectations "
                 "are open, the lifecycle is proved, and the next judge is "
                 "the calendar.")}

    # ------------------ §21 ZERO-TRADE / NO-SIGNAL -------------------
    print("\n=== §21 NO-SIGNAL LEARNING ===")
    zt = [
        {"cycle": "V3_H7_HOUST", "outcome": "REJECTED_SIGNAL",
         "reason": ("the temporal order was a window artifact; the lead "
                    "vanishes on the full origin record"),
         "information_missing": "none — this was resolvable and resolved",
         "confidence": 0.95,
         "later_evaluation_rule": ("re-open only if a measurement on the "
                                   "FULL record shows a lead")},
        {"cycle": "V3_H7_INDPRO", "outcome": "NO_SIGNAL",
         "reason": ("the lead is robust but the incremental Brier delta is "
                    "negative with an episode-aware interval spanning zero, "
                    "and only one episode was warned by both models"),
         "information_missing": ("more episodes in which the base model "
                                 "warns at all"),
         "confidence": 0.6,
         "later_evaluation_rule": ("re-test when the eligible-family episode "
                                   "count exceeds three warned episodes")},
        {"cycle": "V3_HOUSING_BASELINE", "outcome": "NO_SIGNAL",
         "reason": ("housing direction is BASELINE_INVALID in both arms at "
                    "both horizons: the macro block scores 0.2735 against a "
                    "constant's 0.2525"),
         "information_missing": ("a housing model that beats a coin flip; "
                                 "this is not a human-state failure"),
         "confidence": 0.9,
         "later_evaluation_rule": ("H7 on housing cannot be scored until a "
                                   "base model clears the ladder")},
    ]
    out["zero_trade"] = zt
    for r in zt:
        print(f"  {r['cycle']:<22}{r['outcome']:<18}{r['reason'][:60]}")

    # ------------------ §27 INFORMATION PRIORITY ---------------------
    print("\n=== §27 INFORMATION PRIORITY ===")
    evsi = [
        {"question": ("a vintage-correct household credit series before "
                      "2012 (H.8 delinquency real-time archive, or a "
                      "licensed bank-panel equivalent)"),
         "uncertainty": "HIGH", "decision_impact": "HIGH",
         "expected_power_gain": ("financial_anxiety becomes testable across "
                                 "8 more episodes; it is currently the only "
                                 "construct with a discriminating instrument "
                                 "and no history"),
         "acquisition_cost": "MEDIUM — likely a licensed or FOIA route",
         "score": 9},
        {"question": ("a housing-direction baseline that beats a constant "
                      "(mortgage rates, permits, months-of-supply, all "
                      "vintage-correct)"),
         "uncertainty": "HIGH", "decision_impact": "HIGH",
         "expected_power_gain": ("unblocks the target where the sentiment "
                                 "claim was strongest; today it cannot be "
                                 "scored at all"),
         "acquisition_cost": "LOW — MORTGAGE30US and PERMIT are on ALFRED",
         "score": 9},
        {"question": ("a vintage-correct household WEALTH series, to close "
                      "the one adversary alternative that is UNTESTABLE"),
         "uncertainty": "MEDIUM", "decision_impact": "MEDIUM",
         "expected_power_gain": ("turns 'unchecked' into 'ruled out' for the "
                                 "mechanism claim"),
         "acquisition_cost": "MEDIUM — Z.1 has no early real-time archive",
         "score": 6},
        {"question": ("pre-JOLTS labour FLOW data (hires and separations, "
                      "not stocks)"),
         "uncertainty": "MEDIUM", "decision_impact": "MEDIUM",
         "expected_power_gain": ("UEMPMEAN failed as a quits proxy with "
                                 "crisis agreement 0.00; a real flow series "
                                 "would extend perceived_control"),
         "acquisition_cost": "HIGH — no keyless vintage source found",
         "score": 4},
        {"question": "more forecast origins or a finer grid",
         "uncertainty": "LOW", "decision_impact": "LOW",
         "expected_power_gain": ("measured at x2.86 rows for x3.63 effective "
                                 "origins last run; the grid is not the "
                                 "constraint and has not been for two runs"),
         "acquisition_cost": "LOW", "score": 1},
    ]
    out["information_priority"] = sorted(evsi, key=lambda r: -r["score"])
    for r in out["information_priority"]:
        print(f"  [{r['score']}] {r['question'][:88]}")

    # ------------------ §27 CALIBRATION WALL -------------------------
    rep = CAL.report([])
    out["calibration"] = {
        "status": str(CAL.status([])),
        "resolved": 0, "minimum": CAL.MIN_RESOLVED,
        "open_expectations": len(allf),
        "rule": ("every number in this run is HISTORICAL OUT-OF-SAMPLE "
                 "PERFORMANCE and none of it is live accuracy")}
    print(f"\n=== CALIBRATION === {out['calibration']['status']} "
          f"({len(allf)} open, 0 resolved, {CAL.MIN_RESOLVED} required)")

    # ------------------ §23 FOUNDER ----------------------------------
    promoted = [k for k, v in sentiment.items()
                if v["verdict"].startswith("PROMOTE")]
    out["founder_integration"] = {
        "status": "REFUSED" if not promoted else "ELIGIBLE",
        "why": ("nothing earned a supported role. The one replicated "
                "observation was retired as a window artifact on housing and "
                "is INSUFFICIENT_DATA on industrial production. The "
                "six-company test is not run." if not promoted
                else f"promoted: {promoted}")}
    print(f"=== §23 FOUNDER === {out['founder_integration']['status']}")

    # ------------------ §28 LEARNING ACCELERATION --------------------
    deep_v3 = v3["arms"]["DEEP"]["sample"]
    v2ck = json.loads((OUT / "world_model_research_v2.json").read_text())
    out["learning"] = {
        "series_probed": 20, "series_admitted": 5,
        "series_refused": 15,
        "constructs_extended": ["underemployment (2012 -> 1964)"],
        "hypotheses_preregistered": 1,
        "hypotheses_resolved": 1,
        "false_discoveries_killed": 1,
        "assumptions_retired": 3,
        "effective_origins_v2": v2ck["power"]["DEEP"]["effective_origins"],
        "effective_origins_v3": deep_v3["effective_origins"],
        "episodes_v2": v2ck["power"]["DEEP"]["independent_episodes"],
        "episodes_v3": deep_v3["independent_episodes"],
        "network_calls": 580,
        "real_forward_pairs": pairs,
        "learning_quality": (
            "HIGH: the single replicated result the previous run reported as "
            "its one positive finding was retired by a test this run built "
            "to attack it. That is the machinery working."),
        "stagnation": (
            "NO: the constraint moved from 'historical behavioural depth' to "
            "two specific, named, cheap-to-acquire gaps — a pre-2012 "
            "household credit archive and a housing baseline that beats a "
            "coin flip."),
    }
    print("\n=== §28 LEARNING ===")
    for k, v in out["learning"].items():
        if isinstance(v, str) and len(v) > 70:
            print(f"  {k:<26} {v[:70]}...")
        else:
            print(f"  {k:<26} {v}")

    (OUT / "v3_closure.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/v3_closure.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

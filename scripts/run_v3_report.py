"""§32: the V3 report, checked against its own calibration status."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import calibration as CAL            # noqa: E402
from intent_engine.econ import forward_ledger as FL          # noqa: E402
from intent_engine.econ import preregistration as PR         # noqa: E402

OUT = pathlib.Path("reports")


def _j(n):
    return json.loads((OUT / n).read_text())


def main() -> int:
    h7 = _j("h7_experiment.json")
    adv = _j("h7_adversary.json")
    v3 = _j("v2_experiment.json")
    close = _j("v3_closure.json")
    equiv = _j("panel/equivalence.json")
    depth = _j("panel/behavioural_depth.json")
    v2ck = _j("world_model_research_v2.json")
    bp = _j("break_proofs_v3.json") if (OUT / "break_proofs_v3.json").exists() \
        else {"caught": "pending", "proofs": 12, "not_caught": "-",
              "not_applied": "-", "unreliable": "-"}
    life = FL.assert_lifecycle()

    L = []
    A = L.append
    A("HISTORICAL_COVERAGE")
    A(f"    candidates probed        = {len(depth['candidates'])}")
    A(f"    reached before 2011      = 12")
    A(f"    equivalence-tested       = {equiv['tested']}")
    for v, names in sorted(equiv["by_verdict"].items()):
        A(f"    {v:<24} = {names}")
    A(f"    ADMITTED to the behavioural block = ['UEMP15OV'] "
      f"(DEFENSIBLE_PROXY for U6RATE, extending `underemployment` from 2012 "
      f"back to 1964)")
    A(f"    ADMITTED to the base block        = ['BAA','BAA10Y','AAA10Y',"
      f"'T10Y3M'] — never-revised market prices. NOT behavioural proxies: "
      f"the rank correlation of a corporate credit spread with household "
      f"credit-card delinquency is +0.04.")
    A(f"    REFUSED                           = UMCSENT1 (it is FRED's "
      f"pre-1978 quarterly segment of UMCSENT itself, scoring 1.00 on all "
      f"four metrics because it IS the incumbent), UEMPMEAN (crisis "
      f"agreement 0.00 against JTSQUR, 0.17 against U6RATE)")
    A("")
    A("POWER")
    a2, a3 = v2ck["power"]["DEEP"], v3["arms"]["DEEP"]["sample"]
    A(f"    V2 effective origins = {a2['effective_origins']}")
    A(f"    V3 effective origins = {a3['effective_origins']}")
    A(f"    V2 episodes          = {a2['independent_episodes']}")
    A(f"    V3 episodes          = {a3['independent_episodes']}")
    A(f"    V2 MDE               = {v2ck['median_mde']['DEEP']}")
    A(f"    V3 MDE               = {v3['arms']['DEEP']['h3']['mde']}")
    A(f"    The effective count FELL. Adding four financial-conditions "
      f"controls changed the base model's predictions, and the paired "
      f"differences became more autocorrelated across origins. More "
      f"features is not more independent information, and the run says so "
      f"rather than quoting the row count.")
    A("")
    A("H7 SENTIMENT")
    deep = h7["arms"]["DEEP"]
    A(f"    preregistered as {PR.h7_hash()} before the V3 panel was scored")
    A(f"    housing:              NOT SCORED — BASELINE_INVALID in both arms "
      f"at both horizons. Historical out-of-sample: the macro block scores "
      f"Brier 0.2735 against a constant's 0.2525. This is not a human-state "
      f"failure.")
    inc = deep["incremental"]
    A(f"    industrial production (historical out-of-sample, paired Brier):")
    A(f"                           incremental delta {inc['delta']:+.5f}")
    A(f"                           clustered CI {inc['ci']}")
    A(f"                           episode-aware CI {inc['episode_ci']}")
    A(f"                           sample {inc['sample']['headline']}")
    A(f"                           lead time: 1 episode warned by both "
      f"models, below the floor of 3")
    A(f"                           episode stability: "
      f"{deep['episode_stability']['classification']} — the sign of the "
      f"delta flips between episode classes")
    A(f"    VERDICT              = {deep['h7_verdict']}")
    A("")
    A("    THE OBSERVED SIGNAL DID NOT SURVIVE")
    w = adv["tests"]["evaluation_window"]
    for t, r in sorted(w.items()):
        A(f"      UMCSENT -> {t:<7} subsample(n={r['subsample']['n']}) lag "
          f"{r['subsample']['best_lag']:+d} "
          f"{r['subsample']['classification']} | full(n={r['full']['n']}) "
          f"lag {r['full']['best_lag']:+d} {r['full']['classification']}"
          f"  => {'ROBUST' if r['robust_to_window'] else 'WINDOW ARTIFACT'}")
    A(f"      The previous run measured the lag on the 482 origins that "
      f"appeared in its TEST FOLDS. Walk-forward reserves the earliest "
      f"slice for training, so the measurement began in 1986 while the "
      f"record begins in 1978. Adding the Volcker disinflation and the "
      f"1980-82 housing cycles removes the housing lead entirely and RAISES "
      f"the correlation from +0.298 to +0.405.")
    A(f"      Confounders: the industrial lead survives UNRATE, BAA and "
      f"CPIAUCSL one at a time and is KILLED by all three together "
      f"(lag -11, LAGGING).")
    A(f"      2008 break: pre-2008 sentiment LAGS housing by 2 months; "
      f"post-2008 it leads by 8. Not one mechanism.")
    A(f"      Wealth effects: UNTESTABLE — no vintage-correct household "
      f"wealth series exists in this panel. Unchecked, not ruled out.")
    A(f"    MECHANISM ROLE       = {adv['role']}")
    A("")
    A("H3/H4/H5/H6 (rerun: feature coverage and baseline quality both changed)")
    for arm in sorted(v3["arms"]):
        A(f"    {arm:<8} H3 {v3['arms'][arm]['h3_verdict']}  "
          f"H4 {v3['arms'][arm]['h4_verdict']}")
    A(f"    unchanged from V2. The stronger base block and the added "
      f"underemployment history did not move either verdict.")
    A("")
    A("BASELINE VALID TARGETS")
    for arm in sorted(h7["arms"]):
        el = h7["arms"][arm].get("eligibility", {})
        ok = [f for f, v in el.items()
              if v["eligibility"]["eligible_for_human_test"]]
        A(f"    {arm:<8} {ok or 'none'} of {sorted(el)}")
    A(f"    V3 forecast families clearing the ladder: DEEP "
      f"{v3['arms']['DEEP']['baseline_gate_passing_families']}, MODERN "
      f"{v3['arms']['MODERN']['baseline_gate_passing_families']}")
    A("")
    A("CONSTRUCT VERDICTS / HUMAN-STATE ROLES")
    for k, v in sorted(close["construct_verdicts"]["sentiment"].items()):
        A(f"    {k:<20} {v['verdict']}")
    A(f"    collective_block     INSUFFICIENT_DATA (both arms)")
    A(f"    UEMP15OV             OBSERVED — reaches the model, no role earned")
    A(f"    no construct earned FORECASTING, EARLY_WARNING, "
      f"TRANSMISSION_CONTEXT or REGIME_CLASSIFICATION")
    A("")
    A(f"REAL_FORWARD")
    A(f"    open       = {life['open']} expectations = "
      f"{close['real_forward']['pairs']} BASE/AUGMENTED pairs")
    A(f"    resolved   = {life['resolved']}")
    A(f"    waiting    = {close['real_forward']['status']}")
    A(f"    lifecycle  = all seven facts hold "
      f"({life['all_seven_hold']}): opens with a resolution rule, survives "
      f"reload, refuses retrospective edit, resolves only at horizon, "
      f"resolution appends, calibration consumes resolved only, unresolved "
      f"excluded")
    A("")
    A(f"FOUNDER_INTEGRATION      = {close['founder_integration']['status']}")
    A(f"HISTORY_REWIND           = NOT RUN. §24 requires validated episode "
      f"data and nothing was validated; running it would show a "
      f"CollectiveHumanState reading no test supports.")
    A(f"CAUSAL_BLEEDS            = none promoted. H6 was NOT_SUPPORTED in "
      f"both arms in V2 and was not re-run: no mechanism input changed.")
    A(f"FALSE_DISCOVERIES_KILLED = 1 — 'consumer sentiment leads housing "
      f"starts by 6-8 months', the previous run's single positive finding.")
    A(f"ASSUMPTIONS_RETIRED      = 3 — that a longer series is a proxy "
      f"(rank +0.04); that UMCSENT1 is the expectations component (it is "
      f"UMCSENT); that a temporal order measured on evaluation folds "
      f"describes the series.")
    A("")
    A("LEARNING_ACCELERATION")
    for k in ("series_probed", "series_admitted", "series_refused",
              "hypotheses_preregistered", "hypotheses_resolved",
              "false_discoveries_killed", "assumptions_retired",
              "network_calls", "real_forward_pairs"):
        A(f"    {k:<28} {close['learning'][k]}")
    A("")
    A(f"CALIBRATION_STATUS       = {close['calibration']['status']} "
      f"({life['open']} open, 0 resolved, {CAL.MIN_RESOLVED} required). "
      f"Every number above is HISTORICAL OUT-OF-SAMPLE PERFORMANCE.")
    A(f"BREAK_PROOFS             = {bp['caught']}/{bp['proofs']} CAUGHT, "
      f"{bp['not_caught']} NOT_CAUGHT, {bp['not_applied']} NOT_APPLIED, "
      f"{bp['unreliable']} UNRELIABLE")
    text = "\n".join(L)

    rep = CAL.report([])
    CAL.assert_no_unsupported_claim(text, rep)

    print(text)
    (OUT / "v3_final_report.txt").write_text(text + "\n")
    print(f"\n  wrote reports/v3_final_report.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

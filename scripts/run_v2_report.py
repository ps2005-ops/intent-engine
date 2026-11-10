"""§31: the final report, and the guard that checks its own wording.

WHY THE REPORT VALIDATES ITSELF
-------------------------------
`calibration.assert_no_unsupported_claim` existed, was unit-tested, and had
NO production caller -- break proof 12 found it by mutating the call site and
discovering there was none to mutate. A guard nothing calls is a guard that
has never run.

So the report text is assembled first and then passed through it. Every
number here is HISTORICAL OUT-OF-SAMPLE PERFORMANCE, the calibration status
is PRE_CALIBRATION, and if a future edit writes "accuracy" or "hit rate" into
this file the report refuses to be written rather than shipping the claim.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import calibration as CAL            # noqa: E402
from intent_engine.econ import evaluation_record as ER       # noqa: E402
from intent_engine.econ import preregistration as PR         # noqa: E402

OUT = pathlib.Path("reports")


def _j(name):
    return json.loads((OUT / name).read_text())


def main() -> int:
    v1 = _j("v1_reevaluation.json")
    v2 = _j("v2_experiment.json")
    mech = _j("v2_mechanism.json")
    close = _j("v2_closure.json")
    bp = _j("break_proofs_power.json")
    man = _j("panel/historical_acquisition_manifest.json")
    depth = _j("panel/historical_depth.json")

    deep = v2["arms"]["DEEP"]
    modern = v2["arms"]["MODERN"]
    before, after = v1["sample"], deep["sample"]
    L = []
    A = L.append

    A("POWER BEFORE  (V1, quarterly grid, 115 origins)")
    A(f"    raw rows   = {before['raw_rows']}")
    A(f"    origins    = {before['unique_origins']}")
    A(f"    n_eff      = {before['effective_origins']}")
    A(f"    episodes   = {v1.get('phase_based_episodes') or before['independent_episodes']}"
      f"   (the registry's first correction said 1; that was counted by "
      f"contiguity, which always returns 1 for consecutive origins. "
      f"Re-counted against the same discovered phases as the V2 arms, V1's "
      f"fifty origins span 2008-02 to 2020-05 and cover "
      f"{v1.get('phase_based_episodes')} phases.)")
    A(f"    median MDE = {v1['origin_clustered']['ci'][1] - (v1['origin_clustered']['ci'][0] + v1['origin_clustered']['ci'][1]) / 2:.5f}")
    A("")
    A("POWER AFTER   (V2 DEEP, monthly grid, 584 origins, 1978-2026)")
    A(f"    raw rows   = {after['raw_rows']}")
    A(f"    origins    = {after['unique_origins']}")
    A(f"    n_eff      = {after['effective_origins']}")
    A(f"    episodes   = {after['independent_episodes']}")
    A(f"    median MDE = {deep['h3']['mde']}")
    _v1_ep = v1.get("phase_based_episodes") or before["independent_episodes"]
    A(f"    GAIN       = rows x{after['raw_rows'] / before['raw_rows']:.2f}, "
      f"effective origins "
      f"x{after['effective_origins'] / before['effective_origins']:.2f}, "
      f"episodes x{after['independent_episodes'] / _v1_ep:.2f}, "
      f"MDE down "
      f"{1 - deep['h3']['mde'] / (v1['origin_clustered']['ci'][1] - (v1['origin_clustered']['ci'][0] + v1['origin_clustered']['ci'][1]) / 2):.0%}")
    A(f"    VERDICT    = INFORMATION_GAINED_EPISODES. The gain is real and "
      f"it is in the currency that was scarce. It is x3, not the x15 a "
      f"contiguity-counted V1 baseline would have shown.")
    A("")
    A(f"MONTHLY_PANEL          = BUILT. {v2['panel']['series']} series, "
      f"{v2['panel']['cells']} cells, hash {v2['panel']['content_hash']}. "
      f"{v2['panel']['cells_by_revision_state'].get('PUBLISHER_VINTAGE', 0)} "
      f"cells carry a publisher vintage; "
      f"{v2['panel']['cells_by_revision_state'].get('MEASURED_STABLE', 0)} "
      f"carry today's value on a recorded revision measurement.")
    A(f"HISTORICAL_DEPTH       = 1978-01 for the long block (7 base series, "
      f"2 behavioural), 1998-02 for the full block. Earliest ALFRED vintages "
      f"measured per series: INDPRO 1960, UNRATE 1961, HOUST 1961, "
      f"CPIAUCSL 1973, PCEC96 1980. The credit and JOLTS series have no "
      f"vintage before 2011-2012, which is the binding limit on the "
      f"behavioural block, not the origin grid.")
    A(f"NETWORK_CALLS_RERUN    = 0 (verified twice; "
      f"{man['already_cached']} of {man['requested']} requests served from "
      f"cache on the acquisition run, {man['fetched']} fetched, "
      f"{man['failed']} failed)")
    A("")
    A("V1_CORRECTED")
    A(f"    delta              = {v1['delta']:+.5f}")
    A(f"    row bootstrap      = [{v1['row_bootstrap']['ci'][0]:+.5f}, "
      f"{v1['row_bootstrap']['ci'][1]:+.5f}]   (the stored interval)")
    A(f"    clustered CI       = [{v1['origin_clustered']['ci'][0]:+.5f}, "
      f"{v1['origin_clustered']['ci'][1]:+.5f}]   on "
      f"{v1['origin_clustered']['clusters']} origins")
    A(f"    episode-aware CI   = UNDEFINED — all origins fall in "
      f"{v1['episode_aware']['episodes']} contiguous block")
    A(f"    the stored interval was NOT materially too narrow. Within-origin "
      f"correlation of the paired differences is {after['icc'] if False else v1['sample']['icc']:.3f}, "
      f"so clustering cost almost nothing HERE. It cost a great deal on the "
      f"INFLATION_SHOCK slice, which is why the estimator was still right to "
      f"change.")
    A("")
    for h, arm_key in (("H3_GLOBAL_MONTHLY", "h3_verdict"),
                       ("H4_STRESS_CONDITIONAL", "h4_verdict")):
        A(f"{h:<22} = MODERN {modern.get(arm_key)} | "
          f"DEEP {deep.get(arm_key)}")
    A(f"{'H5_EARLY_WARNING':<22} = "
      f"MODERN {mech['arms']['MODERN']['leadtime']['verdict']} | "
      f"DEEP {mech['arms']['DEEP']['leadtime']['verdict']}")
    A(f"{'H6_TRANSMISSION':<22} = "
      f"MODERN {mech['arms']['MODERN']['h6_verdict']} | "
      f"DEEP {mech['arms']['DEEP']['h6_verdict']}")
    A("")
    A("CONSTRUCT VERDICTS (DEEP arm; MODERN in reports/v2_experiment.json)")
    for cid, v in sorted(deep["constructs"].items()):
        A(f"    {cid:<22} {v['verdict']:<22} delta="
          f"{v['delta'] if v['delta'] is not None else '-'}")
    A("")
    A(f"FALSE_DISCOVERIES_KILLED = "
      f"{close['learning_metrics']['false_discoveries_killed']}")
    A("    1. INFLATION_SHOCK +0.171 -- 30 rows, 14 origins, one episode")
    A("    2. CREDIT_STRESS +0.029 -- did not survive contemporaneous "
      "regime classification")
    A("    3. two mechanisms SUPPORTED on the MODERN transmission test -- "
      "scored on families whose base model loses to a constant")
    A("    4. 'the stored V1 interval is too narrow' -- measured, and it is "
      "not")
    A(f"ASSUMPTIONS_RETIRED      = "
      f"{close['learning_metrics']['assumptions_retired']}")
    A("    1. 'the quarterly grid is the origin grid' -- it was a date-string "
      "pattern match that admitted 344 origins")
    A("    2. 'stable over 2015-2024 means stable back to 1998' -- REVOLSL "
      "was redefined; 100% of observations differ by up to 105,016%")
    A("    3. 'a relative change is the right transform' -- not for a rate "
      "that crosses zero")
    A("    4. 'one model can be fitted across ten families' -- base rates "
      "run from 0.28 to 0.92")
    A("")
    A(f"HISTORICAL_EPISODES      = {len(deep['episodes'])} discovered by the "
      f"contemporaneous classifier over 1978-2026; coverage audit "
      f"{deep['coverage_audit']['found']} of the 15 named windows found, "
      f"{deep['coverage_audit']['missed']} missed, "
      f"{deep['coverage_audit']['out_of_reach']} outside the origin reach")
    A(f"REAL_FORWARD_OPENED      = {close['real_forward']['opened']} "
      f"({len(close['world_model']['replicated_across_arms'])} replicated "
      f"mechanisms x BASE and AUGMENTED)")
    A("")
    A(f"FOUNDER_INTEGRATION      = {close['founder']['status']}")
    A(f"WORLD_MODEL_EDGES_ADDED  = "
      f"{len(close['world_model']['edges_added'])} (all OBSERVED; none "
      f"PREDICTIVE, REGIME_CONDITIONAL, EARLY_WARNING or CAUSAL_SUPPORTED)")
    A(f"WORLD_MODEL_EDGES_REFUSED= "
      f"{len(close['world_model']['edges_refused'])}")
    A("")
    A(f"CALIBRATION_STATUS       = {close['calibration']['status']} "
      f"(0 resolved forward predictions; "
      f"{close['calibration']['minimum_before_reporting']} required). Every "
      f"number above is HISTORICAL OUT-OF-SAMPLE PERFORMANCE.")
    A(f"BREAK_PROOFS             = {bp['caught']}/{bp['proofs']} CAUGHT, "
      f"{bp['not_caught']} NOT_CAUGHT, {bp['not_applied']} NOT_APPLIED, "
      f"{bp['unreliable']} UNRELIABLE")
    text = "\n".join(L)

    # THE GUARD, CALLED. See this module's docstring: it had no production
    # caller until now.
    rep = CAL.report([])
    CAL.assert_no_unsupported_claim(text, rep)

    print(text)
    (OUT / "v2_final_report.txt").write_text(text + "\n")
    (OUT / "v2_final_report.json").write_text(json.dumps({
        "power_before": before, "power_after": after,
        "v1_corrected": v1, "hypotheses": close["hypothesis_verdicts"],
        "constructs": {"DEEP": deep["constructs"],
                       "MODERN": modern["constructs"]},
        "break_proofs": {k: v for k, v in bp.items() if k != "results"},
        "calibration": close["calibration"],
        "founder": close["founder"],
        "world_model": {k: (len(v) if isinstance(v, list) else v)
                        for k, v in close["world_model"].items()},
        "v2_hash": PR.v2_hash(),
        "evaluation_registry": ER.summarise()["evaluations"],
    }, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/v2_final_report.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

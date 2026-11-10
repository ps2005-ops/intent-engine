"""§29B: does a mortgage rate and a permits series make housing eligible?

WHY THIS IS A SEPARATE SCRIPT
-----------------------------
H7's base block is frozen in the preregistration hash. Adding MORTGAGE30US to
it would change `h7_hash` and invalidate a result that has already been
reported -- break proof 8's mutation. So the housing-baseline question is
asked on its own terms: does ANY conventional model of housing direction beat
a constant, now that the two variables a housing model obviously needs are
present?

The answer decides one thing only: whether `HOUST` stops being
BASELINE_INVALID. It does not reopen H7, and if the answer is no the target
stays invalid rather than being tuned until it wins.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import baselines as BS               # noqa: E402
from intent_engine.econ import blocked as BL                 # noqa: E402
from intent_engine.econ import episodes as EPI               # noqa: E402
from intent_engine.econ import experiment as EX              # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import power as PW                   # noqa: E402
from intent_engine.econ import regime as RG                  # noqa: E402

OUT = pathlib.Path("reports/housing_baseline.json")

#: The block a housing model should have had. Declared here, once, before the
#: ladder was run on it.
HOUSING_BLOCK = ("UNRATE", "CPIAUCSL", "DFF", "DGS2", "DGS10", "INDPRO",
                 "BAA", "T10Y3M", "MORTGAGE30US", "PERMIT", "HOUST")
BEFORE = ("UNRATE", "CPIAUCSL", "DFF", "DGS2", "DGS10", "HOUST", "INDPRO",
          "PCEC96")


def run(panel, manifest, arm_name, origins, block):
    readable = [s for s in block
                if panel.history(s, as_of=origins[0], lookback=2)
                and panel.history(s, as_of=origins[-1], lookback=2)]
    arm = EX.Arm(name=arm_name, origins=tuple(origins),
                 base_series=tuple(readable), behavioural_series=("UMCSENT",))
    readings = {r.as_of: r for r in RG.classify_many(panel, arm.origins)}
    eps = EPI.discover(list(readings.values()))
    phases = PW.phase_map(arm.origins, eps)
    rows, _sk = EX.build_target_rows(
        panel, arm, targets=("HOUST",), horizons=(180, 240),
        readings=readings, base_series=arm.base_series)
    names, _drop = EX.balanced_names(rows, arm.base_series)
    EX.assert_no_trending_levels(names)
    by_family = {}
    for r in rows:
        by_family.setdefault(r.target, []).append(r)
    out = {}
    for fid, frows in sorted(by_family.items()):
        folds = BL.make_folds(frows, folds=5, embargo_days=45)
        if not folds:
            continue
        BL.assert_folds_clean(folds)
        ladder = BS.score_ladder(folds, macro_prefixes=arm.base_series,
                                 ar_prefixes=("HOUST",),
                                 regime_prefixes=())
        g = BS.gate(ladder)
        s = PW.measure(origins=[r.origin for r in frows],
                       values=[1.0 if r.outcome else 0.0 for r in frows],
                       phase_of=phases)
        out[fid] = {"ladder": {k: v.as_dict() for k, v in ladder.items()},
                    "gate_passed": g.passed, "reason": g.reason,
                    "episodes": s.independent_episodes,
                    "features": len(names)}
    return out, readable


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    man = json.loads(pathlib.Path(
        "reports/panel/historical_acquisition_manifest.json").read_text())
    results = {}
    for arm_name, origins in (("MODERN", man["origins_modern"]),
                              ("DEEP", man["origins_deep"]
                               + man["origins_modern"])):
        print(f"\n=== {arm_name} ===")
        for label, block in (("BEFORE", BEFORE), ("WITH_HOUSING_BLOCK",
                                                  HOUSING_BLOCK)):
            res, readable = run(panel, man, arm_name, origins, block)
            results[f"{arm_name}/{label}"] = {"block": readable,
                                              "families": res}
            print(f"  {label} ({len(readable)} series readable)")
            print(f"    {'family':<14}{'const':>9}{'pers':>9}{'AR':>9}"
                  f"{'MACRO':>9}  gate")
            for fid, v in sorted(res.items()):
                L = v["ladder"]
                def b(n):
                    x = L.get(n)
                    return f"{x['brier']:.4f}" if x and x["n"] else "    -"
                print(f"    {fid:<14}{b('BASE_RATE'):>9}{b('PERSISTENCE'):>9}"
                      f"{b('AR'):>9}{b('MACRO'):>9}  "
                      f"{'PASS' if v['gate_passed'] else 'FAIL'}")
    passed = [k for k, v in results.items()
              if k.endswith("WITH_HOUSING_BLOCK")
              and any(f["gate_passed"] for f in v["families"].values())]
    verdict = ("HOUSING_NOW_ELIGIBLE" if passed else "BASELINE_INVALID")
    print(f"\n  §29B VERDICT = {verdict}")
    if not passed:
        print("    housing direction still does not beat a constant with a "
              "mortgage rate and permits in the model. The target stays "
              "BASELINE_INVALID; it is NOT tuned until it wins.")
    results["verdict"] = verdict
    results["note"] = (
        "H7's base block is frozen in its preregistration hash and was not "
        "touched. This asks only whether housing becomes an eligible target.")
    OUT.write_text(json.dumps(results, indent=2, sort_keys=True,
                              default=str))
    print(f"  wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

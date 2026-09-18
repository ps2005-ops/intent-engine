"""§4/§9/§16/§17: is the collective layer REGIME-CONDITIONAL?

The global test failed. This tests exactly one preregistered follow-up:
does the layer help in credit/liquidity stress and stay quiet in calm?

Both halves matter. A layer that helps in crisis AND in calm has not shown
regime dependence, it has shown a global effect the global test already
failed to find -- which is a reason to disbelieve the crisis number, not to
report two wins.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import baseline_registry as BR    # noqa: E402
from intent_engine.econ import forecast as FC             # noqa: E402
from intent_engine.econ import incremental as INC         # noqa: E402
from intent_engine.econ import panel as PN                # noqa: E402
from intent_engine.econ import preregistration as PR      # noqa: E402
from intent_engine.econ import regime as RG               # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from run_experiment import (                              # noqa: E402
    BASE_SERIES, TRAIN_END, VALIDATION_END, behavioural_series, build_rows,
    names_for,
)

PANEL = pathlib.Path("reports/panel/historical_panel.jsonl")
MANIFEST = pathlib.Path("reports/panel/historical_acquisition_manifest.json")
OUT = pathlib.Path("reports")
REGIME_HASH = "69c6732028a20679"


def main() -> int:
    h = PR.regime_hypothesis_hash()
    if h != REGIME_HASH:
        print(f"regime hypothesis changed: expected {REGIME_HASH}, now {h}")
        return 2
    hyp = PR.REGIME_HYPOTHESIS
    print(f"=== HYPOTHESIS {hyp['hypothesis_id']} (hash {h}) ===")
    print(f"  {hyp['statement']}")
    print(f"  primary regimes : {list(hyp['primary_regimes'])}")
    print(f"  negative control: {hyp['negative_control_regime']}")

    frozen = BR.load().get(hyp["comparator"])
    print(f"\n=== COMPARATOR ===\n  {frozen.statement()}")

    panel = PN.Panel.read(PANEL)
    origins = json.loads(MANIFEST.read_text())["origins"]
    beh = behavioural_series()
    rows, _skipped = build_rows(panel, origins, beh)

    # Regime labels, computed from the walled read at each origin.
    readings = {r.as_of: r for r in RG.classify_many(panel, origins)}
    rsum = RG.summarise(list(readings.values()))
    print(f"\n=== REGIMES === {rsum['confident']}/{rsum['origins']} "
          f"classified, {rsum['multi_regime_origins']} multi-regime")
    print(f"  {json.dumps(rsum['counts'])}")

    # Predictions once, then sliced by regime. Refitting per regime would
    # train on different data per slice and stop being one comparison.
    by_family = {}
    for r in rows:
        by_family.setdefault(r.target, []).append(r)

    preds = []          # (key, p_base, p_aug, outcome, origin, horizon)
    for fid, frows in sorted(by_family.items()):
        part = FC.split_by_date(frows, train_end=TRAIN_END,
                                validation_end=VALIDATION_END)
        pool = list(part.train) + list(part.validation)
        if len(pool) < FC.MIN_TRAIN_ROWS + 10:
            continue
        bn = names_for(pool, BASE_SERIES)
        an = names_for(pool, tuple(BASE_SERIES) + tuple(beh))
        bf = FC.walk_forward(pool, bn, folds=5)
        af = FC.walk_forward(pool, an, folds=5)
        if not bf or not af:
            continue
        bp = {k: p for f in bf for k, p, _y, _r in f.predictions}
        ap = {k: p for f in af for k, p, _y, _r in f.predictions}
        info = {r.key: r for r in frows}
        for k in sorted(set(bp) & set(ap)):
            r = info[k]
            preds.append((k, bp[k], ap[k], r.outcome, r.origin,
                          r.horizon_days, r.outcome_knowable_at))

    print(f"\n=== PAIRED PREDICTIONS === {len(preds)}")

    def compare_slice(name, keep):
        sel = [p for p in preds if keep(p)]
        if len(sel) < INC.MIN_PAIRED:
            return None, len(sel)
        # CLUSTER ON THE ORIGIN. Five targets at two horizons from one
        # origin share their features and overlap in their outcome windows;
        # counting them as ten independent observations is what made an
        # n=30 slice from 14 origins look decisive.
        b = [INC.Forecast(target_id=k, probability=pb,
                          information_cutoff=o, horizon_days=hz,
                          model="BASE", cluster=o)
             for k, pb, _pa, _y, o, hz, _ in sel]
        a = [INC.Forecast(target_id=k, probability=pa,
                          information_cutoff=o, horizon_days=hz,
                          model="BASE_PLUS_COLLECTIVE", cluster=o)
             for k, _pb, pa, _y, o, hz, _ in sel]
        o_ = [INC.Outcome(target_id=k, occurred=y, occurred_at=kn,
                          published_at=kn)
              for k, _pb, _pa, y, _o, _hz, kn in sel]
        return INC.compare(name=name, dimension="collective_block",
                           population="US_households", base=b, augmented=a,
                           outcomes=o_), len(sel)

    results, tests = {}, []
    print(f"\n=== BY REGIME ===")
    print(f"  {'regime':<24} {'n':>5} {'base':>8} {'aug':>8} {'delta':>9} "
          f"{'CI':>22} {'MDE':>8}  verdict")
    for reg in RG.REGIMES:
        c, n = compare_slice(
            reg, lambda p, reg=reg: reg in readings[p[4]].regimes)
        if c is None:
            results[reg] = {"n": n, "verdict": "INSUFFICIENT_SAMPLE"}
            continue
        tests.append(c)
        results[reg] = c.as_dict()
        print(f"  {reg:<24} {c.n_paired:>5} {c.base_score:>8.4f} "
              f"{c.augmented_score:>8.4f} {c.delta:>+9.5f} "
              f"[{c.ci_low:>+8.5f},{c.ci_high:>+8.5f}] {(c.mde or 0):>8.4f}  "
              f"{c.verdict}{' *underpowered' if c.underpowered else ''}")

    # The hypothesis: stressed pooled vs the calm negative control.
    stressed = set(hyp["primary_regimes"])
    calm = hyp["negative_control_regime"]
    c_stress, n_stress = compare_slice(
        "STRESSED_POOLED",
        lambda p: bool(stressed & set(readings[p[4]].regimes)))
    c_calm, n_calm = compare_slice(
        "CALM_CONTROL", lambda p: calm in readings[p[4]].regimes)
    if c_stress is not None:
        tests.append(c_stress)
    if c_calm is not None:
        tests.append(c_calm)

    adjusted = INC.adjust(tests)
    by_name = {c.name: c for c in adjusted}
    cs, cc = by_name.get("STRESSED_POOLED"), by_name.get("CALM_CONTROL")

    print(f"\n=== THE HYPOTHESIS TEST ===")
    for label, c, n in (("stressed (CREDIT|LIQUIDITY)", cs, n_stress),
                        ("calm (LOW_VOL_EXPANSION)", cc, n_calm)):
        if c is None:
            print(f"  {label:<30} n={n} — INSUFFICIENT_SAMPLE")
            continue
        print(f"  {label:<30} n={c.n_paired:<4} delta={c.delta:+.5f} "
              f"CI[{c.ci_low:+.5f},{c.ci_high:+.5f}] MDE={c.mde} "
              f"{c.verdict}{' *underpowered' if c.underpowered else ''}")

    # THE DECISION RULE, applied mechanically.
    if cs is None or cc is None:
        verdict, why = "INSUFFICIENT_DATA", "a slice fell below the floor"
    elif cs.ci_low > 0 and cc.ci_low <= 0:
        verdict, why = ("PROMOTE_REGIME_CONDITIONAL",
                        "stressed interval excludes zero; calm does not")
    elif cs.ci_low > 0 and cc.ci_low > 0:
        verdict, why = ("TESTED_NOT_PROMOTED",
                        "the layer shows value in CALM periods too, so this "
                        "is a global effect the global test already failed "
                        "to find — a reason to disbelieve the crisis number, "
                        "not to report two wins")
    elif cs.underpowered:
        verdict, why = ("INSUFFICIENT_DATA",
                        f"the stressed slice could only have resolved a "
                        f"delta of {cs.mde}; the observed {cs.delta:+.5f} is "
                        "inside that, so it was not measured either way")
    else:
        verdict, why = ("TESTED_NOT_PROMOTED",
                        "the stressed interval includes zero at a sample "
                        "size that could have resolved the effect")

    print(f"\n=== VERDICT === {verdict}")
    print(f"  {why}")
    print(f"  falsifier was: {hyp['falsifier'][:100]}...")

    payload = {"hypothesis": hyp, "hypothesis_hash": h,
               "comparator": frozen.as_dict(),
               "regimes": rsum, "by_regime": results,
               "stressed": cs.as_dict() if cs else {"n": n_stress},
               "calm": cc.as_dict() if cc else {"n": n_calm},
               "verdict": verdict, "why": why,
               "paired_predictions": len(preds)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "regime_conditional.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str))
    with open(OUT / "regime_readings.jsonl", "w", encoding="utf-8") as fh:
        for r in sorted(readings.values(), key=lambda x: x.as_of):
            fh.write(json.dumps(r.as_dict(), sort_keys=True) + "\n")
    print(f"\n  wrote reports/regime_conditional.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

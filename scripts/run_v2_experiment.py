"""§5/§9/§10/§11/§13/§14/§18/§19: the monthly run, and what it bought.

ORDER MATTERS AND IS ENFORCED
-----------------------------
    1. measure the power gain FIRST (§5). If monthly conversion produced
       rows and not information, everything downstream is the same
       experiment with a bigger n printed on it, and the report says so.
    2. discover the episodes (§7) from the contemporaneous classifier.
    3. climb the baseline ladder (§10). If the macro baseline loses to
       persistence, the augmented model is NOT scored -- Section 10's rule,
       applied rather than noted.
    4. only then H3 and H4.

The V2 hypotheses were hashed before this file produced a number, and
`assert_v2_unchanged` refuses to run against a declaration that moved.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import baselines as BS               # noqa: E402
from intent_engine.econ import blocked as BL                 # noqa: E402
from intent_engine.econ import construct as CK               # noqa: E402
from intent_engine.econ import episodes as EPI               # noqa: E402
from intent_engine.econ import evaluation_record as ER       # noqa: E402
from intent_engine.econ import experiment as EX              # noqa: E402
from intent_engine.econ import forecast as FC                # noqa: E402
from intent_engine.econ import incremental as INC            # noqa: E402
from intent_engine.econ import instrument_map as IM          # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import power as PW                   # noqa: E402
from intent_engine.econ import preregistration as PR         # noqa: E402
from intent_engine.econ import proxies as PX                 # noqa: E402
from intent_engine.econ import regime as RG                  # noqa: E402
from intent_engine.econ import series as SER                 # noqa: E402

PANEL = pathlib.Path("reports/panel/historical_panel.jsonl")
MANIFEST = pathlib.Path("reports/panel/historical_acquisition_manifest.json")
OUT = pathlib.Path("reports")

#: Frozen before the monthly panel produced a result.
V2_HASH = "d1e266aa7acfc67f"
PREREG_HASH = "4ae395b62fb60f85"

#: The quarterly grid V1 ran on, so the power comparison is like for like.
V1_MONTHS = (2, 5, 8, 11)

EMBARGO_DAYS = 45
FOLDS = 5


def series_by_construct() -> dict:
    """construct -> LIVE series behind it, from the instrument map."""
    live: dict = {}
    for spec in SER.BEHAVIOURAL:
        if spec.availability != SER.LIVE:
            continue
        if "superseded" in (spec.reason or "").lower():
            continue
        live.setdefault(spec.kind, []).append(spec.key)
    out = {}
    for row in IM.build():
        if not row.measurable:
            continue
        keys = sorted({k for p in PX.BY_DIMENSION.get(row.construct_id, ())
                       for k in live.get(p.kind, ())})
        if keys:
            out[row.construct_id] = tuple(keys)
    return out


def arms(panel, manifest) -> dict:
    """MODERN and DEEP, with each arm's readable block computed, not typed."""
    pol = manifest["policy"]
    usable = {sid: p for sid, p in pol.items() if p["mode"] != "EXCLUDED"}
    beh_all = tuple(sorted({k for keys in series_by_construct().values()
                            for k in keys}))
    # V3: the base block gains four financial-conditions controls. None of
    # them qualified as a BEHAVIOURAL proxy -- corporate credit spreads have
    # a rank correlation of +0.04 with household credit-card delinquency, so
    # they measure a different thing entirely -- but they are conventional
    # economic variables the base model should have had, and a stronger base
    # makes the collective test harder rather than easier.
    base_all = ("UNRATE", "CPIAUCSL", "DFF", "DGS2", "DGS10",
                "HOUST", "INDPRO", "PCEC96",
                "BAA", "BAA10Y", "AAA10Y", "T10Y3M")

    def readable_from(sid, origin):
        """Does this series have any walled value at `origin`?"""
        return bool(panel.history(sid, as_of=origin, lookback=2))

    modern = tuple(manifest["origins_modern"])
    deep_all = tuple(manifest["origins_deep"]) + modern

    def block(cands, origins):
        # A series is in an arm only if it is readable at the arm's FIRST
        # origin as well as its last. Anything else is a feature that starts
        # partway through and becomes a disguised date indicator.
        return tuple(s for s in cands
                     if s in usable and readable_from(s, origins[0])
                     and readable_from(s, origins[-1]))

    return {
        "MODERN": EX.Arm(
            name="MODERN", origins=modern,
            base_series=block(base_all, modern),
            behavioural_series=block(beh_all, modern),
            note="every series with a vintage record from 1998-02"),
        "DEEP": EX.Arm(
            name="DEEP", origins=deep_all,
            base_series=block(base_all, deep_all),
            behavioural_series=block(beh_all, deep_all),
            note=("1978-01 onward. A NARROWER behavioural block -- reported "
                  "as narrower -- bought for the only thing that was scarce: "
                  "separate economic episodes")),
    }


def paired_from_folds(rows, base_names, aug_names):
    """Fit both models PER FAMILY on blocked folds; return paired predictions.

    WHY PER FAMILY, AND WHAT POOLING COST
    -------------------------------------
    The first version of this file fitted ONE logistic across all ten
    (target x horizon) families at once. Those families have base rates from
    0.28 to 0.92 and no feature distinguishes them, so a single fit cannot
    represent them and lost to a per-fold constant everywhere. Measured:
    pooled MACRO Brier 0.25734 against a constant's 0.24435, and no value of
    the L2 penalty fixed it -- the in-sample Brier barely moved from 0.243 at
    any penalty, while out-of-sample degraded monotonically as the penalty
    fell. The model was not overfitting; it was misspecified.

    Fitted per family, the same block beats the per-family constant on
    labour (0.1817 vs 0.2258 at 180d, 0.1233 vs 0.2466 at 360d) and on
    industrial production at 360d (0.1944 vs 0.2532). That is a different
    experiment, and the pooled one was measuring the harness.
    """
    by_family = {}
    for r in rows:
        by_family.setdefault(r.target, []).append(r)
    out, all_folds = [], []
    for fid, frows in sorted(by_family.items()):
        folds = BL.make_folds(frows, folds=FOLDS, embargo_days=EMBARGO_DAYS)
        if not folds:
            continue
        BL.assert_folds_clean(folds)
        all_folds.extend(folds)
        for f in folds:
            if len(f.train) < FC.MIN_TRAIN_ROWS:
                continue
            bm = FC.fit(f.train, base_names)
            am = FC.fit(f.train, aug_names)
            for r in f.test:
                out.append((r.key, bm.predict(r), am.predict(r), r.outcome,
                            r.origin, r.horizon_days, r.outcome_knowable_at,
                            r.target, r.regime))
    return out, all_folds


def family_ladder(rows, arm, reg_names):
    """§10, PER FAMILY. Returns (per_family, gate_passing_families)."""
    by_family = {}
    for r in rows:
        by_family.setdefault(r.target, []).append(r)
    out, passing = {}, []
    for fid, frows in sorted(by_family.items()):
        folds = BL.make_folds(frows, folds=FOLDS, embargo_days=EMBARGO_DAYS)
        if not folds:
            continue
        target_series = PR.BY_ID[fid].target_series
        ladder = BS.score_ladder(
            folds, macro_prefixes=arm.base_series,
            ar_prefixes=(target_series,) if target_series in arm.base_series
                        else (),
            regime_prefixes=("REGIME",) if reg_names else ())
        g = BS.gate(ladder)
        out[fid] = {"ladder": {k: v.as_dict() for k, v in ladder.items()},
                    "gate": g.as_dict()}
        if g.passed:
            passing.append(fid)
    return out, passing


def compare_slice(name, sel, *, dimension="collective_block", blocks=None):
    if len(sel) < INC.MIN_PAIRED:
        return None
    b = [INC.Forecast(target_id=k, probability=pb, information_cutoff=o,
                      horizon_days=hz, model="BASE", cluster=o)
         for k, pb, _pa, _y, o, hz, _kn, _t, _rg in sel]
    a = [INC.Forecast(target_id=k, probability=pa, information_cutoff=o,
                      horizon_days=hz, model="BASE_PLUS_COLLECTIVE",
                      cluster=o)
         for k, _pb, pa, _y, o, hz, _kn, _t, _rg in sel]
    o_ = [INC.Outcome(target_id=k, occurred=y, occurred_at=kn,
                      published_at=kn)
          for k, _pb, _pa, y, _o, _hz, kn, _t, _rg in sel]
    return INC.compare(name=name, dimension=dimension,
                       population="US_households", base=b, augmented=a,
                       outcomes=o_, blocks=blocks)


def sample_of(sel, phases=None):
    diffs, origins, targets, horizons = [], [], [], []
    for k, pb, pa, y, o, hz, _kn, t, _rg in sel:
        yy = 1.0 if y else 0.0
        diffs.append((pb - yy) ** 2 - (pa - yy) ** 2)
        origins.append(o)
        targets.append(t)
        horizons.append(hz)
    return PW.measure(origins=origins, values=diffs, targets=targets,
                      horizons=horizons, phase_of=phases), diffs, origins


def main() -> int:
    t_start = time.time()
    PR.assert_unchanged(PREREG_HASH)
    PR.assert_v2_unchanged(V2_HASH)
    print(f"=== PREREGISTRATION === V1 {PR.declaration_hash()}  "
          f"V2 {PR.v2_hash()} — both unchanged")

    panel = PN.Panel.read(PANEL)
    ps = panel.summarise()
    print(f"=== PANEL === series={ps['series']} cells={ps['cells']} "
          f"hash={ps['content_hash']} span={ps['earliest']}..{ps['latest']}")
    print(f"  by revision state: {ps['cells_by_revision_state']}")

    manifest = json.loads(MANIFEST.read_text())
    A = arms(panel, manifest)
    for a in A.values():
        print(f"\n=== ARM {a.name} === {len(a.origins)} origins "
              f"{a.origins[0]}..{a.origins[-1]}")
        print(f"  base ({len(a.base_series)}): {list(a.base_series)}")
        print(f"  behavioural ({len(a.behavioural_series)}): "
              f"{list(a.behavioural_series)}")

    results = {"panel": ps, "v2_hash": PR.v2_hash(),
               "preregistration_hash": PR.declaration_hash(), "arms": {}}

    for arm in (A["MODERN"], A["DEEP"]):
        print(f"\n{'=' * 66}\n=== RUNNING {arm.name} ===\n{'=' * 66}")
        t0 = time.time()
        readings = {r.as_of: r for r in RG.classify_many(panel, arm.origins)}
        rsum = RG.summarise(list(readings.values()))
        print(f"  regimes: {rsum['confident']}/{rsum['origins']} classified, "
              f"{rsum['unclassifiable']} unclassifiable")
        print(f"    {json.dumps(rsum['counts'])}")

        eps = EPI.discover(list(readings.values()))
        audit = EPI.coverage_audit(eps, (arm.origins[0], arm.origins[-1]))
        print(f"  episodes discovered: {len(eps)}  "
              f"(coverage audit: {audit['found']} found, {audit['missed']} "
              f"missed, {audit['out_of_reach']} out of reach)")
        for e in eps:
            print(f"    {e.episode_id}  {e.start_as_known}..{e.end_as_known}"
                  f"  {e.origin_count:>3} origins  peak={e.peak_stress}  "
                  f"{','.join(e.regime_sequence)}")

        rows, skipped = EX.build_rows(panel, arm, readings=readings)
        print(f"  rows: {len(rows)}  skipped={skipped}")
        if len(rows) < FC.MIN_TRAIN_ROWS * 3:
            print("  too few rows for this arm")
            continue

        base_names, base_dropped = EX.balanced_names(rows, arm.base_series)
        beh_names, beh_dropped = EX.balanced_names(rows,
                                                   arm.behavioural_series)
        reg_names, _ = EX.balanced_names(rows, ("REGIME",))
        print(f"  balanced features: base {len(base_names)} "
              f"(dropped {len(base_dropped)}), behavioural {len(beh_names)} "
              f"(dropped {len(beh_dropped)})")
        if beh_dropped:
            print(f"    dropped for imbalance: {beh_dropped}")
        # The guards, called rather than intended. A mutation that
        # reintroduces a trending level or drops a live instrument turns the
        # run RED here instead of producing a plausible delta.
        EX.assert_no_trending_levels(base_names + beh_names)
        EX.assert_all_live_instruments_present(
            [n.rsplit("_", 1)[0] for n in beh_names],
            [s for s in arm.behavioural_series])
        if not beh_names:
            print("  no balanced behavioural feature; this arm cannot test "
                  "the block")
            continue
        aug_names = sorted(set(base_names) | set(beh_names))

        # ---------------- §10 BASELINE LADDER, PER FAMILY ---------------
        per_fam, passing = family_ladder(rows, arm, reg_names)
        print(f"\n  --- §10 BASELINE LADDER (per family) ---")
        print(f"    {'family':<22}{'const':>9}{'pers':>9}{'AR':>9}"
              f"{'MACRO':>9}{'REG+':>9}  gate")
        for fid, v in sorted(per_fam.items()):
            L = v["ladder"]
            def b(n):
                x = L.get(n)
                return f"{x['brier']:.4f}" if x and x["n"] else "    -"
            print(f"    {fid:<22}{b('BASE_RATE'):>9}{b('PERSISTENCE'):>9}"
                  f"{b('AR'):>9}{b('MACRO'):>9}{b('REGIME_MACRO'):>9}"
                  f"  {'PASS' if v['gate']['passed'] else 'FAIL'}")
        print(f"    families whose base model cleared every trivial rung: "
              f"{len(passing)}/{len(per_fam)}  {passing}")
        gate_passed = bool(passing)

        sel_all, _f = paired_from_folds(rows, base_names, aug_names)
        # §10: the augmented block is scored on the families whose BASE model
        # earned the right to be a comparator. The selection is made from
        # base-model performance alone and never touches the augmented
        # predictions, so it cannot select for the effect being tested.
        sel = [p for p in sel_all if p[7] in set(passing)]
        print(f"\n  paired predictions: {len(sel_all)} total, "
              f"{len(sel)} on gate-passing families")
        phases = PW.phase_map([p[4] for p in sel_all], eps)
        sample, diffs, origins = sample_of(sel or sel_all, phases)
        print(f"  SAMPLE  {sample.headline()}")
        print(f"    within-origin ICC {sample.icc:.3f}, origin "
              f"autocorrelation {sample.origin_autocorrelation:.3f}, "
              f"pseudo-replication x{sample.pseudo_replication_factor}")

        arm_res = {
            "arm": arm.as_dict(), "regimes": rsum,
            "episodes": [e.as_dict() for e in eps],
            "coverage_audit": audit,
            "rows": len(rows), "skipped": skipped,
            "features": {"base": base_names, "behavioural": beh_names,
                         "base_dropped": base_dropped,
                         "behavioural_dropped": beh_dropped},
            "baseline_ladder_per_family": per_fam,
            "baseline_gate_passing_families": passing,
            "baseline_gate_passed": gate_passed,
            "sample": sample.as_dict(),
            "paired_all_families": len(sel_all),
            "paired_scored": len(sel),
            "elapsed_seconds": round(time.time() - t0, 1),
        }

        # ---------------- §13 H3 GLOBAL --------------------------------
        glob = compare_slice("H3_GLOBAL", sel, blocks=phases)
        glob_all = compare_slice("H3_GLOBAL_ALL_FAMILIES", sel_all,
                                 blocks=phases)
        if glob is not None:
            print(f"\n  --- §13 H3_GLOBAL_MONTHLY ---")
            print(f"    delta {glob.delta:+.5f}  clustered CI "
                  f"[{glob.ci_low:+.5f}, {glob.ci_high:+.5f}]  "
                  f"MDE {glob.mde}")
            ep_ci = ("UNDEFINED" if glob.episode_ci_low is None else
                     f"[{glob.episode_ci_low:+.5f}, "
                     f"{glob.episode_ci_high:+.5f}]")
            print(f"    episode-aware CI {ep_ci}  "
                  f"({glob.n_episodes} episodes)")
            _lo, _hi, _mde, which = deciding_interval(glob)
            print(f"    verdict {glob.verdict}"
                  f"{'  UNDERPOWERED' if glob.underpowered else ''}"
                  f"   [decided on the {which} interval, MDE {_mde:.5f}]")
            INC.assert_clusters_are_origins(glob)
            INC.assert_not_promoted_underpowered(glob)
            arm_res["h3"] = glob.as_dict()
            arm_res["h3_all_families"] = (glob_all.as_dict() if glob_all
                                          else None)
            arm_res["h3_verdict"] = h3_verdict(glob, gate_passed,
                                               sample.independent_episodes)
            print(f"    H3 => {arm_res['h3_verdict']}")

        # ---------------- §14 H4 REGIME-CONDITIONAL --------------------
        print(f"\n  --- §14 H4_STRESS_CONDITIONAL ---")
        print(f"    {'regime':<22}{'rows':>6}{'orig':>6}{'eff':>7}{'ep':>4}"
              f"{'delta':>10}{'MDE':>9}  verdict")
        by_regime, regime_tests = {}, []
        for reg in RG.REGIMES:
            s = [p for p in (sel or sel_all)
                 if reg in readings[p[4]].regimes]
            c = compare_slice(reg, s, blocks=phases)
            samp, _d, _o = sample_of(s, phases) if s else (None, [], [])
            if c is None:
                by_regime[reg] = {"verdict": "INSUFFICIENT_SAMPLE",
                                  "sample": samp.as_dict() if samp else None}
                continue
            regime_tests.append(c)
            by_regime[reg] = {**c.as_dict(), "sample": samp.as_dict()}
            print(f"    {reg:<22}{samp.raw_rows:>6}{samp.unique_origins:>6}"
                  f"{samp.effective_origins:>7.1f}"
                  f"{samp.independent_episodes:>4}{c.delta:>+10.5f}"
                  f"{(c.mde or 0):>9.4f}  {regime_verdict(c, samp)}")
        scored = sel or sel_all
        stressed = [p for p in scored
                    if {"CREDIT_STRESS", "LIQUIDITY_STRESS",
                        "INFLATION_SHOCK", "LABOUR_DETERIORATION"}
                    & set(readings[p[4]].regimes)]
        calm = [p for p in scored
                if RG.NEGATIVE_CONTROL in readings[p[4]].regimes]
        cs = compare_slice("STRESSED", stressed, blocks=phases)
        cc = compare_slice("CALM", calm, blocks=phases)
        s_samp = sample_of(stressed, phases)[0] if stressed else None
        c_samp = sample_of(calm, phases)[0] if calm else None
        arm_res["by_regime"] = by_regime
        arm_res["h4"] = {
            "stressed": (cs.as_dict() if cs else None),
            "stressed_sample": s_samp.as_dict() if s_samp else None,
            "calm": (cc.as_dict() if cc else None),
            "calm_sample": c_samp.as_dict() if c_samp else None,
        }
        arm_res["h4_verdict"] = h4_verdict(cs, s_samp, cc, c_samp,
                                           gate_passed)
        for lbl, c, sm in (("stressed", cs, s_samp), ("calm", cc, c_samp)):
            if c is None:
                print(f"    {lbl:<10} INSUFFICIENT_SAMPLE")
            else:
                print(f"    {lbl:<10} {sm.headline()}  delta {c.delta:+.5f} "
                      f"CI[{c.ci_low:+.5f},{c.ci_high:+.5f}] MDE {c.mde}")
        print(f"    H4 => {arm_res['h4_verdict']}")

        # ---------------- §18 PER-CONSTRUCT ----------------------------
        arm_res["constructs"] = per_construct(rows, base_names, passing,
                                              phases)
        print(f"\n  --- §18 CONSTRUCTS ---")
        for cid, v in sorted(arm_res["constructs"].items()):
            print(f"    {cid:<22} {v['verdict']:<22} delta="
                  f"{v['delta']}  {v['sample']}")

        results["arms"][arm.name] = arm_res
        # Store the paired sample so §15/§16 can read it without refitting.
        (OUT / f"v2_paired_{arm.name.lower()}.jsonl").write_text(
            "\n".join(json.dumps({
                "key": k, "p_base": pb, "p_aug": pa, "y": y, "origin": o,
                "horizon": hz, "knowable": kn, "family": t, "regime": rg,
                "gate_passed": t in set(passing)},
                sort_keys=True)
                for k, pb, pa, y, o, hz, kn, t, rg in sel_all))

    # ---------------- §5 POWER, MEASURED ------------------------------
    results["power"] = power_report(results)
    print(f"\n{'=' * 66}\n=== §5 POWER ===\n{'=' * 66}")
    for k, v in results["power"].items():
        if isinstance(v, dict) and "statement" in v:
            print(f"  {k}: {v['statement']}")

    results["elapsed_seconds"] = round(time.time() - t_start, 1)
    (OUT / "v2_experiment.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/v2_experiment.json "
          f"({results['elapsed_seconds']}s)")
    return 0


#: The number H3's falsifier names: the largest improvement V1's interval
#: still admitted. A sample that could resolve an effect this size and finds
#: none has falsified H3; one that could not has measured nothing.
V1_ADMITS_UP_TO = 0.00661


def deciding_interval(c):
    """(lo, hi, mde, which) -- the EPISODE-AWARE interval when it exists.

    §8 requires bootstrapping at the appropriate dependence unit, and the
    coarsest real unit here is the macroeconomic phase. The two intervals
    disagree in exactly the way that matters: on the DEEP arm the
    origin-clustered interval is [-0.01245, -0.00374] and excludes zero,
    while the episode-aware one is [-0.02444, +0.00619] and does not. Taking
    the clustered interval as the headline would report a resolved negative
    effect that fifteen episodes do not support.
    """
    if c.episode_ci_low is not None:
        return (c.episode_ci_low, c.episode_ci_high,
                (c.episode_ci_high - c.episode_ci_low) / 2.0, "EPISODE_AWARE")
    return c.ci_low, c.ci_high, c.mde, "ORIGIN_CLUSTERED"


def h3_verdict(c, gate_passed, n_phases) -> str:
    """§11's decision rule for H3, applied mechanically."""
    if not gate_passed:
        return "NOT_SCORED_BASELINE_GATE_FAILED"
    if n_phases < INC.MIN_EPISODES:
        return "INSUFFICIENT_EPISODES"
    lo, _hi, mde, _which = deciding_interval(c)
    if lo > 0:
        return "SUPPORTED"
    if mde is not None and mde < V1_ADMITS_UP_TO:
        return "NOT_SUPPORTED"
    return "INSUFFICIENT_POWER"


def regime_verdict(c, sample) -> str:
    if c is None:
        return "INSUFFICIENT_SAMPLE"
    if sample.independent_episodes < INC.MIN_EPISODES:
        return "INSUFFICIENT_EPISODES"
    lo, _hi, mde, _which = deciding_interval(c)
    if lo > 0:
        return "SUPPORTED"
    if mde is not None and abs(c.delta) < mde:
        return "INSUFFICIENT_POWER"
    return "NOT_SUPPORTED"


def h4_verdict(cs, s_samp, cc, c_samp, gate_passed) -> str:
    if not gate_passed:
        return "NOT_SCORED_BASELINE_GATE_FAILED"
    if cs is None or cc is None:
        return "INSUFFICIENT_SAMPLE"
    if s_samp.independent_episodes < INC.MIN_EPISODES:
        return "INSUFFICIENT_EPISODES"
    s_lo, _sh, s_mde, _w = deciding_interval(cs)
    c_lo, _ch, _cm, _w2 = deciding_interval(cc)
    if s_lo > 0 and c_lo <= 0:
        return "PROMOTE_REGIME_CONDITIONAL"
    if s_lo > 0 and c_lo > 0:
        return "TESTED_NOT_PROMOTED_GLOBAL_EFFECT"
    if s_mde is not None and abs(cs.delta) < s_mde:
        return "INSUFFICIENT_POWER"
    return "NOT_SUPPORTED"


def per_construct(rows, base_names, passing, phases) -> dict:
    """Each construct on its own, over the same rows, folds and gate."""
    out = {}
    by_construct = series_by_construct()
    for cid, keys in sorted(by_construct.items()):
        names, _dropped = EX.balanced_names(rows, keys)
        if not names:
            out[cid] = {"verdict": "INSUFFICIENT_DATA", "delta": None,
                        "sample": "no balanced feature in this arm",
                        "series": list(keys)}
            continue
        aug = sorted(set(base_names) | set(names))
        if set(aug) == set(base_names):
            out[cid] = {"verdict": "INSUFFICIENT_DATA", "delta": None,
                        "sample": "adds no column", "series": list(keys)}
            continue
        s_all, _f = paired_from_folds(rows, base_names, aug)
        s = [p for p in s_all if p[7] in set(passing)] or s_all
        c = compare_slice(cid, s, dimension=cid, blocks=phases)
        samp = sample_of(s, phases)[0] if s else None
        if c is None or samp is None:
            out[cid] = {"verdict": "INSUFFICIENT_DATA", "delta": None,
                        "sample": "below the paired floor",
                        "series": list(keys)}
            continue
        out[cid] = {"verdict": regime_verdict(c, samp),
                    "delta": c.delta, "ci": [c.ci_low, c.ci_high],
                    "mde": c.mde, "sample": samp.headline(),
                    "sample_detail": samp.as_dict(),
                    "features": names, "series": list(keys)}
    return out


def power_report(results: dict) -> dict:
    """§5, from the arms that actually ran."""
    out = {}
    modern = results["arms"].get("MODERN")
    deep = results["arms"].get("DEEP")
    v1 = json.loads(pathlib.Path("reports/v1_reevaluation.json").read_text())
    before = PW.Sample(
        raw_rows=v1["sample"]["raw_rows"],
        unique_origins=v1["sample"]["unique_origins"],
        effective_origins=v1["sample"]["effective_origins"],
        independent_episodes=v1["sample"]["independent_episodes"],
        icc=v1["sample"]["icc"],
        origin_autocorrelation=v1["sample"]["origin_autocorrelation"])
    for name, arm in (("MONTHLY_VS_QUARTERLY", modern),
                      ("DEEP_VS_QUARTERLY", deep)):
        if not arm or "sample" not in arm:
            continue
        s = arm["sample"]
        after = PW.Sample(
            raw_rows=s["raw_rows"], unique_origins=s["unique_origins"],
            effective_origins=s["effective_origins"],
            independent_episodes=s["independent_episodes"],
            icc=s["icc"],
            origin_autocorrelation=s["origin_autocorrelation"])
        d = PW.PowerDelta(
            before=before, after=after,
            median_mde_before=v1["origin_clustered"]["ci"][1]
            - (v1["origin_clustered"]["ci"][0]
               + v1["origin_clustered"]["ci"][1]) / 2,
            median_mde_after=(arm.get("h3") or {}).get("mde"))
        out[name] = d.as_dict()
    return out


if __name__ == "__main__":
    raise SystemExit(main())

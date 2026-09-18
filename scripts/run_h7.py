"""§6/§8/§9/§10/§11/§12: does the sentiment lead contain anything usable?

THE ONE QUESTION THIS RUN EXISTS TO SETTLE
------------------------------------------
Consumer sentiment leads housing starts by 6-8 months and industrial
production by 7-8 months. Measured twice, on walled data, in two independent
arms. That is a real temporal fact and it is compatible with sentiment being
completely useless, because the lead can be entirely carried by variables the
economic block already has.

So the test is not "does sentiment lead". It is "does sentiment add anything
AFTER the economic model has spoken". Three ways it could:

    FORECAST        a better probability at the horizon
    EARLY WARNING   the same probability, sooner, without more false alarms
    NEITHER         LEADING_BUT_REDUNDANT

ORDER IS ENFORCED
-----------------
Eligibility first (§12): a family whose base model loses to a constant cannot
carry a verdict about sentiment. Then the incremental test on eligible
families only. Then lead time. Then stability across episode classes. A
result from a family that failed the gate is not reported as a weaker result;
it is not reported.
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
from intent_engine.econ import episodes as EPI               # noqa: E402
from intent_engine.econ import experiment as EX              # noqa: E402
from intent_engine.econ import forecast as FC                # noqa: E402
from intent_engine.econ import incremental as INC            # noqa: E402
from intent_engine.econ import leadtime as LT                # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import power as PW                   # noqa: E402
from intent_engine.econ import preregistration as PR         # noqa: E402
from intent_engine.econ import regime as RG                  # noqa: E402

PANEL = pathlib.Path("reports/panel/historical_panel.jsonl")
MANIFEST = pathlib.Path("reports/panel/historical_acquisition_manifest.json")
OUT = pathlib.Path("reports")

H7_HASH = "3a5c4d36259e08a2"
FOLDS, EMBARGO = 5, 45

#: §9's episode classes. Assigned from the CONTEMPORANEOUS regime sequence an
#: episode was discovered with -- never from what we remember the period being.
EPISODE_CLASSES = (
    ("inflationary_recession", ("INFLATION_SHOCK", "LABOUR_DETERIORATION")),
    ("credit_crisis", ("CREDIT_STRESS",)),
    ("ordinary_slowdown", ("LABOUR_DETERIORATION",)),
    ("liquidity_squeeze", ("LIQUIDITY_STRESS",)),
    ("inflation_only", ("INFLATION_SHOCK",)),
)


def classify_episode(e) -> str:
    seq = set(e.regime_sequence)
    for name, need in EPISODE_CLASSES:
        if set(need) <= seq:
            return name
    return "unclassified"


def arms(panel, manifest):
    pol = manifest["policy"]
    usable = {s for s, p in pol.items() if p["mode"] != "EXCLUDED"}
    base_all = tuple(PR.H7["base_block"])

    def readable(sid, o):
        return bool(panel.history(sid, as_of=o, lookback=2))

    def block(cands, origins):
        return tuple(s for s in cands if s in usable
                     and readable(s, origins[0]) and readable(s, origins[-1]))

    modern = tuple(manifest["origins_modern"])
    deep = tuple(manifest["origins_deep"]) + modern
    return {
        "MODERN": EX.Arm(name="MODERN", origins=modern,
                         base_series=block(base_all, modern),
                         behavioural_series=("UMCSENT",),
                         note="1998-02 onward"),
        "DEEP": EX.Arm(name="DEEP", origins=deep,
                       base_series=block(base_all, deep),
                       behavioural_series=("UMCSENT",),
                       note="1978-01 onward"),
    }


def paired(rows, base_names, aug_names):
    by_family = {}
    for r in rows:
        by_family.setdefault(r.target, []).append(r)
    out, folds_all = [], {}
    for fid, frows in sorted(by_family.items()):
        folds = BL.make_folds(frows, folds=FOLDS, embargo_days=EMBARGO)
        if not folds:
            continue
        BL.assert_folds_clean(folds)
        folds_all[fid] = folds
        for f in folds:
            if len(f.train) < FC.MIN_TRAIN_ROWS:
                continue
            bm = FC.fit(f.train, base_names)
            am = FC.fit(f.train, aug_names)
            for r in f.test:
                out.append((r.key, bm.predict(r), am.predict(r), r.outcome,
                            r.origin, r.horizon_days, r.outcome_knowable_at,
                            r.target, r.regime))
    return out, folds_all


def sample_of(sel, phases=None):
    diffs, origins, targets, horizons = [], [], [], []
    for _k, pb, pa, y, o, hz, _kn, t, _rg in sel:
        yy = 1.0 if y else 0.0
        diffs.append((pb - yy) ** 2 - (pa - yy) ** 2)
        origins.append(o); targets.append(t); horizons.append(hz)
    return PW.measure(origins=origins, values=diffs, targets=targets,
                      horizons=horizons, phase_of=phases), diffs


def compare(name, sel, blocks=None, dimension="sentiment"):
    if len(sel) < INC.MIN_PAIRED:
        return None
    b = [INC.Forecast(target_id=k, probability=pb, information_cutoff=o,
                      horizon_days=hz, model="BASE", cluster=o)
         for k, pb, _pa, _y, o, hz, _kn, _t, _rg in sel]
    a = [INC.Forecast(target_id=k, probability=pa, information_cutoff=o,
                      horizon_days=hz, model="BASE_PLUS_SENTIMENT", cluster=o)
         for k, _pb, pa, _y, o, hz, _kn, _t, _rg in sel]
    o_ = [INC.Outcome(target_id=k, occurred=y, occurred_at=kn,
                      published_at=kn)
          for k, _pb, _pa, y, _o, _hz, kn, _t, _rg in sel]
    return INC.compare(name=name, dimension=dimension,
                       population="US_households", base=b, augmented=a,
                       outcomes=o_, blocks=blocks)


def eligibility(rows, arm, phases) -> dict:
    """§11/§12: the ladder per family, and what it permits."""
    by_family = {}
    for r in rows:
        by_family.setdefault(r.target, []).append(r)
    out = {}
    for fid, frows in sorted(by_family.items()):
        folds = BL.make_folds(frows, folds=FOLDS, embargo_days=EMBARGO)
        if not folds:
            continue
        target_series = fid.rsplit("_", 1)[0]
        ladder = BS.score_ladder(
            folds, macro_prefixes=arm.base_series,
            ar_prefixes=(target_series,) if target_series in arm.base_series
                        else (),
            regime_prefixes=("REGIME",))
        g = BS.gate(ladder)
        origins = [r.origin for r in frows]
        s = PW.measure(origins=origins,
                       values=[1.0 if r.outcome else 0.0 for r in frows],
                       phase_of=phases)
        el = EX.TargetEligibility(
            target_id=fid, base_rate=FC.base_rate(frows),
            usable_origins=s.unique_origins,
            effective_origins=s.effective_origins,
            episodes=s.independent_episodes,
            baseline_clear=g.passed, baseline_reason=g.reason)
        out[fid] = {"eligibility": el.as_dict(),
                    "ladder": {k: v.as_dict() for k, v in ladder.items()}}
    return out


def main() -> int:
    t0 = time.time()
    PR.assert_h7_unchanged(H7_HASH)
    PR.assert_unchanged("4ae395b62fb60f85")
    PR.assert_v2_unchanged("d1e266aa7acfc67f")
    print(f"=== PREREGISTRATION === H7 {PR.h7_hash()} — unchanged")
    print(f"  {PR.H7['statement'][:100]}...")

    panel = PN.Panel.read(PANEL)
    ps = panel.summarise()
    manifest = json.loads(MANIFEST.read_text())
    print(f"=== PANEL V3 === series={ps['series']} cells={ps['cells']} "
          f"hash={ps['content_hash']}")

    A = arms(panel, manifest)
    results = {"h7_hash": PR.h7_hash(), "panel": ps, "arms": {}}

    for arm in (A["MODERN"], A["DEEP"]):
        print(f"\n{'=' * 70}\n=== {arm.name} === {len(arm.origins)} origins "
              f"{arm.origins[0]}..{arm.origins[-1]}\n{'=' * 70}")
        print(f"  base ({len(arm.base_series)}): {list(arm.base_series)}")
        readings = {r.as_of: r for r in RG.classify_many(panel, arm.origins)}
        eps = EPI.discover(list(readings.values()))
        phases = PW.phase_map(arm.origins, eps)
        print(f"  episodes: {len(eps)}  phases: {len(set(phases.values()))}")

        rows, skipped = EX.build_target_rows(
            panel, arm, targets=PR.H7["targets"],
            horizons=PR.H7["horizons"], readings=readings,
            base_series=arm.base_series,
            extra_series=PR.H7["feature_added"])
        print(f"  rows: {len(rows)}  skipped={skipped}")
        base_names, bdrop = EX.balanced_names(rows, arm.base_series)
        sent_names, sdrop = EX.balanced_names(rows, PR.H7["feature_added"])
        EX.assert_no_trending_levels(base_names + sent_names)
        if not sent_names:
            print("  sentiment has no balanced feature in this arm")
            continue
        aug_names = sorted(set(base_names) | set(sent_names))
        print(f"  features: base {len(base_names)} (dropped {len(bdrop)}), "
              f"sentiment {sent_names}")

        # ------------- §11/§12 ELIGIBILITY -------------------------------
        elig = eligibility(rows, arm, phases)
        eligible = [f for f, v in elig.items()
                    if v["eligibility"]["eligible_for_human_test"]]
        print(f"\n  --- §12 TARGET ELIGIBILITY ---")
        print(f"    {'family':<16}{'rate':>6}{'orig':>6}{'eff':>7}{'ep':>4}"
              f"  baseline  eligible")
        for fid, v in sorted(elig.items()):
            e = v["eligibility"]
            print(f"    {fid:<16}{e['base_rate']:>6.2f}"
                  f"{e['usable_origins']:>6}{e['effective_origins']:>7.1f}"
                  f"{e['episodes']:>4}  "
                  f"{'PASS' if e['baseline_clear'] else 'FAIL':<8}  "
                  f"{'YES' if e['eligible_for_human_test'] else e['why_not'][:34]}")

        sel_all, folds = paired(rows, base_names, aug_names)
        sel = [p for p in sel_all if p[7] in set(eligible)]
        print(f"\n  paired: {len(sel_all)} total, {len(sel)} on eligible "
              f"families")
        arm_res = {"arm": arm.as_dict(), "episodes": [e.as_dict() for e in eps],
                   "eligibility": elig, "eligible": eligible,
                   "features": {"base": base_names, "sentiment": sent_names},
                   "rows": len(rows), "skipped": skipped,
                   "paired_all": len(sel_all), "paired_scored": len(sel)}

        if not sel:
            arm_res["h7_verdict"] = "NOT_SCORED_NO_ELIGIBLE_TARGET"
            print(f"  H7 => NOT_SCORED_NO_ELIGIBLE_TARGET")
            results["arms"][arm.name] = arm_res
            continue

        # ------------- §8 INCREMENTAL VALUE ------------------------------
        s, _d = sample_of(sel, phases)
        c = compare("H7_INCREMENTAL", sel, blocks=phases)
        print(f"\n  --- §8 INCREMENTAL VALUE ---")
        print(f"    SAMPLE {s.headline()}")
        ep_ci = ("UNDEFINED" if c.episode_ci_low is None else
                 f"[{c.episode_ci_low:+.5f}, {c.episode_ci_high:+.5f}]")
        print(f"    delta {c.delta:+.5f}  clustered "
              f"[{c.ci_low:+.5f}, {c.ci_high:+.5f}]  MDE {c.mde}")
        print(f"    episode-aware {ep_ci}  ({c.n_episodes} episodes)")
        arm_res["incremental"] = {**c.as_dict(), "sample": s.as_dict()}

        # per family
        print(f"    {'family':<16}{'n':>5}{'delta':>10}{'MDE':>9}  verdict")
        per_fam = {}
        for fid in sorted(eligible):
            fs = [p for p in sel if p[7] == fid]
            fc = compare(fid, fs, blocks=phases)
            fsamp, _ = sample_of(fs, phases)
            if fc is None:
                per_fam[fid] = {"verdict": "INSUFFICIENT_SAMPLE"}
                continue
            per_fam[fid] = {**fc.as_dict(), "sample": fsamp.as_dict()}
            lo, _hi, mde, _w = deciding(fc)
            print(f"    {fid:<16}{fc.n_paired:>5}{fc.delta:>+10.5f}"
                  f"{(mde or 0):>9.5f}  {slice_verdict(fc, fsamp)}")
        arm_res["per_family"] = per_fam

        # ------------- §15 LEAD TIME -------------------------------------
        print(f"\n  --- §8/§15 LEAD TIME ---")
        lead = {}
        for fid in sorted(eligible):
            fs = [p for p in sel if p[7] == fid]
            if len(fs) < 20:
                continue
            # DETERIORATION is the target FALLING, so the warning probability
            # is 1 - P(rise). Getting this backwards would score the model
            # for predicting booms and call it an early warning.
            b = sorted((p[4], 1.0 - p[1]) for p in fs)
            a = sorted((p[4], 1.0 - p[2]) for p in fs)
            for mode in ("RAW", "ALARM_MATCHED"):
                r = LT.compare(base=b, augmented=a, episodes=eps, mode=mode)
                lead[f"{fid}/{mode}"] = r.as_dict()
                print(f"    {fid:<16} {r.statement()[:120]}")
        arm_res["lead_time"] = lead

        # ------------- §9 EPISODE STABILITY ------------------------------
        print(f"\n  --- §9 EPISODE STABILITY ---")
        by_class = {}
        for e in eps:
            cls = classify_episode(e)
            fs = [p for p in sel
                  if e.start_as_known <= p[4] <= e.end_as_known]
            if not fs:
                continue
            d = by_class.setdefault(cls, {"episodes": [], "sel": []})
            d["episodes"].append(e.episode_id)
            d["sel"].extend(fs)
        stability = {}
        print(f"    {'class':<24}{'eps':>4}{'n':>6}{'delta':>10}  sign")
        for cls, d in sorted(by_class.items()):
            fs = d["sel"]
            diffs = []
            for _k, pb, pa, y, _o, _hz, _kn, _t, _rg in fs:
                yy = 1.0 if y else 0.0
                diffs.append((pb - yy) ** 2 - (pa - yy) ** 2)
            delta = sum(diffs) / len(diffs) if diffs else 0.0
            stability[cls] = {"episodes": d["episodes"], "n": len(fs),
                              "delta": round(delta, 5),
                              "sign": "+" if delta > 0 else "-"}
            print(f"    {cls:<24}{len(d['episodes']):>4}{len(fs):>6}"
                  f"{delta:>+10.5f}  {'+' if delta > 0 else '-'}")
        signs = {v["sign"] for v in stability.values()}
        arm_res["episode_stability"] = {
            "by_class": stability,
            "classification": ("STABLE" if len(signs) == 1 and len(stability) >= 3
                               else ("REGIME_DEPENDENT" if len(stability) >= 3
                                     else "UNMEASURED")),
            "why": ("the sign of the incremental delta is the same in every "
                    "episode class" if len(signs) == 1 else
                    "the sign flips between episode classes, so this is not "
                    "one stable mechanism")}
        print(f"    => {arm_res['episode_stability']['classification']}")

        arm_res["h7_verdict"] = h7_verdict(c, s, lead)
        print(f"\n  H7 => {arm_res['h7_verdict']}")
        results["arms"][arm.name] = arm_res
        (OUT / f"h7_paired_{arm.name.lower()}.jsonl").write_text(
            "\n".join(json.dumps({
                "key": k, "p_base": pb, "p_aug": pa, "y": y, "origin": o,
                "horizon": hz, "knowable": kn, "family": t, "regime": rg,
                "eligible": t in set(eligible)}, sort_keys=True)
                for k, pb, pa, y, o, hz, kn, t, rg in sel_all))

    results["elapsed_seconds"] = round(time.time() - t0, 1)
    results["code_sha"] = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True).stdout.strip()
    (OUT / "h7_experiment.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/h7_experiment.json "
          f"({results['elapsed_seconds']}s)")
    return 0


def deciding(c):
    if c.episode_ci_low is not None:
        return (c.episode_ci_low, c.episode_ci_high,
                (c.episode_ci_high - c.episode_ci_low) / 2.0, "EPISODE_AWARE")
    return c.ci_low, c.ci_high, c.mde, "ORIGIN_CLUSTERED"


def slice_verdict(c, sample) -> str:
    if c is None:
        return "INSUFFICIENT_SAMPLE"
    if sample.independent_episodes < INC.MIN_EPISODES:
        return "INSUFFICIENT_EPISODES"
    lo, _hi, mde, _w = deciding(c)
    if lo > 0:
        return "SUPPORTED"
    if mde is not None and abs(c.delta) < mde:
        return "INSUFFICIENT_POWER"
    return "NOT_SUPPORTED"


def h7_verdict(c, sample, lead) -> str:
    """§7's decision rule, applied mechanically and in its declared order."""
    if sample.independent_episodes < PR.H7["episode_floor"]:
        return "INSUFFICIENT_EPISODES"
    lo, _hi, mde, _which = deciding(c)
    if lo > 0:
        return "PROMOTE_GLOBAL_FORECAST"
    # The alarm-matched lead time is the ONLY lead-time result that counts.
    matched = [v for k, v in lead.items() if k.endswith("ALARM_MATCHED")]
    good = [v for v in matched
            if v.get("lead_delta_days") is not None
            and v["lead_delta_days"] > 0
            and v["false_alarms_augmented"] <= v["false_alarms_base"]
            and v["episodes"] >= PR.H7["episode_floor"]]
    if good:
        return "PROMOTE_EARLY_WARNING"
    if mde is not None and abs(c.delta) < mde:
        return "INSUFFICIENT_POWER"
    # The temporal order held and neither metric cleared.
    return "LEADING_BUT_REDUNDANT"


if __name__ == "__main__":
    raise SystemExit(main())

"""§8-§13: base economics vs base + collective state, on the real panel.

ONE HARNESS, TWO FEATURE BLOCKS
-------------------------------
Same origins, same targets, same folds, same penalty, same fit. The only
difference is which columns go in. Anything else handled separately is a
place the comparison quietly becomes a comparison of two harnesses.

WHAT COMES OUT
    reports/base_forecasts.jsonl
    reports/augmented_forecasts.jsonl
    reports/model_comparison.json
    reports/promotion_ledger.jsonl

THE PREREGISTRATION IS CHECKED, NOT TRUSTED
-------------------------------------------
`preregistration.assert_unchanged` runs first with the hash recorded when the
families were declared. If targets or horizons moved after the experiment was
designed, this refuses to run rather than producing a number nobody can
interpret.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import construct as CK              # noqa: E402
from intent_engine.econ import forecast as FC               # noqa: E402
from intent_engine.econ import incremental as INC           # noqa: E402
from intent_engine.econ import instrument_map as IM         # noqa: E402
from intent_engine.econ import panel as PN                  # noqa: E402
from intent_engine.econ import preregistration as PR        # noqa: E402
from intent_engine.econ import proxies as PX                # noqa: E402

PANEL = pathlib.Path("reports/panel/historical_panel.jsonl")
OUT = pathlib.Path("reports")
MANIFEST = pathlib.Path("reports/panel/historical_acquisition_manifest.json")


def declared_origins():
    """The forecast origins, READ FROM THE ACQUISITION MANIFEST.

    WHY NOT INFERRED FROM THE PANEL. This line used to be

        origins = [v for v in every vintage_at in the panel
                   if v.endswith("-15")]

    which is a pattern match on a date string, not a grid. It admitted 344
    origins where the acquisition planned 115: BOGZ1FL153064486Q is quarterly
    with a 75-day publication lag, so its RELEASE dates land on the 15th of
    January, April, July and October, and every one of them was read as a
    forecast origin.

    That is not a hindsight leak -- an off-grid origin reads each REVISED
    series at the newest vintage at or before it, which is an UNDER-read. It
    is worse than harmless in a different way: at two of every three origins
    the revised series are stale by up to a quarter, and eleven of the
    sixteen behavioural series are REVISED against two of the eight base
    series. The haircut therefore falls mostly on the augmented model, and
    the pooled delta moved from -0.00948 to -0.06169 for that reason alone.

    An experiment must not take its sampling grid from one series'
    publication calendar. The grid is DECLARED, in the manifest the
    acquisition wrote, and read from there.
    """
    import json as _json
    if not MANIFEST.exists():
        raise SystemExit(
            f"{MANIFEST} is missing. The origin grid is declared by the "
            "acquisition, not inferred from the panel; run "
            "scripts/acquire_panel.py first.")
    grid = _json.loads(MANIFEST.read_text()).get("origins") or []
    if not grid:
        raise SystemExit(f"{MANIFEST} declares no origins")
    return sorted(grid)

#: Fixed when the experiment was designed. Editing FAMILIES changes this and
#: the run refuses.
PREREG_HASH = "4ae395b62fb60f85"

#: The economic block. Model A sees exactly this.
BASE_SERIES = ("UNRATE", "CPIAUCSL", "DFF", "DGS2", "DGS10",
               "HOUST", "INDPRO", "PCEC96")

#: The behavioural block, restricted to series behind a MEASURABLE construct.
#: Built from the instrument map rather than typed, so a construct retired
#: later drops out of the model instead of being filtered at the surface.
def series_by_construct() -> dict:
    """construct -> the LIVE series behind it.

    Derived from the instrument map, not typed, so a construct retired later
    drops out of the model rather than being filtered at a surface.
    """
    from intent_engine.econ import series as SER

    # ALL series per kind, not one. `{s.kind: s.key}` keeps only the LAST
    # entry, and four kinds have several live ids -- delinquency has three.
    # That dict silently dropped quits and participation from the model the
    # moment two superseded BLS ids were declared, and the pooled delta moved
    # from -0.00565 to -0.00454 with nothing in the report saying why.
    #
    # SUPERSEDED SERIES ARE EXCLUDED HERE. They are keyless and real and
    # cannot serve a vintage, so they may not back anything walled; the
    # `reason` field is where that was already recorded.
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


def behavioural_series() -> tuple:
    seen = set()
    for keys in series_by_construct().values():
        seen |= set(keys)
    return tuple(sorted(seen))


TRAIN_END, VALIDATION_END = "2014-01-01", "2021-01-01"


def regime_of(origin: str) -> str:
    y = int(origin[:4])
    for lo, hi, name in ((1998, 2000, "LATE_CYCLE"),
                         (2001, 2003, "DOTCOM_UNWIND"),
                         (2004, 2006, "EXPANSION"),
                         (2007, 2009, "CREDIT_CRISIS"),
                         (2010, 2013, "POST_CRISIS"),
                         (2014, 2019, "LOW_RATE"),
                         (2020, 2020, "COVID_SHOCK"),
                         (2021, 2021, "COVID_RECOVERY"),
                         (2022, 2023, "INFLATION_SHOCK")):
        if lo <= y <= hi:
            return name
    return "RECENT"


def _chg(hist, periods):
    if len(hist) <= periods:
        return None
    a, b = hist[-1 - periods][1], hist[-1][1]
    return None if a == 0 else (b - a) / abs(a)


def build_rows(panel, origins, beh_series):
    """One Row per (origin, family). Inputs walled; outcome in hindsight."""
    truth = {t: dict(panel.history(t, as_of="2099-01-01"))
             for t in PR.TARGET_SERIES}
    periods = {t: sorted(truth[t]) for t in PR.TARGET_SERIES}
    rows, skipped = [], {"thin_features": 0, "no_outcome": 0}

    for origin in origins:
        base_f, beh_f = {}, {}
        # CHANGES ONLY, NEVER LEVELS.
        #
        # The first run used levels AND changes and produced a base model
        # that lost to always-predicting-the-base-rate in 10 families out of
        # 10. The reason is visible once stated: CPIAUCSL and PCEC96 grow
        # almost monotonically, so their LEVEL is a proxy for the date. A
        # model given the date and ~40 training rows fits the calendar, and
        # a delta measured between two models that both fit the calendar is
        # not evidence about anything.
        #
        # RATE SERIES ARE THE EXCEPTION: a policy rate is stationary enough
        # that its level is genuinely informative, and dropping it would
        # remove the single most important economic control.
        STATIONARY_LEVELS = ("UNRATE", "DFF", "DGS2", "DGS10")
        for sid in BASE_SERIES:
            h = panel.history(sid, as_of=origin, lookback=24)
            if len(h) < 6:
                continue
            if sid in STATIONARY_LEVELS:
                base_f[f"{sid}_lvl"] = h[-1][1]
            c4 = _chg(h, 4)
            if c4 is not None:
                base_f[f"{sid}_d4"] = c4
        for sid in beh_series:
            h = panel.history(sid, as_of=origin, lookback=24)
            if len(h) < 6:
                continue
            c4 = _chg(h, 4)
            if c4 is not None:
                beh_f[f"{sid}_d4"] = c4
        if len(base_f) < 6 or len(beh_f) < 3:
            skipped["thin_features"] += 1
            continue

        for fam in PR.FAMILIES:
            t = fam.target_series
            past = [p for p in periods[t] if p <= origin]
            if not past:
                skipped["no_outcome"] += 1
                continue
            now_p = past[-1]
            fut = [p for p in periods[t] if p > now_p]
            want = fam.horizon_days // 30
            if len(fut) <= want:
                skipped["no_outcome"] += 1
                continue
            fut_p = fut[want]
            rows.append(FC.Row(
                origin=origin, target=fam.family_id,
                horizon_days=fam.horizon_days,
                features={**base_f, **beh_f},
                outcome=truth[t][fut_p] > truth[t][now_p],
                regime=regime_of(origin), outcome_knowable_at=fut_p))
    return rows, skipped


def names_for(rows, prefixes):
    seen = set()
    for r in rows:
        seen |= set(r.features)
    return sorted(n for n in seen
                  if any(n.startswith(p + "_") for p in prefixes))


def baselines(rows) -> dict:
    """§9's required baselines, scored on the SAME rows as the models.

    Without these the experiment cannot tell "the collective layer helped"
    from "both models are worse than a constant, and one is less bad". The
    first run of this experiment was the second case in ten families out of
    ten, and only the base-rate baseline revealed it.
    """
    if not rows:
        return {}
    ordered = sorted(rows, key=lambda r: (r.origin, r.target))
    base_rate = FC.base_rate(ordered)
    # Always predict the in-sample base rate.
    const = sum((base_rate - (1.0 if r.outcome else 0.0)) ** 2
                for r in ordered) / len(ordered)
    # Persistence: predict that the target repeats its last direction. With
    # only the outcome available, that is the previous row's outcome.
    persist, prev = [], None
    for r in ordered:
        if prev is not None:
            persist.append((1.0 if prev else 0.0,
                            1.0 if r.outcome else 0.0))
        prev = r.outcome
    pers = (sum((p - y) ** 2 for p, y in persist) / len(persist)
            if persist else None)
    return {"base_rate": round(base_rate, 4),
            "always_base_rate_brier": round(const, 5),
            "persistence_brier": (round(pers, 5) if pers is not None
                                  else None)}


def _verdicts(comparisons, by_construct) -> dict:
    """§12's verdict per construct, from the real historical result."""
    out = {}
    for cid in sorted(by_construct):
        mine = [c for c in comparisons if c.dimension == cid]
        tested = [c for c in mine if c.verdict != INC.INSUFFICIENT_SAMPLE]
        robust = [c for c in tested if c.robust]
        # POWER FIRST. Retiring a construct whose effect was never
        # resolvable is not a scientific result, it is a sample-size
        # artefact recorded as one. A construct is only RETIRED when the
        # sample could have detected an effect and did not find one.
        resolvable = [c for c in tested if not c.underpowered]
        # SYMMETRIC WITH PROMOTION. `construct.PASSES_FOR_PROMOTION` is 2,
        # and `apply_report` retires after 2 failures. Retiring on ONE
        # resolvable observation would make removal easier than admission,
        # which is the wrong asymmetry for a construct that costs nothing to
        # leave at CANDIDATE and something real to delete wrongly.
        if not tested:
            verdict = "INSUFFICIENT_DATA"
        elif robust:
            verdict = ("PROMOTE" if len(robust) >= CK.PASSES_FOR_PROMOTION
                       else "TESTED_NOT_PROMOTED")
        elif len(resolvable) < CK.PASSES_FOR_PROMOTION:
            verdict = "INSUFFICIENT_DATA"
        elif all(c.delta <= 0 for c in resolvable):
            verdict = "RETIRE"
        else:
            verdict = "TESTED_NOT_PROMOTED"
        out[cid] = {
            "construct": cid, "verdict": verdict,
            "families_tested": len(tested),
            "families_robust": len(robust),
            "families_resolvable": len(resolvable),
            "underpowered": len(tested) - len(resolvable),
            "median_mde": (round(sorted(c.mde for c in tested
                                        if c.mde is not None)[len(tested)//2],
                                 5) if tested else None),
            "best_delta": (round(max((c.delta for c in tested), default=0.0),
                                 5) if tested else None),
            "deltas": {c.name: c.delta for c in tested},
            "series": list(by_construct.get(cid, ())),
        }
    return out


def main() -> int:
    PR.assert_unchanged(PREREG_HASH)
    print(f"=== PREREGISTRATION === hash {PR.declaration_hash()} "
          f"({len(PR.FAMILIES)} families) — unchanged")

    if not PANEL.exists():
        print(f"panel not built: {PANEL}")
        return 2
    panel = PN.Panel.read(PANEL)
    s = panel.summarise()
    print(f"=== PANEL === series={s['series']} cells={s['cells']} "
          f"span={s['earliest']}..{s['latest']} "
          f"revised={s['periods_with_more_than_one_vintage']}")

    beh = behavioural_series()
    print(f"=== BLOCKS === base={len(BASE_SERIES)} behavioural={len(beh)}")
    print(f"  behavioural: {list(beh)}")

    origins = declared_origins()
    rows, skipped = build_rows(panel, origins, beh)
    print(f"=== ROWS === {len(rows)} from {len(origins)} origins "
          f"(skipped: {skipped})")
    if len(rows) < FC.MIN_TRAIN_ROWS * 2:
        print("not enough rows; the panel is too thin for a valid experiment")
        return 2

    by_family, comparisons, per_family = {}, [], {}
    for r in rows:
        by_family.setdefault(r.target, []).append(r)

    base_out, aug_out = [], []
    for fid, frows in sorted(by_family.items()):
        fam = PR.BY_ID[fid]
        part = FC.split_by_date(frows, train_end=TRAIN_END,
                                validation_end=VALIDATION_END)
        pool = list(part.train) + list(part.validation)
        if len(pool) < FC.MIN_TRAIN_ROWS + 10:
            print(f"  {fid:<22} SKIP  pool={len(pool)}")
            continue
        bn = names_for(pool, BASE_SERIES)
        an = names_for(pool, tuple(BASE_SERIES) + tuple(beh))

        bf = FC.walk_forward(pool, bn, folds=5)
        af = FC.walk_forward(pool, an, folds=5)
        if not bf or not af:
            print(f"  {fid:<22} SKIP  no folds")
            continue
        bp = [p for f in bf for p in f.predictions]
        ap = [p for f in af for p in f.predictions]
        shared = sorted({k for k, *_ in bp} & {k for k, *_ in ap})
        bp = [x for x in bp if x[0] in shared]
        ap = [x for x in ap if x[0] in shared]

        reg = {r.key: r.regime for r in frows}
        cut = {r.key: r.origin for r in frows}
        out = {r.key: (r.outcome, r.outcome_knowable_at) for r in frows}
        outs = [INC.Outcome(target_id=k, occurred=out[k][0],
                            occurred_at=out[k][1], published_at=out[k][1],
                            regime=reg[k]) for k in shared]
        mk = lambda preds, m: [                              # noqa: E731
            INC.Forecast(target_id=k, probability=p, information_cutoff=cut[k],
                         horizon_days=fam.horizon_days, model=m,
                         regime=reg[k], cluster=cut[k])
            for k, p, _y, _r in preds]

        c = INC.compare(name=fid, dimension="collective_block",
                        population="US_households", base=mk(bp, "BASE"),
                        augmented=mk(ap, "BASE_PLUS_COLLECTIVE"),
                        outcomes=outs, horizon_days=fam.horizon_days)
        comparisons.append(c)
        bl = baselines([r for r in frows if r.key in set(shared)])
        bsum = FC.summarise_predictions(bp)
        asum = FC.summarise_predictions(ap)
        trivial = bl.get("always_base_rate_brier")
        per_family[fid] = {
            "base": bsum, "augmented": asum, "baselines": bl,
            # THE GATE BEFORE THE GATE. A model that loses to a constant is
            # not a baseline anything can be measured against.
            "base_beats_trivial": (trivial is not None
                                   and bsum["brier"] < trivial),
            "augmented_beats_trivial": (trivial is not None
                                        and asum["brier"] < trivial),
            "base_features": len(bn), "augmented_features": len(an),
            "partition": part.summarise(),
            "expected_constructs": list(fam.expected_constructs)}
        for k, p, y, rg in bp:
            base_out.append({"family": fid, "target_id": k, "p": p,
                             "y": y, "regime": rg, "model": "BASE"})
        for k, p, y, rg in ap:
            aug_out.append({"family": fid, "target_id": k, "p": p, "y": y,
                            "regime": rg, "model": "BASE_PLUS_COLLECTIVE"})
        print(f"  {fid:<22} n={c.n_paired:<4} base={c.base_score:<8} "
              f"aug={c.augmented_score:<8} d={c.delta:+.5f}  {c.verdict}")

    # -----------------------------------------------------------------
    # PER-CONSTRUCT ATTRIBUTION (Sections 11, 12)
    #
    # The block comparison answers "does the collective layer add anything".
    # It cannot answer "which construct". So each construct is ALSO run on
    # its own: base vs base + only that construct's series, over the same
    # rows and folds. A construct is credited only for families it was
    # PREREGISTERED to help with -- otherwise a construct that happens to
    # help somewhere gets promoted for a hypothesis nobody made.
    # -----------------------------------------------------------------
    by_construct = series_by_construct()
    construct_comparisons = []
    print()
    print("=== PER-CONSTRUCT ===")
    for cid, keys in sorted(by_construct.items()):
        fams = [f.family_id for f in PR.families_for(cid)]
        if not fams:
            print(f"  {cid:<22} declared in no family — not tested")
            continue
        for fid in fams:
            frows = by_family.get(fid) or []
            part = FC.split_by_date(frows, train_end=TRAIN_END,
                                    validation_end=VALIDATION_END)
            pool = list(part.train) + list(part.validation)
            if len(pool) < FC.MIN_TRAIN_ROWS + 10:
                continue
            bn = names_for(pool, BASE_SERIES)
            cn = names_for(pool, tuple(BASE_SERIES) + tuple(keys))
            if set(cn) == set(bn):
                continue
            bf = FC.walk_forward(pool, bn, folds=5)
            cf_ = FC.walk_forward(pool, cn, folds=5)
            if not bf or not cf_:
                continue
            bp = [x for f in bf for x in f.predictions]
            cp = [x for f in cf_ for x in f.predictions]
            shared = sorted({k for k, *_ in bp} & {k for k, *_ in cp})
            bp = [x for x in bp if x[0] in shared]
            cp = [x for x in cp if x[0] in shared]
            reg = {r.key: r.regime for r in frows}
            cut = {r.key: r.origin for r in frows}
            out = {r.key: (r.outcome, r.outcome_knowable_at) for r in frows}
            outs = [INC.Outcome(target_id=k, occurred=out[k][0],
                                occurred_at=out[k][1],
                                published_at=out[k][1], regime=reg[k])
                    for k in shared]
            mk2 = lambda preds, m: [                         # noqa: E731
                INC.Forecast(target_id=k, probability=p,
                             information_cutoff=cut[k],
                             horizon_days=PR.BY_ID[fid].horizon_days,
                             model=m, regime=reg[k], cluster=cut[k])
                for k, p, _y, _r in preds]
            cc = INC.compare(
                name=f"{cid}/{fid}", dimension=cid,
                population="US_households", base=mk2(bp, "BASE"),
                augmented=mk2(cp, f"BASE_PLUS_{cid}"), outcomes=outs,
                horizon_days=PR.BY_ID[fid].horizon_days)
            construct_comparisons.append(cc)
            print(f"  {cid:<22} {fid:<20} n={cc.n_paired:<4} "
                  f"d={cc.delta:+.5f}  {cc.verdict}")

    # -----------------------------------------------------------------
    # THE POOLED TEST (§11)
    #
    # Nine of ten per-family comparisons are UNDERPOWERED: n=50 can only
    # separate a Brier delta of about 0.05 from zero, and every observed
    # effect is smaller than that. Reporting "no robust improvement" from
    # those alone would be reporting a measurement that was never made.
    #
    # Pooling every family into ONE paired comparison multiplies n by ten
    # and divides the detectable effect by roughly the square root of that.
    # It is legitimate because the hypothesis under test is about the BLOCK
    # -- "does knowing how households feel help predict the economy" -- not
    # about any single family. It is reported ALONGSIDE the per-family
    # results, never instead of them, because a pooled win concentrated in
    # one family is a different finding from a broad one.
    # -----------------------------------------------------------------
    pooled_base, pooled_aug, pooled_out = [], [], []
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
        bp = [x for f in bf for x in f.predictions]
        ap = [x for f in af for x in f.predictions]
        shared = sorted({k for k, *_ in bp} & {k for k, *_ in ap})
        reg = {r.key: r.regime for r in frows}
        cut = {r.key: r.origin for r in frows}
        out = {r.key: (r.outcome, r.outcome_knowable_at) for r in frows}
        h = PR.BY_ID[fid].horizon_days
        for k, pr, _y, _r in bp:
            if k in shared:
                pooled_base.append(INC.Forecast(
                    target_id=k, probability=pr, information_cutoff=cut[k],
                    horizon_days=h, model="BASE", regime=reg[k],
                    cluster=cut[k]))
        for k, pr, _y, _r in ap:
            if k in shared:
                pooled_aug.append(INC.Forecast(
                    target_id=k, probability=pr, information_cutoff=cut[k],
                    horizon_days=h, model="BASE_PLUS_COLLECTIVE",
                    regime=reg[k], cluster=cut[k]))
        for k in shared:
            pooled_out.append(INC.Outcome(
                target_id=k, occurred=out[k][0], occurred_at=out[k][1],
                published_at=out[k][1], regime=reg[k]))

    pooled = None
    if len(pooled_out) >= INC.MIN_PAIRED:
        pooled = INC.compare(name="POOLED_ALL_FAMILIES",
                             dimension="collective_block",
                             population="US_households", base=pooled_base,
                             augmented=pooled_aug, outcomes=pooled_out)
        print()
        print("=== POOLED ACROSS ALL FAMILIES ===")
        print(f"  n={pooled.n_paired}  base={pooled.base_score}  "
              f"aug={pooled.augmented_score}  delta={pooled.delta:+.5f}")
        print(f"  95% CI [{pooled.ci_low:+.5f}, {pooled.ci_high:+.5f}]  "
              f"MDE {pooled.mde}  p={pooled.p_value}")
        print(f"  verdict {pooled.verdict}"
              f"{'  (UNDERPOWERED)' if pooled.underpowered else ''}")

    # Per-regime, on the pooled sample, so the breakdown Section 11 asks for
    # is computed where there is enough n to support it.
    pooled_by_regime = {}
    if pooled is not None:
        for rg in sorted({o.regime for o in pooled_out}):
            c = INC.compare(name=f"POOLED/{rg}", dimension="collective_block",
                            population="US_households", base=pooled_base,
                            augmented=pooled_aug, outcomes=pooled_out,
                            regime=rg)
            pooled_by_regime[rg] = c.as_dict()

    # ONE family-wide correction across BOTH sets. Correcting them separately
    # would be two families of tests reported as one.
    all_adjusted = INC.adjust(list(comparisons) + construct_comparisons)
    block_ids = {c.name for c in comparisons}
    adjusted = [c for c in all_adjusted if c.name in block_ids]
    construct_adjusted = [c for c in all_adjusted if c.name not in block_ids]
    rep = INC.report(adjusted)
    rep["per_construct"] = [c.as_dict() for c in construct_adjusted]
    rep["pooled"] = pooled.as_dict() if pooled is not None else None
    rep["pooled_by_regime"] = pooled_by_regime
    rep["construct_verdicts"] = _verdicts(construct_adjusted, by_construct)
    valid = [f for f in per_family.values() if f["base_beats_trivial"]]
    rep.update({"per_family": per_family, "panel": s,
                "families_with_a_valid_baseline": len(valid),
                "families_total": len(per_family),
                "baseline_gate": ("PASS" if len(valid) == len(per_family)
                                  else "FAIL"),
                "preregistration_hash": PR.declaration_hash(),
                "behavioural_series": list(beh),
                "base_series": list(BASE_SERIES),
                "origins": len(origins), "rows": len(rows),
                "skipped": skipped})

    # -----------------------------------------------------------------
    # §12: THE EXISTING PROMOTION SYSTEM, not a parallel one.
    #
    # `_verdicts` above computes what the evidence says. `construct` is what
    # ACTS on it -- the same lifecycle the closed-loop demonstration used,
    # driven now by real historical comparisons instead of generated ones.
    # Only RESOLVABLE comparisons are handed over: feeding an underpowered
    # null into a retirement rule would delete constructs for having been
    # untested.
    # -----------------------------------------------------------------
    register = [CK.observe(CK.propose(cid, proposed_by="behavioural-economics"),
                           proxy=",".join(by_construct.get(cid, ())),
                           at="2026-08-27")
                for cid in sorted(by_construct)]
    resolvable_comps = [c for c in construct_adjusted if not c.underpowered]
    register = CK.apply_report(register, resolvable_comps, at="2026-08-27")
    reg_summary = CK.summarise(register)
    rep["promotion_register"] = reg_summary

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "model_comparison.json").write_text(
        json.dumps(rep, indent=2, sort_keys=True, default=str))
    for name, data in (("base_forecasts.jsonl", base_out),
                       ("augmented_forecasts.jsonl", aug_out)):
        with open(OUT / name, "w", encoding="utf-8") as fh:
            for r in data:
                fh.write(json.dumps(r, sort_keys=True) + "\n")

    with open(OUT / "promotion_ledger.jsonl", "w", encoding="utf-8") as fh:
        for v in rep["construct_verdicts"].values():
            fh.write(json.dumps(v, sort_keys=True) + "\n")

    print()
    print("=== PROMOTION REGISTER (econ.construct, real results) ===")
    for st, dims in sorted(reg_summary["by_state"].items()):
        print(f"  {st:<12} {dims}")
    print(f"  usable in the causal graph: "
          f"{reg_summary['usable_in_causal_graph'] or 'none'}")
    print(f"  comparisons handed to the gate: {len(resolvable_comps)} "
          f"resolvable of {len(construct_adjusted)}")

    print()
    print("=== BASELINE GATE (§9) ===")
    print(f"  {'family':<22} {'base_rate':>9} {'trivial':>8} {'base':>8} "
          f"{'aug':>8}  valid?")
    for fid, f in sorted(per_family.items()):
        bl = f["baselines"]
        print(f"  {fid:<22} {bl['base_rate']:>9.2f} "
              f"{bl['always_base_rate_brier']:>8.4f} "
              f"{f['base']['brier']:>8.4f} {f['augmented']['brier']:>8.4f}  "
              f"{'YES' if f['base_beats_trivial'] else 'NO'}")
    print(f"  families where the base model beats a constant: "
          f"{rep['families_with_a_valid_baseline']}/{rep['families_total']}"
          f"  -> BASELINE_GATE {rep['baseline_gate']}")

    print()
    print("=== CONSTRUCT VERDICTS ===")
    for cid, v in sorted(rep["construct_verdicts"].items()):
        print(f"  {cid:<22} {v['verdict']:<20} tested={v['families_tested']}"
              f" resolvable={v['families_resolvable']}"
              f" robust={v['families_robust']}"
              f" best={v['best_delta']} mde~{v['median_mde']}")

    print()
    print("=== SECTION 56 ===")
    print(f"  BASE_MODEL_SCORE     = {rep['base_economic_model_score']}")
    print(f"  BASE_PLUS_COLLECTIVE = {rep['base_plus_collective_score']}")
    print(f"  INCREMENTAL_DELTA    = {rep['incremental_delta']}")
    print(f"  robust               = {rep['robust_improvements']}"
          f"/{rep['tested']} tested (FDR q={INC.FDR_Q})")
    print()
    for st in rep["statements"]:
        print(f"  {st}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

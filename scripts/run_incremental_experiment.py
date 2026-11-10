"""§8/§9/§10/§11: base economic model vs base + collective state, on real data.

WHAT THIS ACTUALLY DOES
-----------------------
For each quarterly origin T and each target series:

    features  = the panel AS KNOWN AT T          (walled by vintage)
    outcome   = did the target rise from T to T+h (known in hindsight, which
                is correct -- it is the thing being predicted)

Model A gets the economic block. Model B gets the economic block PLUS the
behavioural block. Same origins, same targets, same fit, same penalty. One
difference.

Then `incremental.compare` scores the paired forecasts, bootstraps the
difference, and `incremental.adjust` applies Benjamini-Hochberg across the
whole family of (target x horizon) comparisons.

WHY THE TARGETS ARE ALL MACRO
-----------------------------
A behavioural series cannot be a target here. If it were, Model B would be
predicting one of its own inputs and the delta would measure leakage. The
targets are consumption, housing, labour, industrial production and the high
yield spread -- economic outcomes that the collective layer claims to
anticipate.

WHY THE OUTCOME USES THE CURRENT VINTAGE
----------------------------------------
Because it is an outcome. What actually happened to consumption between 2015
and 2016 is a resolved fact, and the best estimate of it is the latest
revision. The vintage wall applies to INPUTS -- what the model could see when
it forecast -- not to the grading.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import forecast as FC                # noqa: E402
from intent_engine.econ import incremental as INC            # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import proxies as PX                 # noqa: E402

PANEL = pathlib.Path("reports/panel/historical_panel.jsonl")
OUT = pathlib.Path("reports")

#: The economic block. Model A sees exactly this.
BASE_SERIES = ("UNRATE", "CPIAUCSL", "DFF", "DGS2", "DGS10",
               "BAMLH0A0HYM2", "HOUST", "INDPRO", "PCEC96")

#: The behavioural block. Model B additionally sees this. Only series behind
#: a MEASURABLE construct are included -- a series with no construct is data
#: the collective layer does not claim.
BEHAVIOURAL_SERIES = ("UMCSENT", "PSAVERT", "DRCCLACBS", "REVOLSL", "JTSQUR",
                      "CIVPART", "TDSP", "U6RATE", "EMRATIO",
                      "BOGZ1FL153064486Q", "DGORDER", "HSN1F",
                      "BABATOTALSAUS", "MICH", "USACSCICP02STSAM")

#: What the two models forecast. All economic outcomes; none is a feature the
#: behavioural block supplies, so Model B cannot predict one of its own inputs.
TARGETS = ("PCEC96", "HOUST", "UNRATE", "INDPRO", "BAMLH0A0HYM2")

HORIZONS = (180, 360)          # roughly two and four quarters

#: Regime labels by origin year, used for the per-regime breakdown Section 9
#: asks for. Deliberately coarse and declared up front rather than fitted.
def regime_of(origin: str) -> str:
    y = int(origin[:4])
    if 1998 <= y <= 2000:
        return "LATE_CYCLE"
    if 2001 <= y <= 2003:
        return "DOTCOM_UNWIND"
    if 2004 <= y <= 2006:
        return "EXPANSION"
    if 2007 <= y <= 2009:
        return "CREDIT_CRISIS"
    if 2010 <= y <= 2013:
        return "POST_CRISIS"
    if 2014 <= y <= 2019:
        return "LOW_RATE"
    if y == 2020:
        return "COVID_SHOCK"
    if y == 2021:
        return "COVID_RECOVERY"
    if 2022 <= y <= 2023:
        return "INFLATION_SHOCK"
    return "RECENT"


def _pct_change(hist, periods: int):
    """Recent change, as a fraction. None when there is not enough history."""
    if len(hist) <= periods:
        return None
    a, b = hist[-1 - periods][1], hist[-1][1]
    if a == 0:
        return None
    return (b - a) / abs(a)


def build_rows(panel: PN.Panel, origins) -> list:
    """One Row per (origin, target, horizon). Inputs walled, outcome not."""
    rows = []
    # Outcomes read the CURRENT vintage: what happened is a resolved fact.
    truth = {t: dict(panel.history(t, as_of="2099-01-01")) for t in TARGETS}
    truth_periods = {t: sorted(truth[t]) for t in TARGETS}

    for origin in origins:
        known = panel.as_known_at(origin)
        feats_base, feats_beh = {}, {}
        for sid in BASE_SERIES:
            hist = panel.history(sid, as_of=origin, lookback=24)
            if len(hist) < 6:
                continue
            feats_base[f"{sid}_level"] = hist[-1][1]
            for lag, name in ((1, "d1"), (4, "d4")):
                ch = _pct_change(hist, lag)
                if ch is not None:
                    feats_base[f"{sid}_{name}"] = ch
        for sid in BEHAVIOURAL_SERIES:
            hist = panel.history(sid, as_of=origin, lookback=24)
            if len(hist) < 6:
                continue
            feats_beh[f"{sid}_level"] = hist[-1][1]
            for lag, name in ((1, "d1"), (4, "d4")):
                ch = _pct_change(hist, lag)
                if ch is not None:
                    feats_beh[f"{sid}_{name}"] = ch
        if len(feats_base) < 8:
            continue

        for target in TARGETS:
            periods = truth_periods[target]
            cur = [p for p in periods if p <= origin]
            if not cur:
                continue
            now_p = cur[-1]
            for h in HORIZONS:
                fut = [p for p in periods if p > now_p]
                # roughly h days ahead, in the series' own frequency
                want = h // 30
                if len(fut) <= want:
                    continue
                fut_p = fut[want]
                a, b = truth[target][now_p], truth[target][fut_p]
                rows.append(FC.Row(
                    origin=origin, target=f"{target}/{h}d", horizon_days=h,
                    features={**feats_base, **feats_beh},
                    outcome=b > a, regime=regime_of(origin),
                    outcome_knowable_at=fut_p))
    return rows


def names_for(rows, block: str) -> list:
    """Feature names present in the data, for one block. Order is fixed."""
    prefixes = (BASE_SERIES if block == "base"
                else BASE_SERIES + BEHAVIOURAL_SERIES)
    seen = set()
    for r in rows:
        seen |= set(r.features)
    return sorted(n for n in seen
                  if any(n.startswith(p + "_") for p in prefixes))


def to_forecasts(preds, model: str, regime_by_key, cutoff_by_key,
                 horizon: int):
    return [INC.Forecast(target_id=k, probability=p,
                         information_cutoff=cutoff_by_key[k],
                         horizon_days=horizon, model=model,
                         regime=regime_by_key[k])
            for k, p, _y, _r in preds]


def main() -> int:
    if not PANEL.exists():
        print(f"panel not built yet: {PANEL}")
        return 2
    panel = PN.Panel.read(PANEL)
    s = panel.summarise()
    print(f"=== PANEL === series={s['series']} cells={s['cells']} "
          f"span={s['earliest']}..{s['latest']} "
          f"revised_periods={s['periods_with_more_than_one_vintage']}")

    origins = sorted({c.vintage_at for cs in panel.cells.values()
                      for c in cs if c.vintage_at < "2099-01-01"})
    # Only the quarterly grid vintages, not the current-pass availability dates
    origins = [o for o in origins if o.endswith("-15")]
    print(f"=== ORIGINS === {len(origins)}  {origins[:2]} .. {origins[-2:]}")

    rows = build_rows(panel, origins)
    print(f"=== ROWS === {len(rows)}")
    if len(rows) < FC.MIN_TRAIN_ROWS * 2:
        print("not enough rows to run the experiment")
        return 2

    by_target = {}
    for r in rows:
        by_target.setdefault(r.target, []).append(r)

    comparisons, per_target = [], {}
    for target, trows in sorted(by_target.items()):
        horizon = trows[0].horizon_days
        part = FC.split_by_date(trows, train_end="2014-01-01",
                                validation_end="2021-01-01")
        pool = list(part.train) + list(part.validation)
        if len(pool) < FC.MIN_TRAIN_ROWS + 10:
            continue
        base_names = names_for(pool, "base")
        aug_names = names_for(pool, "aug")

        base_folds = FC.walk_forward(pool, base_names, folds=5)
        aug_folds = FC.walk_forward(pool, aug_names, folds=5)
        if not base_folds or not aug_folds:
            continue
        bp = [p for f in base_folds for p in f.predictions]
        ap = [p for f in aug_folds for p in f.predictions]

        regime_by_key = {r.key: r.regime for r in trows}
        cutoff_by_key = {r.key: r.origin for r in trows}
        outcome_by_key = {r.key: (r.outcome, r.outcome_knowable_at)
                          for r in trows}

        shared = sorted({k for k, *_ in bp} & {k for k, *_ in ap})
        bpre = [x for x in bp if x[0] in shared]
        apre = [x for x in ap if x[0] in shared]
        outs = [INC.Outcome(target_id=k, occurred=outcome_by_key[k][0],
                            occurred_at=outcome_by_key[k][1],
                            published_at=outcome_by_key[k][1],
                            regime=regime_by_key[k]) for k in shared]

        c = INC.compare(
            name=target, dimension="collective_block",
            population="US_households",
            base=to_forecasts(bpre, "BASE_ECONOMIC", regime_by_key,
                              cutoff_by_key, horizon),
            augmented=to_forecasts(apre, "BASE_PLUS_COLLECTIVE",
                                   regime_by_key, cutoff_by_key, horizon),
            outcomes=outs, horizon_days=horizon)
        comparisons.append(c)
        per_target[target] = {
            "base": FC.summarise_predictions(bpre),
            "augmented": FC.summarise_predictions(apre),
            "base_features": len(base_names),
            "augmented_features": len(aug_names),
            "partition": part.summarise()}
        print(f"  {target:<22} n={c.n_paired:<5} base={c.base_score:<9} "
              f"aug={c.augmented_score:<9} delta={c.delta:+.5f} "
              f"{c.verdict}")

    adjusted = INC.adjust(comparisons)
    report = INC.report(adjusted)
    report["per_target"] = per_target
    report["panel"] = s
    report["origins"] = len(origins)
    report["rows"] = len(rows)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "model_comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str))

    print()
    print("=== SECTION 56 ===")
    print(f"  BASE_MODEL_SCORE          = {report['base_economic_model_score']}")
    print(f"  BASE_PLUS_COLLECTIVE      = {report['base_plus_collective_score']}")
    print(f"  INCREMENTAL_DELTA         = {report['incremental_delta']}")
    print(f"  robust improvements       = {report['robust_improvements']}"
          f"/{report['tested']} tested  (FDR q={INC.FDR_Q})")
    print()
    for st in report["statements"]:
        print(f"  {st}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

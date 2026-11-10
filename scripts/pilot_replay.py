"""Pilot replay — the Day 18 measurement of learning capacity.

    python scripts/pilot_replay.py [--tier 1] [--window research]

Runs every preregistered strategy over the tier-1 universe, applies costs,
computes raw AND effective sample sizes, tests each edge on n_effective, and
applies Benjamini-Hochberg FDR control across the whole family.

The holdout (2025+) is not read. `assert_not_holdout` enforces it.

Prices are cached to disk so a rerun costs no network and the run is
reproducible from the same snapshot.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from intent_engine.market import competition as COMP
from intent_engine.market import experiments as EX
from intent_engine.market import replay as RP
from intent_engine.market import strategy_library as LIB
from intent_engine.market import universe_tiers as UT
from intent_engine.market.costs import DEFAULT as COSTS

CACHE = pathlib.Path("reports/market/replay/price_cache")


def series_for(symbol: str) -> dict:
    """Ten years of daily closes, cached. One fetch per symbol, ever."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    from intent_engine.market.prices import fetch_series
    try:
        closes = dict(fetch_series(symbol, range_="10y").closes)
    except Exception as exc:  # noqa: BLE001 - a gap is data, not a crash
        print(f"  ! {symbol}: {type(exc).__name__}", flush=True)
        closes = {}
    path.write_text(json.dumps(closes))
    return closes


WINDOWS = {
    "research": ("2015-01-01", "2022-12-31"),
    "validation": ("2023-01-01", "2024-12-31"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", type=int, default=UT.TIER_1)
    ap.add_argument("--window", default="research", choices=list(WINDOWS))
    ap.add_argument("--max-seconds", type=float, default=600.0)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    start, end = WINDOWS[args.window]
    securities = UT.universe_for(args.tier)
    print(f"tier {args.tier}: {len(securities)} securities | window "
          f"{args.window} {start}..{end}")
    print(f"costs: {COSTS.version} round trip {COSTS.round_trip_bps} bps\n")

    t0 = time.time()
    print("fetching price history (cached after the first run)...")
    cached = {s.symbol: series_for(s.symbol) for s in securities}
    have = sum(1 for v in cached.values() if v)
    print(f"  {have}/{len(securities)} securities have price data "
          f"({time.time()-t0:.0f}s)\n")

    registry = EX.ExperimentRegistry(
        pathlib.Path(args.root) / "reports/market/experiments.jsonl")
    results, performances, tests = [], [], []

    for spec in LIB.specs():
        signal_fn = LIB.SIGNALS[spec.key]
        budget = RP.Budget(max_seconds=args.max_seconds)
        print(f"--- {spec.key}  horizons={list(spec.horizons.horizons)} ---")
        result = RP.run_replay(
            strategy_key=spec.key, signal_fn=signal_fn,
            horizons=spec.horizons.horizons, securities=securities,
            series_for=lambda s: cached.get(s, {}),
            start=start, end=end, window=args.window, tier=args.tier,
            costs=spec.cost_model, budget=budget, root=args.root)
        results.append(result)
        print(f"  scanned {result.sessions_scanned}  fired "
              f"{result.signals_fired}  observations "
              f"{len(result.observations)}  status {result.status}")
        if result.skipped:
            print(f"  skipped: {result.skipped}")

        # Per-horizon, because horizons are NOT independent and each is its own
        # preregistered test.
        for horizon in spec.horizons.horizons:
            spec.horizons.assert_preregistered(horizon)
            obs = [o for o in result.observations if o["horizon"] == horizon]
            sample = EX.effective_sample(obs)
            name = f"{spec.key}@{horizon}d"
            test = EX.test_edge(name, [o["net_return"] for o in obs], sample)
            tests.append(test)
            registry.record(EX.Experiment(
                experiment_id=f"{result.job}:{horizon}", at=result.job,
                strategy_key=spec.key, horizon=horizon, window=args.window,
                universe_tier=args.tier, securities=len(securities),
                n_raw=sample.n_raw, n_effective=sample.n_effective,
                mean_net_return=test.mean, p_value=test.p_value,
                measurable=test.measurable, note=test.reason))
            print(f"    {horizon:>3}d  n_raw {sample.n_raw:>6}  n_eff "
                  f"{sample.n_effective:>5}  (x{sample.design_effect})  "
                  f"binding={sample.binding:<12} mean_net "
                  f"{'—' if test.mean is None else f'{test.mean:+.5f}'}  "
                  f"p {'—' if test.p_value is None else f'{test.p_value:.4f}'}")

        all_obs = result.observations
        sample = EX.effective_sample(all_obs)
        test = EX.test_edge(spec.key, [o["net_return"] for o in all_obs], sample)
        performances.append(COMP.evaluate(spec.key, "REPLAY_ELIGIBLE",
                                          all_obs, sample, test))
        print()

    fdr = EX.benjamini_hochberg(tests)
    board = COMP.leaderboard(performances, fdr)

    print("=" * 72)
    print("FALSE-DISCOVERY CONTROL")
    print(f"  method {fdr['method']}  q={fdr['q']}  tests={fdr['tests']}")
    print(f"  discoveries: {fdr['discoveries'] or 'NONE'}")
    if fdr.get("note"):
        print(f"  {fdr['note']}")
    print(f"\n  registry total experiments: "
          f"{registry.count()['experiments_total']}")

    print("\nLEADERBOARD")
    print(f"  ranked: {board['ranked']} — {board['reason']}")
    hdr = (f"  {'strategy':<26}{'n_raw':>7}{'n_eff':>7}{'net':>10}"
           f"{'win%':>7}{'PF':>7}{'sharpe':>8}  status")
    print(hdr)
    for row in board["rows"]:
        # Precomputed: Python 3.9 cannot nest same-quotes inside an f-string,
        # and a formatted-or-dash expression inline is unreadable regardless.
        net = row["mean_net_return"]
        win = row["win_rate"]
        pf = row["profit_factor"]
        sh = row["sharpe"]
        net_s = "—" if net is None else format(net, "+.5f")
        win_s = "—" if win is None else format(win * 100, ".1f")
        pf_s = "—" if pf is None else format(pf, ".2f")
        sh_s = "—" if sh is None else format(sh, ".2f")
        status = "MEASURABLE" if row["measurable"] else row["reason"]
        print(f"  {row['strategy_key']:<26}{row['n_raw']:>7}"
              f"{row['n_effective']:>7}{net_s:>10}{win_s:>7}{pf_s:>7}"
              f"{sh_s:>8}  {status}")

    print("\n" + COMP.no_promotion_on_trade_count(performances).get("rule", ""))
    out = pathlib.Path(args.root) / "reports/market/pilot_replay.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"window": args.window, "tier": args.tier,
         "universe": UT.composition(securities),
         "runs": [r.as_dict() for r in results],
         "tests": [t.as_dict() for t in tests],
         "fdr": fdr, "leaderboard": board,
         "elapsed_seconds": round(time.time() - t0, 1)},
        indent=1, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

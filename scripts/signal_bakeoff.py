"""Test candidate signals against the measured baseline, identical methodology.

Pre-registered (see the operating log): every variant is declared before any
result is seen, and ALL results are reported. Testing several and publishing
the winner is p-hacking, and it is the single easiest way to manufacture alpha
that does not exist.

Identical replay for every signal: same companies, same decision dates, same
horizon, same no-lookahead rules. Only the signal function differs, so a
difference in accuracy is attributable to the signal and nothing else.
"""
import collections
import json
import math
import pathlib
import sys
from datetime import date, timedelta

from intent_engine.market.opportunity import MarketEvidence
from intent_engine.market.prices import PriceUnavailable, fetch_series
from intent_engine.market.signals import _volatility, momentum_evidence
from intent_engine.universe.companies import default_universe

HORIZON, LOOKBACK = 21, 30
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/bakeoff")
OUT.mkdir(parents=True, exist_ok=True)


def _trailing(prices):
    return (prices[-1] - prices[0]) / prices[0] if prices and prices[0] else 0.0


# --- the candidates, each an explicit hypothesis -----------------------------
def baseline(prices):
    """momentum_persists.v1 — recent direction persists. Measured 0.500."""
    return momentum_evidence(prices, horizon_days=HORIZON)


def mean_reversion(prices):
    """mean_reversion.v1 — recent direction REVERSES.

    The exact negation of the baseline, so it is primarily a correctness check
    on the harness: if momentum is a coin flip this must be too, and a result
    far from 0.500 would indicate a bug rather than alpha.
    """
    ev = momentum_evidence(prices, horizon_days=HORIZON)
    if ev.is_empty:
        return ev
    flipped = "down" if ev.direction == "up" else "up"
    return MarketEvidence(direction=flipped, probability=ev.probability,
                          horizon_days=ev.horizon_days,
                          upside_pct=ev.upside_pct,
                          downside_pct=ev.downside_pct,
                          source="mean_reversion.v1")


def strong_trend(prices, threshold=0.08):
    """strong_trend.v1 — only a LARGE move persists.

    If any momentum effect exists it should concentrate in high-conviction
    moves. Declines to fire below the threshold, which is a real answer.
    """
    if len(prices) < 3 or abs(_trailing(prices)) < threshold:
        return MarketEvidence(source="strong_trend.v1")
    ev = momentum_evidence(prices, horizon_days=HORIZON)
    return MarketEvidence(direction=ev.direction, probability=ev.probability,
                          horizon_days=ev.horizon_days,
                          upside_pct=ev.upside_pct,
                          downside_pct=ev.downside_pct,
                          source="strong_trend.v1")


def calm_trend(prices, max_vol=0.018):
    """calm_trend.v1 — trends persist in low-volatility names.

    Realised volatility is a proxy for how noisy the signal is; the same
    trailing return means more in a calm name than a choppy one.
    """
    vol = _volatility(prices)
    if vol is None or vol > max_vol:
        return MarketEvidence(source="calm_trend.v1")
    ev = momentum_evidence(prices, horizon_days=HORIZON)
    if ev.is_empty:
        return MarketEvidence(source="calm_trend.v1")
    return MarketEvidence(direction=ev.direction, probability=ev.probability,
                          horizon_days=ev.horizon_days,
                          upside_pct=ev.upside_pct,
                          downside_pct=ev.downside_pct,
                          source="calm_trend.v1")


SIGNALS = {"momentum_persists.v1": baseline,
           "mean_reversion.v1": mean_reversion,
           "strong_trend.v1": strong_trend,
           "calm_trend.v1": calm_trend}


def decision_days(series, count=6, spacing=14):
    last = series.as_of
    if not last:
        return []
    end = date.fromisoformat(last) - timedelta(days=HORIZON + 2)
    return [(end - timedelta(days=spacing * i)).isoformat()
            for i in range(count)][::-1]


def main():
    companies = [c for c in default_universe().prediction_companies()
                 if c.tradable_instrument]
    results = {name: {"n": 0, "correct": 0, "declined": 0}
               for name in SIGNALS}
    per_sector = collections.defaultdict(lambda: collections.defaultdict(
        lambda: [0, 0]))
    priced = 0

    for company in companies:
        try:
            series = fetch_series(company.tradable_instrument, days=400)
        except PriceUnavailable:
            continue
        priced += 1
        for day in decision_days(series):
            start = (date.fromisoformat(day)
                     - timedelta(days=LOOKBACK)).isoformat()
            prices = series.window(start, day)
            exit_day = (date.fromisoformat(day)
                        + timedelta(days=HORIZON)).isoformat()
            if series.as_of is None or exit_day > series.as_of:
                continue
            entry, exit_price = series.on(day), series.on(exit_day)
            if not entry or exit_price is None:
                continue
            move = (exit_price - entry) / entry

            for name, fn in SIGNALS.items():
                ev = fn(prices)
                if ev.is_empty:
                    results[name]["declined"] += 1
                    continue
                right = (move > 0) if ev.direction == "up" else (move < 0)
                results[name]["n"] += 1
                results[name]["correct"] += 1 if right else 0
                per_sector[name][company.sector][0] += 1
                per_sector[name][company.sector][1] += 1 if right else 0

    print("=" * 70)
    print("SIGNAL BAKE-OFF — identical replay, all results reported")
    print("=" * 70)
    print(f"companies priced: {priced}/{len(companies)}   "
          f"horizon: {HORIZON}d   lookback: {LOOKBACK}d\n")
    print(f"{'signal':<26}{'n':>5}{'declined':>10}{'accuracy':>11}"
          f"{'2σ band':>16}  verdict")
    rows = []
    for name, r in SIGNALS.items() and results.items():
        n, c = r["n"], r["correct"]
        acc = round(c / n, 4) if n else None
        se = math.sqrt(0.25 / n) if n else None
        band = f"±{round(2*se,3)}" if se else "—"
        if acc is None:
            verdict = "never fired"
        elif se and abs(acc - 0.5) > 2 * se:
            verdict = "DISTINGUISHABLE from 0.500"
        else:
            verdict = "indistinguishable from 0.500"
        rows.append({"signal": name, "n": n, "declined": r["declined"],
                     "accuracy": acc, "verdict": verdict})
        print(f"{name:<26}{n:>5}{r['declined']:>10}"
              f"{(acc if acc is not None else '—'):>11}{band:>16}  {verdict}")

    (OUT / "bakeoff.json").write_text(json.dumps(rows, indent=1))
    return rows


if __name__ == "__main__":
    main()

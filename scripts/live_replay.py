"""Close the loop: real decisions at a past date, resolved against what the
market actually did.

WHY A REPLAY AND NOT A WAIT
---------------------------
A prediction made today with a 21-day horizon resolves in 21 days. To have
resolved predictions NOW, decisions are made as-of a past date using only
prices available on that date, then graded against the real closes that
followed. No lookahead: `PriceSeries.on` never returns a price after the date
asked for, and `trading_window` refuses to grade a horizon that has not
elapsed.

WHAT THIS GRADES, AND WHAT IT DOES NOT
--------------------------------------
It grades `baseline_momentum.v1` in isolation. The strategic gates are not
applied, because company evidence cannot be time-travelled — a website shows
today's content, and using it for a decision dated three months ago would be
lookahead of the worst kind: invisible, and flattering.

So this answers exactly one question, honestly: **does the baseline have any
edge?** That is the bar every future signal has to beat, and it has never been
measured. It is not a measurement of the whole engine.
"""
import collections
import json
import pathlib
import sys
from datetime import date, timedelta

from intent_engine.market.decision_quality import assess, grade
from intent_engine.market.hypothesis import (
    BASELINE_HYPOTHESIS,
    assess_hypothesis,
    revise,
)
from intent_engine.market.prices import PriceUnavailable, fetch_series
from intent_engine.market.signals import momentum_evidence
from intent_engine.universe.companies import default_universe

HORIZON = 21
LOOKBACK = 30
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/replay")
OUT.mkdir(parents=True, exist_ok=True)


def decision_days(series, count=6, spacing=14):
    """Several decision dates per company, spaced so their horizons do not
    fully overlap — overlapping windows would resample one market move and
    report it as several independent tests."""
    last = series.as_of
    if not last:
        return []
    end = date.fromisoformat(last) - timedelta(days=HORIZON + 2)
    return [(end - timedelta(days=spacing * i)).isoformat()
            for i in range(count)][::-1]


def main():
    universe = default_universe()
    companies = [c for c in universe.prediction_companies()
                 if c.tradable_instrument]
    hypothesis = BASELINE_HYPOTHESIS
    decisions, graded_rows, failures = [], [], []

    for company in companies:
        symbol = company.tradable_instrument
        try:
            series = fetch_series(symbol, days=400)
        except PriceUnavailable as exc:
            failures.append(f"{symbol}: {exc}")
            continue

        for day in decision_days(series):
            window_start = (date.fromisoformat(day)
                            - timedelta(days=LOOKBACK)).isoformat()
            prices = series.window(window_start, day)
            market = momentum_evidence(prices, horizon_days=HORIZON)
            if market.is_empty:
                continue          # the signal declined; not a decision

            entry = series.on(day)
            exit_day = (date.fromisoformat(day)
                        + timedelta(days=HORIZON)).isoformat()
            if series.as_of is None or exit_day > series.as_of:
                continue          # horizon has not elapsed; must stay unresolved
            exit_price = series.on(exit_day)

            decision = {
                "company_id": company.company_id, "symbol": symbol,
                "as_of": day, "classification":
                    "BUY" if market.direction == "up" else "SELL",
                "direction": market.direction,
                "probability": market.probability,
                "market_source": market.source,
                "hypothesis_id": hypothesis.hypothesis_id,
                "blocked_by": [], "sector": company.sector,
                "region": company.region, "market_cap": company.market_cap,
            }
            decisions.append(decision)
            g = grade(decision, entry_price=entry, exit_price=exit_price)
            graded_rows.append({**decision, **g.as_dict()})

            verdict = assess_hypothesis(hypothesis, decision_correct=g.correct)
            hypothesis = revise(hypothesis, verdict.verdict, at=day,
                                evidence=f"{symbol} {day} -> {exit_day}")

    prices_map = {d["company_id"]: (None, None) for d in decisions}
    scored = [r for r in graded_rows if r.get("correct") is not None]
    correct = [r for r in scored if r["correct"]]

    by_sector = collections.defaultdict(lambda: [0, 0])
    for r in scored:
        by_sector[r["sector"]][0] += 1
        by_sector[r["sector"]][1] += 1 if r["correct"] else 0

    report = {
        "companies_priced": len(companies) - len(failures),
        "price_failures": failures,
        "paper_trades_opened": len(decisions),
        "predictions_resolved": len(scored),
        "position_accuracy": (round(len(correct) / len(scored), 4)
                              if scored else None),
        "hypothesis": hypothesis.as_dict(),
        "by_sector": {k: {"n": v[0], "accuracy": round(v[1] / v[0], 3)}
                      for k, v in sorted(by_sector.items()) if v[0]},
    }
    (OUT / "replay.json").write_text(json.dumps(
        {"report": report, "decisions": graded_rows}, indent=1))

    print("=" * 62)
    print("LIVE REPLAY — real prices, real outcomes")
    print("=" * 62)
    print(f"companies priced        : {report['companies_priced']}"
          f"/{len(companies)}")
    if failures:
        print(f"price failures          : {failures}")
    print(f"paper trades opened     : {report['paper_trades_opened']}")
    print(f"PREDICTIONS RESOLVED    : {report['predictions_resolved']}")
    print(f"position accuracy       : {report['position_accuracy']}")
    h = report["hypothesis"]
    print(f"\nhypothesis              : {h['hypothesis_id']}")
    print(f"  tested                : {h['tested']}")
    print(f"  supported / refuted   : {h['supported']} / {h['refuted']}")
    print(f"  support rate          : {h['support_rate']}")
    print(f"  confidence  0.55  ->  : {h['confidence']}")
    print(f"  revisions recorded    : {len(h['revisions'])}")
    print("\naccuracy by sector:")
    for sector, v in report["by_sector"].items():
        print(f"  {sector:<26}n={v['n']:<4}{v['accuracy']}")
    return report


if __name__ == "__main__":
    main()

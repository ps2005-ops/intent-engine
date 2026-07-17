#!/usr/bin/env python
"""Task M8 (market-engine-execution-plan.md): the honest scoreboard.

Every run records the SAME class of resolvable prediction the engine's
own structural forecasts will make (an SPY +2%-within-60-days claim),
from two deliberately dumb rules, source="baseline". Same resolution
path as any other market prediction (M6's resolve_market_prediction,
unchanged), same Brier scoring (the ledger's own resolve_prediction,
unchanged). The entire point: the engine's structural predictions must
eventually beat these on calibration, or the ledger honestly says they
don't -- baselines are a comparison point, never a recommendation, and
never tuned (a tuned baseline stops being a baseline).

Rule 1 -- momentum: P = 0.65 if SPY's trailing 3-month return is
positive, else 0.35. Fixed by the plan's own spec, never tuned against
any observed calibration result.

Rule 2 -- base-rate: P = BASE_RATE_SPY_2PCT_60D, a FROZEN constant
(see its own docstring below for the exact one-time computation that
produced it). Recomputing it is a deliberate, separate decision, not
something this script or its callers ever do automatically.

Usage: python scripts/record_baselines.py --entity-id "Acme Inc" [--path data/prediction_ledger.db]
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core.market_resolution import get_prices  # noqa: E402
from intent_engine.core.prediction_ledger import DEFAULT_LEDGER_PATH, Prediction, record_prediction  # noqa: E402

INSTRUMENT = "SPY"
THRESHOLD = 0.02
WINDOW_DAYS = 60

# Fixed per the plan's own spec -- never tuned against any observed
# calibration result. A momentum rule that got adjusted based on how well
# it happened to score would no longer be a fair comparison point.
MOMENTUM_PROBABILITY_IF_POSITIVE = 0.65
MOMENTUM_PROBABILITY_IF_NEGATIVE = 0.35
MOMENTUM_TRAILING_DAYS = 90  # "trailing 3-month return"

# Frozen, one-time computation (this session, 2026-07-17): SPY adjusted
# closes from Tiingo, 2021-01-01 through 2026-07-16 (a single fetch, 1389
# daily observations). For every trading day with a COMPLETE forward
# 60-calendar-day window available (1348 such days -- the final ~60 days
# of the series were excluded since their true 60-day-forward outcome
# isn't knowable yet), checked whether the price touched >=2% above that
# day's own price at ANY point within the following 60 days -- the exact
# same touched-semantics evaluation core.market_resolution.resolve_pct_change_rule
# uses for a real >=2%-in-60-days claim, for direct comparability, not a
# different ad hoc definition. Result: 1089 of 1348 windows (80.79%)
# touched the threshold. FROZEN as of this computation -- this script
# never recomputes it; changing it is a deliberate, separate, documented
# decision, not an automatic refresh.
BASE_RATE_SPY_2PCT_60D = 0.8079


def _resolution_rule() -> dict:
    return {"type": "pct_change", "symbol": INSTRUMENT, "op": ">=", "value": THRESHOLD, "window_days": WINDOW_DAYS}


def record_momentum_baseline(
    entity_id: str, path=DEFAULT_LEDGER_PATH, price_fetcher=get_prices, today: date = None,
) -> Prediction:
    today = today or date.today()
    trailing_start = (today - timedelta(days=MOMENTUM_TRAILING_DAYS)).isoformat()
    series = price_fetcher(INSTRUMENT, trailing_start, today.isoformat())
    if len(series.observations) < 2:
        raise RuntimeError(
            f"Not enough {INSTRUMENT} price data ({len(series.observations)} points) to compute a trailing "
            f"{MOMENTUM_TRAILING_DAYS}-day return."
        )
    trailing_return_positive = series.observations[-1][1] > series.observations[0][1]
    probability = MOMENTUM_PROBABILITY_IF_POSITIVE if trailing_return_positive else MOMENTUM_PROBABILITY_IF_NEGATIVE

    resolve_by = (today + timedelta(days=WINDOW_DAYS)).isoformat()
    return record_prediction(
        "baseline", entity_id,
        f"{INSTRUMENT} rises at least {THRESHOLD * 100:.0f}% within {WINDOW_DAYS} days (momentum baseline)",
        probability, resolve_by, path=path,
        instrument=INSTRUMENT, direction="up", horizon_days=WINDOW_DAYS,
        resolution_rule=_resolution_rule(), resolution_source="tiingo",
    )


def record_base_rate_baseline(entity_id: str, path=DEFAULT_LEDGER_PATH, today: date = None) -> Prediction:
    today = today or date.today()
    resolve_by = (today + timedelta(days=WINDOW_DAYS)).isoformat()
    return record_prediction(
        "baseline", entity_id,
        f"{INSTRUMENT} rises at least {THRESHOLD * 100:.0f}% within {WINDOW_DAYS} days (base-rate baseline)",
        BASE_RATE_SPY_2PCT_60D, resolve_by, path=path,
        instrument=INSTRUMENT, direction="up", horizon_days=WINDOW_DAYS,
        resolution_rule=_resolution_rule(), resolution_source="tiingo",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity-id", required=True, help="Entity to record these baseline predictions under.")
    parser.add_argument("--path", default=str(DEFAULT_LEDGER_PATH), help="Path to the prediction ledger DB.")
    args = parser.parse_args(argv)

    momentum = record_momentum_baseline(args.entity_id, path=args.path)
    print(f"Recorded momentum baseline: probability={momentum.probability}, resolve_by={momentum.resolve_by}, id={momentum.id}")

    base_rate = record_base_rate_baseline(args.entity_id, path=args.path)
    print(f"Recorded base-rate baseline: probability={base_rate.probability}, resolve_by={base_rate.resolve_by}, id={base_rate.id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

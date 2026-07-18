#!/usr/bin/env python
"""Standing monthly cadence (Workstream 2, business-analyst-agent training
per the plan's calibration-first discipline): renders a READ-ONLY
calibration report over the prediction ledger.

Hard wall, stated in code as well as here: this script NEVER writes to the
ledger, NEVER adjusts any generation/drafting prompt or weight, and is not
wired into any generation path. It calls brier_summary() (core.prediction_
ledger, M1-era function, untouched) once per source and prints the result.
Per A-M5, no feedback into generation happens anywhere in this repo until a
human decides that gate is met -- this script exists to give a human that
information, not to act on it.

No Alpaca integration here or anywhere else -- that source stays out of
scope until its own stated gate (>=30 resolved ledger predictions AND a
human calibration review) is met.

Usage: python scripts/monthly_calibration_checkpoint.py [--window-days N] [--path data/prediction_ledger.db]
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core.prediction_ledger import (  # noqa: E402
    DEFAULT_LEDGER_PATH,
    brier_summary,
)

# Every source the ledger schema currently allows (core/prediction_ledger.py
# PredictionSource) -- kept in sync by hand since Literal members aren't
# introspectable without importing typing internals; a mismatch here would
# just mean a source silently doesn't get its own section, not a crash.
ALL_SOURCES = ["premortem", "scrap", "digest", "manual", "market", "baseline"]


def render_source_section(source: str, window_days) -> str:
    summary = brier_summary(source=source, window_days=window_days)
    lines = [f"## source = {source}"]
    if summary.count == 0:
        lines.append("  No resolved predictions yet.")
        return "\n".join(lines)
    lines.append(f"  Resolved count: {summary.count}")
    lines.append(f"  Mean Brier:     {summary.mean_brier:.4f}  (0 = perfect, 0.25 = coin-flip-at-50%, 1 = worst)")
    lines.append("  Calibration buckets (predicted-probability decile -> realized rate):")
    for key in sorted(summary.calibration_buckets, key=lambda k: int(k.split("-")[0])):
        bucket = summary.calibration_buckets[key]
        lines.append(f"    {key:>8}: n={bucket.count:<4} realized_rate={bucket.realized_rate:.2f}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-days", type=int, default=None, help="Only count predictions resolved within the last N days (default: all-time).")
    parser.add_argument("--path", default=str(DEFAULT_LEDGER_PATH), help="Path to the prediction ledger DB.")
    args = parser.parse_args(argv)

    print("MONTHLY CALIBRATION CHECKPOINT (read-only; no feedback into generation)")
    print("=" * 72)
    if args.window_days:
        print(f"Window: last {args.window_days} days")
    else:
        print("Window: all-time")
    print()

    for source in ALL_SOURCES:
        print(render_source_section(source, args.window_days))
        print()

    market = brier_summary(source="market", window_days=args.window_days)
    baseline = brier_summary(source="baseline", window_days=args.window_days)
    print("## engine (market) vs baselines")
    if market.count == 0 or baseline.count == 0:
        print(f"  Not yet comparable: market has {market.count} resolved, baseline has {baseline.count} resolved.")
        print("  Per A-M5, comparison and any confidence-interval adjustment waits until")
        print("  both cohorts have accumulated resolved predictions -- displayed, not acted on.")
    else:
        print(f"  market mean Brier:   {market.mean_brier:.4f}  (n={market.count})")
        print(f"  baseline mean Brier: {baseline.mean_brier:.4f}  (n={baseline.count})")
        delta = market.mean_brier - baseline.mean_brier
        direction = "better than" if delta < 0 else "worse than" if delta > 0 else "tied with"
        print(f"  engine is {direction} baseline by {abs(delta):.4f} Brier (display only)")

    print()
    print("Standing success definition (A-M5): >=30 resolved predictions per source")
    print("before any calibration-based decision is made. No weight tuning, no")
    print("Alpaca, no feedback into generation happens from this script or its output.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

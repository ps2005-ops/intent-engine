#!/usr/bin/env python
"""Task M6 (market-engine-execution-plan.md): resolves all due, unresolved
market/baseline predictions against real data (Tiingo for pct_change
rules, FRED for level rules via core.macro_data, reused unchanged from
M1), writes outcomes + Brier components through the ledger's own
resolve_prediction() (Brier math computed there, in code, untouched by
this script), and prints a summary.

Idempotent by construction, not by a special-cased check: it only ever
queries UNRESOLVED predictions (list_predictions(unresolved_only=True)),
so a second run against the same ledger simply finds nothing left to do.
Never creates predictions -- read due predictions, resolve them, done.

Safe to run on a schedule (human wires the actual schedule -- this script
does not set one up itself, per the task's own scope wall).

Usage: python scripts/resolve_market_predictions.py [--as-of YYYY-MM-DD] [--path data/prediction_ledger.db]
"""

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core.market_resolution import resolve_market_prediction  # noqa: E402
from intent_engine.core.prediction_ledger import (  # noqa: E402
    DEFAULT_LEDGER_PATH,
    list_predictions,
    resolve_prediction,
)


def resolve_due_predictions(as_of: str, path=DEFAULT_LEDGER_PATH) -> dict:
    due = list_predictions(unresolved_only=True, due_by=as_of, path=path)
    # Only market/baseline predictions carry a resolution_rule at all --
    # anything else due (premortem/scrap/digest/manual) resolves through
    # its own existing path, not this script's job.
    due = [p for p in due if p.resolution_rule is not None]

    counts = {"happened": 0, "did_not_happen": 0, "unresolvable": 0}
    details = []
    for prediction in due:
        result = resolve_market_prediction(prediction)
        resolve_prediction(prediction.id, result.outcome, resolution_note=result.note, path=path)
        counts[result.outcome] += 1
        details.append((prediction.id, prediction.claim_text, result.outcome, result.note))

    return {"total": len(due), "counts": counts, "details": details}


# LEGACY CONTAINMENT (2026-08-12). This pipeline was once mistaken for the
# market intelligence system of record: an exploration read its ledger, found
# it twenty-three days stale, and reported that the learning system had learned
# nothing. The banner is printed by main() so the mistake cannot be repeated
# by anyone — human or agent — who runs this file and reads its output.
def _legacy_banner() -> None:
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from intent_engine.market import system_of_record as SOR
    banner = SOR.legacy_banner("daily_market_predictions")
    if banner:
        print(banner)


def main(argv=None):
    _legacy_banner()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=date.today().isoformat(), help="Resolve predictions with resolve_by <= this date (default: today).")
    parser.add_argument("--path", default=str(DEFAULT_LEDGER_PATH), help="Path to the prediction ledger DB.")
    args = parser.parse_args(argv)

    summary = resolve_due_predictions(args.as_of, path=args.path)

    print(f"Resolved {summary['total']} due market/baseline prediction(s) as of {args.as_of}:")
    print(f"  happened:       {summary['counts']['happened']}")
    print(f"  did_not_happen: {summary['counts']['did_not_happen']}")
    print(f"  unresolvable:   {summary['counts']['unresolvable']}")
    for pred_id, claim_text, outcome, note in summary["details"]:
        print(f"\n  [{outcome}] {pred_id}: {claim_text}\n    {note}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Open beliefs from evidence that is ALREADY on the learning ledger.

WHY THIS EXISTS
---------------
`learning_cycle.run` proposes beliefs from `fresh` evidence — rows whose id is
not already recorded. That is correct for a nightly cycle: rule 1 in
`beliefs.py` is that duplicate evidence updates once, so re-reading an
unchanged filing every night must do nothing.

It also left a hole. Evidence ingested by a cycle that ran BEFORE belief
formation existed can never reach formation, because every later run dedupes
those rows away first. Measured on the production ledger on 2026-08-05:

    9 evidence rows, 0 beliefs, and `refused: {}` — not one reason,
    because there was nothing left to refuse.

The identical 9 rows, against a store that had not seen them, declared 8
beliefs. So the engine worked; the rows were simply unreachable.

WHAT IT IS NOT
--------------
Not a fix to deduplication, which is untouched: nothing is re-ingested and no
evidence row is written. Not learning, either — the beliefs it opens are
reported under `belief_formation_backfill` and are deliberately excluded from
`belief_knowledge_gain`, so a repair can never be read as a session that
learned. Expectations are preregistered at TODAY's date, never the evidence's
original date, so the evidence that opened a belief can still never be the
evidence that confirms it.

Run it once, deliberately, after which ordinary cycles carry on unchanged: a
second run declares nothing, because `propose` refuses a belief that already
exists.

Usage:
    python scripts/backfill_belief_formation.py --root . [--as-of YYYY-MM-DD]
    python scripts/backfill_belief_formation.py --root . --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.market import learning_cycle as LC  # noqa: E402
from intent_engine.market import learning_store as LS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".",
                    help="runtime root holding reports/market/")
    ap.add_argument("--as-of", default="",
                    help="session date; defaults to today (UTC)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what WOULD be opened, writing nothing")
    args = ap.parse_args()

    root = pathlib.Path(args.root)
    as_of = args.as_of or datetime.datetime.now(
        datetime.timezone.utc).date().isoformat()
    path = root / LS.DEFAULT_PATH
    if not path.exists():
        print(f"no learning ledger at {path}", file=sys.stderr)
        return 2

    store = LS.LearningStore(path)
    before = len(store.beliefs())
    recorded = len(store.evidence_ids())

    if args.dry_run:
        # A dry run must not write, so it proposes against a throwaway store
        # and reports. It reads the SAME rows the real run would.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            shadow = LS.LearningStore(pathlib.Path(tmp) / LS.DEFAULT_PATH)
            for item in store.evidence():
                shadow.record_evidence(item)
            for belief in store.beliefs():
                shadow.declare_belief(belief)
            result = LC.run(as_of=as_of, store=shadow, evidence=[],
                            trades_opened=0, backfill_evidence=True)
    else:
        result = LC.run(as_of=as_of, store=store, evidence=[],
                        trades_opened=0, backfill_evidence=True)

    summary = result.as_dict()["belief_formation_backfill"]
    print(json.dumps({
        "as_of": as_of,
        "dry_run": bool(args.dry_run),
        "evidence_on_ledger": recorded,
        "beliefs_before": before,
        "beliefs_after": len(store.beliefs()),
        "backfill": summary,
        "belief_knowledge_gain": result.as_dict()["belief_knowledge_gain"],
        "learned_without_trading": result.as_dict()["learned_without_trading"],
        "note": ("beliefs opened here are a repair of evidence that predates "
                 "belief formation; they are excluded from knowledge gain on "
                 "purpose"),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

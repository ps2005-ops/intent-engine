#!/usr/bin/env python
"""Learning cadence orchestrator (unified-learning platform).

Separates LEARNING from TRAINING, exactly as the founder's final
recommendation states:

    DAILY    ingest signal into candidates
             - paper loop: mark resolved predictions to market (human/M6
               closes positions), then emit recurring-mistake candidates
             - synthetic worlds: feed weakness candidates from the latest
               offline/live eval report
    WEEKLY   evaluate candidates against the current system on rolling
             backtests / synthetic scenarios (records Evaluations)
    MONTHLY  REPORT promotion-readiness for human review — this script
             NEVER promotes. Promotion is a human wall (LearningLedger.
             promote requires actor_type='human'); a scheduler cannot open
             it. The monthly job only surfaces which candidates are ready.

Discipline, stated in code (mirrors resolve_market_predictions.py /
monthly_calibration_checkpoint.py): idempotent by construction, human wires
the actual schedule (this script installs none), no retries, and no path
that mutates a generation prompt or weight. Everything is logged; every
candidate is replayable from the append-only ledger.

Usage:
    python scripts/learning_cadence.py daily   [--root data]
    python scripts/learning_cadence.py weekly  [--root data]
    python scripts/learning_cadence.py monthly [--root data]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from intent_engine.events import CompanyEventBus
from intent_engine.learning import LearningLedger
from intent_engine.paper import PaperTradingLoop


def _wire(root: Path):
    bus = CompanyEventBus(root / "events")
    led = LearningLedger(root / "learning_ledger.db", bus=bus)
    loop = PaperTradingLoop(root / "paper_book.db", bus=bus)
    return bus, led, loop


def daily(root: Path) -> dict:
    """Ingest fresh signal into the candidate pipeline. Read-only w.r.t.
    production; it proposes candidates, nothing more."""
    _, led, loop = _wire(root)
    out = {"stage": "daily"}
    # Paper loop: surface recurring, regime-specific mistakes in the CLOSED
    # book as candidates (positions are opened/closed by the market-engine
    # flow; this job only reads the book and proposes).
    out["paper_candidates"] = loop.emit_learning_candidates(led)
    out["paper_metrics"] = loop.metrics()._asdict()
    # Synthetic worlds: if a machine-readable eval report exists, feed its
    # weaknesses. The report is produced by run_synthetic_world_eval.py
    # (human-wired, Mac-only for --live); this job just consumes it.
    report = root.parent / "reports" / "synthetic_worlds_eval.json"
    if report.exists():
        from intent_engine.learning.synthetic_bridge import (
            candidates_from_synthetic_eval,
        )
        results = json.loads(report.read_text()).get("results", [])
        out["synthetic_candidates"] = candidates_from_synthetic_eval(
            results, led, eval_id=report.stem)
    else:
        out["synthetic_candidates"] = []
    out["pipeline"] = _pipeline(led)
    return out


def weekly(root: Path) -> dict:
    """Report which proposed candidates still need evaluation. Evaluations
    themselves require a comparison harness (rolling backtest / synthetic
    scenario) that is invoked with real data by the market-engine flow —
    this job names the work, it does not fabricate metrics."""
    _, led, _ = _wire(root)
    proposed = led.list(status="proposed")
    return {"stage": "weekly",
            "awaiting_evaluation": [c.id for c in proposed],
            "pipeline": _pipeline(led)}


def monthly(root: Path) -> dict:
    """Surface promotion-readiness for HUMAN review. Never promotes."""
    _, led, _ = _wire(root)
    ready, not_ready = [], []
    for c in led.list(status="evaluated"):
        r = led.evaluate_promotion_readiness(c.id)
        (ready if r["ready"] else not_ready).append(
            {"candidate_id": c.id, "statement": c.statement,
             "reasons": r["reasons"]})
    return {"stage": "monthly", "ready_for_human_promotion": ready,
            "not_yet": not_ready, "pipeline": _pipeline(led),
            "note": "promotion is a human wall; this job only reports"}


def _pipeline(led: LearningLedger) -> dict:
    summary: dict = {}
    for c in led.list():
        summary[c.status] = summary.get(c.status, 0) + 1
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["daily", "weekly", "monthly"])
    ap.add_argument("--root", default="data", type=Path)
    args = ap.parse_args()
    result = {"daily": daily, "weekly": weekly, "monthly": monthly}[args.stage](
        args.root)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

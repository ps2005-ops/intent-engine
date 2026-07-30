"""Synthetic Worlds from REAL company failures (section 15).

Scenarios are generated from recurring, company-specific weaknesses observed in
the durable learning state (overconfidence, a losing paper book, a stated-
priority vs evidence contradiction). Synthetic results may generate candidates
but CANNOT prove market profitability — every run is labelled `proves_market_
profitability=False`, and nothing here promotes a rule.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from intent_engine.hosted.budget import record_skip
from intent_engine.universe.learning import CompanyLearningStore

SYNTHETIC_STREAM = "synthetic_run"

# scenario templates keyed to failure modes (section 15 examples)
_SCENARIOS = {
    "overconfidence": "management messaging conflicts with hiring — confidence "
                      "outran realised accuracy",
    "losing_paper_book": "customer demand diverges from investor narrative — the "
                         "book lost money in this regime",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_synthetic_from_failures(ctx, as_of: str) -> Dict:
    ok, why = ctx.budget_ledger.can_spend(
        as_of, calls=1, cad=ctx.budget.synthetic_daily_budget_cad)
    if not ok:
        record_skip(ctx.store, as_of, item="synthetic_daily", reason=why)
        return {"scenarios": 0, "skipped": why}

    states = CompanyLearningStore(ctx.store).all_latest()
    scenarios: List[dict] = []
    for s in states:
        failures = []
        if (s.avg_confidence is not None and s.directional_accuracy is not None
                and s.avg_confidence - s.directional_accuracy > 0.15):
            failures.append("overconfidence")
        if s.paper_pnl < 0 and s.resolved_count >= 3:
            failures.append("losing_paper_book")
        for mode in failures:
            scenarios.append({"company_id": s.company_id, "failure_mode": mode,
                              "scenario": _SCENARIOS[mode],
                              "sample_size": s.resolved_count})

    run = {"as_of": as_of[:10], "generated_at": _now(),
           "scenarios": scenarios, "count": len(scenarios),
           "proves_market_profitability": False}
    ctx.store.append(SYNTHETIC_STREAM, as_of[:10], run, status="run",
                     idem_key=f"synthetic:{as_of[:10]}:{len(scenarios)}",
                     ts=run["generated_at"])
    ctx.budget_ledger.record(as_of, calls=1,
                             cad=ctx.budget.synthetic_daily_budget_cad,
                             kind="synthetic")
    return {"scenarios": len(scenarios),
            "proves_market_profitability": False}

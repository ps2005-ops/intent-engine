"""Nightly learning reports (section 12): COMPANY, PORTFOLIO, ENGINE.

Computed from the durable store — resolved outcomes, orders, equity snapshots,
per-company learning states, candidates — and persisted to a durable
`daily_report` stream (idempotent per day) so the dashboard and the acceptance
test can read "the nightly report was created", not merely "a job ran".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from intent_engine.hosted.budget import BudgetLedger
from intent_engine.predictions.resolution import OUTCOME_STREAM
from intent_engine.universe.learning import CompanyLearningStore

REPORT_STREAM = "daily_report"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_company_report(ctx, as_of: str) -> List[dict]:
    rows = []
    for company in ctx.universe.prediction_companies():
        cid = company.company_id
        preds = ctx.predictions.by_company(cid)
        outs = [r.payload for r in ctx.store.latest(OUTCOME_STREAM, company_id=cid)]
        orders = ctx.orders.by_company(cid)
        state = ctx.learning_store.get(cid)
        resolved = [o for o in outs if o.get("outcome") in
                    ("happened", "did_not_happen")]
        rows.append({
            "company_id": cid, "classification": company.classification.value,
            "instrument": company.tradable_instrument,
            "predictions": len(preds),
            "unresolved": len([p for p in preds if p.outcome is None]),
            "resolved": len(resolved),
            "orders": len(orders),
            "filled_orders": len([o for o in orders if o.is_filled]),
            "directional_accuracy": state.directional_accuracy if state else None,
            "brier": state.brier if state else None,
            "paper_pnl": state.paper_pnl if state else 0.0,
            "avg_market_return": state.avg_market_return if state else None,
            "sample_size": state.sample_size if state else 0,
            "thesis_notes": state.notes if state else [],
        })
    return rows


def build_portfolio_report(ctx, as_of: str) -> dict:
    from intent_engine.paper.reconciliation import EQUITY_STREAM
    equities = sorted((r.payload for r in ctx.store.latest(EQUITY_STREAM)),
                      key=lambda p: p.get("as_of", ""))
    latest = equities[-1] if equities else None
    curve = [float(e.get("equity", 0)) for e in equities if e.get("equity")]
    peak = max(curve) if curve else 0.0
    drawdown = ((peak - curve[-1]) / peak) if (curve and peak > 0) else 0.0

    outs = [r.payload for r in ctx.store.latest(OUTCOME_STREAM)]
    by_company: Dict[str, float] = {}
    by_horizon: Dict[str, float] = {}
    for o in outs:
        if o.get("trade_pnl") is None:
            continue
        by_company[o.get("company_id", "?")] = (
            by_company.get(o.get("company_id", "?"), 0.0) + o["trade_pnl"])
        h = str(o.get("horizon_days", "?"))
        by_horizon[h] = by_horizon.get(h, 0.0) + o["trade_pnl"]

    open_orders = ctx.orders.open_orders()
    return {
        "equity": latest.get("equity") if latest else None,
        "daily_return": latest.get("daily_return") if latest else None,
        "max_drawdown": round(drawdown, 4),
        "open_positions": len(open_orders),
        "exposure_by_company": {o.company_id: o.qty for o in open_orders},
        "pnl_by_company": {k: round(v, 2) for k, v in by_company.items()},
        "pnl_by_horizon": {k: round(v, 2) for k, v in by_horizon.items()},
    }


def build_engine_report(ctx, as_of: str) -> dict:
    from intent_engine.hosted.candidates import CandidateStore
    from intent_engine.universe.learning import CROSS_STREAM
    states = CompanyLearningStore(ctx.store).all_latest()
    weak = [s.company_id for s in states
            if s.calibration_error is not None and s.calibration_error > 0.15]
    cands = CandidateStore(ctx.store).open()
    cross = [r.payload for r in ctx.store.latest(CROSS_STREAM)]
    skipped = [r.payload for r in ctx.store.latest("skipped_work")]
    failures = [r.payload for r in ctx.store.read("job_failure")][-10:]
    return {
        "weak_confidence_companies": weak,
        "open_candidates": [c.id for c in cands],
        "cross_company_candidates": [c.get("id") for c in cross],
        "recent_failures": failures,
        "skipped_work": skipped,
        "evidence_sufficiency": {
            s.company_id: s.sample_size for s in states},
    }


def write_daily_report(ctx, as_of: str) -> dict:
    ledger = BudgetLedger(ctx.store, ctx.budget)
    report = {
        "as_of": as_of[:10], "generated_at": _now(),
        "company": build_company_report(ctx, as_of),
        "portfolio": build_portfolio_report(ctx, as_of),
        "engine": build_engine_report(ctx, as_of),
        "budget": {"usage": ledger.usage(as_of),
                   "remaining": ledger.remaining(as_of)},
    }
    ctx.store.append(REPORT_STREAM, as_of[:10], report, status="written",
                     idem_key=f"report:{as_of[:10]}:{report['generated_at']}",
                     ts=report["generated_at"])
    return report


def latest_report(store) -> dict:
    rows = store.latest(REPORT_STREAM)
    if not rows:
        return {}
    return max(rows, key=lambda r: r.record_id).payload

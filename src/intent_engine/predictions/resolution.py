"""Resolve due predictions and record linked outcomes (leakage-safe).

A prediction is resolved from the market move over its OWN horizon: the price at
its creation timestamp vs the price at `resolve_by`. Brier uses the same formula
as `core.prediction_ledger.resolve_prediction` — (p-1)^2 if it happened,
(p-0)^2 if it did not — so durable-path calibration is identical to the file
ledger's. Each resolution also links the internal prediction to its paper order
and the trade's realized P&L, and is written to a durable `prediction_outcome`
stream that per-company scoring reads.

Idempotent: a prediction resolves once (repo.resolve is keyed on outcome; the
outcome record is keyed on prediction id). Catch-up: `repo.due(as_of)` returns
everything overdue, so a skipped resolution run is recovered by the next.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from intent_engine.predictions.repository import PredictionRepository

OUTCOME_STREAM = "prediction_outcome"

_UP = {"up", "long", "bull", "rise", "increase"}

PriceAt = Callable[[str, str], float]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_up(direction: Optional[str]) -> bool:
    return str(direction or "").lower() in _UP


def resolve_due(
    repo: PredictionRepository, price_at: PriceAt, as_of: str, *,
    store=None, order_repo=None,
) -> Dict:
    """Resolve every market prediction whose horizon completed by `as_of`.

    Strategic (instrument-less, private-company) predictions are left for the
    separate strategic rubric — they have no price outcome and must not be
    scored as market hits/misses.
    """
    store = store or repo.store
    resolved: List[str] = []
    skipped_strategic = 0
    for pred in repo.due(as_of):
        if not pred.instrument:
            skipped_strategic += 1
            continue
        created_day = (pred.created_at or as_of)[:10]
        resolve_day = (pred.resolve_by or as_of)[:10]
        try:
            entry = price_at(pred.instrument, created_day)
            exit_px = price_at(pred.instrument, resolve_day)
        except Exception:  # noqa: BLE001 - a missing price is not a miss
            continue        # leave unresolved; the next run retries (catch-up)

        move = exit_px - entry
        predicted_up = _is_up(pred.direction)
        happened = (predicted_up and move > 0) or (not predicted_up and move < 0)
        outcome = "happened" if happened else "did_not_happen"
        brier = (pred.probability - 1.0) ** 2 if happened \
            else (pred.probability - 0.0) ** 2

        updated = pred.model_copy(update={
            "outcome": outcome, "brier_component": brier,
            "resolved_at": _now(),
            "resolution_note": f"move {move:+.4f} on {pred.instrument} "
                               f"{created_day}->{resolve_day}"})
        repo.resolve(updated)

        # link the trade's realized P&L (if an order exists for this prediction)
        trade_pnl = None
        trade_return = None
        client_order_id = None
        if order_repo is not None:
            # the OPEN leg carries the entry fill; never the horizon-exit close
            orders = [o for o in order_repo.by_prediction(pred.id)
                      if o.is_filled and o.action.startswith("open_")]
            if orders:
                o = orders[0]
                client_order_id = o.client_order_id
                fill = o.filled_avg_price or entry
                sign = 1.0 if o.side == "buy" else -1.0
                trade_pnl = (exit_px - fill) * o.qty * sign
                trade_return = (trade_pnl / (fill * o.qty)) if fill and o.qty \
                    else None

        record = {
            "prediction_id": pred.id, "company_id": pred.entity_id,
            "instrument": pred.instrument, "direction": pred.direction,
            "probability": pred.probability, "horizon_days": pred.horizon_days,
            "created_at": pred.created_at, "resolved_at": updated.resolved_at,
            "entry_price": entry, "exit_price": exit_px, "move": move,
            "outcome": outcome, "brier_component": brier,
            "market_return": (move / entry) if entry else None,
            "trade_pnl": trade_pnl, "trade_return": trade_return,
            "client_order_id": client_order_id, "as_of": as_of,
        }
        store.append(OUTCOME_STREAM, pred.id, record, status=outcome,
                     idem_key=f"outcome:{pred.id}", company_id=pred.entity_id,
                     ref_id=pred.id, ts=updated.resolved_at)
        resolved.append(pred.id)

    return {"as_of": as_of, "resolved": resolved, "resolved_count": len(resolved),
            "skipped_strategic": skipped_strategic}


def outcomes(store) -> List[dict]:
    return [r.payload for r in store.latest(OUTCOME_STREAM)]


def outcomes_for_company(store, company_id: str) -> List[dict]:
    return [r.payload for r in store.latest(OUTCOME_STREAM, company_id=company_id)]

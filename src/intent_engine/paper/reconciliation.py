"""Reconcile Alpaca PAPER state with the internal durable ledger.

PAPER TRADING — SIMULATED — NO REAL MONEY. The hosted model does NOT keep one
long-running process babysitting orders; Alpaca holds them through the day and
these jobs reconcile at intervals (mid-session, after close). Every function
here is:

  * IDEMPOTENT — re-running writes nothing new if state is unchanged (updates
    are keyed on the observed state signature in the durable store);
  * CATCH-UP — it reconciles ALL open/known records regardless of when they
    were created, so a delayed or skipped GitHub-Actions run is fully recovered
    by the next one. No order or mark is lost, none is duplicated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from intent_engine.paper.broker import Broker, deterministic_client_order_id
from intent_engine.paper.orders import OrderRepository, PaperOrder

POSITION_STREAM = "paper_position"
EQUITY_STREAM = "portfolio_equity"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def close_resolved_positions(broker: Broker, order_repo: OrderRepository,
                             pred_repo, *, as_of: str) -> Dict:
    """Close (flatten) each paper position whose prediction has resolved.

    A position is opened per prediction with a fixed horizon; when the
    prediction resolves the position must be exited, or the paper account's
    buying power is consumed without bound (a real "run-forever" failure the
    30-day replay surfaced: 82 positions held after resolution). Idempotent: a
    deterministic close client_order_id and a "close order already exists" guard
    mean re-running never double-closes. Catch-up: it closes every eligible
    position, so a skipped run is recovered by the next.
    """
    closed: List[str] = []
    for opening in order_repo.all_latest():
        if opening.action.startswith("close_") or not opening.is_filled:
            continue
        pred = pred_repo.get(opening.prediction_id)
        if pred is None or pred.outcome is None:
            continue                        # not resolved yet -> keep the position
        # already closed?
        siblings = order_repo.by_prediction(opening.prediction_id)
        if any(o.action.startswith("close_") for o in siblings):
            continue
        close_side = "sell" if opening.side == "buy" else "buy"
        close_action = ("close_long" if opening.action == "open_long"
                        else "close_short")
        cid = deterministic_client_order_id(
            prediction_id=opening.prediction_id,
            strategy_version=opening.strategy_version,
            instrument=opening.instrument,
            trading_date=(pred.resolved_at or as_of)[:10], action=close_action)
        if order_repo.get(cid) is not None:
            continue
        qty = opening.filled_qty or opening.qty
        order = PaperOrder(
            client_order_id=cid, prediction_id=opening.prediction_id,
            decision_id=opening.decision_id, company_id=opening.company_id,
            instrument=opening.instrument, action=close_action, side=close_side,
            qty=qty, trading_date=(pred.resolved_at or as_of)[:10],
            confidence=opening.confidence, regime=opening.regime,
            reasoning=f"horizon complete; closing position for prediction "
                      f"{opening.prediction_id}",
            strategy_version=opening.strategy_version, status="submitted",
            submitted_at=_now())
        order_repo.record_submission(order)
        bo = broker.submit_order(symbol=opening.instrument, qty=qty,
                                 side=close_side, client_order_id=cid)
        order_repo.record_update(order.apply_broker(bo))
        closed.append(cid)
    return {"closed": len(closed), "close_order_ids": closed}


def reconcile_orders(broker: Broker, order_repo: OrderRepository) -> Dict:
    """Update every OPEN local order from its Alpaca counterpart.

    Catch-up: iterates all locally-open orders (not just today's). Idempotent:
    record_update no-ops when the observed (status, fills) is unchanged.
    """
    updated: List[str] = []
    checked = 0
    for local in order_repo.open_orders():
        checked += 1
        bo = broker.get_order_by_client_id(local.client_order_id)
        if bo is None:
            continue
        new = local.apply_broker(bo)
        if (new.status != local.status
                or new.filled_qty != local.filled_qty
                or new.filled_avg_price != local.filled_avg_price):
            order_repo.record_update(new)
            updated.append(new.client_order_id)
    return {"checked_open": checked, "updated": updated,
            "updated_count": len(updated)}


def mark_positions(
    broker: Broker, store, *, as_of: str,
    price_at: Optional[Callable[[str, str], float]] = None,
    universe=None,
) -> Dict:
    """Snapshot Alpaca positions marked to market for `as_of`.

    One durable row per (symbol, as_of): re-running the same day is idempotent.
    `price_at(symbol, as_of)` supplies the closing mark; if omitted, Alpaca's
    own market_value is used.
    """
    snapshots = []
    for pos in broker.list_positions():
        mark = None
        if price_at is not None:
            try:
                mark = price_at(pos.symbol, as_of)
            except Exception:  # noqa: BLE001 - a missing mark is not fatal
                mark = None
        market_value = (mark * pos.qty) if mark is not None else pos.market_value
        unrealized = None
        if mark is not None:
            unrealized = (mark - pos.avg_entry_price) * pos.qty
        elif pos.unrealized_pl is not None:
            unrealized = pos.unrealized_pl
        company_id = None
        if universe is not None:
            c = universe.by_instrument(pos.symbol)
            company_id = c.company_id if c else None
        payload = {"symbol": pos.symbol, "qty": pos.qty,
                   "avg_entry_price": pos.avg_entry_price, "mark_price": mark,
                   "market_value": market_value, "unrealized_pl": unrealized,
                   "as_of": as_of, "company_id": company_id}
        rid = f"{pos.symbol}:{as_of}"
        store.append(POSITION_STREAM, rid, payload, status="marked",
                     idem_key=f"pos:{rid}", company_id=company_id,
                     ref_id=pos.symbol, ts=_now())
        snapshots.append(payload)
    return {"as_of": as_of, "positions": len(snapshots), "snapshots": snapshots}


def snapshot_equity(broker: Broker, store, *, as_of: str) -> Dict:
    """Snapshot portfolio equity for `as_of` from the Alpaca account, computing
    the daily return against the most recent prior snapshot. Idempotent per
    day (record_id = as_of)."""
    account = broker.get_account()
    try:
        equity = float(account.get("equity") or account.get("portfolio_value")
                       or 0.0)
    except (TypeError, ValueError):
        equity = 0.0

    prior = [r for r in store.latest(EQUITY_STREAM) if r.record_id < as_of]
    prior_equity = None
    if prior:
        latest_prior = max(prior, key=lambda r: r.record_id)
        prior_equity = latest_prior.payload.get("equity")
    daily_return = None
    if prior_equity:
        try:
            daily_return = (equity - float(prior_equity)) / float(prior_equity)
        except (TypeError, ValueError, ZeroDivisionError):
            daily_return = None

    payload = {"as_of": as_of, "equity": equity, "prior_equity": prior_equity,
               "daily_return": daily_return,
               "buying_power": account.get("buying_power")}
    store.append(EQUITY_STREAM, as_of, payload, status="snapshot",
                 idem_key=f"equity:{as_of}", ts=_now())
    return payload


def latest_equity(store) -> Optional[dict]:
    rows = store.latest(EQUITY_STREAM)
    if not rows:
        return None
    return max(rows, key=lambda r: r.record_id).payload

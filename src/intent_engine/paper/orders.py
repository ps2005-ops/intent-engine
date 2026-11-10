"""Paper orders — the durable, traceable record of every Alpaca paper order.

PAPER TRADING — SIMULATED — NO REAL MONEY. A PaperOrder links an Alpaca paper
order back to the internal prediction and Decision Record that produced it
(section 4's traceability requirement) and carries the full broker lifecycle
(submitted -> accepted -> filled / rejected / canceled).

Persistence is the durable append-only store (SQLite dev / Postgres prod), so
orders survive a fresh GitHub-Actions runner and a slept Render service:

  * the SUBMISSION is idempotent on `submit:{client_order_id}` — a twice-fired
    submit job writes exactly one submission row;
  * a status UPDATE is idempotent on the observed (status, filled_qty,
    filled_avg_price) signature — re-reconciling an unchanged order writes
    nothing, but a genuine change appends a new row (append-only, replayable).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

from intent_engine.paper.broker import BrokerOrder

STREAM = "paper_order"

# Local lifecycle status, distinct from (but derived from) Alpaca's status.
OPEN_STATUSES = {"pending", "submitted", "accepted", "new", "partially_filled",
                 "pending_new", "accepted_for_bidding"}
TERMINAL_STATUSES = {"filled", "canceled", "expired", "rejected",
                     "done_for_day", "replaced", "stopped"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PaperOrder(BaseModel):
    # -- identity / traceability (all linkable back to the prediction) --------
    client_order_id: str
    prediction_id: str
    decision_id: Optional[str] = None
    company_id: Optional[str] = None
    instrument: str
    action: str                         # "open_long" | "open_short"
    side: str                           # "buy" | "sell"
    qty: float
    trading_date: str                   # YYYY-MM-DD (NY trading day)
    horizon_days: Optional[int] = None
    confidence: float = 0.0
    regime: str = "unknown"
    reasoning: str = ""
    strategy_version: str = ""
    risk_rule_version: Optional[str] = None
    data_snapshot: dict = Field(default_factory=dict)
    # -- broker lifecycle -----------------------------------------------------
    status: str = "pending"
    broker_order_id: Optional[str] = None
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    reject_reason: Optional[str] = None
    submitted_at: Optional[str] = None
    updated_at: str = Field(default_factory=_now)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def is_filled(self) -> bool:
        return self.status == "filled"

    def apply_broker(self, bo: BrokerOrder) -> "PaperOrder":
        """Return a copy updated from an observed broker order state."""
        return self.model_copy(update={
            "status": bo.status,
            "broker_order_id": bo.broker_order_id or self.broker_order_id,
            "filled_qty": bo.filled_qty,
            "filled_avg_price": bo.filled_avg_price,
            "reject_reason": bo.reject_reason,
            "submitted_at": bo.submitted_at or self.submitted_at,
            "updated_at": _now()})


class OrderRepository:
    """Durable persistence for paper orders (append-only, latest-wins)."""

    def __init__(self, store):
        self.store = store

    def record_submission(self, order: PaperOrder) -> PaperOrder:
        """Persist the initial submission. Idempotent on the client_order_id —
        only ONE submission row can ever exist for a given order."""
        self.store.append(
            STREAM, order.client_order_id, order.model_dump(),
            status=order.status, idem_key=f"submit:{order.client_order_id}",
            company_id=order.company_id, ref_id=order.prediction_id,
            ts=order.updated_at)
        return order

    def record_update(self, order: PaperOrder) -> PaperOrder:
        """Persist a lifecycle update. Idempotent on the observed state
        signature: re-reconciling an unchanged order is a no-op, a real change
        appends a new row."""
        sig = (f"upd:{order.client_order_id}:{order.status}:{order.filled_qty}:"
               f"{order.filled_avg_price}")
        self.store.append(
            STREAM, order.client_order_id, order.model_dump(),
            status=order.status, idem_key=sig,
            company_id=order.company_id, ref_id=order.prediction_id,
            ts=order.updated_at)
        return order

    def get(self, client_order_id: str) -> Optional[PaperOrder]:
        rec = self.store.get(STREAM, client_order_id)
        return PaperOrder(**rec.payload) if rec else None

    def all_latest(self) -> List[PaperOrder]:
        return [PaperOrder(**r.payload) for r in self.store.latest(STREAM)]

    def open_orders(self) -> List[PaperOrder]:
        return [o for o in self.all_latest() if o.is_open]

    def by_prediction(self, prediction_id: str) -> List[PaperOrder]:
        return [PaperOrder(**r.payload)
                for r in self.store.latest(STREAM, ref_id=prediction_id)]

    def by_company(self, company_id: str) -> List[PaperOrder]:
        return [PaperOrder(**r.payload)
                for r in self.store.latest(STREAM, company_id=company_id)]

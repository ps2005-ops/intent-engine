"""Paper execution — turn eligible intents into Alpaca PAPER orders, durably.

PAPER TRADING — SIMULATED — NO REAL MONEY. This is the ONLY place an intent
becomes a (paper) order. Three guarantees it must uphold:

  1. PRIVATE COMPANIES NEVER TRADE. The intent's instrument is mapped back to a
     company in the universe; if that company `may_generate_order` is False
     (every private company, every not-yet-eligible public one, an unknown
     instrument), the order is REFUSED and the reason persisted. This is a
     backstop behind eligibility, not a substitute for it.
  2. NO DUPLICATES. The client_order_id is deterministic, so a twice-fired
     submit job returns the already-submitted order instead of doubling up.
  3. EVERY REJECTION IS PERSISTED (section 11) — no silent drops.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from intent_engine.paper.broker import Broker, deterministic_client_order_id
from intent_engine.paper.eligibility import PaperIntent
from intent_engine.paper.orders import OrderRepository, PaperOrder
from intent_engine.paper.portfolio import STARTING_EQUITY, position_size
from intent_engine.universe.companies import CompanyPredictionUniverse

REJECTION_STREAM = "paper_rejection"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OrderRefused(RuntimeError):
    """Execution refused to place an order (e.g. private company). Persisted."""


class PaperExecutionService:
    def __init__(self, store, broker: Broker,
                 universe: CompanyPredictionUniverse):
        self.store = store
        self.broker = broker
        self.universe = universe
        self.orders = OrderRepository(store)

    # -- rejection persistence (section 11) ----------------------------------
    def _reject(self, *, prediction_id: str, instrument: str, reason: str,
                rule: str, company_id: Optional[str] = None) -> None:
        rid = f"{prediction_id}:{instrument}:{rule}"
        self.store.append(
            REJECTION_STREAM, rid,
            {"prediction_id": prediction_id, "instrument": instrument,
             "reason": reason, "rule": rule, "company_id": company_id,
             "at": _now()},
            status="rejected", idem_key=f"reject:{rid}",
            company_id=company_id, ref_id=prediction_id)

    def record_rejection(self, *, prediction_id: str, instrument: str,
                         reason: str, rule: str,
                         company_id: Optional[str] = None) -> None:
        """Public: persist an eligibility rejection (section 11 — all rejection
        reasons are persisted, no silent drop)."""
        self._reject(prediction_id=prediction_id, instrument=instrument,
                     reason=reason, rule=rule, company_id=company_id)

    def rejections(self) -> List[dict]:
        return [r.payload for r in self.store.latest(REJECTION_STREAM)]

    # -- submit --------------------------------------------------------------
    def submit_intent(self, intent: PaperIntent, *, trading_date: str,
                      price: float, equity: float = STARTING_EQUITY
                      ) -> Optional[PaperOrder]:
        """Submit one eligible intent as a paper order. Returns the persisted
        order, or None if it was refused (reason persisted)."""
        company = self.universe.by_instrument(intent.instrument)
        cid_company = company.company_id if company else None

        # (1) hard safety backstop: only order-eligible companies trade
        if company is None:
            self._reject(prediction_id=intent.prediction_id,
                         instrument=intent.instrument,
                         reason=f"instrument {intent.instrument!r} maps to no "
                                "company in the universe",
                         rule="unknown_instrument")
            return None
        if not company.may_generate_order:
            self._reject(prediction_id=intent.prediction_id,
                         instrument=intent.instrument, company_id=cid_company,
                         reason=(f"company {company.company_id!r} is "
                                 f"{company.classification.value} — not order-"
                                 "eligible (private/ineligible never trades)"),
                         rule="not_order_eligible")
            return None

        action = f"open_{intent.direction}"        # open_long | open_short
        cid = deterministic_client_order_id(
            prediction_id=intent.prediction_id,
            strategy_version=intent.strategy_version,
            instrument=intent.instrument, trading_date=trading_date,
            action=action)

        # (2) idempotency: already submitted -> return it, don't double up
        existing = self.orders.get(cid)
        if existing is not None:
            return existing

        # (3) size; refuse (persisted) if the allocation rounds to zero shares
        alloc = position_size(equity, intent.confidence)
        qty = int(alloc // price) if price > 0 else 0
        if qty <= 0:
            self._reject(prediction_id=intent.prediction_id,
                         instrument=intent.instrument, company_id=cid_company,
                         reason=f"position size {alloc:.2f} < 1 share at "
                                f"price {price:.2f}",
                         rule="size_below_one_share")
            return None

        side = "buy" if intent.direction == "long" else "sell"
        order = PaperOrder(
            client_order_id=cid, prediction_id=intent.prediction_id,
            decision_id=intent.decision_id, company_id=cid_company,
            instrument=intent.instrument, action=action, side=side,
            qty=float(qty), trading_date=trading_date,
            horizon_days=intent.horizon_days, confidence=intent.confidence,
            regime=intent.regime, reasoning=intent.reasoning,
            strategy_version=intent.strategy_version,
            risk_rule_version=intent.risk_rule_version,
            data_snapshot=dict(intent.data_snapshot),
            status="submitted", submitted_at=_now())
        self.orders.record_submission(order)

        # submit to Alpaca paper (dedup-safe by client_order_id) + persist state
        bo = self.broker.submit_order(symbol=intent.instrument, qty=float(qty),
                                      side=side, client_order_id=cid)
        updated = order.apply_broker(bo)
        self.orders.record_update(updated)
        return updated

    def submit_many(self, intents: List[PaperIntent], *, trading_date: str,
                    price_at, equity: float = STARTING_EQUITY) -> List[PaperOrder]:
        """Submit a batch. Per-intent isolation: one failure never aborts the
        rest (matches the runtime's per-item batch isolation discipline)."""
        placed: List[PaperOrder] = []
        for intent in intents:
            try:
                price = price_at(intent.instrument, trading_date)
                order = self.submit_intent(intent, trading_date=trading_date,
                                           price=price, equity=equity)
                if order is not None:
                    placed.append(order)
            except Exception as exc:  # noqa: BLE001 - isolate + persist
                self._reject(prediction_id=intent.prediction_id,
                             instrument=intent.instrument,
                             reason=f"{type(exc).__name__}: {exc}",
                             rule="submit_error")
        return placed

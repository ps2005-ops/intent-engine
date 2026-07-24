"""Paper-Trading Shadow Loop — the loop.

SHADOW ONLY. This service opens and closes *simulated* positions from the
engine's own predictions, scores the book in code, and — when the closed
book reveals a recurring, regime-specific mistake — proposes a learning
*candidate* into the Learning & Promotion Ledger. It never submits an
order, never touches real capital, and never modifies any generation path.
It has no order-submission method at all (a test asserts this).

The loop's wiring to the rest of the platform:

    prediction (core.prediction_ledger)  --open-->  PaperPosition
        │  carries prediction_id, decision_id, regime, confidence, reasoning
        ▼
    outcome (prediction resolved)         --close--> realized P&L, metrics
        ▼
    recurring loss in a regime            --propose--> LearningLedger
        (source="paper_trade")                         candidate

So every paper trade is explainable back to a prediction/decision, and the
book becomes an objective feedback source for the learning brain — without
opening any of the founder's live-trading walls.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from intent_engine.events import CompanyEventBus
from intent_engine.learning.records import SuccessCriterion
from intent_engine.paper.ledger import DEFAULT_PAPER_PATH, PaperStore
from intent_engine.paper.portfolio import (
    STARTING_EQUITY, PortfolioMetrics, compute_metrics, position_size,
    realized_pnl,
)
from intent_engine.paper.records import Direction, ExitReason, PaperPosition

PRODUCER = "paper_trading"

# When to flag a regime as a recurring mistake worth a learning candidate:
# at least this many closed trades in the regime AND a losing win-rate.
_MIN_TRADES_FOR_CANDIDATE = 3


class PaperTradingLoop:
    def __init__(self, path: Union[str, Path] = DEFAULT_PAPER_PATH, *,
                 bus: Optional[CompanyEventBus] = None,
                 starting_equity: float = STARTING_EQUITY):
        self.store = PaperStore(path)
        self.bus = bus
        self.starting_equity = starting_equity

    # --- open ----------------------------------------------------------------
    def open_position(
        self, *, prediction_id: str, instrument: str, direction: Direction,
        entry_price: float, regime: str, confidence: float, reasoning: str,
        decision_id: Optional[str] = None,
        stop_price: Optional[float] = None, target_price: Optional[float] = None,
        actor_id: str = "paper_loop",
    ) -> PaperPosition:
        equity = self.current_equity()
        alloc = position_size(equity, confidence)
        size = (alloc / entry_price) if entry_price > 0 else 0.0
        position = PaperPosition(
            prediction_id=prediction_id, decision_id=decision_id,
            regime=regime, confidence=confidence, reasoning=reasoning,
            instrument=instrument, direction=direction, entry_price=entry_price,
            size=size, stop_price=stop_price, target_price=target_price,
            status="open")
        position.require_traceable()
        self.store.append(position)
        self._publish("paper.position_opened", position, actor_id=actor_id,
                      payload={"instrument": instrument, "direction": direction,
                               "confidence": confidence, "regime": regime,
                               "size": size, "entry_price": entry_price})
        return position

    def open_from_intent(self, intent, *, entry_price: float,
                         stop_price: Optional[float] = None,
                         target_price: Optional[float] = None,
                         actor_id: str = "market_loop") -> PaperPosition:
        """Open a position from an eligibility PaperIntent, carrying its full
        provenance (strategy/risk versions, horizon, data snapshot). Idempotent
        per prediction: if the prediction already has an OPEN position, that
        position is returned rather than opening a duplicate."""
        existing = [p for p in self.store.by_prediction(intent.prediction_id)
                    if p.status == "open"]
        if existing:
            return existing[0]
        equity = self.current_equity()
        alloc = position_size(equity, intent.confidence)
        size = (alloc / entry_price) if entry_price > 0 else 0.0
        position = PaperPosition(
            prediction_id=intent.prediction_id, decision_id=intent.decision_id,
            regime=intent.regime, confidence=intent.confidence,
            reasoning=intent.reasoning, instrument=intent.instrument,
            direction=intent.direction, entry_price=entry_price, size=size,
            stop_price=stop_price, target_price=target_price, status="open",
            horizon_days=intent.horizon_days,
            strategy_version=intent.strategy_version,
            risk_rule_version=intent.risk_rule_version, opened_from="prediction",
            data_snapshot=dict(intent.data_snapshot))
        position.require_traceable()
        self.store.append(position)
        self._publish("paper.position_opened", position, actor_id=actor_id,
                      payload={"instrument": intent.instrument,
                               "direction": intent.direction,
                               "confidence": intent.confidence,
                               "regime": intent.regime, "size": size,
                               "entry_price": entry_price,
                               "strategy_version": intent.strategy_version,
                               "opened_from": "prediction"})
        return position

    # --- close ---------------------------------------------------------------
    def close_position(
        self, position_id: str, *, exit_price: float, exit_reason: ExitReason,
        regime_at_exit: Optional[str] = None, actor_id: str = "paper_loop",
    ) -> PaperPosition:
        current = self.store.get(position_id)
        if current is None:
            raise ValueError(f"no paper position {position_id!r}")
        if current.status == "closed":
            raise ValueError(f"paper position {position_id!r} already closed")
        move = exit_price - current.entry_price
        if current.direction == "short":
            move = -move
        pnl = move * current.size
        return_pct = (move / current.entry_price) if current.entry_price else 0.0
        closed = current.model_copy(update={
            "status": "closed", "closed_at": _now(), "exit_price": exit_price,
            "exit_reason": exit_reason, "pnl": pnl, "return_pct": return_pct,
            "regime_at_exit": regime_at_exit or current.regime})
        self.store.append(closed)
        self._publish("paper.position_closed", closed, actor_id=actor_id,
                      payload={"exit_reason": exit_reason, "pnl": pnl,
                               "return_pct": return_pct,
                               "regime": closed.regime_at_exit})
        return closed

    # --- metrics -------------------------------------------------------------
    def metrics(self) -> PortfolioMetrics:
        return compute_metrics(self.store.closed_positions(),
                               self.starting_equity)

    def current_equity(self) -> float:
        return self.starting_equity + sum(
            realized_pnl(p) for p in self.store.closed_positions())

    # --- connection to the learning brain ------------------------------------
    def emit_learning_candidates(self, learning_ledger) -> List[str]:
        """Discover recurring, regime-specific mistakes in the CLOSED book
        and propose them as learning candidates (source='paper_trade').
        Read-only w.r.t. production: it proposes, it never promotes. Returns
        the ids of any candidates proposed. Idempotent by regime signature —
        re-running does not duplicate a still-open candidate."""
        closed = self.store.closed_positions()
        by_regime: Dict[str, List[PaperPosition]] = {}
        for p in closed:
            by_regime.setdefault(p.regime_at_exit or p.regime, []).append(p)

        # A regime with a still-open (non-terminal) paper_trade candidate is
        # not re-proposed — the store append is not itself idempotent, so
        # this guard is what makes re-running the loop safe.
        open_regimes = {
            c.provenance.get("regime")
            for c in learning_ledger.list(source="paper_trade")
            if c.status in ("proposed", "evaluated")}

        proposed: List[str] = []
        for regime, trades in by_regime.items():
            if len(trades) < _MIN_TRADES_FOR_CANDIDATE:
                continue
            if regime in open_regimes:
                continue   # already has an open candidate under review
            wins = [t for t in trades if (t.pnl or 0) > 0]
            win_rate = len(wins) / len(trades)
            if win_rate >= 0.5:
                continue   # not a recurring mistake
            key = f"paper_trade:recurring_loss:{regime}"
            candidate = learning_ledger.propose(
                source="paper_trade", target=f"regime:{regime}",
                statement=(f"The engine loses money in the {regime!r} regime "
                           f"(win rate {win_rate:.0%} over {len(trades)} "
                           "paper trades)"),
                hypothesis=("confidence or direction in this regime is "
                            "systematically miscalibrated"),
                baseline_ref="paper_book.current",
                success_criteria=[SuccessCriterion(
                    metric="win_rate", comparator=">=", threshold=0.5,
                    direction="higher_better")],
                param_diff={"regime": regime, "review": "confidence_mapping"},
                provenance={"regime": regime, "trades": len(trades),
                            "win_rate": win_rate,
                            "position_ids": [t.id for t in trades]},
                idempotency_key=key)
            proposed.append(candidate.id)
        return proposed

    # --- internals -----------------------------------------------------------
    def _publish(self, event_type: str, position: PaperPosition, *,
                 actor_id: str, payload: Dict[str, Any]) -> None:
        if self.bus is None:
            return
        self.bus.publish(
            event_type, subject_type="paper_position", subject_id=position.id,
            producer=PRODUCER, actor_type="system", actor_id=actor_id,
            source="system", payload=payload,
            prediction_id=position.prediction_id,
            decision_id=position.decision_id,
            idempotency_key=f"{event_type}:{position.id}")


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

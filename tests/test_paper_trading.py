"""Paper-Trading Shadow Loop — traceability, code-computed metrics, and the
connection to the learning brain. Simulation only; no order surface exists.
"""
import math

import pytest

from intent_engine.events import CompanyEventBus
from intent_engine.learning import LearningLedger
from intent_engine.paper import PaperTradingLoop
from intent_engine.paper.portfolio import (
    compute_metrics, max_drawdown, position_size, realized_pnl,
)
from intent_engine.paper.records import PaperPosition


def _loop(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    return PaperTradingLoop(tmp_path / "paper.db", bus=bus), bus


# --- portfolio math (pure, in code) -----------------------------------------

def test_position_size_scales_with_confidence():
    assert position_size(100_000, 0.5) == 0.0        # no edge -> no risk
    assert position_size(100_000, 1.0) == pytest.approx(10_000)   # full frac
    assert 0 < position_size(100_000, 0.75) < 10_000


def test_realized_pnl_long_and_short():
    long = PaperPosition(prediction_id="p", regime="r", confidence=0.8,
                         reasoning="x", instrument="SPY", direction="long",
                         entry_price=100, size=10, status="closed",
                         exit_price=110)
    short = long.model_copy(update={"direction": "short"})
    assert realized_pnl(long) == pytest.approx(100)      # +10 * 10
    assert realized_pnl(short) == pytest.approx(-100)


def test_max_drawdown():
    assert max_drawdown([100, 120, 90, 130]) == pytest.approx((120 - 90) / 120)
    assert max_drawdown([100]) is None


def test_metrics_over_mixed_book():
    def pos(entry, exit_, regime, direction="long"):
        return PaperPosition(prediction_id="p", regime=regime, confidence=0.8,
                             reasoning="x", instrument="SPY",
                             direction=direction, entry_price=entry, size=1,
                             status="closed", exit_price=exit_,
                             return_pct=(exit_ - entry) / entry,
                             regime_at_exit=regime)
    book = [pos(100, 110, "risk_on"), pos(100, 90, "risk_off"),
            pos(100, 105, "risk_on")]
    m = compute_metrics(book, starting=1000)
    assert m.closed_count == 3
    assert m.win_rate == pytest.approx(2 / 3)
    assert m.profit_factor == pytest.approx((10 + 5) / 10)
    assert m.regime_attribution["risk_on"] == pytest.approx(15)
    assert m.regime_attribution["risk_off"] == pytest.approx(-10)
    assert m.sharpe is not None and math.isfinite(m.sharpe)


def test_empty_book_metrics_are_honest_none():
    m = compute_metrics([], starting=1000)
    assert m.closed_count == 0 and m.win_rate is None
    assert m.sharpe is None and m.ending_equity == 1000


# --- the loop ----------------------------------------------------------------

def test_open_is_traceable_and_publishes(tmp_path):
    loop, bus = _loop(tmp_path)
    p = loop.open_position(prediction_id="pred-1", instrument="SPY",
                           direction="long", entry_price=100, regime="risk_on",
                           confidence=0.8, reasoning="mechanism X",
                           decision_id="DEC-2026-000001")
    assert p.status == "open" and p.decision_id == "DEC-2026-000001"
    ev = [e for e in bus.store.read_all()
          if e.event_type == "paper.position_opened"]
    assert len(ev) == 1
    # the event carries the prediction + decision linkage (no black box)
    assert ev[0].prediction_id == "pred-1"
    assert ev[0].decision_id == "DEC-2026-000001"


def test_untraceable_position_is_rejected(tmp_path):
    loop, _ = _loop(tmp_path)
    with pytest.raises(ValueError, match="not traceable"):
        loop.open_position(prediction_id="", instrument="SPY",
                           direction="long", entry_price=100, regime="",
                           confidence=0.8, reasoning="")


def test_close_computes_pnl_and_equity(tmp_path):
    loop, bus = _loop(tmp_path)
    p = loop.open_position(prediction_id="pred-1", instrument="SPY",
                           direction="long", entry_price=100, regime="risk_on",
                           confidence=1.0, reasoning="x")
    closed = loop.close_position(p.id, exit_price=110,
                                 exit_reason="prediction_resolved")
    assert closed.status == "closed"
    assert closed.return_pct == pytest.approx(0.10)
    assert loop.current_equity() > loop.starting_equity
    assert loop.metrics().closed_count == 1


def test_cannot_double_close(tmp_path):
    loop, _ = _loop(tmp_path)
    p = loop.open_position(prediction_id="pred-1", instrument="SPY",
                           direction="long", entry_price=100, regime="r",
                           confidence=0.8, reasoning="x")
    loop.close_position(p.id, exit_price=110, exit_reason="target")
    with pytest.raises(ValueError, match="already closed"):
        loop.close_position(p.id, exit_price=120, exit_reason="target")


def test_recurring_loss_emits_learning_candidate(tmp_path):
    loop, bus = _loop(tmp_path)
    led = LearningLedger(tmp_path / "learning.db", bus=bus)
    for i in range(4):
        p = loop.open_position(prediction_id=f"pred-{i}", instrument="SPY",
                               direction="long", entry_price=100,
                               regime="risk_off", confidence=0.8,
                               reasoning="x")
        loop.close_position(p.id, exit_price=95,
                            exit_reason="prediction_resolved")
    ids = loop.emit_learning_candidates(led)
    assert len(ids) == 1
    cand = led.get(ids[0])
    assert cand.source == "paper_trade" and cand.status == "proposed"
    assert cand.provenance["regime"] == "risk_off"
    # idempotent: a still-open candidate for the regime is not re-proposed
    assert loop.emit_learning_candidates(led) == []


def test_winning_regime_emits_no_candidate(tmp_path):
    loop, bus = _loop(tmp_path)
    led = LearningLedger(tmp_path / "learning.db", bus=bus)
    for i in range(4):
        p = loop.open_position(prediction_id=f"pred-{i}", instrument="SPY",
                               direction="long", entry_price=100,
                               regime="risk_on", confidence=0.8, reasoning="x")
        loop.close_position(p.id, exit_price=110, exit_reason="target")
    assert loop.emit_learning_candidates(led) == []


def test_loop_has_no_order_submission_surface():
    """Shadow only: nothing here submits a live order."""
    surface = [m for m in dir(PaperTradingLoop)
               if not m.startswith("_")
               and any(w in m.lower() for w in ("order", "submit", "broker",
                                                "buy", "sell", "execute"))]
    assert surface == []

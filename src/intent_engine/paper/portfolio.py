"""Paper-Trading Shadow Loop — portfolio mathematics, in code.

Every number here is computed deterministically from closed positions —
never asserted by a model, the same "code decides / computes" discipline
as the prediction ledger's Brier math. Pure functions over a list of
closed PaperPositions so they are trivially testable and carry no state.

Metrics the founder's architecture names: position sizing, equity,
drawdown, Sharpe, Sortino, profit factor, win rate, expected value,
rolling performance, market-regime attribution.
"""
from __future__ import annotations

import math
from typing import Dict, List, NamedTuple, Optional

from intent_engine.paper.records import PaperPosition

# Fixed starting equity for the shadow book. A round number; the loop is a
# relative-performance instrument, not a claim about capital.
STARTING_EQUITY = 100_000.0


def position_size(equity: float, confidence: float, *,
                  max_fraction: float = 0.10) -> float:
    """Confidence-scaled fixed-fraction sizing. A 50% confidence call risks
    nothing (no edge); a 100% call risks the full max_fraction. Linear and
    explainable on purpose — the point is traceability, not a clever
    sizing model. Returns the equity amount to allocate."""
    edge = max(0.0, (confidence - 0.5) * 2.0)   # 0.5->0, 1.0->1
    return equity * max_fraction * edge


def realized_pnl(position: PaperPosition) -> float:
    """Signed P&L in equity units for a closed position."""
    if position.exit_price is None:
        return 0.0
    move = position.exit_price - position.entry_price
    if position.direction == "short":
        move = -move
    return move * position.size


def _returns(closed: List[PaperPosition]) -> List[float]:
    return [p.return_pct for p in closed if p.return_pct is not None]


class PortfolioMetrics(NamedTuple):
    closed_count: int
    starting_equity: float
    ending_equity: float
    total_pnl: float
    win_rate: Optional[float]
    profit_factor: Optional[float]     # gross wins / gross losses
    expected_value: Optional[float]    # mean return per trade
    sharpe: Optional[float]            # per-trade, unannualized
    sortino: Optional[float]
    max_drawdown: Optional[float]      # fraction, >= 0
    regime_attribution: Dict[str, float]   # regime -> total pnl


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs)


def _std(xs: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _downside_std(xs: List[float]) -> Optional[float]:
    downs = [x for x in xs if x < 0]
    if len(downs) < 1:
        return None
    return math.sqrt(sum(x ** 2 for x in downs) / len(downs))


def max_drawdown(equity_curve: List[float]) -> Optional[float]:
    """Largest peak-to-trough fractional decline along the equity curve."""
    if len(equity_curve) < 2:
        return None
    peak = equity_curve[0]
    worst = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def equity_curve(closed: List[PaperPosition],
                 starting: float = STARTING_EQUITY) -> List[float]:
    """Running equity after each closed position, in chronological order."""
    ordered = sorted(closed, key=lambda p: p.closed_at or "")
    curve = [starting]
    running = starting
    for p in ordered:
        running += realized_pnl(p)
        curve.append(running)
    return curve


def compute_metrics(closed: List[PaperPosition],
                    starting: float = STARTING_EQUITY) -> PortfolioMetrics:
    closed = [p for p in closed if p.status == "closed"]
    curve = equity_curve(closed, starting)
    ending = curve[-1]
    total_pnl = ending - starting

    if not closed:
        return PortfolioMetrics(
            closed_count=0, starting_equity=starting, ending_equity=starting,
            total_pnl=0.0, win_rate=None, profit_factor=None,
            expected_value=None, sharpe=None, sortino=None,
            max_drawdown=None, regime_attribution={})

    pnls = [realized_pnl(p) for p in closed]
    rets = _returns(closed)
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]

    gross_win = sum(wins)
    gross_loss = -sum(losses)   # positive magnitude
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_win > 0 else None)

    sd = _std(rets) if rets else None
    dsd = _downside_std(rets) if rets else None
    ev = _mean(rets) if rets else None
    sharpe = (ev / sd) if (ev is not None and sd not in (None, 0)) else None
    sortino = (ev / dsd) if (ev is not None and dsd not in (None, 0)) else None

    regime_attr: Dict[str, float] = {}
    for p, pnl in zip(closed, pnls):
        regime_attr[p.regime] = regime_attr.get(p.regime, 0.0) + pnl

    return PortfolioMetrics(
        closed_count=len(closed), starting_equity=starting,
        ending_equity=ending, total_pnl=total_pnl,
        win_rate=len(wins) / len(closed),
        profit_factor=profit_factor, expected_value=ev,
        sharpe=sharpe, sortino=sortino,
        max_drawdown=max_drawdown(curve),
        regime_attribution=regime_attr)

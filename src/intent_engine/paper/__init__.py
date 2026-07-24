"""Paper-Trading Shadow Loop (unified-learning platform).

SIMULATION ONLY — no broker, no real money, no order surface. Turns the
engine's predictions into tracked paper positions (each traceable to
prediction/decision/regime/confidence/reasoning), scores the book in code
(equity, drawdown, Sharpe, Sortino, profit factor, win rate, EV, regime
attribution), and feeds recurring regime-specific mistakes to the Learning
& Promotion Ledger as candidates. The first objective feedback source for
the learning brain; it opens none of the live-trading walls.
"""
from intent_engine.paper.records import (  # noqa: F401
    Direction, ExitReason, PaperPosition, PositionStatus,
)
from intent_engine.paper.portfolio import (  # noqa: F401
    STARTING_EQUITY, PortfolioMetrics, compute_metrics, equity_curve,
    max_drawdown, position_size, realized_pnl,
)
from intent_engine.paper.ledger import (  # noqa: F401
    DEFAULT_PAPER_PATH, PaperStore,
)
from intent_engine.paper.service import PRODUCER, PaperTradingLoop  # noqa: F401

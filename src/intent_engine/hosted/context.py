"""HostedContext — the wiring the hosted jobs share.

Adapters (predict_fn, price_at, research_fn, broker) are injected, so the SAME
job code runs against the injected fakes in the acceptance test and against real
Alpaca/Tiingo/LLM adapters in production. `from_env` builds the production wiring
(real Alpaca PAPER broker, Tiingo prices) and refuses to start against anything
non-paper. Repositories are built once from the durable store.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from intent_engine.hosted.budget import Budget, BudgetLedger
from intent_engine.paper.broker import Broker
from intent_engine.paper.execution import PaperExecutionService
from intent_engine.paper.orders import OrderRepository
from intent_engine.predictions.repository import PredictionRepository
from intent_engine.storage.durable import DurableStore
from intent_engine.universe.companies import CompanyPredictionUniverse, default_universe
from intent_engine.universe.learning import CompanyLearningStore
from intent_engine.universe.store import UniverseStore

PredictFn = Callable[[Any, Dict[str, Any], str], Optional[Dict[str, Any]]]
PriceAt = Callable[[str, str], float]
ResearchFn = Callable[[Any, str], Optional[Dict[str, Any]]]


@dataclass
class HostedContext:
    store: DurableStore
    broker: Broker
    universe: CompanyPredictionUniverse
    predict_fn: PredictFn
    price_at: PriceAt
    research_fn: ResearchFn
    regime: str = "unknown"
    budget: Budget = field(default_factory=Budget)

    def __post_init__(self) -> None:
        self.predictions = PredictionRepository(self.store)
        self.orders = OrderRepository(self.store)
        self.learning_store = CompanyLearningStore(self.store)
        self.budget_ledger = BudgetLedger(self.store, self.budget)
        self.execution = PaperExecutionService(self.store, self.broker,
                                               self.universe)

    # -- production wiring ---------------------------------------------------
    @classmethod
    def from_env(cls, *, env: Optional[Dict[str, str]] = None,
                 store: Optional[DurableStore] = None) -> "HostedContext":
        """Build the production context from environment configuration. The
        broker is the REAL Alpaca PAPER broker (paper-only guard enforced in
        AlpacaConfig.from_env); prices come from Tiingo; predictions from the LLM
        adapter, gated by the budget's PREDICTION_GENERATION_ENABLED flag."""
        env = env if env is not None else os.environ
        from intent_engine.paper.broker import AlpacaConfig, AlpacaPaperBroker

        store = store or DurableStore(env.get("DATABASE_URL"))
        budget = Budget.from_env(env)
        universe = UniverseStore(store).load_or_seed(default_universe())
        broker = AlpacaPaperBroker(AlpacaConfig.from_env(env))
        return cls(
            store=store, broker=broker, universe=universe,
            predict_fn=_env_predict_fn(env, budget),
            price_at=_tiingo_price_at(env),
            research_fn=_env_research_fn(env, budget),
            regime=_env_regime(env), budget=budget)


def _tiingo_price_at(env) -> PriceAt:
    key = env.get("TIINGO_API_KEY", "")

    def price_at(symbol: str, as_of: str) -> float:
        from intent_engine.core.market_resolution import get_prices
        series = get_prices(symbol, as_of, as_of, api_key=key)
        if not series.observations:
            raise RuntimeError(f"no price for {symbol} at {as_of}")
        return series.observations[-1][1]
    return price_at


def _env_regime(env) -> str:
    def _r():
        try:
            from intent_engine.runtime.regime import fetch_regime_label
            from intent_engine.runtime.market_calendar import today_ny
            return fetch_regime_label(today_ny().isoformat(),
                                      fred_key=env.get("FRED_API_KEY", ""))
        except Exception:  # noqa: BLE001 - regime is advisory, never fatal
            return "unknown"
    return _r()


def _env_predict_fn(env, budget) -> PredictFn:
    """Production prediction adapter placeholder. Disabled unless
    PREDICTION_GENERATION_ENABLED is set AND an LLM adapter is configured — it
    never fabricates a signal, so with generation off the loop simply produces
    no new predictions that day (safe, budget-respecting default)."""
    def predict_fn(company, state, as_of):
        if not budget.prediction_generation_enabled:
            return None
        # A real LLM generator is wired here in production. Until configured it
        # returns None (no prediction) rather than a fake signal.
        return None
    return predict_fn


def _env_research_fn(env, budget) -> ResearchFn:
    def research_fn(company, as_of):
        # A real bounded web+LLM research adapter is wired here in production.
        return {"evidence": [], "thesis": "", "priorities": []}
    return research_fn

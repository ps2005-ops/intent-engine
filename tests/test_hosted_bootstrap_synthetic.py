"""Historical bootstrap (leakage-safe, costed, labelled) + synthetic-from-failures."""
import tempfile
from datetime import date, timedelta

from intent_engine.hosted.bootstrap import BootstrapConfig, run_bootstrap
from intent_engine.hosted.context import HostedContext
from intent_engine.hosted.synthetic import run_synthetic_from_failures
from intent_engine.paper.broker import FakeAlpacaPaperBroker
from intent_engine.storage.durable import DurableStore
from intent_engine.universe.companies import default_universe
from intent_engine.universe.learning import CompanyLearningState, CompanyLearningStore

_DAYS = [(date(2026, 6, 1) + timedelta(days=i)).isoformat() for i in range(8)]
_IDX = {d: i for i, d in enumerate(_DAYS)}


def _rising_price(sym, day):
    return 100.0 + 3.0 * _IDX[day[:10]]        # monotonically rising


def _predict_up(company, state, as_of):
    return {"direction": "up", "probability": 0.8, "horizon_days": 1,
            "claim_text": "up"}


def test_bootstrap_is_walkforward_costed_and_labelled():
    store = DurableStore(f"sqlite:///{tempfile.mkdtemp()}/b.db")
    result = run_bootstrap(default_universe(), _predict_up, _rising_price,
                           _DAYS[:6], store=store,
                           config=BootstrapConfig(cost_bps=5, slippage_bps=5))
    assert result["label"] == "historical"
    assert result["proves_live_profitability"] is False
    assert result["train_dates"] >= 1 and result["test_dates"] >= 1
    shop = result["companies"]["shopify"]
    # rising prices -> every "up" call is correct, in AND out of sample
    assert shop["in_sample_accuracy"] == 1.0
    assert shop["out_of_sample_accuracy"] == 1.0
    # costs+slippage were charged (net < gross); persisted + labelled historical
    rows = [r.payload for r in store.latest("bootstrap_outcome")]
    assert rows and all(r["label"] == "historical" for r in rows)
    assert all(r["net_return"] < r["gross_return"] for r in rows)


def test_bootstrap_does_not_leak_future_prices():
    seen = []

    def price_spy(sym, day):
        seen.append(day)
        return _rising_price(sym, day)

    run_bootstrap(default_universe(), _predict_up, price_spy, _DAYS[:5])
    # every price lookup is at a created or resolve date within the window —
    # never a date beyond the last resolve date used (no forward leak)
    assert max(seen) <= _DAYS[5]      # resolve of the last (index 4) date


def test_synthetic_scenarios_from_real_failures():
    store = DurableStore(f"sqlite:///{tempfile.mkdtemp()}/s.db")
    ctx = HostedContext(
        store=store, broker=FakeAlpacaPaperBroker(), universe=default_universe(),
        predict_fn=lambda *a: None, price_at=lambda s, d: 1.0,
        research_fn=lambda *a: {}, regime="calm")
    # seed a company with a real, sample-backed weakness
    CompanyLearningStore(store).save(CompanyLearningState(
        company_id="duolingo", peer_group="consumer_subscription",
        resolved_count=5, directional_accuracy=0.2, avg_confidence=0.8,
        calibration_error=0.6, paper_pnl=-40.0))
    result = run_synthetic_from_failures(ctx, "2026-07-11")
    assert result["scenarios"] >= 1
    assert result["proves_market_profitability"] is False
    runs = [r.payload for r in store.latest("synthetic_run")]
    assert runs and any(s["company_id"] == "duolingo"
                        for s in runs[-1]["scenarios"])

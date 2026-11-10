"""Alpaca PAPER broker + durable order repository — all via the injected fake.

No real network call anywhere. Proves: the live host is refused, client_order_id
is deterministic (the twice-fired-job guard), the fake dedupes like Alpaca, and
orders persist durably with idempotent submission + reconciliation.
"""
import pytest

from intent_engine.paper.broker import (
    AlpacaConfig,
    FakeAlpacaPaperBroker,
    LiveTradingRejected,
    PAPER_BASE_URL,
    assert_paper_only,
    deterministic_client_order_id,
)
from intent_engine.paper.orders import OrderRepository, PaperOrder
from intent_engine.storage.durable import DurableStore


# --- paper-only wall ---------------------------------------------------------

def test_assert_paper_only_allows_paper_rejects_live():
    assert_paper_only(PAPER_BASE_URL)                       # ok
    with pytest.raises(LiveTradingRejected):
        assert_paper_only("https://api.alpaca.markets")     # the live host
    with pytest.raises(LiveTradingRejected):
        assert_paper_only("https://evil.example.com")


def test_config_from_env_rejects_live_and_requires_keys():
    with pytest.raises(LiveTradingRejected):
        AlpacaConfig.from_env({"ALPACA_PAPER_BASE_URL": "https://api.alpaca.markets",
                               "ALPACA_PAPER_API_KEY": "k",
                               "ALPACA_PAPER_SECRET_KEY": "s"})
    with pytest.raises(RuntimeError):
        AlpacaConfig.from_env({"ALPACA_PAPER_BASE_URL": PAPER_BASE_URL})  # no keys
    cfg = AlpacaConfig.from_env({"ALPACA_PAPER_API_KEY": "k",
                                 "ALPACA_PAPER_SECRET_KEY": "s"})
    assert cfg.base_url == PAPER_BASE_URL


# --- deterministic client_order_id (idempotency seed) ------------------------

def test_client_order_id_is_deterministic_and_input_sensitive():
    kw = dict(prediction_id="pred1", strategy_version="v1", instrument="SHOP",
              trading_date="2026-07-24", action="open_long")
    a = deterministic_client_order_id(**kw)
    b = deterministic_client_order_id(**kw)
    assert a == b                                    # stable across calls
    assert a.startswith("ie-open_long-SHOP-2026-07-24-")
    assert len(a) <= 128
    # any input change -> different id
    c = deterministic_client_order_id(**{**kw, "trading_date": "2026-07-25"})
    assert c != a


# --- fake broker mirrors Alpaca dedup + fills --------------------------------

def test_fake_broker_dedupes_and_fills():
    b = FakeAlpacaPaperBroker(equity=100_000)
    o1 = b.submit_order(symbol="SHOP", qty=10, side="buy", client_order_id="cid1")
    o2 = b.submit_order(symbol="SHOP", qty=10, side="buy", client_order_id="cid1")
    assert o1.broker_order_id == o2.broker_order_id           # dedup
    assert len(b.list_orders()) == 1
    b.simulate_fill("cid1", price=95.0)
    filled = b.get_order_by_client_id("cid1")
    assert filled.is_filled and filled.filled_avg_price == 95.0
    pos = b.list_positions()
    assert len(pos) == 1 and pos[0].symbol == "SHOP" and pos[0].qty == 10


def test_fake_broker_reject():
    b = FakeAlpacaPaperBroker()
    b.submit_order(symbol="NET", qty=5, side="buy", client_order_id="cid2")
    b.simulate_reject("cid2", "insufficient buying power")
    o = b.get_order_by_client_id("cid2")
    assert o.status == "rejected" and o.reject_reason == "insufficient buying power"


# --- durable order repository ------------------------------------------------

def _order(**over):
    base = dict(client_order_id="cid1", prediction_id="pred1",
                company_id="shopify", instrument="SHOP", action="open_long",
                side="buy", qty=10.0, trading_date="2026-07-24",
                strategy_version="v1", confidence=0.8, regime="calm")
    base.update(over)
    return PaperOrder(**base)


def test_order_submission_is_idempotent(tmp_path):
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    repo = OrderRepository(store)
    repo.record_submission(_order())
    repo.record_submission(_order())          # twice-fired submit
    assert store.count("paper_order") == 1     # exactly one submission row


def test_order_update_idempotent_on_state_but_appends_real_change(tmp_path):
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    repo = OrderRepository(store)
    repo.record_submission(_order())
    filled = _order(status="filled", filled_qty=10.0, filled_avg_price=95.0)
    repo.record_update(filled)
    repo.record_update(filled)                # re-reconcile same state -> no-op
    # 1 submission + 1 fill update = 2 rows; the 2nd reconcile wrote nothing
    assert store.count("paper_order") == 2
    latest = repo.get("cid1")
    assert latest.is_filled and latest.filled_avg_price == 95.0


def test_repo_lookups_by_prediction_and_company(tmp_path):
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    repo = OrderRepository(store)
    repo.record_submission(_order(client_order_id="cidA", prediction_id="pA"))
    repo.record_submission(_order(client_order_id="cidB", prediction_id="pB",
                                  company_id="cloudflare", instrument="NET"))
    assert {o.client_order_id for o in repo.by_prediction("pA")} == {"cidA"}
    assert {o.client_order_id for o in repo.by_company("cloudflare")} == {"cidB"}
    assert len(repo.all_latest()) == 2

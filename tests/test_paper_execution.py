"""Paper execution + reconciliation — via the injected fake broker (no network).

Proves the three execution guarantees (private/ineligible refused + persisted,
deterministic idempotent submission, rejections persisted) and idempotent,
catch-up reconciliation of orders / positions / equity.
"""
from intent_engine.paper.broker import (
    FakeAlpacaPaperBroker,
    deterministic_client_order_id,
)
from intent_engine.paper.eligibility import PaperIntent
from intent_engine.paper.execution import PaperExecutionService
from intent_engine.paper.orders import OrderRepository
from intent_engine.paper.reconciliation import (
    close_resolved_positions,
    mark_positions,
    reconcile_orders,
    snapshot_equity,
)
from intent_engine.predictions.generation import build_prediction
from intent_engine.predictions.repository import PredictionRepository
from intent_engine.predictions.resolution import resolve_due
from intent_engine.storage.durable import DurableStore
from intent_engine.universe.companies import (
    CompanyClass,
    CompanyProfile,
    CompanyPredictionUniverse,
)

TRADING_DATE = "2026-07-24"


def _universe():
    return CompanyPredictionUniverse(companies=[
        CompanyProfile(company_id="shopify", canonical_name="Shopify",
                       classification=CompanyClass.PUBLIC_AND_TRADABLE,
                       is_public=True, ticker="SHOP", tradable_instrument="SHOP",
                       paper_trading_eligible=True),
        CompanyProfile(company_id="freshco", canonical_name="Fresh IPO",
                       classification=CompanyClass.PUBLIC_BUT_NOT_ELIGIBLE,
                       is_public=True, ticker="FRSH", tradable_instrument="FRSH",
                       paper_trading_eligible=False),
    ]).validate()


def _intent(instrument="SHOP", direction="long", confidence=0.8, pid="pred1"):
    return PaperIntent(
        prediction_id=pid, decision_id="dec1", instrument=instrument,
        direction=direction, confidence=confidence, regime="calm",
        reasoning="thesis", horizon_days=21, created_at="2026-07-24T12:00:00")


def _svc(tmp_path, broker):
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    return PaperExecutionService(store, broker, _universe()), store


# --- submission --------------------------------------------------------------

def test_public_tradable_intent_places_order(tmp_path):
    broker = FakeAlpacaPaperBroker(equity=100_000)
    svc, store = _svc(tmp_path, broker)
    order = svc.submit_intent(_intent(), trading_date=TRADING_DATE, price=95.0,
                              equity=100_000)
    assert order is not None and order.company_id == "shopify"
    assert order.side == "buy" and order.qty > 0
    assert order.client_order_id == deterministic_client_order_id(
        prediction_id="pred1", strategy_version=order.strategy_version,
        instrument="SHOP", trading_date=TRADING_DATE, action="open_long")
    # the order is live at the broker
    assert broker.get_order_by_client_id(order.client_order_id) is not None


def test_submission_is_idempotent_twice_fired(tmp_path):
    broker = FakeAlpacaPaperBroker()
    svc, store = _svc(tmp_path, broker)
    a = svc.submit_intent(_intent(), trading_date=TRADING_DATE, price=95.0)
    b = svc.submit_intent(_intent(), trading_date=TRADING_DATE, price=95.0)
    assert a.client_order_id == b.client_order_id
    assert len(broker.list_orders()) == 1           # one order at the broker
    assert len(OrderRepository(store).all_latest()) == 1


def test_ineligible_public_company_is_refused_and_persisted(tmp_path):
    broker = FakeAlpacaPaperBroker()
    svc, store = _svc(tmp_path, broker)
    order = svc.submit_intent(_intent(instrument="FRSH"),
                              trading_date=TRADING_DATE, price=20.0)
    assert order is None
    assert broker.list_orders() == []               # nothing submitted
    reasons = svc.rejections()
    assert any(r["rule"] == "not_order_eligible" for r in reasons)


def test_unknown_instrument_refused(tmp_path):
    broker = FakeAlpacaPaperBroker()
    svc, _ = _svc(tmp_path, broker)
    assert svc.submit_intent(_intent(instrument="ZZZZ"),
                             trading_date=TRADING_DATE, price=10.0) is None
    assert any(r["rule"] == "unknown_instrument" for r in svc.rejections())


def test_submit_many_isolates_failures(tmp_path):
    broker = FakeAlpacaPaperBroker()
    svc, store = _svc(tmp_path, broker)
    intents = [_intent(pid="pA"), _intent(instrument="FRSH", pid="pB"),
               _intent(pid="pC", instrument="SHOP")]
    prices = {"SHOP": 95.0, "FRSH": 20.0}
    placed = svc.submit_many(intents, trading_date=TRADING_DATE,
                             price_at=lambda s, d: prices[s])
    # pA and pC placed (SHOP), pB refused (ineligible) — no exception aborted it
    assert {o.prediction_id for o in placed} == {"pA", "pC"}


# --- reconciliation ----------------------------------------------------------

def test_reconcile_orders_picks_up_fill_and_is_idempotent(tmp_path):
    broker = FakeAlpacaPaperBroker()
    svc, store = _svc(tmp_path, broker)
    order = svc.submit_intent(_intent(), trading_date=TRADING_DATE, price=95.0)
    repo = OrderRepository(store)
    # broker fills it during the day
    broker.simulate_fill(order.client_order_id, price=96.5)
    r1 = reconcile_orders(broker, repo)
    assert r1["updated_count"] == 1
    assert repo.get(order.client_order_id).is_filled
    # re-running reconcile writes nothing new (idempotent / catch-up safe)
    before = store.count("paper_order")
    reconcile_orders(broker, repo)
    assert store.count("paper_order") == before


def test_mark_positions_and_equity_idempotent(tmp_path):
    broker = FakeAlpacaPaperBroker(equity=100_000)
    svc, store = _svc(tmp_path, broker)
    order = svc.submit_intent(_intent(), trading_date=TRADING_DATE, price=95.0)
    broker.simulate_fill(order.client_order_id, price=95.0)
    reconcile_orders(broker, OrderRepository(store))

    marks = mark_positions(broker, store, as_of=TRADING_DATE,
                           price_at=lambda s, d: 100.0, universe=_universe())
    assert marks["positions"] == 1
    pos = store.get("paper_position", f"SHOP:{TRADING_DATE}").payload
    assert pos["company_id"] == "shopify" and pos["mark_price"] == 100.0
    assert pos["unrealized_pl"] > 0                 # bought 95, marked 100

    eq = snapshot_equity(broker, store, as_of=TRADING_DATE)
    assert eq["equity"] == 100_000
    # idempotent per day
    mark_positions(broker, store, as_of=TRADING_DATE,
                   price_at=lambda s, d: 100.0, universe=_universe())
    snapshot_equity(broker, store, as_of=TRADING_DATE)
    assert store.count("paper_position") == 1 and store.count("portfolio_equity") == 1


# --- closing resolved positions (horizon exit) -------------------------------

def test_close_resolved_positions_flattens_and_is_idempotent(tmp_path):
    """A filled position must be flattened once its prediction resolves — the
    30-day replay defect (82 positions held after resolution -> buying power
    consumed without bound). Idempotent + catch-up: never double-exits."""
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    broker = FakeAlpacaPaperBroker(equity=100_000)
    repo = OrderRepository(store)
    preds = PredictionRepository(store)

    # a filled, OPEN long for a 1-day-horizon prediction
    company = _universe().by_instrument("SHOP")
    pred = build_prediction(
        company, {"direction": "up", "probability": 0.7, "horizon_days": 1,
                  "created_at": "2026-07-24T13:30:00+00:00"}, "2026-07-24")
    preds.add(pred)
    svc = PaperExecutionService(store, broker, _universe())
    order = svc.submit_intent(_intent(pid=pred.id), trading_date=TRADING_DATE,
                              price=95.0)
    broker.simulate_fill(order.client_order_id, price=95.0)
    reconcile_orders(broker, repo)

    prices = {("SHOP", "2026-07-24"): 95.0, ("SHOP", "2026-07-25"): 99.0}
    price_at = lambda s, d: prices[(s, d[:10])]        # noqa: E731

    # unresolved -> nothing to close (position stays open)
    assert close_resolved_positions(broker, repo, preds,
                                    as_of="2026-07-24")["closed"] == 0

    # resolve the horizon, then close: an opposite-side exit for the full qty
    resolve_due(preds, price_at, "2026-07-25", store=store, order_repo=repo)
    assert close_resolved_positions(broker, repo, preds,
                                    as_of="2026-07-25")["closed"] == 1
    close = [o for o in repo.by_prediction(pred.id)
             if o.action.startswith("close_")][0]
    assert close.side == "sell" and close.action == "close_long"
    assert close.qty == order.qty

    # idempotent: re-running exits nothing more (no double-close)
    assert close_resolved_positions(broker, repo, preds,
                                    as_of="2026-07-25")["closed"] == 0

    # once the exit fills, the broker is flat for the instrument
    broker.simulate_fill(close.client_order_id, price=99.0)
    reconcile_orders(broker, repo)
    assert "SHOP" not in {p.symbol for p in broker.list_positions()}

    # the realized-P&L link still reads the ENTRY leg, not the exit (sign safe)
    outcome = store.get("prediction_outcome", pred.id).payload
    assert outcome["entry_price"] == 95.0 and outcome["trade_pnl"] > 0

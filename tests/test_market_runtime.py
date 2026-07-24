"""Market runtime end-to-end (Part 1): prediction -> paper -> resolve ->
metrics -> daily candidates. All market data is injected (no network)."""
from datetime import date, timedelta

from intent_engine.core import prediction_ledger as pl
from intent_engine.core.market_resolution import ResolutionResult
from intent_engine.events import CompanyEventBus
from intent_engine.runtime.market import MarketRuntime

AS_OF = "2026-07-24"
FUTURE = "2027-01-01"


def _seed(tmp_path, **over):
    kw = dict(source="market", entity_id="e", claim_text="SPY up 2%",
              probability=0.8, resolve_by=(date(2026, 7, 24) + timedelta(days=30)).isoformat(),
              path=tmp_path / "prediction_ledger.db", instrument="SPY",
              direction="up", horizon_days=30,
              resolution_rule={"type": "pct_change", "symbol": "SPY",
                               "op": ">=", "value": 0.02, "window_days": 30},
              resolution_source="tiingo", decision_id="DEC-1")
    kw.update(over)
    return pl.record_prediction(**kw)


def _mr(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    return MarketRuntime(tmp_path, bus=bus,
                         ledger_path=tmp_path / "prediction_ledger.db"), bus


def _price(_sym, _d):
    return 100.0


def test_daily_prediction_creates_eligible_paper_intent(tmp_path):
    _seed(tmp_path)
    mr, _ = _mr(tmp_path)
    out = mr.open_paper_from_predictions(as_of=AS_OF, price_at=_price,
                                         regime_for=lambda a: "risk_on")
    assert len(out["opened"]) == 1
    pos = mr.paper.store.open_positions()[0]
    assert pos.opened_from == "prediction" and pos.decision_id == "DEC-1"
    assert pos.strategy_version and pos.horizon_days == 30


def test_ineligible_predictions_persist_rejection(tmp_path):
    _seed(tmp_path, probability=0.51, decision_id=None)
    mr, _ = _mr(tmp_path)
    out = mr.open_paper_from_predictions(as_of=AS_OF, price_at=_price)
    assert out["opened"] == []
    assert out["rejected"][0]["rule"] == "low_confidence"
    assert mr.rejections.read_all()[0]["rule"] == "low_confidence"


def test_duplicate_daily_run_no_duplicate_trades(tmp_path):
    _seed(tmp_path)
    mr, _ = _mr(tmp_path)
    mr.open_paper_from_predictions(as_of=AS_OF, price_at=_price)
    mr.open_paper_from_predictions(as_of=AS_OF, price_at=_price)   # re-run
    assert len(mr.paper.store.open_positions()) == 1
    # and the re-run logged no spurious rejection for the already-open one
    assert mr.rejections.read_all() == []


def test_due_predictions_resolve_and_link(tmp_path):
    _seed(tmp_path)
    mr, bus = _mr(tmp_path)
    mr.open_paper_from_predictions(as_of=AS_OF, price_at=_price)
    res = mr.resolve_and_link(
        as_of=FUTURE, resolver=lambda p: ResolutionResult("happened", "ok"),
        price_at=lambda s, d: 105.0)
    assert len(res["resolved"]) == 1 and len(res["closed_positions"]) == 1
    m = mr.metrics()
    assert m.closed_count == 1 and m.total_pnl > 0        # long, price rose
    types = {e.event_type for e in bus.store.read_all()}
    assert "prediction.resolved" in types and "paper.position_closed" in types


def test_missing_outcome_stays_unresolved(tmp_path):
    _seed(tmp_path)
    mr, _ = _mr(tmp_path)
    res = mr.resolve_and_link(
        as_of=FUTURE, resolver=lambda p: ResolutionResult("unresolvable", "no data"),
        price_at=lambda s, d: 100.0)
    assert res["resolved"][0]["outcome"] == "unresolvable"
    # unresolvable is not a hit/miss; stays out of the scored book
    assert res["closed_positions"] == []
    remaining = pl.list_predictions(unresolved_only=True,
                                    path=tmp_path / "prediction_ledger.db")
    # resolved (with unresolvable outcome) -> not in unresolved set
    assert all(p.outcome is not None for p in
               pl.list_predictions(path=tmp_path / "prediction_ledger.db"))


def test_resolve_is_idempotent(tmp_path):
    _seed(tmp_path)
    mr, _ = _mr(tmp_path)
    r1 = mr.resolve_and_link(as_of=FUTURE,
                             resolver=lambda p: ResolutionResult("happened", "ok"))
    r2 = mr.resolve_and_link(as_of=FUTURE,
                             resolver=lambda p: ResolutionResult("happened", "ok"))
    assert len(r1["resolved"]) == 1 and r2["resolved"] == []


def test_daily_candidates_use_only_persisted_evidence(tmp_path):
    # 6 resolved losing trades in one regime -> a paper_trade candidate
    _seed(tmp_path)
    mr, _ = _mr(tmp_path)
    for i in range(6):
        p = mr.paper.open_position(prediction_id=f"pr{i}", instrument="SPY",
                                   direction="long", entry_price=100,
                                   regime="risk_off", confidence=0.8, reasoning="x")
        mr.paper.close_position(p.id, exit_price=95, exit_reason="prediction_resolved")
    out = mr.generate_daily_candidates()
    assert len(out["paper_candidates"]) == 1
    cand = mr.learning.get(out["paper_candidates"][0])
    assert cand.source == "paper_trade" and cand.provenance["regime"] == "risk_off"

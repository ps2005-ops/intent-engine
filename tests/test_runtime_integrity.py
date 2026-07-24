"""Data-integrity verification (Phase 3) and the regime label (hardening)."""
from datetime import date, timedelta

from intent_engine.core import prediction_ledger as pl
from intent_engine.core.market_resolution import ResolutionResult
from intent_engine.events import CompanyEventBus
from intent_engine.learning.ledger import LearningStore
from intent_engine.learning.records import Candidate, Evaluation, PromotionDecision
from intent_engine.runtime.integrity import run_integrity
from intent_engine.runtime.market import MarketRuntime
from intent_engine.runtime.regime import (
    NEUTRAL, RISK_OFF, RISK_ON, UNKNOWN, fetch_regime_label, regime_label,
)


class _Curve:
    def __init__(self, inv): self.inverted = inv


class _Credit:
    def __init__(self, p): self.percentile = p


def test_regime_label_mapping():
    assert regime_label({"curve_inversion": _Curve(True),
                         "credit_spread_percentile": _Credit(85)}) == RISK_OFF
    assert regime_label({"curve_inversion": _Curve(False),
                         "credit_spread_percentile": _Credit(20)}) == RISK_ON
    assert regime_label({"curve_inversion": _Curve(False),
                         "credit_spread_percentile": _Credit(50)}) == NEUTRAL
    assert regime_label({}) == UNKNOWN


def test_fetch_regime_label_is_safe_without_key():
    assert fetch_regime_label("2026-07-24", fred_key="") == UNKNOWN


def _populate(tmp_path):
    lp = tmp_path / "prediction_ledger.db"
    bus = CompanyEventBus(tmp_path / "events")
    pl.record_prediction(
        source="market", entity_id="e", claim_text="SPY up", probability=0.8,
        resolve_by=(date(2026, 7, 24) + timedelta(days=30)).isoformat(), path=lp,
        instrument="SPY", direction="up", horizon_days=30,
        resolution_rule={"type": "pct_change", "symbol": "SPY", "op": ">=",
                         "value": 0.02, "window_days": 30},
        resolution_source="tiingo", decision_id="DEC-1")
    mr = MarketRuntime(tmp_path, bus=bus, ledger_path=lp)
    mr.open_paper_from_predictions(as_of="2026-07-24", price_at=lambda s, d: 100.0,
                                   regime_for=lambda a: "risk_on")
    mr.resolve_and_link(as_of="2027-01-01",
                        resolver=lambda p: ResolutionResult("happened", "ok"),
                        price_at=lambda s, d: 105.0)
    mr.generate_daily_candidates()
    return mr


def test_populated_stores_are_clean(tmp_path):
    _populate(tmp_path)
    rep = run_integrity(tmp_path)
    assert rep["clean"] is True and rep["issue_count"] == 0


def test_orphan_evaluation_detected(tmp_path):
    _populate(tmp_path)
    LearningStore(tmp_path / "learning_ledger.db").append_evaluation(
        Evaluation(candidate_id="GHOST", kind="rolling_backtest",
                   verdict="inconclusive"))
    rep = run_integrity(tmp_path)
    assert not rep["clean"]
    assert any(i["kind"] == "orphan_evaluation" for i in rep["issues"])


def test_orphan_promotion_detected(tmp_path):
    _populate(tmp_path)
    LearningStore(tmp_path / "learning_ledger.db").append_promotion(
        PromotionDecision(candidate_id="GHOST", decision="rejected",
                          actor_type="system", rationale="x"))
    rep = run_integrity(tmp_path)
    assert any(i["kind"] == "orphan_promotion" for i in rep["issues"])


def test_status_regression_detected(tmp_path):
    store = LearningStore(tmp_path / "learning_ledger.db")
    c = Candidate(source="manual", target="t", statement="s", hypothesis="h",
                  baseline_ref="b", success_criteria=[], status="promoted")
    store.append_candidate(c)
    store.append_candidate(c.model_copy(update={"status": "proposed"}))  # illegal
    rep = run_integrity(tmp_path)
    assert any(i["kind"] == "status_regression" for i in rep["issues"])


def test_empty_root_is_clean(tmp_path):
    rep = run_integrity(tmp_path)
    assert rep["clean"] is True

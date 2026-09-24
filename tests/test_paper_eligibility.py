"""Prediction -> paper eligibility (1C) and persisted rejections."""
from datetime import date, timedelta

import pytest

from intent_engine.core import prediction_ledger as pl
from intent_engine.paper.eligibility import (
    EligibilityConfig, PaperIntent, evaluate_prediction,
)
from intent_engine.paper.rejections import RejectionStore


def _pred(tmp_path, **over):
    kw = dict(source="market", entity_id="e", claim_text="SPY up 2%",
              probability=0.8, resolve_by=(date(2026, 7, 24) + timedelta(days=30)).isoformat(),
              path=tmp_path / "led.db", instrument="SPY", direction="up",
              horizon_days=30, resolution_source="tiingo", decision_id="DEC-1")
    kw.update(over)
    return pl.record_prediction(**kw)


AS_OF = "2026-07-24"


def test_eligible_prediction_becomes_intent(tmp_path):
    p = _pred(tmp_path)
    r = evaluate_prediction(p, config=EligibilityConfig(), as_of=AS_OF,
                            reasoning="mechanism")
    assert r.eligible and isinstance(r.intent, PaperIntent)
    assert r.intent.direction == "long" and r.intent.instrument == "SPY"
    assert r.intent.decision_id == "DEC-1"
    assert r.intent.strategy_version and r.intent.risk_rule_version


@pytest.mark.parametrize("over,rule", [
    (dict(probability=0.55), "low_confidence"),
    (dict(instrument="TSLA"), "unsupported_instrument"),
    (dict(direction="sideways"), "bad_direction"),
    (dict(horizon_days=None), "bad_horizon"),
    (dict(horizon_days=9999), "bad_horizon"),
])
def test_ineligible_rules(tmp_path, over, rule):
    p = _pred(tmp_path, **over)
    r = evaluate_prediction(p, config=EligibilityConfig(), as_of=AS_OF,
                            reasoning="m")
    assert not r.eligible and r.rule == rule and r.reason


def test_stale_prediction_rejected(tmp_path):
    """A prediction older than the freshness window is refused.

    THE `as_of` IS RELATIVE TO THE PREDICTION, NOT TO THE CALENDAR.
    `record_prediction` stamps `created_at` with the real current date, so a
    hardcoded "late" date only sits the required number of days after it
    while the wall clock is near the date this test was written. It drifted
    past it and the test began asserting that a prediction zero days old is
    stale -- a test that passes or fails depending on what day it is run,
    which is the failure this file now cannot have. Reproduced on the frozen
    baseline db6946fa, so it predates and is unrelated to the V2 layer.
    """
    p = _pred(tmp_path)
    config = EligibilityConfig()
    created = date.fromisoformat(str(p.created_at)[:10])
    late = (created + timedelta(days=config.max_data_age_days + 1)).isoformat()
    r = evaluate_prediction(p, config=config, as_of=late, reasoning="m")
    assert not r.eligible and r.rule == "stale_data", (
        f"a prediction {config.max_data_age_days + 1}d old was accepted: "
        f"{r.rule!r}")


def test_duplicate_exposure_rejected(tmp_path):
    p = _pred(tmp_path)
    r = evaluate_prediction(p, config=EligibilityConfig(),
                            open_prediction_ids={p.id}, as_of=AS_OF, reasoning="m")
    assert not r.eligible and r.rule == "duplicate_exposure"


def test_risk_limit_rejected(tmp_path):
    p = _pred(tmp_path)
    r = evaluate_prediction(p, config=EligibilityConfig(max_open_positions=3),
                            open_position_count=3, as_of=AS_OF, reasoning="m")
    assert not r.eligible and r.rule == "risk_limit"


def test_rejections_persist_idempotently(tmp_path):
    p = _pred(tmp_path, probability=0.55)
    r = evaluate_prediction(p, config=EligibilityConfig(), as_of=AS_OF, reasoning="m")
    store = RejectionStore(tmp_path / "rej.jsonl")
    assert store.record(r, as_of=AS_OF) is True
    assert store.record(r, as_of=AS_OF) is False        # idempotent per day
    rows = store.read_all()
    assert len(rows) == 1 and rows[0]["rule"] == "low_confidence"

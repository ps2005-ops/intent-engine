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


# `record_prediction` stamps the REAL current date and accepts no override, so
# a hard-coded evaluation date drifts: once real time passes it, every
# `as_of=AS_OF`-style call evaluates a prediction dated in the FUTURE. That is a
# different code path from the one these tests mean to exercise, and before
# the `future_dated` guard existed it was indistinguishable from a pass.
# Evaluate as of the prediction's own day instead.
def _as_of(prediction) -> str:
    return prediction.created_at[:10]


def test_eligible_prediction_becomes_intent(tmp_path):
    p = _pred(tmp_path)
    r = evaluate_prediction(p, config=EligibilityConfig(), as_of=_as_of(p),
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
    r = evaluate_prediction(p, config=EligibilityConfig(), as_of=_as_of(p),
                            reasoning="m")
    assert not r.eligible and r.rule == rule and r.reason


def test_stale_prediction_rejected(tmp_path):
    """Staleness measured from the prediction's OWN timestamp.

    `record_prediction` stamps the real current date and takes no `created_at`
    override, so a hard-coded `as_of` silently becomes a FUTURE date as real
    time advances past it -- which is how this test came to assert staleness
    while actually exercising the future-dated path. Derive `as_of` from the
    prediction so the case under test is the one named.
    """
    p = _pred(tmp_path)
    created = date.fromisoformat(p.created_at[:10])
    late = (created + timedelta(days=60)).isoformat()
    r = evaluate_prediction(p, config=EligibilityConfig(), as_of=late,
                            reasoning="m")
    assert not r.eligible and r.rule == "stale_data"
    assert "60d old" in r.reason


# ===========================================================================
# BREAK PROOF 1 — future evidence must not inform an earlier decision
# ===========================================================================
def test_future_dated_prediction_is_rejected_not_treated_as_fresh(tmp_path):
    """`age > max_age` is False for every negative age.

    Before this guard a prediction stamped after `as_of` passed the freshness
    check, because -17 is not greater than 5. A decision cannot be informed by
    a prediction that did not exist when it was made.
    """
    p = _pred(tmp_path)
    created = date.fromisoformat(p.created_at[:10])
    early = (created - timedelta(days=17)).isoformat()
    r = evaluate_prediction(p, config=EligibilityConfig(), as_of=early,
                            reasoning="m")
    assert not r.eligible
    assert r.rule == "future_dated"
    assert "17d after" in r.reason


def test_future_dated_is_a_different_finding_from_stale(tmp_path):
    """Lumping them together hides a clock fault inside a backfill fault."""
    p = _pred(tmp_path)
    created = date.fromisoformat(p.created_at[:10])
    stale = evaluate_prediction(
        p, config=EligibilityConfig(),
        as_of=(created + timedelta(days=60)).isoformat(), reasoning="m")
    future = evaluate_prediction(
        p, config=EligibilityConfig(),
        as_of=(created - timedelta(days=60)).isoformat(), reasoning="m")
    assert stale.rule != future.rule
    assert {stale.rule, future.rule} == {"stale_data", "future_dated"}


def test_same_day_prediction_is_neither_stale_nor_future(tmp_path):
    """The boundary must stay open, or nothing is ever eligible."""
    p = _pred(tmp_path)
    r = evaluate_prediction(p, config=EligibilityConfig(),
                            as_of=p.created_at[:10], reasoning="m")
    assert r.eligible


def test_duplicate_exposure_rejected(tmp_path):
    p = _pred(tmp_path)
    r = evaluate_prediction(p, config=EligibilityConfig(),
                            open_prediction_ids={p.id}, as_of=_as_of(p), reasoning="m")
    assert not r.eligible and r.rule == "duplicate_exposure"


def test_risk_limit_rejected(tmp_path):
    p = _pred(tmp_path)
    r = evaluate_prediction(p, config=EligibilityConfig(max_open_positions=3),
                            open_position_count=3, as_of=_as_of(p), reasoning="m")
    assert not r.eligible and r.rule == "risk_limit"


def test_rejections_persist_idempotently(tmp_path):
    p = _pred(tmp_path, probability=0.55)
    r = evaluate_prediction(p, config=EligibilityConfig(), as_of=_as_of(p), reasoning="m")
    store = RejectionStore(tmp_path / "rej.jsonl")
    assert store.record(r, as_of=_as_of(p)) is True
    assert store.record(r, as_of=_as_of(p)) is False        # idempotent per day
    rows = store.read_all()
    assert len(rows) == 1 and rows[0]["rule"] == "low_confidence"

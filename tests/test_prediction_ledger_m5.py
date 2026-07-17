"""Tests for Task M5's additive extension to core/prediction_ledger.py
(market-engine-execution-plan.md). tests/test_prediction_ledger.py's own
tests are untouched and still exercise the original fields -- these are
new, market-specific coverage only.
"""

import json

import pytest
from pydantic import ValidationError

from intent_engine.core.db import get_connection
from intent_engine.core.prediction_ledger import (
    LevelRule,
    PctChangeRule,
    Prediction,
    record_prediction,
)


def test_market_prediction_round_trips_with_all_new_fields(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_prediction(
        "market", "Acme Inc", "SPY rises at least 2% within 60 days", 0.6, "2026-12-31", path=path,
        instrument="SPY", direction="up", horizon_days=60,
        resolution_rule={"type": "pct_change", "symbol": "SPY", "op": ">=", "value": 0.02, "window_days": 60},
        resolution_source="tiingo",
    )
    assert isinstance(p, Prediction)
    assert p.source == "market"
    assert p.instrument == "SPY"
    assert p.direction == "up"
    assert p.horizon_days == 60
    assert isinstance(p.resolution_rule, PctChangeRule)
    assert p.resolution_rule.symbol == "SPY"
    assert p.resolution_source == "tiingo"


def test_baseline_prediction_with_level_rule_round_trips(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_prediction(
        "baseline", "Acme Inc", "Unemployment reaches 4.5% by year end", 0.4, "2026-12-31", path=path,
        resolution_rule={"type": "level", "series": "UNRATE", "op": ">=", "value": 4.5, "by": "2026-12-31"},
        resolution_source="fred",
    )
    assert p.source == "baseline"
    assert isinstance(p.resolution_rule, LevelRule)
    assert p.resolution_rule.series == "UNRATE"
    assert p.resolution_rule.by == "2026-12-31"


def test_non_market_prediction_leaves_all_new_fields_none(tmp_path):
    """The original 4 sources never touch these fields -- confirms the
    extension is genuinely additive/optional, not a hidden requirement."""
    path = tmp_path / "ledger.db"
    p = record_prediction("premortem", "Acme Inc", "claim", 0.7, "2026-09-30", path=path)
    assert p.instrument is None
    assert p.direction is None
    assert p.horizon_days is None
    assert p.resolution_rule is None
    assert p.resolution_source is None


def test_malformed_resolution_rule_raises_at_record_time_missing_field(tmp_path):
    path = tmp_path / "ledger.db"
    with pytest.raises(ValidationError):
        record_prediction(
            "market", "Acme Inc", "bad rule", 0.5, "2026-12-31", path=path,
            resolution_rule={"type": "pct_change", "op": ">=", "value": 0.02, "window_days": 60},  # missing symbol
        )


def test_malformed_resolution_rule_raises_at_record_time_unknown_type(tmp_path):
    path = tmp_path / "ledger.db"
    with pytest.raises(ValidationError):
        record_prediction(
            "market", "Acme Inc", "bad rule", 0.5, "2026-12-31", path=path,
            resolution_rule={"type": "not_a_real_type", "value": 1},
        )


def test_malformed_resolution_rule_never_persists(tmp_path):
    """A malformed rule must raise BEFORE anything is written -- the ledger
    file shouldn't even exist afterward for a first-ever malformed call."""
    path = tmp_path / "ledger.db"
    with pytest.raises(ValidationError):
        record_prediction(
            "market", "Acme Inc", "bad rule", 0.5, "2026-12-31", path=path,
            resolution_rule={"type": "level", "series": "UNRATE"},  # missing op, value, by
        )
    assert not path.exists()


def test_malformed_resolution_rule_wrong_value_type_raises(tmp_path):
    path = tmp_path / "ledger.db"
    with pytest.raises(ValidationError):
        record_prediction(
            "market", "Acme Inc", "bad rule", 0.5, "2026-12-31", path=path,
            resolution_rule={"type": "pct_change", "symbol": "SPY", "op": ">=", "value": "not-a-number", "window_days": 60},
        )


def test_old_row_missing_m5_fields_still_reads_via_model_validate_json(tmp_path):
    """A pre-M5 row (JSON blob with none of the new fields at all) must
    still parse cleanly -- the additive-migration bar. Constructed by
    inserting a raw row shaped exactly like the pre-M5 Prediction schema,
    not by calling record_prediction() (which would already include the
    new fields as None -- this proves an ACTUALLY OLD row, missing the
    keys entirely, still works)."""
    path = tmp_path / "ledger.db"
    old_style_data = {
        "id": "old-id-123",
        "created_at": "2026-01-01T00:00:00+00:00",
        "source": "manual",
        "entity_id": "Acme Inc",
        "claim_text": "a prediction from before M5 existed",
        "probability": 0.5,
        "resolve_by": "2026-06-01",
        "resolved_at": None,
        "outcome": None,
        "brier_component": None,
        "resolution_note": None,
        # deliberately no instrument/direction/horizon_days/resolution_rule/resolution_source keys
    }
    conn = get_connection(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS predictions (id TEXT NOT NULL, created_at TEXT NOT NULL, "
        "source TEXT NOT NULL, entity_id TEXT NOT NULL, resolved_at TEXT, outcome TEXT, data TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO predictions (id, created_at, source, entity_id, resolved_at, outcome, data) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (old_style_data["id"], old_style_data["created_at"], old_style_data["source"],
         old_style_data["entity_id"], None, None, json.dumps(old_style_data)),
    )
    conn.commit()
    conn.close()

    from intent_engine.core.prediction_ledger import _read_all
    predictions = _read_all(path)
    assert len(predictions) == 1
    old_prediction = predictions[0]
    assert old_prediction.id == "old-id-123"
    assert old_prediction.claim_text == "a prediction from before M5 existed"
    assert old_prediction.instrument is None
    assert old_prediction.resolution_rule is None
    assert old_prediction.resolution_source is None


def test_market_and_baseline_are_valid_prediction_sources(tmp_path):
    path = tmp_path / "ledger.db"
    market = record_prediction("market", "Acme Inc", "c1", 0.5, "2026-12-31", path=path)
    baseline = record_prediction("baseline", "Acme Inc", "c2", 0.5, "2026-12-31", path=path)
    assert market.source == "market"
    assert baseline.source == "baseline"

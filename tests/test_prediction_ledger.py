from datetime import datetime, timedelta, timezone

import pytest

from intent_engine.core.prediction_ledger import (
    Prediction,
    brier_summary,
    record_prediction,
    resolve_prediction,
)


def test_record_prediction_round_trips(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_prediction("manual", "Acme Inc", "Revenue doubles in Q3", 0.6, "2026-09-30", path=path)
    assert isinstance(p, Prediction)
    assert p.probability == 0.6
    assert p.outcome is None
    assert p.brier_component is None


def test_record_prediction_rejects_out_of_range_probability(tmp_path):
    path = tmp_path / "ledger.db"
    with pytest.raises(ValueError):
        record_prediction("manual", "Acme Inc", "claim", 1.5, "2026-09-30", path=path)
    with pytest.raises(ValueError):
        record_prediction("manual", "Acme Inc", "claim", -0.1, "2026-09-30", path=path)


def test_resolve_prediction_computes_brier_component_for_happened(tmp_path):
    """Hand-computed: probability=0.9, happened -> (0.9 - 1.0)^2 = 0.01"""
    path = tmp_path / "ledger.db"
    p = record_prediction("premortem", "Acme Inc", "claim", 0.9, "2026-09-30", path=path)
    resolved = resolve_prediction(p.id, "happened", path=path)
    assert resolved.brier_component == pytest.approx(0.01)


def test_resolve_prediction_computes_brier_component_for_did_not_happen(tmp_path):
    """Hand-computed: probability=0.2, did_not_happen -> (0.2 - 0.0)^2 = 0.04"""
    path = tmp_path / "ledger.db"
    p = record_prediction("scrap", "Acme Inc", "claim", 0.2, "2026-09-30", path=path)
    resolved = resolve_prediction(p.id, "did_not_happen", path=path)
    assert resolved.brier_component == pytest.approx(0.04)


def test_resolve_prediction_unresolvable_leaves_brier_component_none(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_prediction("digest", "Acme Inc", "claim", 0.5, "2026-09-30", path=path)
    resolved = resolve_prediction(p.id, "unresolvable", resolution_note="became unmeasurable", path=path)
    assert resolved.brier_component is None
    assert resolved.outcome == "unresolvable"


def test_resolve_prediction_raises_for_unknown_id(tmp_path):
    path = tmp_path / "ledger.db"
    with pytest.raises(ValueError):
        resolve_prediction("nonexistent-id", "happened", path=path)


def test_resolve_prediction_raises_if_already_resolved(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_prediction("manual", "Acme Inc", "claim", 0.5, "2026-09-30", path=path)
    resolve_prediction(p.id, "happened", path=path)
    with pytest.raises(ValueError):
        resolve_prediction(p.id, "did_not_happen", path=path)


def test_brier_summary_matches_hand_computed_mean_across_3_known_cases(tmp_path):
    """3 known cases, hand-computed:
    (0.9, happened)       -> (0.9-1.0)^2 = 0.01
    (0.2, did_not_happen) -> (0.2-0.0)^2 = 0.04
    (0.5, happened)       -> (0.5-1.0)^2 = 0.25
    mean = (0.01 + 0.04 + 0.25) / 3 = 0.10
    """
    path = tmp_path / "ledger.db"
    p1 = record_prediction("manual", "Acme Inc", "c1", 0.9, "2026-09-30", path=path)
    p2 = record_prediction("manual", "Acme Inc", "c2", 0.2, "2026-09-30", path=path)
    p3 = record_prediction("manual", "Acme Inc", "c3", 0.5, "2026-09-30", path=path)
    resolve_prediction(p1.id, "happened", path=path)
    resolve_prediction(p2.id, "did_not_happen", path=path)
    resolve_prediction(p3.id, "happened", path=path)

    summary = brier_summary(path=path)
    assert summary.count == 3
    assert summary.mean_brier == pytest.approx(0.10)


def test_brier_summary_excludes_unresolvable_and_unresolved(tmp_path):
    path = tmp_path / "ledger.db"
    p1 = record_prediction("manual", "Acme Inc", "resolved", 0.9, "2026-09-30", path=path)
    p2 = record_prediction("manual", "Acme Inc", "unresolvable", 0.5, "2026-09-30", path=path)
    record_prediction("manual", "Acme Inc", "never resolved", 0.3, "2026-09-30", path=path)  # left pending
    resolve_prediction(p1.id, "happened", path=path)
    resolve_prediction(p2.id, "unresolvable", path=path)

    summary = brier_summary(path=path)
    assert summary.count == 1  # only p1
    assert summary.mean_brier == pytest.approx(0.01)


def test_brier_summary_filters_by_source(tmp_path):
    path = tmp_path / "ledger.db"
    p1 = record_prediction("premortem", "Acme Inc", "c1", 0.9, "2026-09-30", path=path)
    p2 = record_prediction("scrap", "Acme Inc", "c2", 0.9, "2026-09-30", path=path)
    resolve_prediction(p1.id, "happened", path=path)
    resolve_prediction(p2.id, "happened", path=path)

    assert brier_summary(source="premortem", path=path).count == 1
    assert brier_summary(source="scrap", path=path).count == 1
    assert brier_summary(path=path).count == 2


def test_brier_summary_filters_by_window_days(tmp_path):
    path = tmp_path / "ledger.db"
    p_old = record_prediction("manual", "Acme Inc", "old", 0.9, "2026-01-01", path=path)
    p_recent = record_prediction("manual", "Acme Inc", "recent", 0.9, "2026-09-30", path=path)
    resolve_prediction(p_old.id, "happened", path=path)
    resolve_prediction(p_recent.id, "happened", path=path)

    # Manually backdate the "old" prediction's resolved_at past the window --
    # real resolve_prediction() always uses now(), so this simulates history.
    import json
    from intent_engine.core.db import get_connection
    conn = get_connection(path)
    old_cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    row = conn.execute("SELECT data FROM predictions WHERE id = ? ORDER BY rowid DESC LIMIT 1", (p_old.id,)).fetchone()
    data = json.loads(row[0])
    data["resolved_at"] = old_cutoff
    conn.execute(
        "INSERT INTO predictions (id, created_at, source, entity_id, resolved_at, outcome, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["id"], data["created_at"], data["source"], data["entity_id"], data["resolved_at"], data["outcome"], json.dumps(data)),
    )
    conn.commit()
    conn.close()

    windowed = brier_summary(window_days=30, path=path)
    assert windowed.count == 1  # only the recent one


def test_brier_summary_calibration_buckets_reflect_realized_rate(tmp_path):
    """2 predictions at probability=0.9 (the 90-100% bucket): one happened,
    one didn't -> realized_rate = 0.5 for that bucket, a real, checkable
    (not hand-waved) calibration signal."""
    path = tmp_path / "ledger.db"
    p1 = record_prediction("manual", "Acme Inc", "c1", 0.9, "2026-09-30", path=path)
    p2 = record_prediction("manual", "Acme Inc", "c2", 0.9, "2026-09-30", path=path)
    resolve_prediction(p1.id, "happened", path=path)
    resolve_prediction(p2.id, "did_not_happen", path=path)

    summary = brier_summary(path=path)
    bucket = summary.calibration_buckets["90-100%"]
    assert bucket.count == 2
    assert bucket.realized_rate == pytest.approx(0.5)


def test_brier_summary_returns_zero_count_and_none_mean_when_nothing_resolved(tmp_path):
    path = tmp_path / "ledger.db"
    record_prediction("manual", "Acme Inc", "pending", 0.5, "2026-09-30", path=path)
    summary = brier_summary(path=path)
    assert summary.count == 0
    assert summary.mean_brier is None
    assert summary.calibration_buckets == {}

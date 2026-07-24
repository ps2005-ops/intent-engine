"""Marketing performance ingestion + attribution + learning bridge (3E/3F/3G).

Distinct from test_marketing_performance.py (T017): this covers the NEW
credential-independent PerformanceStore and the marketing -> shared Learning
Ledger bridge added in the unified-learning runtime work.
"""
import pytest

from intent_engine.events import CompanyEventBus
from intent_engine.learning import LearningLedger
from intent_engine.marketing.performance import (
    INFERRED, OBSERVED, UNKNOWN, PerformanceRecord, PerformanceStore,
    candidates_from_performance,
)


def _rec(campaign="C1", variant="V1", cls=OBSERVED, retrieved="2026-07-24T00:00:00",
         metrics=None):
    return PerformanceRecord(
        campaign_id=campaign, variant_id=variant, channel="linkedin",
        metrics=metrics or {"impressions": 100.0, "clicks": 5.0},
        attribution_class=cls, provenance={"source": "manual_test"},
        retrieved_at=retrieved, external_post_id="sim_abc")


def test_ingest_persists_and_events(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    store = PerformanceStore(tmp_path / "perf.jsonl")
    store.ingest(_rec(), bus=bus)
    rows = store.for_campaign("C1")
    assert len(rows) == 1 and rows[0]["variant_id"] == "V1"
    types = [e.event_type for e in bus.store.read_all()]
    assert types == ["marketing.performance_ingested"]


def test_attribution_class_validated(tmp_path):
    store = PerformanceStore(tmp_path / "perf.jsonl")
    with pytest.raises(ValueError, match="attribution_class"):
        store.ingest(_rec(cls="definitely_caused_it"))


def test_absent_metric_not_fabricated(tmp_path):
    store = PerformanceStore(tmp_path / "perf.jsonl")
    store.ingest(_rec(metrics={"impressions": 100.0}))     # no clicks/conversions
    row = store.for_campaign("C1")[0]
    assert "clicks" not in row["metrics"] and "conversions" not in row["metrics"]


def test_observed_evidence_generates_candidate(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    led = LearningLedger(tmp_path / "learning.db", bus=bus)
    store = PerformanceStore(tmp_path / "perf.jsonl")
    store.ingest(_rec(retrieved="2026-07-24T00:00:00"))
    store.ingest(_rec(retrieved="2026-07-25T00:00:00"))    # 2 observed samples
    ids = candidates_from_performance("C1", led, store=store)
    assert len(ids) == 1
    c = led.get(ids[0])
    assert c.source == "marketing" and "association, not proven causal" in c.statement
    assert candidates_from_performance("C1", led, store=store) == []   # idempotent


def test_tiny_or_non_observed_sample_no_candidate(tmp_path):
    led = LearningLedger(tmp_path / "learning.db")
    store = PerformanceStore(tmp_path / "perf.jsonl")
    store.ingest(_rec(cls=INFERRED))       # inferred, not observed
    store.ingest(_rec(cls=UNKNOWN, variant="V2"))
    assert candidates_from_performance("C1", led, store=store) == []

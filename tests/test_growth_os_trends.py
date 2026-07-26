"""Trend Intelligence (§3) — provider-fed ingestion with provenance, permitted-
source enforcement, and the seven-way trend classification. Offline: injected
FakeTrendSource, no network."""
import pytest

from intent_engine.growth_os.foundation import GrowthOSError, IntelStore
from intent_engine.growth_os.trends import (
    FakeTrendSource,
    RawTrendItem,
    TrendIntelligenceService,
)
from intent_engine.growth_os.trends.records import (
    TREND_BOT,
    TREND_EXECUTIVE,
    TREND_HIGH_VOLUME_LOW_VALUE,
    TREND_RISING,
    TREND_SEASONAL,
)


def _svc(tmp_path):
    return TrendIntelligenceService(IntelStore(tmp_path / "trends.jsonl"))


def _item(topic, day, **kw):
    base = dict(topic=topic, audience="founders", fmt="thread",
                source_url=f"https://hn/{topic}/{day}", published_at=f"{day}T09:00:00+00:00",
                engagement={"impressions": 1000, "engagement": 20},
                metric_definitions={"impressions": "times shown"},
                sample_limitations="single provider window",
                quality_signals={"bot_ratio": 0.05, "unique_account_ratio": 0.9, "sentiment": 0.2})
    base.update(kw)
    return RawTrendItem(**base)


def test_permitted_method_enforced_no_scrape():
    with pytest.raises(GrowthOSError):
        FakeTrendSource("sketchy", method="scrape")     # not a permitted path


def test_ingest_records_full_provenance_and_dedupes(tmp_path):
    svc = _svc(tmp_path)
    src = FakeTrendSource("hn", method="api", items=[_item("AI agents", "2026-07-20")])
    a = svc.ingest(src, query="AI agents")
    b = svc.ingest(src, query="AI agents")              # same item again
    assert len(a) == 1 and len(b) == 1
    rows = svc.store.read_all()
    assert len(rows) == 1                               # deduped
    r = rows[0]
    assert r.provenance.source == "hn" and r.provenance.method == "api"
    assert r.provenance.uri.startswith("https://")
    for f in ("provider", "published_at", "metric_definitions", "sample_limitations",
              "permitted_method"):
        assert f in r.payload
    # limited sample -> lowered confidence, with a basis
    assert r.confidence.value < 0.7 and r.confidence.basis


def test_low_quality_viral_is_rejected_as_bot(tmp_path):
    svc = _svc(tmp_path)
    src = FakeTrendSource("x", method="api", items=[
        _item("crypto pump", "2026-07-20",
              engagement={"impressions": 500000, "engagement": 9000},
              quality_signals={"bot_ratio": 0.8, "unique_account_ratio": 0.1, "sentiment": 0.0})])
    svc.ingest(src, query="crypto")
    cls = svc.classify_trend("crypto pump")
    assert cls.trend_type == TREND_BOT                  # not celebrated as rising


def test_executive_attention_trend_detected(tmp_path):
    svc = _svc(tmp_path)
    src = FakeTrendSource("linkedin", method="api", items=[
        _item("AI for CFOs", "2026-07-20",
              business_signals={"demo_requests": 3, "qualified_visits": 12})])
    svc.ingest(src, query="AI for CFOs")
    assert svc.classify_trend("AI for CFOs").trend_type == TREND_EXECUTIVE


def test_high_volume_low_value_distinguished(tmp_path):
    svc = _svc(tmp_path)
    src = FakeTrendSource("x", method="api", items=[
        _item("funny meme", "2026-07-20",
              engagement={"impressions": 50000, "engagement": 5})])
    svc.ingest(src, query="funny meme")
    assert svc.classify_trend("funny meme").trend_type == TREND_HIGH_VOLUME_LOW_VALUE


def test_genuinely_rising_across_days(tmp_path):
    svc = _svc(tmp_path)
    items = [_item("agent evals", d, engagement={"impressions": 1000, "engagement": e})
             for d, e in [("2026-07-01", 5), ("2026-07-10", 20), ("2026-07-11", 40)]]
    src = FakeTrendSource("hn", method="api", items=items)
    svc.ingest(src, query="agent evals")
    assert svc.classify_trend("agent evals").trend_type == TREND_RISING


def test_seasonal_flagged(tmp_path):
    svc = _svc(tmp_path)
    src = FakeTrendSource("trends", method="api", items=[
        _item("black friday saas deals", "2026-07-20", is_seasonal=True)])
    svc.ingest(src, query="black friday")
    assert svc.classify_trend("black friday saas deals").trend_type == TREND_SEASONAL


def test_explain_is_pattern_not_copy_and_execattn_unknown(tmp_path):
    svc = _svc(tmp_path)
    src = FakeTrendSource("hn", method="api", items=[_item("AI agents", "2026-07-20")])
    svc.ingest(src, query="AI agents")
    ex = svc.explain_trend("AI agents")
    assert set(ex) >= {"what_is_spreading", "why_it_works", "hook_structure",
                       "business_relevance", "risks_of_copying"}
    # no source text is copied — hook/cta are pattern labels or 'manual review'
    assert "manual review" in ex["hook_structure"]
    assert "UNKNOWN" in ex["business_relevance"]        # no exec evidence supplied

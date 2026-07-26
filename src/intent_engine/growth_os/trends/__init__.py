"""Trend Intelligence (§3) — understand current attention WITHOUT violating
platform terms.

Ingestion is behind a `TrendSource` provider interface; every observation is a
foundation IntelRecord whose provenance names the PERMITTED access path
(api/rss/export/…) — unauthorized scraping is not expressible. Trends are
classified (genuinely rising vs seasonal vs one-off virality vs controversy vs
bot/low-quality vs high-volume-low-value vs meaningful executive attention) and
each carries a structured, non-copying explanation (what spreads, who responds,
why, hook, format, timing, CTA, business relevance, risks of copying).
"""
from intent_engine.growth_os.trends.providers import (  # noqa: F401
    FakeTrendSource,
    RawTrendItem,
    TrendSource,
)
from intent_engine.growth_os.trends.records import (  # noqa: F401
    TREND_STREAM,
    TREND_TYPES,
    TrendClassification,
)
from intent_engine.growth_os.trends.service import TrendIntelligenceService  # noqa: F401

__all__ = [
    "TrendSource", "FakeTrendSource", "RawTrendItem", "TREND_STREAM",
    "TREND_TYPES", "TrendClassification", "TrendIntelligenceService",
]

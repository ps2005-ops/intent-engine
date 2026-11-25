"""Trend Intelligence taxonomy + classification value object (§3). Pure."""
from __future__ import annotations

from dataclasses import dataclass, field

TREND_STREAM = "growth_trends"
TREND_OBSERVED = "growth_trends.observed"

# The distinctions §3 requires trend analysis to make.
TREND_RISING = "rising"                       # genuinely rising interest
TREND_SEASONAL = "seasonal"                   # recurring seasonal interest
TREND_ONE_OFF = "one_off_virality"            # a single spike
TREND_CONTROVERSY = "controversy"
TREND_BOT = "bot_low_quality"                 # bot / low-quality engagement
TREND_HIGH_VOLUME_LOW_VALUE = "high_volume_low_value"
TREND_EXECUTIVE = "executive_attention"       # meaningful buyer/executive attention
TREND_TYPES = (
    TREND_RISING, TREND_SEASONAL, TREND_ONE_OFF, TREND_CONTROVERSY, TREND_BOT,
    TREND_HIGH_VOLUME_LOW_VALUE, TREND_EXECUTIVE,
)

# Fields every stored observation must carry (§3). Enforced by the service.
REQUIRED_OBSERVATION_FIELDS = (
    "provider", "source_url", "retrieved_at", "published_at", "audience",
    "topic", "format", "engagement", "metric_definitions", "sample_limitations",
    "permitted_method",
)


@dataclass
class TrendClassification:
    trend_type: str
    reasons: list = field(default_factory=list)   # why — human-readable, explainable
    signals: dict = field(default_factory=dict)   # the measured features used

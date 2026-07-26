"""Business & Executive Attention (§4) — never optimize for vanity metrics.

Keeps three outcomes SEPARATE (attention / quality-engagement / business-outcome)
and computes an ExecutiveAttentionScore only from observable, lawfully-available
evidence. It never infers sensitive personal characteristics and never claims a
viewer holds a role (e.g. "CEO") without supporting data — absent evidence, the
score is UNKNOWN, not assumed.
"""
from intent_engine.growth_os.attention.records import (  # noqa: F401
    ATTENTION,
    BUSINESS_OUTCOME,
    METRIC_TIERS,
    QUALITY_ENGAGEMENT,
    TIERS,
    ExecutiveAttentionScore,
    tier_of,
)
from intent_engine.growth_os.attention.service import (  # noqa: F401
    BusinessAttentionService,
    score_executive_attention,
)

__all__ = [
    "ATTENTION", "QUALITY_ENGAGEMENT", "BUSINESS_OUTCOME", "TIERS",
    "METRIC_TIERS", "tier_of", "ExecutiveAttentionScore",
    "BusinessAttentionService", "score_executive_attention",
]

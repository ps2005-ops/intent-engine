"""Business/Executive Attention taxonomy (§4). Pure, no I/O.

Three outcome tiers that must NEVER be collapsed into one number, plus the
ExecutiveAttentionScore value object whose contract forbids unsupported claims.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from intent_engine.growth_os.foundation.records import GrowthOSError

ATTENTION = "attention"
QUALITY_ENGAGEMENT = "quality_engagement"
BUSINESS_OUTCOME = "business_outcome"
TIERS = (ATTENTION, QUALITY_ENGAGEMENT, BUSINESS_OUTCOME)

# The metric -> tier map (§4). Vanity metrics live only in ATTENTION; nothing
# in a lower tier is ever added to a higher one.
METRIC_TIERS: dict = {
    # A. ATTENTION (vanity on their own)
    "impressions": ATTENTION, "views": ATTENTION, "reach": ATTENTION,
    "watch_time": ATTENTION, "completion_rate": ATTENTION,
    # B. QUALITY ENGAGEMENT
    "saves": QUALITY_ENGAGEMENT, "meaningful_comments": QUALITY_ENGAGEMENT,
    "shares": QUALITY_ENGAGEMENT, "profile_visits": QUALITY_ENGAGEMENT,
    "repo_visits": QUALITY_ENGAGEMENT, "newsletter_subscriptions": QUALITY_ENGAGEMENT,
    "repeat_visitors": QUALITY_ENGAGEMENT,
    # C. BUSINESS OUTCOMES
    "executive_engagement": BUSINESS_OUTCOME, "qualified_visits": BUSINESS_OUTCOME,
    "demo_requests": BUSINESS_OUTCOME, "waitlist_joins": BUSINESS_OUTCOME,
    "trials": BUSINESS_OUTCOME, "github_stars_target": BUSINESS_OUTCOME,
    "target_account_replies": BUSINESS_OUTCOME, "crm_qualified_leads": BUSINESS_OUTCOME,
    "pipeline_influence": BUSINESS_OUTCOME, "conversion": BUSINESS_OUTCOME,
    "revenue": BUSINESS_OUTCOME,
}


def tier_of(metric: str) -> str:
    if metric not in METRIC_TIERS:
        raise GrowthOSError(f"unknown attention metric {metric!r}")
    return METRIC_TIERS[metric]


# The only evidence an ExecutiveAttentionScore may be built from — each is an
# OBSERVED fact, never an inference about a person. `seniority` is only ever set
# when `role_verified` is a lawful, supported source.
EXEC_EVIDENCE_FIELDS = (
    "role_verified",           # lawful role/company source (e.g. verified reply
                               #  metadata, opted-in profile), or None
    "target_account_match",    # matches a configured target account (bool)
    "seniority",               # only if role_verified supports it, else None
    "meaningful_reply",        # a real conversation happened (bool)
    "website_behavior",        # e.g. "viewed_pricing" (observed), or None
    "conversion",              # observed conversion event, or None
)

UNKNOWN_SCORE = None


@dataclass(frozen=True)
class ExecutiveAttentionScore:
    """Score in [0,1] AND its evidence + basis — or `value=None` (UNKNOWN) when
    evidence is insufficient. NEVER asserts a role/seniority without a supporting
    `role_verified` source; NEVER infers sensitive characteristics."""
    value: Optional[float]
    basis: str
    evidence: dict = field(default_factory=dict)

    @property
    def is_known(self) -> bool:
        return self.value is not None

    def validate(self) -> "ExecutiveAttentionScore":
        if self.value is not None and not (0.0 <= float(self.value) <= 1.0):
            raise GrowthOSError(f"exec-attention value {self.value!r} not in [0,1]")
        if not (self.basis or "").strip():
            raise GrowthOSError("exec-attention needs a basis (no black-box)")
        # the load-bearing safety wall: a claimed seniority MUST be backed by a
        # verified role source — never asserted from behavior alone.
        if self.evidence.get("seniority") and not self.evidence.get("role_verified"):
            raise GrowthOSError(
                "cannot assert seniority without a verified role source "
                "(never claim a viewer is a CEO without supported data)")
        return self

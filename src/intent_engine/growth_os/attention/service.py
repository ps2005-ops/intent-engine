"""Business/Executive Attention scoring (§4).

`BusinessAttentionService.summarize` buckets observed metrics into the three
tiers and KEEPS THEM SEPARATE — there is no single blended score, by design.
`score_executive_attention` turns observed evidence into an
ExecutiveAttentionScore, refusing to assert anything the evidence does not
support (UNKNOWN instead of a guess).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from intent_engine.growth_os.attention.records import (
    ATTENTION,
    BUSINESS_OUTCOME,
    QUALITY_ENGAGEMENT,
    TIERS,
    ExecutiveAttentionScore,
    tier_of,
)
from intent_engine.growth_os.foundation.records import GrowthOSError


@dataclass
class AttentionSummary:
    """Three separate tiers — never summed together (§4)."""
    tiers: dict = field(default_factory=lambda: {t: {} for t in TIERS})

    def totals(self) -> dict:
        return {t: sum(v for v in self.tiers[t].values()) for t in TIERS}

    def has_business_outcome(self) -> bool:
        return any(self.tiers[BUSINESS_OUTCOME].values())


class BusinessAttentionService:
    @staticmethod
    def summarize(metrics: dict) -> AttentionSummary:
        """Bucket {metric: value} into the 3 tiers. Unknown metrics are refused
        loudly rather than silently dropped."""
        s = AttentionSummary()
        for metric, value in metrics.items():
            s.tiers[tier_of(metric)][metric] = value
        return s


# --- executive attention -----------------------------------------------------

def score_executive_attention(evidence: dict) -> ExecutiveAttentionScore:
    """Combine OBSERVED evidence into an executive-attention score, or UNKNOWN.

    Weighting is explicit and explainable — no black box. Absent any qualifying
    evidence, the result is UNKNOWN (value=None). A claimed `seniority` without a
    verified role source is rejected by ExecutiveAttentionScore.validate()."""
    weights = {
        "role_verified": 0.30,          # a lawful, supported role/company source
        "target_account_match": 0.25,   # matches a configured target account
        "meaningful_reply": 0.20,       # a real conversation happened
        "conversion": 0.15,             # an observed conversion event
        "website_behavior": 0.10,       # observed high-intent behavior
    }
    contributing = []
    value = 0.0
    for field_name, w in weights.items():
        if evidence.get(field_name):
            value += w
            contributing.append(field_name)
    if not contributing:
        return ExecutiveAttentionScore(
            value=None,
            basis="no qualifying evidence observed — executive attention UNKNOWN",
            evidence=dict(evidence)).validate()
    basis = "observed: " + ", ".join(contributing)
    return ExecutiveAttentionScore(
        value=round(min(value, 1.0), 3), basis=basis, evidence=dict(evidence)
    ).validate()

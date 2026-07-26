"""Business/Executive Attention (§4) — three separate outcome tiers and an
executive score that never over-claims. Offline, deterministic."""
import pytest

from intent_engine.growth_os.attention import (
    ATTENTION,
    BUSINESS_OUTCOME,
    QUALITY_ENGAGEMENT,
    BusinessAttentionService,
    ExecutiveAttentionScore,
    score_executive_attention,
    tier_of,
)
from intent_engine.growth_os.foundation import GrowthOSError


def test_metrics_map_to_the_right_tier():
    assert tier_of("impressions") == ATTENTION
    assert tier_of("saves") == QUALITY_ENGAGEMENT
    assert tier_of("demo_requests") == BUSINESS_OUTCOME
    with pytest.raises(GrowthOSError):
        tier_of("not_a_metric")


def test_tiers_are_kept_separate_never_summed():
    s = BusinessAttentionService.summarize(
        {"impressions": 10000, "saves": 40, "demo_requests": 2})
    assert s.tiers[ATTENTION] == {"impressions": 10000}
    assert s.tiers[QUALITY_ENGAGEMENT] == {"saves": 40}
    assert s.tiers[BUSINESS_OUTCOME] == {"demo_requests": 2}
    assert s.has_business_outcome()
    # totals are per-tier; there is deliberately no single blended number
    assert set(s.totals()) == {ATTENTION, QUALITY_ENGAGEMENT, BUSINESS_OUTCOME}


def test_executive_attention_unknown_without_evidence():
    score = score_executive_attention({})
    assert not score.is_known and score.value is None
    assert "UNKNOWN" in score.basis


def test_executive_attention_scores_from_observed_evidence():
    score = score_executive_attention({
        "role_verified": "verified reply metadata",
        "target_account_match": True, "meaningful_reply": True})
    assert score.is_known and 0 < score.value <= 1
    assert "role_verified" in score.basis and "target_account_match" in score.basis


def test_never_assert_seniority_without_verified_role():
    # claiming seniority with no verified role source is refused (never claim a
    # viewer is a CEO without supported data)
    with pytest.raises(GrowthOSError):
        ExecutiveAttentionScore(value=0.9, basis="looked senior",
                                evidence={"seniority": "CEO"}).validate()
    # with a verified role it is allowed
    ExecutiveAttentionScore(
        value=0.9, basis="verified", evidence={"seniority": "CEO",
        "role_verified": "opted-in profile"}).validate()

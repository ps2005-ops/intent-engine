"""The hook selector (T023.5) — memorable, but truth before surprise.

The first major insight must be memorable, but the product earns trust by
never choosing drama over evidence. The selector chooses among
ALREADY-SUPPORTED claims only, by a fixed rule order and a deterministic
evidence-strength key. It creates no claim. It never prefers a more
dramatic low-confidence claim over a less dramatic high-confidence one. If
nothing clears the bar, it returns None and the UI says so honestly — a
successful outcome.
"""
from __future__ import annotations

from intent_engine.founder_intelligence.records import (
    AVAIL_CONFLICTED, AVAIL_PARTIAL, AVAIL_SUPPORTED, FRESH_CURRENT,
    InsightCard, SECTION_STOOD_OUT,
)

HOOK_VERSION = "fi_hook.v1"

_CONFIDENCE_RANK = {"High": 3, "Moderate": 2, "Low": 1, None: 0}
_AVAILABILITY_RANK = {AVAIL_SUPPORTED: 3, AVAIL_PARTIAL: 2, AVAIL_CONFLICTED: 1}

_HEADLINES = {
    "blind_spot": "Your public messaging appears narrower than your visible "
                  "customer evidence.",
    "market_contrast": "The market appears to describe the outcome "
                       "differently from your own messaging.",
    "persona_mismatch": "Your public signals appear to address more customer "
                        "groups than your website directly speaks to.",
}


def _evidence_strength(claim) -> tuple:
    """Availability and confidence dominate; novelty never enters the key,
    so a dramatic weak claim can never outrank a solid quiet one."""
    return (_AVAILABILITY_RANK.get(claim.availability, 0),
            _CONFIDENCE_RANK.get(claim.confidence, 0),
            1 if claim.freshness_status == FRESH_CURRENT else 0,
            len(claim.source_refs))


def select_hook(*, blind_spot_claims=(), market_view_claims=(),
                persona_claims=(), min_confidence="Moderate") -> InsightCard | None:
    """Deterministic selection among supported claims, in the brief's
    priority order; None when nothing clears the confidence bar."""
    candidates = []

    for c in blind_spot_claims:
        if c.availability == AVAIL_SUPPORTED:
            candidates.append(("blind_spot", c))

    company = [c for c in market_view_claims
               if c.availability == AVAIL_SUPPORTED and "company" in c.claim_id]
    customer = [c for c in market_view_claims
                if c.availability == AVAIL_SUPPORTED and "customer" in c.claim_id]
    if company and customer:
        candidates.append(("market_contrast", company[0]))

    homepage = [c for c in persona_claims if "homepage" in c.claim_id]
    personas = [c for c in persona_claims
                if c.availability in (AVAIL_SUPPORTED, AVAIL_PARTIAL)
                and c.claim_id.startswith("p.") and "homepage" not in c.claim_id]
    if homepage and len(personas) >= 2:
        candidates.append(("persona_mismatch", homepage[0]))

    if not candidates:
        return None

    kind, claim = max(candidates,
                      key=lambda kc: (_evidence_strength(kc[1]), kc[1].claim_id))
    # a claim below the confidence bar is only allowed if it is fully SUPPORTED
    if (_CONFIDENCE_RANK.get(claim.confidence, 0)
            < _CONFIDENCE_RANK.get(min_confidence, 0)
            and claim.availability != AVAIL_SUPPORTED):
        return None

    card = InsightCard(
        insight_id=f"hook.{claim.claim_id}", kind=SECTION_STOOD_OUT,
        headline=_HEADLINES[kind], availability=claim.availability,
        claims=(claim,), confidence=claim.confidence,
        why_it_matters="selected because it is supported by current "
                       "evidence, not because it is dramatic",
        alternative_explanation="this may be intentional positioning; we do "
                                "not yet know whether it is deliberate",
        what_would_change_the_view="founder-approved customer interviews or "
                                   "connected sales evidence",
        question_to_investigate="is the narrower public messaging a "
                                "deliberate focus, or an unexamined default?")
    card.validate()
    return card

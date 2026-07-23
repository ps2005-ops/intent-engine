"""Stage One — Proof of Understanding + evidence-backed analytics (T023.5).

The most important stage: it proves the product knows the company before
offering any perspective. Every field carries value / confidence /
freshness / evidence-count / availability. Only supported fields are
shown; an unsupported field is omitted or rendered UNAVAILABLE — never
inferred, and UNAVAILABLE is never rendered as 0.

The workspace computes NO business intelligence here. Each field is a
`SourceClaim` an agent (or the demo fixture) produced; understanding only
groups and labels it with an external-view qualifier.
"""
from __future__ import annotations

from intent_engine.founder_intelligence.records import (
    AVAIL_CONFLICTED, AVAIL_PARTIAL, AVAIL_STALE, AVAIL_SUPPORTED,
    AVAIL_UNAVAILABLE, InsightCard, IntelligenceSection, SECTION_ANALYTICS,
    SECTION_UNDERSTANDING,
)

UNDERSTANDING_VERSION = "fi_understanding.v1"
EXTERNAL_QUALIFIER = ("From public information / currently approved sources — "
                      "the external market view, not internal knowledge")


def _card(claim, kind) -> InsightCard:
    return InsightCard(
        insight_id=f"{kind}.{claim.claim_id}", kind=kind,
        headline=claim.text, availability=claim.availability,
        claims=(claim,), confidence=claim.confidence,
        why_it_matters=EXTERNAL_QUALIFIER)


def assemble_understanding(claims: list) -> IntelligenceSection:
    """Proof of Understanding — supported fields only, each cited."""
    cards = tuple(_card(c, SECTION_UNDERSTANDING) for c in claims
                  if c.availability != AVAIL_UNAVAILABLE)
    section = IntelligenceSection(
        kind=SECTION_UNDERSTANDING, title="What we understood",
        cards=cards, availability=AVAIL_SUPPORTED if cards else AVAIL_UNAVAILABLE,
        limitations=(EXTERNAL_QUALIFIER,
                     "public information can be incomplete"),
        note="every field shows its value, confidence, freshness, and "
             "evidence; unsupported fields are omitted rather than inferred")
    section.validate()
    return section


def assemble_analytics(claims: list) -> IntelligenceSection:
    """Evidence-backed company analytics. An empty metric is UNAVAILABLE,
    never 0; a stale metric is labelled; a conflicted signal is preserved."""
    cards = []
    for claim in claims:
        card = InsightCard(
            insight_id=f"{SECTION_ANALYTICS}.{claim.claim_id}",
            kind=SECTION_ANALYTICS, headline=claim.text,
            availability=claim.availability,
            claims=(claim,) if claim.availability != AVAIL_UNAVAILABLE else (),
            confidence=claim.confidence,
            why_it_matters="what is measured, its sources, and what should "
                           "not be inferred from it")
        cards.append(card)
    unavailable = [c.headline for c in cards
                   if c.availability == AVAIL_UNAVAILABLE]
    conflicted = [c.headline for c in cards
                  if c.availability == AVAIL_CONFLICTED]
    section = IntelligenceSection(
        kind=SECTION_ANALYTICS, title="Evidence and analytics",
        cards=tuple(cards), availability=AVAIL_SUPPORTED,
        limitations=tuple(
            [f"unavailable (not zero): {m}" for m in unavailable]
            + [f"sources disagree: {m}" for m in conflicted]),
        note="an unavailable metric renders as unavailable, never as zero; a "
             "conflicted signal is preserved, never averaged")
    section.validate()
    return section

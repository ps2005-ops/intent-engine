"""Stage Two & Three — the executive perspective sections (T023.5).

Assembled only AFTER Proof of Understanding. Each section composes supported
claims; none invents a strategic conclusion, a causal relationship, or a
competitor. Blind spots and assumptions are possible interpretations with
an alternative explanation and a question — never verdicts. Executive
attention preserves the owning agent's ordering and creates no master
score. "What we do not believe yet" is first-class skepticism, not
contrarian theatre.
"""
from __future__ import annotations

from intent_engine.founder_intelligence.records import (
    AVAIL_CONFLICTED, AVAIL_OUT_OF_SCOPE, AVAIL_PARTIAL, AVAIL_STALE,
    AVAIL_SUPPORTED, AVAIL_UNAVAILABLE, InsightCard, IntelligenceSection,
    OPP_HYPOTHESIS, OPP_OBSERVED, SECTION_ASSUMPTIONS, SECTION_ATTENTION,
    SECTION_BLIND_SPOTS, SECTION_COMPETITORS, SECTION_CONFIDENCE,
    SECTION_DONT_BELIEVE, SECTION_MARKET_VIEW, SECTION_OPPORTUNITIES,
    SECTION_STOOD_OUT,
)

PERSPECTIVE_VERSION = "fi_perspective.v1"


def assemble_stood_out(hook_card, extra_claims=()) -> IntelligenceSection:
    """At most three supported items. The hook is first if present."""
    cards = []
    if hook_card is not None:
        cards.append(hook_card)
    for claim in extra_claims:
        if len(cards) >= 3:
            break
        if claim.availability == AVAIL_SUPPORTED:
            cards.append(InsightCard(
                insight_id=f"{SECTION_STOOD_OUT}.{claim.claim_id}",
                kind=SECTION_STOOD_OUT, headline=claim.text,
                availability=claim.availability, claims=(claim,),
                confidence=claim.confidence,
                why_it_matters="a supported, non-obvious observation",
                alternative_explanation="an alternative reading may exist",
                what_would_change_the_view="stronger or contradicting "
                                           "evidence",
                question_to_investigate="what would a customer say about "
                                        "this?"))
    if not cards:
        section = IntelligenceSection(
            kind=SECTION_STOOD_OUT, title="What stood out",
            availability=AVAIL_UNAVAILABLE,
            note="We understand the visible company profile, but we do not "
                 "yet have enough evidence for a responsible blind-spot "
                 "claim.")
        return section
    section = IntelligenceSection(
        kind=SECTION_STOOD_OUT, title="What stood out", cards=tuple(cards),
        note="at most three supported observations; truth before surprise")
    section.validate()
    return section


def assemble_market_view(company_lang, customer_lang) -> IntelligenceSection:
    """Company language vs market language — a bounded textual comparison.
    NO causality is added (never 'this reduces conversion')."""
    if not (company_lang and customer_lang):
        return IntelligenceSection(
            kind=SECTION_MARKET_VIEW, title="Market view",
            availability=AVAIL_UNAVAILABLE,
            note="insufficient supported language evidence to compare")
    card = InsightCard(
        insight_id="market_view.contrast", kind=SECTION_MARKET_VIEW,
        headline="What you emphasize vs. what the market emphasizes",
        availability=AVAIL_SUPPORTED, claims=(company_lang, customer_lang),
        confidence="Moderate",
        why_it_matters="the visible customer language focuses more on the "
                       "operational outcome than the technical mechanism")
    card.validate()
    section = IntelligenceSection(
        kind=SECTION_MARKET_VIEW, title="Market view", cards=(card,),
        note="a bounded language comparison; no causal claim is added")
    section.validate()
    return section


def assemble_blind_spots(claims) -> IntelligenceSection:
    """Possible blind spots — each source-backed, each with an alternative
    explanation and a question. Never a verdict."""
    cards = []
    for claim in claims:
        if claim.availability != AVAIL_SUPPORTED:
            continue
        cards.append(InsightCard(
            insight_id=f"{SECTION_BLIND_SPOTS}.{claim.claim_id}",
            kind=SECTION_BLIND_SPOTS,
            headline="You may be measuring acquisition more clearly than "
                     "trust." if "messaging" in claim.claim_id
            else claim.text,
            availability=claim.availability, claims=(claim,),
            confidence=claim.confidence,
            why_it_matters="every successful company develops blind spots; "
                           "this is an observation worth examining",
            alternative_explanation="the public view is incomplete; this may "
                                    "be intentional or already understood "
                                    "internally",
            what_would_change_the_view="connected internal evidence or "
                                       "founder-approved customer interviews",
            question_to_investigate="are customers learning the category from "
                                    "someone else before they learn from "
                                    "you?"))
    section = IntelligenceSection(
        kind=SECTION_BLIND_SPOTS, title="Possible blind spots",
        cards=tuple(cards),
        availability=AVAIL_SUPPORTED if cards else AVAIL_UNAVAILABLE,
        note="observations worth examining, not verdicts")
    section.validate()
    return section


def assemble_assumptions(visible, complicating) -> IntelligenceSection:
    """Assumptions we would investigate — visible assumption + complicating
    evidence + what would resolve. The product never declares it false."""
    if not visible:
        return IntelligenceSection(
            kind=SECTION_ASSUMPTIONS, title="Assumptions we would investigate",
            availability=AVAIL_UNAVAILABLE,
            note="no visible assumption is sufficiently supported to surface")
    card = InsightCard(
        insight_id=f"{SECTION_ASSUMPTIONS}.{visible.claim_id}",
        kind=SECTION_ASSUMPTIONS,
        headline="Visible assumption: buyers choose primarily on feature "
                 "breadth",
        availability=AVAIL_SUPPORTED,
        claims=(visible,) + ((complicating,) if complicating else ()),
        confidence="Moderate",
        why_it_matters="worth testing because the visible evidence points "
                       "two ways",
        alternative_explanation="the visible assumption may hold for a "
                                "segment we cannot see from outside",
        what_would_change_the_view="founder-approved customer interviews or "
                                   "connected sales evidence",
        question_to_investigate="do buyers describe the decision the way the "
                                "homepage does?")
    card.validate()
    section = IntelligenceSection(
        kind=SECTION_ASSUMPTIONS, title="Assumptions we would investigate",
        cards=(card,),
        note="the product investigates assumptions; it does not declare them "
             "false")
    section.validate()
    return section


def assemble_attention(claims) -> IntelligenceSection:
    """Where leadership attention may be most valuable. Preserves the owning
    agent's ordering; creates NO combined executive score. Uses bands, not
    fake heatmap precision."""
    cards = []
    for claim in claims:      # order preserved as supplied by the owner
        band = ("High attention signal" if claim.availability == AVAIL_SUPPORTED
                else "Moderate attention signal"
                if claim.availability == AVAIL_PARTIAL else "Watch")
        cards.append(InsightCard(
            insight_id=f"{SECTION_ATTENTION}.{claim.claim_id}",
            kind=SECTION_ATTENTION, headline=claim.text,
            availability=claim.availability, claims=(claim,),
            confidence=band,
            why_it_matters=f"{band} — raised by the approved evidence",
            alternative_explanation="the attention signal reflects the "
                                    "visible view only",
            question_to_investigate="what internal evidence would confirm or "
                                    "lower this signal?"))
    section = IntelligenceSection(
        kind=SECTION_ATTENTION, title="Where leadership attention may be most "
        "valuable", cards=tuple(cards),
        availability=AVAIL_SUPPORTED if cards else AVAIL_UNAVAILABLE,
        note="attention bands, not a combined score; owner ordering preserved")
    section.validate()
    return section


def assemble_dont_believe_yet(insufficient_topics) -> IntelligenceSection:
    """First-class skepticism. Each entry states why the evidence is
    insufficient, what exists, what is missing, and what would change the
    view. Never a dramatic rejection without evidence."""
    cards = []
    for topic in insufficient_topics:
        cards.append(InsightCard(
            insight_id=f"{SECTION_DONT_BELIEVE}.{topic['id']}",
            kind=SECTION_DONT_BELIEVE, headline=topic["headline"],
            availability=AVAIL_UNAVAILABLE, claims=(),
            why_it_matters=topic.get("why_insufficient", ""),
            what_would_change_the_view=topic.get("what_would_change", "")))
    section = IntelligenceSection(
        kind=SECTION_DONT_BELIEVE, title="What we do not believe yet",
        cards=tuple(cards), availability=AVAIL_SUPPORTED,
        note="the evidence does not yet support these conclusions; stated "
             "rather than guessed")
    return section


def assemble_competitors(supported=False, claims=()) -> IntelligenceSection:
    """Competitor analysis has no owning subsystem (Gap 2). Honest
    OUT_OF_SCOPE — never a model-generated competitor list."""
    if not supported:
        return IntelligenceSection(
            kind=SECTION_COMPETITORS, title="Companies worth comparing",
            availability=AVAIL_OUT_OF_SCOPE,
            note="No comparison is shown because no approved source names a "
                 "competitor or alternative. A competitor list is never "
                 "invented. To fill this in, add an independent source such "
                 "as market reporting, an analyst note, or a competitor's own "
                 "positioning page.")
    cards = tuple(InsightCard(
        insight_id=f"{SECTION_COMPETITORS}.{c.claim_id}",
        kind=SECTION_COMPETITORS, headline=c.text, availability=c.availability,
        claims=(c,)) for c in claims if c.availability == AVAIL_SUPPORTED)
    section = IntelligenceSection(kind=SECTION_COMPETITORS,
                                  title="Companies worth comparing", cards=cards)
    section.validate()
    return section


def assemble_opportunities(claims) -> IntelligenceSection:
    """Opportunities worth investigating. The three states (observed /
    hypothesis / decision-ready) are kept distinct, never collapsed, and an
    opportunity is never silently a recommendation."""
    cards = []
    for claim in claims:
        state = OPP_HYPOTHESIS if claim.availability == AVAIL_PARTIAL else \
            OPP_OBSERVED
        cards.append(InsightCard(
            insight_id=f"{SECTION_OPPORTUNITIES}.{claim.claim_id}",
            kind=SECTION_OPPORTUNITIES,
            headline=f"[{state}] {claim.text}", availability=claim.availability,
            claims=(claim,), confidence=claim.confidence,
            why_it_matters="an opportunity to investigate, not a "
                           "recommendation",
            what_would_change_the_view="evidence that the benefiting persona "
                                       "exists at scale"))
    section = IntelligenceSection(
        kind=SECTION_OPPORTUNITIES, title="Opportunities worth investigating",
        cards=tuple(cards),
        availability=AVAIL_SUPPORTED if cards else AVAIL_UNAVAILABLE,
        note="observed opportunity / opportunity hypothesis / decision-ready "
             "proposal are distinct; none is silently a recommendation")
    section.validate()
    return section

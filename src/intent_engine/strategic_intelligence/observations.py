"""V1.2 observation derivation for REAL runs.

Turns approved, retrieved ingestion documents into structured
StrategicObservations by detecting controlled-vocabulary signals in their text.
Signal detection is an internal reasoning input — never surfaced as a
"top terms" insight. A real run over company-owned pages only will, by design,
produce a one-sided observation set that the quality gate marks partial.
"""
from __future__ import annotations

from intent_engine.strategic_intelligence.records import StrategicObservation

# document source_type -> strategic source_class
_SOURCE_CLASS = {
    "external_approved": "independent_reporting",
    "pasted": "customer_voice",
}

# signal -> phrases that evidence it (substring match, lowercased)
#
# THESE MUST BE SPECIFIC ENOUGH TO BE WRONG.
#
# The pattern library these feed is a COMMERCE library — SMB wedge, agentic
# commerce, storefront commoditisation — and `reasoning.py` already gates each
# hypothesis behind a 2-signal threshold. The gate was never the problem: the
# detectors were. Single generic words ("infrastructure", "enterprise",
# "identity", "partners", "apps", "ecosystem", "simple", "outcomes",
# "network", "owned", "native") appear on essentially every B2B software page,
# so any company cleared a 2-signal threshold on vocabulary alone and inherited
# commerce hypotheses it had nothing to do with. Palantir matched five.
#
# Rule of thumb when editing: a phrase belongs here only if a company that is
# NOT in this business would be unlikely to publish it. Prefer multi-word
# phrases. A bare noun is almost never specific enough.
_SIGNAL_KEYWORDS = {
    "infrastructure_positioning": ("commerce infrastructure", "commerce rails",
                                   "powering commerce", "infrastructure for "
                                   "commerce", "payments infrastructure",
                                   "commerce backbone", "commerce platform"),
    "checkout_identity_rails": ("checkout", "shop pay", "shoppay",
                                "buyer identity", "payment rails",
                                "one-click checkout", "digital wallet"),
    "agentic_commerce": ("ai agent", "agentic", "ai-mediated", "ai shopping",
                         "shopping assistant", "ai commerce"),
    "distribution_shift": ("shop app", "marketplace", "demand capture",
                           "wherever your customers", "sales channels",
                           "omnichannel"),
    "enterprise_expansion": ("shopify plus", "large merchants",
                             "commerce components", "enterprise merchants",
                             "upmarket", "move upmarket", "enterprise tier"),
    "smb_simplicity": ("anyone can sell", "start your business",
                       "no code", "no-code", "small business owners",
                       "launch your store", "sell online in minutes",
                       "simple", "easy to", "fast setup", "simplicity"),
    "product_breadth": ("point of sale", "fulfillment network",
                        "merchant capital", "everything you need to sell",
                        "one platform for", "unified suite"),
    "merchant_outcome_positioning": ("grow your business", "sell more",
                                     "merchant outcomes", "merchant success",
                                     "more sales"),
    "partner_ecosystem_enablement": ("app store", "app marketplace",
                                     "partner ecosystem", "developer platform",
                                     "third-party apps", "app developers"),
    "platform_control": ("first-party", "we own the", "end-to-end control",
                         "vertically integrated", "own the full stack"),
    "storefront_creation": ("storefront", "online store", "build your store",
                            "store builder", "store themes"),
    "data_network": ("shopper data", "consumer data", "cross-merchant",
                     "audience network", "buyer network"),
}

# a coarse observation_type per dominant signal (for section grouping only)
_TYPE_FOR_SIGNAL = {
    "infrastructure_positioning": "infrastructure_platform",
    "checkout_identity_rails": "infrastructure_platform",
    "platform_control": "infrastructure_platform",
    "data_network": "monetization_ecosystem",
    "partner_ecosystem_enablement": "monetization_ecosystem",
    "product_breadth": "product_surface",
    "storefront_creation": "product_surface",
    "enterprise_expansion": "buyer_segment",
    "smb_simplicity": "messaging",
    "merchant_outcome_positioning": "messaging",
    "agentic_commerce": "channel_distribution",
    "distribution_shift": "channel_distribution",
}


# One-line strategic MEANING per signal — an observation is this, not a title.
#
# THESE LABELS MUST BE INDUSTRY-NEUTRAL. The detectors below key off generic
# words — "infrastructure", "enterprise", "identity", "ecosystem", "simple" —
# which nearly every technology company uses, but the labels used to assert
# e-commerce as a fact. So Palantir's brief opened by telling the reader that
# Palantir "positions itself as commerce infrastructure" and "still centers
# small-merchant simplicity": confident, prominent, and wrong. A signal
# detector can honestly say WHAT SHAPE it saw; it cannot say what industry the
# company is in, and it must not imply one.
_SIGNAL_LABEL = {
    "infrastructure_positioning": "positions itself as infrastructure others "
                                  "build on",
    "checkout_identity_rails": "is consolidating transaction / identity rails",
    "agentic_commerce": "is building for AI agents as users or buyers",
    "distribution_shift": "is shifting where demand is captured (distribution)",
    "enterprise_expansion": "is expanding toward enterprise / larger buyers",
    "smb_simplicity": "still centers ease of adoption for smaller customers",
    "product_breadth": "is expanding first-party product breadth",
    "merchant_outcome_positioning": "frames value as customer outcomes",
    "partner_ecosystem_enablement": "leans on a partner / app ecosystem",
    "platform_control": "is consolidating control of key layers",
    "storefront_creation": "retains its original core product surface",
    "data_network": "is building a cross-customer data / distribution network",
}
_SIGNAL_RELEVANCE = {
    "infrastructure_positioning": "bears on whether value is moving from the "
                                  "product to the rails beneath it",
    "checkout_identity_rails": "bears on where durable advantage and lock-in sit",
    "agentic_commerce": "bears on a possible distribution shift to AI buyers",
    "enterprise_expansion": "bears on an up-market move and a tension with "
                            "smaller customers",
    "product_breadth": "bears on ecosystem lock-in vs value-proposition clarity",
}
# generic marketing / navigation language that is weak strategic evidence
_WEAK_PHRASES = (
    "sign up", "get started", "start free", "free trial", "book a demo",
    "learn more", "trusted by", "join thousands", "the best way", "log in",
    "contact sales", "terms of service", "privacy policy", "cookie",
)


# THE DOMAIN GATE.
#
# Every signal above feeds a pattern library of COMMERCE mechanisms. Keywords
# alone cannot separate "this company sells commerce infrastructure" from "this
# company uses the word infrastructure" — so a document must first show it is
# talking about commerce at all before any commerce signal is read from it.
#
# Without this, Palantir matched five commerce patterns on generic B2B
# vocabulary and was handed hypotheses about merchants and storefronts. The
# 2-signal threshold in the reasoning layer could not help: the detectors were
# manufacturing the signals it counted.
#
# This is a floor, not a classifier. It is deliberately cheap and obvious:
# a commerce company says these words constantly, and a defence-analytics
# company essentially never does.
_DOMAIN_ANCHORS = (
    "merchant", "commerce", "storefront", "checkout", "shopper", "retail",
    "e-commerce", "ecommerce", "online store", "seller", "point of sale",
    "shopping", "buyer", "cart", "marketplace",
)
MIN_DOMAIN_ANCHORS = 1


def in_commerce_domain(text: str) -> bool:
    """True when a document is plausibly about commerce at all."""
    low = " " + (text or "").lower() + " "
    return sum(1 for a in _DOMAIN_ANCHORS if a in low) >= MIN_DOMAIN_ANCHORS


def _detect_signals(text: str) -> list:
    low = " " + text.lower() + " "
    if not in_commerce_domain(text):
        return []
    return [sig for sig, phrases in _SIGNAL_KEYWORDS.items()
            if any(p in low for p in phrases)]


def _normalize_url(url: str) -> str:
    u = (url or "").split("#")[0].split("?")[0].rstrip("/").lower()
    return u.replace("https://", "").replace("http://", "").replace("www.", "")


def _is_weak(excerpt: str, title: str, signals: list) -> bool:
    """Title-only or generic marketing copy is weak strategic evidence."""
    ex = (excerpt or "").strip()
    if len(ex) < 40:
        return True                          # too thin to be a real observation
    if ex.lower() == (title or "").strip().lower():
        return True                          # a page title is not an observation
    low = ex.lower()
    generic_hits = sum(1 for p in _WEAK_PHRASES if p in low)
    # marketing-dominated snippet with only a single, non-specific signal
    return generic_hits >= 2 and len(signals) <= 1


def derive_observations(documents) -> list:
    """Build StrategicObservations from retrieved ingestion documents.

    Deduplicates repeated pages, filters title-only / generic-marketing noise
    into weak evidence, and records a real strategic signal (not a page title)
    for each observation. Only documents carrying at least one strategic signal
    become observations at all."""
    observations, seen = [], set()
    for doc in documents:
        # collapse duplicate pages: same content hash or same normalized URL
        key = doc.get("content_hash") or _normalize_url(doc.get("final_url", ""))
        norm = _normalize_url(doc.get("final_url", ""))
        if key in seen or (norm and norm in seen):
            continue
        seen.add(key)
        if norm:
            seen.add(norm)

        text = " ".join(filter(None, [
            doc.get("title", ""), doc.get("meta_description", ""),
            doc.get("text_content", "")]))
        signals = _detect_signals(text)
        if not signals:
            continue
        source_class = doc.get("source_class") or _SOURCE_CLASS.get(
            doc.get("source_type"), "company_owned")
        otype = _TYPE_FOR_SIGNAL.get(signals[0], "messaging")
        excerpt = (doc.get("meta_description")
                   or doc.get("text_content", "")[:280]).strip()
        title = doc.get("title", "")
        weak = _is_weak(excerpt, title, signals)
        dominant = signals[0]
        entity = (title or norm).split("—")[0].strip()[:80]
        strategic = f"{entity or 'The company'} {_SIGNAL_LABEL.get(dominant, 'shows a strategic signal')}"
        observations.append(StrategicObservation(
            observation_id=f"obs-{doc.get('source_id', '')}",
            text=strategic[:200],
            observation_type=otype,
            source_refs=[{"subsystem": "company_ingestion",
                          "artifact_type": "retrieved_source",
                          "artifact_id": doc.get("source_id", ""),
                          "source_class": source_class}],
            confidence="moderate",
            freshness=doc.get("freshness", "CURRENT"),
            directly_observed=True,
            signals=tuple(signals),
            source_class=source_class,
            excerpt=excerpt[:400],
            source_title=title or source_class,
            origin=doc.get("final_url", ""),
            date=(doc.get("retrieved_at", "") or "")[:10],
            strategic_signal=_SIGNAL_LABEL.get(dominant, ""),
            relevance=_SIGNAL_RELEVANCE.get(dominant, "adds context to the "
                                            "strategic picture"),
            entity=entity,
            weak=weak,
            evidence_quality="weak" if weak else "strong"))
    return observations

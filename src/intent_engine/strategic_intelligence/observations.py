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
_SIGNAL_KEYWORDS = {
    "infrastructure_positioning": ("infrastructure", "powering commerce",
                                   "commerce rails", "backbone", "platform for"),
    "checkout_identity_rails": ("checkout", "shop pay", "shoppay", "payments",
                                "wallet", "buyer identity", "identity"),
    "agentic_commerce": ("ai agent", "agentic", "ai-mediated", "ai shopping",
                         "shopping assistant", "ai commerce"),
    "distribution_shift": ("distribution", "marketplace", "shop app",
                           "discovery", "channels", "wherever your customers"),
    "enterprise_expansion": ("enterprise", "shopify plus", " plus ",
                             "large merchants", "commerce components"),
    "smb_simplicity": ("easy to", "simple", "anyone can", "get started",
                       "no code", "no-code", "start your business"),
    "product_breadth": ("capital", "fulfillment", "point of sale", "pos ",
                        "markets", "audiences", "suite", "everything you need"),
    "merchant_outcome_positioning": ("grow your business", "sell more",
                                     "grow your", "outcomes"),
    "partner_ecosystem_enablement": ("app store", "partners", "developers",
                                     "apps", "ecosystem"),
    "platform_control": ("first-party", "native", "we own", "owned",
                         "end-to-end"),
    "storefront_creation": ("storefront", "online store", "build your store",
                            "themes", "store builder"),
    "data_network": ("audiences", "network", "consumer data", "shopper data"),
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
_SIGNAL_LABEL = {
    "infrastructure_positioning": "positions itself as commerce infrastructure",
    "checkout_identity_rails": "is consolidating checkout / buyer-identity rails",
    "agentic_commerce": "is building for AI-agent / agentic commerce",
    "distribution_shift": "is shifting where demand is captured (distribution)",
    "enterprise_expansion": "is expanding toward enterprise / larger buyers",
    "smb_simplicity": "still centers small-merchant simplicity",
    "product_breadth": "is expanding first-party product breadth",
    "merchant_outcome_positioning": "frames value as merchant outcomes",
    "partner_ecosystem_enablement": "leans on a partner / app ecosystem",
    "platform_control": "is consolidating control of key layers",
    "storefront_creation": "retains storefront-creation as a core surface",
    "data_network": "is building a cross-merchant data / distribution network",
}
_SIGNAL_RELEVANCE = {
    "infrastructure_positioning": "bears on whether value is moving from the "
                                  "product to the rails beneath it",
    "checkout_identity_rails": "bears on where durable advantage and lock-in sit",
    "agentic_commerce": "bears on a possible distribution shift to AI buyers",
    "enterprise_expansion": "bears on an up-market move and SMB tension",
    "product_breadth": "bears on ecosystem lock-in vs value-proposition clarity",
}
# generic marketing / navigation language that is weak strategic evidence
_WEAK_PHRASES = (
    "sign up", "get started", "start free", "free trial", "book a demo",
    "learn more", "trusted by", "join thousands", "the best way", "log in",
    "contact sales", "terms of service", "privacy policy", "cookie",
)


def _detect_signals(text: str) -> list:
    low = " " + text.lower() + " "
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

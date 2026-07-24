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


def _detect_signals(text: str) -> list:
    low = " " + text.lower() + " "
    return [sig for sig, phrases in _SIGNAL_KEYWORDS.items()
            if any(p in low for p in phrases)]


def derive_observations(documents) -> list:
    """Build StrategicObservations from retrieved ingestion documents. Only
    documents that carry at least one strategic signal become observations."""
    observations = []
    for doc in documents:
        text = " ".join(filter(None, [
            doc.get("title", ""), doc.get("meta_description", ""),
            doc.get("text_content", "")]))
        signals = _detect_signals(text)
        if not signals:
            continue
        source_class = _SOURCE_CLASS.get(doc.get("source_type"), "company_owned")
        otype = _TYPE_FOR_SIGNAL.get(signals[0], "messaging")
        excerpt = (doc.get("meta_description")
                   or doc.get("text_content", "")[:240]).strip()
        observations.append(StrategicObservation(
            observation_id=f"obs-{doc.get('source_id', '')}",
            text=(doc.get("title") or doc.get("final_url", ""))[:160],
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
            source_title=doc.get("title") or source_class,
            origin=doc.get("final_url", ""),
            date=(doc.get("retrieved_at", "") or "")[:10]))
    return observations

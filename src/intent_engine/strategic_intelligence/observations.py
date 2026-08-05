"""V1.2 observation derivation for REAL runs.

Turns approved, retrieved ingestion documents into structured
StrategicObservations by detecting controlled-vocabulary signals in their text.
Signal detection is an internal reasoning input — never surfaced as a
"top terms" insight. A real run over company-owned pages only will, by design,
produce a one-sided observation set that the quality gate marks partial.
"""
from __future__ import annotations

import re
from functools import lru_cache

from intent_engine.strategic_intelligence.records import StrategicObservation


# --- phrase matching ----------------------------------------------------------
#
# Detection used to be `phrase in text`, which matches ACROSS WORD BOUNDARIES.
# The three-letter signal phrase "api" is a substring of "capital", "rapid",
# "therapies" and "capitalise", so every company that discussed capital
# allocation was reported as exposing "a surface others can build on". Sony
# Interactive Entertainment's corporate page tripped it on the single sentence
# "our capital allocation supports ... the rapid growth of our network".
#
# Matching is now anchored to word boundaries, with internal whitespace allowed
# to vary (spaces, hyphens and slashes) so "point of sale" still matches
# "point-of-sale".
@lru_cache(maxsize=8192)
def _phrase_pattern(phrase: str) -> "re.Pattern":
    parts = [re.escape(w) for w in phrase.split()]
    return re.compile(r"(?<!\w)" + r"[\s\-/]+".join(parts) + r"(?!\w)", re.I)


def _has_phrase(text: str, phrase: str) -> bool:
    return _phrase_pattern(phrase).search(text) is not None


def _any_phrase(text: str, phrases) -> bool:
    return any(_has_phrase(text, p) for p in phrases)

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
    # "simple", "easy to", "simplicity" and "fast setup" were removed: they are
    # marketing adjectives every consumer page uses and they carry no strategic
    # content. What remains describes a small-merchant GO-TO-MARKET.
    "smb_simplicity": ("anyone can sell", "start your business",
                       "no code", "no-code", "small business owners",
                       "launch your store", "sell online in minutes"),
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
    "capacity_investment": "organizational",
    "customer_concentration": "buyer_segment",
    "segment_reporting": "organizational",
    "disclosed_risk": "market_context",
    "content_and_channel": "product_surface",
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
    # neutral set is merged in below the commerce entries (see _NEUTRAL_LABEL)
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
# WHY EACH SIGNAL MATTERS — the mechanism, then the consequence.
#
# A supporting bullet that only restates the observation is not analysis. Live,
# the Sentry brief offered "API Authentication Bypass | Sentry Blog exposes a
# surface others can build on" as a reason to believe something: a page title
# welded to a label, answering neither "why does this matter" nor "so what".
#
# Each clause below completes the sentence "<Company> <label>, <clause>" and
# has to survive a founder asking "so what?" once. Written in plain language,
# not analyst vocabulary: these are read by someone deciding what to do, not
# by the system that produced them. Five of the twenty-six had a clause and
# the rest fell back to "retrieved evidence", which is not a reason.
_SIGNAL_RELEVANCE = {
    # --- commerce set ---
    "infrastructure_positioning": "so its growth depends on other companies "
                                  "building on top of it, not only on its own "
                                  "selling",
    "checkout_identity_rails": "so the durable advantage would sit in the "
                               "rails rather than the product above them",
    "agentic_commerce": "so the buyer it designs for may stop being a person",
    "distribution_shift": "so the channel it grew on may stop paying for "
                          "itself before the new one covers the gap",
    "enterprise_expansion": "so the roadmap now has two buyers to satisfy, "
                            "and they rarely want the same thing",
    "smb_simplicity": "so the promise that wins small customers is the one an "
                      "enterprise push would strain",
    "product_breadth": "so each addition buys lock-in and spends some of the "
                       "original product's sharpness",
    "merchant_outcome_positioning": "so it is judged on its customers' "
                                    "results rather than on its own feature "
                                    "list",
    "partner_ecosystem_enablement": "so part of what it sells is built by "
                                    "people it does not employ",
    "platform_control": "so it is taking ownership of layers its customers "
                        "would otherwise control themselves",
    "storefront_creation": "so the original product still carries the "
                           "customer relationship, whatever is added around "
                           "it",
    "data_network": "so the product improves as more customers use it, which "
                    "is the hardest thing for a newcomer to copy",
    # --- neutral set ---
    "multi_product": "so attention and engineering are split across products "
                     "that compete with each other for both",
    "segment_split": "so one roadmap has to serve buyers who want different "
                     "things",
    "named_customers": "so those customers agreed to be named, which is a "
                       "stronger claim than a logo wall",
    "developer_surface": "so other people's work comes to depend on it, and "
                         "that dependence is hard to unwind",
    "services_motion": "so growth needs people as well as software, and "
                       "margin follows headcount",
    "pricing_published": "so competitors can price against it directly and "
                         "customers can compare without a conversation",
    "pricing_gated": "so price is set deal by deal, which protects margin and "
                     "slows the sales cycle",
    "regulated_buyer": "so compliance becomes a moat and a constraint at the "
                       "same time",
    "consolidation": "so a customer who leaves later has to rebuild more than "
                     "one workflow to do it",
    "capacity_investment": "so the cost lands now while the payoff depends on "
                           "demand that has not arrived yet",
    "customer_concentration": "so a small number of buyers can move the whole "
                              "revenue line",
    "segment_reporting": "so the parts can be valued separately, and a weak "
                         "one has nowhere to hide",
    "disclosed_risk": "so these are the exposures management expects to be "
                      "held to, and each one can be checked against outcomes",
    "content_and_channel": "so it keeps the margin a distributor would take, "
                           "and no one else sits between it and the buyer",
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
# The anchors are MERCHANT-SIDE ONLY, and that distinction is the whole point.
# The previous list contained "checkout", "cart", "buyer", "shopping", "retail"
# and "marketplace" — the ordinary vocabulary of ANY consumer storefront. The
# PlayStation Store page ("add to cart and checkout securely ... every buyer")
# therefore opened the commerce gate, after which the bare adjectives "simple"
# and "easy to" matched `smb_simplicity` and a console business was handed a
# small-merchant strategy, with "SMB / Product" named as an affected function.
#
# Selling commerce infrastructure TO merchants and OPERATING a store are
# different businesses. Only the former says "merchant", "seller", "commerce",
# "sell online", "point of sale". The discrimination is done by the CONTENT of
# this list, not by a count: one merchant-side term is enough, because a games
# storefront can say "cart", "checkout", "buyer" and "shopping" all day without
# ever saying "merchant".
_DOMAIN_ANCHORS = (
    "merchant", "merchants", "seller", "sellers", "e-commerce", "ecommerce",
    "commerce", "storefront", "storefronts", "online store", "point of sale",
    "dropshipping", "sell online", "your store",
)
MIN_DOMAIN_ANCHORS = 1


def in_commerce_domain(text: str) -> bool:
    """True when a document is plausibly about selling commerce capability."""
    low = text or ""
    return sum(1 for a in _DOMAIN_ANCHORS
               if _has_phrase(low, a)) >= MIN_DOMAIN_ANCHORS


# --- domain-neutral signals ---------------------------------------------------
# The commerce set above is one domain library. These are shapes that any
# company can exhibit and that any reader would recognise as strategically
# meaningful, so a company outside commerce is not left with nothing to say.
#
# This gap was invisible until the product evaluation measured it: once the
# domain gate correctly stopped commerce patterns firing on Palantir, Linear
# and Notion, those companies produced no thesis, no hypothesis and no slides
# at all — and the pipeline still reported success, because "no hypothesis" is
# not an error anywhere downstream.
#
# Keep these OBSERVABLE. Each one should be something you could point at on a
# page, not a judgement about the company.
_NEUTRAL_SIGNAL_KEYWORDS = {
    # several distinct named products or platforms. Bare "platforms" and
    # "modules" were removed — one plural noun is not evidence of a portfolio.
    "multi_product": ("our products", "product suite", "three platforms",
                      "two platforms", "product family", "one platform for",
                      "our platforms", "product portfolio"),
    # the company names more than one kind of buyer. Bare "segments" was
    # removed: it matched any sentence containing the word, including
    # "customer segments" in a marketing page.
    "segment_split": ("government and commercial", "public and private sector",
                      "enterprise and small", "consumer and business",
                      "business units", "public sector",
                      "commercial customers", "government customers"),
    # specific named customers or deployments, not "trusted by thousands"
    "named_customers": ("case study", "case studies", "customer story",
                        "customer stories", "deployments include",
                        "named deployments", "customers include"),
    # a surface third parties can build on. Bare "documentation" was removed
    # (legal, support and help pages all have documentation); "api" is now
    # boundary-matched so it no longer fires inside "capital" or "rapid".
    "developer_surface": ("api", "apis", "rest api", "graphql", "public api",
                          "sdk", "developer docs", "developer documentation",
                          "developer portal", "webhooks", "integrations",
                          "open source"),
    # people-heavy delivery rather than self-serve
    "services_motion": ("forward deployed", "embed alongside",
                        "professional services", "implementation team",
                        "on site with", "bespoke deployment",
                        "solutions engineering"),
    # price is published vs gated
    "pricing_published": ("per seat", "per user", "starts at", "free plan",
                          "monthly price", "pricing page", "per month"),
    "pricing_gated": ("contact sales", "request a quote", "talk to sales",
                      "custom pricing", "quoted"),
    # buyers in regulated or accredited environments
    # Bare "compliance" and "regulated" were removed — every B2B page has a
    # compliance footer; that is not a regulated BUYER.
    "regulated_buyer": ("defence", "defense", "intelligence community",
                        "accredited", "regulated industries",
                        "regulated environments", "government systems",
                        "public procurement", "fedramp"),
    # explicit consolidation of previously separate tools. Bare "unified" was
    # removed: it is one of the most common words in corporate English, and on
    # its own it produced "absorbing adjacent tools until the work lives inside
    # it" for a company that had merely called itself a unified organisation.
    "consolidation": ("one workspace", "single system", "replace several",
                      "all in one", "connected workspace", "one place",
                      "unified platform", "unified suite",
                      "single source of truth"),
    # --- shapes that only a company with physical or disclosed operations
    # exhibits. Added because the neutral set above is a SOFTWARE-shaped
    # neutral set: it reads pricing pages, developer surfaces and workspace
    # consolidation. A manufacturer whose evidence is segment reporting,
    # capacity commitments and disclosed risk matched exactly one signal
    # ("segments") and therefore produced a brief with no hypothesis behind
    # it at all — a summary of what the company says, with nothing about what
    # it means.
    #
    # committed capacity: money spent before the demand arrives
    "capacity_investment": ("capacity expansion", "expansion of its image "
                            "sensor", "fabrication capacity",
                            "manufacturing capacity", "production capacity",
                            "capital allocation", "capital expenditure",
                            "sensor capacity", "expanding capacity",
                            "new facility", "plant capacity"),
    # a dependency the company itself has written down
    "customer_concentration": ("limited number of customers",
                               "small number of customers",
                               "limited number of smartphone customers",
                               "customer concentration",
                               "largest customers accounted",
                               "depend on a limited number",
                               "dependence on a limited number"),
    # formal segment reporting — a conglomerate shape, not a marketing one
    "segment_reporting": ("business segments", "operating segments",
                          "reportable segments", "segment revenue",
                          "segment results", "segment reporting",
                          "revenue and operating income for each"),
    # disclosure-grade statements of what could go wrong
    "disclosed_risk": ("risk factors", "principal risks", "risks disclosed",
                       "risk factors disclosed", "material weakness",
                       "these risks include"),
    # owns both the content and the channel it reaches people through
    # Bare "intellectual property" was removed: it is legal-footer boilerplate.
    "content_and_channel": ("creators and users", "first-party content",
                            "original content", "content and the hardware",
                            "catalogue of titles", "catalog of titles",
                            "content pipeline", "owned content"),
}

# Neutral labels — what the signal MEANS, stated so it is true of any industry.
_NEUTRAL_LABEL = {
    "multi_product": "sells several distinct products rather than one",
    "segment_split": "serves more than one clearly different buyer",
    "named_customers": "publishes named customers rather than logos alone",
    "developer_surface": "exposes a surface others can build on",
    "services_motion": "delivers through people, not only through software",
    "pricing_published": "publishes its prices",
    "pricing_gated": "keeps pricing behind a sales conversation",
    "regulated_buyer": "sells into regulated or accredited environments",
    "consolidation": "positions itself as replacing several separate tools",
    "capacity_investment": "is committing capital to capacity ahead of the "
                           "demand for it",
    "customer_concentration": "has written down a dependence on a few buyers",
    "segment_reporting": "reports as several separate businesses",
    "disclosed_risk": "discloses specific risks rather than generic caveats",
    "content_and_channel": "owns both what is sold and the channel it reaches "
                           "people through",
}


# --- claims that only count when somebody ELSE makes them ---------------------
#
# "Simple", "easy to use", "fast setup", "helps you grow" are meaningless as
# SELF-description: every company on earth says them, which is why they were
# removed from the detectors above. They are not meaningless as OUTSIDE
# description. When independent reviewers or customers repeatedly say a product
# is chosen FOR its simplicity, that is real evidence about the value
# proposition and the buyer it wins.
#
# So the rule is about who is speaking, not about the words. These phrases
# qualify a signal only from a vantage point that is not the company's own.
_OUTSIDE_ONLY_PHRASES = {
    "smb_simplicity": ("simple", "simplicity", "easy to", "fast setup",
                       "easy to use", "straightforward"),
    "merchant_outcome_positioning": ("helped us grow", "grew our sales",
                                     "increased our revenue"),
}
from intent_engine.strategic_intelligence.evidence_classes import (
    INDEPENDENT_CLASSES as _INDEPENDENT_CLASSES,
)

_OUTSIDE_VANTAGE_CLASSES = frozenset(_INDEPENDENT_CLASSES)


def _detect_neutral_signals(text: str) -> list:
    return [sig for sig, phrases in _NEUTRAL_SIGNAL_KEYWORDS.items()
            if _any_phrase(text or "", phrases)]


def _detect_signals(text: str, source_class: str = "company_owned") -> list:
    """Domain signals when the document is in that domain, plus the neutral
    set always. A company outside every domain library still has a strategy."""
    text = text or ""
    signals = list(_detect_neutral_signals(text))
    if in_commerce_domain(text):
        signals += [sig for sig, phrases in _SIGNAL_KEYWORDS.items()
                    if _any_phrase(text, phrases)]
        if source_class in _OUTSIDE_VANTAGE_CLASSES:
            signals += [sig for sig, phrases in _OUTSIDE_ONLY_PHRASES.items()
                        if sig not in signals and _any_phrase(text, phrases)]
    return signals


# --- what KIND of page this is ------------------------------------------------
#
# Distinct from source_class (whose account it is). A company's careers page and
# its product page are both company_owned, but only one of them is evidence of
# strategy.
#
# This was the qualifying evidence for Sony Interactive Entertainment's
# "turning a people-delivered service into a repeatable product" hypothesis: a
# CAREERS page listing job families ("solutions engineering", "professional
# services", "implementation team"). Those phrases describe who the company is
# hiring, not how it delivers value — and a recruiting page is the one place
# where every large company sounds like a consulting firm.
_NON_STRATEGIC_URL_MARKERS = {
    "careers": ("/careers", "/career", "/jobs", "/job/", "/join-us",
                "/life-at", "/working-at", "greenhouse.io", "lever.co",
                "myworkdayjobs", "/recruiting", "/vacancies"),
    "legal": ("/legal", "/terms", "/tos", "/privacy", "/cookie", "/gdpr",
              "/patents", "/trademark", "/accessibility-statement",
              "/modern-slavery", "/imprint"),
    "support": ("/support", "/help", "/faq", "/contact", "/customer-service",
                "/returns", "/warranty", "/troubleshoot", "/service-status"),
}
_NON_STRATEGIC_TITLE_MARKERS = {
    "careers": ("careers", "jobs at", "work with us", "join our team",
                "life at", "open roles", "open positions"),
    "legal": ("terms of service", "terms of use", "terms and conditions",
              "privacy policy", "privacy notice", "cookie policy",
              "cookie notice", "legal notice"),
    "support": ("help centre", "help center", "support centre",
                "support center", "frequently asked questions",
                "contact us", "customer support"),
}


def page_kind(url: str, title: str = "") -> str:
    """Classify a retrieved page. 'strategic' means it may carry strategy."""
    u = (url or "").lower()
    t = (title or "").strip().lower()
    for kind, markers in _NON_STRATEGIC_URL_MARKERS.items():
        if any(m in u for m in markers):
            return kind
    for kind, markers in _NON_STRATEGIC_TITLE_MARKERS.items():
        if any(t.startswith(m) or m in t for m in markers):
            return kind
    return "strategic"


def qualifying_signals_of(observation) -> set:
    """The signals an observation may use to QUALIFY a hypothesis.

    Weak evidence — a page title, a snippet that is mostly calls-to-action —
    can still appear as context, but it must never be the reason a strategic
    claim fires. Previously `_signals_present` unioned every observation's
    signals regardless of quality, so a marketing snippet could push a
    hypothesis over its threshold on its own.
    """
    if getattr(observation, "weak", False):
        return set()
    return set(observation.signals)


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


#: below this, a page has no substance worth reasoning over
MIN_ANALYST_EXCERPT_CHARS = 120


def derive_analyst_evidence(documents, company: str = "") -> list:
    """Evidence for the grounded analyst -- every strategic page, signal or not.

    `derive_observations` below requires a controlled-vocabulary signal match,
    because a signal is the unit the PATTERN LIBRARY matches against. For the
    analyst that requirement is not just unnecessary, it is harmful: the
    analyst reads excerpts and reasons over them, so a document that matches no
    keyword is not uninformative to it.

    The cost of conflating the two was measured. An independent analysis of
    console economics -- hardware sold near cost, margin recovered through
    software attach and subscriptions, and a named contrast with a competitor's
    day-one first-party strategy -- matched zero signals and was dropped
    entirely. That is the single most valuable document in the set, and the one
    an independent vantage point is hardest to get.

    So the two consumers get two derivations from the same documents. This one
    filters on whether a human would consider the page evidence at all: is it a
    strategic page, and does it actually say something.
    """
    evidence, seen = [], set()
    for doc in documents:
        key = doc.get("content_hash") or _normalize_url(
            doc.get("final_url", ""))
        norm = _normalize_url(doc.get("final_url", ""))
        if key in seen or (norm and norm in seen):
            continue
        seen.add(key)
        if norm:
            seen.add(norm)

        title = doc.get("title", "")
        if page_kind(doc.get("final_url", ""), title) != "strategic":
            continue

        body = (doc.get("text_content") or "").strip()
        # AN INDEPENDENT SOURCE STILL HAS TO SAY SOMETHING.
        #
        # Measured on the eighteen third-party filings this product accepts:
        # seventeen were not statements about the subject at all -- executive
        # compensation peer groups, XBRL taxonomy fragments, director
        # biographies, forward-looking boilerplate. They raised the
        # independence COUNT and taught the analyst nothing.
        #
        # Only third-party sources are screened. Company-owned pages are the
        # company describing itself and are expected to; the question there is
        # never "is this about the company".
        if (doc.get("source_class") or "") == "competitor":
            from intent_engine.strategic_intelligence.claim_relevance import (
                assess,
            )
            verdict = assess(text=body, company_name=company or "")
            if not verdict.usable_as_support:
                continue
        excerpt = (body or doc.get("meta_description") or "").strip()
        if len(excerpt) < MIN_ANALYST_EXCERPT_CHARS:
            continue

        source_class = doc.get("source_class") or _SOURCE_CLASS.get(
            doc.get("source_type"), "company_owned")
        text = " ".join(filter(None, [
            title, doc.get("meta_description", ""), body]))
        signals = _detect_signals(text, source_class)
        weak = _is_weak(excerpt, title, signals)
        dominant = signals[0] if signals else ""
        entity = (title or norm).split("—")[0].strip()[:80]
        evidence.append(StrategicObservation(
            observation_id=f"obs-{doc.get('source_id', '')}",
            text=(f"{entity or 'The company'} "
                  f"{_SIGNAL_LABEL[dominant]}" if dominant
                  else excerpt[:200]),
            observation_type=_TYPE_FOR_SIGNAL.get(dominant, "messaging"),
            source_refs=[{"subsystem": "company_ingestion",
                          "artifact_type": "retrieved_source",
                          "artifact_id": doc.get("source_id", ""),
                          "source_class": source_class}],
            confidence="moderate",
            freshness=doc.get("freshness", "CURRENT"),
            directly_observed=True,
            signals=tuple(signals),
            source_class=source_class,
            excerpt=excerpt[:1200],
            source_title=title or source_class,
            origin=doc.get("final_url", ""),
            date=(doc.get("retrieved_at", "") or "")[:10],
            strategic_signal=_SIGNAL_LABEL.get(dominant, ""),
            relevance=_SIGNAL_RELEVANCE.get(dominant, "retrieved evidence"),
            entity=entity,
            weak=weak,
            evidence_quality="weak" if weak else "strong"))
    return evidence


def observation_sentence(subject: str, signal: str, label: str) -> str:
    """"<Company> <what it does>, <why that matters>." — one analytical claim.

    The clause is dropped rather than faked when a signal has no stated
    consequence: a sentence that stops after the label is still true, and
    padding it with "which is a strategic signal" would be the template
    wording this product exists to avoid.
    """
    subject = " ".join((subject or "The company").split())
    sentence = f"{subject} {label}".rstrip(" .")
    because = _SIGNAL_RELEVANCE.get(signal, "")
    return f"{sentence}, {because}." if because else f"{sentence}."


def derive_observations(documents, *, company: str = "") -> list:
    """Build StrategicObservations from retrieved ingestion documents.

    Deduplicates repeated pages, filters title-only / generic-marketing noise
    into weak evidence, and records a real strategic signal (not a page title)
    for each observation.

    Only documents carrying at least one strategic signal become observations.

    KNOWN LIMITATION (measured, not theoretical). A run can retrieve real
    pages, match no signal, and therefore produce no observations, no report
    and no brief — while the pipeline still reports success. The product
    evaluation catches this as "evidence was retrieved but no brief,
    hypothesis or slide was produced"; it currently affects companies whose
    pages are purely descriptive.

    Admitting signal-free documents as descriptive observations is NOT the
    fix: it was tried, and it breaks the meaning of an observation across the
    reasoning layer (76 tests, which are right to object — an observation is
    the unit patterns match against). The fix belongs one level up, where a
    run with documents but no strategic report should still render an
    evidence-grounded descriptive brief instead of redirecting to nothing.
    """
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

        title = doc.get("title", "")
        # Careers / legal / support pages are retrieved and kept for the source
        # library, but they are not evidence of strategy and must not qualify a
        # hypothesis. See `page_kind`.
        if page_kind(doc.get("final_url", ""), title) != "strategic":
            continue

        text = " ".join(filter(None, [
            title, doc.get("meta_description", ""),
            doc.get("text_content", "")]))
        source_class = doc.get("source_class") or _SOURCE_CLASS.get(
            doc.get("source_type"), "company_owned")
        signals = _detect_signals(text, source_class)
        if not signals:
            continue
        otype = _TYPE_FOR_SIGNAL.get(signals[0], "messaging")
        excerpt = (doc.get("meta_description")
                   or doc.get("text_content", "")[:280]).strip()
        weak = _is_weak(excerpt, title, signals)
        dominant = signals[0]
        entity = (title or norm).split("—")[0].strip()[:80]
        # The SUBJECT of a strategic claim is the company, never the page it
        # was found on. Taking it from the title produced, verbatim on
        # production: "API Authentication Bypass | Sentry Blog exposes a
        # surface others can build on" and "Linear customers publishes named
        # customers rather than logos alone" -- a headline welded to a label,
        # ungrammatical, and attributing the company's behaviour to a URL.
        #
        # The clause after the label answers the question a bullet exists to
        # answer: why does this matter? Without it the sentence restates the
        # observation and stops.
        strategic = observation_sentence(
            company or "The company", dominant,
            _SIGNAL_LABEL.get(dominant, "shows a strategic signal"))
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

# The neutral signals participate in exactly the same maps as the domain ones,
# so nothing downstream needs to know there are two libraries.
_SIGNAL_KEYWORDS.update(_NEUTRAL_SIGNAL_KEYWORDS)
_SIGNAL_LABEL.update(_NEUTRAL_LABEL)
_TYPE_FOR_SIGNAL.update({
    "multi_product": "product_surface",
    "consolidation": "product_surface",
    "developer_surface": "infrastructure_platform",
    "segment_split": "buyer_segment",
    "regulated_buyer": "buyer_segment",
    "named_customers": "monetization_ecosystem",
    "services_motion": "messaging",
    "pricing_published": "messaging",
    "pricing_gated": "buyer_segment",
})

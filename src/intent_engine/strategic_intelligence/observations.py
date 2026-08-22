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

from intent_engine.strategic_intelligence import evidence_text as ET
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


# --- WHERE a signal was found, not merely THAT it was ------------------------
#
# THE DEFECT THIS EXISTS TO FIX. An observation is one document, and carries
# every signal detected anywhere in it — HubSpot's 10-K carried eighteen. Its
# `excerpt` is chosen ONCE for the whole document (the filing's best section,
# or its opening), so it can be the right evidence for at most one of those
# eighteen signals, and in practice for none of them.
#
# Measured live at bdbc0d0: `tool_to_system_of_record` qualified for HubSpot on
# `system_of_record_claim`, which is genuinely there — the 10-K says "Our
# customer platform includes a system of record for maintaining a unified view
# of the customer experience". The reader was shown "We provide an agentic
# customer platform that helps marketing, sales, and customer service teams
# drive business growth", the document's first 400 characters, which says
# nothing of the kind. The gate fired correctly and the explanation layer
# showed the wrong four hundred characters.
#
# So a signal now carries the sentence that produced it. Evidence for a claim
# is the text that caused the claim, or it is not evidence for that claim.
_MAX_SPAN = 320
#: How many occurrences of a phrase to test for ownership before giving up.
#: See `owned_match`.
_MAX_OCCURRENCES = 20


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing a match, trimmed to something quotable."""
    left = text.rfind(". ", 0, start)
    left = 0 if left < 0 else left + 2
    right = text.find(". ", end)
    right = len(text) if right < 0 else right + 1
    span = " ".join(text[left:right].split())
    if len(span) > _MAX_SPAN:
        # keep the match itself in view rather than truncating from the left
        rel = start - left
        head = max(0, rel - _MAX_SPAN // 2)
        # ...and cut at word boundaries. Measured on the deployed Palantir
        # result: the quote opened "…ong with ongoing O&M services", a
        # half-word the reader has to decode before they can judge the
        # evidence. A quotation is only checkable if it reads as language.
        if head:
            space = span.find(" ", head)
            head = space + 1 if 0 <= space < head + 40 else head
        tail = head + _MAX_SPAN
        if tail < len(span):
            space = span.rfind(" ", head, tail)
            tail = space if space > head else tail
        span = (("…" if head else "") + span[head:tail].strip()
                + ("…" if tail < len(span) else ""))
    return span


def _foreign_match(text, match, company) -> bool:
    """Whether this occurrence belongs to somebody other than the company."""
    from intent_engine.strategic_intelligence import subject as SUBJ
    # Scoped to the sentence, so a subject three sentences back cannot govern
    # this clause. `filing_detectors` has matched sentence-scoped from the
    # start for the same reason.
    left = text.rfind(". ", 0, match.start())
    left = 0 if left < 0 else left + 2
    return SUBJ.subject_of(text[left:match.end()],
                           match.start() - left, company) == SUBJ.FOREIGN


def owned_match(text: str, phrases, company: str = ""):
    """The first occurrence of any phrase that is NOT somebody else's.

    REJECT FOREIGN RATHER THAN REQUIRE OWN, deliberately, and this is the one
    place this cycle does not fail closed on `unknown`.

    Marketing copy is largely subjectless — "Explore the suite", "One platform
    for everything" — so requiring an explicit owner would silence most of
    what a company publishes about itself and call it rigour. On a page the
    company owns, an unattributed sentence is the company talking; that is
    provenance, which the run already establishes, not proximity, which is
    what this module exists to stop trusting.

    A demonstrably foreign subject is different, and is always rejected.
    """
    for phrase in phrases:
        # BOUNDED. When every occurrence is somebody else's, the loop would
        # otherwise walk all of them — and a 10-K can repeat a phrase across
        # hundreds of risk-factor sentences, which is precisely the document
        # where the subject is most often foreign. A company that owns the
        # claim states it early; twenty occurrences is a generous place to
        # stop looking, and stopping there fails closed rather than open.
        for n, match in enumerate(_phrase_pattern(phrase).finditer(text or "")):
            if n >= _MAX_OCCURRENCES:
                break
            if not _foreign_match(text, match, company):
                return match
    return None


def phrase_span(text: str, phrases, company: str = "") -> str:
    """The first sentence in `text` that evidences one of `phrases`.

    Skips occurrences owned by someone else: quoting a competitor's sentence
    as this company's evidence is the defect this cycle removes.
    """
    match = owned_match(text, phrases, company)
    return _sentence_around(text, match.start(), match.end()) if match else ""


def signal_spans(text: str, signals=(), company: str = "") -> dict:
    """signal -> the sentence in this document that evidenced it.

    Only the keyword-driven vocabularies are resolvable this way; filing
    propositions are matched by their own sentence-scoped rules and carry
    their span through `filing_detectors`. A signal with no resolvable span is
    ABSENT from this mapping rather than present-and-empty, so a caller can
    tell "no evidence to show" from "evidence is the empty string".
    """
    text = text or ""
    wanted = set(signals) if signals else None
    spans = {}
    for table in (_NEUTRAL_SIGNAL_KEYWORDS, _SIGNAL_KEYWORDS,
                  _OUTSIDE_ONLY_PHRASES):
        for signal, phrases in table.items():
            if signal in spans or (wanted is not None and signal not in wanted):
                continue
            span = phrase_span(text, phrases, company)
            if span:
                spans[signal] = span
    return spans

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
    # BARE "checkout" WAS REMOVED. Every commerce site has a checkout; the
    # word says nothing about owning the rails underneath one, and it was one
    # of the three signals that fired on Shopify from a single ordinary
    # sentence. Same defect as bare "defence" in `regulated_buyer` and bare
    # "system of record" in the mechanism set: the phrase has to carry the
    # claim, not merely co-occur with the topic.
    "checkout_identity_rails": ("one-click checkout", "checkout api",
                                "hosted checkout", "checkout rails",
                                "shop pay", "shoppay",
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
    "productization": "so what the engagements taught is being sold without "
                      "them, which is the margin the transition is for",
    "pricing_published": "so competitors can price against it directly and "
                         "customers can compare without a conversation",
    "pricing_gated": "so price is set deal by deal, which protects margin and "
                     "slows the sales cycle",
    "regulated_buyer": "so compliance becomes a moat and a constraint at the "
                       "same time",
    "gov_dedicated_delivery": "so part of the engineering budget is spent "
                              "serving one buyer type that the commercial "
                              "product does not benefit from",
    "accreditation_gate": "so the authorization, not the product, decides "
                          "when a deal may close",
    "public_procurement_vehicle": "so the buying cycle is set by a budget "
                                  "calendar rather than by the customer's "
                                  "need",
    "disclosed_public_sector_exposure": "so a shift in public budgets reaches "
                                        "the revenue line directly",
    "human_intervention_reduced": "so the labour it replaces is the thing "
                                  "being sold, not the software",
    "agent_executes_actions": "so the work leaves the person who used to "
                              "do it, and the labour it replaces is the "
                              "thing being sold",
    "agent_callable_endpoint": "so demand can arrive without a human ever "
                               "seeing the interface it used to arrive "
                               "through",
    "human_in_the_loop": "so the workflow has not actually changed hands",
    "cross_product_coupling": "so the products stop being separable to a "
                              "customer, and to anyone reading their "
                              "performance apart",
    "independently_operated": "so a weak business can be sold or closed "
                              "without disturbing the others",
    "third_party_builds_on": "so leaving means other people's work stops "
                             "working, not just yours",
    "external_operations_depend": "so the switching cost is an operational "
                                  "migration for somebody else's business, "
                                  "not a procurement decision",
    "consolidation": "so a customer who leaves later has to rebuild more than "
                     "one workflow to do it",
    "system_of_record_claim": "so the data other systems trust now lives here, "
                              "and leaving means moving the record itself",
    "shared_data_model": "so the products stop being separable: the second one "
                         "is worth more because the first already holds the "
                         "data",
    "replaces_incumbent_systems": "so the customer has already retired the "
                                  "thing they would otherwise fall back to",
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
    #
    # TWO GROUPS, OR IT IS NOT A SPLIT. Half of this list used to name only
    # ONE buyer — "public sector", "commercial customers", "government
    # customers" — and one named none at all: "business units" is the
    # company's own org chart, not who it sells to. The signal's own label is
    # "serves more than one clearly different buyer", and the pattern that
    # depends on it says it does not apply when "only one buyer group is ever
    # described". Both were contradicted by the detector.
    #
    # Every phrase here is a PAIR. A company that only ever mentions the
    # public sector is a company with one buyer, and the reading built on this
    # signal — that the organisation is pulling apart to serve a second one —
    # is not true of it.
    "segment_split": ("government and commercial",
                      "commercial and government",
                      "public and private sector",
                      "private and public sector",
                      "enterprise and small", "small and enterprise",
                      "enterprise and smb", "smb and enterprise",
                      "consumer and business", "consumers and businesses",
                      "startups and enterprises",
                      "individuals and teams",
                      "self-serve and enterprise",
                      "developers and enterprises"),
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
    # THE TRANSFER ITSELF, which is a different claim from having services.
    # "services → product" is not "this company has a services page"; it is
    # "what the engagements taught became something sold without them". Almost
    # every large vendor has the first. Only some describe the second, and the
    # phrases below are the ones that describe it rather than imply it.
    #
    # Measured: with `services_motion` alone required, the reading still
    # dominated MongoDB, Cloudflare, HubSpot and Amazon, all of which publish
    # professional-services pages and none of which claimed the transfer.
    "productization": ("productize", "productized", "productise",
                       "productised", "productizing",
                       "what we learned delivering", "learned from delivering",
                       "learned delivering", "codified into",
                       "codify what", "packaged into a product",
                       "packaged as a product", "now available as a product",
                       "from bespoke to", "turned into a repeatable",
                       "into a repeatable product", "repeatable offering",
                       "reusable accelerators", "delivery accelerators",
                       "reference implementations",
                       "self-serve version of", "productized service"),
    # price is published vs gated
    "pricing_published": ("per seat", "per user", "starts at", "free plan",
                          "monthly price", "pricing page", "per month"),
    "pricing_gated": ("contact sales", "request a quote", "talk to sales",
                      "custom pricing", "quoted"),
    # buyers in regulated or accredited environments — the company SAYING it
    # serves them. This is a marketing surface, and it is kept as one: it is
    # context and it may colour a segment reading, but on its own it is not
    # evidence that regulated buyers drive the business. For that see the
    # mechanism signals below.
    #
    # Bare "compliance" and "regulated" were removed earlier — every B2B page
    # has a compliance footer; that is not a regulated BUYER.
    #
    # Bare "defence"/"defense" were removed 2026-08-06 and MUST NOT COME BACK.
    # Measured on HubSpot's live security page: "HubSpot uses a
    # defense-in-depth approach to implement layers of security" — a security
    # ARCHITECTURE phrase — matched `regulated_buyer` and was, with a
    # case-studies page, most of the reason HubSpot and Snowflake were handed
    # the same "dependence on regulated or public-sector buyers" conclusion.
    # The buyer has to be named as a buyer.
    "regulated_buyer": ("defence sector", "defense sector",
                        "defence customers", "defense customers",
                        "department of defense", "ministry of defence",
                        "intelligence community", "accredited",
                        "regulated industries", "regulated environments",
                        "government systems", "public procurement",
                        "government agencies", "public sector customers"),
    # --- regulated-buyer CAUSAL MECHANISMS ------------------------------------
    # Each of the four below is something a company only has if regulated or
    # public-sector buyers actually shaped it: a place it had to build, an
    # authorization it had to win, a way it had to be bought, or an exposure it
    # had to disclose. A compliance badge, a security page or one case study
    # produces none of them.
    #
    # They are separate signals rather than one, so the reading can say WHICH
    # mechanism it read off — two companies that genuinely qualify then get two
    # different sentences because they have two different mechanisms, not
    # because the prose was varied.
    #
    # somewhere it had to build: a separate region/estate for these buyers
    "gov_dedicated_delivery": ("govcloud", "government cloud", "gov cloud",
                               "sovereign cloud", "sovereign region",
                               "sovereign deployment", "dedicated government "
                               "region", "public sector edition",
                               "government community cloud", "air gapped",
                               "in-country data residency"),
    # something it had to win before it could sell: an authorization that
    # gates the purchase. NOT a general assurance badge — SOC 2, ISO 27001,
    # GDPR and HIPAA are deliberately absent, because every B2B vendor has
    # them and they gate nothing.
    "accreditation_gate": ("fedramp", "stateramp", "impact level", "il4",
                           "il5", "il6", "cjis", "itar", "dod provisional",
                           "provisional authorization",
                           "authority to operate", "criminal justice "
                           "information services"),
    # a way it had to be bought: public procurement machinery
    "public_procurement_vehicle": ("gsa schedule", "contract vehicle",
                                   "procurement vehicle", "g-cloud",
                                   "sewp", "idiq",
                                   "blanket purchase agreement",
                                   "framework agreement", "ccs framework"),
    # an exposure it had to write down: materiality, in its own words.
    # "government revenue" and "federal revenue" are here because reporting
    # one as its own line IS the disclosure — a company does not separate a
    # revenue line for a buyer type that does not matter to it. This is what
    # Palantir's investor page says ("quarterly results separate United States
    # government revenue from United States commercial revenue"), and it is a
    # far better reason to reach a buyer-concentration reading than the word
    # "defence" appearing on a product page.
    "disclosed_public_sector_exposure": (
        "government customers accounted", "public sector revenue",
        "revenue from government", "government contracts represented",
        "sales to government", "public sector segment revenue",
        "depend on government contracts", "government appropriations",
        "government revenue", "federal revenue", "government segment"),
    # explicit consolidation of previously separate tools. Bare "unified" was
    # removed: it is one of the most common words in corporate English, and on
    # its own it produced "absorbing adjacent tools until the work lives inside
    # it" for a company that had merely called itself a unified organisation.
    "consolidation": ("one workspace", "single system", "replace several",
                      "all in one", "connected workspace", "one place",
                      "unified platform", "unified suite",
                      "single source of truth"),
    # --- human-to-agent-workflow CAUSAL MECHANISMS ----------------------------
    #
    # THE HIGHEST-FREQUENCY UNGATED READING IN THE LIBRARY. Live it fired for
    # Amazon, HubSpot, Shopify and Stripe, all with the identical sentence.
    # Reproduced from one line: the bare word "agentic" plus "marketplace"
    # qualifies it. "Agentic" is a 2025-26 marketing word every commerce and
    # SaaS company now prints; "marketplace" is a distribution noun.
    #
    # `when_it_applies` names three clauses and the first is "ships agent/
    # AI-commerce ENDPOINTS". Nothing measured that. `when_it_does_not_apply`
    # says the reading fails where "buying remains human-driven … with no
    # agent endpoints".
    #
    # An AI feature is a capability. A workflow a human used to run being
    # executed by software that acts is the transition — which is what moves
    # where demand is captured.
    #
    # DIRECTIONAL. "assistant", "copilot" and "agentic" are absent by design:
    # drafting and suggesting leave the human doing the work.
    "agent_executes_actions": ("acts on your behalf", "act on your behalf",
                               "agents complete", "agent completes",
                               "agents place orders", "agent places orders",
                               "agents purchase", "completes the purchase",
                               "executes the workflow", "agents execute"),
    # THE OTHER HALF OF THE SAME TRANSITION: the human stops doing it.
    #
    # Split out after measuring recall at 0.60. Folded into
    # `agent_executes_actions` these phrases produced ONE signal, so a genuine
    # description ("agents execute the workflow with no human intervention")
    # still needed a generic commerce attribute to clear the threshold — the
    # mechanism was not sufficient on its own, which is backwards. Two
    # mechanism signals mean a real description qualifies on mechanism alone
    # and marketing vocabulary still cannot.
    "human_intervention_reduced": ("without human intervention",
                                   "no human intervention", "unattended",
                                   "hands-off", "zero touch",
                                   "end-to-end autonomously",
                                   "runs autonomously", "fully autonomous"),
    # A surface built for a machine caller rather than a person. This is the
    # clause `when_it_applies` already required and nothing measured.
    "agent_callable_endpoint": ("agentic checkout", "agent api",
                                "agent-ready", "agent ready",
                                "for ai agents to", "machine-readable checkout",
                                "mcp server", "agent toolkit",
                                "agent protocol"),
    # The stated counter-case: the human is still doing it.
    "human_in_the_loop": ("requires your approval", "requires human approval",
                          "you review and approve", "human review is required",
                          "review before it is sent",
                          "recommends rather than", "suggests rather than",
                          "always keeps a human in the loop"),
    # --- portfolio-run-as-one CAUSAL MECHANISM --------------------------------
    #
    # `portfolio_run_as_one.when_it_applies` requires the company to report
    # several segments AND to describe "owning both the content or product and
    # the channel that distributes it" — a COUPLING. The gate was any two of
    # `segment_reporting`, `content_and_channel` and `multi_product`, so
    # "operating segments" plus "our product portfolio" was enough, and that
    # is every multi-product filer. Measured live: HubSpot, Microsoft and
    # Stripe all received it, the highest live frequency of any ungated
    # pattern with no disconfirmers.
    #
    # `content_and_channel` already carries the coupling for a media-shaped
    # company (owned titles plus the box they play on). This is the same
    # coupling for a software-shaped one: the businesses are run as one
    # because they share the machinery a customer actually touches.
    "cross_product_coupling": ("cross-product", "across our products",
                               "one account across", "single sign-on across",
                               "unified billing", "common billing",
                               "one contract across", "shared services across",
                               "bundled across", "adopt more than one of our"),
    # THE DISCONFIRMER THE PATTERN ALREADY DESCRIBED AND NEVER DECLARED.
    # `when_it_does_not_apply` says "segments are unrelated holdings with no
    # described operational connection" — the Constellation Software shape.
    # A company that says its businesses are run separately is telling you the
    # coupling is absent.
    "independently_operated": ("operates independently",
                               "operate independently",
                               "standalone businesses", "separately managed",
                               "autonomous business units",
                               "decentralised operating model",
                               "decentralized operating model",
                               "run as separate businesses"),
    # --- product-to-platform CAUSAL MECHANISMS --------------------------------
    #
    # THE PATTERN NAMED ITS OWN MECHANISM AND HAD NO SIGNAL FOR IT.
    # `product_to_platform.when_it_applies` requires three things: the company
    # frames itself as infrastructure, it owns payment/identity rails, AND
    # "third parties increasingly build on it". `when_it_does_not_apply` says
    # it does not hold when "there is no third-party build-on ecosystem".
    # There was no signal for third-party dependence anywhere in the
    # qualifying set, so the reading could fire with none of it.
    #
    # Measured live at 037f805 on Shopify, and reproducible from one ordinary
    # sentence: "commerce platform" + "checkout" + "one platform for" lights
    # three of the four qualifying signals against a threshold of two. Every
    # commerce company with a checkout and a platform claim was told it is
    # "repositioning toward operating the payment, identity, data and
    # distribution rails its market runs on".
    #
    # An app store is a thing a company HAS. Outsiders whose own operations
    # stop working without you is the mechanism. These two signals are the
    # difference, and both are DIRECTIONAL: "build on our" cannot match "we
    # build on AWS", which is the same relationship pointing the other way.
    # Third-person forms are safe HERE and would not have been a cycle ago:
    # `subject.py` now rejects an occurrence whose nearest governing subject
    # is a rival, so "extend the platform" cannot be harvested from a sentence
    # about a competitor's ecosystem. The possessive-only list missed the
    # commonest phrasing — Shopify's own fixture says "merchants extend the
    # platform", which is precisely the mechanism.
    "third_party_builds_on": ("build on our", "built on our", "builds on our",
                              "building on our", "developers build on",
                              "partners build on", "apps built on",
                              "integrations built on", "extend our platform",
                              "extend the platform", "extends the platform",
                              "build on the platform",
                              "built on the platform"),
    # Not "they integrate with us" — an integration is switchable by
    # reconnecting it. This is the customer's own operation running on top.
    "external_operations_depend": ("run their business on",
                                   "run their businesses on",
                                   "power their business",
                                   "powers their business",
                                   "businesses run on", "merchants run on",
                                   "depend on our platform",
                                   "rely on our platform",
                                   "rely on our infrastructure",
                                   "depend on our infrastructure"),
    # --- tool-to-system-of-record CAUSAL MECHANISMS ---------------------------
    # `consolidation` is what a company SAYS; `multi_product` and
    # `developer_surface` are things almost every B2B software company HAS.
    # The pattern's own mechanism is that the customer's source of truth moves
    # and switching cost rises once other systems read from it — and none of
    # those three establishes that. Measured live at dad7d28: Palantir,
    # HubSpot and Snowflake each qualified on multi_product + developer_surface
    # and were handed the same secondary sentence, name-substituted.
    #
    # Each of the three below is something a company only has if the record
    # really is moving into it.
    # DIRECTIONAL PHRASES ONLY. Bare "system of record" and "system of truth"
    # were tried and removed the same day: they match the sentence that says
    # the record lives SOMEWHERE ELSE. "We integrate with your existing tools;
    # two-way sync keeps your system of truth wherever it already lives" is
    # the exact opposite of this mechanism and matched it. A keyword cannot
    # read negation, so the phrase itself has to carry the direction — the
    # same reason bare "defence" is banned from `regulated_buyer` above.
    "system_of_record_claim": ("system of record for", "the system of record",
                               "becomes your system of record",
                               "source of truth for your",
                               "authoritative record", "golden record"),
    # the thing that actually creates the lock-in: not several products, but
    # several products over ONE model of the customer's data.
    "shared_data_model": ("shared data model", "common data model",
                          "unified data model", "single data model",
                          "one data layer", "shared schema",
                          "same underlying data"),
    # the customer had a system and stopped using it. "Integrates with" is
    # deliberately absent — integration is the opposite of replacement.
    "replaces_incumbent_systems": ("replace your existing", "migrate off",
                                   "rip and replace", "retire legacy",
                                   "consolidate your stack", "sunset your",
                                   "move off spreadsheets"),
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
    "productization": "describes turning delivered work into something sold on its own",
    "pricing_published": "publishes its prices",
    "pricing_gated": "keeps pricing behind a sales conversation",
    "regulated_buyer": "sells into regulated or accredited environments",
    "gov_dedicated_delivery": "runs a separate estate built for government or "
                              "sovereign deployment",
    "accreditation_gate": "holds an authorization that public buyers require "
                          "before they may purchase",
    "public_procurement_vehicle": "is bought through public procurement "
                                  "machinery rather than ordinary sales",
    "disclosed_public_sector_exposure": "has written down what public-sector "
                                        "buyers contribute",
    "consolidation": "positions itself as replacing several separate tools",
    "agent_executes_actions": "describes software acting rather than suggesting",
    "human_intervention_reduced": "describes the workflow running without a person",
    "agent_callable_endpoint": "ships a surface built for a machine caller",
    "human_in_the_loop": "keeps a person in every step of the workflow",
    "cross_product_coupling": "runs its products over shared identity, billing or contracts",
    "independently_operated": "says its businesses are run separately from one another",
    "third_party_builds_on": "has outside organisations building on it",
    "external_operations_depend": "has customers running their own operations on it",
    "system_of_record_claim": "claims to hold the authoritative record, not a "
                              "copy of it",
    "shared_data_model": "runs its products over one model of the customer's "
                         "data",
    "replaces_incumbent_systems": "describes customers retiring a system they "
                                  "already had",
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
from intent_engine.strategic_intelligence import filing_detectors as FD
from intent_engine.strategic_intelligence import filing_sections as FS


def FD_looks_like_filing(text: str) -> bool:
    return FS.looks_like_filing(text)
from intent_engine.strategic_intelligence.evidence_classes import (
    INDEPENDENT_CLASSES as _INDEPENDENT_CLASSES,
)

_OUTSIDE_VANTAGE_CLASSES = frozenset(_INDEPENDENT_CLASSES)


def _detect_neutral_signals(text: str, company: str = "") -> list:
    """Signals this document evidences ABOUT THIS COMPANY.

    Was `_any_phrase(text, phrases)` — does the phrase appear anywhere in the
    document — which infers ownership from proximity and nothing else.
    Measured live at `037f805`: Microsoft was told it "serves two clearly
    different buyer groups" on the strength of "Our competitors are ...
    deploying competing cloud-based services for consumers and businesses".
    The phrase is there; the buyers are the competitors'.

    A signal now needs at least one occurrence that is not demonstrably
    somebody else's. See `owned_match` for why the test rejects foreign
    subjects rather than requiring explicit ownership.
    """
    return [sig for sig, phrases in _NEUTRAL_SIGNAL_KEYWORDS.items()
            if owned_match(text or "", phrases, company) is not None]


def _detect_signals(text: str, source_class: str = "company_owned",
                    company: str = "") -> list:
    """Domain signals when the document is in that domain, plus the neutral
    set always. A company outside every domain library still has a strategy."""
    text = text or ""
    signals = list(_detect_neutral_signals(text, company))
    # FILINGS ARE THEIR OWN DOMAIN. The commerce library never matches a
    # 10-K from a company that does not sell commerce software, so a filing
    # contributed nothing even after section extraction found its prose.
    # Source-specific detection, same canonical observation -- NOT a wider
    # global vocabulary, and NOT an admission bypass: every filing rule needs
    # a stated mechanism, so descriptive prose still fails closed.
    if FD_looks_like_filing(text):
        signals += [s_ for s_ in FD.detect(text) if s_ not in signals]
    if in_commerce_domain(text):
        signals += [sig for sig, phrases in _SIGNAL_KEYWORDS.items()
                    if owned_match(text, phrases, company) is not None]
        if source_class in _OUTSIDE_VANTAGE_CLASSES:
            signals += [sig for sig, phrases in _OUTSIDE_ONLY_PHRASES.items()
                        if sig not in signals
                        and owned_match(text, phrases, company) is not None]
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


#: The classes in which a document SPEAKS FOR the subject. Derived from the
#: vocabulary rather than hand-written, so a class added tomorrow belongs to
#: neither set until somebody decides — the same reason the pattern library's
#: applicability had to stop being a denylist.
def _subject_speaking_classes():
    from intent_engine.company_ingestion.records import (
        INDEPENDENT_CLASSES, SOURCE_CLASSES,
    )
    return tuple(c for c in SOURCE_CLASSES if c not in INDEPENDENT_CLASSES)


def _document_url(doc) -> str:
    get = (doc.get if isinstance(doc, dict)
           else lambda k, d=None, o=doc: getattr(o, k, d))
    return str(get("final_url", "") or get("url", "") or "")


def subject_documents(documents, *, subject_cik: str = "") -> list:
    """The documents that may describe THIS company. One owner for the rule.

    MEASURED LIVE on 0420fb0. JPMorgan's rendered page carried, under "How
    the business actually works -> Distribution model", the sentence "Is
    committing capital to capacity ahead of the demand for it" — attributed
    to WELLS FARGO & COMPANY's 10-K. A signal detected in another bank's
    filing became JPMorgan's own distribution model. The same run's evidence
    also carried a blank-check SPAC whose 10-K opens "We are a blank check
    company". Walmart's carried Ranpak, Ibotta and a 2023 BitNile filing.

    A claim belongs to whoever made it. `strategic_read._named_rivals`
    already carried this rule — it was repaired when Meta's introduction
    named AT&T and Alphabet, which were the AUTHORS of third-party filings
    the run had retrieved. The competitor producer was fixed and the
    OBSERVATION producer, one level upstream and feeding the same report,
    was not. One defect, two producers, one fixed.

    Two rules, because one is not enough:

      * a document in an INDEPENDENT class is another party's vantage by
        definition, and must not describe the subject's own mechanics;
      * a document filed under a DIFFERENT registrant's EDGAR path is not
        this filer's, whatever class it was given — which is the rule that
        catches a third-party 10-K classed as investor material.

    This belongs to the producer, not to each call site, because a function
    that builds a company's own mechanics should not silently accept
    documents about other companies.
    """
    allowed = _subject_speaking_classes()
    subject = (subject_cik or "").lstrip("0")
    kept = []
    for doc in documents or ():
        get = (doc.get if isinstance(doc, dict)
               else lambda k, d=None, o=doc: getattr(o, k, d))
        source_class = str(get("source_class", "") or "")
        if source_class and source_class not in allowed:
            continue
        url = str(get("final_url", "") or get("url", "") or "")
        if subject and "/data/" in url and f"/data/{subject}/" not in url:
            continue
        kept.append(doc)
    return kept


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

        # ONE excerpt rule, shared with `derive_observations` below. Two
        # derivations reading the same document must not disagree about what
        # it says; they differ in what they admit, not in what they read.
        body = ET.body_text(doc)
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
        excerpt = ET.evidence_excerpt(doc)
        if len(excerpt) < MIN_ANALYST_EXCERPT_CHARS:
            continue

        source_class = doc.get("source_class") or _SOURCE_CLASS.get(
            doc.get("source_type"), "company_owned")
        text = " ".join(filter(None, [
            title, doc.get("meta_description", ""), body]))
        signals = _detect_signals(text, source_class, company)
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
            excerpt=excerpt[:ET.EXCERPT_CHARS],
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


def derive_observations(documents, *, company: str = "",
                        subject_cik: str = "",
                        subject_only: bool = False) -> list:
    """Build StrategicObservations from retrieved ingestion documents.

    OWNERSHIP IS ENFORCED WHERE THE CLAIM IS MADE, NOT HERE. Filtering
    third-party documents out at this point was tried and is wrong: a
    COMPLETE report requires at least one INDEPENDENT source class, that
    coverage is computed from these observations, and dropping them made
    every run fail the cross-source bar to fix a claim nobody had made yet.
    A rival's filing is real evidence; it simply may not describe the
    SUBJECT'S OWN mechanics. `model.build_mental_model` applies
    `subject_documents`' rule to the observations that STATE a component,
    while leaving those that CONTRADICT one alone.

    `subject_only=True` is available for a caller that wants the documents
    narrowed here instead.

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
    if subject_only:
        documents = subject_documents(documents, subject_cik=subject_cik)
    # WHOSE DOCUMENT IS THIS, decided at the only layer that still has the
    # URL. `build_mental_model` sees observations and never a URL, and
    # `source_class` cannot answer it -- see `records.subject_owned`.
    owned_urls = {_document_url(d)
                  for d in subject_documents(documents,
                                             subject_cik=subject_cik)}
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
        signals = _detect_signals(text, source_class, company)
        if not signals:
            continue
        otype = _TYPE_FOR_SIGNAL.get(signals[0], "messaging")
        # A FILING IS NOT READ FROM ITS FIRST 280 CHARACTERS. For a web page
        # that is the summary; for a 10-K it is the cover page -- form title,
        # filing-status checkboxes, state of incorporation, IRS number. That
        # is why a run which retrieved Datadog's annual report produced no
        # filing-derived observation, and why "What was verified" fell back to
        # blog marketing once the cover page was filtered out.
        #
        # Section-aware selection is tried FIRST and falls back silently, so a
        # malformed or unrecognised filing keeps the old behaviour rather than
        # losing its observation.
        body_text = doc.get("text_content", "") or ""
        excerpt, section = "", ""
        is_filing = FS.looks_like_filing(body_text, doc.get("final_url", ""))
        # A FILING BY SOMEONE ELSE IS READ FOR WHAT IT SAYS ABOUT US.
        #
        # `third_party_filings` retrieves filings by other registrants that
        # name the subject, which is the only independent vantage most runs
        # get. Selecting the excerpt the same way as for the subject's own
        # filing gives the FILER's description of ITSELF: measured live on
        # Stripe, "Infinite Group is a developer of cybersecurity software"
        # was presented as evidence about Stripe.
        #
        # Fails closed. A third-party filing whose usable prose never names
        # the subject is not evidence about the subject, and the document is
        # dropped rather than shown with someone else's business description.
        if is_filing and doc.get("source_class") == "competitor":
            excerpt = FS.subject_span(body_text, company)
            if not excerpt:
                continue
            section = "the passage naming this company"
        elif is_filing:
            # The form decides which Item carries MD&A: 7 in an annual report,
            # 2 in a quarterly one. The parser already established it, so this
            # never has to be guessed from the text.
            excerpt, section = FS.best_excerpt(
                body_text, form=(doc.get("filing") or {}).get("form", ""))
        if not excerpt:
            # THE MEASURED DEFECT this replaced read
            #     (meta_description or text_content[:280])
            # and it was production for every observation the engine made. A
            # marketing page's meta_description IS its blurb; a filing's first
            # 280 characters ARE its cover page. `evidence_excerpt` is the one
            # body selector both derivations share.
            excerpt = ET.evidence_excerpt(doc)
        else:
            excerpt = excerpt.strip()
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
            # Resolved against the SAME text detection ran on, so a span is
            # the actual sentence that produced the signal rather than a
            # second, looser search. `text` is the detection input; for a
            # filing that is the extracted body, which is where the phrase
            # was found.
            signal_spans=signal_spans(text, signals, company),
            source_title=title or source_class,
            origin=doc.get("final_url", ""),
            date=(doc.get("retrieved_at", "") or "")[:10],
            strategic_signal=_SIGNAL_LABEL.get(dominant, ""),
            relevance=_SIGNAL_RELEVANCE.get(dominant, "adds context to the "
                                            "strategic picture"),
            entity=entity,
            weak=weak,
            subject_owned=_document_url(doc) in owned_urls,
            evidence_quality="weak" if weak else "strong"))
    return observations

# The neutral signals participate in exactly the same maps as the domain ones,
# so nothing downstream needs to know there are two libraries.
_SIGNAL_KEYWORDS.update(_NEUTRAL_SIGNAL_KEYWORDS)
_SIGNAL_LABEL.update(_NEUTRAL_LABEL)
# Filing propositions carry their own label and observation type, so the
# taxonomy stays the single source of truth for both.
_SIGNAL_LABEL.update({k: v["label"] for k, v in FD.PROPOSITIONS.items()})
_TYPE_FOR_SIGNAL.update({k: v["type"] for k, v in FD.PROPOSITIONS.items()})
# A signal with no stated consequence produces a bullet that restates itself
# and stops, so the taxonomy carries the consequence too.
_SIGNAL_RELEVANCE.update({k: v["relevance"] for k, v in FD.PROPOSITIONS.items()})
_TYPE_FOR_SIGNAL.update({
    "multi_product": "product_surface",
    "consolidation": "product_surface",
    "agent_executes_actions": "product_surface",
    "human_intervention_reduced": "product_surface",
    "agent_callable_endpoint": "infrastructure_platform",
    "human_in_the_loop": "product_surface",
    "cross_product_coupling": "product_surface",
    "independently_operated": "product_surface",
    "third_party_builds_on": "infrastructure_platform",
    "external_operations_depend": "infrastructure_platform",
    "system_of_record_claim": "product_surface",
    "shared_data_model": "infrastructure_platform",
    "replaces_incumbent_systems": "product_surface",
    "developer_surface": "infrastructure_platform",
    "segment_split": "buyer_segment",
    "regulated_buyer": "buyer_segment",
    "gov_dedicated_delivery": "buyer_segment",
    "accreditation_gate": "buyer_segment",
    "public_procurement_vehicle": "buyer_segment",
    "disclosed_public_sector_exposure": "buyer_segment",
    "named_customers": "monetization_ecosystem",
    "services_motion": "messaging",
    "productization": "messaging",
    "pricing_published": "messaging",
    "pricing_gated": "buyer_segment",
})

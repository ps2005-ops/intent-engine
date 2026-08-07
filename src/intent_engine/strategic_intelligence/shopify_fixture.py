"""V1.2 curated Shopify strategic validation fixture.

A deterministic, sourced set of structured observations spanning multiple
source classes (company-owned, executive, investor, independent, customer,
competitor). Every entry is a faithful paraphrase of well-known public facts
about Shopify's positioning — no verbatim source text, no private/internal
claims, no hard-coded conclusions. It feeds the SAME reasoning and rendering
pipeline a real run uses; the engine must reach or reject hypotheses from this
evidence, not from prose written here.

This is the "bounded, explicit source-addition step + curated validation
fixture" contemplated for the V1.2 slice while live external discovery is not
yet production-ready.
"""
from __future__ import annotations

from intent_engine.strategic_intelligence.records import StrategicObservation

SHOPIFY_COMPANY = "Shopify"


def _o(oid, text, otype, sclass, signals, *, excerpt, title, origin,
       date="", directly_observed=True, confidence="moderate",
       freshness="CURRENT"):
    refs = [{"subsystem": "company_ingestion", "artifact_type": "approved_source",
             "artifact_id": f"src-{oid}", "replay_id": f"replay-{oid}",
             "source_class": sclass}]
    return StrategicObservation(
        observation_id=oid, text=text, observation_type=otype,
        source_refs=refs, confidence=confidence, freshness=freshness,
        directly_observed=directly_observed, signals=tuple(signals),
        source_class=sclass, excerpt=excerpt, source_title=title,
        origin=origin, date=date)


def shopify_observations() -> list:
    """The full multi-source-class fixture."""
    return [
        _o("infra-positioning",
           "Shopify frames itself as the infrastructure that powers commerce, "
           "not only a store builder.",
           "messaging", "company_owned",
           ("infrastructure_positioning", "merchant_outcome_positioning"),
           excerpt="Public positioning describes Shopify as powering commerce "
                   "everywhere merchants sell, framed as underlying "
                   "infrastructure rather than a single storefront tool.",
           title="Shopify — company positioning", origin="https://www.shopify.com/",
           date="2024-06-01"),
        _o("checkout-rails",
           "Shop Pay and a unified checkout/identity are pushed as first-party "
           "rails across every surface a merchant sells on.",
           "infrastructure_platform", "company_owned",
           ("checkout_identity_rails", "platform_control", "data_network"),
           excerpt="Shop Pay is presented as an accelerated checkout and buyer "
                   "identity that Shopify owns and extends across online, "
                   "in-person, and third-party surfaces.",
           title="Shopify — Shop Pay / checkout", origin="https://www.shopify.com/shop-pay",
           date="2024-05-01"),
        _o("product-breadth",
           "The product surface now spans payments, capital, fulfillment, "
           "point of sale, cross-border, and audience/marketing tools.",
           "product_surface", "company_owned",
           ("product_breadth",),
           excerpt="Shopify's own product listing covers Payments, Capital, "
                   "Fulfillment, POS, Markets, and Audiences alongside the "
                   "core storefront.",
           title="Shopify — products", origin="https://www.shopify.com/",
           date="2024-04-01"),
        _o("exec-infra",
           "Executive commentary emphasizes owning the commercial rails and "
           "being the infrastructure beneath many merchants.",
           "messaging", "executive_statement",
           ("infrastructure_positioning", "checkout_identity_rails"),
           excerpt="Leadership has publicly framed the mission as building the "
                   "essential internet infrastructure for commerce and "
                   "reducing the work of running a business.",
           title="Shopify leadership remarks", origin="https://news.shopify.com/",
           date="2024-10-01"),
        _o("investor-enterprise",
           "Shareholder materials highlight enterprise (Shopify Plus) momentum "
           "and larger-merchant adoption.",
           "buyer_segment", "investor_material",
           ("enterprise_expansion", "product_breadth"),
           excerpt="Investor updates emphasize growth among larger merchants "
                   "and enterprise brands adopting the platform and its "
                   "additional products.",
           title="Shopify shareholder materials", origin="https://investors.shopify.com/",
           date="2024-08-01"),
        _o("agentic-company",
           "Shopify describes enabling agentic/AI-driven storefronts and "
           "AI-mediated buying experiences.",
           "channel_distribution", "company_owned",
           ("agentic_commerce", "distribution_shift"),
           excerpt="Shopify has announced tooling for AI/agent-driven shopping "
                   "and machine-readable commerce endpoints so buying can be "
                   "mediated by assistants, not only human browsing.",
           title="Shopify — AI commerce", origin="https://www.shopify.com/",
           date="2025-01-15"),
        _o("independent-agentic",
           "Independent reporting describes retail moving toward AI shopping "
           "agents that transact on buyers' behalf.",
           "market_context", "independent_reporting",
           ("agentic_commerce", "distribution_shift"),
           excerpt="Business/technology reporting frames AI shopping agents as "
                   "an emerging distribution layer that could intermediate "
                   "human browsing across retailers.",
           title="Independent reporting — AI commerce", origin="https://www.example-press.com/ai-commerce",
           date="2025-02-01"),
        _o("independent-control",
           "Analysts note Shopify consolidating checkout, identity, and "
           "merchant/consumer data as strategic control points.",
           "infrastructure_platform", "independent_reporting",
           ("platform_control", "checkout_identity_rails", "data_network"),
           excerpt="Independent analysis observes that Shopify's durable "
                   "advantage increasingly rests on owning checkout, buyer "
                   "identity, and data rather than storefront creation alone.",
           title="Independent analysis — Shopify strategy", origin="https://www.example-press.com/shopify",
           date="2024-11-01"),
        _o("partner-ecosystem",
           "The App Store and partner ecosystem are central to how merchants "
           "extend the platform.",
           "monetization_ecosystem", "company_owned",
           # `third_party_builds_on` added because this observation's own text
           # already carries it — "merchants extend the platform". Signals
           # here are hand-attached rather than detected, so the coarse
           # `partner_ecosystem_enablement` was the only one listed, and
           # `product_to_platform` now needs the mechanism rather than the
           # existence of a marketplace. Having an app store is a thing a
           # company HAS; outsiders extending the platform is the transition.
           ("partner_ecosystem_enablement", "third_party_builds_on"),
           excerpt="Shopify promotes an app marketplace and partner program as "
                   "the way merchants add capabilities, positioning partners "
                   "as core to extensibility.",
           title="Shopify — App Store / partners", origin="https://apps.shopify.com/",
           date="2024-03-01"),
        _o("data-network",
           "The Shop app and Audiences leverage cross-merchant consumer data "
           "and a Shopify-owned distribution surface.",
           "monetization_ecosystem", "company_owned",
           ("data_network", "distribution_shift"),
           excerpt="The Shop app and Audiences use aggregated buyer data and a "
                   "first-party consumer surface to drive discovery and "
                   "distribution across merchants.",
           title="Shopify — Shop app / Audiences", origin="https://www.shopify.com/",
           date="2024-07-01"),
        # --- counter-evidence: the SMB-simplicity / storefront identity ------
        _o("smb-simplicity",
           "The core promise remains letting anyone start and run a business "
           "simply, without technical complexity.",
           "messaging", "company_owned",
           ("smb_simplicity", "storefront_creation", "merchant_outcome_positioning"),
           excerpt="Shopify's top-level marketing still centers on making it "
                   "easy for small merchants to start, run, and grow a "
                   "business with minimal setup.",
           title="Shopify — start a business", origin="https://www.shopify.com/",
           date="2024-06-01"),
        _o("storefront-origin",
           "Storefront creation remains a large part of the brand and the "
           "entry product for most merchants.",
           "product_surface", "company_owned",
           ("storefront_creation",),
           excerpt="For most merchants the storefront builder is still the "
                   "entry point and a central part of Shopify's identity.",
           title="Shopify — online store", origin="https://www.shopify.com/online",
           date="2024-02-01"),
        _o("customer-simplicity",
           "Merchant reviews repeatedly value ease of setup and day-to-day "
           "simplicity.",
           "buyer_segment", "customer_voice",
           ("smb_simplicity",),
           excerpt="Public merchant reviews frequently cite quick setup and "
                   "simplicity as the main reason they chose and stay on "
                   "Shopify.",
           title="Public merchant reviews", origin="https://www.example-reviews.com/shopify",
           date="2024-09-01"),
        _o("competitor-enterprise",
           "Competing commerce platforms are pushing hard into enterprise, "
           "pressuring Shopify upmarket.",
           "market_context", "competitor",
           ("enterprise_expansion",),
           excerpt="Competitor public materials emphasize enterprise-grade "
                   "commerce, creating competitive pressure on Shopify to "
                   "serve larger merchants.",
           title="Competitor positioning", origin="https://www.example-competitor.com/enterprise",
           date="2024-10-01"),
    ]


def company_owned_only(observations=None) -> list:
    """The one-sided subset — used to prove the partial-scope quality state."""
    obs = observations if observations is not None else shopify_observations()
    return [o for o in obs if o.source_class == "company_owned"]

"""Deterministic company fixtures spanning real evidence environments.

The existing golden fixtures are all information-rich public companies, which
is why the product's behaviour on a five-person SaaS company or a local
business was never measured. These add those environments deliberately, and
each one models how that KIND of company actually publishes:

  * a public company has filings and investor pages and says little about
    customers;
  * a private startup has docs, a changelog and a pricing page, and no
    filings at all — expecting SEC evidence from it is a product bug;
  * a local business has a services page, hours and a phone number, and
    almost nothing a strategic analysis can chew on. Refusing responsibly is
    the correct outcome, not a failure.

Nothing here reaches the network.
"""
from __future__ import annotations

import email
import urllib.error
from dataclasses import dataclass, field


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "err",
                                  email.message_from_string(""), None)


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    website: str
    company_type: str                 # public | private | local
    pages: dict = field(default_factory=dict)   # path fragment -> body html
    blocked: tuple = ()                # fragments that answer 403
    missing: tuple = ()                # fragments that answer 404
    serves_sitemap: bool = True


def _page(title, paragraphs):
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (f"<html><head><title>{title}</title>"
            f'<meta name="description" content="{paragraphs[0][:150]}">'
            f"</head><body><main><h1>{title}</h1>{body}</main></body></html>")


# --- public, information-rich -------------------------------------------------
SHOPIFY = Site(
    "shopify", "Shopify", "https://shopify.example", "public",
    pages={
        "/": _page("Shopify — commerce infrastructure", [
            "Shopify is commerce infrastructure powering commerce for "
            "merchants of every size, from a first online store to global "
            "enterprise retail.",
            "Shop Pay checkout and buyer identity, payments, capital, "
            "fulfillment, point of sale and an app marketplace sit behind "
            "every merchant storefront.",
        ]),
        "/about": _page("About Shopify", [
            "Our mission is to make commerce better for everyone. More than "
            "two million merchants sell online and in person on our commerce "
            "platform across 175 countries.",
            "We build the commerce rails — payments, checkout, fulfillment "
            "network and point of sale — so merchants can focus on their "
            "products rather than their infrastructure.",
        ]),
        "/products": _page("Shopify products", [
            "One platform for online store, point of sale, shipping, "
            "merchant capital and marketing. Everything you need to sell "
            "across sales channels.",
            "Shopify Plus serves enterprise merchants moving upmarket with "
            "commerce components and dedicated support.",
        ]),
        "/customers": _page("Customer stories", [
            "Independent merchant reviews repeatedly praise fast setup and "
            "simple day-to-day operation, citing that simplicity as the top "
            "reason they choose Shopify over heavier enterprise platforms.",
            "Large merchants including national retail brands cite the "
            "checkout conversion rate as the reason they migrated.",
        ]),
        "/news": _page("Shopify newsroom", [
            "Leadership: we are building the essential infrastructure for "
            "commerce, owning checkout and buyer identity so merchants can "
            "focus on their business. Payment rails are first-party.",
            "We are investing in AI agent commerce so shoppers can buy "
            "through an agentic shopping assistant rather than by browsing.",
        ]),
        "/investors": _page("Shopify investor relations", [
            "Investor update: enterprise merchants momentum with Shopify Plus "
            "and large merchants; expanding product breadth across payments, "
            "merchant capital, fulfillment network and point of sale drives "
            "commerce platform adoption.",
        ]),
        "/pricing": _page("Shopify pricing", [
            "Plans start at a low monthly price for small business owners. "
            "Enterprise tier pricing is quoted for large merchants.",
        ]),
        "/careers": _page("Careers at Shopify", [
            "We are hiring across payments, fulfillment network and "
            "merchant-facing product teams.",
        ]),
    },
)

PALANTIR = Site(
    "palantir", "Palantir Technologies", "https://palantir.example", "public",
    pages={
        "/": _page("Palantir", [
            "Palantir builds software that lets organisations integrate their "
            "data, decisions and operations. We serve government and "
            "commercial institutions.",
        ]),
        "/about": _page("About Palantir", [
            "Palantir Technologies builds three platforms: Foundry for the "
            "commercial enterprise, Gotham for defence and intelligence, and "
            "AIP for deploying AI against private data.",
            "We embed alongside customers rather than selling seats.",
        ]),
        "/products": _page("Palantir platforms", [
            "Foundry is the ontology-powered operating system for the modern "
            "enterprise, integrating the semantic, kinetic and dynamic "
            "elements of a business.",
            "Gotham has surfaced insights from complex data for global "
            "defence agencies, the intelligence community and disaster relief "
            "organisations for over a decade.",
            "AIP connects large language models to enterprise data, logic and "
            "systems of action through the Palantir Ontology.",
        ]),
        "/customers": _page("Palantir impact", [
            "Named deployments include an aerospace manufacturer using "
            "Foundry across its supply chain, a utility reducing plant-wide "
            "power consumption, and hospitals coordinating capacity.",
        ]),
        "/news": _page("Palantir newsroom", [
            "Government revenue and commercial revenue are reported as "
            "separate segments. Leadership has said commercial adoption "
            "follows the AIP bootcamp motion.",
        ]),
        "/investors": _page("Palantir investor relations", [
            "Quarterly results separate United States government revenue from "
            "United States commercial revenue.",
        ]),
        "/careers": _page("Careers at Palantir", [
            "We hire forward deployed engineers who work on site with "
            "government and commercial customers.",
        ]),
    },
)

# --- public, blocked / thin ---------------------------------------------------
SONY = Site(
    "sony", "Sony Group Corporation", "https://sony.example", "public",
    pages={
        "/filings": _page("Form 6-K", [
            "Sony Group Corporation furnishes this report under the "
            "Securities Exchange Act. Consolidated results for the quarter "
            "reflect the Game and Network Services, Music, Pictures, Imaging "
            "and Sensing Solutions and Financial Services segments.",
        ]),
    },
    blocked=("/", "/about", "/products", "/customers", "/news", "/pricing",
             "/careers", "/investors", "/robots.txt", "/sitemap.xml"),
    serves_sitemap=False,
)

# --- private startups ---------------------------------------------------------
LINEAR = Site(
    "linear", "Linear", "https://linear.example", "private",
    pages={
        "/": _page("Linear — issue tracking for software teams", [
            "Linear is a purpose-built tool for planning and building "
            "software products. Teams track issues, plan cycles and manage "
            "product roadmaps in one workspace.",
        ]),
        "/about": _page("About Linear", [
            "Linear was founded to fix the sprawl of general-purpose project "
            "tools. The company is privately held and does not publish "
            "financial results.",
        ]),
        "/products": _page("Linear features", [
            "Cycles, projects, roadmaps, triage and a keyboard-first "
            "interface. Integrations with source control, design tools and "
            "customer support systems.",
        ]),
        "/docs": _page("Linear documentation", [
            "The API supports issues, projects, cycles and webhooks. The "
            "changelog records weekly releases across the last two years.",
        ]),
        "/customers": _page("Linear customers", [
            "Software teams at venture-backed startups and scale-ups use "
            "Linear for product planning. Public case studies describe "
            "reduced planning overhead.",
        ]),
        "/pricing": _page("Linear pricing", [
            "Free for small teams, a per-seat standard plan, and a business "
            "plan with advanced admin controls.",
        ]),
        "/careers": _page("Careers at Linear", [
            "We are hiring engineers and designers. The team is small and "
            "fully remote.",
        ]),
    },
    missing=("/investors",),
)

NOTION = Site(
    "notion", "Notion", "https://notion.example", "private",
    pages={
        "/": _page("Notion — the connected workspace", [
            "Notion combines notes, documents, databases and wikis in one "
            "connected workspace for teams and individuals.",
        ]),
        "/about": _page("About Notion", [
            "Notion is a privately held software company. We do not publish "
            "revenue or financial statements.",
        ]),
        "/products": _page("Notion product", [
            "Docs, wikis, projects and a database model that teams shape "
            "themselves. AI features summarise and draft inside the "
            "workspace.",
        ]),
        "/docs": _page("Notion help centre", [
            "Guides cover databases, permissions, templates and the public "
            "API.",
        ]),
        "/pricing": _page("Notion pricing", [
            "Free personal plan, per-seat plus and business plans, and an "
            "enterprise plan with audit controls.",
        ]),
        "/customers": _page("Notion customer stories", [
            "Teams describe replacing several separate tools with one "
            "workspace.",
        ]),
    },
    missing=("/investors", "/careers"),
)

# --- local business -----------------------------------------------------------
CORNER_CAFE = Site(
    "corner_cafe", "Corner Cafe", "https://cornercafe.example", "local",
    pages={
        "/": _page("Corner Cafe", [
            "Corner Cafe serves breakfast and lunch seven days a week on Elm "
            "Street. Coffee is roasted locally.",
        ]),
        "/about": _page("About Corner Cafe", [
            "A family-run cafe open since 2016.",
        ]),
    },
    missing=("/products", "/customers", "/news", "/investors", "/pricing",
             "/careers", "/docs"),
)

# --- pathological -------------------------------------------------------------
BLOCKED_CO = Site(
    "blocked_co", "Blocked Co", "https://blocked.example", "public",
    pages={},
    blocked=("/", "/about", "/products", "/customers", "/news", "/pricing",
             "/careers", "/investors", "/robots.txt", "/sitemap.xml", "/docs"),
    serves_sitemap=False,
)

GHOST_CO = Site(
    "ghost_co", "Ghost Co", "https://ghost.example", "private",
    pages={
        "/": ("<html><head><title>Ghost Co</title></head>"
              "<body><div id=root></div></body></html>"),
    },
    missing=("/about", "/products", "/customers", "/news", "/investors",
             "/pricing", "/careers", "/docs"),
)

SITES = {s.key: s for s in (SHOPIFY, PALANTIR, SONY, LINEAR, NOTION,
                            CORNER_CAFE, BLOCKED_CO, GHOST_CO)}


def site_transport(site: Site):
    """A transport that serves this fixture and nothing else."""
    def _tx(url, timeout):
        low = url.lower().split("#")[0].rstrip("/") or "/"
        path = low.split(site.website.lower().rstrip("/"), 1)[-1] or "/"
        if not path.startswith("/"):
            path = "/" + path
        for fragment in site.blocked:
            if path == fragment or path.startswith(fragment.rstrip("/") + "/"):
                raise _http_error(url, 403)
        if path in ("/robots.txt", "/sitemap.xml"):
            if not site.serves_sitemap:
                raise _http_error(url, 404)
            if path == "/robots.txt":
                body = b"User-agent: *\nAllow: /\n"
                return (200, {"content-type": "text/plain"}, body, False)
            locs = "".join(f"<url><loc>{site.website}{p}</loc></url>"
                           for p in site.pages if p != "/")
            body = (f'<?xml version="1.0"?><urlset>{locs}</urlset>').encode()
            return (200, {"content-type": "application/xml"}, body, False)
        for fragment in site.missing:
            if path == fragment:
                raise _http_error(url, 404)
        page = site.pages.get(path)
        if page is None:
            raise _http_error(url, 404)
        return (200, {"content-type": "text/html"}, page.encode(), False)
    return _tx

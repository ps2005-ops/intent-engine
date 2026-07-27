"""V1.1 bounded, deterministic source discovery — no crawling.

One homepage fetch yields same-domain links; known paths are proposed
without assuming they exist. Hard caps everywhere; transparent
deterministic ranking; never a model choosing URLs.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

from intent_engine.company_ingestion.records import (
    MAX_CANDIDATES_SHOWN, MAX_HOMEPAGE_LINKS, MAX_KNOWN_PATHS,
)
from intent_engine.company_ingestion.validation import same_domain

# Known-path probes, ordered by evidence family so a run reaches BEYOND the
# homepage even when the site is JavaScript-rendered and its links are not in
# the served HTML. Company-agnostic and bounded; every probe is still an
# approval-gated candidate that is only fetched if it actually exists.
KNOWN_PATHS = ("/",
               # identity. NOTE: "/leadership" is deliberately NOT probed here
               # — it classifies as an executive-statement source, so guessing
               # it can consume the strategy slot ahead of a newsroom page that
               # actually carries content. Leadership pages still arrive
               # through sitemap discovery when the company publishes one.
               "/about", "/about-us", "/company", "/team",
               # products & platform
               "/product", "/products", "/platform", "/platforms",
               "/solutions", "/offerings", "/services",
               # documentation / technical
               "/docs", "/documentation", "/developers", "/api",
               # customers & use cases. Large consumer companies publish these
               # under a segment path (/business, /enterprise, /education)
               # rather than /customers, and often omit them from the sitemap.
               "/customers", "/case-studies", "/success-stories", "/partners",
               "/business", "/business/success-stories", "/enterprise",
               "/education", "/customer-stories",
               # commercial
               "/pricing", "/plans",
               # strategy & communications
               "/blog", "/news", "/press", "/newsroom", "/media",
               # investor
               "/investors", "/investor-relations", "/ir",
               # talent
               "/careers", "/jobs", "/engineering")

# Map a same-domain path to its strategic source class. A company publishes
# more than one vantage point: press/newsroom/leadership speak for executives;
# investor-relations pages are investor material; customer stories are the
# customer voice. Everything else is a plain company-owned page. This is a
# generic, company-agnostic classification — no company-specific rules.
# NOTE: independent classes (customer_voice, competitor, independent_reporting)
# deliberately come only from OFF-domain sources — a company's own case-study or
# customer page is company-published marketing, not an independent vantage point.
_CLASS_RULES = (
    ("investor_material", ("investor", "shareholder", "/ir", "earnings",
                           "annual-report", "financ")),
    ("executive_statement", ("press", "newsroom", "news", "media",
                             "leadership", "keynote", "letter")),
)

_TYPE_RULES = (
    ("pricing", ("pricing", "plans")),
    ("product", ("product", "solution", "features", "platform", "offering",
                 "how-it-works", "docs", "documentation", "developer", "api",
                 "services")),
    ("about", ("about", "company", "team", "mission", "leadership")),
    ("customers", ("customer", "case-stud", "case_stud", "testimonial",
                   "success", "stories", "partner")),
    ("blog", ("blog", "news", "press", "newsroom", "articles", "updates")),
    ("careers", ("career", "jobs", "join", "hiring")),
)

_RANK = ("homepage", "product", "pricing", "about", "customers", "blog",
         "careers")

_SKIP_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip",
                    ".mp4", ".webp", ".ico", ".css", ".js", ".xml", ".webm")


def classify_path(path: str) -> str:
    lowered = (path or "/").lower()
    if lowered in ("", "/"):
        return "homepage"
    for source_type, needles in _TYPE_RULES:
        if any(n in lowered for n in needles):
            return source_type
    return "product" if len(lowered.strip("/").split("/")) == 1 else "blog"


def classify_source_class(path: str) -> str:
    """Strategic source class for a same-domain path (company-agnostic)."""
    lowered = (path or "/").lower()
    for source_class, needles in _CLASS_RULES:
        if any(n in lowered for n in needles):
            return source_class
    return "company_owned"


def why_relevant(source_class: str, source_type: str) -> str:
    return {
        "investor_material": "investor-facing framing of strategy, growth, and "
                             "risks in the company's own words",
        "executive_statement": "how leadership publicly frames direction and "
                               "priorities",
        "customer_voice": "how customers describe value and outcomes, a check "
                          "on the company's own claims",
    }.get(source_class,
          f"company-owned {source_type} page — primary positioning evidence")


def why_useful(source_type: str) -> str:
    return {
        "homepage": "primary positioning and value proposition",
        "product": "what the company sells and how it describes it",
        "pricing": "visible pricing model and packaging",
        "about": "company identity, mission, and history",
        "customers": "customer language and proof points",
        "blog": "publication activity and market language",
        "careers": "hiring signals and internal language",
    }.get(source_type, "supporting public context")


def discover_candidates(*, company_url: str, homepage_links: list) -> list:
    """Deterministic bounded candidate list from homepage links + known
    paths. Returns [{url, source_type, discovery_method, same_domain,
    why_useful}]; capped at MAX_CANDIDATES_SHOWN; homepage first."""
    parsed = urlparse(company_url)
    base = f"{parsed.scheme}://{parsed.hostname}"
    seen: set = set()
    candidates: list = []

    def add(url, method):
        url = url.split("#")[0].rstrip()
        if not url or url in seen or len(candidates) >= 200:
            return
        if any(urlparse(url).path.lower().endswith(e)
               for e in _SKIP_EXTENSIONS):
            return
        if not same_domain(company_url, url):
            return                       # external URLs need explicit approval
        seen.add(url)
        path = urlparse(url).path
        source_type = classify_path(path)
        source_class = classify_source_class(path)
        candidates.append({
            "url": url, "source_type": source_type,
            "discovery_method": method, "same_domain": True,
            "source_class": source_class,
            "why_useful": why_useful(source_type),
            "why_relevant": why_relevant(source_class, source_type)})

    add(company_url, "entered")
    for link in homepage_links[:200]:
        if len([c for c in candidates
                if c["discovery_method"] == "homepage_link"]) \
                >= MAX_HOMEPAGE_LINKS:
            break
        absolute = urljoin(company_url, link)
        if absolute.startswith(("http://", "https://")):
            add(absolute, "homepage_link")
    known = 0
    for path in KNOWN_PATHS:
        if known >= MAX_KNOWN_PATHS:
            break
        before = len(candidates)
        add(f"{base}{path}" if path != "/" else company_url, "known_path")
        known += len(candidates) - before

    candidates.sort(key=lambda c: (_RANK.index(c["source_type"])
                                   if c["source_type"] in _RANK else 99,
                                   c["url"]))
    return candidates[:MAX_CANDIDATES_SHOWN]

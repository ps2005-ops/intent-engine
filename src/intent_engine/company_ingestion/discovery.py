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

KNOWN_PATHS = ("/", "/product", "/products", "/solutions", "/pricing",
               "/about", "/customers", "/case-studies", "/blog", "/news",
               "/careers")

_TYPE_RULES = (
    ("pricing", ("pricing", "plans")),
    ("product", ("product", "solution", "features", "platform", "how-it-works")),
    ("about", ("about", "company", "team", "mission")),
    ("customers", ("customer", "case-stud", "case_stud", "testimonial",
                   "success", "stories")),
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
        source_type = classify_path(urlparse(url).path)
        candidates.append({
            "url": url, "source_type": source_type,
            "discovery_method": method, "same_domain": True,
            "why_useful": why_useful(source_type)})

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

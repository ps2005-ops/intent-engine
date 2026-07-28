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


# Language/region prefixes and query locales that mark a page as a TRANSLATION
# of one already reachable in English, rather than as new evidence.
#
# Deliberately conservative: only two-letter codes in a leading path segment
# (optionally region-qualified, "de", "de-DE", "pt_BR"), and only when the
# segment is not a real word the site might use as a section. "in" is excluded
# because /in/ is far more often a product path than India.
_LOCALE_CODES = frozenset("""
af ar az be bg bn bs ca cs cy da de el es et eu fa fi fr ga gl he hi hr hu hy
id is it ja ka kk km kn ko lt lv mk ml mn mr ms my nb ne nl nn no pa pl pt ro
ru si sk sl sq sr sv sw ta te th tl tr uk ur uz vi zh
""".split())
#: never treat these as locales even though they look like codes
_NOT_LOCALES = frozenset({"in", "no", "it", "is", "be", "as", "at", "so",
                          "id", "my", "me", "us", "ai", "app", "api"})


def is_localised_path(path: str) -> bool:
    """True when the first path segment is a language/region code.

    Matches /de/..., /de-DE/..., /pt_BR/..., /zh-hans/... and the bare /de.
    Does not match /india/, /internal/, /design/ -- only exact codes.
    """
    segments = [seg for seg in (path or "").split("/") if seg]
    if not segments:
        return False
    first = segments[0].lower()
    root = first.replace("_", "-").split("-")[0]
    if root in _NOT_LOCALES:
        return False
    return root in _LOCALE_CODES and len(root) == 2


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
        if is_localised_path(urlparse(url).path):
            # Localised duplicates of pages that also exist in English.
            #
            # Figma returned "Not enough public evidence" after reading eight
            # real sources, because discovery had walked into its German blog
            # ("Tag: Fallstudie", "Tag: Produktupdates") and the readable-
            # language gate then voided the whole run. The English equivalents
            # of those same pages existed and were never fetched.
            #
            # Dropping them costs nothing: a localised page is a translation
            # of a page already reachable, not additional evidence.
            return
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
    if len(candidates) <= MAX_CANDIDATES_SHOWN:
        return candidates
    # The cap must not be filled by whichever source type happens to be most
    # numerous. A site with many product links would otherwise crowd out the
    # single customer-story or pricing page entirely — the candidate never
    # reaches approval, and the report reports that family as missing.
    # Take a round-robin across source types so every type keeps a place.
    buckets: dict = {}
    for candidate in candidates:
        buckets.setdefault(candidate["source_type"], []).append(candidate)
    ordered_types = sorted(buckets, key=lambda t: _RANK.index(t)
                           if t in _RANK else 99)
    balanced, depth = [], 0
    while len(balanced) < MAX_CANDIDATES_SHOWN:
        progressed = False
        for source_type in ordered_types:
            group = buckets[source_type]
            if depth < len(group) and len(balanced) < MAX_CANDIDATES_SHOWN:
                balanced.append(group[depth])
                progressed = True
        if not progressed:
            break
        depth += 1
    return balanced

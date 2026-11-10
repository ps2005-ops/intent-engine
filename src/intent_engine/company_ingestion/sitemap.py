"""Sitemap- and robots-based URL discovery.

Guessing known paths produces mostly 403/404 responses: the guessed URL either
does not exist on that site or is refused. A site's own ``sitemap.xml`` (and the
``Sitemap:`` directives in ``robots.txt``) is the publisher's OWN list of real,
canonical, publicly-crawlable URLs — the highest-precision discovery source
available without a search provider, and it works even when the homepage is
JavaScript-rendered and exposes no links in its served HTML.

Everything here is bounded, deterministic, stdlib-only, and fetched through the
same SSRF-guarded transport as every other retrieval. Nothing is fetched for
analysis: URLs found here become approval-gated candidates like any other.

robots.txt is honoured as policy: ``Disallow`` rules for our user-agent remove
URLs from consideration. This module never bypasses access controls.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

# Large sites nest sitemap INDEXES (index -> child sitemaps -> URLs), so the
# budget must cover the index hops AND enough children to actually reach URLs.
MAX_SITEMAP_FETCHES = 10         # total sitemap documents fetched per run
MAX_SITEMAP_CHILDREN = 8         # children queued from any one index
MAX_SITEMAP_URLS = 400           # URLs parsed out of the sitemap set
MAX_URLS_PER_FAMILY = 3          # keep the candidate list reviewable

# Ordered, company-agnostic patterns mapping a URL path to an evidence family.
# First match wins, so more specific families are listed first.
FAMILY_PATTERNS = (
    # NOTE: keep these needles specific. A loose needle such as "/financial"
    # captures product pages like "/offerings/financial-services/" and
    # mislabels marketing content as investor evidence.
    ("investor", ("/investor", "/investors", "/ir/", "/shareholder",
                  "/annual-report", "/quarterly-result", "/earnings",
                  "/financial-report", "/financial-results", "/sec-filing")),
    ("customers", ("/customer", "/case-stud", "/case_stud", "/success",
                   "/stories", "/testimonial", "/partners", "/partner/")),
    ("documentation", ("/docs", "/documentation", "/developer", "/developers",
                       "/api", "/reference", "/guides", "/learn")),
    ("product", ("/product", "/products", "/platform", "/platforms",
                 "/solutions", "/offerings", "/services", "/features")),
    ("newsroom", ("/news", "/newsroom", "/press", "/media", "/blog",
                  "/announcements", "/updates")),
    ("leadership", ("/leadership", "/team", "/executive", "/management",
                    "/board", "/about", "/company", "/who-we-are")),
    ("pricing", ("/pricing", "/plans", "/price")),
    ("careers", ("/careers", "/jobs", "/join-us", "/hiring", "/work-with-us")),
)

# Paths that are never useful executive evidence.
_NOISE = ("/legal", "/privacy", "/terms", "/cookie", "/sitemap", "/search",
          "/login", "/signin", "/account", "/cart", "/support/ticket",
          "/rss", "/feed.xml", "/wp-", "/tag/", "/category/", "/author/")


# ---------------------------------------------------------------------------
# LOCALE PARTITIONS: the same page, in languages this analysis cannot read.
# ---------------------------------------------------------------------------
# MEASURED locally on a cold NVIDIA run (docs/PRE100_MINIMUM_CORE_PREREGISTRATION.md):
# NINE of the fourteen CORE evidence slots went to non-English locale pages, and
# ONE page -- a Broadcast app setup guide -- took THREE of them in Czech, Danish
# and Austrian German. `readiness.is_english` then discarded four of them, so
# the run paid 2.4MB and four slots for evidence its own gate refuses.
#
# The cause is here, not in ranking. `parse_sitemap` returned the FIRST
# MAX_SITEMAP_CHILDREN children of the index in document order; NVIDIA lists its
# locale sitemaps alphabetically, so the walk queued cs-cz, da-dk, de-at, de-ch,
# de-de, en-gb and never reached en-us. The English pages were not out-ranked --
# they were never discovered.
#
# THE RULE IS ABOUT THE SITE, NOT THE COMPANY. A locale segment is recognised
# only in the unambiguous `xx-yy` LANGUAGE-REGION form, and only when the site
# exposes AT LEAST TWO DISTINCT ones -- because partitioning by locale is by
# definition plural, and a lone `/to-do/` slug matches the pattern by accident.
# Where a company publishes in one language only, nothing here changes what is
# discovered or in what order; the readable-language finding in `readiness`
# remains the thing that reports it.
_LOCALE_SEGMENT = re.compile(r"^([a-z]{2})-([a-z]{2})$")

#: Locales this analysis can actually read. `readiness.MIN_ENGLISH_SHARE` is
#: the gate that decides evidence is unreadable; this is the same fact applied
#: one step earlier, where it still costs nothing to act on.
_READABLE_LANGUAGES = ("en",)


def locale_of(url: str) -> str:
    """The `xx-yy` locale segment in a URL path, or "" if it carries none.

    Any segment may hold it: NVIDIA's child sitemaps are
    `/cs-cz/cs-cz.sitemap.xml`, and some publishers put the locale second.
    """
    for segment in (urlparse(url).path or "").lower().split("/"):
        if _LOCALE_SEGMENT.match(segment):
            return segment
    return ""


def _partitioned_by_locale(urls) -> bool:
    """True when these URLs are a locale partition rather than a coincidence."""
    return len({locale_of(u) for u in urls if locale_of(u)}) >= 2


def _readable_locale(url: str) -> bool:
    locale = locale_of(url)
    return not locale or locale.split("-")[0] in _READABLE_LANGUAGES


def prefer_readable_locales(urls, limit=None) -> list:
    """Reorder a locale-partitioned URL set so readable locales come first.

    Order-preserving within each group, so a site that is NOT locale-
    partitioned comes back exactly as it went in. Nothing is dropped here;
    `limit` is applied by the caller that owns the budget.
    """
    urls = list(urls)
    if not _partitioned_by_locale(urls):
        return urls[:limit] if limit else urls
    readable = [u for u in urls if _readable_locale(u)]
    other = [u for u in urls if not _readable_locale(u)]
    ordered = readable + other
    return ordered[:limit] if limit else ordered


def locale_free_path(url: str) -> str:
    """The URL path with its locale segment removed.

    `/cs-cz/products/rtx-spark/` and `/da-dk/products/rtx-spark/` are the same
    page, and a run that spends two of fourteen slots on it has bought one
    piece of evidence twice.
    """
    parts = [seg for seg in (urlparse(url).path or "").split("/")
             if not _LOCALE_SEGMENT.match(seg.lower())]
    return "/".join(parts) or "/"


def classify_family(url: str):
    """Return the evidence family for a URL path, or None if it is noise."""
    path = (urlparse(url).path or "/").lower()
    if any(marker in path for marker in _NOISE):
        return None
    for family, needles in FAMILY_PATTERNS:
        if any(needle in path for needle in needles):
            return family
    return None


def parse_robots(text: str, *, base_url: str) -> dict:
    """Extract {'sitemaps': [...], 'disallow': [...]} from robots.txt.

    Disallow rules are collected for the wildcard agent and for ours; they are
    treated as policy and applied to every discovered URL.
    """
    sitemaps, disallow = [], []
    agent_applies = False
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "sitemap" and value:
            sitemaps.append(urljoin(base_url, value))
        elif field == "user-agent":
            agent_applies = value == "*" or "founderintelligence" in value.lower()
        elif field == "disallow" and agent_applies and value:
            disallow.append(value)
    return {"sitemaps": sitemaps, "disallow": disallow}


def allowed_by_robots(url: str, disallow: list) -> bool:
    """Robots path matching with wildcard (*) and end-anchor ($) support.

    A naive ``rule.split('*')[0]`` prefix test is WRONG: a real-world rule such
    as ``/*/*?*shpxid=*`` reduces to the prefix ``/``, which then blocks every
    URL on the site. Translate the rule to a regex instead, matching robots
    semantics: ``*`` is any sequence, ``$`` anchors the end, and the rule is a
    prefix match otherwise.
    """
    path = urlparse(url).path or "/"
    for rule in disallow:
        if not rule:
            continue
        if rule == "/":
            return False
        anchored = rule.endswith("$")
        body = rule[:-1] if anchored else rule
        pattern = "".join(".*" if part == "*" else re.escape(part)
                          for part in re.split(r"(\*)", body))
        if re.match(pattern + ("$" if anchored else ""), path):
            return False
    return True


def parse_sitemap(xml: str) -> dict:
    """Return {'sitemaps': [...], 'urls': [...]} from a sitemap or index.

    Deliberately regex-based rather than an XML parser: sitemaps in the wild are
    frequently malformed, and this must never raise.
    """
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml or "", re.I)
    is_index = "<sitemapindex" in (xml or "").lower()
    if is_index:
        # WHICH children, not just how many. Truncating an alphabetical list
        # of locale sitemaps at eight is what stopped `en-us` from ever being
        # queued -- see `prefer_readable_locales`.
        return {"sitemaps": prefer_readable_locales(locs,
                                                    MAX_SITEMAP_CHILDREN),
                "urls": []}
    return {"sitemaps": [], "urls": locs[:MAX_SITEMAP_URLS]}


def discover_from_sitemap(company_url: str, *, fetcher) -> list:
    """Discover real, publisher-listed URLs grouped by evidence family.

    ``fetcher`` is a callable(url) -> {"ok": bool, "body": str} (the caller
    supplies one bound to the SSRF-guarded transport). Returns a bounded list of
    {url, family} dicts. Never raises: any failure yields fewer candidates.
    """
    parsed = urlparse(company_url)
    base = f"{parsed.scheme}://{parsed.hostname}"
    disallow: list = []
    sitemap_urls: list = []

    try:
        robots = fetcher(f"{base}/robots.txt")
        if robots.get("ok"):
            found = parse_robots(robots.get("body", ""), base_url=base)
            disallow = found["disallow"]
            sitemap_urls.extend(found["sitemaps"])
    except Exception:                                       # noqa: BLE001
        pass
    if not sitemap_urls:
        sitemap_urls = [f"{base}/sitemap.xml"]

    seen_sitemaps, urls, fetches = set(), [], 0
    queue = list(dict.fromkeys(sitemap_urls))
    while queue and fetches < MAX_SITEMAP_FETCHES and len(urls) < MAX_SITEMAP_URLS:
        target = queue.pop(0)
        if target in seen_sitemaps:
            continue
        seen_sitemaps.add(target)
        fetches += 1
        try:
            result = fetcher(target)
        except Exception:                                   # noqa: BLE001
            continue
        if not result.get("ok"):
            continue                     # e.g. a multi-megabyte child sitemap
        parsed_map = parse_sitemap(result.get("body", ""))
        # Children are appended, so index hops do not starve URL collection.
        for child in parsed_map["sitemaps"]:
            if child not in seen_sitemaps and child not in queue:
                queue.append(child)
        # Keep only URLs that belong to an evidence family. A big site's
        # sitemap is mostly long-tail marketing pages; retaining everything
        # would exhaust the URL budget before any useful path appeared.
        urls.extend(u for u in parsed_map["urls"] if classify_family(u))

    # Group by family, keeping the shortest (most canonical) URLs per family.
    by_family: dict = {}

    def _registrable(hostname: str) -> str:
        # NOTE: str.lstrip("www.") strips a CHARACTER SET, not the prefix, and
        # mangles hostnames — compare registrable domains instead.
        labels = (hostname or "").lower().rstrip(".").split(".")
        return ".".join(labels[-2:]) if len(labels) >= 2 else (hostname or "")

    host = _registrable(parsed.hostname or "")
    for url in dict.fromkeys(urls):
        if not url.startswith(("http://", "https://")):
            continue
        if _registrable(urlparse(url).hostname or "") != host:
            continue                     # same registrable site only
        if not allowed_by_robots(url, disallow):
            continue                     # robots policy is honoured
        family = classify_family(url)
        if family is None:
            continue
        by_family.setdefault(family, []).append(url)

    out = []
    for family, _patterns in FAMILY_PATTERNS:
        group = list(dict.fromkeys(by_family.get(family, [])))
        partitioned = _partitioned_by_locale(group)
        # Shortest path is the most canonical page in a family, and the tie
        # was broken lexicographically -- which prefers `cs-cz` to `en-us`
        # over two URLs of identical length. Readability breaks it first now,
        # and only on a site that is actually locale-partitioned.
        group.sort(key=lambda u: (
            0 if (not partitioned or _readable_locale(u)) else 1,
            len(urlparse(u).path), u))
        # ONE PAGE, ONE SLOT. The same article in three languages is one piece
        # of evidence bought three times; the family budget is the scarce
        # resource, so a path already represented does not take a second.
        seen_paths = set()
        for url in group:
            if len(seen_paths) >= MAX_URLS_PER_FAMILY:
                break
            key = locale_free_path(url) if partitioned else url
            if key in seen_paths:
                continue
            seen_paths.add(key)
            out.append({"url": url, "family": family})
    return out

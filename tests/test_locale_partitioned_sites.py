"""§9/§20: a locale-partitioned site must not spend CORE on languages this
analysis cannot read.

MEASURED (docs/PRE100_MINIMUM_CORE_PREREGISTRATION.md): nine of NVIDIA's
fourteen CORE evidence slots went to non-English locale pages, one page took
three of them in three languages, and `readiness.is_english` then discarded
four of those documents. The run paid for evidence its own gate refuses.
"""
from __future__ import annotations

from intent_engine.company_ingestion.sitemap import (
    MAX_SITEMAP_CHILDREN, discover_from_sitemap, locale_free_path, locale_of,
    parse_sitemap, prefer_readable_locales,
)


def _index(urls):
    return ("<sitemapindex>" + "".join(f"<sitemap><loc>{u}</loc></sitemap>"
                                       for u in urls) + "</sitemapindex>")


def _urlset(urls):
    return ("<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls)
            + "</urlset>")


def test_an_index_of_locale_sitemaps_reaches_the_readable_one():
    """The English child must be queued even when it sorts last.

    NVIDIA's index lists locale sitemaps alphabetically. Truncating at
    MAX_SITEMAP_CHILDREN queued cs-cz .. en-gb and never reached en-us, so
    the English pages were not out-ranked — they were never discovered.
    """
    locales = ["cs-cz", "da-dk", "de-at", "de-ch", "de-de", "es-es", "fr-fr",
               "it-it", "ja-jp", "ko-kr", "en-us"]
    children = [f"https://x.example/{loc}/{loc}.sitemap.xml"
                for loc in locales]
    assert len(children) > MAX_SITEMAP_CHILDREN
    chosen = parse_sitemap(_index(children))["sitemaps"]
    assert any("en-us" in c for c in chosen), (
        "the only readable child sitemap was truncated away")


def test_a_site_that_is_not_locale_partitioned_is_untouched():
    """One accidental `xx-yy` slug must not trigger a locale rule."""
    children = ["https://x.example/to-do/a.xml", "https://x.example/b.xml",
                "https://x.example/c.xml"]
    assert parse_sitemap(_index(children))["sitemaps"] == children


def test_a_company_publishing_only_in_one_other_language_keeps_its_evidence():
    """No English pages exist, so nothing may be demoted out of existence."""
    children = [f"https://x.example/{loc}/s.xml"
                for loc in ("de-de", "de-at", "de-ch")]
    chosen = parse_sitemap(_index(children))["sitemaps"]
    assert set(chosen) == set(children)


def test_one_page_in_three_languages_takes_one_slot():
    """The family budget is the scarce resource, not the request."""
    pages = [f"https://x.example/{loc}/products/widget/"
             for loc in ("cs-cz", "da-dk", "de-at", "en-us")]

    def fetcher(url):
        if url.endswith("robots.txt"):
            return {"ok": True, "body": "Sitemap: https://x.example/s.xml"}
        return {"ok": True, "body": _urlset(pages)}

    found = discover_from_sitemap("https://x.example", fetcher=fetcher)
    widget = [f["url"] for f in found if "/products/widget/" in f["url"]]
    assert len(widget) == 1, f"one page took {len(widget)} slots: {widget}"
    assert "en-us" in widget[0], "the unreadable variant took the slot"


def test_locale_helpers_are_conservative():
    assert locale_of("https://x.example/cs-cz/about/") == "cs-cz"
    assert locale_of("https://x.example/about/") == ""
    assert locale_free_path("https://x.example/da-dk/products/x/") == \
        "/products/x/"
    # Not partitioned: fewer than two distinct locale segments, so the order
    # is returned untouched even though one segment matches the pattern.
    same = ["https://x.example/to-do/", "https://x.example/b/"]
    assert prefer_readable_locales(same) == same

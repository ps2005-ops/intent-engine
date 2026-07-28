"""Localised duplicates must not crowd out the English pages.

Figma returned "Not enough public evidence" after reading eight real sources:
discovery had walked into its German blog ("Tag: Fallstudie", "Tag:
Produktupdates") and the readable-language gate then voided the whole run,
while the English equivalents of those same pages were never fetched.
"""
import pytest

from intent_engine.company_ingestion.discovery import (
    discover_candidates, is_localised_path,
)


@pytest.mark.parametrize("path", [
    "/de/blog", "/de-DE/pricing", "/pt_BR/about", "/zh-hans/product",
    "/fr/", "/ja/newsroom", "/ko-KR/customers",
])
def test_language_prefixes_are_recognised(path):
    assert is_localised_path(path)


@pytest.mark.parametrize("path", [
    "/", "/pricing", "/blog", "/india/offices", "/internal", "/design",
    "/investors", "/api", "/in/enterprise", "/it-operations", "/about",
])
def test_ordinary_paths_are_not_mistaken_for_locales(path):
    assert not is_localised_path(path), path


def test_localised_pages_are_not_offered_as_candidates():
    links = ["https://x.test/blog", "https://x.test/de/blog",
             "https://x.test/pricing", "https://x.test/de-DE/pricing",
             "https://x.test/ja/blog"]
    urls = [c["url"] for c in discover_candidates(
        company_url="https://x.test", homepage_links=links)]
    assert "https://x.test/blog" in urls
    assert "https://x.test/pricing" in urls
    for dropped in ("https://x.test/de/blog", "https://x.test/de-DE/pricing",
                    "https://x.test/ja/blog"):
        assert dropped not in urls, dropped

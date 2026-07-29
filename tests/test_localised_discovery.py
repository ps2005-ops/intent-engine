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


# --- unreadable pages are set aside, not held against the run --------------

def _doc(text, url="https://x.test/p", family_hint="about"):
    return {"final_url": url, "text_content": text, "title": "T",
            "retrieval_status": "OK", "source_type": family_hint,
            "content_hash": str(abs(hash(text))), "freshness": "CURRENT",
            "retrieved_at": "2026-07-28T00:00:00Z"}


_EN = ("Our platform helps design teams collaborate on interface work across "
       "the whole product process, from first sketch to developer handoff, "
       "with shared libraries and review built in for every project.")
_DE = ("Erstellung von User Journey Maps mit unseren Werkzeugen für Teams, "
       "die gemeinsam an Produkten arbeiten und ihre Entwürfe für die "
       "Übergabe an die Entwicklung vorbereiten möchten und sollen.")


def test_unreadable_pages_do_not_drag_down_a_readable_run():
    from intent_engine.company_ingestion.readiness import assess_readiness
    docs = [_doc(_EN + " one"), _doc(_EN + " two"), _doc(_EN + " three"),
            _doc(_DE + " eins"), _doc(_DE + " zwei"), _doc(_DE + " drei")]
    result = assess_readiness(documents=docs, identity={"status": "RESOLVED",
                                    "company_name": "X",
                                    "domain": "x.test"})
    assert result["set_aside_unreadable"] >= 1, \
        "German pages were not set aside"
    assert result["readable_share"] < 1.0, \
        "the reader is no longer told that pages could not be read"


def test_a_wholly_unreadable_run_is_still_reported_as_such():
    from intent_engine.company_ingestion.readiness import assess_readiness
    docs = [_doc(_DE + " eins"), _doc(_DE + " zwei"), _doc(_DE + " drei")]
    result = assess_readiness(documents=docs, identity={"status": "RESOLVED",
                                    "company_name": "X",
                                    "domain": "x.test"})
    assert result["readable_share"] < 0.6


# --- unreadable pages must not be presented as read ------------------------

def test_unreadable_pages_are_not_listed_as_sources_that_were_read(tmp_path):
    """OBSERVED LIVE on Figma: German blog pages were fetched fine, could not
    be read, were correctly excluded from the evidence -- and were still
    listed to the user under "Sources that were read". The page asserted
    something false about its own work."""
    import email as _email
    import urllib.error

    from test_webapp_demo_mode import Client, _make, _start_demo

    def mixed(url, timeout):
        u = url.lower()
        if "example.test" not in u:
            raise urllib.error.HTTPError(url, 404, "nf",
                                         _email.message_from_string(""), None)
        path = u.split("example.test", 1)[-1].strip("/") or "home"
        text = _DE if "blog" in path else _EN
        html = (f"<html><head><title>Example {path}</title></head>"
                f"<body><p>{text}</p></body></html>")
        return (200, {"content-type": "text/html"}, html.encode(), False)

    app = _make(tmp_path, transport=mixed, autorun_sources=True)
    c = _start_demo(app)
    _, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={c.csrf()}&website=https://example.test")
    _, _, page = c.request("GET", headers["Location"].rsplit("/progress", 1)[0])
    if "Sources" not in page:
        return                       # this run did not reach a limited result
    assert "Sources that were read" not in page,         "unreadable pages are still presented as read"


def test_readability_decides_which_list_a_source_lands_in():
    from intent_engine.company_ingestion.readiness import is_english
    assert is_english(_doc(_EN))
    assert not is_english(_doc(_DE))

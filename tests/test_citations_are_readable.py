"""A citation names the page it cites, not an internal identifier.

MEASURED on the deployed preview 2026-08-03, the first grounded run after
ANTHROPIC_API_KEY was added (Palantir, commit 2b2e437). The executive brief
rendered:

    Sources behind this (8)
    obs-src-eb15293b7148
    obs-src-4856bb8a9f80
    obs-src-70d3827bdb21
    ...

Eight opaque strings where a reader expects the name of what was read. The
60-second brief did the same under "What this rests on (10)". The map from id
to readable title already existed and already served the evidence DETAIL page
-- `WebApp._citation_labels` -- so this was a list that never asked for it.

The rule is not "always show a title": it is "never show an internal id when a
real title exists, and never invent one when it does not".
"""
import re

from intent_engine.founder_brief.render import _citations

_INTERNAL_ID = re.compile(r"obs-src-[0-9a-f]{6,}|\bsrc-[0-9a-f]{6,}")


def _visible_text(html):
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


def test_a_citation_shows_the_source_name_not_the_id():
    html = _citations(["obs-src-eb15293b7148"], "run-1", "Evidence",
                      {"obs-src-eb15293b7148": "About Palantir"})
    text = _visible_text(html)
    assert "About Palantir" in text
    assert not _INTERNAL_ID.search(text), text


def test_the_link_still_resolves_through_the_real_evidence_route():
    """Renaming the label must not change where the citation points."""
    html = _citations(["obs-src-eb15293b7148"], "run-1", "Evidence",
                      {"obs-src-eb15293b7148": "About Palantir"})
    assert 'href="/runs/run-1/evidence/obs-src-eb15293b7148"' in html


def test_an_id_with_no_known_source_is_left_alone_not_invented():
    """A made-up document name is worse than an ugly one."""
    text = _visible_text(_citations(["obs-src-deadbeef1234"], "run-1",
                                    "Evidence", {}))
    assert "obs-src-deadbeef1234" in text


def test_every_labelled_citation_is_free_of_internal_ids():
    labels = {"obs-src-aaaaaa111111": "Palantir 2026 Q2 results",
              "obs-src-bbbbbb222222": "About Palantir",
              "obs-src-cccccc333333": "Investor relations"}
    text = _visible_text(_citations(list(labels), "run-1", "Sources", labels))
    assert not _INTERNAL_ID.search(text), text
    for title in labels.values():
        assert title in text


def test_the_founder_brief_page_passes_labels_through(tmp_path):
    """THE GATE. The renderer supporting labels is not the same as the page
    handing them over -- that gap is exactly what shipped."""
    import inspect

    from intent_engine.webapp.app import WebApp
    source = inspect.getsource(WebApp._founder_brief_page)
    assert "citation_labels=self._citation_labels(run_id)" in source, (
        "the 60-second brief renders citations without the label map")
    source = inspect.getsource(WebApp._executive_brief_page)
    assert "citation_labels=self._citation_labels(run_id)" in source, (
        "the executive brief renders citations without the label map")

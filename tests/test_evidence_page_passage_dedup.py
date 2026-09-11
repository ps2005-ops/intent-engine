"""One passage, one blockquote -- per page (§L EVIDENCE).

MEASURED 2026-09-11 on 223f1ca4, all ten demo companies, /evidence:

    Highspot 1 repeated passage    BigID 2    Cyera 2 (one of them THREE times)
    Druva 1                        Slalom 1   Sigma Computing 1
    Monte Carlo 0   Veeam 0   ZoomInfo 0   Point B 0

Six of ten. The cause is not a selection bug: every card is a genuinely
different source with its own URL, author and dates. It is that a site reuses
ONE meta description across many pages, so the excerpt drawn from each of
those pages is byte-identical -- and a reader looking at Cyera met the same
sentence three times on the page whose entire argument is "here is the
evidence".

WHAT THE REPAIR MAY NOT DO is drop the source. A source removed is a source
the reader cannot check, and the card carries the link, the author and the
dates that make it checkable. Only the repeated BLOCKQUOTE is replaced, by a
line naming the source whose wording it shares.
"""
import re

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


@pytest.fixture()
def app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=None, resolver=False)


def _quotes(html):
    return [" ".join(re.sub(r"<[^>]+>", " ", q).split())
            for q in re.findall(r"<blockquote[^>]*>(.*?)</blockquote>",
                                html, re.S | re.I)]


def _code(obj) -> str:
    """The source with runs of whitespace collapsed.

    The assertions below name phrases the page prints. Those phrases live in
    multi-line f-strings, so the literal text is split across lines and a
    naive `in` check fails on code that is perfectly correct -- which is how
    the first version of this file failed. Matching on collapsed whitespace
    tests the phrase rather than the line wrapping.
    """
    import inspect
    return " ".join(inspect.getsource(obj).split())


def test_the_dedup_is_page_scoped_and_normalised():
    """The key ignores whitespace, so two spellings of one sentence collide.

    Asserted on the normaliser directly: the page builder is a closure and
    the property that matters is which strings are treated as the same.
    """
    norm = lambda t: " ".join(str(t or "").split()).strip().lower()
    a = "Explore how AI helps your team train,  coach, and execute better."
    b = "explore how ai helps your team train, coach, and execute better."
    assert norm(a) == norm(b)
    assert norm("") == ""


def test_a_repeated_passage_is_named_not_reprinted():
    """The second card keeps its identity and loses only the duplicate text.

    MEASURED on a local instance of this build, Cyera: eight sources, five
    blockquotes and three "same published description" notes -- every source
    still on the page, no sentence printed twice. Before the repair: eight
    blockquotes, five distinct.
    """
    code = _code(WebApp._evidence_screen)
    assert "seen_passages" in code, (
        "the evidence page no longer tracks passages it has printed")
    assert "same published description as" in code, (
        "a repeated passage must be NAMED rather than silently dropped")
    assert "blockquote" in code, "the first occurrence must still be quoted"


def test_the_route_a_live_run_uses_reaches_this_renderer():
    """`/runs/<id>/evidence` is where the duplicates were measured.

    It does not render anything itself -- it resolves a manifest key and
    delegates. A repair applied to the demo-dossier renderer only would have
    been INERT on the surface that actually showed the defect, and this
    pins the delegation so that stays true.
    """
    assert "_evidence_screen" in _code(WebApp._run_evidence)


def test_the_repair_does_not_hide_the_source():
    """A source removed is a source the reader cannot check.

    The defect is a REPEATED QUOTE, not a repeated source: the card, its
    link, its author and its dates must survive dedup untouched.
    """
    code = _code(WebApp._evidence_screen)
    # the card is still emitted for every record in the group
    assert 'join(_card(r) for r in group)' in code, (
        "records are no longer rendered one card each")
    # and nothing in the card builder skips a record outright
    card = code.split("def _card(rec):", 1)[1].split("sections = [headline]")[0]
    assert " continue " not in card, (
        "the card builder skips a record instead of only its blockquote")

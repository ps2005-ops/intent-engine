"""Prospect-100 resume, visual round: the session bar wraps as items.

MEASURED at 375 and 390 px on all five status pages (light and dark): the
session bar broke between "Getting started" and "signed in as", so line two
opened with a bare "·". The separators are now decorative spans the phone
layout hides, and no bare separator text is left for a line break to strand.
"""
import re

from intent_engine.webapp.app import WebApp, _A11Y_CSS
from intent_engine.webapp.config import AppConfig


def _app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, resolver=False)


def _bare_separators(html):
    return re.sub(r'<span class="sep" aria-hidden="true">·</span>', "",
                  html).count("·")


def test_no_session_bar_variant_carries_a_bare_separator(tmp_path):
    app = _app(tmp_path)
    variants = [
        app._nav(None),
        app._nav({"user_id": "u", "email": "a@b.test"}, csrf="c"),
        app._nav({"user_id": "u", "anonymous": True}, csrf="c"),
    ]
    for html in variants:
        assert 'aria-label="Session"' in html
        assert _bare_separators(html) == 0, html


def test_phones_hide_the_separators_and_the_bar_is_a_flex_row():
    css = _A11Y_CSS
    assert 'nav[aria-label="Session"]{display:flex;flex-wrap:wrap' in css
    assert re.search(r'@media \(max-width:600px\)\{nav\[aria-label="Session"\] '
                     r'\.sep\{display:none\}', css)


def test_unstyled_links_take_the_product_accent_without_winning_fights():
    # :where() keeps specificity at zero, so any component rule still wins.
    assert ":where(a[href]){color:#1d4ed8}" in _A11Y_CSS

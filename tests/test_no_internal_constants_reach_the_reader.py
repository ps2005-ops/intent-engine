"""Stylesheets and enum constants are not customer copy.

Both found on Meta's live capture at b0ec8cb, on the two pages whose whole job
is to make a hostile reader trust the analysis.
"""
from __future__ import annotations

import re

import pytest

from intent_engine.founder_brief import challenge_block
from intent_engine.webapp.app import WebApp


# --- D1: every CSS constant concatenated into a page must be wrapped -------

def _css_constants():
    """The four constants `_full_analysis` concatenates, by import."""
    from intent_engine.founder_brief import render as fr
    from intent_engine.founder_brief import narrative as fn
    from intent_engine.founder_brief import history_chart as charts
    return {
        "BRIEF_CSS": fr.BRIEF_CSS,
        "NARRATIVE_CSS": fn.NARRATIVE_CSS,
        "CHART_CSS": charts.CHART_CSS,
        "challenge_block.CSS": challenge_block.CSS,
    }


@pytest.mark.parametrize("name", sorted(_css_constants()))
def test_every_css_constant_is_style_wrapped(name):
    """THE DEFECT WAS THE ASYMMETRY, so the guard is over the whole set.

    `app.py` builds the full analysis as `BRIEF_CSS + NARRATIVE_CSS +
    CHART_CSS + _cb.CSS + render_dossier(...)`. Three of those opened with
    `<style>` and one did not, so `_stylize` hoisted three into <head> and
    left the fourth sitting in the body AS TEXT:

        <main> .challenge{border:1px solid var(--rule);border-radius:10px; ...

    Every reader, text extractor and screen reader got a stylesheet as the
    opening content of the analysis -- and because the rules never applied,
    the belief-challenge card rendered unstyled on every company.
    """
    css = _css_constants()[name]
    assert css.lstrip().startswith("<style"), \
        f"{name} is concatenated into a page body but is not <style>-wrapped"
    assert "</style>" in css, f"{name} opens a <style> it never closes"


def test_the_challenge_rules_are_not_loose_text():
    """The specific shape that shipped: a bare selector at the string head."""
    assert not challenge_block.CSS.lstrip().startswith(".challenge{")


# --- D2: internal state names never reach the page ------------------------

#: A token that looks like a constant: two or more SHOUTING words joined by
#: underscores. Deliberately not a list of the known enums -- the point is to
#: catch the one nobody thought of.
_CONSTANT = re.compile(r"\b[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]{2,})+\b")


@pytest.mark.parametrize("state,expected", [
    ("DISCOVERY_PARTIAL", "partial — more sources remain unread"),
    ("HAVE_INDEPENDENT", "independent corroboration found"),
    ("DIRECTLY_RELEVANT", "directly about this company"),
    ("CURRENT", "current"),
    ("STALE", "out of date"),
])
def test_the_states_the_live_page_leaked_are_mapped(state, expected):
    assert WebApp._plain_state(state) == expected


def test_an_unmapped_constant_still_does_not_shout():
    """A state nobody has looked at degrades; it does not leak verbatim."""
    out = WebApp._plain_state("SOME_FUTURE_STATE")
    assert not _CONSTANT.search(out), out
    assert out == "some future state"


def test_ordinary_values_are_left_alone():
    """The control. This runs over every record on the page, so it must not
    rewrite a title, a host or a date."""
    for value in ("Meta Platforms, Inc.", "sec.gov", "2026-01-29",
                  "10-K", "USA", ""):
        assert WebApp._plain_state(value) == value


def test_no_constant_survives_the_mapping_of_any_known_state():
    """Every value in the table maps to something a reader can act on."""
    for state, plain in WebApp._PLAIN_STATE.items():
        assert not _CONSTANT.search(plain), f"{state} -> {plain}"
        assert plain and plain[0].islower(), f"{state} -> {plain}"


def test_the_render_sites_call_the_mapper_not_the_raw_value():
    """STRUCTURAL, and it reads the running code.

    The four sites are the ones the live capture leaked from. A guard that
    only tested `_plain_state` in isolation would stay green while a call
    site kept printing the constant -- which is exactly how a raw enum has
    shipped past a green test in this codebase before.
    """
    import inspect
    src = inspect.getsource(WebApp._evidence_screen)
    for leaked in ('_e(reading["coverage"])', '_e(reading["reading"])',
                   '_e(rec.get("relevance") or "")'):
        assert leaked not in src, f"{leaked} still renders the raw constant"
    assert src.count("_plain_state(") >= 3, \
        "the evidence screen must map every state it prints"

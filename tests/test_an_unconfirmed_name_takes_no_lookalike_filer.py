"""An unconfirmed run takes a filer only when its name IS the typed name."""
from __future__ import annotations

import json

from intent_engine.company_ingestion import edgar
from intent_engine.company_ingestion.edgar import resolve_cik

TABLE = {str(i): r for i, r in enumerate([
    {"cik_str": 1049521, "ticker": "MRCY", "title": "MERCURY SYSTEMS INC"},
    {"cik_str": 64996, "ticker": "MCY", "title": "MERCURY GENERAL CORP"},
    {"cik_str": 1639723, "ticker": "NAVN", "title": "Navan, Inc."},
    {"cik_str": 60667, "ticker": "LOW", "title": "LOWES COMPANIES INC"},
])}


def _tickers(url, timeout, max_bytes=None):
    if "company_tickers" in url:
        return (200, {"Content-Type": "application/json"},
                json.dumps(TABLE).encode(), False)
    return (404, {}, b"", False)


def test_a_lookalike_filer_is_refused_when_nobody_confirmed_it():
    assert resolve_cik("Mercury", transport=_tickers, resolver=False,
                       exact=True) is None


def test_the_same_name_still_resolves_exactly():
    """CONTROL: exactness must not cost a real filer its filings."""
    got = resolve_cik("Navan", transport=_tickers, resolver=False, exact=True)
    assert got and got["cik"] == 1639723
    low = resolve_cik("Lowe's Companies", transport=_tickers, resolver=False,
                      exact=True)
    assert low and low["cik"] == 60667


def test_a_suggestion_still_contains_match():
    """The default (autocomplete, a person then confirms) is unchanged."""
    got = resolve_cik("Mercury", transport=_tickers, resolver=False)
    assert got and got["cik"] in (1049521, 64996)


def test_the_run_path_asks_for_exactness(monkeypatch):
    """CALLER PIN: the proposal a run makes passes exact=True."""
    seen = {}

    def fake(name, **kw):
        seen.update(kw)
        return None
    monkeypatch.setattr(edgar, "resolve_cik", fake)
    monkeypatch.setattr("intent_engine.company_ingestion.entities.declared_cik",
                        lambda **kw: None)
    assert edgar.propose_edgar_candidates(company_name="Mercury") == []
    assert seen.get("exact") is True

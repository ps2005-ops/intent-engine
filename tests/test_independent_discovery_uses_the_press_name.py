"""Independent discovery searches under the name the press uses.

MEASURED 2026-11-28 (prospect-98 w4): a registry pick carries the LEGAL name,
and the query became "Prophix Software" -- found nothing -- where the same
company typed by website found four articles directly about it.
"""
import types

from intent_engine.company_ingestion import independent_reporting as IR
from intent_engine.company_ingestion import service as SVC


def _calls(monkeypatch, meta):
    seen = {}

    def discover(**kw):
        seen.update(kw)
        return {"candidates": []}

    monkeypatch.setattr(IR, "discover", discover)
    monkeypatch.setattr(IR, "live_fetchers", lambda: (None, None))
    monkeypatch.setattr(IR, "recall", lambda d: [])
    monkeypatch.setattr(IR, "remember", lambda d, c: None)
    cls = next(v for v in vars(SVC).values()
               if isinstance(v, type) and hasattr(v, "_independent_reporting_candidates"))
    obj = cls.__new__(cls)
    obj.transport = None
    obj.INDEPENDENT_REPORTING_LIVE = True
    obj._INDEPENDENT_REPORTING_CAP_S = getattr(cls, "_INDEPENDENT_REPORTING_CAP_S", 20)
    obj._namesake_free = lambda meta: False
    obj._independent_reporting_candidates(meta)
    return seen


def test_a_registry_pick_is_searched_by_its_curated_common_name(monkeypatch):
    seen = _calls(monkeypatch, {"company_name": "Prophix Software Inc.",
                                "website": "https://prophix.com", "domain": "prophix.com"})
    assert seen["company"] == "Prophix"
    assert "Prophix Software Inc." in seen["aliases"]


def test_a_short_common_word_alias_is_never_a_search_term(monkeypatch):
    seen = _calls(monkeypatch, {"company_name": "Safe Security, Inc.",
                                "website": "https://safe.security", "domain": "safe.security"})
    assert seen["company"] == "SAFE"
    assert "safe" not in [a.lower() for a in seen["aliases"] if len(a) <= 4]


def test_an_unregistered_company_keeps_the_old_behaviour(monkeypatch):
    seen = _calls(monkeypatch, {"company_name": "Acme Widgets Inc.",
                                "website": "https://acme-widgets.example", "domain": "acme-widgets.example"})
    assert seen["company"] == "Acme Widgets"

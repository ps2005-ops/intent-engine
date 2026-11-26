"""An article verified about a company once is offered again -- and re-verified.

Rounds 8 and 9 counted 9 and then 4 companies with two independent origins
on unchanged code: search feeds return what is newest, so verified coverage
fell out of the feed between runs.
"""
from __future__ import annotations

from intent_engine.company_ingestion import independent_reporting as IR

ART = "https://siliconangle.com/2026/04/15/qlik-debuts-agentic-capabilities/"
PAGE = ("<html><head><title>Qlik debuts agentic capabilities</title></head>"
        "<body><p>Qlik debuts new agentic capabilities for its analytics "
        "platform, Qlik said on Tuesday, and Qlik customers can now automate "
        "pipelines. Qlik expanded its partner program in Europe.</p>"
        "<p>Qlik competes with Microsoft and Salesforce in analytics.</p>"
        "</body></html>")


class _Robots:
    def allows(self, url):
        return True


def _fetch(pages):
    def fetch(url, mimes=()):
        if url in pages:
            return {"ok": True, "body": pages[url], "final_url": url}
        return {"ok": False, "failure_type": "http_status"}
    return fetch


def _discover(pages, remembered):
    return IR.discover(company="Qlik", domain="qlik.com", fetch=_fetch(pages),
                       fetch_json=lambda u: None, robots=_Robots(),
                       today="2026-11-26", use_wikipedia=False,
                       use_gdelt=False, namesake_free=True,
                       remembered=remembered)


def test_a_remembered_article_is_offered_and_reverified():
    rep = _discover({ART: PAGE}, [{"url": ART, "title": "t",
                                   "published": "2026-04-15"}])
    assert rep.get("remembered_offered") == 1
    assert [c["url"] for c in rep["candidates"]] == [ART]


def test_a_remembered_article_that_no_longer_verifies_is_refused():
    """CONTROL: memory is a pointer, never evidence on its own."""
    rep = _discover({}, [{"url": ART, "title": "t", "published": "2026-04-15"}])
    assert rep["candidates"] == []


def test_memory_round_trips_per_company(tmp_path, monkeypatch):
    monkeypatch.setenv("INDEPENDENT_MEMORY_DIR", str(tmp_path))
    IR.remember("qlik.com", [{"url": ART, "source_class": "independent_reporting",
                              "title": "t", "published": "2026-04-15"},
                             {"url": "https://wire.example/x",
                              "source_class": "company_owned"}])
    got = IR.recall("www.qlik.com")
    assert [g["url"] for g in got] == [ART]   # a wire release is not kept
    assert IR.recall("brex.com") == []


def test_no_directory_means_no_memory(monkeypatch):
    monkeypatch.delenv("INDEPENDENT_MEMORY_DIR", raising=False)
    monkeypatch.delenv("ACQUISITION_MEMORY_DIR", raising=False)
    assert IR.memory_path("qlik.com") is None
    IR.remember("qlik.com", [{"url": ART, "source_class": "independent_reporting"}])
    assert IR.recall("qlik.com") == []

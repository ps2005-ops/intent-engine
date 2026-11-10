"""Independent reporting: discovery is not evidence, robots are policy, a wire
release is the company speaking, and a name is not an identity."""
from __future__ import annotations

from intent_engine.company_ingestion import independent_reporting as IR

ARTICLE = """<html><head><title>Hammerspace nabs $100M</title></head><body>
<p>Hammerspace raised $100 million to expand its data platform, and
customers are migrating from legacy storage to Hammerspace for AI training.</p>
<p>Analysts said Hammerspace competes with established storage vendors on
price and integration with GPU clusters.</p></body></html>"""
WIRE = """<html><body><p>SAN MATEO, Calif., /PRNewswire/ -- Hammerspace today
announced a partnership with a GPU cloud and said customers are migrating to
Hammerspace for training. Hammerspace competes on price.</p></body></html>"""
NOT_ABOUT = """<html><body><p>Storage prices rose this quarter across the
industry, analysts said, and several vendors announced new arrays.</p>
</body></html>"""


def _feed(*items):
    body = "".join(f"<item><title>{t}</title><link>{u}</link>"
                   f"<pubDate>{d}</pubDate><description>{s}</description></item>"
                   for t, u, d, s in items)
    return f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>"


class _Web:
    """A fake web: url -> (status, body). robots.txt defaults to 404 (allow)."""

    def __init__(self, pages, robots=None):
        self.pages, self.robots, self.calls = pages, robots or {}, []

    def fetch(self, url, extra=()):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            host = IR._host(url)
            if host in self.robots:
                status, body = self.robots[host]
                return {"ok": status == 200, "status_code": status,
                        "body": body, "final_url": url}
            return {"ok": False, "status_code": 404, "body": "",
                    "failure_type": "http_status"}
        if url in self.pages:
            status, body = self.pages[url]
            return {"ok": status == 200, "status_code": status, "body": body,
                    "final_url": url, "failure_type": None if status == 200
                    else "http_status"}
        return {"ok": False, "status_code": 404, "body": "",
                "failure_type": "http_status"}


def _only_siliconangle(monkeypatch):
    monkeypatch.setattr(IR, "PUBLISHERS", (IR.Publisher(
        "SiliconANGLE", "siliconangle.com", "/tag/{slug}/feed/", ""),))


def _run(web, **kw):
    return IR.discover(company=kw.pop("company", "Hammerspace"),
                       domain=kw.pop("domain", "hammerspace.com"),
                       fetch=web.fetch, fetch_json=lambda u: None,
                       use_gdelt=False, use_wikipedia=False,
                       today="2026-11-09", **kw)


TAG = "https://siliconangle.com/tag/hammerspace/feed/"
A1 = "https://siliconangle.com/2025/04/16/hammerspace-100m/"


def test_a_verified_article_becomes_an_independent_candidate(monkeypatch):
    _only_siliconangle(monkeypatch)
    web = _Web({TAG: (200, _feed(("Hammerspace nabs $100M", A1,
                                  "Wed, 16 Apr 2025 10:00:00 GMT", "x"))),
                A1: (200, ARTICLE)})
    report = _run(web)
    assert len(report["candidates"]) == 1
    cand = report["candidates"][0]
    assert cand["source_class"] == "independent_reporting"
    assert cand["publisher"] == "SiliconANGLE"
    assert cand["published"] == "2025-04-16"
    assert "Hammerspace" in cand["excerpt"]
    assert report["independent_relevant_origins"] == 1


def test_robots_disallow_is_honoured_for_feed_and_article(monkeypatch):
    _only_siliconangle(monkeypatch)
    web = _Web({TAG: (200, _feed(("t", A1, "", ""))), A1: (200, ARTICLE)},
               robots={"siliconangle.com":
                       (200, "User-agent: *\nDisallow: /tag/\n")})
    report = _run(web)
    assert report["candidates"] == []
    assert TAG not in web.calls, "a disallowed feed was fetched"
    assert report["rejection_reasons"]["FEED_DISALLOWED_BY_ROBOTS"] == 1


def test_a_refused_robots_file_means_do_not_fetch(monkeypatch):
    _only_siliconangle(monkeypatch)
    web = _Web({TAG: (200, _feed(("t", A1, "", ""))), A1: (200, ARTICLE)},
               robots={"siliconangle.com": (403, "")})
    report = _run(web)
    assert report["candidates"] == [] and TAG not in web.calls


def test_a_wire_release_is_the_company_speaking(monkeypatch):
    _only_siliconangle(monkeypatch)
    web = _Web({TAG: (200, _feed(("Hammerspace partners", A1, "", ""))),
                A1: (200, WIRE)})
    report = _run(web)
    assert report["candidates"][0]["source_class"] == "company_owned"
    assert report["candidates"][0]["independence"] == "COMPANY_ISSUED_VIA_WIRE"
    assert report["independent_relevant_origins"] == 0


def test_an_article_that_does_not_discuss_the_subject_is_refused(monkeypatch):
    _only_siliconangle(monkeypatch)
    web = _Web({TAG: (200, _feed(("Storage prices", A1, "", ""))),
                A1: (200, NOT_ABOUT)})
    report = _run(web)
    assert report["candidates"] == []
    assert any(k.startswith("RELEVANCE_") for k in report["rejection_reasons"])


def test_syndicated_copies_count_once():
    pointers = [{"url": "https://a.com/x", "title": "Hammerspace nabs $100M"},
                {"url": "https://b.com/y", "title": "Hammerspace Nabs $100M!"},
                {"url": "https://a.com/x/", "title": "other"}]
    assert len(IR.dedupe(pointers)) == 1


def test_a_one_word_name_is_a_proper_noun_not_a_word():
    assert IR.mentions_subject("Soda raised a round", "Soda")
    assert not IR.mentions_subject("a can of soda on the desk", "Soda")
    assert IR.mentions_subject("the cube dev team", "Cube Dev")


def test_search_feed_items_must_name_the_subject(monkeypatch):
    monkeypatch.setattr(IR, "PUBLISHERS", (IR.Publisher(
        "ZDNET", "www.zdnet.com", "", "/?s={q}&feed=rss2"),))
    url = "https://www.zdnet.com/?s=%22Hammerspace%22&feed=rss2"
    web = _Web({url: (200, _feed(("Best laptops of 2026", A1, "", "")))})
    report = _run(web)
    assert report["pointers_found"] == 0
    assert A1 not in web.calls


def test_wikipedia_references_need_the_company_website(monkeypatch):
    """Name search found "Jones Soda" for Soda; the gate is Wikidata P856."""
    monkeypatch.setattr(IR, "PUBLISHERS", ())

    def fetch_json(url):
        if "wbsearchentities" in url:
            return {"search": [{"id": "Q1"}]}
        if "wbgetentities" in url:
            return {"entities": {"Q1": {
                "claims": {"P856": [{"mainsnak": {"datavalue": {
                    "value": "https://www.jonessoda.com"}}}]},
                "sitelinks": {"enwiki": {"title": "Jones Soda"}}}}}
        raise AssertionError("must not read references of the wrong company")
    report = IR.discover(company="Soda", domain="soda.io",
                         fetch=_Web({}).fetch, fetch_json=fetch_json,
                         use_gdelt=False, today="2026-11-09")
    assert report["candidates"] == []
    assert report["rejection_reasons"][
        "WIKIDATA_NO_ITEM_WITH_THIS_WEBSITE"] == 1


def test_gdelt_is_paced_to_its_published_limit():
    waits = []
    IR._GDELT_LAST[0] = 100.0
    report = {"channels_attempted": [], "channels_successful": [],
              "rejection_reasons": IR._Counter()}
    IR._gdelt_pointers("Acme", lambda u: None, report,
                       sleeper=waits.append, clock=lambda: 101.0)
    assert waits and waits[0] >= IR.GDELT_MIN_INTERVAL_S - 1.0 - 1e-9
    assert report["rejection_reasons"]["GDELT_UNAVAILABLE_OR_RATE_LIMITED"] == 1


def test_discovery_never_raises_on_a_broken_channel(monkeypatch):
    _only_siliconangle(monkeypatch)

    def boom(url, extra=()):
        raise RuntimeError("network on fire")
    report = IR.discover(company="Hammerspace", domain="hammerspace.com",
                         fetch=boom, fetch_json=lambda u: None,
                         use_gdelt=False, use_wikipedia=False)
    assert report["candidates"] == []
    assert report["rejection_reasons"]["FEED_CHANNEL_RAISED"] == 1


def test_every_admitted_publisher_records_its_probe():
    for pub in IR.PUBLISHERS:
        assert pub.verified.startswith("20"), pub.name


def test_the_two_accounts_merge_without_lending_coverage():
    from intent_engine.company_ingestion import relevance as R
    from intent_engine.company_ingestion.service import _merge_reporting
    base = {"contract": "third_party_discovery.v1",
            "coverage": R.DISCOVERY_EXHAUSTED,
            "channels_attempted": ["edgar_full_text_search"],
            "channels_successful": ["edgar_full_text_search"],
            "hits_total": 3, "candidates_considered": 2,
            "candidates_fetched": 2, "rejection_reasons": {"IRRELEVANT": 2},
            "independent_relevant_origins": 0}
    news = {"contract": IR.CONTRACT, "query": "Hammerspace",
            "channels_attempted": ["publisher_feed:siliconangle.com"],
            "channels_successful": ["publisher_feed"], "pointers_found": 5,
            "candidates_considered": 5, "candidates_fetched": 5,
            "rejection_reasons": {"RELEVANCE_IRRELEVANT": 1},
            "independent_relevant_origins": 1,
            "candidates": [{"publisher": "SiliconANGLE",
                            "source_class": "independent_reporting"}]}
    out = _merge_reporting(base, news)
    assert out["coverage"] == R.DISCOVERY_EXHAUSTED        # filing's own grade
    assert out["independent_relevant_origins"] == 1
    assert out["candidates_fetched"] == 7
    assert out["rejection_reasons"]["reporting:RELEVANCE_IRRELEVANT"] == 1
    assert out["rejection_reasons"]["IRRELEVANT"] == 2
    assert out["independent_reporting"]["publishers"] == ["SiliconANGLE"]


def test_an_injected_transport_never_reaches_live_publishers():
    from intent_engine.company_ingestion.service import (
        CompanyIngestionService,
    )
    svc = CompanyIngestionService.__new__(CompanyIngestionService)
    svc.transport = object()
    assert svc._independent_reporting_candidates(
        {"company_name": "Hammerspace, Inc.", "domain": "hammerspace.com"}) \
        == []


def test_the_suite_cannot_reach_live_publishers():
    from intent_engine.company_ingestion.service import (
        CompanyIngestionService,
    )
    assert CompanyIngestionService.INDEPENDENT_REPORTING_LIVE is False
    svc = CompanyIngestionService.__new__(CompanyIngestionService)
    svc.transport = None
    assert svc._independent_reporting_candidates(
        {"company_name": "Hammerspace, Inc.", "domain": "hammerspace.com"}) \
        == []


def test_a_name_that_is_also_a_word_needs_an_identity_anchor(monkeypatch):
    """"Ramp" the company vs "ramp up" the phrase: the article itself shows
    the collision, and then only the domain or a full name identifies it."""
    _only_siliconangle(monkeypatch)
    tag = "https://siliconangle.com/tag/ramp/feed/"
    url = "https://siliconangle.com/2026/01/02/ramp-story/"
    text = ("<html><body><p>Ramp competes with legacy vendors on price as "
            "firms ramp up spending. Ramp raised a round and customers are "
            "migrating to Ramp.</p></body></html>")
    web = _Web({tag: (200, _feed(("Ramp story", url, "", ""))),
                url: (200, text)})
    report = IR.discover(company="Ramp", domain="ramp.com",
                         fetch=web.fetch, fetch_json=lambda u: None,
                         use_gdelt=False, use_wikipedia=False)
    assert report["candidates"] == []
    assert report["rejection_reasons"][
        "AMBIGUOUS_NAME_NO_IDENTITY_ANCHOR"] == 1
    # positive control: the same article naming ramp.com is accepted
    web.pages[url] = (200, text.replace("</p>", " See ramp.com.</p>"))
    report = IR.discover(company="Ramp", domain="ramp.com",
                         fetch=web.fetch, fetch_json=lambda u: None,
                         use_gdelt=False, use_wikipedia=False)
    assert len(report["candidates"]) == 1


def test_a_regulatory_filing_is_not_independent_reporting():
    report = {"rejection_reasons": IR._Counter(), "candidates_fetched": 0}
    out = IR.verify({"url": "https://www.sec.gov/Archives/x.htm"},
                    company="Verisk", domain="verisk.com", aliases=(),
                    fetch=lambda u, e=(): {"ok": True, "body": ""},
                    robots=IR.Robots(lambda u: {"ok": False,
                                                "status_code": 404}, "ua"),
                    report=report)
    assert out is None
    assert report["rejection_reasons"]["REGULATORY_FILING_NOT_REPORTING"] == 1


def test_could_not_look_is_never_reported_as_found_nothing(monkeypatch):
    _only_siliconangle(monkeypatch)
    web = _Web({TAG: (429, "")})
    report = IR.discover(company="Hammerspace", domain="hammerspace.com",
                         fetch=web.fetch, fetch_json=lambda u: None,
                         use_gdelt=False, use_wikipedia=True)
    assert report["rejection_reasons"]["FEED_UNAVAILABLE_429"] == 1
    assert report["rejection_reasons"]["WIKIDATA_UNAVAILABLE"] == 1


def test_requests_to_one_host_are_spaced():
    waits, t = [], [1000.0]
    IR._HOST_NEXT.clear()
    for _ in range(3):
        IR._polite("https://example.org/a", clock=lambda: t[0],
                   sleeper=waits.append)
    assert [round(w, 6) for w in waits] == [
        round(IR.PER_HOST_INTERVAL_S, 6), round(2 * IR.PER_HOST_INTERVAL_S, 6)]


def test_the_article_most_about_the_subject_comes_first(monkeypatch):
    _only_siliconangle(monkeypatch)
    a_new = "https://siliconangle.com/2026/10/06/summit/"
    a_old = "https://siliconangle.com/2025/04/16/hammerspace-100m/"
    roundup = ("<html><body><p>At the summit, vendors discussed storage. "
               "Hammerspace competes on price in AI storage.</p></body></html>")
    web = _Web({TAG: (200, _feed(("Summit round-up", a_new,
                                  "Mon, 06 Oct 2026 10:00:00 GMT", ""),
                                 ("Hammerspace nabs $100M", a_old,
                                  "Wed, 16 Apr 2025 10:00:00 GMT", ""))),
                a_new: (200, roundup), a_old: (200, ARTICLE)})
    report = _run(web)
    assert report["candidates"][0]["url"] == a_old, \
        [c["url"] for c in report["candidates"]]


def test_a_wikipedia_reference_must_be_a_dated_article():
    """Measured: a library catalogue and investors' portfolio pages arrived
    as "independent reporting" through Wikipedia references."""
    report = {"rejection_reasons": IR._Counter(), "candidates_fetched": 0}
    portfolio = ("<html><body><p>Oak Hill portfolio: Gusto competes in "
                 "payroll and customers are migrating to Gusto.</p>"
                 "</body></html>")
    out = IR.verify({"url": "https://oakhill.com/portfolio/gusto",
                     "channel": "wikipedia_references",
                     "publisher": "oakhill.com"},
                    company="Gusto", domain="gusto.com", aliases=(),
                    fetch=lambda u, e=(): {"ok": True, "body": portfolio},
                    robots=IR.Robots(lambda u: {"ok": False,
                                                "status_code": 404}, "ua"),
                    report=report)
    assert out is None
    assert report["rejection_reasons"]["REFERENCE_NOT_A_DATED_ARTICLE"] == 1
    assert IR._NOT_REPORTING.search("catalogue.bnf.fr.")


def test_a_quoted_verdict_leaves_a_competitor_card_out_not_the_run():
    """Live (pass 4): a competitor claim quoting "is broken" made the
    competitors section raise and the conversation endpoint answer 500."""
    from intent_engine.founder_intelligence import perspective as P
    from intent_engine.founder_intelligence.records import AVAIL_SUPPORTED

    class _C:
        def __init__(self, cid, text):
            self.claim_id, self.text = cid, text
            self.availability, self.confidence = AVAIL_SUPPORTED, "MEDIUM"

        def validate(self):
            return None
    section = P.assemble_competitors(True, claims=[
        _C("a", "Analysts say the incumbent's pricing model is broken."),
        _C("b", "Rival Co sells to the same data teams.")])
    heads = [c.headline for c in section.cards]
    assert heads == ["Rival Co sells to the same data teams."]


def test_a_slide_given_bare_strings_renders():
    """belief_slides passes strings; /slides answered 500 on 8 of 95."""
    from intent_engine.strategic_intelligence import slides as S
    slide = S._slide("market_believes", "What the market believes",
                     ["The market expects growth to slow.", "Basis: prices."])
    assert [b["text"] for b in slide["bullets"]][:1] == [
        "The market expects growth to slow."]

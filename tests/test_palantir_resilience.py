"""Palantir resilience regression (production incident).

A public company whose own website is JavaScript-only (Palantir) must not
dead-end. An authoritative SEC EDGAR fallback supplies real, server-rendered
evidence, so the run completes (PARTIAL) instead of FAILED, individual source
failures are recorded rather than failing the whole run, and every guest
lifecycle page stays styled.

No test here touches the network — the SEC and company responses are injected.
"""
import email
import json
import urllib.error

from test_webapp_demo_mode import Client, _make, _start_demo   # noqa: F401
from intent_engine.company_ingestion.edgar import (
    filing_candidates, propose_edgar_candidates, resolve_cik,
)
from intent_engine.company_ingestion.records import MAX_APPROVED_SOURCES
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService

PALANTIR = "https://www.palantir.com"
PLTR_CIK = 1321655
AS_OF = "2026-07-26T00:00:00+00:00"

TICKERS = json.dumps({
    "0": {"cik_str": PLTR_CIK, "ticker": "PLTR",
          "title": "Palantir Technologies Inc."},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
})
_8K_ACC = "0001321655-25-000045"
_10Q_ACC = "0001321655-25-000032"
SUBMISSIONS = json.dumps({"filings": {"recent": {
    "form": ["4", "8-K", "10-Q"],
    "accessionNumber": ["0000000000-25-000001", _8K_ACC, _10Q_ACC],
    "primaryDocument": ["form4.xml", "pltr-8k.htm", "pltr-10q.htm"],
    "filingDate": ["2025-05-01", "2025-05-05", "2025-05-06"],
}}})
_8K_HTML = ("<html><head><title>Palantir 8-K</title></head><body>"
            "<h1>Results of Operations</h1><p>Palantir Technologies reported "
            "revenue growth driven by commercial customer expansion and its "
            "AIP platform.</p><p>Government and commercial customers use the "
            "software for data integration and analytics.</p></body></html>")
_10Q_HTML = ("<html><head><title>Palantir 10-Q</title></head><body>"
             "<h1>Quarterly Report</h1><p>The company describes risks in "
             "customer concentration and its government contracting business "
             "and discusses margins and remaining performance obligations.</p>"
             "</body></html>")
# A realistic JavaScript-first marketing shell: no body text, but — like every
# real SPA marketing site — server-rendered <title>, OpenGraph and JSON-LD that
# genuinely describe the company. The extractor salvages these.
_JS_SHELL = (
    '<html><head><title>Palantir Technologies</title>'
    '<meta property="og:title" content="Palantir">'
    '<meta property="og:description" content="Palantir builds software '
    'platforms - Foundry, Gotham and AIP - that help government and commercial '
    'organizations integrate their data and make operational decisions.">'
    '<script type="application/ld+json">{"@type":"Organization",'
    '"name":"Palantir Technologies Inc.","description":"Builds Foundry, '
    'Gotham, Apollo and AIP for defense, intelligence and commercial '
    'customers."}</script></head><body>'
    '<div id="__next"></div><script>window.__NEXT_DATA__={}</script>'
    '</body></html>')
# A truly empty shell — no metadata at all — must STILL be recorded as a
# javascript_only failure (the salvage must not invent content).
_EMPTY_SHELL = ('<html><head><title></title></head><body><div id="app"></div>'
                '<script>render()</script></body></html>')


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "err",
                                  email.message_from_string(""), None)


def palantir_transport(url, timeout):
    """JS-only company site + one 403 page + a reachable SEC EDGAR. External
    review sites time out; anything else 404s."""
    bare = url.split("#")[0].rstrip("/")
    if bare in ("https://www.palantir.com", "https://palantir.com"):
        return (200, {"content-type": "text/html"}, _JS_SHELL.encode(), False)
    if bare.endswith("/about"):
        raise _http_error(url, 403)                 # access refused
    if "company_tickers.json" in url:
        return (200, {"content-type": "application/json"},
                TICKERS.encode(), False)
    if "/submissions/CIK" in url:
        return (200, {"content-type": "application/json"},
                SUBMISSIONS.encode(), False)
    if "pltr-8k.htm" in url:
        return (200, {"content-type": "text/html"}, _8K_HTML.encode(), False)
    if "pltr-10q.htm" in url:
        return (200, {"content-type": "text/html"}, _10Q_HTML.encode(), False)
    if any(s in url for s in ("g2.com", "trustpilot", "capterra")):
        raise TimeoutError("timed out")             # external voice: timeout
    if "palantir.com" in url:                        # other pages: JS-only
        return (200, {"content-type": "text/html"}, _JS_SHELL.encode(), False)
    raise _http_error(url, 404)


# --- SEC EDGAR adapter ------------------------------------------------------

def test_resolve_cik_by_name_and_ticker():
    by_name = resolve_cik("Palantir Technologies", transport=palantir_transport,
                          resolver=False)
    assert by_name and by_name["cik"] == PLTR_CIK
    assert by_name["ticker"] == "PLTR" and by_name["cik10"] == "0001321655"
    by_ticker = resolve_cik("literally anything", ticker="PLTR",
                            transport=palantir_transport, resolver=False)
    assert by_ticker["cik"] == PLTR_CIK


def test_resolve_cik_unknown_company_returns_none():
    assert resolve_cik("Definitely Not A Real Filer QZX",
                       transport=palantir_transport, resolver=False) is None


def test_filing_candidates_prefer_small_html_filings():
    resolved = resolve_cik("Palantir Technologies",
                           transport=palantir_transport, resolver=False)
    cands = filing_candidates(resolved, transport=palantir_transport,
                              resolver=False)
    assert cands, "expected SEC filing candidates"
    assert all(c["source_class"] == "investor_material" for c in cands)
    # the form-4 XML primary document is skipped; only parseable HTML remains
    assert all(c["url"].lower().endswith((".htm", ".html")) for c in cands)
    assert "8-K" in cands[0]["title"]               # small 8-K preferred first


def test_propose_edgar_never_raises_when_sec_unreachable():
    def down(url, timeout):
        raise OSError("sec down")
    assert propose_edgar_candidates(company_name="Palantir", transport=down,
                                    resolver=False) == []


# --- service lifecycle: Palantir completes despite a JS-only site -----------

def _service(tmp_path, transport=palantir_transport):
    return CompanyIngestionService(tmp_path / "ci.jsonl", transport=transport,
                                   resolver=False)


def test_palantir_completes_via_authoritative_fallback(tmp_path):
    ci = _service(tmp_path)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name="Palantir Technologies",
                           website=PALANTIR, user_id="u1",
                           as_of=AS_OF)["run_id"]
    cands = ci.discover(run_id)
    sec = [c for c in cands if c.get("source_class") == "investor_material"]
    assert sec, "SEC EDGAR fallback should propose authoritative candidates"
    home = [c for c in cands if c["source_type"] == "homepage"][:1]
    about = [c for c in cands if c["source_type"] == "about"][:1]
    approved = [c["candidate_id"] for c in home + about + sec]
    ci.approve(run_id, user_id="u1", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in cands
                             if c["candidate_id"] not in approved])
    fetched = ci.fetch_approved(run_id)

    # authoritative evidence retrieved despite the JS-only homepage + 403 page
    assert any(r["source_class"] == "investor_material" for r in fetched["ok"])
    ftypes = {f["failure_type"] for f in fetched["failed"]}
    assert "http_status" in ftypes                  # the 403 /about page
    # The JS-only homepage is SALVAGED from its server-rendered metadata
    # (title/OpenGraph/JSON-LD) rather than discarded, so real company
    # description reaches the report instead of an empty "javascript_only" gap.
    home_doc = [r for r in fetched["ok"] if r["source_type"] == "homepage"]
    assert home_doc, "JS-only homepage should be salvaged via metadata"
    assert "Foundry" in home_doc[0]["text_content"]

    result = ci.compose(run_id, fi_service=fi)
    assert result["ingestion_status"] == "PARTIAL"  # NOT FAILED
    assert ci.store.run_state(run_id) == "PARTIAL"
    assert result["sections"], "a completed run must be openable"
    lib = result["evidence_library"]
    assert lib["external_public"]                   # SEC filings listed
    assert lib["unavailable_or_failed"]             # failures recorded, honest
    ids = [r["source_id"] for r in ci.store.retrieved(run_id)]
    assert len(ids) == len(set(ids))                # no duplicate evidence


def test_metadata_salvage_never_invents_content(tmp_path):
    """The JS salvage recovers only server-rendered metadata that genuinely
    exists. A shell with NO metadata must still be an honest javascript_only
    failure — the fix must not manufacture evidence."""
    from intent_engine.company_ingestion.parsing import parse_html
    assert not parse_html(_EMPTY_SHELL)["text"].strip()

    def empty_shell_site(url, timeout):
        if "company_tickers.json" in url:
            return (200, {"content-type": "application/json"},
                    json.dumps({}).encode(), False)   # not an SEC filer
        if "hollow.example" in url:
            return (200, {"content-type": "text/html"},
                    _EMPTY_SHELL.encode(), False)
        raise _http_error(url, 404)

    ci = _service(tmp_path, transport=empty_shell_site)
    run_id = ci.create_run(company_name="Hollow Co",
                           website="https://hollow.example", user_id="u1",
                           as_of=AS_OF)["run_id"]
    cands = ci.discover(run_id)
    approved = [c["candidate_id"] for c in cands][:MAX_APPROVED_SOURCES]
    ci.approve(run_id, user_id="u1", approved_ids=approved, rejected_ids=[])
    fetched = ci.fetch_approved(run_id)
    assert not fetched["ok"], "no metadata → nothing may be salvaged"
    assert "javascript_only" in {f["failure_type"] for f in fetched["failed"]}


def test_sec_legal_boilerplate_never_becomes_customer_language(tmp_path):
    """REGRESSION for the 2026-07 report-quality incident: SEC filing text must
    never surface as the company's emphasized customer/market language, and
    procedural vocabulary must never appear as a business insight."""
    from intent_engine.company_ingestion.claims import build_claims
    filing = {
        "source_id": "src-sec-1", "source_type": "external_approved",
        "source_class": "investor_material", "retrieval_status": "OK",
        "title": "SEC 8-K", "meta_description": "", "content_hash": "a" * 64,
        "retrieved_at": AS_OF, "parser_version": "v1", "freshness": "CURRENT",
        "text_content": ("Pursuant to the requirements of the Securities "
                         "Exchange Act of 1934, the registrant has duly caused "
                         "this report to be signed on its behalf by the "
                         "undersigned hereunto duly authorized. Item 2.02 "
                         "Results of Operations. Exhibit 99.1 furnished "
                         "herewith pursuant to Rule 13a-15."),
    }
    claims = build_claims(documents=[filing], company_name="Palantir",
                          domain="palantir.com")
    flat = " ".join(c.text for group in claims.values()
                    if isinstance(group, list) for c in group).lower()
    # the filing is acknowledged as financial/regulatory disclosure ...
    assert "filing" in flat or "disclosure" in flat
    # ... but its procedural vocabulary is never presented as emphasis/insight
    for token in ("pursuant", "hereunder", "registrant", "undersigned",
                  "exchange act"):
        assert f'"{token}"' not in flat, f"legal token {token} surfaced as insight"
    assert "customer language" not in flat  # filings are not customer voice


def test_all_sources_unavailable_still_fails_honestly(tmp_path):
    """Section 14.A: when nothing — not even SEC — is retrievable, the run
    still fails honestly rather than inventing a result."""
    def all_403(url, timeout):
        if "company_tickers.json" in url:
            return (200, {"content-type": "application/json"},
                    json.dumps({}).encode(), False)   # not an SEC filer
        raise _http_error(url, 403)

    ci = _service(tmp_path, transport=all_403)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name="Ghost Co",
                           website="https://ghost.example", user_id="u1",
                           as_of=AS_OF)["run_id"]
    cands = ci.discover(run_id)
    approved = [c["candidate_id"] for c in cands][:MAX_APPROVED_SOURCES]
    ci.approve(run_id, user_id="u1", approved_ids=approved, rejected_ids=[])
    ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi)
    assert result["status"] == "FAILED"
    assert ci.store.run_state(run_id) == "FAILED"


# --- guest lifecycle pages stay styled (web layer) --------------------------

def _start_named(client, website, name):
    csrf = client.csrf()
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name={name}&website={website}")
    assert status.startswith("303"), status
    loc = headers["Location"]
    assert loc.endswith("/sources"), loc
    return loc.split("/runs/")[1].rsplit("/sources", 1)[0]


def _approve(app, client, run_id, cand_ids):
    body = ("csrf=" + client.csrf() + "&approve_consent=on&"
            + "&".join(f"cand={c}" for c in cand_ids))
    return client.request("POST", f"/runs/{run_id}/sources/approve", body)


def test_guest_lifecycle_pages_are_styled_and_run_completes(tmp_path):
    app = _make(tmp_path, transport=palantir_transport)
    c = _start_demo(app)
    run_id = _start_named(c, PALANTIR, "Palantir+Technologies")

    # Section 10 / 14.E: the source-review page carries the product stylesheet
    status, _, body = c.request("GET", f"/runs/{run_id}/sources")
    assert status == "200 OK"
    assert "<style" in body, "source page must be styled, not plain HTML"
    assert "Official filings" in body               # authoritative group shown
    assert 'id="cand-count"' in body                # live selection counter

    # approve the authoritative filings + the JS-only homepage + 403 page
    cands = app.ci.store.candidates(run_id)
    picked = [c2["candidate_id"] for c2 in cands
              if c2.get("source_class") == "investor_material"
              or c2["source_type"] in ("homepage", "about")]
    status, headers, _ = _approve(app, c, run_id, picked)
    assert status.startswith("303") and headers["Location"].endswith(
        "/progress")
    assert app.ci.store.run_state(run_id) in ("PARTIAL", "COMPLETE")

    # progress + result pages are styled too
    for path in (f"/runs/{run_id}/progress", f"/runs/{run_id}"):
        status, _, body = c.request("GET", path)
        assert status == "200 OK", (path, status)
        assert "<style" in body, f"{path} must be styled"


def test_autorun_skips_source_page_and_completes_palantir(tmp_path):
    """With auto-run ON (the production default), submitting the analyze form
    goes straight to the result — no source-review page — and Palantir still
    completes via the SEC EDGAR fallback."""
    app = _make(tmp_path, transport=palantir_transport, autorun_sources=True)
    c = _start_demo(app)
    csrf = c.csrf()
    status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Palantir+Technologies"
        f"&website={PALANTIR}")
    assert status.startswith("303")
    loc = headers["Location"]
    assert "/sources" not in loc                    # the 2nd page never appears
    assert loc.endswith("/progress")                # lands on styled progress
    run_id = loc.split("/runs/")[1].split("/")[0]
    # the run already ran to a terminal, openable, styled result. Either
    # terminal success is acceptable: COMPLETE when every approved source was
    # usable, PARTIAL when some failed but the quorum still held.
    assert app.ci.store.run_state(run_id) in ("COMPLETE", "PARTIAL")
    docs = app.ci.store.retrieved(run_id)
    assert any(d.get("source_class") == "investor_material" for d in docs)
    status, _, body = c.request("GET", f"/runs/{run_id}")
    assert status == "200 OK" and "<style" in body
    # visiting the (now-internal) source route just forwards to the finished run
    status, headers, _ = c.request("GET", f"/runs/{run_id}/sources")
    assert status.startswith("303")                 # approval exists → redirect


def test_double_submit_creates_exactly_one_run(tmp_path):
    """A2: a double-clicked / duplicate Analyze submit must not create a
    second analysis run (deterministic run id + idempotent machinery)."""
    app = _make(tmp_path, transport=palantir_transport, autorun_sources=True)
    c = _start_demo(app)

    def submit():
        csrf = c.csrf()
        return c.request(
            "POST", "/analyze",
            f"consent=on&csrf={csrf}&company_name=Palantir+Technologies"
            f"&website={PALANTIR}")

    st1, hd1, _ = submit()
    st2, hd2, _ = submit()                              # the "double click"
    assert st1.startswith("303") and st2.startswith("303")
    rid1 = hd1["Location"].split("/runs/")[1].split("/")[0]
    rid2 = hd2["Location"].split("/runs/")[1].split("/")[0]
    assert rid1 == rid2                                 # same deterministic run
    assert app.ci.store.run_ids() == [rid1]            # exactly ONE run exists
    ids = [r["source_id"] for r in app.ci.store.retrieved(rid1)]
    assert len(ids) == len(set(ids))                   # no duplicated evidence


def test_progress_page_terminal_styled_stops_refresh(tmp_path):
    """A2/A5/A6: auto-run lands on a styled progress page carrying the product
    shell; a terminal run shows the result link and stops auto-refreshing."""
    app = _make(tmp_path, transport=palantir_transport, autorun_sources=True)
    c = _start_demo(app)
    csrf = c.csrf()
    _, hd, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Palantir+Technologies"
        f"&website={PALANTIR}")
    loc = hd["Location"]
    assert loc.endswith("/progress")
    st, _, body = c.request("GET", loc)
    assert st == "200 OK"
    assert "<style" in body and "<nav" in body         # styled product shell
    assert "Open the result" in body                   # terminal → result link
    assert "http-equiv=\"refresh\"" not in body        # terminal → refresh off


def test_failed_guest_page_is_styled(tmp_path):
    """Even the honest-failure page must be styled (the incident screenshot
    showed it as plain HTML)."""
    def all_403(url, timeout):
        raise _http_error(url, 403)

    app = _make(tmp_path, transport=all_403)
    c = _start_demo(app)
    run_id = _start_named(c, "https://blocked.example", "Blocked+Co")
    cands = app.ci.store.candidates(run_id)
    picked = [c2["candidate_id"] for c2 in cands][:MAX_APPROVED_SOURCES]
    _approve(app, c, run_id, picked)
    assert app.ci.store.run_state(run_id) == "FAILED"
    status, _, body = c.request("GET", f"/runs/{run_id}")
    assert status == "200 OK"
    assert "<style" in body
    assert "could not be completed" in body

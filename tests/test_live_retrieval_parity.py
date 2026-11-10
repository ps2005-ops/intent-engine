"""Regressions for the gap between the fixture suite and the live deployment.

The existing golden fixtures are hand-written pages that serve their content
the way the parser already reads it, so they proved the pipeline worked while
the deployed service produced a materially worse report from the same code.
These tests model what the live sites ACTUALLY serve, measured 2026-07-27:

  * palantir.com is a Next.js Pages Router site. It answers 200 with ~700 KB
    and an EMPTY <body> — every word of copy lives in the server-rendered
    <script id="__NEXT_DATA__" type="application/json"> payload. The parser
    skipped script tags, so a 692 KB page was admitted as 120 characters of
    og:description and the report never mentioned Foundry.

  * sony.com answers 403 to every request including its own robots.txt, while
    its SEC filings serve plain HTML — and selection ranked the unreachable
    pages first, so the run admitted nothing at all.

Nothing here reaches the network.
"""
import email
import io
import re
import urllib.error

import pytest

from intent_engine.company_ingestion.parsing import parse_html
from intent_engine.company_ingestion.records import MAX_APPROVED_SOURCES
from intent_engine.company_ingestion.retry import plan_retry
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.storage_state import record_boot

AS_OF = "2026-07-27T00:00:00+00:00"


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "err",
                                  email.message_from_string(""), None)


# --- parsing: server-rendered page state --------------------------------------
def _next_data_page(title, description, prose):
    """A Next.js Pages Router response, shaped like palantir.com's."""
    import json
    payload = json.dumps({
        "props": {"pageProps": {"page": {
            "sections": [{"heading": h, "body": b} for h, b in prose],
            "assetUrl": "https://cdn.example.com/img/hero-2x.png",
            "id": "a7f3c9d2e1b8", "slug": "platforms-foundry",
            "alt": "Picture of water with a logo",
        }}},
        "buildId": "3QNJqLvJcLxmZUhulkUqK",
    })
    return (f'<html><head><title>{title}</title>'
            f'<meta property="og:title" content="{title}">'
            f'<meta property="og:description" content="{description}">'
            f'</head><body><div id="__next"></div>'
            f'<script id="__NEXT_DATA__" type="application/json">{payload}'
            f'</script></body></html>')


PROSE = [
    ("The Ontology-Powered Operating System for the Modern Enterprise",
     "The Foundry Ontology is the heart of Palantir Foundry. It integrates "
     "the semantic, kinetic and dynamic elements of your business."),
    ("Built for government and commercial operators alike",
     "Gotham has surfaced insights from complex data for global defense "
     "agencies, the intelligence community and disaster relief organizations."),
]


def test_next_data_page_yields_real_text_not_a_meta_description():
    html = _next_data_page("Palantir Foundry", "Run your business as code.",
                           PROSE)
    parsed = parse_html(html)
    assert parsed["extraction_mode"] == "structured"
    # The failure this replaces admitted ~120 characters of og:description
    # from a 692 KB response. Anything in this range is real page copy.
    assert len(parsed["text"]) > 300, parsed["text"]
    lowered = parsed["text"].lower()
    for term in ("foundry", "ontology", "gotham", "government", "defense"):
        assert term in lowered, f"{term!r} lost from a page that served it"


def test_page_state_extraction_drops_identifiers_and_asset_labels():
    parsed = parse_html(_next_data_page("T", "d", PROSE))
    text = parsed["text"]
    for noise in ("a7f3c9d2e1b8", "platforms-foundry", "hero-2x.png",
                  "3QNJqLvJcLxmZUhulkUqK", "Picture of water"):
        assert noise not in text, f"{noise!r} is not evidence"


def test_a_page_that_serves_real_html_is_untouched():
    """The structured path must not fire on, or pollute, an ordinary page."""
    html = ("<html><head><title>About</title></head><body>"
            + "".join(f"<p>Sentence number {i} explaining the company in "
                      f"enough words to count as a block of prose.</p>"
                      for i in range(12))
            + "</body></html>")
    parsed = parse_html(html)
    assert parsed["extraction_mode"] == "body"
    assert "Sentence number 11" in parsed["text"]


def test_metadata_salvage_still_covers_a_page_with_nothing_else():
    html = ('<html><head><title>Acme</title>'
            '<meta name="description" content="Acme builds industrial robots.">'
            '</head><body><div id="root"></div></body></html>')
    parsed = parse_html(html)
    assert parsed["extraction_mode"] == "metadata"
    assert "industrial robots" in parsed["text"]


# --- the record carries WHERE the text came from ------------------------------
class _StateSite:
    HTML = {"content-type": "text/html"}

    def transport(self):
        def _tx(url, timeout):
            bare = url.split("#")[0].rstrip("/")
            if bare.endswith("/robots.txt") or bare.endswith("/sitemap.xml"):
                raise _http_error(url, 404)
            return (200, self.HTML,
                    _next_data_page("Acme", "Acme builds robots.",
                                    PROSE).encode(), False)
        return _tx


def test_retrieved_records_state_where_the_text_came_from(tmp_path):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=_StateSite().transport(),
                                 resolver=False)
    run = ci.create_run(company_name="Acme", website="https://acme.example",
                        user_id="u", as_of=AS_OF)
    candidates = ci.discover(run["run_id"])
    picked = [c["candidate_id"] for c in candidates[:2]]
    ci.approve(run["run_id"], user_id="u", approved_ids=picked,
               rejected_ids=[])
    ci.fetch_approved(run["run_id"])
    documents = ci.store.retrieved(run["run_id"])
    assert documents
    for document in documents:
        assert document["extraction_mode"] == "structured"
        assert document["blocks_found"] > 0


# --- selection: relevance, then reachability ----------------------------------
def _candidate(cid, url, source_type="product", method="known_path",
               why="", source_class="company_owned"):
    return {"candidate_id": cid, "url": url, "source_type": source_type,
            "discovery_method": method, "why_relevant": why,
            "source_class": source_class}


def test_curated_source_outranks_a_sitemap_url_and_a_guess():
    candidates = [
        _candidate("c-guess", "https://x.example/docs"),
        _candidate("c-sitemap", "https://x.example/blog",
                   why="listed in the company's own sitemap"),
        _candidate("c-curated", "https://x.example/platforms/foundry/",
                   method="official_fallback",
                   why="published by X itself; official segment source"),
    ]
    picked = WebApp._recommended_candidate_ids(candidates)
    assert picked[0] == "c-curated", picked


def test_a_guess_at_a_host_already_refusing_us_is_not_tried_at_all():
    """Ranking it last was not enough: the leftover fill spent the slot.

    This asserted an ORDER until the 50-company gauntlet measured what that
    order cost -- Goldman Sachs made 26 fetch failures, 24 of them at
    goldmansachs.com, every one after the homepage had already answered 403.
    The regulatory source still gets its slot; the certain failure does not.
    """
    candidates = [
        _candidate("c-guess", "https://blocked.example/products"),
        _candidate("c-edgar", "https://www.sec.gov/Archives/edgar/x.htm",
                   source_type="external_approved", method="external_proposed",
                   why="official 6-K filing from SEC EDGAR — audited",
                   source_class="investor_material"),
    ]
    picked = WebApp._recommended_candidate_ids(
        candidates, refusing_hosts={"blocked.example"})
    assert "c-guess" not in picked, picked
    assert "c-edgar" in picked, picked


def test_a_curated_source_is_still_tried_on_a_refusing_host():
    """One 403 on a homepage is not proof that every path is shut. A
    hand-verified URL keeps its rank; only guesses are demoted."""
    candidates = [
        _candidate("c-curated", "https://blocked.example/ir/",
                   method="official_fallback", why="official investor source"),
        _candidate("c-guess", "https://blocked.example/products"),
    ]
    picked = WebApp._recommended_candidate_ids(
        candidates, refusing_hosts={"blocked.example"})
    assert picked[0] == "c-curated", picked


def test_product_family_can_hold_the_platforms_and_the_segments():
    """A company with three platforms and two market segments needs more than
    one product slot — the cap that starved Palantir of Foundry."""
    candidates = [
        _candidate(f"c-{name}", f"https://x.example/platforms/{name}/",
                   method="official_fallback", why="official segment source")
        for name in ("foundry", "gotham", "aip", "government", "commercial")
    ]
    picked = WebApp._recommended_candidate_ids(candidates)
    assert len(picked) == 5, picked
    assert len(picked) <= MAX_APPROVED_SOURCES


# --- retry: spend the budget where it can succeed -----------------------------
def test_retry_prefers_a_family_it_can_actually_reach():
    candidates = [
        _candidate("c-id", "https://blocked.example/about",
                   source_type="about"),
        _candidate("c-prod", "https://blocked.example/product"),
        _candidate("c-cust", "https://blocked.example/customers",
                   source_type="customers"),
        _candidate("c-edgar", "https://www.sec.gov/Archives/edgar/y.htm",
                   source_type="external_approved", method="external_proposed",
                   why="official 6-K filing from SEC EDGAR",
                   source_class="investor_material"),
    ]
    chosen = plan_retry(
        missing_families=["identity", "product", "customers", "investor"],
        candidates=candidates, already_approved=set(), failed_urls=set(),
        refusing_hosts={"blocked.example"}, limit=2)
    assert "c-edgar" in chosen, chosen


def test_retry_without_a_refusing_host_is_unchanged():
    candidates = [
        _candidate("c-prod", "https://ok.example/product"),
        _candidate("c-edgar", "https://www.sec.gov/Archives/edgar/z.htm",
                   source_type="external_approved", method="external_proposed",
                   why="official filing from SEC EDGAR",
                   source_class="investor_material"),
    ]
    chosen = plan_retry(missing_families=["product", "investor"],
                        candidates=candidates, already_approved=set(),
                        failed_urls=set(), limit=1)
    assert chosen == ["c-prod"], chosen


# --- one bad source must never cost the whole run -----------------------------
class _SiteWithOneCredentialLookalike:
    HTML = {"content-type": "text/html"}

    def transport(self):
        def _tx(url, timeout):
            bare = url.split("#")[0].rstrip("/")
            if bare.endswith("/robots.txt") or bare.endswith("/sitemap.xml"):
                raise _http_error(url, 404)
            if bare.endswith("/about"):
                # A public filing index: commission file numbers concatenate
                # into something the card-number heuristic matches.
                return (200, self.HTML,
                        b"<html><body><p>Commission File Number "
                        b"06439261100329 for the registrant named "
                        b"herein.</p></body></html>", False)
            return (200, self.HTML,
                    b"<html><head><title>Acme</title></head><body>"
                    b"<p>Acme builds industrial robots for factories across "
                    b"Europe and sells them to manufacturers.</p>"
                    b"</body></html>", False)
        return _tx


def test_a_credential_lookalike_costs_one_source_not_the_run(tmp_path):
    ci = CompanyIngestionService(
        tmp_path / "ci.jsonl",
        transport=_SiteWithOneCredentialLookalike().transport(),
        resolver=False)
    run = ci.create_run(company_name="Acme", website="https://acme.example",
                        user_id="u", as_of=AS_OF)
    candidates = ci.discover(run["run_id"])
    about = [c for c in candidates if c["url"].endswith("/about")]
    assert about, "fixture must offer the offending page"
    picked = [about[0]["candidate_id"]] + [
        c["candidate_id"] for c in candidates
        if not c["url"].endswith("/about")][:3]
    ci.approve(run["run_id"], user_id="u", approved_ids=picked,
               rejected_ids=[])
    outcome = ci.fetch_approved(run["run_id"])     # must not raise
    assert outcome["ok"], "the run kept nothing after one bad source"
    rejected = [f for f in outcome["failed"]
                if f["failure_type"] == "content_rejected"]
    assert rejected, outcome["failed"]


# --- the limited-evidence page a reader actually sees -------------------------
class _BlockedEverywhere:
    """Every company page refuses; only SEC filings serve."""

    HTML = {"content-type": "text/html"}
    JSON = {"content-type": "application/json"}

    def transport(self):
        def _tx(url, timeout):
            if "data.sec.gov" in url or "sec.gov/files" in url:
                raise _http_error(url, 404)
            if url.startswith("https://blocked.example"):
                raise _http_error(url, 403)
            raise _http_error(url, 404)
        return _tx


@pytest.fixture
def blocked_app(tmp_path):
    record_boot(tmp_path, boot_id="previous-process-boot")
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       autorun_sources=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(config, transport=_BlockedEverywhere().transport(),
                 resolver=False)
    return app


class _Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie" and value.startswith("sid="):
                self.cookie = ("" if "Max-Age=0" in value
                               else value.split(";")[0])
        return out["status"], dict(out["headers"]), payload

    def get(self, path, hops=5):
        status, headers, body = "", {}, ""
        for _ in range(hops):
            status, headers, body = self.request("GET", path)
            if not status.startswith("30") or "Location" not in headers:
                break
            path = headers["Location"]
        return status, body

    def csrf(self):
        sid = self.cookie.split("=", 1)[1] if self.cookie else None
        return self.app.auth.csrf_token(sid)


def test_a_fully_blocked_company_never_shows_internal_ids_or_tuples(
        blocked_app):
    client = _Client(blocked_app)
    client.request("POST", "/demo")
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name=Blocked"
        f"&website=https://blocked.example")
    assert not status.startswith("5"), status
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    _status, html = client.get(f"/runs/{run_id}")

    # The defect: the failure list was interpolated as a Python object, so the
    # reader saw tuple syntax and opaque candidate ids.
    assert "cand-" not in html, "internal candidate id shown to the reader"
    assert not re.search(r"\[\(&#x27;|\[\('", html), "raw tuple rendered"
    assert "', '" not in html, "raw tuple rendered"


# --- synthesis: the thesis a reader actually reads ----------------------------
def test_every_hypothesis_title_reads_as_a_sentence_after_appears_to_be():
    """`_view` renders "{company} appears to be {title}". Four of the six
    scaffolds were full clauses, so the most prominent sentence in the brief
    came out as "Palantir Technologies appears to be product breadth is
    building a controlled ecosystem"."""
    from intent_engine.strategic_intelligence.patterns import (
        HYPOTHESIS_SCAFFOLDS,
    )
    for key, scaffold in HYPOTHESIS_SCAFFOLDS.items():
        title = scaffold["title"]
        assert "\n" not in title, f"{key}: title contains a newline"
        rendered = f"Acme appears to be {title[0].lower()}{title[1:]}."
        # The slot after "appears to be" takes a complement, not a clause. A
        # clause is betrayed by its own finite verb, which lands the sentence
        # with two predicates and no grammar between them.
        lowered = f" {title.lower()} "
        for finite_verb in (" is ", " are ", " was ", " were ", " implies ",
                            " may be ", " has ", " have "):
            assert finite_verb not in lowered, (
                f"{key}: title is a clause, not a complement — "
                f"{rendered!r}")


def test_signal_labels_never_assert_an_industry():
    """The detectors key off generic words ("infrastructure", "enterprise",
    "identity", "ecosystem"), so their labels must not name a market. Saying
    Palantir "positions itself as commerce infrastructure" was confident,
    prominent and false."""
    from intent_engine.strategic_intelligence.observations import (
        _SIGNAL_LABEL,
    )
    forbidden = ("commerce", "merchant", "storefront", "shopper", "retail")
    for signal, label in _SIGNAL_LABEL.items():
        lowered = label.lower()
        for word in forbidden:
            assert word not in lowered, (
                f"{signal}: label {label!r} asserts an industry")

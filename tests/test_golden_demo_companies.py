"""Golden-demo regressions — permanent protection for the executive report.

These pin the quality bar that the 2026-07 incident broke: for a major public
company the default guest flow must produce a report that explains what the
company does, rests on several independent evidence families, and never
presents legal boilerplate as insight.

Every company here is a deterministic offline fixture — no network. Each site
models what these companies actually serve: a JavaScript-rendered marketing
shell (with real server-rendered metadata), some pages that refuse automated
access, a sitemap listing real URLs, and SEC filings whose business content
lives in an exhibit rather than the procedural cover page.
"""
import email
import json
import urllib.error

import pytest

from intent_engine.company_ingestion.coverage import (
    EVIDENCE_REPORT_READY, assess,
)
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService
from intent_engine.webapp.app import WebApp

AS_OF = "2026-07-27T00:00:00+00:00"

# Vocabulary that must never be presented as a business insight.
LEGAL_TOKENS = ("pursuant", "hereunder", "registrant", "undersigned",
                "exchange act", "incorporated by reference")


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "err",
                                  email.message_from_string(""), None)


class GoldenCompany:
    """A deterministic fixture site for one golden company."""

    def __init__(self, name, domain, description, products, customer_text,
                 cik=None, ticker=None):
        self.name = name
        self.domain = domain
        self.base = f"https://{domain}"
        self.description = description
        self.products = products
        self.customer_text = customer_text
        self.cik = cik
        self.ticker = ticker

    # -- page bodies --------------------------------------------------------
    def js_shell(self):
        """JS-rendered homepage: no body text, but real metadata (as served)."""
        return (
            f'<html><head><title>{self.name}</title>'
            f'<meta property="og:title" content="{self.name}">'
            f'<meta property="og:description" content="{self.description}">'
            f'<script type="application/ld+json">'
            f'{{"@type":"Organization","name":"{self.name}",'
            f'"description":"{self.description} Products include '
            f'{", ".join(self.products)}."}}</script></head>'
            f'<body><div id="root"></div><script>hydrate()</script></body>'
            f'</html>')

    def product_page(self):
        return (f'<html><head><title>{self.name} Products</title></head><body>'
                f'<h1>{" and ".join(self.products)}</h1>'
                f'<p>{self.description} {self.products[0]} is used by teams to '
                f'integrate data and run operational workflows.</p>'
                f'</body></html>')

    def customers_page(self):
        return (f'<html><head><title>{self.name} Customers</title></head>'
                f'<body><h2>Customer stories</h2><p>{self.customer_text}</p>'
                f'</body></html>')

    def sitemap(self):
        paths = ("/products", "/customers", "/about", "/blog", "/pricing")
        locs = "".join(f"<url><loc>{self.base}{p}</loc></url>" for p in paths)
        return f'<?xml version="1.0"?><urlset>{locs}</urlset>'

    def exhibit(self):
        return ('<html><body><h1>Quarterly Results</h1>'
                '<p>Revenue grew year over year, driven by commercial customer '
                'expansion and platform adoption. Operating margin improved as '
                'the customer base expanded.</p></body></html>')

    def cover_page(self):
        return ('<html><body><p>Pursuant to the requirements of the Securities '
                'Exchange Act of 1934, the registrant has duly caused this '
                'report to be signed by the undersigned hereunto duly '
                'authorized. Incorporated by reference.</p></body></html>')

    # -- transport ----------------------------------------------------------
    def transport(self):
        acc = "0001321655-26-000001"
        nodash = acc.replace("-", "")

        def _tx(url, timeout):
            bare = url.split("#")[0].rstrip("/")
            html = {"content-type": "text/html"}
            xml = {"content-type": "application/xml"}
            js = {"content-type": "application/json"}
            if bare in (self.base, f"https://www.{self.domain}"):
                return (200, html, self.js_shell().encode(), False)
            if bare.endswith("/robots.txt"):
                return (200, {"content-type": "text/plain"},
                        f"User-agent: *\nDisallow: /admin/\n"
                        f"Sitemap: {self.base}/sitemap.xml\n".encode(), False)
            if bare.endswith("/sitemap.xml"):
                return (200, xml, self.sitemap().encode(), False)
            if bare.endswith("/products"):
                return (200, html, self.product_page().encode(), False)
            if bare.endswith("/customers"):
                return (200, html, self.customers_page().encode(), False)
            if bare.endswith("/about"):
                return (200, html, self.js_shell().encode(), False)
            if bare.endswith("/pricing"):
                raise _http_error(url, 403)          # refuses automation
            if bare.endswith("/blog"):
                raise TimeoutError("timed out")      # transient failure
            if "company_tickers.json" in url:
                rows = ({} if self.cik is None else
                        {"0": {"cik_str": self.cik, "ticker": self.ticker,
                               "title": self.name}})
                return (200, js, json.dumps(rows).encode(), False)
            if "/submissions/CIK" in url:
                return (200, js, json.dumps({"filings": {"recent": {
                    "form": ["8-K"], "accessionNumber": [acc],
                    "primaryDocument": ["cover.htm"],
                    "filingDate": ["2026-05-05"]}}}).encode(), False)
            if url.endswith("index.json"):
                return (200, js, json.dumps({"directory": {"item": [
                    {"name": "cover.htm"},
                    {"name": "a2026q1ex991pressrelease.htm"}]}}).encode(),
                    False)
            if "ex991" in url:
                return (200, html, self.exhibit().encode(), False)
            if "cover.htm" in url:
                return (200, html, self.cover_page().encode(), False)
            raise _http_error(url, 404)
        return _tx


GOLDEN = [
    GoldenCompany(
        "Palantir Technologies", "palantir.com",
        "Palantir builds software platforms that help institutions integrate "
        "their data, decisions and operations.",
        ["Foundry", "Gotham", "AIP"],
        "Government and commercial customers use the platform for data "
        "integration, analytics and operational decision making.",
        cik=1321655, ticker="PLTR"),
    GoldenCompany(
        "Microsoft", "microsoft.com",
        "Microsoft builds cloud, productivity and AI platforms for "
        "organizations and developers worldwide.",
        ["Azure", "Microsoft 365", "Copilot"],
        "Enterprises adopt the cloud platform for infrastructure, "
        "collaboration and AI workloads.",
        cik=789019, ticker="MSFT"),
    GoldenCompany(
        "NVIDIA", "nvidia.com",
        "NVIDIA designs accelerated computing platforms for AI, graphics and "
        "data center workloads.",
        ["CUDA", "DGX", "Omniverse"],
        "Data centers and research teams use the accelerated computing "
        "platform to train and serve AI models.",
        cik=1045810, ticker="NVDA"),
    GoldenCompany(
        "Apple", "apple.com",
        "Apple designs consumer hardware, software and services including "
        "personal computing and mobile devices.",
        ["iPhone", "Mac", "iCloud"],
        "Customers and developers build on the platform and its services "
        "ecosystem.",
        cik=320193, ticker="AAPL"),
    GoldenCompany(
        "Shopify", "shopify.com",
        "Shopify provides commerce infrastructure that lets merchants sell "
        "online, in store and across channels.",
        ["Shopify Plus", "Shop Pay", "Storefront API"],
        "Merchants and enterprise brands run their storefronts, checkout and "
        "payments on the commerce platform.",
        cik=1594805, ticker="SHOP"),
    GoldenCompany(
        "Snowflake", "snowflake.com",
        "Snowflake operates a cloud data platform for analytics, data "
        "engineering and data sharing.",
        ["Data Cloud", "Snowpark", "Cortex"],
        "Enterprise data teams consolidate analytics and share governed data "
        "across organizations.",
        cik=1640147, ticker="SNOW"),
]


def _run(company, tmp_path):
    """Run the default guest path: discover -> recommended selection ->
    retrieve -> compose. Exactly what a guest gets, offline."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=company.transport(), resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name=company.name, website=company.base,
                           user_id="u1", as_of=AS_OF)["run_id"]
    candidates = ci.discover(run_id)
    approved = WebApp._recommended_candidate_ids(candidates)
    ci.approve(run_id, user_id="u1", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi)
    return ci, run_id, result


@pytest.mark.parametrize("company", GOLDEN, ids=lambda c: c.domain)
def test_golden_company_report_is_useful(company, tmp_path):
    """The permanent bar: a major public company must produce a grounded,
    multi-family report that explains what the company does."""
    ci, run_id, result = _run(company, tmp_path)
    documents = ci.store.retrieved(run_id)
    flat = str(result).lower()

    # 1. the run reaches a terminal success state with an openable result
    assert result["ingestion_status"] in ("COMPLETE", "PARTIAL")
    assert result["sections"], "a completed run must be openable"

    # 2. it can explain what the company does, in the company's own words
    assert any(word.lower() in flat
               for word in company.description.split()[:6]), \
        "the report must describe what the company does"

    # 3. product evidence is present — not just filings
    assert any(p.lower() in flat for p in company.products), \
        f"no product evidence for {company.name}"

    # 4. several independent evidence families, and SEC is not the only one
    coverage = result["coverage"]
    assert len(coverage["families"]) >= 3, coverage["family_counts"]
    assert coverage["families"] != ["investor"], \
        "SEC filings must never be the only successful source family"
    assert coverage["dominant_share"] <= 0.75, coverage

    # 5. legal boilerplate is never presented as an insight
    for token in LEGAL_TOKENS:
        assert f'"{token}"' not in flat, \
            f"legal boilerplate {token!r} surfaced as insight"

    # 6. the report is not mostly empty
    populated = [s for s in result["sections"] if s.get("cards")]
    assert len(populated) >= len(result["sections"]) * 0.4, (
        f"{len(populated)}/{len(result['sections'])} sections populated")

    # 7. no internal identifiers leak into the user-facing evidence library
    for entry in result["evidence_library"]["company_website"]:
        assert not str(entry.get("origin", "")).startswith("cand-")


@pytest.mark.parametrize("company", GOLDEN, ids=lambda c: c.domain)
def test_golden_company_meets_evidence_quorum(company, tmp_path):
    """Coverage must be semantically sufficient, not merely numerous."""
    ci, run_id, _result = _run(company, tmp_path)
    coverage = assess(ci.store.retrieved(run_id))
    assert coverage["state"] == EVIDENCE_REPORT_READY, coverage["reasons"]


def test_golden_failures_are_recorded_not_hidden(tmp_path):
    """Blocked and timed-out sources are honestly recorded while the run still
    succeeds through the remaining evidence."""
    company = GOLDEN[0]
    ci, run_id, result = _run(company, tmp_path)
    failures = ci.store.failures(run_id)
    assert failures, "refused/timed-out sources must be recorded"
    types = {f["failure_type"] for f in failures}
    assert types & {"http_status", "timeout", "connection"}
    assert result["ingestion_status"] == "PARTIAL"


def test_golden_sec_exhibit_is_preferred_over_cover_page(tmp_path):
    """The filing's business content (exhibit) must be what gets analysed."""
    company = GOLDEN[0]
    ci, run_id, _result = _run(company, tmp_path)
    filings = [d for d in ci.store.retrieved(run_id)
               if d.get("source_class") == "investor_material"]
    assert filings, "an SEC filing should be part of the evidence"
    text = " ".join(d["text_content"].lower() for d in filings)
    assert "revenue" in text or "margin" in text, \
        "the analysed filing should be the earnings exhibit, not the cover"
    assert "pursuant to the requirements" not in text

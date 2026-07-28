"""Sony end-to-end: a primary domain that refuses automated access.

`sony.com` answers HTTP 403 to automated clients. Before this, that single fact
was enough to reduce a Japanese multinational to whatever one SEC document
remained reachable. These tests drive the real pipeline against a fixture that
behaves the way sony.com actually behaves, and assert the two properties that
matter: the run still knows WHO it is about, and it still reaches official
material across several kinds of evidence.
"""
import email
import urllib.error

import pytest

from intent_engine.company_ingestion.coverage import assess
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService
from intent_engine.webapp.app import WebApp

AS_OF = "2026-07-27T00:00:00+00:00"


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "Forbidden",
                                  email.message_from_string(""), None)


class BlockedMultinational:
    """sony.com as it really responds: 403 to the homepage, robots.txt and
    sitemap — but the curated official IR/report/newsroom URLs serve content."""

    HTML = {"content-type": "text/html"}

    def _page(self, title, body):
        return (f"<html><head><title>{title}</title></head>"
                f"<body><main>{body}</main></body></html>").encode()

    def transport(self):
        def _tx(url, timeout):
            bare = url.split("#")[0].rstrip("/")
            # Everything on the bare corporate domain refuses automation.
            if bare in ("https://www.sony.com", "https://sony.com"):
                raise _http_error(url, 403)
            if bare.endswith("/robots.txt") or bare.endswith("/sitemap.xml"):
                raise _http_error(url, 403)
            if "/SonyInfo/CorporateInfo/Data" in bare:
                return (200, self.HTML, self._page(
                    "Sony Group — business segments",
                    "<p>Sony Group Corporation reports six segments: Game &amp; "
                    "Network Services, Music, Pictures, Entertainment, "
                    "Technology &amp; Services, Imaging &amp; Sensing "
                    "Solutions, and Financial Services.</p>"), False)
            if "/SonyInfo/CorporateInfo" in bare:
                return (200, self.HTML, self._page(
                    "Sony Group — corporate information",
                    "<p>Sony Group Corporation is a Japanese diversified "
                    "technology and entertainment company headquartered in "
                    "Tokyo, operating across games, music, pictures, imaging "
                    "sensors and financial services.</p>"), False)
            if "/SonyInfo/IR/library/presen/er" in bare:
                return (200, self.HTML, self._page(
                    "Sony Group — earnings release",
                    "<p>Consolidated results for the quarter ended June 2026. "
                    "Game &amp; Network Services sales rose on higher "
                    "PlayStation 5 software and network services revenue.</p>"),
                    False)
            if "/SonyInfo/IR/library/report" in bare:
                return (200, self.HTML, self._page(
                    "Sony Group — integrated report",
                    "<p>Our long-term strategy centres on creative "
                    "entertainment supported by imaging and sensing "
                    "technology.</p>"), False)
            if "/SonyInfo/IR" in bare:
                return (200, self.HTML, self._page(
                    "Sony Group — investor relations",
                    "<p>Investor relations for Sony Group Corporation, listed "
                    "on the Tokyo Stock Exchange (6758) and, through American "
                    "Depositary Receipts, the New York Stock Exchange "
                    "(SONY).</p>"), False)
            if "/SonyInfo/News" in bare:
                return (200, self.HTML, self._page(
                    "Sony Group — newsroom",
                    "<p>Sony Group Corporation announced an expansion of its "
                    "image sensor manufacturing capacity.</p>"), False)
            if "/SonyInfo/csr/library" in bare:
                return (200, self.HTML, self._page(
                    "Sony Group — sustainability reporting",
                    "<p>Sustainability and governance reporting for the "
                    "group.</p>"), False)
            if "sec.gov" in bare:
                return (200, self.HTML, self._page(
                    "SEC EDGAR — Sony Group 20-F",
                    "<p>Annual report on Form 20-F for Sony Group "
                    "Corporation.</p>"), False)
            raise _http_error(url, 403)
        return _tx


@pytest.fixture
def sony(tmp_path):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=BlockedMultinational().transport(),
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name="Sony Group Corporation",
                           website="https://www.sony.com", user_id="u1",
                           as_of=AS_OF)["run_id"]
    return ci, fi, run_id


def _drive(ci, fi, run_id):
    candidates = ci.discover(run_id)
    approved = WebApp._recommended_candidate_ids(candidates)
    ci.approve(run_id, user_id="u1", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    ci.fetch_approved(run_id)
    return candidates, ci.compose(run_id, fi_service=fi)


def test_identity_survives_a_completely_blocked_primary_domain(sony):
    ci, fi, run_id = sony
    ci.discover(run_id)
    identity = ci.entity_identity(run_id)
    assert identity["entity_resolved"] is True
    assert identity["canonical_legal_name"] == "Sony Group Corporation"
    assert identity["country"] == "Japan"
    assert identity["common_name"] == "Sony"
    # identity is asserted, not inferred from whatever document arrived
    assert identity["primary_domain"] == "sony.com"
    assert identity["sec_cik"]


def test_blocked_domain_still_reaches_official_sources(sony):
    ci, fi, run_id = sony
    candidates, _ = _drive(ci, fi, run_id)
    fallback = [c for c in candidates
                if c["discovery_method"] == "official_fallback"]
    assert len(fallback) >= 5, "a 403 homepage must not end the run"
    # every one is classified before it is used
    assert all(c.get("authority") for c in fallback)
    assert all(c.get("entity_relationship") for c in fallback)


def test_sony_is_not_reduced_to_a_single_filing(sony):
    ci, fi, run_id = sony
    _drive(ci, fi, run_id)
    documents = ci.store.retrieved(run_id)
    ok = [d for d in documents if d.get("retrieval_status") == "OK"]
    assert len(ok) >= 4, "one filing is not a view of a multinational"

    coverage = assess(documents)
    assert len(coverage["families"]) >= 3, coverage["family_counts"]
    # and no single family — least of all filings — may carry the whole report
    assert coverage["dominant_share"] <= 0.75, coverage


def test_retrieved_evidence_describes_the_group_not_one_subsidiary(sony):
    ci, fi, run_id = sony
    _drive(ci, fi, run_id)
    text = " ".join((d.get("text_content") or "")
                    for d in ci.store.retrieved(run_id)).lower()
    assert "sony group corporation" in text
    # the multinational context the one-filing report entirely lacked
    assert "tokyo" in text
    assert "segment" in text


def test_official_fallback_urls_are_attributed_to_sony_group(sony):
    ci, fi, run_id = sony
    candidates, _ = _drive(ci, fi, run_id)
    for candidate in candidates:
        if candidate["discovery_method"] != "official_fallback":
            continue
        assert candidate["entity_id"] == "sony-group"
        assert candidate["why_relevant"].strip()

"""Report-quality gate and targeted rediscovery loop.

Retrieval succeeding is not the same as the report being useful. These tests
pin the gate's outcomes, the bounded retry that goes looking for the missing
evidence family, and the guarantees that keep it honest: nothing is invented,
no failed URL is retried, no second report run is minted, and a report that is
still short of the bar is published as explicitly LIMITED.
"""
import pathlib
import tempfile

import pytest

from test_golden_demo_companies import GOLDEN, _http_error
from intent_engine.company_ingestion.quality import (
    REPORT_QUALITY_FAIL, REPORT_QUALITY_LIMITED, REPORT_QUALITY_PASS,
    REPORT_QUALITY_RETRYABLE, assess, downgrade_to_limited, evidence_gaps,
    is_meaningfully_populated, user_visible_text,
)
from intent_engine.company_ingestion.retry import (
    MAX_NEW_SOURCES_PER_PASS, plan_retry,
)
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService

AS_OF = "2026-07-27T00:00:00+00:00"


def _doc(sid, source_type, source_class="company_owned", text="real business "
         "content describing the platform and how customers use it"):
    return {"source_id": sid, "source_type": source_type,
            "source_class": source_class, "retrieval_status": "OK",
            "title": sid, "meta_description": "", "content_hash": "a" * 64,
            "retrieved_at": AS_OF, "parser_version": "v1",
            "freshness": "CURRENT", "text_content": text}


def _section(kind, *claim_texts, note=""):
    cards = [{"headline": t, "claims": [{"text": t}]} for t in claim_texts]
    return {"kind": kind, "title": kind, "cards": cards, "note": note}


# --- section population -----------------------------------------------------

def test_placeholder_section_is_not_meaningfully_populated():
    assert not is_meaningfully_populated(
        _section("market_view", "Not available — no supported evidence"))
    assert not is_meaningfully_populated({"kind": "market_view", "cards": []})
    assert not is_meaningfully_populated(
        _section("company_understanding", "Evidence scope: 3 company page(s)"))
    assert is_meaningfully_populated(
        _section("market_view", "The company positions itself for regulated "
                                "government and commercial buyers"))


def test_user_visible_text_excludes_internal_plumbing():
    result = {"overview": [{"text": "visible overview"}],
              "sections": [_section("market_view", "visible claim")],
              "internal_refs": [{"subsystem": "company_ingestion"}]}
    visible = user_visible_text(result)
    assert "visible overview" in visible and "visible claim" in visible
    assert "company_ingestion" not in visible


# --- gate outcomes ----------------------------------------------------------

def _rich_result():
    return {
        "overview": [{"text": 'What the company appears to sell (directly '
                              'observed): "a data platform"'}],
        "sections": [
            _section("company_understanding", "identity and offering"),
            _section("what_stood_out", "a specific observation"),
            _section("market_view", "positioning versus alternatives"),
            _section("possible_blind_spots", "a tension worth checking"),
            _section("assumptions_to_investigate", "an assumption"),
            _section("executive_attention", "an attention area"),
            _section("executive_confidence", "confidence summary"),
            _section("what_we_do_not_believe_yet", "an unsupported narrative"),
            _section("leadership_questions", "a question for the team"),
            _section("competitors", "a supported comparison"),
            _section("opportunities", "an opportunity hypothesis"),
        ],
        "evidence_library": {"company_website": []},
    }


def _rich_documents():
    return [_doc("s1", "homepage"), _doc("s2", "product"),
            _doc("s3", "customers"),
            _doc("s4", "external_approved", "investor_material"),
            _doc("s5", "blog", "executive_statement")]


def test_quality_passes_on_a_broadly_evidenced_report():
    result = assess(_rich_result(), _rich_documents())
    assert result["outcome"] == REPORT_QUALITY_PASS, result["failed_rules"]
    assert result["metrics"]["has_product_evidence"]
    assert result["metrics"]["has_customer_evidence"]


def test_quality_retryable_when_a_family_is_missing():
    docs = [_doc("s1", "homepage"),
            _doc("s2", "external_approved", "investor_material")]
    result = assess(_rich_result(), docs)
    assert result["outcome"] == REPORT_QUALITY_RETRYABLE
    assert any("product" in r for r in result["retryable_rules"])
    assert "product" in result["missing_families"]


def test_quality_retryable_when_sections_are_placeholders():
    thin = dict(_rich_result(), sections=[
        _section("company_understanding", "identity"),
        _section("what_stood_out", "Not available"),
        _section("market_view", "Not available"),
        _section("possible_blind_spots", "Not available"),
        _section("assumptions_to_investigate", "Not available"),
        _section("executive_attention", "Not available"),
    ])
    result = assess(thin, _rich_documents())
    assert result["outcome"] == REPORT_QUALITY_RETRYABLE
    assert any("placeholder" in r for r in result["retryable_rules"])


def test_quality_hard_fails_on_legal_boilerplate_as_insight():
    bad = dict(_rich_result(), sections=[
        _section("market_view", 'Evidence emphasizes: "pursuant", "registrant"')
    ] + _rich_result()["sections"])
    result = assess(bad, _rich_documents())
    assert result["outcome"] == REPORT_QUALITY_FAIL
    assert any("legal boilerplate" in r for r in result["hard_rules"])


def test_quality_hard_fails_on_opaque_ids_and_internal_terms():
    bad = dict(_rich_result(), sections=[
        _section("market_view", "cand-ab12cd34ef56 could not be retrieved"),
    ])
    assert assess(bad, _rich_documents())["outcome"] == REPORT_QUALITY_FAIL

    leaky = dict(_rich_result(), sections=[
        _section("market_view", "no subsystem reports this yet"),
    ])
    assert assess(leaky, _rich_documents())["outcome"] == REPORT_QUALITY_FAIL


def test_limited_downgrade_never_upgrades_a_hard_failure():
    hard = {"outcome": REPORT_QUALITY_FAIL}
    assert downgrade_to_limited(hard)["outcome"] == REPORT_QUALITY_FAIL
    retry = {"outcome": REPORT_QUALITY_RETRYABLE}
    assert downgrade_to_limited(retry)["outcome"] == REPORT_QUALITY_LIMITED


# --- evidence gaps / retry planning -----------------------------------------

def test_evidence_gaps_identify_missing_families():
    gaps = evidence_gaps([_doc("s1", "external_approved",
                               "investor_material")])
    assert not gaps["sufficient"]
    assert {"identity", "product", "customers"} <= set(gaps["missing_families"])


def test_evidence_gaps_sufficient_on_diverse_evidence():
    assert evidence_gaps(_rich_documents())["sufficient"]


def test_retry_plan_targets_the_missing_family():
    candidates = [
        {"candidate_id": "c1", "url": "https://x.com/products",
         "source_type": "product", "source_class": "company_owned",
         "why_relevant": "listed in the company's own sitemap"},
        {"candidate_id": "c2", "url": "https://x.com/careers",
         "source_type": "careers", "source_class": "company_owned",
         "why_relevant": ""},
    ]
    picked = plan_retry(missing_families=["product"], candidates=candidates,
                        already_approved=[], failed_urls=[])
    assert picked == ["c1"]


def test_retry_never_reuses_failed_urls_or_approved_candidates():
    candidates = [
        {"candidate_id": "c1", "url": "https://x.com/products",
         "source_type": "product", "source_class": "company_owned",
         "why_relevant": ""},
        {"candidate_id": "c2", "url": "https://x.com/platform",
         "source_type": "product", "source_class": "company_owned",
         "why_relevant": ""},
    ]
    # c1 already failed -> never retried; c2 already approved -> not re-picked
    assert plan_retry(missing_families=["product"], candidates=candidates,
                      already_approved=["c2"],
                      failed_urls=["https://x.com/products"]) == []


def test_retry_budget_is_bounded():
    candidates = [
        {"candidate_id": f"c{i}", "url": f"https://x.com/p{i}",
         "source_type": "product", "source_class": "company_owned",
         "why_relevant": ""} for i in range(20)]
    picked = plan_retry(missing_families=["product", "customers", "strategy"],
                        candidates=candidates, already_approved=[],
                        failed_urls=[])
    assert len(picked) <= MAX_NEW_SOURCES_PER_PASS


# --- end-to-end loop --------------------------------------------------------

def _service(company, tmp_path):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=company.transport(), resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name=company.name, website=company.base,
                           user_id="u1", as_of=AS_OF)["run_id"]
    return ci, fi, run_id


def test_retry_loop_recovers_missing_families_and_composes_once(tmp_path):
    """Approving ONLY filings must trigger targeted rediscovery that finds the
    product and customer evidence — while minting exactly one report run."""
    company = GOLDEN[0]
    ci, fi, run_id = _service(company, tmp_path)
    candidates = ci.discover(run_id)
    filings = [c["candidate_id"] for c in candidates
               if c.get("source_class") == "investor_material"]
    ci.approve(run_id, user_id="u1", approved_ids=filings, rejected_ids=[])
    ci.fetch_approved(run_id)

    before = evidence_gaps(ci.store.retrieved(run_id))
    assert not before["sufficient"]

    result = ci.compose_with_quality(run_id, fi_service=fi)
    after = evidence_gaps(ci.store.retrieved(run_id))

    assert result["quality_passes"] >= 1, "a retry pass should have run"
    assert len(after["families"]) > len(before["families"])
    assert result["quality"]["metrics"]["has_product_evidence"]
    assert result["quality"]["metrics"]["has_customer_evidence"]
    # exactly one report run — retry must never duplicate the analysis
    runs = [r for r in fi.store.read_all()
            if r.event_type == "fi.run_created"]
    assert len(runs) == 1
    # and every pass is diagnosed
    passes = [h for h in result["quality_history"]
              if isinstance(h.get("pass"), int)]
    assert all(h["reason"] and h["new_sources"] for h in passes)


def test_retry_stops_and_labels_limited_when_evidence_cannot_be_found(tmp_path):
    """When rediscovery cannot fill the gaps, the report is published as
    explicitly LIMITED — never as complete, and never padded."""
    company = GOLDEN[0]

    def only_filings(url, timeout):
        if "company_tickers.json" in url or "/submissions/CIK" in url \
                or url.endswith("index.json") or "ex991" in url \
                or "cover.htm" in url:
            return company.transport()(url, timeout)
        if url.rstrip("/") == company.base:
            return company.transport()(url, timeout)
        raise _http_error(url, 403)

    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=only_filings, resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name=company.name, website=company.base,
                           user_id="u1", as_of=AS_OF)["run_id"]
    candidates = ci.discover(run_id)
    filings = [c["candidate_id"] for c in candidates
               if c.get("source_class") == "investor_material"]
    ci.approve(run_id, user_id="u1", approved_ids=filings, rejected_ids=[])
    ci.fetch_approved(run_id)
    result = ci.compose_with_quality(run_id, fi_service=fi)

    assert result["quality"]["outcome"] in (REPORT_QUALITY_LIMITED,
                                            REPORT_QUALITY_FAIL)
    assert result["ingestion_status"] != "COMPLETE"
    # the reader is told what is missing, specifically
    assert result["coverage"]["next_evidence_steps"]


def test_no_source_retrieved_is_still_an_honest_failure(tmp_path):
    """Rediscovery cannot rescue a run where nothing is retrievable."""
    def all_blocked(url, timeout):
        if "company_tickers.json" in url:
            import json as _json
            return (200, {"content-type": "application/json"},
                    _json.dumps({}).encode(), False)
        raise _http_error(url, 403)

    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=all_blocked, resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name="Blocked Co",
                           website="https://blocked.example", user_id="u1",
                           as_of=AS_OF)["run_id"]
    candidates = ci.discover(run_id)
    ci.approve(run_id, user_id="u1",
               approved_ids=[c["candidate_id"] for c in candidates][:5],
               rejected_ids=[])
    ci.fetch_approved(run_id)
    result = ci.compose_with_quality(run_id, fi_service=fi)
    assert result["status"] == "FAILED"
    assert ci.store.run_state(run_id) == "FAILED"


def test_failed_sources_are_shown_readably_not_as_internal_ids(tmp_path):
    """Phase 7: a failed source is identified by title/URL, never by an opaque
    candidate id."""
    company = GOLDEN[0]
    ci, fi, run_id = _service(company, tmp_path)
    candidates = ci.discover(run_id)
    ci.approve(run_id, user_id="u1",
               approved_ids=[c["candidate_id"] for c in candidates][:8],
               rejected_ids=[])
    ci.fetch_approved(run_id)
    library = ci.evidence_library(run_id)
    failed = library["unavailable_or_failed"]
    assert failed, "the fixture blocks some sources"
    for entry in failed:
        assert not str(entry["origin"]).startswith("cand-")
        assert entry["title"] and entry["source_family"]
        assert entry["failure_type"]


def test_dropped_sections_are_not_scored_as_populated():
    """Release-gate metric correctness.

    populated_share once used the sections PRESENT in the report as its
    denominator, so a report that dropped ten of its eleven major sections
    scored 1.0 — exactly the same as a complete report — because numerator
    and denominator shrank together. A gate that cannot tell a whole report
    from a gutted one is a false positive, not a gate.
    """
    from intent_engine.company_ingestion.quality import MAJOR_SECTIONS, assess

    def section(kind):
        text = (f"Substantive evidence-derived content about the company "
                f"covering {kind.replace('_', ' ')} in enough detail to read "
                f"as populated rather than a placeholder.")
        return {"kind": kind, "text": text,
                "cards": [{"claims": [{"text": text}]}]}

    complete = assess({"sections": [section(k) for k in MAJOR_SECTIONS]}, [])
    gutted = assess({"sections": [section(MAJOR_SECTIONS[0])]}, [])

    assert complete["metrics"]["populated_share"] == 1.0
    assert gutted["metrics"]["populated_share"] < complete["metrics"][
        "populated_share"], "a gutted report must not score like a full one"
    # 1 of 11 populated, not 1 of 1.
    assert gutted["metrics"]["populated_share"] == round(
        1 / len(MAJOR_SECTIONS), 3)
    assert gutted["metrics"]["missing_sections"] == list(MAJOR_SECTIONS[1:])
    assert gutted["metrics"]["present_sections"] == 1
    assert gutted["metrics"]["major_sections"] == len(MAJOR_SECTIONS)
    # placeholder_share is the complement, over the same denominator.
    assert round(gutted["metrics"]["placeholder_share"]
                 + gutted["metrics"]["populated_share"], 3) == 1.0

"""V1.1 — discovery, approval, retrieval, lineage, report quality,
persistence, and conversation over the recorded-source fixture."""
import pytest

from company_fixture_pages import (
    BASE, DOMAIN, EXTERNAL_EXCERPT, PAGES, transport,
)
from intent_engine.company_ingestion.claims import (
    assert_real_claims, build_claims,
)
from intent_engine.company_ingestion.records import (
    IngestionError, MAX_APPROVED_SOURCES, MAX_CANDIDATES_SHOWN,
)
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService

AS_OF = "2026-07-23T00:00:00+00:00"


@pytest.fixture
def pipeline(tmp_path):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=transport,
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Brightlake", website=BASE,
                        user_id="user-1", as_of=AS_OF)
    return ci, fi, run["run_id"]


def _approve_all(ci, run_id, *, user="user-1"):
    candidates = ci.discover(run_id)
    approved = [c["candidate_id"] for c in candidates
                if c["url"] in PAGES or c["url"].endswith("/missing")]
    approved = approved[:MAX_APPROVED_SOURCES]
    ci.approve(run_id, user_id=user, approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    return approved


# --- discovery -----------------------------------------------------------------

def test_discovery_bounded_deterministic_same_domain(pipeline):
    ci, _, run_id = pipeline
    first = ci.discover(run_id)
    again = ci.discover(run_id)                  # idempotent, no refetch
    assert [c["url"] for c in first] == [c["url"] for c in again]
    assert len(first) <= MAX_CANDIDATES_SHOWN
    assert all(c["same_domain"] for c in first)
    assert first[0]["source_type"] == "homepage"
    urls = [c["url"] for c in first]
    assert len(urls) == len(set(urls))           # deduplicated


# --- approval -------------------------------------------------------------------

def test_rejected_candidates_are_never_fetched(pipeline):
    ci, _, run_id = pipeline
    candidates = ci.discover(run_id)
    keep = [c["candidate_id"] for c in candidates
            if c["url"] == BASE]
    ci.approve(run_id, user_id="user-1", approved_ids=keep,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in keep])
    result = ci.fetch_approved(run_id)
    fetched_urls = {r["original_url"] for r in result["ok"]}
    assert fetched_urls == {BASE}                # nothing else touched


def test_approval_is_immutable_owner_checked_and_consented(pipeline):
    ci, _, run_id = pipeline
    ci.discover(run_id)
    with pytest.raises(IngestionError, match="owner"):
        ci.approve(run_id, user_id="intruder", approved_ids=["x"],
                   rejected_ids=[])
    approved = _approve_all(ci, run_id)
    first = ci.store.approval(run_id)
    assert first["consent_version"] == "v1.1-source-approval"
    # a second approval does not overwrite the first
    second = ci.approve(run_id, user_id="user-1",
                        approved_ids=approved[:1], rejected_ids=[])
    assert second["approved_candidate_ids"] == \
        first["approved_candidate_ids"]


def test_unknown_candidate_and_empty_approval_rejected(pipeline):
    ci, _, run_id = pipeline
    ci.discover(run_id)
    with pytest.raises(IngestionError, match="unknown candidates"):
        ci.approve(run_id, user_id="user-1", approved_ids=["cand-nope"],
                   rejected_ids=[])
    with pytest.raises(IngestionError, match="at least one"):
        ci.approve(run_id, user_id="user-1", approved_ids=[],
                   rejected_ids=[])


def test_nothing_fetched_without_approval(pipeline):
    ci, _, run_id = pipeline
    ci.discover(run_id)
    with pytest.raises(IngestionError, match="no approval"):
        ci.fetch_approved(run_id)


# --- retrieval ------------------------------------------------------------------

def test_partial_success_is_honest(pipeline):
    ci, _, run_id = pipeline
    _approve_all(ci, run_id)
    result = ci.fetch_approved(run_id)
    assert result["status"] == "PARTIAL"          # /missing 404s
    assert result["ok"] and result["failed"]
    assert result["failed"][0]["failure_type"] == "http_status"
    assert "HTTP 404" in result["failed"][0]["safe_message"]


def test_retrieval_idempotent_no_refetch(pipeline):
    ci, _, run_id = pipeline
    _approve_all(ci, run_id)
    first = ci.fetch_approved(run_id)
    rows_before = len(ci.store.read_all())
    second = ci.fetch_approved(run_id)
    assert len(second["ok"]) == len(first["ok"])
    # ok sources are served from the store, not refetched
    assert len([r for r in ci.store.read_all()
                if r.event_type == "ci.source_retrieved"]) == \
        len(first["ok"])
    assert rows_before <= len(ci.store.read_all()) + len(second["failed"])


def test_stale_page_is_marked_stale(pipeline):
    ci, _, run_id = pipeline
    _approve_all(ci, run_id)
    ci.fetch_approved(run_id)
    blog = [r for r in ci.store.retrieved(run_id)
            if r["source_type"] == "blog"]
    assert blog and blog[0]["freshness"] == "STALE"


# --- lineage and report quality ---------------------------------------------------

def test_full_compose_real_lineage_and_quality(pipeline):
    ci, fi, run_id = pipeline
    _approve_all(ci, run_id)
    ci.fetch_approved(run_id)
    ci.add_pasted(run_id, user_id="user-1", label="Review excerpt",
                  origin="public review site", text=EXTERNAL_EXCERPT,
                  privacy="user_public_excerpt", authorized=True)
    result = ci.compose(run_id, fi_service=fi)
    assert result["ingestion_status"] == "PARTIAL"
    # every claim resolves to real refs
    for section in result["sections"]:
        for card in section.get("cards", []):
            for claim in card.get("claims", []):
                for ref in claim.get("source_refs", []):
                    assert ref["subsystem"] == "company_ingestion"
    # overview: <=250 words, has limitation, every sentence has claim ids
    words = sum(len(s["text"].split()) for s in result["overview"])
    assert words <= 250
    assert all(s["claim_ids"] for s in result["overview"])
    assert "limitation" in result["overview"][-1]["text"].lower()
    # evidence library: grouped, deduplicated, failures listed
    lib = result["evidence_library"]
    assert lib["company_website"] and lib["user_provided"]
    assert lib["unavailable_or_failed"]
    origins = [e["origin"] for e in lib["company_website"]]
    assert len(origins) == len(set(origins))
    # the conflicting signal produced a real two-source blind spot
    blind = [s for s in result["sections"]
             if s["kind"] == "possible_blind_spots"][0]
    assert blind["cards"], "conflicting homepage/case-study emphasis " \
                           "should surface one blind spot"
    refs = {r["artifact_id"]
            for c in blind["cards"] for cl in c["claims"]
            for r in cl["source_refs"]}
    assert len(refs) >= 2                        # two distinct sources
    # no company master score anywhere (the disclaimer that none exists
    # is allowed; an actual "NN/100" assignment is not)
    import re
    assert not re.search(r"\b\d{1,3}/100\b", str(result))
    assert "your company is" not in str(result).lower()


def test_synthetic_evidence_cannot_enter_real_run():
    from intent_engine.founder_intelligence.fixtures import demo_claims
    with pytest.raises(IngestionError, match="synthetic"):
        assert_real_claims(demo_claims())


def test_no_invented_numbers_or_competitors(pipeline):
    ci, fi, run_id = pipeline
    _approve_all(ci, run_id)
    ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi)
    competitors = [s for s in result["sections"]
                   if s["kind"] == "competitors"][0]
    assert competitors["availability"] == "OUT_OF_SCOPE"
    flat = str(result).lower()
    for banned in ("market share", "conversion rate", "revenue of",
                   "customer count"):
        assert banned not in flat


def test_unavailable_is_not_zero(pipeline):
    ci, fi, run_id = pipeline
    _approve_all(ci, run_id)
    ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi)
    analytics = [s for s in result["sections"]
                 if s["kind"] == "evidence_and_analytics"][0]
    unavailable = [c for c in analytics["cards"]
                   if c["availability"] == "UNAVAILABLE"]
    assert unavailable                           # engagement metric honest
    assert all(not c["claims"] for c in unavailable)


# --- quotes ---------------------------------------------------------------------

def test_invented_quote_is_rejected():
    doc = {"source_id": "src-1", "source_type": "homepage",
           "retrieval_status": "OK", "title": "Real Title",
           "meta_description": "", "content_hash": "a" * 64,
           "retrieved_at": AS_OF, "parser_version": "v1",
           "freshness": "CURRENT",
           "text_content": "Actual page text only."}
    from intent_engine.company_ingestion.claims import assert_quotes_exist
    with pytest.raises(IngestionError, match="does not exist"):
        assert_quotes_exist('The page says "something it never said".',
                            {"src-1": doc}, ["src-1"])


# --- persistence ----------------------------------------------------------------

def test_restart_preserves_everything(tmp_path):
    path = tmp_path / "ci.jsonl"
    ci = CompanyIngestionService(path, transport=transport, resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name="Brightlake", website=BASE,
                           user_id="user-1", as_of=AS_OF)["run_id"]
    _approve_all(ci, run_id)
    ci.fetch_approved(run_id)
    first = ci.compose(run_id, fi_service=fi)
    # "restart": fresh service instances over the same files
    ci2 = CompanyIngestionService(path, transport=transport, resolver=False)
    fi2 = FounderIntelligenceService(tmp_path / "fi.jsonl")
    assert ci2.store.approval(run_id) is not None
    assert len(ci2.store.retrieved(run_id)) == \
        len(ci.store.retrieved(run_id))
    second = ci2.compose(run_id, fi_service=fi2)
    assert [s["kind"] for s in second["sections"]] == \
        [s["kind"] for s in first["sections"]]


# --- conversation ----------------------------------------------------------------

def test_conversation_uses_real_run_claims_only(pipeline):
    ci, fi, run_id = pipeline
    _approve_all(ci, run_id)
    ci.fetch_approved(run_id)
    ci.compose(run_id, fi_service=fi)
    meta = ci.run_meta(run_id)
    claims = build_claims(documents=ci.store.retrieved(run_id),
                          company_name=meta["company_name"],
                          domain=meta["domain"])
    flat = [c for g in claims.values() if isinstance(g, list) for c in g]
    assert_real_claims(claims)
    fi_run_id = None
    for row in fi.store.read_all():
        if row.event_type == "fi.run_created":
            fi_run_id = row.run_id
    answer = fi.converse(fi_run_id, "why do you think this? show evidence",
                         run_claims=flat)
    assert answer["intent"] == "SUPPORTED"
    citations = [c for p in answer["answer"]["paragraphs"]
                 for c in p["citations"]]
    assert citations                             # cited from real claims

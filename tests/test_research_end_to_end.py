"""T019 end-to-end: the golden path, three refusals, the Evidence Index,
lineage, coverage, snapshots, consumer, and repository invariants.

0 real model calls (fake client). 0 network.
"""
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intent_engine.knowledge import KnowledgeService
from intent_engine.research import (
    ResearchError, ResearchService, capture_graph_snapshot,
    capture_package_snapshot, claim_key, fingerprint_request,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-07-21T00:00:00+00:00"

PAPER_TEXT = ("Reply rate rose from 4% to 9% after the subject line was "
              "shortened in a controlled trial of 800 messages.")
BLOG_TEXT = ("Reply rate rose from 4% to 9% after the subject line was "
             "shortened in a controlled trial of 800 messages.")
CONTRA_TEXT = ("Shortening the subject line reduced replies in our sample "
               "of small accounts.")

QUESTIONS = ["Does shortening the subject line change reply rate?",
             "Does send time change reply rate?",
             "Does audience overlap explain the difference?"]


def _client(mapping):
    """Fake model client: returns candidates keyed by the text it is given."""
    client = MagicMock()

    def call_tool(**kwargs):
        text = kwargs["user_message"]
        for needle, candidates in mapping.items():
            if needle in text:
                return {"candidates": candidates}
        return {"candidates": []}

    client.call_tool.side_effect = call_tool
    return client


CANDIDATES = {
    PAPER_TEXT: [{"claim_text": "Reply rate rose from 4% to 9%",
                  "evidence_class": "observation",
                  "quote_span": "Reply rate rose from 4% to 9%"}],
    CONTRA_TEXT: [{"claim_text": "Reply rate rose from 4% to 9%",
                   "evidence_class": "observation",
                   "quote_span": "Shortening the subject line reduced replies"}],
}


@pytest.fixture()
def rig(tmp_path):
    know = KnowledgeService(tmp_path / "feedback.jsonl",
                            tmp_path / "knowledge.jsonl")
    svc = ResearchService(tmp_path / "research.jsonl",
                          knowledge_service=know,
                          llm_client=_client(CANDIDATES),
                          model_version="fake.v0")
    return svc, know, tmp_path


PLAN = dict(
    goal="explain the reply-rate difference between campaign A and B",
    questions=QUESTIONS,
    evidence_requirements={"minimum_sources": 2, "minimum_quality": "MEDIUM"},
    stopping_conditions={"max_sources": 12,
                         "corroborated_per_question": 2},
    failure_definition="if no source addresses a question, say so and stop",
    tool_allowlist=["supplied"], budget={"max_sources": 12,
                                         "max_model_calls": 10})


def _approved_request(svc, question="Why did campaign A outperform B?"):
    request = svc.create_request(question, motivation="post-campaign review",
                                 constraints=["2026-Q3"], scope="outbound")
    rid = request["request_id"]
    svc.draft_plan(rid, **PLAN)
    svc.submit_plan(rid)
    svc.approve_plan(rid, actor_id="founder")
    return rid


def _register(svc, rid, session, *, sid_class, text, **over):
    kw = dict(source_class=sid_class, title="A study", text=text,
              locator=f"https://example.com/{sid_class}",
              retrieved_at=AS_OF, acquisition_method="supplied",
              acquisition_tool="supplied", author="Author",
              publisher="Publisher", published_date="2026-07-01T00:00:00+00:00",
              domain="ai_research")
    kw.update(over)
    return svc.register_source(rid, session, **kw)


# =============================================================================
# The golden path
# =============================================================================

def test_golden_path(rig):
    svc, know, tmp = rig
    rid = _approved_request(svc)
    session = svc.start_session(rid)

    paper = _register(svc, rid, session, sid_class="peer_reviewed",
                      text=PAPER_TEXT, locator="https://example.com/paper")
    docs = _register(svc, rid, session, sid_class="official_docs",
                     text=PAPER_TEXT, locator="https://example.com/docs")
    contra = _register(svc, rid, session, sid_class="reputable_press",
                       text=CONTRA_TEXT, locator="https://example.com/press",
                       population="small accounts")
    blog = _register(svc, rid, session, sid_class="company_blog",
                     text=CONTRA_TEXT, locator="https://example.com/blog",
                     population="small accounts")
    forum = _register(svc, rid, session, sid_class="forum_post",
                      text=BLOG_TEXT, locator="https://example.com/forum")
    llm = _register(svc, rid, session, sid_class="llm_generated",
                    text=BLOG_TEXT, locator="https://example.com/llm")

    # one source fails verification: marked, never deleted
    svc.mark_source_unverified(rid, forum, "content hash changed on re-read")

    svc.extract_evidence(rid, session, paper, PAPER_TEXT,
                         question=QUESTIONS[0], stance="supports")
    svc.extract_evidence(rid, session, docs, PAPER_TEXT,
                         question=QUESTIONS[0], stance="supports")
    svc.extract_evidence(rid, session, contra, CONTRA_TEXT,
                         question=QUESTIONS[0], stance="contradicts")
    svc.extract_evidence(rid, session, blog, CONTRA_TEXT,
                         question=QUESTIONS[0], stance="contradicts")

    index = svc.get_index(rid, as_of=AS_OF)
    assert index.assert_invariants()["invariants"] == "ok"
    assert len(index.sources) == 6
    key = claim_key("Reply rate rose from 4% to 9%")
    assert len(index.evidence_for_claim(key)) == 4

    contradicting = [e["evidence_id"] for e in index.evidence_for_claim(key)
                     if e["stance"] == "contradicts"]
    supporting = [e["evidence_id"] for e in index.evidence_for_claim(key)
                  if e["stance"] == "supports"]
    svc.record_contradiction(rid, session, claim_key_=key,
                             evidence_id=contradicting[0],
                             counterpart=supporting[0],
                             conflict_reason="different_populations")

    svc.close_session(rid, session)

    # question 1 investigated; question 2 investigated with no evidence;
    # question 3 never investigated at all
    claim_map = {QUESTIONS[0]: [key], QUESTIONS[1]: []}
    package_id = svc.assemble_package(rid, session, claim_map=claim_map,
                                      as_of=AS_OF)
    package = svc.get_package(rid, package_id)

    totals = package["coverage"]["totals"]
    assert totals["contradicted"] == 1          # Q1: MIXED
    assert totals["not_covered"] == 1           # Q2: searched, nothing found
    assert totals["not_investigated"] == 1      # Q3: never searched
    assert package["sources"]["unverified"] == [forum]
    assert package["research_debt"]

    conclusion = svc.draft_conclusion(rid, package_id, question=QUESTIONS[0])
    assert conclusion["uncertainty_label"] == "CONFLICTING"
    assert conclusion["structured"] is True
    assert conclusion["what_would_change_this"]

    narrative = svc.generate_narrative(rid, conclusion)
    assert "Conflicting evidence" in narrative
    assert QUESTIONS[2] in narrative            # names what was not addressed

    # the mechanism draft states the contradiction rather than hiding it
    lib = REPO_ROOT / "src/intent_engine/core/data/mechanisms.json"
    before = lib.read_bytes()
    proposal_id = svc.queue_mechanism_draft(
        rid, package_id, candidate_name="subject_line_length_effect",
        hypothesis="shorter subject lines may change reply rate in outbound",
        trigger_conditions=["outbound email", "subject line shortened"],
        expected_effects="reply rate shifts", scope="B2B outbound",
        claim_key_=key, as_of=AS_OF)
    proposal = know.get_mechanism_proposal(proposal_id)
    assert proposal["status"] == "proposed"
    assert "MIXED" in proposal["hypothesis"]
    assert "different_populations" in proposal["hypothesis"]
    assert lib.read_bytes() == before
    assert know.search_knowledge() == []        # nothing promoted

    pkg_snap = capture_package_snapshot(svc, rid, package_id, as_of=AS_OF)
    graph_snap = capture_graph_snapshot(svc, rid, as_of=AS_OF)
    assert pkg_snap["versions"]["index_version"] == "evidence_index.v1"
    assert graph_snap["invariants"]["invariants"] == "ok"
    assert graph_snap["independence_groups"][paper]

    svc.request_review(rid)
    svc.record_review(rid, notes="conflicting; needs a matched-population run",
                      actor_id="founder")

    # replay: zero duplicates anywhere
    rows_before = len(svc.store.read_all())
    svc.assemble_package(rid, session, claim_map=claim_map, as_of=AS_OF)
    svc.draft_conclusion(rid, package_id, question=QUESTIONS[0])
    capture_package_snapshot(svc, rid, package_id, as_of=AS_OF)
    capture_graph_snapshot(svc, rid, as_of=AS_OF)
    assert len(svc.store.read_all()) == rows_before

    # the index is reproducible from the log
    fresh = ResearchService(tmp / "research.jsonl")
    assert sorted(fresh.get_index(rid, as_of=AS_OF).evidence) == \
        sorted(index.evidence)

    # language wall over the ENTIRE serialized run
    blob = json.dumps([r.payload for r in svc.get_history(rid)],
                      default=str).lower()
    for phrase in ("everyone knows", "the answer is", "clearly shows"):
        assert phrase not in blob
    for pattern in (r"\bproved\b", r"\bproven\b", r"\bobviously\b",
                    r"\balways\b", r"\bcertain\b", r"\bconfirmed\b"):
        assert not re.search(pattern, blob), pattern


# =============================================================================
# Refusal A — insufficient evidence
# =============================================================================

def test_insufficient_evidence_is_a_successful_outcome(rig):
    svc, know, _ = rig
    rid = _approved_request(svc)
    session = svc.start_session(rid)
    a = _register(svc, rid, session, sid_class="personal_blog",
                  text=PAPER_TEXT, locator="https://example.com/a")
    svc.extract_evidence(rid, session, a, PAPER_TEXT, question=QUESTIONS[0],
                         stance="supports")
    svc.close_session(rid, session)

    key = claim_key("Reply rate rose from 4% to 9%")
    package_id = svc.assemble_package(rid, session,
                                      claim_map={QUESTIONS[0]: [key]},
                                      as_of=AS_OF)
    conclusion = svc.draft_conclusion(rid, package_id, question=QUESTIONS[0])
    assert conclusion["uncertainty_label"] in ("UNKNOWN", "SPECULATIVE")

    package = svc.get_package(rid, package_id)
    assert package["research_debt"]
    plan = svc.get_plan(rid)
    assert plan["failure_definition"]           # pre-authorized outcome

    with pytest.raises(ResearchError, match="minimum corroboration|INSUFFICIENT"):
        svc.queue_mechanism_draft(
            rid, package_id, candidate_name="thin", hypothesis="thin claim",
            trigger_conditions=["x"], expected_effects="y", scope="z",
            claim_key_=key, as_of=AS_OF)
    assert know.search_knowledge() == []
    assert know.list_mechanism_proposals() == []


def test_opinion_only_evidence_cannot_become_a_mechanism(rig):
    svc, know, _ = rig
    rid = _approved_request(svc)
    session = svc.start_session(rid)
    opinion_text = "We think shorter subject lines feel better to read."
    svc.llm_client = _client({opinion_text: [
        {"claim_text": "shorter subject lines feel better",
         "evidence_class": "opinion",
         "quote_span": "shorter subject lines feel better"}]})
    src = _register(svc, rid, session, sid_class="peer_reviewed",
                    text=opinion_text, locator="https://example.com/op")
    svc.extract_evidence(rid, session, src, opinion_text,
                         question=QUESTIONS[0], stance="supports")
    svc.close_session(rid, session)
    key = claim_key("shorter subject lines feel better")
    package_id = svc.assemble_package(rid, session,
                                      claim_map={QUESTIONS[0]: [key]},
                                      as_of=AS_OF)
    with pytest.raises(ResearchError):
        svc.queue_mechanism_draft(
            rid, package_id, candidate_name="opinion_only",
            hypothesis="a claim from opinion alone",
            trigger_conditions=["x"], expected_effects="y", scope="z",
            claim_key_=key, as_of=AS_OF)


# =============================================================================
# Refusal B — collection before plan approval
# =============================================================================

def test_collection_before_approval_is_rejected(rig):
    svc, _, _ = rig
    request = svc.create_request("Unapproved question", motivation="m")
    rid = request["request_id"]
    svc.draft_plan(rid, **PLAN)
    with pytest.raises(ResearchError, match="APPROVED research plan"):
        svc.start_session(rid)
    svc.submit_plan(rid)
    with pytest.raises(ResearchError, match="APPROVED research plan"):
        svc.start_session(rid)


def test_plan_approval_is_human_only_and_requires_all_parts(rig):
    svc, _, _ = rig
    request = svc.create_request("q", motivation="m")
    rid = request["request_id"]
    with pytest.raises(ResearchError, match="failure_definition"):
        svc.draft_plan(rid, **{**PLAN, "failure_definition": "  "})
    with pytest.raises(ResearchError, match="tool allowlist"):
        svc.draft_plan(rid, **{**PLAN, "tool_allowlist": []})
    svc.draft_plan(rid, **PLAN)
    svc.submit_plan(rid)
    for actor in ("system", "agent"):
        with pytest.raises(ResearchError, match="human wall"):
            svc.approve_plan(rid, actor_id="bot", actor_type=actor)


def test_tool_allowlist_is_enforced(rig):
    svc, _, _ = rig
    rid = _approved_request(svc)
    session = svc.start_session(rid)
    with pytest.raises(ResearchError, match="allowlist"):
        _register(svc, rid, session, sid_class="peer_reviewed",
                  text=PAPER_TEXT, acquisition_tool="web_crawler")
    kinds = [r.event_type for r in svc.get_history(rid)]
    assert "research.source_rejected" in kinds


# =============================================================================
# Four-layer separation, lineage, dedup, consumer, invariants
# =============================================================================

def test_four_layer_structural_rules(rig):
    svc, _, _ = rig
    rid = _approved_request(svc)
    session = svc.start_session(rid)
    src = _register(svc, rid, session, sid_class="peer_reviewed",
                    text=PAPER_TEXT)
    svc.extract_evidence(rid, session, src, PAPER_TEXT,
                         question=QUESTIONS[0], stance="supports")
    svc.close_session(rid, session)
    key = claim_key("Reply rate rose from 4% to 9%")
    package_id = svc.assemble_package(rid, session,
                                      claim_map={QUESTIONS[0]: [key]},
                                      as_of=AS_OF)

    # one session produces exactly ONE package
    from intent_engine.research.state import fold_research
    state = svc.get_state(rid)
    assert state.session_packages[session] == package_id

    # a conclusion cannot exist without its package
    with pytest.raises(ResearchError, match="existing package"):
        svc._record(rid, "research.conclusion_drafted", actor_type="agent",
                    actor_id="a", version=state.approved_plan_version,
                    subject_id="C1", payload={"package_id": "ghost"})

    # at most ONE conclusion per package per plan version
    svc.draft_conclusion(rid, package_id, question=QUESTIONS[0])
    with pytest.raises(ResearchError, match="at most ONE conclusion"):
        svc._record(rid, "research.conclusion_drafted", actor_type="agent",
                    actor_id="a", version=state.approved_plan_version,
                    subject_id="C2", payload={"package_id": package_id})


def test_lineage_answers_the_full_chain(rig):
    svc, _, _ = rig
    rid = _approved_request(svc)
    session = svc.start_session(rid)
    src = _register(svc, rid, session, sid_class="peer_reviewed",
                    text=PAPER_TEXT)
    result = svc.extract_evidence(rid, session, src, PAPER_TEXT,
                                  question=QUESTIONS[0], stance="supports")
    lineage = svc.lineage(rid, result["accepted"][0], as_of=AS_OF)
    assert lineage["source_id"] == src
    assert lineage["session_id"] == session
    assert lineage["plan_version"] == 1
    assert lineage["request_id"] == rid
    assert lineage["retrieved_at"] == AS_OF
    assert lineage["content_hash"].startswith("sha256:")
    assert lineage["source_quality"] == "HIGH"


def test_index_rejects_orphan_evidence(rig):
    svc, _, _ = rig
    rid = _approved_request(svc)
    session = svc.start_session(rid)
    src = _register(svc, rid, session, sid_class="peer_reviewed",
                    text=PAPER_TEXT)
    result = svc.extract_evidence(rid, session, src, PAPER_TEXT,
                                  question=QUESTIONS[0], stance="supports")
    index = svc.get_index(rid, as_of=AS_OF)
    broken = dict(index.evidence)
    broken[result["accepted"][0]] = {**broken[result["accepted"][0]],
                                     "source_id": "ghost"}
    from intent_engine.research.index import EvidenceIndex
    with pytest.raises(ResearchError, match="unregistered source"):
        EvidenceIndex(request_id=rid, sources=index.sources,
                      evidence=broken, claims=index.claims).assert_invariants()


def test_duplicate_request_reuses_prior_work(rig):
    svc, _, _ = rig
    first = svc.create_request("Why did A outperform B?", motivation="m",
                               constraints=["2026-Q3"], scope="outbound")
    again = svc.create_request("why did a outperform b?", motivation="other",
                               constraints=["2026-Q3"], scope="outbound")
    assert again["reused"] is True
    assert again["request_id"] == first["request_id"]
    # a different scope is a DIFFERENT question, never auto-merged
    other = svc.create_request("Why did A outperform B?", motivation="m",
                               constraints=["2026-Q3"], scope="inbound")
    assert other["reused"] is False
    assert fingerprint_request("q", ["a"], "s") != fingerprint_request(
        "q", ["a"], "t")


def test_consumer_suggests_a_request_and_nothing_more(rig):
    svc, _, _ = rig
    from intent_engine.research.consumer import ResearchCompanyEventConsumer

    class _Ev:
        event_type = "growth.result_labelled"
        event_id = "EV1"
        subject_id = "EXP1"
        decision_id = None
        occurred_at = AS_OF

    consumer = ResearchCompanyEventConsumer(svc)
    assert consumer.consumer_name == "research"
    consumer.process(_Ev())
    assert len(consumer.suggested) == 1
    rid = consumer.suggested[0]
    state = svc.get_state(rid)
    assert state.plan_status == "none"          # no plan
    assert state.sessions == ()                 # no session
    consumer.process(_Ev())                     # replay: dedup by fingerprint
    assert len(set(consumer.suggested)) == 1


def test_repository_invariants(rig):
    """Improvement 15: exactly one implementation of each research concern."""
    svc, _, _ = rig
    research = REPO_ROOT / "src/intent_engine/research"

    def _count(pattern):
        return sum(f.read_text().count(pattern) for f in research.glob("*.py"))

    assert _count("def grade_source(") == 1
    assert _count("def canonicalize_locator(") == 1
    assert _count("def independence_group(") == 1
    assert _count("def freshness_of(") == 1
    assert _count("def stance_for_claim(") == 1
    assert _count("def rank_evidence(") == 1
    assert _count("def build_index(") == 1
    assert _count("def draft_conclusion(") == 2      # definition + service call

    # the T016 citation model is reused, not duplicated
    assert _count("CITATION_TYPES = ") == 0
    # research writes no other subsystem's store
    service_src = (research / "service.py").read_text()
    for forbidden in ("crm.jsonl", "knowledge.jsonl", "feedback.jsonl",
                      "marketing.jsonl", "growth.jsonl", "events.jsonl"):
        assert forbidden not in service_src
    # and it has no promote/validate/crawl surface at all
    for banned in ("promote", "validate_insight", "crawl", "fetch", "browse"):
        assert not [m for m in dir(svc)
                    if banned in m.lower() and not m.startswith("_")]

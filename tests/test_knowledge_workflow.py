"""T016 bars: citations, insight workflow, knowledge promotion,
mechanism proposal queue."""
import pytest

from intent_engine.knowledge import KnowledgeError, KnowledgeService


@pytest.fixture()
def svc(tmp_path):
    return KnowledgeService(tmp_path / "feedback.jsonl",
                            tmp_path / "knowledge.jsonl")


def _feedback(svc):
    return svc.record_feedback("feedback.founder_outcome",
                               "Runway assumption broke in month 2.",
                               actor_type="human", actor_id="founder")


def _cit(svc, fid):
    return [{"source_type": "feedback_record", "source_id":
             svc.get_feedback(fid)[0].row_id}]


def _propose(svc, fid, claim="Runway assumptions in this niche tend to "
                            "break early in observed cases."):
    return svc.propose_insight(
        "Runway assumptions fragile", claim,
        scope="B2B SaaS premortems reviewed so far",
        limitations="single-digit observation count",
        source_feedback_ids=[fid], citations=_cit(svc, fid),
        proposed_by="analysis_agent", actor_type="system")


# --- citations ---------------------------------------------------------------

def test_uncited_insight_rejected(svc):
    fid = _feedback(svc)
    with pytest.raises(KnowledgeError, match="CITATION REQUIRED"):
        svc.propose_insight("t", "claim text", scope="s", limitations="l",
                            source_feedback_ids=[fid], citations=[],
                            proposed_by="x")


def test_invalid_internal_citation_rejected(svc):
    fid = _feedback(svc)
    with pytest.raises(KnowledgeError, match="not found"):
        svc.propose_insight(
            "t", "claim", scope="s", limitations="l",
            source_feedback_ids=[fid],
            citations=[{"source_type": "feedback_record",
                        "source_id": "Z" * 26}], proposed_by="x")


def test_external_citation_requires_metadata(svc):
    fid = _feedback(svc)
    with pytest.raises(KnowledgeError, match="title"):
        svc.propose_insight(
            "t", "claim", scope="s", limitations="l",
            source_feedback_ids=[fid],
            citations=[{"source_type": "external_source",
                        "source_id": "x", "url": "https://example.com"}],
            proposed_by="x")


def test_below_gate_analytics_cannot_support_positive_claim(tmp_path):
    metrics = {"calibration": {"status":
                               "TOO FEW RESOLVED TO CLAIM CALIBRATION"}}
    svc = KnowledgeService(tmp_path / "f.jsonl", tmp_path / "k.jsonl",
                           resolvers={"metric_lookup": metrics.get})
    fid = svc.record_feedback("feedback.internal_review", "note",
                              actor_type="human", actor_id="founder")
    with pytest.raises(KnowledgeError, match="cannot support a positive"):
        svc.propose_insight(
            "t", "our probability quality looks fine", scope="s",
            limitations="l", source_feedback_ids=[fid],
            citations=[{"source_type": "analytics_metric",
                        "source_id": "calibration"}], proposed_by="x")


# --- insight workflow --------------------------------------------------------

def test_system_proposes_human_validates(svc):
    fid = _feedback(svc)
    iid = _propose(svc, fid)                       # system-generated: fine
    assert svc.get_insight(iid)["status"] == "proposed"
    with pytest.raises(KnowledgeError, match="human wall"):
        svc.validate_insight(iid, 1, actor_id="bot", actor_type="system")
    svc.validate_insight(iid, 1, actor_id="founder")
    assert svc.get_insight(iid)["current_is_validated"] is True


def test_validation_attaches_to_exact_revision(svc):
    fid = _feedback(svc)
    iid = _propose(svc, fid)
    with pytest.raises(KnowledgeError, match="exact current revision"):
        svc.validate_insight(iid, 2, actor_id="founder")
    svc.validate_insight(iid, 1, actor_id="founder")
    # a revision AFTER validation demands revalidation
    rev = svc.revise_insight(iid, actor_type="human", actor_id="founder",
                             scope="slightly broader scope")
    st = svc.get_insight(iid)
    assert rev == 2 and st["current_is_validated"] is False
    assert st["status"] == "proposed"
    assert iid in svc.list_pending_validations()


def test_rejected_insight_remains_visible(svc):
    fid = _feedback(svc)
    iid = _propose(svc, fid)
    svc.reject_insight(iid, "too narrow", actor_id="founder")
    st = svc.get_insight(iid)
    assert st["status"] == "rejected"
    kinds = [r.record_type for r in svc.get_insight_history(iid)]
    assert "insight.rejected" in kinds
    with pytest.raises(KnowledgeError, match="rejected insight"):
        svc.validate_insight(iid, 1, actor_id="founder")


def test_claim_language_wall(svc):
    fid = _feedback(svc)
    for bad in ("This is proven to work", "It always breaks",
                "X causes Y", "validated by data"):
        with pytest.raises(KnowledgeError, match="INSUFFICIENT SUPPORT"):
            _propose(svc, fid, claim=bad)


# --- knowledge promotion -----------------------------------------------------

def _validated(svc):
    fid = _feedback(svc)
    iid = _propose(svc, fid)
    svc.validate_insight(iid, 1, actor_id="founder")
    return iid


def test_unvalidated_cannot_promote(svc):
    fid = _feedback(svc)
    iid = _propose(svc, fid)
    with pytest.raises(KnowledgeError, match="NOT VALIDATED"):
        svc.promote_knowledge(iid, 1, category="risk_pattern",
                              actor_id="founder")


def test_human_promotion_and_versioning(svc):
    iid = _validated(svc)
    with pytest.raises(KnowledgeError, match="human wall"):
        svc.promote_knowledge(iid, 1, category="risk_pattern",
                              actor_id="bot", actor_type="system")
    kid = svc.promote_knowledge(iid, 1, category="risk_pattern",
                                actor_id="founder")
    item = svc.get_knowledge_item(kid)
    assert item["version"] == 1 and item["status"] == "active"
    assert item["citations"] and item["scope"] and item["limitations"]
    v2 = svc.supersede_knowledge(kid, actor_id="founder",
                                 limitations="wider evidence needed")
    assert v2 == 2
    assert svc.get_knowledge_item(kid)["version"] == 2
    assert svc.get_knowledge_item(kid, version=1)["status"] == "historical"


def test_retraction_keeps_history(svc):
    iid = _validated(svc)
    kid = svc.promote_knowledge(iid, 1, category="risk_pattern",
                                actor_id="founder")
    with pytest.raises(KnowledgeError, match="unknown retraction"):
        svc.retract_knowledge(kid, "changed my mind", actor_id="founder")
    svc.retract_knowledge(kid, "outdated", actor_id="founder")
    assert svc.get_current_knowledge(kid) is None
    assert svc.get_knowledge_item(kid)["status"] == "retracted"
    assert svc.get_knowledge_item(kid, version=1)["title"]   # retrievable


def test_search_is_deterministic(svc):
    for _ in range(2):
        iid = _validated(svc)
        svc.promote_knowledge(iid, 1, category="risk_pattern",
                              actor_id="founder")
    a = svc.search_knowledge(category="risk_pattern")
    b = svc.search_knowledge(category="risk_pattern")
    assert [i["knowledge_id"] for i in a] == [i["knowledge_id"] for i in b]
    assert len(a) == 2


# --- mechanism proposal queue ------------------------------------------------

def _mk_proposal(svc, name="early_runway_fragility"):
    iid = _validated(svc)
    kid = svc.promote_knowledge(iid, 1, category="mechanism_candidate",
                                actor_id="founder")
    return svc.propose_mechanism(
        name, "runway assumptions may break early in this niche",
        trigger_conditions=["runway < 6 months stated"],
        expected_effects="premortem flags timeline risk",
        scope="B2B SaaS", counterexamples="none recorded yet",
        citations=_cit(svc, _feedback(svc)),
        source_knowledge_ids=[kid], proposed_by="analysis_agent")


def test_proposal_flow_and_frozen_library_untouched(svc):
    from pathlib import Path
    lib = Path("src/intent_engine/core/data/mechanisms.json")
    before = lib.read_bytes()
    pid = _mk_proposal(svc)
    assert svc.get_mechanism_proposal(pid)["status"] == "proposed"
    with pytest.raises(KnowledgeError, match="human wall"):
        svc.review_mechanism(pid, "accepted_for_library_change", "ok",
                             actor_id="bot", actor_type="system")
    svc.review_mechanism(pid, "accepted_for_library_change",
                         "queue for the gated library update",
                         actor_id="founder")
    assert svc.get_mechanism_proposal(pid)["status"] == \
        "accepted_for_library_change"
    assert lib.read_bytes() == before          # frozen library untouched


def test_duplicate_proposal_detection(svc):
    _mk_proposal(svc, "dup_name")
    with pytest.raises(KnowledgeError, match="already exists"):
        _mk_proposal(svc, "dup_name")


def test_rejected_proposal_visible_and_name_reusable(svc):
    pid = _mk_proposal(svc, "rejected_name")
    svc.review_mechanism(pid, "rejected", "not enough support",
                         actor_id="founder")
    assert svc.list_mechanism_proposals(status="rejected")
    _mk_proposal(svc, "rejected_name")          # rejected frees the name

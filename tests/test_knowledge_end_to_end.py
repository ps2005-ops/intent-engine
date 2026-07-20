"""T016 end-to-end: consumer + the three required paths + replay + the
frozen library staying frozen. 0 model calls."""
from pathlib import Path

import pytest

from intent_engine.core.decision_record import DecisionService
from intent_engine.events import CompanyEventBus, bridge_decision_events, drain, replay
from intent_engine.knowledge import (
    KnowledgeCompanyEventConsumer, KnowledgeError, KnowledgeService,
)


@pytest.fixture()
def rig(tmp_path):
    ds = DecisionService(str(tmp_path / "decisions.db"))
    bus = CompanyEventBus(tmp_path / "events")
    svc = KnowledgeService(tmp_path / "feedback.jsonl",
                           tmp_path / "knowledge.jsonl",
                           resolvers={"decision_service": ds})
    return ds, bus, svc


def _resolve_decision(ds):
    rec = ds.create_decision("founder")
    for ev in ("RecommendationIssued", "DecisionSubmitted", "DecisionApproved",
               "ExecutionStarted", "DecisionResolved"):
        ds.record_event(rec.decision_id, ev, actor_type="human",
                        actor_id="founder", source="cli")
    return rec


def test_full_promotion_path_with_replay(rig):
    ds, bus, svc = rig
    rec = _resolve_decision(ds)
    bridge_decision_events(ds, bus)

    consumer = KnowledgeCompanyEventConsumer(svc)
    rep = drain(bus, consumer)
    assert rep.processed == 1                     # decision.resolved only
    obs = svc.get_feedback_for_decision(rec.decision_id)
    assert len(obs) == 1
    assert obs[0].record_type == "feedback.founder_outcome"
    assert obs[0].company_event_id                 # provenance kept
    # confidential payloads never copied: observation is type + ids only
    assert "intake" not in obs[0].payload["content"]

    fid = obs[0].subject_id
    iid = svc.propose_insight(
        "Resolution observed", "resolution events arrive with usable "
        "provenance in observed cases",
        scope="decisions bridged so far", limitations="one observation",
        source_feedback_ids=[fid],
        citations=[{"source_type": "feedback_record",
                    "source_id": obs[0].row_id}],
        proposed_by="analysis_agent")
    svc.validate_insight(iid, 1, actor_id="founder")
    kid = svc.promote_knowledge(iid, 1, category="measurement_rule",
                                actor_id="founder")
    item = svc.get_knowledge_item(kid)
    assert item["status"] == "active" and item["citations"]

    lib = Path("src/intent_engine/core/data/mechanisms.json")
    before = lib.read_bytes()
    pid = svc.propose_mechanism(
        "resolution_provenance", "bridged resolutions may carry reusable "
        "provenance", trigger_conditions=["decision.resolved consumed"],
        expected_effects="observations traceable", scope="event pipeline",
        counterexamples="none yet",
        citations=[{"source_type": "feedback_record",
                    "source_id": obs[0].row_id}],
        source_knowledge_ids=[kid], proposed_by="analysis_agent")
    assert svc.get_mechanism_proposal(pid)["status"] == "proposed"
    assert lib.read_bytes() == before             # mechanisms.json unchanged

    # replay: zero duplicate observations, zero duplicate anything
    n_feedback = len(svc.feedback.read_all())
    n_rows = len(svc.rows.read_all())
    replay(bus, consumer, from_offset=0)
    drain(bus, consumer)
    assert len(svc.feedback.read_all()) == n_feedback
    assert len(svc.rows.read_all()) == n_rows


def test_rejection_path_preserves_history_no_knowledge(rig):
    _, _, svc = rig
    fid = svc.record_feedback("feedback.internal_review",
                              "one anecdote, no pattern",
                              actor_type="human", actor_id="founder")
    iid = svc.propose_insight(
        "Weak claim", "a single anecdote may suggest a pattern",
        scope="n=1", limitations="insufficient observations",
        source_feedback_ids=[fid],
        citations=[{"source_type": "feedback_record",
                    "source_id": svc.get_feedback(fid)[0].row_id}],
        proposed_by="analysis_agent")
    svc.reject_insight(iid, "insufficient support", actor_id="founder")
    with pytest.raises(KnowledgeError):
        svc.promote_knowledge(iid, 1, category="customer_signal",
                              actor_id="founder")
    assert svc.search_knowledge() == []           # no knowledge item exists
    assert svc.get_insight(iid)["status"] == "rejected"


def test_consumer_checkpoint_and_failure_semantics(rig):
    ds, bus, svc = rig
    _resolve_decision(ds)
    bridge_decision_events(ds, bus)
    consumer = KnowledgeCompanyEventConsumer(svc)
    real = svc.record_feedback
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("briefly down")
        return real(*a, **k)

    svc.record_feedback = flaky
    rep = drain(bus, consumer)
    assert rep.retried == 1
    assert bus.store.get_checkpoint("knowledge") < len(bus.store.read_all())
    rep2 = drain(bus, consumer)                   # restart redelivers safely
    assert rep2.processed == 1
    assert len(svc.get_feedback_for_decision(
        ds.list_decision_ids()[0])) == 1          # no duplicates


def test_consumption_never_auto_promotes(rig):
    ds, bus, svc = rig
    _resolve_decision(ds)
    bridge_decision_events(ds, bus)
    drain(bus, KnowledgeCompanyEventConsumer(svc))
    assert svc.search_knowledge() == []
    assert svc.list_pending_validations() == []   # observations only


def test_language_wall_over_promoted_knowledge(rig):
    _, _, svc = rig
    fid = svc.record_feedback("feedback.internal_review", "note",
                              actor_type="human", actor_id="founder")
    cit = [{"source_type": "feedback_record",
            "source_id": svc.get_feedback(fid)[0].row_id}]
    iid = svc.propose_insight("ok", "pattern appears in observed cases",
                              scope="s", limitations="l",
                              source_feedback_ids=[fid], citations=cit,
                              proposed_by="x")
    svc.validate_insight(iid, 1, actor_id="founder")
    kid = svc.promote_knowledge(iid, 1, category="decision_pattern",
                                actor_id="founder")
    with pytest.raises(KnowledgeError, match="INSUFFICIENT SUPPORT"):
        svc.supersede_knowledge(kid, actor_id="founder",
                                statement="this is proven and always true")

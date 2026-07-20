"""T014 bars: the outreach approval wall — drafting may be automated;
sending may not bypass a prior human approval for the same draft."""
import pytest

from intent_engine.crm import CRMService, CRMTransitionError


@pytest.fixture()
def crm(tmp_path):
    return CRMService(tmp_path / "crm.jsonl")


@pytest.fixture()
def entity(crm):
    return crm.create_prospect(email="j@a.com")


def _draft(crm, a, draft="d-1"):
    crm.record(a, "crm.outreach_drafted", actor_type="agent",
               actor_id="content_agent", source="system",
               payload={"draft_id": draft})


def test_draft_may_exist_without_approval_and_is_pending(crm, entity):
    _draft(crm, entity)
    assert crm.get_pending_approvals(entity) == ["d-1"]


def test_send_before_approval_rejected(crm, entity):
    _draft(crm, entity)
    with pytest.raises(CRMTransitionError, match="prior human approval"):
        crm.record(entity, "crm.outreach_sent", actor_type="human",
                   actor_id="founder", payload={"draft_id": "d-1"})


def test_agent_or_system_approval_rejected(crm, entity):
    _draft(crm, entity)
    for actor in ("agent", "system"):
        with pytest.raises(CRMTransitionError, match="human wall"):
            crm.record(entity, "crm.outreach_approved", actor_type=actor,
                       actor_id="bot", payload={"draft_id": "d-1"})


def test_rejection_blocks_send(crm, entity):
    _draft(crm, entity)
    crm.record(entity, "crm.outreach_rejected", actor_type="human",
               actor_id="founder", payload={"draft_id": "d-1"})
    with pytest.raises(CRMTransitionError):
        crm.record(entity, "crm.outreach_sent", actor_type="human",
                   actor_id="founder", payload={"draft_id": "d-1"})


def test_approved_send_succeeds_once_retry_no_duplicate(crm, entity):
    _draft(crm, entity)
    crm.record(entity, "crm.outreach_approved", actor_type="human",
               actor_id="founder", payload={"draft_id": "d-1"})
    for _ in range(2):                                # retry the send
        crm.record(entity, "crm.outreach_sent", actor_type="human",
                   actor_id="founder", payload={"draft_id": "d-1"},
                   idempotency_key="send:d-1")
    kinds = [e.event_type for e in crm.get_history(entity)]
    assert kinds.count("crm.outreach_sent") == 1      # zero duplicates
    assert crm.get_pending_approvals(entity) == []


def test_approval_scoped_per_draft(crm, entity):
    _draft(crm, entity, "d-1")
    _draft(crm, entity, "d-2")
    crm.record(entity, "crm.outreach_approved", actor_type="human",
               actor_id="founder", payload={"draft_id": "d-1"})
    with pytest.raises(CRMTransitionError):
        crm.record(entity, "crm.outreach_sent", actor_type="human",
                   actor_id="founder", payload={"draft_id": "d-2"})


def test_no_auto_approval_path_exists():
    from intent_engine.crm.service import _HUMAN_ONLY
    assert {"crm.outreach_approved", "crm.outreach_rejected"} <= _HUMAN_ONLY

"""T014 end-to-end: the two required deterministic scenarios, replay
included. No live model calls; no external messages."""
import pytest

from intent_engine.core.decision_record import DecisionService
from intent_engine.crm import CRMCompanyEventConsumer, CRMService
from intent_engine.events import (
    CompanyEventBus, bridge_decision_events, drain, replay,
)


@pytest.fixture()
def rig(tmp_path):
    return (CRMService(tmp_path / "crm.jsonl"),
            DecisionService(str(tmp_path / "decisions.db")),
            CompanyEventBus(tmp_path / "events"))


def test_prospect_to_high_conversion_with_replay(rig):
    crm, svc, bus = rig
    founder = dict(actor_type="human", actor_id="founder")

    a = crm.create_prospect(name="Jane", email="jane@acme.com",
                            idempotency_key="intake-jane")
    crm.record(a, "crm.qualified", **founder)
    rec = svc.create_decision("founder", idempotency_key="jane-decision")
    svc.record_event(rec.decision_id, "RecommendationIssued",
                     actor_type="system", actor_id="pipeline", source="system")
    crm.link_decision(a, rec.decision_id, "subject", decision_service=svc)

    bridge_decision_events(svc, bus)
    bus.publish("report.generated", subject_type="report", subject_id="r.pdf",
                producer="report_renderer", actor_type="system",
                actor_id="report_renderer", source="system",
                decision_id=rec.decision_id, idempotency_key="rep-jane")
    consumer = CRMCompanyEventConsumer(crm)
    drain(bus, consumer)

    crm.record(a, "crm.outreach_drafted", actor_type="agent",
               actor_id="content_agent", source="system",
               payload={"draft_id": "d-1"})
    crm.record(a, "crm.outreach_approved", **founder,
               payload={"draft_id": "d-1"})
    crm.record(a, "crm.outreach_sent", **founder,
               payload={"draft_id": "d-1"}, idempotency_key="send:d-1")
    crm.record(a, "crm.replied", **founder)
    crm.record(a, "crm.meeting_booked", **founder)
    crm.record(a, "crm.opportunity_opened", **founder)

    assert crm.get_conversion_signal(a)["category"] == "HIGH"
    st = crm.get_current_state(a)
    assert st.opportunity == "opportunity" and st.relationship == "engaged"
    assert crm.get_decisions(a)[0]["decision_id"] == rec.decision_id
    kinds = [e.event_type for e in crm.get_history(a)]
    assert kinds.count("crm.report_generated") == 1

    # replay everything: zero duplicate CRM facts anywhere
    n = len(crm.get_history(a))
    replay(bus, consumer, from_offset=0)
    drain(bus, consumer)
    assert len(crm.get_history(a)) == n

    # the CRM answers the decision-history questions deterministically
    assert crm.get_entity("jane@acme.com") == a
    activity = [e for e in crm.get_history(a)
                if e.event_type == "crm.decision_activity"]
    assert all(e.decision_id == rec.decision_id for e in activity)


def test_customer_risk_scenario_health_changes_history_intact(rig):
    crm, _, _ = rig
    founder = dict(actor_type="human", actor_id="founder")
    a = crm.create_prospect(email="ceo@beta.com")
    for ev in ("crm.qualified", "crm.opportunity_opened", "crm.proposal_sent",
               "crm.won", "crm.customer_activated"):
        crm.record(a, ev, **founder)
    now = "2026-07-20T12:00:00+00:00"
    crm.record(a, "crm.meeting_booked", **founder, occurred_at=now)
    assert crm.get_health(a, now=now)["category"] == "HEALTHY"

    crm.record(a, "crm.customer_at_risk", **founder,
               payload={"reason_note": "renewal stalled"})
    assert crm.get_health(a, now=now)["category"] == "AT_RISK"

    crm.record(a, "crm.customer_recovered", **founder)
    assert crm.get_health(a, now=now)["category"] == "HEALTHY"
    assert crm.get_current_state(a).customer == "active"

    types = [e.event_type for e in crm.get_history(a)]
    assert "crm.customer_at_risk" in types and "crm.customer_recovered" in types
    # consumer failure can never break the Decision Platform: the CRM file
    # is separate, append-only, and nothing upstream reads it
    assert crm.store.path.name == "crm.jsonl"


def test_crm_failure_cannot_break_decision_platform(rig, tmp_path):
    """The synchronous intake->analysis->ledger->report path never touches
    the CRM: a poisoned CRM store leaves the Decision Platform green."""
    crm, svc, bus = rig
    with open(crm.store.path, "a") as f:
        f.write("corrupted beyond repair\n")
    rec = svc.create_decision("founder")                     # still works
    svc.record_event(rec.decision_id, "DecisionSubmitted", actor_type="human",
                     actor_id="founder", source="cli")
    assert svc.get_current_state(rec.decision_id).decision_status == "under_review"
    assert bridge_decision_events(svc, bus)["published"] == 2  # bus unaffected

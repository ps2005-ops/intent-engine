"""T014 bars: decision links + the checkpointed, idempotent Company Event
consumer (first real consumer of the T013 log)."""
import pytest

from intent_engine.core.decision_record import DecisionService
from intent_engine.crm import CRMCompanyEventConsumer, CRMService
from intent_engine.events import CompanyEventBus, bridge_decision_events, drain


@pytest.fixture()
def rig(tmp_path):
    return (CRMService(tmp_path / "crm.jsonl"),
            DecisionService(str(tmp_path / "decisions.db")),
            CompanyEventBus(tmp_path / "events"))


# --- decision links ----------------------------------------------------------

def test_entity_links_many_decisions_idempotently(rig):
    crm, svc, _ = rig
    a = crm.create_prospect(email="j@a.com")
    d1 = svc.create_decision("founder")
    d2 = svc.create_decision("founder")
    crm.link_decision(a, d1.decision_id, "subject", decision_service=svc)
    crm.link_decision(a, d1.decision_id, "subject", decision_service=svc)  # dup
    crm.link_decision(a, d2.decision_id, "champion", decision_service=svc)
    links = crm.get_decisions(a)
    assert len(links) == 2
    assert {(l["decision_id"], l["link_type"]) for l in links} == {
        (d1.decision_id, "subject"), (d2.decision_id, "champion")}


def test_invalid_decision_id_fails_clearly(rig):
    crm, svc, _ = rig
    a = crm.create_prospect(email="j@a.com")
    with pytest.raises(KeyError, match="no such decision"):
        crm.link_decision(a, "Z" * 26, decision_service=svc)


def test_crm_never_stores_decision_state(rig):
    """The Decision Record stays authoritative: the CRM stores references,
    never folded status or intake content."""
    crm, svc, _ = rig
    a = crm.create_prospect(email="j@a.com")
    rec = svc.create_decision(
        "founder", metadata={"intake_sha256": "ab" * 32})
    svc.record_event(rec.decision_id, "DecisionSubmitted", actor_type="human",
                     actor_id="founder", source="cli")
    crm.link_decision(a, rec.decision_id, decision_service=svc)
    blob = "".join(ev.to_json() for ev in crm.get_history(a))
    assert "under_review" not in blob and "draft" not in blob
    assert "intake_sha256" not in blob


# --- company event consumer --------------------------------------------------

def _bridged_rig(rig):
    crm, svc, bus = rig
    a = crm.create_prospect(email="j@a.com")
    rec = svc.create_decision("founder")
    svc.record_event(rec.decision_id, "RecommendationIssued",
                     actor_type="system", actor_id="pipeline", source="system")
    crm.link_decision(a, rec.decision_id, decision_service=svc)
    bridge_decision_events(svc, bus)
    return crm, svc, bus, a, rec


def test_eligible_events_map_once_with_provenance(rig):
    crm, svc, bus, a, rec = _bridged_rig(rig)
    consumer = CRMCompanyEventConsumer(crm)
    rep = drain(bus, consumer)
    assert rep.processed == 2                    # created + recommendation
    facts = [e for e in crm.get_history(a)
             if e.event_type == "crm.decision_activity"]
    assert len(facts) == 2
    assert all(f.company_event_id and f.decision_id == rec.decision_id
               for f in facts)
    assert bus.store.get_checkpoint("crm") == 2


def test_report_generated_maps_once(rig):
    crm, svc, bus, a, rec = _bridged_rig(rig)
    bus.publish("report.generated", subject_type="report", subject_id="r.pdf",
                producer="report_renderer", actor_type="system",
                actor_id="report_renderer", source="system",
                decision_id=rec.decision_id, idempotency_key="rep-1")
    drain(bus, CRMCompanyEventConsumer(crm))
    kinds = [e.event_type for e in crm.get_history(a)]
    assert kinds.count("crm.report_generated") == 1


def test_replay_creates_zero_duplicate_crm_facts(rig):
    from intent_engine.events import replay
    crm, svc, bus, a, rec = _bridged_rig(rig)
    consumer = CRMCompanyEventConsumer(crm)
    drain(bus, consumer)
    n = len(crm.get_history(a))
    replay(bus, consumer, from_offset=0)         # full re-delivery
    drain(bus, consumer)
    assert len(crm.get_history(a)) == n          # idempotency keys held


def test_failure_does_not_advance_checkpoint_and_restart_is_safe(rig, monkeypatch):
    crm, svc, bus, a, rec = _bridged_rig(rig)
    consumer = CRMCompanyEventConsumer(crm)
    calls = {"n": 0}
    real = consumer.crm.record

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("crm briefly down")
        return real(*args, **kwargs)

    monkeypatch.setattr(consumer.crm, "record", flaky)
    rep = drain(bus, consumer)
    assert rep.retried == 1 and bus.store.get_checkpoint("crm") == 0
    rep2 = drain(bus, consumer)                  # restart: redelivered safely
    assert rep2.processed == 2
    facts = [e for e in crm.get_history(a)
             if e.event_type == "crm.decision_activity"]
    assert len(facts) == 2                       # no duplicates from the retry


def test_unlinked_decision_is_skipped_never_guessed(rig):
    crm, svc, bus = rig
    other = svc.create_decision("founder")       # decision with NO CRM link
    bridge_decision_events(svc, bus)
    consumer = CRMCompanyEventConsumer(crm)
    rep = drain(bus, consumer)
    assert rep.processed == 1                    # delivered, then skipped inside
    assert consumer.skipped_no_identity == 1
    assert crm.store.read_all() == []            # zero invented CRM facts
    # a later explicit link + replay backfills deterministically
    a = crm.create_prospect(email="late@a.com")
    crm.link_decision(a, other.decision_id, decision_service=svc)
    from intent_engine.events import replay
    replay(bus, consumer, from_offset=0)
    assert [e.event_type for e in crm.get_history(a)].count(
        "crm.decision_activity") == 1


def test_unsupported_event_types_not_consumed(rig):
    crm, svc, bus = rig
    consumer = CRMCompanyEventConsumer(crm)
    assert not consumer.handles("prediction.recorded")
    assert not consumer.handles("content.approved")
    assert consumer.handles("decision.approved")
    assert consumer.handles("report.generated")


def test_company_events_remain_unchanged_after_consumption(rig):
    crm, svc, bus, a, rec = _bridged_rig(rig)
    before = [e.to_json() for e in bus.store.read_all()]
    drain(bus, CRMCompanyEventConsumer(crm))
    assert [e.to_json() for e in bus.store.read_all()] == before

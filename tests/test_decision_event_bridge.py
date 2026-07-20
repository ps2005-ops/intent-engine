"""T013 bars: the DecisionEvent -> Company Event bridge. One-way,
deterministic, replayable with zero duplicates; the DecisionEvent store
stays the source of truth (nothing there changes)."""
import pytest

from intent_engine.core.decision_record import (
    EVENT_TYPES as DOMAIN_TYPES, DecisionService,
)
from intent_engine.events import (
    BRIDGED_EVENT_TYPES, CompanyEventBus, SKIPPED_EVENT_TYPES,
    bridge_decision_events,
)


@pytest.fixture()
def svc(tmp_path):
    return DecisionService(str(tmp_path / "decisions.db"))


@pytest.fixture()
def bus(tmp_path):
    return CompanyEventBus(tmp_path / "events")


def _advance(svc, did, *events):
    for ev in events:
        svc.record_event(did, ev, actor_type="human", actor_id="founder",
                         source="cli",
                         payload={"owner": "P"} if ev == "OwnerAssigned" else None)


def test_every_domain_event_type_has_an_explicit_policy():
    assert set(BRIDGED_EVENT_TYPES) | SKIPPED_EVENT_TYPES == DOMAIN_TYPES
    assert set(BRIDGED_EVENT_TYPES) & SKIPPED_EVENT_TYPES == set()


def test_lifecycle_events_map_once_with_provenance(svc, bus):
    rec = svc.create_decision("founder")
    _advance(svc, rec.decision_id, "RecommendationIssued",
             "DecisionSubmitted", "DecisionApproved", "ExecutionStarted",
             "DecisionResolved")
    counts = bridge_decision_events(svc, bus)
    # created + recommendation + submitted + approved + resolved bridge;
    # ExecutionStarted is explicitly skipped
    assert counts == {"published": 5, "duplicates": 0, "skipped": 1}
    evs = bus.store.read_all()
    types = [e.event_type for e in evs]
    assert types == ["decision.created", "decision.recommendation_issued",
                     "decision.submitted", "decision.approved",
                     "decision.resolved"]
    domain = svc.get_events(rec.decision_id)
    for company, orig in zip(evs, [d for d in domain
                                   if d["event_type"] not in SKIPPED_EVENT_TYPES]):
        assert company.decision_id == rec.decision_id
        assert company.causation_id == orig["event_id"]      # source identity
        assert company.payload["source_event_id"] == orig["event_id"]
        assert company.occurred_at == orig["occurred_at"]
        assert company.producer == "decision_event_bridge"
    # the authoritative store is unchanged by bridging
    assert len(svc.get_events(rec.decision_id)) == len(domain)


def test_failure_event_maps_correctly(svc, bus):
    rec = svc.create_decision("founder")
    svc.record_event(rec.decision_id, "AnalysisFailed", actor_type="system",
                     actor_id="premortem_pipeline", source="system",
                     payload={"error_type": "RuntimeError"})
    bridge_decision_events(svc, bus)
    types = [e.event_type for e in bus.store.read_all()]
    assert "decision.analysis_failed" in types


def test_privacy_and_owner_events_follow_skip_policy(svc, bus):
    rec = svc.create_decision("founder")
    _advance(svc, rec.decision_id, "OwnerAssigned")
    counts = bridge_decision_events(svc, bus)
    assert counts["skipped"] == 1                     # OwnerAssigned skipped
    blob = "".join(e.to_json() for e in bus.store.read_all())
    assert '"owner"' not in blob                      # owner PII never fanned out
    for t in SKIPPED_EVENT_TYPES & {"RedactionRequested", "Tombstoned"}:
        assert t not in blob


def test_bridge_retry_creates_zero_duplicates(svc, bus):
    rec = svc.create_decision("founder")
    _advance(svc, rec.decision_id, "RecommendationIssued", "DecisionSubmitted")
    first = bridge_decision_events(svc, bus)
    again = bridge_decision_events(svc, bus)
    assert first["published"] == 3
    assert again == {"published": 0, "duplicates": 3, "skipped": 0}
    assert len(bus.store.read_all()) == 3


def test_bridge_resumes_publishing_only_new_events(svc, bus):
    rec = svc.create_decision("founder")
    bridge_decision_events(svc, bus)                  # bridges DecisionCreated
    _advance(svc, rec.decision_id, "DecisionSubmitted")
    counts = bridge_decision_events(svc, bus)
    assert counts["published"] == 1                   # only the new fact
    assert counts["duplicates"] == 1
    assert [e.event_type for e in bus.store.read_all()] == [
        "decision.created", "decision.submitted"]


def test_bridge_covers_multiple_decisions(svc, bus):
    a = svc.create_decision("founder")
    b = svc.create_decision("founder")
    counts = bridge_decision_events(svc, bus)
    assert counts["published"] == 2
    ids = {e.decision_id for e in bus.store.read_all()}
    assert ids == {a.decision_id, b.decision_id}

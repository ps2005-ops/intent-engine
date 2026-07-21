"""T017 bars: CRM audience selection and evidence resolution."""
import pytest

from intent_engine.core.decision_record import DecisionService
from intent_engine.crm import CRMService
from intent_engine.knowledge import KnowledgeService
from intent_engine.marketing import MarketingError, MarketingService

AS_OF = "2026-12-31T00:00:00+00:00"


@pytest.fixture()
def rig(tmp_path):
    crm = CRMService(tmp_path / "crm.jsonl")
    know = KnowledgeService(tmp_path / "feedback.jsonl",
                            tmp_path / "knowledge.jsonl")
    svc = MarketingService(tmp_path / "marketing.jsonl", crm_service=crm,
                           knowledge_service=know)
    return svc, crm, know


def _campaign(svc):
    return svc.create_campaign("c", objective="o", channel="linkedin",
                               owner="P")


def _entity(crm, email, *events):
    eid = crm.create_prospect(email=email)
    for ev in events:
        crm.record(eid, ev, actor_type="human", actor_id="founder")
    return eid


# --- audience ----------------------------------------------------------------

def test_audience_selects_from_explicit_crm_criteria(rig):
    svc, crm, _ = rig
    a = _campaign(svc)
    qualified = _entity(crm, "q@x.com", "crm.qualified")
    _entity(crm, "cold@x.com")                       # no qualification
    sel = svc.define_audience(a, as_of=AS_OF, include_opportunity=["qualified"])
    assert sel["entity_count"] == 1
    assert sel["sample_entity_ids"] == [qualified]
    assert sel["rule_version"] == "audience.v1"
    assert sel["as_of"] == AS_OF


def test_closed_and_churned_excluded_unless_explicit(rig):
    svc, crm, _ = rig
    a = _campaign(svc)
    _entity(crm, "lost@x.com", "crm.qualified", "crm.lost")
    sel = svc.define_audience(a, as_of=AS_OF)
    assert sel["entity_count"] == 0
    assert "closed" in sel["exclusion_sample"][0]["reason"]
    b = _campaign(svc)
    sel2 = svc.define_audience(b, as_of=AS_OF, include_closed=True)
    assert sel2["entity_count"] == 1


def test_missing_signal_data_is_never_positive_intent(rig):
    svc, crm, _ = rig
    a = _campaign(svc)
    _entity(crm, "silent@x.com", "crm.qualified")     # no contact facts
    sel = svc.define_audience(a, as_of=AS_OF, include_health=["HEALTHY"])
    assert sel["entity_count"] == 0
    assert "UNKNOWN" in sel["exclusion_sample"][0]["reason"]


def test_conversion_unavailable_is_not_intent(rig):
    svc, crm, _ = rig
    a = _campaign(svc)
    _entity(crm, "new@x.com")
    sel = svc.define_audience(a, as_of=AS_OF, include_conversion=["HIGH"])
    assert sel["entity_count"] == 0
    assert "UNAVAILABLE" in sel["exclusion_sample"][0]["reason"]


def test_audience_is_deterministic_for_fixed_as_of(rig):
    svc, crm, _ = rig
    a = _campaign(svc)
    for i in range(3):
        _entity(crm, f"p{i}@x.com", "crm.qualified")
    first = svc.define_audience(a, as_of=AS_OF, include_opportunity=["qualified"])
    b = _campaign(svc)
    second = svc.define_audience(b, as_of=AS_OF, include_opportunity=["qualified"])
    assert first["sample_entity_ids"] == second["sample_entity_ids"]


def test_require_decision_link(rig, tmp_path):
    svc, crm, _ = rig
    ds = DecisionService(str(tmp_path / "d.db"))
    a = _campaign(svc)
    linked = _entity(crm, "linked@x.com", "crm.qualified")
    _entity(crm, "unlinked@x.com", "crm.qualified")
    rec = ds.create_decision("founder")
    crm.link_decision(linked, rec.decision_id, decision_service=ds)
    sel = svc.define_audience(a, as_of=AS_OF, require_decision_link=True)
    assert sel["sample_entity_ids"] == [linked]


def test_readiness_cannot_become_purchase_probability():
    from intent_engine.marketing.audience import assert_no_probability_language
    with pytest.raises(MarketingError, match="purchase probability"):
        assert_no_probability_language("These leads are 80% likely to buy")


# --- evidence ----------------------------------------------------------------

def test_below_gate_analytics_rejected_as_positive_support(tmp_path):
    metrics = {"calibration": {"status":
                               "TOO FEW RESOLVED TO CLAIM CALIBRATION"}}
    svc = MarketingService(tmp_path / "m.jsonl", metric_lookup=metrics.get)
    a = _campaign(svc)
    with pytest.raises(MarketingError, match="cannot support a positive"):
        svc.attach_evidence(a, {"evidence_type": "analytics_metric",
                                "source_id": "calibration"})
    # the rejection itself is recorded, not swallowed
    kinds = [r.event_type for r in svc.get_history(a)]
    assert "marketing.evidence_rejected" in kinds


def test_no_observation_source_cannot_support_engagement(tmp_path):
    metrics = {"report_engagement": {"status": "NO OBSERVATION SOURCE"}}
    svc = MarketingService(tmp_path / "m.jsonl", metric_lookup=metrics.get)
    a = _campaign(svc)
    with pytest.raises(MarketingError, match="cannot support a positive"):
        svc.attach_evidence(a, {"evidence_type": "analytics_metric",
                                "source_id": "report_engagement"})


def test_ok_metric_preserves_status_version_and_annotations(tmp_path):
    metrics = {"decisions_created": {"status": "OK", "value": 3,
                                     "metric_version": "decision_metrics.v1",
                                     "computed_at": AS_OF,
                                     "window": {"start": None, "end": AS_OF},
                                     "annotations": ["counted from events"]}}
    svc = MarketingService(tmp_path / "m.jsonl", metric_lookup=metrics.get)
    a = _campaign(svc)
    snap = svc.attach_evidence(a, {"evidence_type": "analytics_metric",
                                   "source_id": "decisions_created"})
    assert snap["metric_version"] == "decision_metrics.v1"
    assert snap["annotations"] == ["counted from events"]
    assert snap["status"] == "OK" and snap["window"]["end"] == AS_OF


def test_retracted_knowledge_rejected(rig):
    svc, _, know = rig
    a = _campaign(svc)
    fid = know.record_feedback("feedback.internal_review", "note",
                               actor_type="human", actor_id="founder")
    cit = [{"source_type": "feedback_record",
            "source_id": know.get_feedback(fid)[0].row_id}]
    iid = know.propose_insight("t", "pattern observed", scope="s",
                               limitations="l", source_feedback_ids=[fid],
                               citations=cit, proposed_by="x")
    know.validate_insight(iid, 1, actor_id="founder")
    kid = know.promote_knowledge(iid, 1, category="decision_pattern",
                                 actor_id="founder")
    snap = svc.attach_evidence(a, {"evidence_type": "knowledge_item",
                                   "source_id": kid})
    assert snap["scope"] == "s" and snap["limitations"] == "l"
    know.retract_knowledge(kid, "outdated", actor_id="founder")
    b = _campaign(svc)
    with pytest.raises(MarketingError, match="retracted"):
        svc.attach_evidence(b, {"evidence_type": "knowledge_item",
                                "source_id": kid})


def test_narrow_knowledge_scope_cannot_support_universal_claim(rig):
    svc, _, know = rig
    a = _campaign(svc)
    fid = know.record_feedback("feedback.internal_review", "note",
                               actor_type="human", actor_id="founder")
    cit = [{"source_type": "feedback_record",
            "source_id": know.get_feedback(fid)[0].row_id}]
    iid = know.propose_insight("t", "pattern observed",
                               scope="three B2B SaaS premortems",
                               limitations="n=3", source_feedback_ids=[fid],
                               citations=cit, proposed_by="x")
    know.validate_insight(iid, 1, actor_id="founder")
    kid = know.promote_knowledge(iid, 1, category="decision_pattern",
                                 actor_id="founder")
    with pytest.raises(MarketingError, match="universal claim"):
        svc.attach_evidence(a, {"evidence_type": "knowledge_item",
                                "source_id": kid},
                            claim_text="This holds for every company")


def test_external_evidence_requires_metadata(rig):
    svc, _, _ = rig
    a = _campaign(svc)
    with pytest.raises(MarketingError, match="title"):
        svc.attach_evidence(a, {"evidence_type": "external_source",
                                "source_id": "x", "url": "https://e.com"})
    snap = svc.attach_evidence(a, {"evidence_type": "external_source",
                                   "source_id": "x", "url": "https://e.com",
                                   "title": "A real paper",
                                   "publisher": "Journal"})
    assert snap["title"] == "A real paper"


def test_report_evidence_carries_generation_limitation(tmp_path):
    from intent_engine.events import CompanyEventBus
    bus = CompanyEventBus(tmp_path / "events")
    bus.publish("report.generated", subject_type="report", subject_id="r1",
                producer="report_renderer", actor_type="system",
                actor_id="report_renderer", source="system",
                idempotency_key="r1")
    svc = MarketingService(tmp_path / "m.jsonl", event_bus=bus)
    a = _campaign(svc)
    snap = svc.attach_evidence(a, {"evidence_type": "report",
                                   "source_id": "r1"})
    assert "not evidence that anyone read" in snap["limitations"]
    b = _campaign(svc)
    with pytest.raises(MarketingError, match="not found"):
        svc.attach_evidence(b, {"evidence_type": "report",
                                "source_id": "ghost"})

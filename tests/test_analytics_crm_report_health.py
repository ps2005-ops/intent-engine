"""T015 bars: CRM funnel metrics, report metrics, consumer health."""
import pytest

from intent_engine.analytics import AnalyticsService
from intent_engine.core.decision_record import DecisionService
from intent_engine.crm import CRMService
from intent_engine.events import CompanyEventBus, drain

AS_OF = "2026-12-31T00:00:00+00:00"


@pytest.fixture()
def crm(tmp_path):
    return CRMService(tmp_path / "crm.jsonl")


def _founder(crm, a, *events):
    for ev in events:
        crm.record(a, ev, actor_type="human", actor_id="founder")


# --- CRM funnel --------------------------------------------------------------

def test_entities_deduplicated_and_transitions_counted(crm):
    a = crm.create_prospect(email="a@x.com")
    b = crm.create_prospect(email="b@x.com")
    _founder(crm, a, "crm.qualified", "crm.opportunity_opened", "crm.won")
    _founder(crm, b, "crm.qualified", "crm.lost")
    # b reopened and re-qualified: still ONE distinct entity per metric
    crm.record(b, "crm.reopened", actor_type="human", actor_id="founder")
    _founder(crm, b, "crm.qualified")
    m = AnalyticsService(crm_service=crm).crm_funnel_metrics(as_of=AS_OF)
    assert m["crm_prospect_created"].value == 2
    assert m["crm_qualified"].value == 2          # deduped by entity
    assert m["crm_won"].value == 1
    assert m["crm_lost"].value == 1               # loss stays visible
    assert m["crm_ratio_qualified_to_won"].value == 0.5


def test_current_distribution_differs_from_history(crm):
    a = crm.create_prospect(email="a@x.com")
    _founder(crm, a, "crm.qualified", "crm.opportunity_opened", "crm.won",
             "crm.customer_activated", "crm.customer_at_risk")
    m = AnalyticsService(crm_service=crm).crm_funnel_metrics(as_of=AS_OF)
    dist = m["crm_current_stage_distribution"].value
    assert dist["customer"] == {"at_risk": 1}     # current state
    assert m["crm_won"].value == 1                # historical fact retained


def test_empty_denominator_is_unavailable_not_zero_percent(crm):
    crm.create_prospect(email="a@x.com")          # nobody approved anything
    m = AnalyticsService(crm_service=crm).crm_funnel_metrics(as_of=AS_OF)
    r = m["crm_ratio_approved_to_sent"]
    assert r.status == "UNAVAILABLE" and r.value is None


def test_outreach_counts_use_actual_facts(crm):
    a = crm.create_prospect(email="a@x.com")
    crm.record(a, "crm.outreach_drafted", actor_type="agent", actor_id="bot",
               source="system", payload={"draft_id": "d1"})
    crm.record(a, "crm.outreach_approved", actor_type="human",
               actor_id="founder", payload={"draft_id": "d1"})
    crm.record(a, "crm.outreach_sent", actor_type="human", actor_id="founder",
               payload={"draft_id": "d1"})
    m = AnalyticsService(crm_service=crm).crm_funnel_metrics(as_of=AS_OF)
    assert m["crm_outreach_drafted"].value == 1
    assert m["crm_outreach_approved"].value == 1
    assert m["crm_ratio_approved_to_sent"].value == 1.0


# --- report metrics ----------------------------------------------------------

def test_report_metrics_generated_failed_and_no_fake_engagement(tmp_path):
    svc = DecisionService(str(tmp_path / "decisions.db"))
    bus = CompanyEventBus(tmp_path / "events")
    rec = svc.create_decision("founder")
    no_report = svc.create_decision("founder")
    bus.publish("report.generated", subject_type="report", subject_id="r1",
                producer="report_renderer", actor_type="system",
                actor_id="report_renderer", source="system",
                decision_id=rec.decision_id, idempotency_key="r1")
    bus.publish("report.generated", subject_type="report", subject_id="r2",
                producer="report_renderer", actor_type="system",
                actor_id="report_renderer", source="system",
                decision_id=rec.decision_id, idempotency_key="r2")
    bus.publish("report.generation_failed", subject_type="report",
                subject_id="r3", producer="report_renderer",
                actor_type="system", actor_id="report_renderer",
                source="system", idempotency_key="r3")
    m = AnalyticsService(decision_service=svc, event_store=bus.store
                         ).report_metrics(as_of=AS_OF)
    assert m["reports_generated"].value == 2
    assert m["report_generation_failures"].value == 1
    assert m["reports_per_decision_max"].value == 2
    assert m["decisions_without_reports"].value == 1
    ids = m["decisions_without_reports"].provenance["contributors"]["sample_ids"]
    assert no_report.decision_id in ids
    eng = m["report_engagement"]
    assert eng.status == "NO OBSERVATION SOURCE" and eng.value is None


# --- consumer health ---------------------------------------------------------

def _bus_with_events(tmp_path, n=3):
    bus = CompanyEventBus(tmp_path / "events")
    for i in range(n):
        bus.publish("prediction.recorded", subject_type="prediction",
                    subject_id=f"p{i}", producer="premortem_pipeline",
                    actor_type="system", actor_id="pipe", source="system",
                    idempotency_key=f"k{i}")
    return bus


class _OK:
    consumer_name = "ok"

    def handles(self, t):
        return True

    def process(self, e):
        pass


class _Broken:
    consumer_name = "broken"

    def handles(self, t):
        return True

    def process(self, e):
        raise RuntimeError("nope")


def test_consumer_lag_never_started_and_dead_letters(tmp_path):
    bus = _bus_with_events(tmp_path)
    drain(bus, _OK())
    drain(bus, _Broken(), max_attempts=1)         # first event -> DLQ, rest too
    m = AnalyticsService(event_store=bus.store).consumer_health(as_of=AS_OF)
    consumers = m["consumers"].value
    assert consumers["ok"]["lag_events"] == 0
    assert consumers["broken"]["dead_letters_total"] == 3
    assert consumers["broken"]["dead_letters_unresolved"] == 3
    # a consumer that never ran shows NEVER STARTED, not healthy
    m2 = AnalyticsService(event_store=bus.store).consumer_health(
        as_of=AS_OF, )
    health = AnalyticsService(event_store=bus.store)
    out = health.consumer_health(as_of=AS_OF)
    named = out["consumers"].value
    assert "ok" in named
    from intent_engine.analytics.consumer_health import consumer_health as ch
    from intent_engine.analytics.models import make_window
    view = ch(bus.store, make_window("all", AS_OF), AS_OF,
              consumer_names=["ghost"])
    ghost = view["consumers"].value["ghost"]
    assert ghost["started"] is False and "NEVER STARTED" in ghost["note"]


def test_health_reads_do_not_modify_checkpoints(tmp_path):
    bus = _bus_with_events(tmp_path)
    drain(bus, _OK())
    before = bus.store.checkpoint_path.read_text()
    AnalyticsService(event_store=bus.store).consumer_health(as_of=AS_OF)
    assert bus.store.checkpoint_path.read_text() == before


def test_retry_backlog_counted(tmp_path):
    bus = _bus_with_events(tmp_path, n=1)
    drain(bus, _Broken(), max_attempts=3)         # 1 failure persisted
    m = AnalyticsService(event_store=bus.store).consumer_health(as_of=AS_OF)
    assert m["consumers"].value["broken"]["retry_backlog"] == 1


def test_missing_sources_are_unavailable_sections():
    svc = AnalyticsService()                       # nothing configured
    for section in (svc.decision_metrics(), svc.calibration_metrics(),
                    svc.crm_funnel_metrics(), svc.report_metrics(),
                    svc.consumer_health()):
        only = list(section.values())[0]
        assert only.status == "UNAVAILABLE"

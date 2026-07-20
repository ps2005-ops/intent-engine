"""T013 end-to-end: one mocked premortem workflow flows into the company
log, a consumer drains it, retries and dead letters work, and reruns
produce zero duplicates. 0 model calls (fake analyzer + fake bridge
client, same fixtures as the T010 wiring tests)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from intent_engine.core.decision_record import DecisionService
from intent_engine.core.prediction_ledger import list_predictions
from intent_engine.core.schemas import FailureMode, RiskAudit
from intent_engine.events import CompanyEventBus, drain, redrive
from intent_engine.simulator.pipeline import run_premortem


def _fake_analyzer():
    audit = RiskAudit(
        narrative_summary="You're explaining to the board why burn outpaced growth.",
        failure_modes=[FailureMode(description="Burn exceeds growth",
                                   likelihood="likely", rationale="hiring plan")],
        recommended_stress_tests=["Model churn"],
        key_sensitivity="Revenue concentration",
    )
    analyzer = MagicMock()
    analyzer.run.return_value = SimpleNamespace(
        intent=MagicMock(), risk_audit=audit, scenario_set=MagicMock())
    return analyzer


def _fake_bridge_client():
    client = MagicMock()
    client.call_tool.return_value = {"predictions": [
        {"claim_text": "Burn exceeds plan for 2 quarters",
         "probability": 0.6, "resolve_by": "2027-02-01"}]}
    return client


def _run(tmp_path, svc, bus):
    return run_premortem(
        "Hire a 4-person sales team", MagicMock(), analyzer=_fake_analyzer(),
        bridge_client=_fake_bridge_client(), bridge_entity_id="acme",
        bridge_ledger_path=tmp_path / "ledger.db",
        decision_service=svc, decision_intake_key="intake-e2e",
        event_bus=bus)


class Collector:
    consumer_name = "e2e_collector"

    def __init__(self, fail_first_n=0):
        self.seen = []
        self.remaining_failures = fail_first_n

    def handles(self, event_type):
        return True

    def process(self, event):
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise RuntimeError("consumer down")
        self.seen.append(event.event_type)


def test_end_to_end_workflow_drains_once_and_reruns_add_nothing(tmp_path):
    svc = DecisionService(str(tmp_path / "decisions.db"))
    bus = CompanyEventBus(tmp_path / "events")
    result = _run(tmp_path, svc, bus)

    types = [e.event_type for e in bus.store.read_all()]
    assert types == ["prediction.recorded", "decision.created",
                     "decision.recommendation_issued"]
    did = result.decision_record.decision_id
    assert all(e.decision_id == did or e.event_type == "prediction.recorded"
               for e in bus.store.read_all())
    # the prediction event carries the SAME decision_id (one identity)
    pred_ev = bus.store.read_all()[0]
    assert pred_ev.decision_id == did and pred_ev.correlation_id == did

    c = Collector()
    rep = drain(bus, c)
    assert rep.processed == 3
    assert bus.store.get_checkpoint("e2e_collector") == 3

    # rerun the same intake: idempotent end to end — no new events, no new
    # ledger rows, nothing redelivered
    _run(tmp_path, svc, bus)
    assert len(bus.store.read_all()) == 3
    assert len(list_predictions(path=tmp_path / "ledger.db",
                                decision_id=did)) == 1
    assert drain(bus, c).processed == 0


def test_end_to_end_consumer_failure_retry_dead_letter_redrive(tmp_path):
    svc = DecisionService(str(tmp_path / "decisions.db"))
    bus = CompanyEventBus(tmp_path / "events")
    _run(tmp_path, svc, bus)

    c = Collector(fail_first_n=3)                 # first event fails 3x
    assert drain(bus, c, max_attempts=3).retried == 1
    assert bus.store.get_checkpoint("e2e_collector") == 0   # no advance
    assert len(bus.store.read_all()) == 3                    # log untouched
    drain(bus, c, max_attempts=3)
    rep = drain(bus, c, max_attempts=3)           # third attempt -> DLQ
    assert rep.dead_lettered == 1
    assert rep.processed == 2                     # the rest flowed on
    dls = bus.store.read_dead_letters()
    assert len(dls) == 1 and dls[0]["redrive_status"] == "pending"

    # explicit redrive now succeeds (consumer recovered), history preserved
    assert redrive(bus, c, dls[0]["original_event_id"]) == "succeeded"
    statuses = [d["redrive_status"] for d in bus.store.read_dead_letters()]
    assert statuses == ["pending", "succeeded"]
    assert redrive(bus, c, dls[0]["original_event_id"]) == "already_redriven"


def test_report_renderer_publishes_generated_event(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "_frr_e2e", Path(__file__).resolve().parents[1]
        / "scripts/render_founder_report.py")
    frr = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = frr
    spec.loader.exec_module(frr)

    svc = DecisionService(str(tmp_path / "decisions.db"))
    bus = CompanyEventBus(tmp_path / "events")
    result = _run(tmp_path, svc, bus)

    from intent_engine.simulator.context_schema import BusinessContext
    ta_spec = importlib.util.spec_from_file_location(
        "_ta_e2e", Path(__file__).resolve().parent / "test_analysis.py")
    ta = importlib.util.module_from_spec(ta_spec)
    sys.modules[ta_spec.name] = ta
    ta_spec.loader.exec_module(ta)
    from intent_engine.simulator.analysis import PremortemAnalyzer
    real = PremortemAnalyzer(client=ta.FakeLLMClient(ta.CANNED_FLAT_RESPONSE)) \
        .run("Hire a sales team", BusinessContext(revenue="$60k MRR"))
    wired = result._replace(intent=real.intent, risk_audit=real.risk_audit,
                            scenario_set=real.scenario_set)
    out = tmp_path / "report.pdf"
    frr.render_premortem_pdf("Hire a sales team",
                             BusinessContext(revenue="$60k MRR"), wired, out,
                             decision_service=svc, event_bus=bus,
                             generated_at="2026-07-20T19:00:00+00:00")
    evs = bus.store.read_all()
    gen = [e for e in evs if e.event_type == "report.generated"]
    assert len(gen) == 1
    assert gen[0].decision_id == result.decision_record.decision_id
    assert gen[0].producer == "report_renderer"
    # idempotent: re-render with the same timestamp adds nothing
    frr.render_premortem_pdf("Hire a sales team",
                             BusinessContext(revenue="$60k MRR"), wired, out,
                             decision_service=svc, event_bus=bus,
                             generated_at="2026-07-20T19:00:00+00:00")
    assert len([e for e in bus.store.read_all()
                if e.event_type == "report.generated"]) == 1

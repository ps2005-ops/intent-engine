"""T015 end-to-end: one deterministic fixture across all stores, a
combined snapshot, the calibration gate flipping at 30, and the language
wall over everything analytics emits."""
import json

import pytest

from intent_engine.analytics import AnalyticsService
from intent_engine.core.decision_record import DecisionService
from intent_engine.core.prediction_ledger import (
    record_prediction, resolve_prediction,
)
from intent_engine.crm import CRMService
from intent_engine.events import CompanyEventBus, bridge_decision_events, drain

AS_OF = "2026-12-31T00:00:00+00:00"


@pytest.fixture()
def world(tmp_path):
    ds = DecisionService(str(tmp_path / "decisions.db"))
    crm = CRMService(tmp_path / "crm.jsonl")
    bus = CompanyEventBus(tmp_path / "events")
    ledger = tmp_path / "ledger.db"

    # decisions in mixed states, one superseded
    a = ds.create_decision("founder", occurred_at="2026-07-01T00:00:00+00:00")
    for ev in ("RecommendationIssued", "DecisionSubmitted", "DecisionApproved",
               "ExecutionStarted"):
        ds.record_event(a.decision_id, ev, actor_type="human",
                        actor_id="founder", source="cli",
                        occurred_at="2026-07-02T00:00:00+00:00")
    old = ds.create_decision("founder")
    new = ds.create_decision("founder")
    ds.supersede_decision(old.decision_id, new.decision_id)

    # predictions below the gate
    for i in range(5):
        p = record_prediction(source="premortem", entity_id="e",
                              claim_text=f"c{i}", probability=0.6,
                              resolve_by="2026-07-01", path=ledger,
                              decision_id=a.decision_id)
        resolve_prediction(p.id, "happened", path=ledger)

    # CRM entities across stages
    j = crm.create_prospect(email="jane@acme.com")
    for ev in ("crm.qualified", "crm.opportunity_opened", "crm.won",
               "crm.customer_activated"):
        crm.record(j, ev, actor_type="human", actor_id="founder")
    k = crm.create_prospect(email="kim@beta.com")
    crm.record(k, "crm.contacted", actor_type="human", actor_id="founder")
    crm.link_decision(j, a.decision_id, decision_service=ds)

    # events + report success/failure + a lagging/broken consumer
    bridge_decision_events(ds, bus)
    bus.publish("report.generated", subject_type="report", subject_id="r1",
                producer="report_renderer", actor_type="system",
                actor_id="report_renderer", source="system",
                decision_id=a.decision_id, idempotency_key="r1")
    bus.publish("report.generation_failed", subject_type="report",
                subject_id="r2", producer="report_renderer",
                actor_type="system", actor_id="report_renderer",
                source="system", idempotency_key="r2")

    class Broken:
        consumer_name = "flaky"

        def handles(self, t):
            return True

        def process(self, e):
            raise RuntimeError("down")

    drain(bus, Broken(), max_attempts=1)
    return AnalyticsService(decision_service=ds, crm_service=crm,
                            event_store=bus.store, ledger_path=ledger), ledger


def test_snapshot_is_deterministic_and_complete(world):
    svc, _ = world
    snap1 = svc.snapshot(as_of=AS_OF)
    assert set(snap1["sections"]) == {"decisions", "calibration", "crm_funnel",
                                      "reports", "consumer_health"}
    assert snap1["as_of"] == AS_OF
    assert snap1["metric_versions"]["calibration_metrics"] == "calibration_metrics.v1"
    # deterministic for fixed as_of, modulo the computed_at stamps
    snap2 = svc.snapshot(as_of=AS_OF)

    def strip(d):
        return json.loads(json.dumps(d, default=str).replace(
            "", ""))  # deep copy
    s1, s2 = strip(snap1), strip(snap2)
    for s in (s1, s2):
        for sec in s["sections"].values():
            for m in sec.values():
                m.pop("computed_at", None)
    assert s1 == s2
    # sanity of a few section values
    dec = snap1["sections"]["decisions"]
    assert dec["decisions_created"]["value"] == 3
    assert dec["decisions_superseded"]["value"] == 1
    cal = snap1["sections"]["calibration"]["calibration"]
    assert cal["status"] == "TOO FEW RESOLVED TO CLAIM CALIBRATION"
    crm_dist = snap1["sections"]["crm_funnel"][
        "crm_current_stage_distribution"]["value"]
    assert crm_dist["customer"]["active"] == 1
    health = snap1["sections"]["consumer_health"]["consumers"]["value"]
    assert health["crm" if "crm" in health else "flaky"] is not None
    assert snap1["sections"]["reports"]["reports_generated"]["value"] == 1


def test_expanding_fixture_to_gate_flips_calibration(world):
    svc, ledger = world
    for i in range(25):                                # 5 + 25 = 30 resolved
        p = record_prediction(source="premortem", entity_id="e",
                              claim_text=f"more {i}", probability=0.6,
                              resolve_by="2026-07-01", path=ledger)
        resolve_prediction(p.id, "did_not_happen", path=ledger)
    m = svc.calibration_metrics(as_of=AS_OF)
    assert m["calibration"].status == "OK"
    assert m["calibration"].value["resolved_count"] == 30
    assert any("founder calibration review" in a
               for a in m["calibration"].annotations)


def test_language_wall_over_all_analytics_output(world):
    import re
    svc, _ = world
    blob = json.dumps(svc.snapshot(as_of=AS_OF), default=str).lower()
    for banned in ("accura", "well calibrated", "guarantee",
                   "causal", "engagement score", "track record",
                   "hit rate", "win rate"):
        assert banned not in blob, banned
    # word-boundary terms ('provenance' is a field name, not a claim)
    for pattern in (r"\bproven\b", r"\bpredicts\b", r"\bcertain\b"):
        assert not re.search(pattern, blob), pattern
    # honest markers survive
    assert "too few resolved to claim calibration" in blob
    assert "no observation source" in blob


def test_analytics_never_writes_to_any_store(world, tmp_path):
    svc, ledger = world
    files = {}
    for p in [svc.crm_service.store.path, svc.event_store.log_path,
              svc.event_store.checkpoint_path]:
        files[p] = p.read_bytes()
    svc.snapshot(as_of=AS_OF)
    for p, before in files.items():
        assert p.read_bytes() == before

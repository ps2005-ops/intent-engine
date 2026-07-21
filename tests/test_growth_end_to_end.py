"""T018 end-to-end: the full arc, the refusal, integration, snapshots,
the consumer, and the repository invariants. 0 model calls."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from intent_engine.analytics import AnalyticsService
from intent_engine.core.decision_record import DecisionService
from intent_engine.crm import CRMService
from intent_engine.events import CompanyEventBus, drain, replay
from intent_engine.growth import (
    NAMESPACE_PRODUCTION, NAMESPACE_SYNTHETIC, GrowthError, GrowthService,
    capture_snapshot,
)
from intent_engine.growth.snapshots import get_snapshot
from intent_engine.knowledge import KnowledgeService
from intent_engine.marketing import MarketingService

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_sibling(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_reg = _load_sibling("test_growth_registration")
_res = _load_sibling("test_growth_results")
register, ARMS = _reg.register, _reg.ARMS
populate = _res._populate


@pytest.fixture()
def world(tmp_path):
    ds = DecisionService(str(tmp_path / "decisions.db"))
    crm = CRMService(tmp_path / "crm.jsonl")
    know = KnowledgeService(tmp_path / "feedback.jsonl",
                            tmp_path / "knowledge.jsonl")
    bus = CompanyEventBus(tmp_path / "events")
    mkt = MarketingService(tmp_path / "marketing.jsonl", crm_service=crm)
    ledger = tmp_path / "ledger.db"
    svc = GrowthService(tmp_path, NAMESPACE_PRODUCTION, crm_service=crm,
                        knowledge_service=know, decision_service=ds,
                        event_bus=bus, ledger_path=ledger)
    return svc, ds, crm, know, bus, mkt, ledger, tmp_path


# =============================================================================
# Scenario A — the full arc
# =============================================================================

def test_full_experiment_arc(world):
    svc, ds, crm, know, bus, mkt, ledger, tmp = world

    # a marketing campaign and a CRM audience exist upstream
    campaign = mkt.create_campaign("CTA test", objective="lift replies",
                                   channel="linkedin", owner="Pratham")
    for i in range(4):
        eid_crm = crm.create_prospect(email=f"p{i}@x.com")
        crm.record(eid_crm, "crm.qualified", actor_type="human",
                   actor_id="founder")

    # the originating decision, so provenance is real
    decision = ds.create_decision("founder", idempotency_key="cta-decision")

    experiment = register(svc, decision_id=decision.decision_id,
                          campaign_id=campaign, minimum=20)
    reg = svc.get_registration(experiment)
    assert reg["provenance"]["originating_decision_id"] == decision.decision_id
    assert reg["provenance"]["campaign_id"] == campaign

    # the hypothesis is ledgered as a real prediction, graded by the ledger
    prediction_id = svc.link_hypothesis_prediction(
        experiment, claim_text="the shorter CTA lifts reply rate by launch+30d",
        probability=0.6, resolve_by="2026-12-01",
        decision_id=decision.decision_id)
    from intent_engine.core.prediction_ledger import list_predictions
    assert [p.id for p in list_predictions(path=ledger)] == [prediction_id]

    svc.start_experiment(experiment, actor_id="founder")
    assert any(e.event_type == "growth.experiment_started"
               for e in bus.store.read_all())

    # first batch: below the pre-registered minimum
    populate(svc, experiment, per_arm=5, control_successes=2,
             treatment_successes=3, prefix="batch1-")
    first = svc.get_result(experiment)
    assert first["label"] == "TOO FEW OBSERVATIONS"

    # peeking is recorded, not hidden
    svc.record_interim_read(experiment, actor_id="founder", note="early look")

    # more observations arrive
    populate(svc, experiment, per_arm=45, control_successes=9,
             treatment_successes=27, prefix="batch2-")

    outcome = svc.evaluate_stopping_rules(
        experiment, as_of="2026-09-01T00:00:00+00:00")
    assert outcome["satisfied"] is True
    assert svc.get_state(experiment).stopped is False   # not auto-stopped

    svc.stop_experiment(experiment, "stopping rule satisfied",
                        actor_id="founder")
    result = svc.get_result(experiment)
    assert result["label"] == "DIFFERENCE OBSERVED"
    assert "REVIEW REQUIRED" in result["modifiers"]
    assert result["interim_read_count"] == 1

    snapshot = capture_snapshot(svc, experiment,
                                as_of="2026-09-01T00:00:00+00:00")
    assert snapshot["experiment_version"] == 1
    assert snapshot["versions"]["label_rule_version"] == "result_label.v1"
    assert snapshot["source_high_watermarks"]["observations"] > 0

    svc.request_review(experiment)
    svc.record_review(experiment,
                      conclusion="the arms differed under the registered "
                                 "analysis; adopt the shorter CTA and re-run",
                      actor_id="founder", snapshot_id=snapshot["snapshot_id"])

    conclusion = ds.create_decision("founder", idempotency_key="cta-conclusion")
    svc.link_decision(experiment, conclusion.decision_id, actor_id="founder")
    assert conclusion.decision_id in svc.get_state(experiment).decision_ids

    feedback_id = svc.request_knowledge_candidate(
        experiment, content="shorter CTA associated with more replies in one "
                            "registered experiment", actor_id="founder")
    assert know.get_feedback(feedback_id)
    assert know.search_knowledge() == []            # NOT promoted

    # replay everything: zero duplicates anywhere
    rows_before = len(svc.store.read_all())
    knowledge_before = len(know.feedback.read_all())
    svc.request_knowledge_candidate(
        experiment, content="shorter CTA associated with more replies in one "
                            "registered experiment", actor_id="founder")
    capture_snapshot(svc, experiment, as_of="2026-09-01T00:00:00+00:00")
    svc.link_decision(experiment, conclusion.decision_id, actor_id="founder")
    assert len(svc.store.read_all()) == rows_before
    assert len(know.feedback.read_all()) == knowledge_before

    # the snapshot is reproducible from the log
    reread = get_snapshot(svc, experiment, snapshot["snapshot_id"])
    assert reread["label"] == snapshot["label"]
    assert reread["per_arm"] == snapshot["per_arm"]
    recomputed = svc.get_result(experiment)
    assert recomputed["label"] == snapshot["label"]
    assert recomputed["per_arm"] == snapshot["per_arm"]

    # no forbidden vocabulary anywhere in the whole experiment record
    blob = json.dumps([r.payload for r in svc.get_history(experiment)],
                      default=str).lower()
    import re
    for pattern in (r"\bwinner\b", r"\bwon\b", r"\bproven\b",
                    r"\bsignificant\b", r"\bcaused\b"):
        assert not re.search(pattern, blob), pattern


# =============================================================================
# Scenario B — the refusal
# =============================================================================

def test_insufficient_sample_refuses_everything(world):
    svc, ds, crm, know, bus, mkt, ledger, tmp = world
    experiment = register(svc, minimum=30)
    svc.start_experiment(experiment, actor_id="founder")
    populate(svc, experiment, per_arm=4, control_successes=1,
             treatment_successes=3)

    result = svc.get_result(experiment)
    assert result["label"] == "TOO FEW OBSERVATIONS"
    assert "NO CAUSAL CLAIM" in result["modifiers"]
    assert result["statistic"]["status"] == "UNAVAILABLE"

    # no winner exists to declare
    assert "winner" not in result
    # no rollout API exists at any layer
    for banned in ("rollout", "roll_out", "rollback", "launch", "promote_arm"):
        assert not [m for m in dir(svc) if banned in m.lower()]

    # knowledge is not promoted, and a candidate is labelled as observation only
    svc.request_review(experiment)
    svc.record_review(experiment, conclusion="not enough data to conclude",
                      actor_id="founder")
    fid = svc.request_knowledge_candidate(
        experiment, content="no usable read yet", actor_id="founder")
    row = know.get_feedback(fid)[0]
    assert "TOO FEW OBSERVATIONS" in row.payload["content"]
    assert "supports no conclusion" in row.payload["content"]
    assert know.search_knowledge() == []


def test_no_control_arm_never_earns_a_causal_claim(world):
    svc, *_ = world
    one_arm = [{"arm_id": "single", "is_control": False, "allocation": 1.0}]
    experiment = register(svc, arms=one_arm, minimum=2)
    svc.start_experiment(experiment, actor_id="founder")
    for i in range(30):
        entity = f"e{i}"
        svc.assign_entity(experiment, entity)
        svc.record_exposure(experiment, entity, exposure_key="s")
        svc.record_observation(experiment, entity, metric_name="reply_rate",
                               outcome_value=(i % 3 != 0), source="crm",
                               window_start="2026-08-01",
                               window_end="2026-08-14")
    result = svc.get_result(experiment)
    assert result["label"] == "OBSERVATIONAL ONLY"
    assert "NO CAUSAL CLAIM" in result["modifiers"]
    assert result["participation_funnel"]["totals"]["observed"] == 30


# =============================================================================
# Integration, consumer, namespaces, invariants
# =============================================================================

def test_knowledge_candidate_requires_human_review_first(world):
    svc, *_ = world
    experiment = register(svc, minimum=2)
    svc.start_experiment(experiment, actor_id="founder")
    with pytest.raises(GrowthError, match="requires human review"):
        svc.request_knowledge_candidate(experiment, content="x",
                                        actor_id="founder")


def test_decision_link_requires_review_and_a_real_decision(world):
    svc, ds, *_ = world
    experiment = register(svc, minimum=2)
    svc.start_experiment(experiment, actor_id="founder")
    populate(svc, experiment, per_arm=3, control_successes=1,
             treatment_successes=2)
    with pytest.raises(GrowthError, match="after human review"):
        svc.link_decision(experiment, "Z" * 26, actor_id="founder")
    svc.request_review(experiment)
    svc.record_review(experiment, conclusion="inconclusive", actor_id="founder")
    with pytest.raises(KeyError, match="no such decision"):
        svc.link_decision(experiment, "Z" * 26, actor_id="founder")


def test_consumer_observes_only_assigned_entities_and_replays_safely(world):
    svc, ds, crm, know, bus, mkt, ledger, tmp = world
    from intent_engine.growth.consumer import GrowthCompanyEventConsumer
    experiment = register(svc, minimum=2)
    svc.start_experiment(experiment, actor_id="founder")
    svc.assign_entity(experiment, "known-entity")
    svc.record_exposure(experiment, "known-entity", exposure_key="s")

    consumer = GrowthCompanyEventConsumer(
        svc, outcome_event_types={"reply_rate"})
    assert consumer.consumer_name == "growth_production"
    assert consumer.handles("reply_rate") and not consumer.handles("crm.won")

    class _Ev:
        event_type = "reply_rate"
        event_id = "EV1"
        occurred_at = "2026-08-05T00:00:00+00:00"
        subject_type = "crm_entity"
        subject_id = "known-entity"
        crm_entity_id = "known-entity"

    consumer.process(_Ev())
    assert consumer.observed == 1
    consumer.process(_Ev())                    # replay: idempotent
    assert len([r for r in svc.get_history(experiment)
                if r.event_type == "growth.observation_recorded"]) == 1

    class _Unknown(_Ev):
        subject_id = "stranger"
        crm_entity_id = "stranger"

    consumer.process(_Unknown())               # never guesses
    assert consumer.skipped >= 1


def test_synthetic_and_production_replay_independently(tmp_path):
    prod = GrowthService(tmp_path, NAMESPACE_PRODUCTION)
    synth = GrowthService(tmp_path, NAMESPACE_SYNTHETIC)
    from intent_engine.growth.consumer import GrowthCompanyEventConsumer
    assert GrowthCompanyEventConsumer(prod).consumer_name == "growth_production"
    assert GrowthCompanyEventConsumer(synth).consumer_name == "growth_synthetic"
    p = register(prod, minimum=2)
    s = register(synth, minimum=2)
    assert prod.store.experiment_ids() == [p]
    assert synth.store.experiment_ids() == [s]


def test_repository_invariants(world):
    """Improvement 10: one owner per artifact, no duplicated implementations."""
    svc, ds, crm, know, bus, mkt, ledger, tmp = world
    import intent_engine.growth.randomization as rnd
    import intent_engine.growth.statistics as stats

    # exactly one randomization implementation and one assignment function
    assert rnd.assign.__module__ == "intent_engine.growth.randomization"
    growth_src = (REPO_ROOT / "src/intent_engine/growth")
    assignment_defs = sum(
        f.read_text().count("def assign(") for f in growth_src.glob("*.py"))
    assert assignment_defs == 1

    # exactly one statistical implementation; nobody else computes intervals
    for other in ("analytics", "marketing", "crm", "knowledge"):
        pkg = REPO_ROOT / "src/intent_engine" / other
        for f in pkg.glob("*.py"):
            text = f.read_text()
            assert "difference_in_proportions" not in text, f
            assert "interval_excludes_zero" not in text, f

    # growth never writes another subsystem's store
    service_src = (growth_src / "service.py").read_text()
    for forbidden in ("crm.jsonl", "knowledge.jsonl", "feedback.jsonl",
                      "marketing.jsonl", "events.jsonl"):
        assert forbidden not in service_src

    # every read model is reproducible from the append-only history
    experiment = register(svc, minimum=2)
    svc.start_experiment(experiment, actor_id="founder")
    populate(svc, experiment, per_arm=3, control_successes=1,
             treatment_successes=2)
    first = svc.get_result(experiment)
    fresh = GrowthService(tmp, NAMESPACE_PRODUCTION)
    assert fresh.get_result(experiment) == first


def test_frozen_assets_untouched(world):
    svc, ds, crm, know, bus, mkt, ledger, tmp = world
    lib = REPO_ROOT / "src/intent_engine/core/data/mechanisms.json"
    analyzer = REPO_ROOT / "src/intent_engine/simulator/analysis.py"
    before = (lib.read_bytes(), analyzer.read_bytes())
    experiment = register(svc, minimum=2)
    svc.start_experiment(experiment, actor_id="founder")
    populate(svc, experiment, per_arm=3, control_successes=1,
             treatment_successes=2)
    capture_snapshot(svc, experiment, as_of="2026-09-01T00:00:00+00:00")
    assert (lib.read_bytes(), analyzer.read_bytes()) == before

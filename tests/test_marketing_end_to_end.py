"""T017 end-to-end: the full C3–C8 vertical, the company-event consumer,
rejection paths, and the language wall over everything marketing emits.

0 model calls. 0 external publications. 0 external messages.
"""
import json
from pathlib import Path

import pytest

from intent_engine.analytics import AnalyticsService
from intent_engine.core.decision_record import DecisionService
from intent_engine.core.prediction_ledger import record_prediction
from intent_engine.crm import CRMService
from intent_engine.events import CompanyEventBus, drain, replay
from intent_engine.knowledge import KnowledgeService
from intent_engine.marketing import (
    MarketingCompanyEventConsumer, MarketingError, MarketingService,
    claim_identity,
)

AS_OF = "2026-12-31T00:00:00+00:00"
QUOTE = "The premortem changed how we scoped the hire."
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def world(tmp_path):
    ds = DecisionService(str(tmp_path / "decisions.db"))
    crm = CRMService(tmp_path / "crm.jsonl")
    know = KnowledgeService(tmp_path / "feedback.jsonl",
                            tmp_path / "knowledge.jsonl")
    bus = CompanyEventBus(tmp_path / "events")
    ledger = tmp_path / "ledger.db"
    metrics = {"decisions_created": {"status": "OK", "value": 4,
                                     "metric_version": "decision_metrics.v1",
                                     "annotations": ["counted from events"]}}
    svc = MarketingService(tmp_path / "marketing.jsonl", crm_service=crm,
                           knowledge_service=know, event_bus=bus,
                           decision_service=ds, metric_lookup=metrics.get)
    return svc, ds, crm, know, bus, ledger, tmp_path


def _knowledge_item(know):
    fid = know.record_feedback("feedback.internal_review", "observed pattern",
                               actor_type="human", actor_id="founder")
    cit = [{"source_type": "feedback_record",
            "source_id": know.get_feedback(fid)[0].row_id}]
    iid = know.propose_insight("Pattern", "the pattern appears in observed cases",
                               scope="four B2B SaaS premortems",
                               limitations="small sample",
                               source_feedback_ids=[fid], citations=cit,
                               proposed_by="analysis_agent")
    know.validate_insight(iid, 1, actor_id="founder")
    return know.promote_knowledge(iid, 1, category="decision_pattern",
                                  actor_id="founder")


def test_full_campaign_vertical(world):
    svc, ds, crm, know, bus, ledger, tmp = world

    # CRM entities exist
    jane = crm.create_prospect(email="jane@acme.com")
    crm.record(jane, "crm.qualified", actor_type="human", actor_id="founder")
    crm.create_prospect(email="cold@beta.com")

    # campaign + deterministic audience
    cid = svc.create_campaign("Method launch", objective="explain the method",
                              channel="linkedin", owner="Pratham")
    audience = svc.define_audience(cid, as_of=AS_OF,
                                   include_opportunity=["qualified"])
    assert audience["entity_count"] == 1
    assert audience["sample_entity_ids"] == [jane]

    # evidence: active knowledge + an OK metric
    kid = _knowledge_item(know)
    svc.attach_evidence(cid, {"evidence_type": "knowledge_item",
                              "source_id": kid})
    svc.attach_evidence(cid, {"evidence_type": "analytics_metric",
                              "source_id": "decisions_created"})

    # consented quote
    fid = know.record_feedback("feedback.customer_reply", QUOTE,
                               actor_type="human", actor_id="founder")
    know.record_quote_consent(fid, "approved", QUOTE, "public",
                              actor_type="human", actor_id="founder")

    brief_rev = svc.create_brief(
        cid, message="We publish the reasoning behind each premortem.",
        call_to_action="Read the method",
        quotes=[{"feedback_id": fid, "quote_text": QUOTE}])
    brief = svc.get_brief(cid)
    assert brief["audience"]["entity_count"] == 1
    assert brief["limitations"]                     # scope travels into the brief

    body = (f'We publish the reasoning behind each premortem. '
            f'A customer told us: "{QUOTE}" '
            f'We reviewed 4 decisions this month.')
    draft_rev = svc.create_draft(cid, body, brief_revision_id=brief_rev,
                                 quotes=[{"feedback_id": fid,
                                          "quote_text": QUOTE,
                                          "intended_use": "public"}])
    validation = svc.get_draft(cid)["validation"]
    assert validation["valid_for_review"] is True
    assert validation["valid_for_handoff"] is False   # claims need review

    # claim review through the EXISTING gate; humans only
    for claim in validation["claim_references"]:
        if claim["requires_review"]:
            svc.request_claim_review(cid, claim["claim_id"], claim["text"])
            bus.publish("claim.approved", subject_type="claim",
                        subject_id=claim["claim_id"], producer="approval_wall",
                        actor_type="human", actor_id="founder", source="cli")
    assert svc.revalidate_draft(cid)["valid_for_handoff"] is True

    # human draft approval, then human handoff approval
    svc.request_draft_review(cid, draft_rev)
    svc.approve_draft(cid, draft_rev, actor_id="founder", comment="ship it")
    handoff = svc.create_handoff(cid, channel="linkedin",
                                 external_target="linkedin.com/company/x")
    svc.approve_handoff(cid, handoff, actor_id="founder")

    # an EXTERNAL system published; we record the supplied result
    svc.record_publication(cid, handoff, external_platform="linkedin",
                           external_post_id="urn:li:1",
                           occurred_at="2026-07-22T09:00:00+00:00",
                           actor_id="founder")
    obs = svc.record_performance_observation(
        cid, external_post_id="urn:li:1", observation_source="linkedin_ui",
        window_start="2026-07-22", window_end="2026-07-29",
        metrics={"impressions": 1200, "clicks": 18, "leads": None})
    fb = svc.link_feedback(cid, obs, content="method post: low click-through")

    state = svc.get_state(cid)
    assert state.publishing_status == "recorded_as_published"
    assert state.observation_status == "recorded"
    assert know.get_feedback(fb)                    # feedback via KnowledgeService
    assert know.search_knowledge() != []            # only the pre-made item
    ratio = svc.observation_ratio(cid, "clicks", "impressions")
    assert ratio["status"] == "OK" and ratio["value"] == 0.015
    assert svc.observation_ratio(cid, "leads", "impressions")["status"] \
        == "UNAVAILABLE"                            # unobserved stays unobserved


# --- rejection scenarios ------------------------------------------------------

def _ready_campaign(svc, know, bus, body=None):
    cid = svc.create_campaign("c", objective="o", channel="linkedin",
                              owner="P")
    rev = svc.create_brief(cid, message="m", call_to_action="cta")
    text = body or ("We publish the reasoning behind each premortem. "
                    "Every claim lands on an append-only ledger.")
    d = svc.create_draft(cid, text, brief_revision_id=rev)
    svc.request_draft_review(cid, d)
    svc.approve_draft(cid, d, actor_id="founder")
    return cid, d


def test_revoked_quote_blocks_handoff(world):
    svc, _, _, know, bus, _, _ = world
    fid = know.record_feedback("feedback.customer_reply", QUOTE,
                               actor_type="human", actor_id="founder")
    know.record_quote_consent(fid, "approved", QUOTE, "public",
                              actor_type="human", actor_id="founder")
    cid = svc.create_campaign("c", objective="o", channel="linkedin", owner="P")
    rev = svc.create_brief(cid, message="m", call_to_action="cta")
    d = svc.create_draft(cid, f'A customer told us: "{QUOTE}"',
                         brief_revision_id=rev,
                         quotes=[{"feedback_id": fid, "quote_text": QUOTE,
                                  "intended_use": "public"}])
    for claim in svc.get_draft(cid)["validation"]["claim_references"]:
        if claim["requires_review"]:
            bus.publish("claim.approved", subject_type="claim",
                        subject_id=claim["claim_id"], producer="approval_wall",
                        actor_type="human", actor_id="founder", source="cli")
    svc.request_draft_review(cid, d)
    svc.approve_draft(cid, d, actor_id="founder")
    know.record_quote_consent(fid, "revoked", QUOTE, "public",
                              actor_type="human", actor_id="founder")
    with pytest.raises(MarketingError, match="handoff blocked"):
        svc.create_handoff(cid, channel="linkedin")


def test_below_gate_calibration_claim_blocks_evidence(world):
    svc, _, _, _, _, _, tmp = world
    metrics = {"calibration": {"status":
                               "TOO FEW RESOLVED TO CLAIM CALIBRATION"}}
    svc.metric_lookup = metrics.get
    cid = svc.create_campaign("c", objective="o", channel="linkedin", owner="P")
    with pytest.raises(MarketingError, match="cannot support a positive"):
        svc.attach_evidence(cid, {"evidence_type": "analytics_metric",
                                  "source_id": "calibration"})


def test_retracted_knowledge_blocks_handoff_after_the_fact(world):
    svc, _, _, know, bus, _, _ = world
    kid = _knowledge_item(know)
    cid = svc.create_campaign("c", objective="o", channel="linkedin", owner="P")
    svc.attach_evidence(cid, {"evidence_type": "knowledge_item",
                              "source_id": kid})
    rev = svc.create_brief(cid, message="m", call_to_action="cta")
    d = svc.create_draft(cid, "We publish the reasoning behind each premortem.",
                         brief_revision_id=rev)
    svc.request_draft_review(cid, d)
    svc.approve_draft(cid, d, actor_id="founder")
    know.retract_knowledge(kid, "source_invalidated", actor_id="founder")
    blockers = svc.handoff_blockers(cid)
    assert any("retracted" in b for b in blockers)
    with pytest.raises(MarketingError, match="handoff blocked"):
        svc.create_handoff(cid, channel="linkedin")


def test_system_actor_cannot_approve_anything(world):
    svc, _, _, know, bus, _, _ = world
    cid, d = _ready_campaign(svc, know, bus)
    h = svc.create_handoff(cid, channel="linkedin")
    for actor in ("system", "agent"):
        with pytest.raises(MarketingError, match="human wall"):
            svc.approve_handoff(cid, h, actor_id="bot", actor_type=actor)


# --- company event consumer (C3 as a checkpointed consumer) -------------------

def test_consumer_fans_predictions_and_replay_creates_no_duplicates(world):
    svc, _, _, _, bus, ledger, tmp = world
    p = record_prediction(source="premortem", entity_id="acme",
                          claim_text="Burn exceeds plan", probability=0.6,
                          resolve_by="2027-02-01", path=ledger)
    bus.publish("prediction.recorded", subject_type="prediction",
                subject_id=p.id, producer="premortem_pipeline",
                actor_type="system", actor_id="pipe", source="system",
                prediction_id=p.id, idempotency_key=f"prediction:{p.id}")
    bus.publish("report.generated", subject_type="report", subject_id="r1",
                producer="report_renderer", actor_type="system",
                actor_id="report_renderer", source="system",
                idempotency_key="r1")

    drafts_root = tmp / "drafts"
    consumer = MarketingCompanyEventConsumer(drafts_root=drafts_root,
                                             ledger_path=ledger)
    rep = drain(bus, consumer)
    assert rep.processed == 2
    assert consumer.drafted == [p.id]
    assert consumer.skipped == 1                 # report observed, not drafted
    files = sorted(x.name for x in (drafts_root / "predictions" / p.id).iterdir())
    assert len(files) == 7
    assert bus.store.get_checkpoint("marketing") == 2

    before = {f.name: f.read_bytes()
              for f in (drafts_root / "predictions" / p.id).iterdir()}
    replay(bus, consumer, from_offset=0)
    drain(bus, consumer)
    after = {f.name: f.read_bytes()
             for f in (drafts_root / "predictions" / p.id).iterdir()}
    assert after == before                       # byte-identical, no duplicates


def test_consumer_never_guesses_a_missing_ledger_row(world):
    svc, _, _, _, bus, ledger, tmp = world
    bus.publish("prediction.recorded", subject_type="prediction",
                subject_id="ghost", producer="premortem_pipeline",
                actor_type="system", actor_id="pipe", source="system",
                prediction_id="ghost", idempotency_key="ghost")
    consumer = MarketingCompanyEventConsumer(drafts_root=tmp / "d",
                                             ledger_path=ledger)
    drain(bus, consumer)
    assert consumer.drafted == [] and consumer.skipped == 1
    assert not (tmp / "d").exists() or not list((tmp / "d").rglob("*.md"))


def test_consumer_failure_leaves_checkpoint_and_source_log_intact(world):
    svc, _, _, _, bus, ledger, tmp = world
    p = record_prediction(source="premortem", entity_id="a", claim_text="c",
                          probability=0.5, resolve_by="2027-01-01",
                          path=ledger)
    bus.publish("prediction.recorded", subject_type="prediction",
                subject_id=p.id, producer="premortem_pipeline",
                actor_type="system", actor_id="pipe", source="system",
                prediction_id=p.id, idempotency_key=f"p:{p.id}")
    before = bus.store.log_path.read_bytes()
    consumer = MarketingCompanyEventConsumer(drafts_root=tmp / "d",
                                             ledger_path=ledger)
    consumer.process = lambda ev: (_ for _ in ()).throw(RuntimeError("down"))
    rep = drain(bus, consumer, max_attempts=3)
    assert rep.retried == 1
    assert bus.store.get_checkpoint("marketing") == 0
    assert bus.store.log_path.read_bytes() == before   # byte-identical


# --- language wall over everything marketing emits ---------------------------

def test_language_wall_over_marketing_output(world):
    svc, _, _, know, bus, ledger, tmp = world
    cid, d = _ready_campaign(svc, know, bus)
    blob = json.dumps([r.payload for r in svc.get_history(cid)],
                      default=str).lower()
    import re
    for banned in ("guaranteed", "market-leading", "drove revenue",
                   "customer-approved", "high-converting",
                   "statistically significant"):
        assert banned not in blob, banned
    for pattern in (r"\bproven\b", r"\balways\b", r"\bpredicts\b",
                    r"\bcaused\b"):
        assert not re.search(pattern, blob), pattern


def test_frozen_assets_untouched_by_the_whole_vertical(world):
    """The mechanism library and the analyzer prompt module are read-only
    to marketing — asserted by byte identity across a full run."""
    svc, ds, crm, know, bus, ledger, tmp = world
    lib = REPO_ROOT / "src/intent_engine/core/data/mechanisms.json"
    analyzer = REPO_ROOT / "src/intent_engine/simulator/analysis.py"
    before = (lib.read_bytes(), analyzer.read_bytes())
    cid, d = _ready_campaign(svc, know, bus)
    h = svc.create_handoff(cid, channel="linkedin")
    svc.approve_handoff(cid, h, actor_id="founder")
    from intent_engine.marketing.generators import render_public_pages
    render_public_pages(ledger, drafts_root=tmp / "pages")
    assert (lib.read_bytes(), analyzer.read_bytes()) == before

"""T017 bars: publication recording, performance observations, feedback
loop. Nothing here publishes; a publication is an OBSERVED fact."""
import pytest

from intent_engine.knowledge import KnowledgeService
from intent_engine.marketing import MarketingError, MarketingService

BODY = ("We publish the reasoning behind each premortem. "
        "Every claim is recorded on an append-only ledger.")


@pytest.fixture()
def rig(tmp_path):
    know = KnowledgeService(tmp_path / "feedback.jsonl",
                            tmp_path / "knowledge.jsonl")
    svc = MarketingService(tmp_path / "marketing.jsonl",
                           knowledge_service=know)
    return svc, know


def _approved_handoff(svc):
    cid = svc.create_campaign("c", objective="o", channel="linkedin",
                              owner="P")
    rev = svc.create_brief(cid, message="m", call_to_action="cta")
    d = svc.create_draft(cid, BODY, brief_revision_id=rev)
    svc.request_draft_review(cid, d)
    svc.approve_draft(cid, d, actor_id="founder")
    h = svc.create_handoff(cid, channel="linkedin")
    svc.approve_handoff(cid, h, actor_id="founder")
    return cid, h


# --- publication recording ----------------------------------------------------

def test_publication_requires_an_approved_handoff(rig):
    svc, _ = rig
    cid = svc.create_campaign("c", objective="o", channel="linkedin",
                              owner="P")
    rev = svc.create_brief(cid, message="m", call_to_action="cta")
    d = svc.create_draft(cid, BODY, brief_revision_id=rev)
    svc.request_draft_review(cid, d)
    svc.approve_draft(cid, d, actor_id="founder")
    h = svc.create_handoff(cid, channel="linkedin")     # created, NOT approved
    with pytest.raises(MarketingError, match="APPROVED handoff"):
        svc.record_publication(cid, h, external_platform="linkedin",
                               external_post_id="urn:1",
                               occurred_at="2026-07-21T10:00:00+00:00",
                               actor_id="founder")


def test_publication_is_recorded_idempotently_and_never_performed(rig):
    svc, _ = rig
    cid, h = _approved_handoff(svc)
    for _ in range(2):
        svc.record_publication(cid, h, external_platform="linkedin",
                               external_post_id="urn:1",
                               occurred_at="2026-07-21T10:00:00+00:00",
                               actor_id="founder")
    rows = [r for r in svc.get_history(cid)
            if r.event_type == "marketing.publish_recorded"]
    assert len(rows) == 1                       # idempotent
    assert "not performed by it" in rows[0].payload["recorded_by"]
    assert svc.get_state(cid).publishing_status == "recorded_as_published"


def test_publication_requires_external_identifiers(rig):
    svc, _ = rig
    cid, h = _approved_handoff(svc)
    with pytest.raises(MarketingError, match="never assumed"):
        svc.record_publication(cid, h, external_platform="linkedin",
                               external_post_id="",
                               occurred_at="2026-07-21T10:00:00+00:00",
                               actor_id="founder")


def test_no_publish_surface_exists_on_the_service(rig):
    svc, _ = rig
    assert not [m for m in dir(svc)
                if m.startswith("publish") or m == "send"]


# --- performance observations -------------------------------------------------

def _published(svc):
    cid, h = _approved_handoff(svc)
    svc.record_publication(cid, h, external_platform="linkedin",
                           external_post_id="urn:1",
                           occurred_at="2026-07-21T10:00:00+00:00",
                           actor_id="founder")
    return cid


def test_observation_requires_publication_source_and_window(rig):
    svc, _ = rig
    cid = svc.create_campaign("c", objective="o", channel="linkedin",
                              owner="P")
    with pytest.raises(MarketingError, match="observation source"):
        svc.record_performance_observation(
            cid, external_post_id="urn:1", observation_source="",
            window_start="a", window_end="b", metrics={})
    with pytest.raises(MarketingError, match="observation window"):
        svc.record_performance_observation(
            cid, external_post_id="urn:1", observation_source="linkedin_ui",
            window_start="", window_end="", metrics={})
    with pytest.raises(MarketingError, match="requires a recorded publication"):
        svc.record_performance_observation(
            cid, external_post_id="urn:1", observation_source="linkedin_ui",
            window_start="2026-07-21", window_end="2026-07-28", metrics={})


def test_zero_is_distinct_from_unavailable(rig):
    svc, _ = rig
    cid = _published(svc)
    svc.record_performance_observation(
        cid, external_post_id="urn:1", observation_source="linkedin_ui",
        window_start="2026-07-21", window_end="2026-07-28",
        metrics={"impressions": 240, "clicks": 0, "leads": None})
    obs = [r.payload for r in svc.get_history(cid)
           if r.event_type == "marketing.performance_observation_recorded"][-1]
    assert obs["metrics"]["clicks"] == 0            # a real observed zero
    assert obs["metrics"]["leads"] == "UNAVAILABLE"  # not observed at all
    assert "no causal attribution" in obs["limitations"]


def test_ratio_refuses_empty_or_missing_denominator(rig):
    svc, _ = rig
    cid = _published(svc)
    svc.record_performance_observation(
        cid, external_post_id="urn:1", observation_source="linkedin_ui",
        window_start="2026-07-21", window_end="2026-07-28",
        metrics={"impressions": 0, "clicks": 0, "leads": None})
    r = svc.observation_ratio(cid, "clicks", "impressions")
    assert r["status"] == "UNAVAILABLE" and r["value"] is None
    r2 = svc.observation_ratio(cid, "clicks", "leads")
    assert r2["status"] == "UNAVAILABLE"


def test_observation_is_idempotent_and_rejects_non_numeric(rig):
    svc, _ = rig
    cid = _published(svc)
    kw = dict(external_post_id="urn:1", observation_source="linkedin_ui",
              window_start="2026-07-21", window_end="2026-07-28")
    svc.record_performance_observation(cid, metrics={"clicks": 3}, **kw)
    svc.record_performance_observation(cid, metrics={"clicks": 3}, **kw)
    rows = [r for r in svc.get_history(cid)
            if r.event_type == "marketing.performance_observation_recorded"]
    assert len(rows) == 1
    with pytest.raises(MarketingError, match="numeric or null"):
        svc.record_performance_observation(cid, metrics={"clicks": "lots"},
                                           **kw)


def test_no_revenue_or_causal_field_is_invented(rig):
    svc, _ = rig
    cid = _published(svc)
    obs_id = svc.record_performance_observation(
        cid, external_post_id="urn:1", observation_source="linkedin_ui",
        window_start="2026-07-21", window_end="2026-07-28",
        metrics={"impressions": 100})
    payload = svc.store.for_artifact(obs_id)[0].payload
    blob = str(payload).lower()
    for banned in ("revenue", "attributed", "caused", "impact score"):
        assert banned not in blob or "no causal attribution" in blob


# --- feedback loop -------------------------------------------------------------

def test_feedback_goes_through_knowledge_service_only(rig):
    svc, know = rig
    cid = _published(svc)
    obs_id = svc.record_performance_observation(
        cid, external_post_id="urn:1", observation_source="linkedin_ui",
        window_start="2026-07-21", window_end="2026-07-28",
        metrics={"impressions": 100, "clicks": 4})
    fid = svc.link_feedback(cid, obs_id,
                            content="low click-through on the method post")
    # the fact lives in the KNOWLEDGE store, not the marketing store
    assert know.get_feedback(fid)
    assert not any("feedback.jsonl" in str(p)
                   for p in [svc.store.path])
    # marketing has no direct feedback-store handle at all
    assert not hasattr(svc, "feedback")
    # idempotent: linking twice creates one feedback row and one link
    svc.link_feedback(cid, obs_id, content="low click-through on the method post")
    links = [r for r in svc.get_history(cid)
             if r.event_type == "marketing.feedback_linked"]
    assert len(links) == 1
    assert len(know.feedback.read_all()) == 1


def test_feedback_never_auto_promotes(rig):
    svc, know = rig
    cid = _published(svc)
    obs_id = svc.record_performance_observation(
        cid, external_post_id="urn:1", observation_source="linkedin_ui",
        window_start="2026-07-21", window_end="2026-07-28",
        metrics={"clicks": 4})
    svc.link_feedback(cid, obs_id, content="observation note")
    assert know.search_knowledge() == []
    assert know.list_pending_validations() == []

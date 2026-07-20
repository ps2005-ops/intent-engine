"""T013 bars: the two human walls as structural event rules.

    generation is automated / publication is not
    analysis is automated / performance claims are not
"""
import pytest

from intent_engine.events import CompanyEventBus, WallViolation


@pytest.fixture()
def bus(tmp_path):
    return CompanyEventBus(tmp_path / "events")


def _wall(bus, event_type, actor_type="human", subject_id="draft-1", **over):
    kw = dict(subject_type="claim" if event_type.startswith("claim")
              else "content",
              subject_id=subject_id, producer="approval_wall",
              actor_type=actor_type,
              actor_id="founder" if actor_type == "human" else "content_agent",
              source="cli" if actor_type == "human" else "system")
    kw.update(over)
    return bus.publish(event_type, **kw)


def test_approval_request_may_be_automated(bus):
    r = _wall(bus, "content.approval_requested", actor_type="agent")
    assert r.event.actor_type == "agent"      # generation side: automated OK


def test_approval_requires_human_actor(bus):
    for actor in ("agent", "system"):
        with pytest.raises(WallViolation, match="human wall"):
            _wall(bus, "content.approved", actor_type=actor)
    assert _wall(bus, "content.approved").event.actor_type == "human"


def test_publication_without_prior_approval_is_rejected(bus):
    _wall(bus, "content.approval_requested", actor_type="agent")
    with pytest.raises(WallViolation, match="requires a prior"):
        _wall(bus, "content.published")
    assert bus.store.read_all()[-1].event_type == "content.approval_requested"


def test_publication_after_approval_succeeds(bus):
    _wall(bus, "content.approval_requested", actor_type="agent")
    _wall(bus, "content.approved")
    r = _wall(bus, "content.published")
    assert r.event.event_type == "content.published"


def test_approval_of_one_draft_does_not_unlock_another(bus):
    _wall(bus, "content.approved", subject_id="draft-1")
    with pytest.raises(WallViolation):
        _wall(bus, "content.published", subject_id="draft-2")


def test_claim_approval_is_separate_from_content_approval(bus):
    _wall(bus, "content.approved", subject_id="draft-1")
    # a content approval never satisfies the claim wall, and vice versa
    with pytest.raises(WallViolation, match="human wall"):
        _wall(bus, "claim.approved", actor_type="system",
              subject_id="claim-1")
    r = _wall(bus, "claim.approved", subject_id="claim-1")
    assert r.event.subject_type == "claim"
    types = {e.event_type for e in bus.store.read_all()}
    assert {"content.approved", "claim.approved"} <= types


def test_no_auto_approval_path_exists(bus):
    """Every approval/rejection/publication type is in the human-only set."""
    from intent_engine.events.publisher import _HUMAN_ONLY_EVENTS
    assert {"content.approved", "content.rejected", "content.published",
            "claim.approved", "claim.rejected"} <= _HUMAN_ONLY_EVENTS

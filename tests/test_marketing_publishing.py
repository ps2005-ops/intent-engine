"""Marketing publishing adapter (3C/3D): dry-run default, real disabled,
idempotent, human-walled. No real publication ever happens in tests."""
import pytest

from intent_engine.events import CompanyEventBus
from intent_engine.marketing.publishing import (
    APPROVAL_REQUIRED, TRUSTED_AUTONOMY, PublishingAdapter, PublishingDisabled,
    PublishingError,
)


def _adapter(tmp_path, **kw):
    bus = CompanyEventBus(tmp_path / "events")
    return PublishingAdapter(bus=bus, allowlist=("linkedin",), **kw), bus


def test_dry_run_is_default_and_simulated(tmp_path):
    a, bus = _adapter(tmp_path)
    r = a.publish(campaign_id="C1", revision_id="R1", channel="linkedin",
                  body="hello", dry_run=True)
    assert r.dry_run and r.status == "simulated"
    assert r.external_post_id and r.external_post_id.startswith("sim_")
    types = [e.event_type for e in bus.store.read_all()]
    assert types == ["content.publish_dry_run"]
    assert "content.published" not in types      # never the real wall event


def test_dry_run_idempotent_no_duplicate(tmp_path):
    a, bus = _adapter(tmp_path)
    r1 = a.publish(campaign_id="C1", revision_id="R1", channel="linkedin",
                   body="x", dry_run=True)
    r2 = a.publish(campaign_id="C1", revision_id="R1", channel="linkedin",
                   body="x", dry_run=True)
    assert r1.external_post_id == r2.external_post_id
    dry = [e for e in bus.store.read_all()
           if e.event_type == "content.publish_dry_run"]
    assert len(dry) == 1                          # idempotency key deduped


def test_channel_not_on_allowlist_refused(tmp_path):
    a, _ = _adapter(tmp_path)
    with pytest.raises(PublishingError, match="allowlist"):
        a.publish(campaign_id="C1", revision_id="R1", channel="twitter",
                  body="x", dry_run=True)


def test_real_publish_disabled_without_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("PUBLISHING_ENABLED", raising=False)
    a, _ = _adapter(tmp_path, mode=APPROVAL_REQUIRED)
    with pytest.raises(PublishingDisabled):
        a.publish(campaign_id="C1", revision_id="R1", channel="linkedin",
                  body="x", approved=True, dry_run=False, actor_type="human")


def test_real_publish_requires_human_and_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISHING_ENABLED", "1")
    a, _ = _adapter(tmp_path, mode=APPROVAL_REQUIRED)
    # not approved
    with pytest.raises(PublishingError, match="approved"):
        a.publish(campaign_id="C1", revision_id="R1", channel="linkedin",
                  body="x", approved=False, dry_run=False, actor_type="human")
    # approved + human, but provider is a manual step -> still disabled
    with pytest.raises(PublishingDisabled, match="MANUAL"):
        a.publish(campaign_id="C1", revision_id="R1", channel="linkedin",
                  body="x", approved=True, dry_run=False, actor_type="human")


def test_trusted_autonomy_locked(tmp_path, monkeypatch):
    monkeypatch.delenv("MARKETING_TRUSTED_AUTONOMY", raising=False)
    with pytest.raises(PublishingError, match="TRUSTED_AUTONOMY"):
        PublishingAdapter(mode=TRUSTED_AUTONOMY)

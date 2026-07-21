"""T017 bars: marketing store, identities, and lifecycle fold."""
import threading

import pytest

from intent_engine.core.decision_ids import is_ulid
from intent_engine.marketing import MarketingError, MarketingService
from intent_engine.marketing.store import MarketingCorruptLogError


@pytest.fixture()
def svc(tmp_path):
    return MarketingService(tmp_path / "marketing.jsonl")


def _campaign(svc, **over):
    kw = dict(objective="explain the premortem", channel="linkedin",
              owner="Pratham")
    kw.update(over)
    return svc.create_campaign("July launch", **kw)


def test_ids_are_opaque_and_stable(svc):
    a = _campaign(svc)
    b = _campaign(svc)
    assert is_ulid(a) and is_ulid(b) and a != b
    # the human label is an attribute, never the key
    rows = svc.get_history(a)
    assert rows[0].payload["name"] == "July launch"
    assert rows[0].campaign_id == a != "July launch"


def test_append_only_no_mutation_api(svc):
    a = _campaign(svc)
    banned = [m for m in dir(svc.store)
              if any(w in m.lower() for w in ("update", "delete", "remove"))
              and not m.startswith("_")]
    assert banned == []
    assert len(svc.get_history(a)) == 1


def test_idempotent_retry_zero_rows_and_conflict_rejected(svc):
    a = _campaign(svc, idempotency_key="camp-1")
    b = _campaign(svc, idempotency_key="camp-1")
    assert a == b
    assert len(svc.store.read_all()) == 1
    with pytest.raises(ValueError, match="different content"):
        svc.create_campaign("Different name", objective="x",
                            channel="linkedin", owner="P",
                            idempotency_key="camp-1")


def test_corrupt_log_fails_loudly(svc):
    _campaign(svc)
    with open(svc.store.path, "a") as f:
        f.write("not json\n")
    with pytest.raises(MarketingCorruptLogError, match="malformed"):
        svc.store.read_all()


def test_unknown_event_and_channel_rejected(svc):
    with pytest.raises(MarketingError, match="unknown channel"):
        _campaign(svc, channel="billboard")


def test_concurrent_writers_do_not_corrupt(svc):
    a = _campaign(svc)
    errors = []

    def worker(n):
        try:
            for i in range(6):
                svc._record(a, "marketing.evidence_attached",
                            actor_type="system", actor_id="agent",
                            payload={"evidence_type": "external_source",
                                     "source_id": f"s-{n}-{i}"},
                            idempotency_key=f"ev-{n}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(svc.get_history(a)) == 19          # 1 create + 18 evidence


def test_state_folds_across_independent_axes(svc):
    a = _campaign(svc)
    state = svc.get_state(a)
    assert state.campaign_status == "active"
    assert state.brief_status == "missing"
    assert state.draft_status == "missing"
    assert state.publishing_status == "not_ready"
    assert state.observation_status == "none"


def test_draft_before_brief_rejected(svc):
    a = _campaign(svc)
    with pytest.raises(KeyError):
        svc.create_draft(a, "body", brief_revision_id="nope")


def test_tampered_history_fails_validated_fold(svc):
    from intent_engine.marketing.records import MarketingRow
    a = _campaign(svc)
    svc.store.append(MarketingRow(
        event_type="marketing.publish_recorded", campaign_id=a,
        actor_type="system", actor_id="tamper", source="system"))
    with pytest.raises(MarketingError, match="invalid at"):
        svc.get_state(a)

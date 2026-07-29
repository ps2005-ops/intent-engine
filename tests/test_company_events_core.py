"""T013 bars: envelope contract + append-only store + idempotent publisher."""
import json
import threading

import pytest

from intent_engine.events import (
    CompanyEvent, CompanyEventBus, CorruptLogError, EnvelopeError, EventStore,
)


def _bus(tmp_path):
    return CompanyEventBus(tmp_path / "events")


def _publish(bus, **over):
    kw = dict(event_type="prediction.recorded", subject_type="prediction",
              subject_id="p-1", producer="premortem_pipeline",
              actor_type="system", actor_id="premortem_pipeline",
              source="system", payload={"resolve_by": "2027-01-01"})
    kw.update(over)
    return bus.publish(**kw)


# --- envelope ----------------------------------------------------------------

def test_valid_event_round_trips(tmp_path):
    ev = _publish(_bus(tmp_path), correlation_id="wf-1",
                  causation_id="C" * 26).event
    back = CompanyEvent.from_json(ev.to_json())
    assert back == ev
    assert back.correlation_id == "wf-1" and back.causation_id == "C" * 26


def test_unknown_event_type_rejected(tmp_path):
    with pytest.raises(EnvelopeError, match="unknown event_type"):
        _publish(_bus(tmp_path), event_type="decision.deleted")


def test_wrong_producer_rejected(tmp_path):
    """One authoritative producer per event type — enforced, not advisory."""
    with pytest.raises(EnvelopeError, match="owned by"):
        _publish(_bus(tmp_path), producer="report_renderer")


def test_invalid_actor_and_subject_rejected(tmp_path):
    with pytest.raises(EnvelopeError, match="actor_type"):
        _publish(_bus(tmp_path), actor_type="robot")
    with pytest.raises(EnvelopeError, match="subject_type"):
        _publish(_bus(tmp_path), subject_type="widget")
    with pytest.raises(EnvelopeError, match="subject_id"):
        _publish(_bus(tmp_path), subject_id="")


def test_payload_must_be_json_safe(tmp_path):
    with pytest.raises(EnvelopeError, match="JSON-safe"):
        _publish(_bus(tmp_path), payload={"bad": object()})


def test_schema_version_guard_on_read(tmp_path):
    bus = _bus(tmp_path)
    ev = _publish(bus).event
    data = json.loads(ev.to_json())
    data["payload_schema_version"] = 99
    with pytest.raises(EnvelopeError, match="payload schema v99"):
        CompanyEvent.from_json(json.dumps(data))


# --- append-only store -------------------------------------------------------

def test_events_append_in_order(tmp_path):
    bus = _bus(tmp_path)
    ids = [_publish(bus, subject_id=f"p-{i}",
                    idempotency_key=f"k-{i}").event.event_id
           for i in range(5)]
    assert [e.event_id for e in bus.store.read_all()] == ids


def test_no_update_or_delete_in_public_api():
    banned = [m for m in dir(EventStore)
              if any(w in m.lower() for w in ("update", "delete", "remove"))
              and not m.startswith("_")]
    assert banned == []          # append/read only


def test_duplicate_idempotent_publish_writes_zero_lines(tmp_path):
    bus = _bus(tmp_path)
    r1 = _publish(bus, idempotency_key="k-1")
    lines_before = bus.store.log_path.read_text().count("\n")
    r2 = _publish(bus, idempotency_key="k-1")
    assert r2.duplicate is True
    assert r2.event.event_id == r1.event.event_id      # the ORIGINAL back
    assert bus.store.log_path.read_text().count("\n") == lines_before


def test_same_key_different_content_fails(tmp_path):
    bus = _bus(tmp_path)
    _publish(bus, idempotency_key="k-1")
    with pytest.raises(ValueError, match="different content"):
        _publish(bus, idempotency_key="k-1",
                 payload={"resolve_by": "2028-06-06"})


def test_a_retry_a_second_later_is_still_the_same_event(tmp_path):
    """`occurred_at` defaults to the clock at second resolution, and the
    fingerprint used to include it. Two identical publishes therefore agreed
    only while they landed inside the same wall-clock second: straddle the
    boundary and the retry was rejected as "different content".

    That is exactly backwards -- a retry is by definition later than the
    call it retries -- and it made every duplicate-publish test in the suite
    a coin flip on where the second boundary fell. Caught as an intermittent
    failure in test_marketing_publishing.py, whose two back-to-back dry-run
    publishes are the same shape as `_publish` here."""
    bus = _bus(tmp_path)
    first = _publish(bus, idempotency_key="k-1", occurred_at="2026-07-28T10:00:00+00:00")
    later = _publish(bus, idempotency_key="k-1", occurred_at="2026-07-28T11:30:00+00:00")

    assert later.duplicate is True
    assert later.event.event_id == first.event.event_id     # the ORIGINAL back
    assert bus.store.log_path.read_text().count("\n") == 1  # zero lines added


def test_malformed_log_fails_clearly(tmp_path):
    bus = _bus(tmp_path)
    _publish(bus)
    with open(bus.store.log_path, "a") as f:
        f.write("{this is not json\n")
    with pytest.raises(CorruptLogError, match="malformed"):
        bus.store.read_all()


def test_concurrent_writers_do_not_corrupt_lines(tmp_path):
    bus = _bus(tmp_path)
    errors = []

    def worker(n):
        try:
            for i in range(10):
                _publish(bus, subject_id=f"p-{n}-{i}",
                         idempotency_key=f"k-{n}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    events = bus.store.read_all()          # parses -> no torn lines
    assert len(events) == 40
    assert len({e.event_id for e in events}) == 40


def test_publish_survives_because_fsync_happens_before_return(tmp_path):
    """After publish() returns, the event is on disk — a fresh reader from a
    separate store object sees it."""
    bus = _bus(tmp_path)
    ev = _publish(bus, idempotency_key="durable-1").event
    fresh = EventStore(tmp_path / "events")
    assert fresh.find_by_event_id(ev.event_id) is not None

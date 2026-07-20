"""Consumer protocol, checkpoints, bounded retry, dead letters, replay
(T013). At-least-once delivery: consumers MUST be idempotent. A checkpoint
advances only after successful processing; a consumer failure never
touches the event log itself.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from intent_engine.events.publisher import CompanyEventBus

DEFAULT_MAX_ATTEMPTS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EventConsumer:
    """Subclass or duck-type: `consumer_name`, `handles(event_type)`,
    `process(event)`. process() raising = failure (will be retried, then
    dead-lettered). Unknown/unhandled event types are SKIPPED and the
    checkpoint advances past them — the documented policy."""

    consumer_name = "unnamed_consumer"

    def handles(self, event_type: str) -> bool:  # pragma: no cover - protocol
        return True

    def process(self, event) -> None:  # pragma: no cover - protocol
        raise NotImplementedError


@dataclass
class DrainReport:
    processed: int = 0
    skipped: int = 0
    retried: int = 0
    dead_lettered: int = 0
    stopped_at_event_id: str | None = None
    dry_run_events: list = field(default_factory=list)


# --- persisted retry state (separate from the log AND the checkpoints) -------

def _retry_path(store):
    return store.dir / "retries.json"


def _read_retries(store) -> dict:
    p = _retry_path(store)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _write_retries(store, data: dict) -> None:
    tmp = _retry_path(store).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, _retry_path(store))


def _record_failure(store, consumer_name, event_id, exc) -> int:
    """Track attempts + error metadata. Only the exception TYPE and its
    message are stored — never an event payload."""
    data = _read_retries(store)
    entry = data.setdefault(consumer_name, {}).setdefault(
        event_id, {"attempts": 0, "first_failed_at": _now()})
    entry["attempts"] += 1
    entry["last_error_type"] = type(exc).__name__
    entry["last_error_message"] = str(exc)[:300]
    entry["last_attempted_at"] = _now()
    _write_retries(store, data)
    return entry["attempts"]


def _clear_failure(store, consumer_name, event_id) -> None:
    data = _read_retries(store)
    if data.get(consumer_name, {}).pop(event_id, None) is not None:
        _write_retries(store, data)


# --- drain (the synchronous V1 delivery loop) --------------------------------

def drain(bus: CompanyEventBus, consumer,
          max_attempts: int = DEFAULT_MAX_ATTEMPTS,
          dry_run: bool = False) -> DrainReport:
    """Deliver every event past the consumer's checkpoint, in order.

    - success            -> checkpoint advances to just past the event
    - unhandled type     -> skipped, checkpoint advances (documented policy)
    - failure < limit    -> retry state persisted, drain STOPS at the event
                            (checkpoint untouched; next drain retries)
    - failure at limit   -> append-only dead-letter row, retry state
                            cleared, checkpoint advances so one poisoned
                            event cannot block the stream forever
    """
    store = bus.store
    events = store.read_all()
    offset = store.get_checkpoint(consumer.consumer_name)
    report = DrainReport()

    if dry_run:
        for ev in events[offset:]:
            if consumer.handles(ev.event_type):
                report.dry_run_events.append(ev.event_id)
        return report

    i = offset
    while i < len(events):
        ev = events[i]
        if not consumer.handles(ev.event_type):
            report.skipped += 1
            store.set_checkpoint(consumer.consumer_name, i + 1)
            i += 1
            continue
        try:
            consumer.process(ev)
        except Exception as exc:  # noqa: BLE001 - consumer code is arbitrary
            attempts = _record_failure(store, consumer.consumer_name,
                                       ev.event_id, exc)
            if attempts >= max_attempts:
                store.append_dead_letter({
                    "original_event_id": ev.event_id,
                    "consumer_name": consumer.consumer_name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:300],
                    "attempt_count": attempts,
                    "failed_at": _now(),
                    "redrive_status": "pending",
                })
                _clear_failure(store, consumer.consumer_name, ev.event_id)
                report.dead_lettered += 1
                store.set_checkpoint(consumer.consumer_name, i + 1)
                i += 1
                continue
            report.retried += 1
            report.stopped_at_event_id = ev.event_id
            return report
        _clear_failure(store, consumer.consumer_name, ev.event_id)
        report.processed += 1
        store.set_checkpoint(consumer.consumer_name, i + 1)
        i += 1
    return report


# --- explicit, idempotent redrive --------------------------------------------

def redrive(bus: CompanyEventBus, consumer, event_id: str) -> str:
    """Re-deliver ONE dead-lettered event, explicitly. Idempotent: a
    previously successful redrive is a no-op. History is never erased — the
    outcome is a NEW append-only row referencing the original."""
    store = bus.store
    entries = [d for d in store.read_dead_letters()
               if d["original_event_id"] == event_id
               and d["consumer_name"] == consumer.consumer_name]
    if not entries:
        raise ValueError(f"no dead letter for event {event_id!r} / "
                         f"consumer {consumer.consumer_name!r}")
    if any(d.get("redrive_status") == "succeeded" for d in entries):
        return "already_redriven"
    event = store.find_by_event_id(event_id)
    if event is None:
        raise ValueError(f"event {event_id!r} not found in the log")
    try:
        consumer.process(event)
        status = "succeeded"
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        store.append_dead_letter({
            "original_event_id": event_id,
            "consumer_name": consumer.consumer_name,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:300],
            "attempt_count": 1,
            "failed_at": _now(),
            "redrive_status": "failed",
            "redrive_of": event_id,
        })
        return status
    store.append_dead_letter({
        "original_event_id": event_id,
        "consumer_name": consumer.consumer_name,
        "redrive_status": "succeeded",
        "redriven_at": _now(),
        "redrive_of": event_id,
    })
    return status


# --- replay (re-delivery only; never re-publishes) ---------------------------

def replay(bus: CompanyEventBus, consumer, from_offset: int = 0,
           to_offset: int | None = None, dry_run: bool = False,
           rewind_checkpoint: bool = False) -> DrainReport:
    """Re-deliver EXISTING events in a bounded range. Source events are
    never republished. Checkpoints are respected (untouched) unless the
    caller explicitly asks to rewind."""
    store = bus.store
    events = store.read_all()[from_offset:to_offset]
    report = DrainReport()
    if dry_run:
        report.dry_run_events = [ev.event_id for ev in events
                                 if consumer.handles(ev.event_type)]
        return report
    if rewind_checkpoint:
        store.set_checkpoint(consumer.consumer_name, from_offset)
        return drain(bus, consumer)
    for ev in events:
        if not consumer.handles(ev.event_type):
            report.skipped += 1
            continue
        consumer.process(ev)
        report.processed += 1
    return report

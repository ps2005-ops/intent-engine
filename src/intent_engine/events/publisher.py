"""The one publishing interface (T013). Producers never write JSONL
directly — everything goes through CompanyEventBus.publish(), which
validates the envelope, enforces producer ownership, enforces the two
human walls structurally, and appends durably + idempotently.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from intent_engine.events.envelope import CompanyEvent
from intent_engine.events.store import EventStore

DEFAULT_EVENTS_DIR = Path("events")

# The two walls, structurally: these transitions are only valid from a
# human actor. Generation is automated; publication and claims are not.
_HUMAN_ONLY_EVENTS = {"content.approved", "content.rejected",
                      "content.published", "claim.approved",
                      "claim.rejected",
                      # Promotion is the only learning transition that
                      # authorizes a change to production. Automation
                      # proposes and evaluates; a human promotes. Same wall
                      # discipline as content/claim approval.
                      "learning.candidate_promoted"}


class WallViolation(ValueError):
    """A structural approval-wall rule was violated."""


@dataclass(frozen=True)
class PublishResult:
    event: CompanyEvent
    duplicate: bool   # True when an idempotent retry returned the original


class CompanyEventBus:
    def __init__(self, dir_path=DEFAULT_EVENTS_DIR):
        self.store = EventStore(dir_path)

    def publish(self, event_type: str, *, subject_type: str, subject_id: str,
                producer: str, actor_type: str, actor_id: str, source: str,
                payload: dict | None = None, decision_id: str | None = None,
                prediction_id: str | None = None,
                prospect_id: str | None = None,
                correlation_id: str | None = None,
                causation_id: str | None = None,
                idempotency_key: str | None = None,
                occurred_at: str | None = None) -> PublishResult:
        event_kwargs = dict(
            event_type=event_type, subject_type=subject_type,
            subject_id=subject_id, producer=producer, actor_type=actor_type,
            actor_id=actor_id, source=source, payload=dict(payload or {}),
            decision_id=decision_id, prediction_id=prediction_id,
            prospect_id=prospect_id, correlation_id=correlation_id,
            causation_id=causation_id, idempotency_key=idempotency_key,
        )
        if occurred_at is not None:
            event_kwargs["occurred_at"] = occurred_at
        event = CompanyEvent(**event_kwargs)
        self._enforce_walls(event)
        stored = self.store.append(event)
        return PublishResult(event=stored,
                             duplicate=stored.event_id != event.event_id)

    # --- the two walls, as code ----------------------------------------------
    def _enforce_walls(self, event: CompanyEvent) -> None:
        if event.event_type in _HUMAN_ONLY_EVENTS \
                and event.actor_type != "human":
            raise WallViolation(
                f"{event.event_type} is a human wall transition; "
                f"actor_type={event.actor_type!r} cannot emit it "
                "(no auto-approval, no auto-publishing)")
        if event.event_type == "content.published":
            approved = any(
                ev.event_type == "content.approved"
                and ev.subject_id == event.subject_id
                and ev.actor_type == "human"
                for ev in self.store.read_all())
            if not approved:
                raise WallViolation(
                    f"content.published for {event.subject_id!r} requires a "
                    "prior content.approved fact from a human — none exists")

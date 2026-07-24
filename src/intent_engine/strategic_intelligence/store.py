"""V1.3 StrategicMemory — persistent, append-only company state + events.

Reuses the AgentOS append-only log so the mental model is versioned and
replayable, and strategic events are published to a durable store (not just
attached to the report). Keyed by company domain so future evidence UPDATES the
model instead of rebuilding from zero.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from intent_engine.core.decision_ids import is_ulid, new_ulid

DEFAULT_STRATEGIC_PATH = Path("data/strategic_state.jsonl")

STRATEGIC_EVENTS = frozenset({
    "company_model_created", "company_model_updated",
    "strategic_surprise_detected", "agenda_item_detected",
    "opportunity_detected", "vulnerability_detected",
    "hypothesis_created", "hypothesis_strengthened", "hypothesis_weakened",
    "confidence_changed", "decision_impact_changed",
    "source_portfolio_completed", "contradiction_detected",
    "source_selected", "evidence_rejected", "likely_agenda_item_detected",
    "report_completed", "conversation_routing_failure", "answer_challenged",
    "report_viewed", "evidence_opened", "feedback_received",
    "model_snapshot",
})


class StrategicMemoryError(RuntimeError):
    pass


@dataclass
class StrategicEvent:
    event_type: str
    domain: str
    payload: dict = field(default_factory=dict)
    event_id: str = field(default_factory=new_ulid)
    occurred_at: str = field(default_factory=lambda:
                             datetime.now(timezone.utc).isoformat())
    idempotency_key: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


class StrategicMemory:
    """Append-only per-company strategic state. Idempotent event publication."""

    def __init__(self, path=DEFAULT_STRATEGIC_PATH):
        self.path = Path(path)
        self._keys = set()
        self._load_keys()

    def _load_keys(self):
        if not self.path.exists():
            return
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("idempotency_key"):
                self._keys.add(row["idempotency_key"])

    def _append(self, event: StrategicEvent):
        if event.idempotency_key and event.idempotency_key in self._keys:
            return False
        if event.event_type not in STRATEGIC_EVENTS:
            raise StrategicMemoryError(f"unknown event {event.event_type!r}")
        if not is_ulid(event.event_id):
            raise StrategicMemoryError("event_id must be a ULID")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(event.to_json() + "\n")
        if event.idempotency_key:
            self._keys.add(event.idempotency_key)
        return True

    def _rows(self):
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out

    # --- model persistence ---------------------------------------------------
    def latest_model(self, domain: str):
        """The most recent persisted mental-model snapshot for a company."""
        snap = None
        for row in self._rows():
            if row.get("event_type") == "model_snapshot" and \
                    row.get("domain") == domain:
                snap = row["payload"].get("model")
        return snap

    def save_snapshot(self, domain: str, model: dict):
        version = model.get("version", 1)
        self._append(StrategicEvent(
            event_type="model_snapshot", domain=domain,
            payload={"model": model},
            idempotency_key=f"snapshot:{domain}:v{version}"))

    def publish(self, domain: str, events: list, *, run_id: str = ""):
        """Publish a batch of strategic events idempotently for this run."""
        written = 0
        for i, ev in enumerate(events):
            etype = ev.get("event", "")
            if etype not in STRATEGIC_EVENTS:
                continue
            key = f"{run_id}:{etype}:{i}" if run_id else None
            if self._append(StrategicEvent(
                    event_type=etype, domain=domain,
                    payload={k: v for k, v in ev.items() if k != "event"},
                    idempotency_key=key)):
                written += 1
        return written

    def events_for(self, domain: str):
        return [r for r in self._rows() if r.get("domain") == domain]

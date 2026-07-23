"""V2.0 Growth Studio store — AgentOS AppendOnlyStore subclass."""
from __future__ import annotations

from pathlib import Path

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.growth_studio.records import StudioError, StudioEvent

DEFAULT_STUDIO_PATH = Path("data/growth_studio.jsonl")


class StudioCorruptLogError(CorruptLogError):
    """The growth-studio log contains a line that cannot be parsed."""


class StudioStore(AppendOnlyStore):
    event_cls = StudioEvent
    record_error = StudioError
    corrupt_error = StudioCorruptLogError

    def __init__(self, path=DEFAULT_STUDIO_PATH):
        super().__init__(path)

    def for_item(self, item_id: str) -> list:
        return [r for r in self.read_all() if r.item_id == item_id]

    def item_state(self, item_id: str):
        state = None
        for row in self.for_item(item_id):
            if row.event_type == "studio.item_transitioned":
                state = row.payload["to"]
            elif row.event_type == "studio.item_created":
                state = row.payload.get("state", "OBSERVED")
        return state

    def items(self) -> dict:
        """item_id -> {kind, state, created payload}."""
        out = {}
        for row in self.read_all():
            if row.event_type == "studio.item_created":
                out[row.item_id] = {"kind": row.payload.get("kind"),
                                    "state": row.payload.get("state",
                                                             "OBSERVED"),
                                    "payload": dict(row.payload)}
            elif row.event_type == "studio.item_transitioned" \
                    and row.item_id in out:
                out[row.item_id]["state"] = row.payload["to"]
        return out

    def briefings(self) -> dict:
        return {row.subject_id: dict(row.payload)
                for row in self.read_all()
                if row.event_type == "studio.briefing_produced"}

    def accepted_learnings(self) -> list:
        return [row for row in self.read_all()
                if row.event_type == "studio.learning_accepted"]

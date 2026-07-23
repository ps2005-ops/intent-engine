"""Append-only workspace store (T023): `data/personal.jsonl`.

Subclasses the AgentOS kernel `AppendOnlyStore` (T022) — the workspace
reimplements no store mechanics, it inherits flock, fsync, idempotency,
the parse cache, and loud corruption, and adds only its own query methods.
The store records the founder's SESSION — questions, pins, briefs — and
never an operational fact owned by another subsystem.
"""
from __future__ import annotations

from pathlib import Path

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.personal.records import PersonalError, PersonalEvent

DEFAULT_PERSONAL_PATH = Path("data/personal.jsonl")


class PersonalCorruptLogError(CorruptLogError):
    """The workspace log contains a line that cannot be parsed."""


class PersonalStore(AppendOnlyStore):
    event_cls = PersonalEvent
    record_error = PersonalError
    corrupt_error = PersonalCorruptLogError

    def __init__(self, path=DEFAULT_PERSONAL_PATH):
        super().__init__(path)

    def for_session(self, session_id: str) -> list[PersonalEvent]:
        return [r for r in self.read_all() if r.session_id == session_id]

    def for_type(self, event_type: str) -> list[PersonalEvent]:
        return [r for r in self.read_all() if r.event_type == event_type]

    def session_ids(self) -> list[str]:
        return sorted({r.session_id for r in self.read_all() if r.session_id})

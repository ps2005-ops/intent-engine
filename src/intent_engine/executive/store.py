"""Append-only executive store (T021): `data/executive.jsonl`.

The append-only discipline — flock, fsync, fingerprint-checked
idempotency, loud corruption, no mutation API, and the (mtime_ns, size)
parse cache — now lives ONCE in `agentos.append_only.AppendOnlyStore`
(T022). This store subclasses it and adds only its domain query methods;
behaviour is unchanged.
"""
from __future__ import annotations

from pathlib import Path

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.executive.records import ExecutiveError, ExecutiveEvent

DEFAULT_EXECUTIVE_PATH = Path("data/executive.jsonl")


class ExecutiveCorruptLogError(CorruptLogError):
    """The executive log contains a line that cannot be parsed."""


class ExecutiveStore(AppendOnlyStore):
    event_cls = ExecutiveEvent
    record_error = ExecutiveError
    corrupt_error = ExecutiveCorruptLogError

    def __init__(self, path=DEFAULT_EXECUTIVE_PATH):
        super().__init__(path)

    def for_field(self, field_name: str, value: str) -> list[ExecutiveEvent]:
        return [r for r in self.read_all() if getattr(r, field_name) == value]

    def for_candidate(self, candidate_id: str) -> list[ExecutiveEvent]:
        return self.for_field("candidate_id", candidate_id)

    def for_package(self, package_id: str) -> list[ExecutiveEvent]:
        return self.for_field("package_id", package_id)

    def ids(self, field_name: str) -> list[str]:
        return sorted({getattr(r, field_name) for r in self.read_all()
                       if getattr(r, field_name)})

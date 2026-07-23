"""Append-only research store (T019): `data/research.jsonl`.

The append-only discipline — flock, fsync before success,
fingerprint-checked idempotency, loud corruption, no mutation API, and the
(mtime_ns, size)-keyed parse cache — now lives ONCE in
`agentos.append_only.AppendOnlyStore` (T022), extracted from the three
byte-identical copies the agents used to carry. This store subclasses it
and adds only its domain query methods; behaviour is unchanged.
"""
from __future__ import annotations

from pathlib import Path

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.research.records import ResearchError, ResearchEvent

DEFAULT_RESEARCH_PATH = Path("data/research.jsonl")


class ResearchCorruptLogError(CorruptLogError):
    """The research log contains a line that cannot be parsed."""


class ResearchStore(AppendOnlyStore):
    event_cls = ResearchEvent
    record_error = ResearchError
    corrupt_error = ResearchCorruptLogError

    def __init__(self, path=DEFAULT_RESEARCH_PATH):
        super().__init__(path)

    def for_request(self, request_id: str) -> list[ResearchEvent]:
        return [r for r in self.read_all() if r.request_id == request_id]

    def request_ids(self) -> list[str]:
        return sorted({r.request_id for r in self.read_all()})

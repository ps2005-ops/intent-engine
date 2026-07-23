"""Append-only Founder Intelligence store (T023.5): `data/founder_intelligence.jsonl`.

Subclasses the AgentOS kernel `AppendOnlyStore` (T022) — no store mechanics
reimplemented. Every row is scoped to a `run_id` and a `company_domain`, so
cross-run and cross-company isolation is enforceable at read time.
"""
from __future__ import annotations

from pathlib import Path

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.founder_intelligence.records import (
    FounderIntelligenceError, FounderIntelligenceEvent,
)

DEFAULT_FI_PATH = Path("data/founder_intelligence.jsonl")


class FounderIntelligenceCorruptLogError(CorruptLogError):
    """The founder-intelligence log contains a line that cannot be parsed."""


class FounderIntelligenceStore(AppendOnlyStore):
    event_cls = FounderIntelligenceEvent
    record_error = FounderIntelligenceError
    corrupt_error = FounderIntelligenceCorruptLogError

    def __init__(self, path=DEFAULT_FI_PATH):
        super().__init__(path)

    def for_run(self, run_id: str) -> list[FounderIntelligenceEvent]:
        return [r for r in self.read_all() if r.run_id == run_id]

    def for_company(self, company_domain: str) -> list[FounderIntelligenceEvent]:
        return [r for r in self.read_all()
                if r.company_domain == company_domain]

    def run_ids(self) -> list[str]:
        return sorted({r.run_id for r in self.read_all() if r.run_id})

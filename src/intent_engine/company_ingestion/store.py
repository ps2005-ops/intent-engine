"""V1.1 ingestion store — AgentOS AppendOnlyStore subclass."""
from __future__ import annotations

from pathlib import Path

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.company_ingestion.records import (
    IngestionError, IngestionEvent,
)

DEFAULT_CI_PATH = Path("data/company_ingestion.jsonl")


class IngestionCorruptLogError(CorruptLogError):
    """The company-ingestion log contains a line that cannot be parsed."""


class IngestionStore(AppendOnlyStore):
    event_cls = IngestionEvent
    record_error = IngestionError
    corrupt_error = IngestionCorruptLogError

    def __init__(self, path=DEFAULT_CI_PATH):
        super().__init__(path)

    def for_run(self, run_id: str) -> list:
        return [r for r in self.read_all() if r.run_id == run_id]

    def run_state(self, run_id: str):
        state = None
        for row in self.for_run(run_id):
            if row.event_type == "ci.run_transitioned":
                state = row.payload["to"]
            elif row.event_type == "ci.run_created":
                state = "VALIDATING_COMPANY"
        return state

    def candidates(self, run_id: str) -> list:
        return [r.payload for r in self.for_run(run_id)
                if r.event_type == "ci.candidate_discovered"]

    def approval(self, run_id: str):
        rows = [r.payload for r in self.for_run(run_id)
                if r.event_type == "ci.approval_recorded"]
        return rows[0] if rows else None      # immutable: first one wins

    def retrieved(self, run_id: str) -> list:
        return [r.payload for r in self.for_run(run_id)
                if r.event_type in ("ci.source_retrieved",
                                    "ci.pasted_evidence_added")]

    def failures(self, run_id: str) -> list:
        return [r.payload for r in self.for_run(run_id)
                if r.event_type == "ci.retrieval_failed"]

    def run_ids(self) -> list:
        return list(dict.fromkeys(
            r.run_id for r in self.read_all()
            if r.event_type == "ci.run_created"))

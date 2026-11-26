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

    #: States after which the run has an answer. Mirrors WebApp.TERMINAL_STATES.
    TERMINAL = frozenset({"COMPLETE", "PARTIAL", "FAILED", "REJECTED",
                          "INTERRUPTED"})

    def run_state(self, run_id: str):
        """The run's state. A RETRY PASS AFTER THE ANSWER DOES NOT REOPEN IT.

        `compose_with_quality` records each targeted-retry pass as a
        transition to DISCOVERING_SOURCES. On the first, live pass the worker
        writes the terminal state after it. A RE-composition of a finished
        run -- the retry button, or a read in a fresh process -- records the
        same pass, and nothing writes a terminal state after it, so a finished
        run read as "discovering sources" forever: 8 of 95 prospect-100 runs,
        decks redirecting for good. Activity during such a recompose is the
        in-flight check's to report, not the ledger's.
        """
        state = None
        for row in self.for_run(run_id):
            if row.event_type == "ci.run_transitioned":
                if (state in self.TERMINAL
                        and "retry_pass" in (row.payload or {})):
                    continue
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

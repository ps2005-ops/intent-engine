"""Data foundation pass, Stage 2: a two-tier raw/summary layer over entity
memory.

Tier 1 (raw): core/entity_memory.py's EntityMemoryRecord, one row per real
occurrence, SQLite-backed since Stage 1 -- full fidelity, never summarized
away, never deleted or mutated by anything in this module.

Tier 2 (summary): this module. EntitySummaryRecord condenses the Tier-1
records covering one period (e.g. one week) into a single synthesized
summary_text, FOR READING, not for REPLACING Tier 1. A summary existing
never causes its source raw records to be deleted, hidden, or treated as
less authoritative -- summaries are a cheap, compact lens on top of the
same real records, not a second copy of the truth.

source_record_ids is a REAL citation, computed deterministically in code
from exactly which Tier-1 records were read for that period -- never an
LLM claim. Same "structured prior over statistical rediscovery" discipline
as compute_coherence_note in scrap_estimate.py: the model only ever sees
the gathered raw records and writes summary_text from them; it is never
asked which records it drew on, because a self-reported citation list is
exactly the kind of LLM claim this project's own honesty discipline
distrusts (a model can be wrong, or vague, about what it actually used).
The citation list a person reads is always literally the list of
record_ids that were fed into the prompt, not anything the model asserted.

Tiered retrieval: get_tiered_view() below returns the summary tier by
default (cheap, compact) and, only if the caller explicitly asks
(include_raw=True), the full raw detail every returned summary cites.
Nothing here decides "you only get the summary" on the caller's behalf --
the raw tier is always one call away, never deleted or hidden behind the
summary.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, NamedTuple, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from .db import get_connection
from .entity_memory import DEFAULT_PATH, EntityMemoryRecord, normalize_entity_id, read_records
from .llm_client import LLMClient

FAST_MODEL = "claude-haiku-4-5-20251001"

DEFAULT_SUMMARY_PATH = Path("data/entity_summaries.db")


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class EntitySummaryRecord(BaseModel):
    summary_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_id: str
    period_start: str  # ISO-8601, inclusive
    period_end: str  # ISO-8601, exclusive
    summary_text: str
    # REAL citation -- the exact record_ids read for this period, computed
    # in code, never asked of or asserted by the model. See module docstring.
    source_record_ids: List[str]
    created_at: str = Field(default_factory=_current_timestamp)


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS summaries (
            summary_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_summaries_entity_period ON summaries(entity_id, period_start, period_end)")
    conn.commit()


def _records_in_period(
    entity_id: str, period_start: str, period_end: str, path: Union[str, Path]
) -> List[EntityMemoryRecord]:
    """Tier-1 records for entity_id timestamped in [period_start,
    period_end) -- plain ISO-8601 string comparison, safe here because
    every timestamp in this codebase is generated via
    datetime.now(timezone.utc).isoformat(), which sorts lexicographically
    identically to chronologically (fixed-width, zero-padded, UTC)."""
    return [r for r in read_records(entity_id, path=path) if period_start <= r.timestamp < period_end]


SUMMARY_SYSTEM_PROMPT = """You are writing a short, factual summary of a period's real recorded \
activity for an entity, for someone reviewing what happened.

Only state things directly supported by the items given below -- do not infer motives, \
predict outcomes, or add detail not present in the text. If the items cover multiple \
distinct topics, mention each briefly rather than dropping any to keep the summary short. \
2-4 sentences, plain prose, no bullet points."""

SUMMARY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_text": {
            "type": "string",
            "description": "A 2-4 sentence factual summary of the given period's real recorded items.",
        },
    },
    "required": ["summary_text"],
}


def generate_weekly_summary(
    entity_id: str,
    period_start: str,
    period_end: str,
    client: Optional[LLMClient] = None,
    entity_memory_path: Union[str, Path] = DEFAULT_PATH,
    summary_path: Union[str, Path] = DEFAULT_SUMMARY_PATH,
) -> EntitySummaryRecord:
    """Gathers the real Tier-1 records for entity_id in [period_start,
    period_end), asks the model to synthesize them into summary_text, and
    persists an EntitySummaryRecord whose source_record_ids is exactly the
    set of records gathered -- computed here in code, not requested from
    or trusted from the model's own output. Real records are never
    deleted or altered; this is purely additive."""
    records = _records_in_period(entity_id, period_start, period_end, entity_memory_path)

    if not records:
        summary_text = f"No activity recorded for this entity between {period_start} and {period_end}."
    else:
        client = client or LLMClient(model=FAST_MODEL)
        items = "\n".join(f"{i + 1}. [{r.timestamp}] {r.decision_text}" for i, r in enumerate(records))
        user_message = f"Real recorded items for this period:\n{items}\n\nWrite the summary."
        result = client.call_tool(
            system=SUMMARY_SYSTEM_PROMPT,
            user_message=user_message,
            tool_name="record_summary",
            tool_description="Record the period summary.",
            input_schema=SUMMARY_TOOL_SCHEMA,
            max_tokens=300,
        )
        summary_text = result["summary_text"]

    record = EntitySummaryRecord(
        entity_id=normalize_entity_id(entity_id),
        period_start=period_start,
        period_end=period_end,
        summary_text=summary_text,
        source_record_ids=[r.record_id for r in records],
    )
    _persist_summary(record, path=summary_path)
    return record


def _persist_summary(record: EntitySummaryRecord, path: Union[str, Path] = DEFAULT_SUMMARY_PATH) -> None:
    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO summaries (summary_id, entity_id, period_start, period_end, created_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (record.summary_id, record.entity_id, record.period_start, record.period_end, record.created_at,
             record.model_dump_json()),
        )
        conn.commit()
    finally:
        conn.close()


def read_summaries(entity_id: str, path: Union[str, Path] = DEFAULT_SUMMARY_PATH) -> List[EntitySummaryRecord]:
    """Every persisted summary for entity_id, oldest period first."""
    target = normalize_entity_id(entity_id)
    path = Path(path)
    if not path.exists():
        return []
    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT data FROM summaries WHERE entity_id = ? ORDER BY period_start", (target,)
        ).fetchall()
    finally:
        conn.close()
    return [EntitySummaryRecord.model_validate_json(row[0]) for row in rows]


class TieredView(NamedTuple):
    summaries: List[EntitySummaryRecord]
    # None unless include_raw=True was passed -- distinguishes "raw tier not
    # requested" from "raw tier requested but empty", same three-state
    # discipline as GmailContext/CalendarContext.state elsewhere in this
    # project (state what happened, don't collapse a real distinction into
    # one falsy value).
    raw_records: Optional[List[EntityMemoryRecord]]


def get_tiered_view(
    entity_id: str,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    include_raw: bool = False,
    entity_memory_path: Union[str, Path] = DEFAULT_PATH,
    summary_path: Union[str, Path] = DEFAULT_SUMMARY_PATH,
) -> TieredView:
    """The tiered-retrieval entrypoint: summary tier by default (cheap,
    compact), full raw tier only on request -- and even then, restricted
    to exactly the records the returned summaries actually cite, not every
    record for the entity, so the raw tier stays scoped to what's being
    reviewed rather than dumping the entire history."""
    summaries = read_summaries(entity_id, path=summary_path)
    if period_start is not None:
        summaries = [s for s in summaries if s.period_start >= period_start]
    if period_end is not None:
        summaries = [s for s in summaries if s.period_end <= period_end]

    if not include_raw:
        return TieredView(summaries=summaries, raw_records=None)

    cited_ids = {record_id for s in summaries for record_id in s.source_record_ids}
    raw_records = [r for r in read_records(entity_id, path=entity_memory_path) if r.record_id in cited_ids]
    return TieredView(summaries=summaries, raw_records=raw_records)

"""Stage A: entity memory. A structured, append-only store that both simulator/
and voice/ write into, per docs/weekly/intent-engine-v2-entity-memory.md.

DATA FOUNDATION PASS, STAGE 1: backing store is now SQLite (core/db.py),
not JSON Lines -- the O(n) full-scan-per-read this module's original
docstring flagged as a thing to revisit "if the file grows large enough"
is exactly what this migration answers: read_records() is now an indexed
`WHERE entity_id = ?` query, not a full file scan. See
scripts/migrate_jsonl_to_sqlite.py for the one-time migration of any
existing data, and PROGRESS.md's "Data foundation pass, Stage 1" section
for the full writeup.

Signatures are deliberately UNCHANGED — every existing caller (18 call
sites across production and test code) continues to work with zero
changes: same function names, same parameters, same return types, same
empty-list-on-missing-file behavior. One explicit, flagged exception:
`JsonlEntityMemoryWriter`'s class NAME is now backend-inaccurate (it
writes to SQLite, not JSONL) — kept anyway rather than renamed, because a
rename touches all 18 call sites for a cosmetic reason alone, which is a
larger blast radius than a "signatures unchanged" migration stage should
take on. Tracked as a real, visible followup (not silently accepted) in
PROGRESS.md, to be done as its own small, dedicated rename pass, not
folded into this one.

DOMAIN-TYPING: `EntityMemoryRecord.artifact_kind` is new this pass (see
the field's own docstring below) — the schema-level fix for Part 2/3's
real finding that caption-domain records had to masquerade as messages
(the "Update Instagram with today's caption:" scaffolding prefix, needed
only to satisfy pattern_watcher's recipient-verb-gate) purely because
gathering had exactly one record shape to group by. This pass adds the
column and backfills it correctly for existing data; it does NOT change
gathering/matching logic itself (pattern_watcher.py, draft_generator.py)
to consume it — that is a separate, deliberately deferred build, per the
same "state the finding, don't build the fix under a different stage's
momentum" discipline as every other deferred design question in this
project (e.g. the compound-action mechanism, the PersonalContext
pull-strategy). See PROGRESS.md for the full proposal.
"""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Union

from pydantic import BaseModel, Field

try:
    from typing import Literal
except ImportError:  # pragma: no cover - py<3.8 fallback, not expected here
    from typing_extensions import Literal

from .db import get_connection

DEFAULT_PATH = Path("data/entity_memory.db")

_PUNCTUATION_EXCEPT_HYPHEN = re.compile(r"[^\w\s-]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_entity_id(raw: str) -> str:
    """Normalize an entity identifier so the same entity always maps to the same id.

    Lowercase, strip leading/trailing whitespace, collapse internal whitespace,
    strip punctuation except hyphens. Without this, "Sarah's Startup", "sarahs
    startup", and "  Sarah's Startup  " would each become a distinct entity_id,
    silently orphaning records across what should be one accumulating history --
    memory would never actually accumulate, it would just fragment into
    near-duplicate entities per input variation (capitalization, punctuation,
    stray whitespace) of what a human typed for the same real person or company.
    """
    normalized = raw.strip().lower()
    normalized = _PUNCTUATION_EXCEPT_HYPHEN.sub("", normalized)
    normalized = _WHITESPACE.sub(" ", normalized)
    return normalized.strip()


def _new_record_id() -> str:
    return str(uuid.uuid4())


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class EntityMemoryRecord(BaseModel):
    # record_id/timestamp are generated at construction time via default_factory
    # (practically "write time," since callers build a record immediately before
    # writing it) -- unlike entity_id, these are fresh-generated values, not a
    # transformation of caller input, so there's nothing for the writer to do to
    # them. entity_id normalization is different: it transforms whatever raw
    # string the caller passed in, and is deliberately NOT done here (see
    # normalize_entity_id's docstring and JsonlEntityMemoryWriter.write below) --
    # it happens in the writer so every write path normalizes consistently,
    # rather than trusting every caller to remember to do it themselves.
    record_id: str = Field(default_factory=_new_record_id)
    entity_id: str
    source: Literal["simulator", "voice"]
    timestamp: str = Field(default_factory=_current_timestamp)

    decision_text: str
    goals: List[str]
    constraints: List[str]
    risk_tolerance: Optional[str] = None
    primary_priority: Optional[str] = None  # simulator-only; None from voice writes
    salience: Optional[Literal["low", "medium", "high"]] = None  # voice-only; None from simulator writes

    outcome: Optional[str] = None  # reserved for Stage D+, always None for now

    # New this pass (Data foundation, Stage 1). Additive, default None -- every
    # existing caller (simulator decisions, voice interactions, scrap-estimate
    # records) is unaffected and stays None; this field is only meaningful for
    # records that feed the recurring-artifact-generation loop
    # (pattern_watcher.py -> draft_generator.py). "message" and "caption" are
    # the two real artifact kinds that loop has handled so far (recurring
    # text/email messages; Part 2/3's Instagram captions). This is a SCHEMA
    # change only this pass -- gathering/matching (pattern_watcher._extract_recipient,
    # draft_generator._gather_supporting_records) still operate exactly as
    # before, unaware this field exists; a future pass could group caption
    # records by (entity_id, artifact_kind) directly instead of requiring a
    # recipient-verb-gate match, eliminating the need for scaffolding prefixes
    # like "Update Instagram with today's caption:" entirely -- see
    # PROGRESS.md's Stage 1 section for the full proposal. Not built this pass.
    artifact_kind: Optional[Literal["message", "caption"]] = None


class EntityMemoryWriter(Protocol):
    """Deliberately not a Stage. Stage.run() (core/pipeline.py) models
    compute-and-return-a-value -- every existing Stage (IntentClassifier,
    PremortemAnalyzer, RiskAuditGenerator) takes input and produces a result
    consumers use. A memory writer's job is a side effect (persist a record), not
    a computed value; forcing it into run()->value would mean either returning
    None (misleading -- implies "this Stage doesn't compute anything") or
    inventing a fake return value just to satisfy an abstraction it doesn't fit.
    Own small contract instead, using structural typing (Protocol) rather than
    another ABC subclass, so it doesn't read as "a kind of Stage" at all."""

    def write(self, record: EntityMemoryRecord) -> None: ...


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            record_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            artifact_kind TEXT,
            timestamp TEXT NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_entity_id ON records(entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_entity_artifact_kind ON records(entity_id, artifact_kind)")
    conn.commit()


class JsonlEntityMemoryWriter:
    """Writes one row per record to a local SQLite file (core/db.py).

    Class name kept as-is despite no longer writing JSONL -- see the module
    docstring's "Signatures are deliberately UNCHANGED" note for why this is
    a flagged, deliberate exception rather than an oversight.

    No locking/concurrency control beyond SQLite's own -- fine for a
    single-process CLI, would need revisiting for concurrent writers.
    """

    def __init__(self, path: Union[str, Path] = DEFAULT_PATH):
        self.path = Path(path)

    def write(self, record: EntityMemoryRecord) -> None:
        normalized = record.model_copy(update={"entity_id": normalize_entity_id(record.entity_id)})
        conn = get_connection(self.path)
        try:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO records (record_id, entity_id, artifact_kind, timestamp, data) VALUES (?, ?, ?, ?, ?)",
                (
                    normalized.record_id,
                    normalized.entity_id,
                    normalized.artifact_kind,
                    normalized.timestamp,
                    normalized.model_dump_json(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def read_records(entity_id: str, path: Union[str, Path] = DEFAULT_PATH) -> List[EntityMemoryRecord]:
    """Indexed `WHERE entity_id = ?` query against the SQLite store, ordered
    by insertion (rowid) -- same result ordering full JSONL scans always
    produced. Answers the O(n) full-scan cost the pre-migration docstring
    here used to flag as a thing to revisit.
    """
    target = normalize_entity_id(entity_id)
    path = Path(path)
    if not path.exists():
        return []

    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT data FROM records WHERE entity_id = ? ORDER BY rowid", (target,)
        ).fetchall()
    finally:
        conn.close()
    return [EntityMemoryRecord.model_validate_json(row[0]) for row in rows]


def records_by_artifact_kind(
    entity_id: str, artifact_kind: str, path: Union[str, Path] = DEFAULT_PATH
) -> List[EntityMemoryRecord]:
    """Query helper, new this pass: real, indexed lookup by (entity_id,
    artifact_kind) -- demonstrates the domain-typing column added above is
    genuinely queryable, not just a decorative field nothing reads. Not
    wired into any gathering/matching logic yet (see the module docstring's
    DOMAIN-TYPING section) -- this is the building block a future pass
    would use to do that, exercised here on its own.
    """
    target = normalize_entity_id(entity_id)
    path = Path(path)
    if not path.exists():
        return []

    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT data FROM records WHERE entity_id = ? AND artifact_kind = ? ORDER BY rowid",
            (target, artifact_kind),
        ).fetchall()
    finally:
        conn.close()
    return [EntityMemoryRecord.model_validate_json(row[0]) for row in rows]


def count_records_by_entity(entity_id: str, path: Union[str, Path] = DEFAULT_PATH) -> int:
    """Query helper, new this pass: a count that doesn't require pulling
    every record's full JSON blob into Python just to call len() on it --
    the kind of thing a full-table-scan-per-read backend couldn't offer
    cheaply."""
    target = normalize_entity_id(entity_id)
    path = Path(path)
    if not path.exists():
        return 0

    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        (count,) = conn.execute("SELECT COUNT(*) FROM records WHERE entity_id = ?", (target,)).fetchone()
    finally:
        conn.close()
    return count

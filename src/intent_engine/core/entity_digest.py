"""Data foundation pass, Stage 3: the quiet-observer digest, built per the
approved proposal (PROGRESS.md's "Data foundation pass, Stage 3" section)
plus these decisions:

- M = 2 consecutive Tier-2 periods for trend persistence (tunable later,
  documented as such -- not empirically derived from anything).
- Batch digest, hard cap of DIGEST_ITEM_CAP=3 items, ranked by
  supporting-evidence count descending. Overflow candidates that pass
  every bar but don't make the cap are NOT recorded as surfaced -- they
  stay eligible (novel) for their next check, rather than being silently
  discarded forever.
- Trend novelty identity = (entity_id, trend_dimension, direction),
  compared exactly -- a direction reversal is treated as a genuinely NEW
  candidate, not a continuation of the same trend.
- Pattern novelty reuses suggestion.py's own _same_underlying_pattern()
  (real reuse, not a second overlap implementation) against every
  previously-surfaced pattern item for the entity.
- All digest/cadence state lives in SQLite (core/db.py), own tables, same
  per-store ownership pattern as every Stage 1/2 store.

MODEL DRAFTS, CODE DECIDES: every candidate is gathered, evidence-counted,
persistence-checked (trends only), novelty-checked, ranked, and capped --
ALL in code -- before the model is ever called. The model's only job is
writing digest_text for an item that has ALREADY been selected; its tool
schema has no include/exclude field at all (checked directly by a test,
not just asserted here), the same structural guarantee as Stage 2's
source_record_ids never being asked of the model.

SILENCE IS THE DEFAULT: check_for_digest() returns None whenever nothing
clears every applicable bar -- no digest object is created, not an empty
or hedged one. Cadence (should_check_for_digest()) gates WHEN the
(cheap-but-not-free) bar-evaluation logic runs at all; it says nothing
about whether that run produces anything. A month of checks that all
return None is the system working correctly, not a bug.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union
from uuid import uuid4

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from pydantic import BaseModel, Field

from .db import get_connection
from .entity_memory import DEFAULT_PATH, normalize_entity_id
from .entity_summary import DEFAULT_SUMMARY_PATH, TrendCandidate, detect_trends
from .llm_client import LLMClient
from .pattern_watcher import DetectedPattern, detect_recurring_message_patterns
from .suggestion import _same_underlying_pattern

FAST_MODEL = "claude-haiku-4-5-20251001"

DEFAULT_DIGEST_PATH = Path("data/entity_digests.db")

# N: minimum real supporting-evidence records behind any digest candidate.
# Reuses the existing convention already anchored across this codebase
# (detect_recurring_message_patterns's own min_occurrences=3 default,
# generate_draft's min_occurrences_for_confidence=3) rather than inventing
# a new, unprecedented threshold.
MIN_EVIDENCE_COUNT = 3

# M: minimum consecutive agreeing period-to-period comparisons a trend
# needs to clear the persistence bar. Tunable later, documented as such --
# 2 is a stated design decision, not empirically derived.
MIN_TREND_PERSISTENCE = 2

DIGEST_ITEM_CAP = 3

DigestItemKind = Literal["pattern", "trend"]


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class DigestItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_id: str
    kind: DigestItemKind
    digest_text: str
    # REAL citation, computed in code from the candidate that passed every
    # bar -- never requested from or asserted by the model. See module
    # docstring.
    source_record_ids: List[str]
    evidence_count: int
    created_at: str = Field(default_factory=_current_timestamp)


class DigestRecord(BaseModel):
    digest_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_id: str
    items: List[DigestItem]
    created_at: str = Field(default_factory=_current_timestamp)


# --- Schema (2 tables: digest_checks for cadence, digest_history for --------
# --- novelty + the persisted digests themselves) ----------------------------


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS digest_checks (
            entity_id TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            items_surfaced INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS digest_item_history (
            entity_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            candidate_json TEXT NOT NULL,
            surfaced_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS digest_records (
            digest_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_digest_checks_entity_id ON digest_checks(entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_digest_history_entity_kind ON digest_item_history(entity_id, kind)")
    conn.commit()


# --- Cadence: WHEN to check, independent of whether a check finds anything -

def should_check_for_digest(
    entity_id: str,
    path: Union[str, Path] = DEFAULT_DIGEST_PATH,
    min_interval_days: int = 3,
    now: Optional[str] = None,
) -> bool:
    """True if no check has ever run for this entity, or the last one was
    >= min_interval_days ago. Says nothing about whether a check that
    runs now would find anything -- that's check_for_digest()'s job
    entirely. now is an explicit, optional override (ISO-8601 string) so
    this stays deterministic and testable without depending on the real
    wall clock."""
    now = now or _current_timestamp()
    target = normalize_entity_id(entity_id)
    path = Path(path)
    if not path.exists():
        return True

    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT checked_at FROM digest_checks WHERE entity_id = ? ORDER BY checked_at DESC LIMIT 1",
            (target,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return True

    last_checked = datetime.fromisoformat(row[0])
    elapsed = datetime.fromisoformat(now) - last_checked
    return elapsed.days >= min_interval_days


def _record_check(entity_id: str, items_surfaced: int, path: Union[str, Path], now: Optional[str] = None) -> None:
    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO digest_checks (entity_id, checked_at, items_surfaced) VALUES (?, ?, ?)",
            (normalize_entity_id(entity_id), now or _current_timestamp(), items_surfaced),
        )
        conn.commit()
    finally:
        conn.close()


# --- Novelty: has this exact candidate already been surfaced? --------------

def _prior_surfaced(entity_id: str, kind: DigestItemKind, path: Union[str, Path]) -> List[str]:
    path = Path(path)
    if not path.exists():
        return []
    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT candidate_json FROM digest_item_history WHERE entity_id = ? AND kind = ?",
            (normalize_entity_id(entity_id), kind),
        ).fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]


def _pattern_already_surfaced(pattern: DetectedPattern, path: Union[str, Path]) -> bool:
    """Reuses suggestion.py's own _same_underlying_pattern() -- real
    reuse, not a second overlap-detection implementation."""
    for candidate_json in _prior_surfaced(pattern.entity_id, "pattern", path):
        prior = DetectedPattern.model_validate_json(candidate_json)
        if _same_underlying_pattern(pattern, prior):
            return True
    return False


def _trend_already_surfaced(trend: TrendCandidate, path: Union[str, Path]) -> bool:
    """Identity = (entity_id, trend_dimension, direction), exact match. A
    direction reversal changes the identity -- it is a new candidate, not
    a continuation."""
    for candidate_json in _prior_surfaced(trend.entity_id, "trend", path):
        prior = TrendCandidate.model_validate_json(candidate_json)
        if (prior.trend_dimension, prior.direction) == (trend.trend_dimension, trend.direction):
            return True
    return False


def _record_surfaced(entity_id: str, kind: DigestItemKind, candidate_json: str, path: Union[str, Path]) -> None:
    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO digest_item_history (entity_id, kind, candidate_json, surfaced_at) VALUES (?, ?, ?, ?)",
            (normalize_entity_id(entity_id), kind, candidate_json, _current_timestamp()),
        )
        conn.commit()
    finally:
        conn.close()


# --- Drafting: model writes text for an ALREADY-selected item, never -------
# --- decides inclusion -------------------------------------------------------

DIGEST_ITEM_SYSTEM_PROMPT = """You are drafting one short digest item surfacing a real, \
already-confirmed pattern or trend from someone's accumulated activity, for them to review.

Only state what's directly supported by the description given -- do not editorialize about \
whether this is good or bad, do not suggest an action, do not speculate about causes. State \
the observation plainly. One or two sentences."""

DIGEST_ITEM_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "digest_text": {
            "type": "string",
            "description": "A one or two sentence factual observation, no editorializing or suggested action.",
        },
    },
    "required": ["digest_text"],
}


def _describe_candidate(kind: DigestItemKind, candidate) -> str:
    if kind == "pattern":
        return candidate.description
    weeks = candidate.persistence_count + 1
    return (
        f"Over the last {weeks} weekly summaries, '{candidate.trend_dimension}' has been "
        f"{candidate.direction} for this entity's recorded activity."
    )


def _draft_digest_item_text(kind: DigestItemKind, candidate, client: LLMClient) -> str:
    description = _describe_candidate(kind, candidate)
    user_message = f"Real, already-confirmed observation:\n{description}\n\nWrite the digest item."
    result = client.call_tool(
        system=DIGEST_ITEM_SYSTEM_PROMPT,
        user_message=user_message,
        tool_name="record_digest_item",
        tool_description="Record the digest item text.",
        input_schema=DIGEST_ITEM_TOOL_SCHEMA,
        max_tokens=150,
    )
    return result["digest_text"]


# --- The gate ----------------------------------------------------------------

def check_for_digest(
    entity_id: str,
    client: Optional[LLMClient] = None,
    entity_memory_path: Union[str, Path] = DEFAULT_PATH,
    summary_path: Union[str, Path] = DEFAULT_SUMMARY_PATH,
    digest_path: Union[str, Path] = DEFAULT_DIGEST_PATH,
) -> Optional[DigestRecord]:
    """The one real entrypoint. Gathers every candidate (Pattern-Watcher
    detections + Tier-2 trends), applies every deterministic bar
    (evidence count; persistence for trends; novelty), ranks survivors by
    evidence count descending, caps at DIGEST_ITEM_CAP, drafts text ONLY
    for the included items, records the check (always) and the surfaced
    items (only the ones actually included -- overflow stays eligible for
    next time), and returns the DigestRecord, or None if nothing cleared
    every bar. Always records that a check ran, even when it returns
    None -- see should_check_for_digest()."""
    entity_id = normalize_entity_id(entity_id)

    patterns = detect_recurring_message_patterns(entity_id, path=entity_memory_path)
    pattern_survivors = [
        p for p in patterns
        if len(p.supporting_record_ids) >= MIN_EVIDENCE_COUNT
        and not _pattern_already_surfaced(p, digest_path)
    ]

    trends = detect_trends(entity_id, summary_path=summary_path, entity_memory_path=entity_memory_path)
    trend_survivors = [
        t for t in trends
        if t.persistence_count >= MIN_TREND_PERSISTENCE
        and len(t.source_record_ids) >= MIN_EVIDENCE_COUNT
        and not _trend_already_surfaced(t, digest_path)
    ]

    ranked = sorted(
        [("pattern", p, len(p.supporting_record_ids)) for p in pattern_survivors]
        + [("trend", t, len(t.source_record_ids)) for t in trend_survivors],
        key=lambda entry: entry[2],
        reverse=True,
    )
    included = ranked[:DIGEST_ITEM_CAP]

    _record_check(entity_id, items_surfaced=len(included), path=digest_path)

    if not included:
        return None

    client = client or LLMClient(model=FAST_MODEL)
    items = []
    for kind, candidate, evidence_count in included:
        digest_text = _draft_digest_item_text(kind, candidate, client)
        source_record_ids = candidate.supporting_record_ids if kind == "pattern" else candidate.source_record_ids
        items.append(DigestItem(
            entity_id=entity_id, kind=kind, digest_text=digest_text,
            source_record_ids=source_record_ids, evidence_count=evidence_count,
        ))
        _record_surfaced(entity_id, kind, candidate.model_dump_json(), digest_path)

    record = DigestRecord(entity_id=entity_id, items=items)
    conn = get_connection(digest_path)
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO digest_records (digest_id, entity_id, created_at, data) VALUES (?, ?, ?, ?)",
            (record.digest_id, entity_id, record.created_at, record.model_dump_json()),
        )
        conn.commit()
    finally:
        conn.close()

    return record

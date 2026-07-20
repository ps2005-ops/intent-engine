"""Event-sourced Decision Record — the decision-identity primitive (T010).

The backbone every other system keys to (report, ledger, CRM, events, APIs,
Personal AI). Designed per the architecture review of 2026-07-20, with all
ten final decisions locked:

  1. The base record holds NO state. `decision_status`, `execution_status`,
     `evaluation_status`, and `owner` are folded from an append-only event
     stream — one source of truth.
  2. A deterministic transition validator rejects illegal event sequences.
  3. Relationships are stored in ONE canonical direction; inverses are
     derived on read.
  4. Terminology locked: `decision_id` = opaque ULID; `decision_key` = human.
  5. SQLite backend (transactions, uniqueness, FKs, append-only triggers).
  6. Explicit UNIQUE constraints (see schema below).
  7. Per-decision monotonic `sequence_number` is the ordering authority.
  8. `occurred_at` (when it happened) is separate from `recorded_at`.
  9. Typed failure/recovery events, not one generic Failure.
 10. Privacy: reserved event types + a payload class; raw sensitive intake
     text is never copied into event payloads. Enforcement is a later slice.

Stdlib only (sqlite3 / json) — no new dependency (A3). Append-only is
enforced structurally by triggers, not merely by convention.

Hardening (pre-commit review, 2026-07-20): foreign keys + self-reference
CHECK on decision_relationships; append-only triggers on all four tables;
supersede_decision writes edge + event in one transaction; owner/supersede
payloads validated before insert; production reads fold with validation, so
a hand-tampered history raises instead of folding silently; a reused
idempotency_key must match the original operation or it raises.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from intent_engine.core.decision_ids import (
    format_decision_key, is_decision_key, new_ulid,
)

RECORD_SCHEMA_VERSION = 1
EVENT_SCHEMA_VERSION = 1

# Same convention as prediction_ledger.DEFAULT_LEDGER_PATH: the one real
# store lives under data/ (git-ignored), tests always pass a tmp path.
DEFAULT_DECISIONS_DB = Path("data/decisions.db")

# --- the closed event taxonomy ------------------------------------------------
LIFECYCLE_EVENTS = {
    "DecisionCreated", "OwnerAssigned", "OwnerTransferred", "DecisionSubmitted",
    "RecommendationIssued", "DecisionApproved", "DecisionDeclined",
    "ExecutionStarted", "ExecutionPaused", "ExecutionResumed",
    "ExecutionCompleted", "DecisionCancelled", "DecisionResolved",
    "DecisionCalibrated", "DecisionSuperseded", "AssumptionChanged",
}
# Typed failure/recovery events — audit-only, never silently change an axis.
FAILURE_EVENTS = {
    "AnalysisFailed", "PredictionLoggingFailed", "ReportGenerationFailed",
    "DeliveryFailed", "RetryScheduled", "RecoveryCompleted",
}
# Privacy events — reserved now, enforced in a later slice. Audit-only here.
PRIVACY_EVENTS = {
    "RedactionRequested", "AccessRestricted", "Anonymized", "Tombstoned",
}
EVENT_TYPES = LIFECYCLE_EVENTS | FAILURE_EVENTS | PRIVACY_EVENTS

ACTOR_TYPES = {"human", "agent", "system"}
SOURCES = {"web_intake", "cli", "report_review", "crm", "api", "system"}
PAYLOAD_CLASSES = {"analytical", "pii", "confidential"}

RELATIONSHIP_TYPES = {
    "supersedes", "depends_on", "blocks", "contradicts", "implements",
    "caused_by", "follow_up_to", "alternative_to", "same_initiative_as",
}
_INVERSE = {
    "supersedes": "superseded_by", "depends_on": "depended_on_by",
    "blocks": "blocked_by", "contradicts": "contradicts",
    "implements": "implemented_by", "caused_by": "caused",
    "follow_up_to": "followed_up_by", "alternative_to": "alternative_to",
    "same_initiative_as": "same_initiative_as",
}
ENTITY_RELATIONSHIP_TYPES = {
    "subject", "competitor", "partner", "acquirer", "market", "benchmark",
}


@dataclass(frozen=True)
class DecisionState:
    decision_status: str | None
    execution_status: str
    evaluation_status: str
    owner: str | None


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    decision_key: str
    created_at: str
    created_by: str
    record_schema_version: int
    metadata: dict


class TransitionError(ValueError):
    """Raised when an event is illegal given the current folded state."""


class SchemaVersionError(ValueError):
    """Raised when stored data has an unsupported future major version."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- the deterministic state machine -----------------------------------------

def _precondition(state: DecisionState, event_type: str) -> tuple[bool, str]:
    ds, es, ev = (state.decision_status, state.execution_status,
                  state.evaluation_status)
    terminal = ds in ("declined", "cancelled", "superseded")
    if event_type == "DecisionCreated":
        return (ds is None, "a decision may be created only once")
    if ds is None:
        return (False, f"{event_type} before DecisionCreated")
    if event_type == "DecisionSubmitted":
        return (ds == "draft", "DecisionSubmitted requires decision_status=draft")
    if event_type == "DecisionApproved":
        return (ds == "under_review", "DecisionApproved requires decision_status=under_review")
    if event_type == "DecisionDeclined":
        return (ds == "under_review", "DecisionDeclined requires decision_status=under_review")
    if event_type == "DecisionCancelled":
        return (ds in ("draft", "under_review", "approved"), "cannot cancel a terminal decision")
    if event_type == "DecisionSuperseded":
        return (not terminal, "cannot supersede a terminal decision")
    if event_type == "ExecutionStarted":
        return (ds == "approved" and es == "not_started",
                "ExecutionStarted requires decision_status=approved and execution_status=not_started")
    if event_type == "ExecutionPaused":
        return (es == "executing", "ExecutionPaused requires execution_status=executing")
    if event_type == "ExecutionResumed":
        return (es == "paused", "ExecutionResumed requires execution_status=paused")
    if event_type == "ExecutionCompleted":
        return (es in ("executing", "paused"), "ExecutionCompleted requires execution in progress")
    if event_type == "DecisionResolved":
        return (ds == "approved" and ev == "unresolved",
                "DecisionResolved requires an approved, unresolved decision")
    if event_type == "DecisionCalibrated":
        return (ev == "resolved", "DecisionCalibrated requires evaluation_status=resolved")
    if event_type == "OwnerAssigned":
        return (state.owner is None, "OwnerAssigned requires no current owner (use OwnerTransferred)")
    if event_type == "OwnerTransferred":
        return (state.owner is not None, "OwnerTransferred requires an existing owner")
    if event_type in ("RecommendationIssued", "AssumptionChanged"):
        return (not terminal, f"{event_type} not allowed on a terminal decision")
    return (True, "")  # failure + privacy events: audit-only, any live state


def _apply(state: DecisionState, event_type: str, payload: dict) -> DecisionState:
    ds, es, ev, owner = (state.decision_status, state.execution_status,
                         state.evaluation_status, state.owner)
    if event_type == "DecisionCreated":
        ds = "draft"
    elif event_type == "DecisionSubmitted":
        ds = "under_review"
    elif event_type == "DecisionApproved":
        ds = "approved"
    elif event_type == "DecisionDeclined":
        ds = "declined"
    elif event_type == "DecisionCancelled":
        ds = "cancelled"
        if es in ("executing", "paused"):
            es = "abandoned"
    elif event_type == "DecisionSuperseded":
        ds = "superseded"
    elif event_type == "ExecutionStarted":
        es = "executing"
    elif event_type == "ExecutionPaused":
        es = "paused"
    elif event_type == "ExecutionResumed":
        es = "executing"
    elif event_type == "ExecutionCompleted":
        es = "completed"
    elif event_type == "DecisionResolved":
        ev = "resolved"
    elif event_type == "DecisionCalibrated":
        ev = "calibrated"
    elif event_type in ("OwnerAssigned", "OwnerTransferred"):
        owner = payload.get("owner")
    return DecisionState(ds, es, ev, owner)


def validate_event(state: DecisionState, event_type: str) -> tuple[bool, str]:
    """Deterministic predicate: is this event legal given the current state?"""
    if event_type not in EVENT_TYPES:
        return (False, f"unknown event_type: {event_type}")
    return _precondition(state, event_type)


# Events whose payload MUST carry a non-empty value for state to fold truthfully.
_REQUIRED_PAYLOAD_FIELD = {
    "OwnerAssigned": "owner",
    "OwnerTransferred": "owner",
    "DecisionSuperseded": "superseded_by",
}


def _validate_payload(event_type: str, payload: dict | None) -> None:
    field = _REQUIRED_PAYLOAD_FIELD.get(event_type)
    if field is None:
        return
    value = (payload or {}).get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{event_type} requires a non-empty string payload[{field!r}]")


def fold(events, *, validate: bool = False) -> DecisionState:
    """Fold an ordered event stream (by sequence_number) into the three
    independent state axes plus current owner.

    With ``validate=True`` (production reads), every event is re-checked
    against the same deterministic preconditions used at write time, so an
    illegal history smuggled into storage by hand raises TransitionError
    instead of folding silently."""
    state = DecisionState(None, "not_started", "unresolved", None)
    for ev in events:
        event_type = ev["event_type"]
        if validate:
            ok, reason = validate_event(state, event_type)
            if not ok:
                raise TransitionError(
                    f"stored event history is invalid at {event_type}: {reason}")
        state = _apply(state, event_type, ev.get("payload") or {})
    return state


class DecisionService:
    """The ONLY coordinator for decision identity and state. The prediction
    ledger and every other consumer *reference* a decision through this
    service; none of them allocate ids, infer status, or mutate records."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        # autocommit mode: we manage BEGIN/COMMIT/ROLLBACK explicitly.
        con = sqlite3.connect(self.db_path, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    @contextmanager
    def _tx(self):
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def _init_db(self) -> None:
        con = self._connect()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS decision_records (
                    decision_id           TEXT PRIMARY KEY,
                    decision_key          TEXT UNIQUE NOT NULL,
                    created_at            TEXT NOT NULL,
                    created_by            TEXT NOT NULL,
                    record_schema_version INTEGER NOT NULL,
                    metadata              TEXT
                );
                CREATE TABLE IF NOT EXISTS decision_events (
                    event_id             TEXT PRIMARY KEY,
                    decision_id          TEXT NOT NULL REFERENCES decision_records(decision_id),
                    sequence_number      INTEGER NOT NULL,
                    event_type           TEXT NOT NULL,
                    occurred_at          TEXT NOT NULL,
                    recorded_at          TEXT NOT NULL,
                    actor_type           TEXT NOT NULL,
                    actor_id             TEXT NOT NULL,
                    source               TEXT NOT NULL,
                    idempotency_key      TEXT UNIQUE,
                    payload_class        TEXT NOT NULL,
                    payload              TEXT,
                    event_schema_version INTEGER NOT NULL,
                    UNIQUE (decision_id, sequence_number)
                );
                CREATE TABLE IF NOT EXISTS decision_entities (
                    decision_id       TEXT NOT NULL REFERENCES decision_records(decision_id),
                    entity_id         TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    UNIQUE (decision_id, entity_id, relationship_type)
                );
                CREATE TABLE IF NOT EXISTS decision_relationships (
                    from_decision_id  TEXT NOT NULL REFERENCES decision_records(decision_id),
                    to_decision_id    TEXT NOT NULL REFERENCES decision_records(decision_id),
                    relationship_type TEXT NOT NULL,
                    CHECK (from_decision_id <> to_decision_id),
                    UNIQUE (from_decision_id, to_decision_id, relationship_type)
                );
                CREATE INDEX IF NOT EXISTS idx_events_decision
                    ON decision_events(decision_id, sequence_number);

                CREATE TRIGGER IF NOT EXISTS dr_no_update
                    BEFORE UPDATE ON decision_records
                    BEGIN SELECT RAISE(ABORT, 'decision_records is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS dr_no_delete
                    BEFORE DELETE ON decision_records
                    BEGIN SELECT RAISE(ABORT, 'decision_records is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS de_no_update
                    BEFORE UPDATE ON decision_events
                    BEGIN SELECT RAISE(ABORT, 'decision_events is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS de_no_delete
                    BEFORE DELETE ON decision_events
                    BEGIN SELECT RAISE(ABORT, 'decision_events is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS rel_no_update
                    BEFORE UPDATE ON decision_relationships
                    BEGIN SELECT RAISE(ABORT, 'decision_relationships is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS rel_no_delete
                    BEFORE DELETE ON decision_relationships
                    BEGIN SELECT RAISE(ABORT, 'decision_relationships is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS ent_no_update
                    BEFORE UPDATE ON decision_entities
                    BEGIN SELECT RAISE(ABORT, 'decision_entities is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS ent_no_delete
                    BEFORE DELETE ON decision_entities
                    BEGIN SELECT RAISE(ABORT, 'decision_entities is append-only'); END;
                """
            )
        finally:
            con.close()

    # --- internal append (assumes an open transaction on `con`) --------------
    def _append(self, con, decision_id, event_type, actor_type, actor_id,
                source, *, payload, payload_class, occurred_at,
                idempotency_key) -> str:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event_type: {event_type}")
        if actor_type not in ACTOR_TYPES:
            raise ValueError(f"unknown actor_type: {actor_type}")
        if source not in SOURCES:
            raise ValueError(f"unknown source: {source}")
        if payload_class not in PAYLOAD_CLASSES:
            raise ValueError(f"unknown payload_class: {payload_class}")
        _validate_payload(event_type, payload)   # invalid payload -> zero rows
        now = _now()
        seq = con.execute(
            "SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM decision_events "
            "WHERE decision_id = ?", (decision_id,)).fetchone()[0]
        event_id = new_ulid()
        con.execute(
            "INSERT INTO decision_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, decision_id, seq, event_type, occurred_at or now, now,
             actor_type, actor_id, source, idempotency_key, payload_class,
             json.dumps(payload or {}), EVENT_SCHEMA_VERSION))
        return event_id

    # --- writes --------------------------------------------------------------
    def create_decision(self, created_by: str, *, actor_type: str = "human",
                        actor_id: str | None = None, source: str = "cli",
                        idempotency_key: str | None = None,
                        metadata: dict | None = None,
                        occurred_at: str | None = None) -> DecisionRecord:
        """Allocate a decision and append its DecisionCreated event, in one
        transaction. Idempotent: re-running with the same idempotency_key
        returns the existing record and writes nothing new."""
        actor_id = actor_id or created_by
        scoped_key = f"create:{idempotency_key}" if idempotency_key else None
        existing_id = None
        result = None
        with self._tx() as con:
            if scoped_key:
                row = con.execute(
                    "SELECT decision_id FROM decision_events WHERE idempotency_key = ?",
                    (scoped_key,)).fetchone()
                if row:
                    existing_id = row["decision_id"]
            if existing_id is None:
                now = _now()
                occurred = occurred_at or now
                year = int(occurred[:4])
                nxt = con.execute(
                    "SELECT COALESCE(MAX(CAST(substr(decision_key, 10) AS INTEGER)), 0) + 1 "
                    "FROM decision_records WHERE decision_key LIKE ?",
                    (f"DEC-{year:04d}-%",)).fetchone()[0]
                decision_id = new_ulid()
                decision_key = format_decision_key(year, nxt)
                meta = dict(metadata or {})
                con.execute("INSERT INTO decision_records VALUES (?,?,?,?,?,?)",
                            (decision_id, decision_key, now, created_by,
                             RECORD_SCHEMA_VERSION, json.dumps(meta)))
                self._append(con, decision_id, "DecisionCreated", actor_type,
                             actor_id, source,
                             payload={"decision_key": decision_key},
                             payload_class="analytical", occurred_at=occurred,
                             idempotency_key=scoped_key)
                result = DecisionRecord(decision_id, decision_key, now,
                                        created_by, RECORD_SCHEMA_VERSION, meta)
        if existing_id is not None:
            return self.get_decision(existing_id)
        return result

    def record_event(self, decision_id: str, event_type: str, *,
                     actor_type: str, actor_id: str, source: str,
                     payload: dict | None = None,
                     payload_class: str = "analytical",
                     occurred_at: str | None = None,
                     idempotency_key: str | None = None) -> str:
        """Validate the transition against the current folded state, then
        append. Returns the event_id. Idempotent on idempotency_key."""
        with self._tx() as con:
            if idempotency_key:
                row = con.execute(
                    "SELECT event_id, decision_id, event_type FROM decision_events "
                    "WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                if row:
                    # The key is globally UNIQUE; a replay must be the SAME
                    # operation. Reuse for a different decision or event type
                    # is a caller bug, never a silent no-op.
                    if (row["decision_id"] != decision_id
                            or row["event_type"] != event_type):
                        raise ValueError(
                            f"idempotency_key {idempotency_key!r} already used "
                            f"by {row['event_type']} on decision "
                            f"{row['decision_id']}; keys are scoped per operation")
                    return row["event_id"]
            self._require_decision(con, decision_id)
            state = fold(self._events(con, decision_id), validate=True)
            ok, reason = validate_event(state, event_type)
            if not ok:
                raise TransitionError(f"{event_type}: {reason}")
            return self._append(con, decision_id, event_type, actor_type,
                                actor_id, source, payload=payload,
                                payload_class=payload_class,
                                occurred_at=occurred_at,
                                idempotency_key=idempotency_key)

    def _require_decision(self, con, decision_id: str) -> None:
        if not con.execute("SELECT 1 FROM decision_records WHERE decision_id = ?",
                           (decision_id,)).fetchone():
            raise KeyError(f"no such decision: {decision_id}")

    def _add_relationship(self, con, from_decision_id: str, to_decision_id: str,
                          relationship_type: str) -> None:
        if relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"unknown relationship_type: {relationship_type}")
        if from_decision_id == to_decision_id:
            raise ValueError("a decision cannot relate to itself")
        self._require_decision(con, from_decision_id)
        self._require_decision(con, to_decision_id)
        con.execute("INSERT OR IGNORE INTO decision_relationships VALUES (?,?,?)",
                    (from_decision_id, to_decision_id, relationship_type))

    def add_relationship(self, from_decision_id: str, to_decision_id: str,
                         relationship_type: str) -> None:
        """Store ONE canonical direction. Inverses are derived on read.
        Both decisions must exist (also enforced by DB foreign keys);
        self-relationships are rejected; duplicates are idempotent."""
        with self._tx() as con:
            self._add_relationship(con, from_decision_id, to_decision_id,
                                   relationship_type)

    def add_entity(self, decision_id: str, entity_id: str,
                   relationship_type: str) -> None:
        if relationship_type not in ENTITY_RELATIONSHIP_TYPES:
            raise ValueError(f"unknown entity relationship_type: {relationship_type}")
        with self._tx() as con:
            self._require_decision(con, decision_id)
            con.execute("INSERT OR IGNORE INTO decision_entities VALUES (?,?,?)",
                        (decision_id, entity_id, relationship_type))

    def supersede_decision(self, old_decision_id: str, new_decision_id: str,
                           *, actor_type: str = "human", actor_id: str = "founder",
                           source: str = "cli") -> None:
        """Canonical edge new --supersedes--> old, plus a DecisionSuperseded
        event on the old decision — written in ONE transaction, so an illegal
        supersession (e.g. of a terminal decision) leaves zero rows behind."""
        with self._tx() as con:
            self._add_relationship(con, new_decision_id, old_decision_id,
                                   "supersedes")
            state = fold(self._events(con, old_decision_id), validate=True)
            ok, reason = validate_event(state, "DecisionSuperseded")
            if not ok:
                raise TransitionError(f"DecisionSuperseded: {reason}")
            self._append(con, old_decision_id, "DecisionSuperseded", actor_type,
                         actor_id, source,
                         payload={"superseded_by": new_decision_id},
                         payload_class="analytical", occurred_at=None,
                         idempotency_key=None)

    # --- reads ---------------------------------------------------------------
    def _events(self, con, decision_id: str) -> list[dict]:
        rows = con.execute(
            "SELECT * FROM decision_events WHERE decision_id = ? "
            "ORDER BY sequence_number", (decision_id,)).fetchall()
        out = []
        for r in rows:
            if r["event_schema_version"] > EVENT_SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"event {r['event_id']} schema v{r['event_schema_version']} "
                    f"> supported v{EVENT_SCHEMA_VERSION}")
            d = dict(r)
            d["payload"] = json.loads(r["payload"]) if r["payload"] else {}
            out.append(d)
        return out

    def get_events(self, decision_id: str) -> list[dict]:
        con = self._connect()
        try:
            return self._events(con, decision_id)
        finally:
            con.close()

    def get_decision(self, id_or_key: str) -> DecisionRecord | None:
        col = "decision_key" if is_decision_key(id_or_key) else "decision_id"
        con = self._connect()
        try:
            r = con.execute(f"SELECT * FROM decision_records WHERE {col} = ?",
                            (id_or_key,)).fetchone()
        finally:
            con.close()
        if not r:
            return None
        if r["record_schema_version"] > RECORD_SCHEMA_VERSION:
            raise SchemaVersionError(
                f"record {r['decision_id']} schema v{r['record_schema_version']} "
                f"> supported v{RECORD_SCHEMA_VERSION}")
        return DecisionRecord(
            r["decision_id"], r["decision_key"], r["created_at"],
            r["created_by"], r["record_schema_version"],
            json.loads(r["metadata"]) if r["metadata"] else {})

    def get_current_state(self, decision_id: str) -> DecisionState:
        con = self._connect()
        try:
            return fold(self._events(con, decision_id), validate=True)
        finally:
            con.close()

    def get_related_decisions(self, decision_id: str) -> dict:
        """Outgoing canonical edges + inbound edges expressed via their
        derived inverse label — the Decision-Graph read view."""
        con = self._connect()
        try:
            out = con.execute(
                "SELECT to_decision_id, relationship_type FROM decision_relationships "
                "WHERE from_decision_id = ?", (decision_id,)).fetchall()
            inbound = con.execute(
                "SELECT from_decision_id, relationship_type FROM decision_relationships "
                "WHERE to_decision_id = ?", (decision_id,)).fetchall()
        finally:
            con.close()
        return {
            "outgoing": [{"decision_id": r["to_decision_id"],
                          "relationship_type": r["relationship_type"]} for r in out],
            "incoming": [{"decision_id": r["from_decision_id"],
                          "relationship_type": _INVERSE[r["relationship_type"]]}
                         for r in inbound],
        }

    def list_decision_ids(self) -> list[str]:
        """All decision ids, in creation order (T013: the DecisionEvent
        bridge iterates decisions through the service, never raw SQL)."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT decision_id FROM decision_records "
                "ORDER BY created_at, decision_key").fetchall()
        finally:
            con.close()
        return [r["decision_id"] for r in rows]

    def get_entities(self, decision_id: str) -> list[dict]:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT entity_id, relationship_type FROM decision_entities "
                "WHERE decision_id = ?", (decision_id,)).fetchall()
        finally:
            con.close()
        return [{"entity_id": r["entity_id"],
                 "relationship_type": r["relationship_type"]} for r in rows]

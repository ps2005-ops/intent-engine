"""Backend-agnostic append-only record store (SQLite dev / Postgres prod).

One generic table, `durable_records`, holds every hosted-runtime entity as a
JSON blob discriminated by `stream` (e.g. 'paper_order', 'company_profile',
'scheduler_execution'). This mirrors the per-store JSON-blob convention the
repo already uses (see core/db.py, learning/ledger.py) but under a backend
that survives ephemeral GitHub-Actions runners and Render free restarts.

Contract (identical on both backends):

  * APPEND-ONLY. `append()` inserts one row. A "status change" to a logical
    record is a NEW row with the same (stream, record_id) — never an UPDATE.
    `latest()` folds to the most recent row per record_id; `read()` returns the
    full history (replayable).
  * IDEMPOTENT. An `idem_key` is unique within a stream. Re-appending the same
    key + same payload returns the original row and writes nothing (this is
    what makes a GitHub Action that fires twice — e.g. an order submit — safe).
    "Same payload" ignores wall-clock write stamps (created_at/at/ts/...; see
    `_VOLATILE_KEYS`), so a record re-written a second later dedupes cleanly
    instead of raising on a timestamp that means "when", not "what". Same key +
    genuinely DIFFERENT content raises IdempotencyConflict, never silently
    overwrites.
  * PORTABLE. SQL is written with `?` placeholders and translated to `%s` for
    Postgres. Payloads are TEXT JSON (portable, queryable enough, replayable).

Only sqlite3 is imported at module load. The Postgres driver (psycopg 3, then
psycopg2) is imported lazily, so development and the offline test-suite need no
database server and no extra dependency.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

DEFAULT_SQLITE_PATH = "data/intent_engine.db"


class IdempotencyConflict(RuntimeError):
    """An idem_key was reused within a stream for DIFFERENT content.

    Keys are scoped to one logical write; reusing one for different content is
    a bug (e.g. two different orders deriving the same client_order_id), and we
    fail loudly rather than clobber the first write.
    """


class StorageError(RuntimeError):
    """A backend/config problem — surfaced loudly, never guessed around."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Domain timestamps that MEAN something — when an event happened in the world,
# when data is valid/published, when a referenced record was created. These
# distinguish content and MUST stay in the idempotency fingerprint.
_MEANINGFUL_TIME_KEYS = frozenset({
    "occurred_at", "published_at", "expires_at", "latest_event_at",
    "prediction_created_at", "effective_at", "as_of",
})


def _is_write_stamp(key: str) -> bool:
    """True for a payload key that records WHEN a row was written, not WHAT it
    asserts (created_at / at / ts / *_at). These wall-clock stamps must never
    break idempotency: the same logical record re-written a moment later — a
    twice-fired job, a daily re-propose of unchanged evidence — differs only by
    them and must dedupe to a no-op, not raise IdempotencyConflict. Meaningful
    domain time (see _MEANINGFUL_TIME_KEYS) is explicitly preserved."""
    if key in _MEANINGFUL_TIME_KEYS:
        return False
    return key in ("at", "ts", "timestamp") or key.endswith("_at")


def _fingerprint(payload: Dict[str, Any]) -> str:
    """Content fingerprint used ONLY for idempotency equality (same idem_key ->
    same content?). Wall-clock write stamps are excluded so an identical record
    re-written a second later is a no-op, never a spurious conflict; genuine
    content changes (and meaningful domain timestamps) still change it."""
    core = ({k: v for k, v in payload.items() if not _is_write_stamp(k)}
            if isinstance(payload, dict) else payload)
    return sha256(
        json.dumps(core, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class DurableRecord:
    """One persisted row. `payload` is the decoded record; the rest is the
    envelope repositories query on (record_id/company_id/ref_id/status/ts)."""

    seq: int
    stream: str
    record_id: str
    status: Optional[str]
    ts: str
    idem_key: Optional[str]
    company_id: Optional[str]
    ref_id: Optional[str]
    payload: Dict[str, Any]


# --- URL resolution ----------------------------------------------------------
def resolve_database_url(url: Optional[str] = None) -> str:
    """Resolve the effective DATABASE_URL.

    Precedence: explicit arg > $DATABASE_URL > local sqlite default. Render and
    most managed Postgres providers hand out `postgres://…`; SQLAlchemy-style
    `postgresql://` is also accepted. Anything else is a config error we refuse
    to guess about.
    """
    url = url or os.environ.get("DATABASE_URL") or f"sqlite:///{DEFAULT_SQLITE_PATH}"
    scheme = urlparse(url).scheme.lower()
    if scheme in ("sqlite", "postgres", "postgresql"):
        return url
    raise StorageError(
        f"unsupported DATABASE_URL scheme {scheme!r}; use sqlite:// or postgresql://"
    )


def _is_postgres(url: str) -> bool:
    return urlparse(url).scheme.lower() in ("postgres", "postgresql")


def _sqlite_path(url: str) -> str:
    """Extract a filesystem path (or ':memory:') from a sqlite URL."""
    # sqlite:///relative/x.db -> relative/x.db ; sqlite:////abs/x.db -> /abs/x.db
    # sqlite://:memory: or sqlite:///:memory: -> :memory:
    rest = url[len("sqlite://"):]
    if rest in (":memory:", "/:memory:"):
        return ":memory:"
    return rest[1:] if rest.startswith("/") else rest


# --- backend connections -----------------------------------------------------
class _Backend:
    """Thin uniform wrapper over a DB-API connection.

    Normalises the two things that differ between sqlite3 and psycopg for the
    narrow SQL this store uses: the placeholder token and the serial-PK DDL.
    """

    paramstyle_token = "?"
    serial_pk = "INTEGER PRIMARY KEY AUTOINCREMENT"

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params: Tuple = ()):  # -> cursor
        cur = self._conn.cursor()
        cur.execute(self._translate(sql), params)
        return cur

    def _translate(self, sql: str) -> str:
        return sql

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        try:
            self._conn.rollback()
        except Exception:  # pragma: no cover - best-effort
            pass

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # pragma: no cover
            pass


class _SqliteBackend(_Backend):
    paramstyle_token = "?"
    serial_pk = "INTEGER PRIMARY KEY AUTOINCREMENT"

    @classmethod
    def connect(cls, url: str) -> "_SqliteBackend":
        path = _sqlite_path(url)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return cls(conn)


class _PostgresBackend(_Backend):
    paramstyle_token = "%s"
    serial_pk = "BIGSERIAL PRIMARY KEY"

    def _translate(self, sql: str) -> str:
        # Our SQL only uses `?` as a bound-parameter placeholder (never inside a
        # string literal), so a straight replacement is safe and readable.
        return sql.replace("?", "%s")

    @classmethod
    def connect(cls, url: str) -> "_PostgresBackend":
        driver = None
        try:  # psycopg 3
            import psycopg  # type: ignore

            driver = psycopg
            conn = psycopg.connect(url, autocommit=False)
        except ImportError:
            try:  # psycopg2 fallback
                import psycopg2  # type: ignore

                driver = psycopg2
                conn = psycopg2.connect(url)
            except ImportError as exc:  # pragma: no cover - prod-only path
                raise StorageError(
                    "DATABASE_URL is Postgres but no driver is installed; "
                    "add `psycopg[binary]` to requirements (hosted only)."
                ) from exc
        _ = driver
        return cls(conn)


def _make_backend(url: str) -> _Backend:
    if _is_postgres(url):
        return _PostgresBackend.connect(url)
    return _SqliteBackend.connect(url)


# --- the store ---------------------------------------------------------------
class DurableStore:
    """Append-only record store, backend-selected by DATABASE_URL.

    A single instance holds one connection (reused; GitHub-Actions jobs are
    short-lived and single-process). Thread-safe for the modest concurrency the
    web dashboard needs via an internal lock.
    """

    def __init__(self, url: Optional[str] = None):
        self.url = resolve_database_url(url)
        self._backend = _make_backend(self.url)
        self._lock = threading.RLock()
        self._migrated = False
        self.migrate()

    # -- schema (idempotent = the migration) ---------------------------------
    def migrate(self) -> None:
        """Create the schema if absent. Idempotent: safe to call every process
        start (which is how a fresh runner "migrates")."""
        if self._migrated:
            return
        with self._lock:
            b = self._backend
            b.execute(
                f"""CREATE TABLE IF NOT EXISTS durable_records (
                    seq        {b.serial_pk},
                    stream     TEXT NOT NULL,
                    record_id  TEXT NOT NULL,
                    status     TEXT,
                    ts         TEXT NOT NULL,
                    idem_key   TEXT,
                    company_id TEXT,
                    ref_id     TEXT,
                    payload    TEXT NOT NULL
                )"""
            )
            b.execute(
                "CREATE INDEX IF NOT EXISTS idx_dr_stream_rec "
                "ON durable_records(stream, record_id)"
            )
            b.execute(
                "CREATE INDEX IF NOT EXISTS idx_dr_stream_seq "
                "ON durable_records(stream, seq)"
            )
            b.execute(
                "CREATE INDEX IF NOT EXISTS idx_dr_company "
                "ON durable_records(stream, company_id)"
            )
            b.execute(
                "CREATE INDEX IF NOT EXISTS idx_dr_ref "
                "ON durable_records(stream, ref_id)"
            )
            b.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_dr_idem "
                "ON durable_records(stream, idem_key) WHERE idem_key IS NOT NULL"
            )
            b.commit()
            self._migrated = True

    # -- append --------------------------------------------------------------
    def append(
        self,
        stream: str,
        record_id: str,
        payload: Dict[str, Any],
        *,
        status: Optional[str] = None,
        idem_key: Optional[str] = None,
        company_id: Optional[str] = None,
        ref_id: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> DurableRecord:
        """Append one row. Returns the persisted DurableRecord.

        If `idem_key` is set and already present in this stream: same payload
        returns the ORIGINAL row (no write); different payload raises
        IdempotencyConflict. This is the deduplication a twice-fired scheduled
        job relies on.
        """
        if not stream or not record_id:
            raise ValueError("stream and record_id are required")
        ts = ts or _now_iso()
        with self._lock:
            if idem_key is not None:
                existing = self._find_by_idem(stream, idem_key)
                if existing is not None:
                    if _fingerprint(existing.payload) != _fingerprint(payload):
                        raise IdempotencyConflict(
                            f"idem_key {idem_key!r} in stream {stream!r} was "
                            "already used for different content"
                        )
                    return existing
            blob = json.dumps(payload, sort_keys=True, default=str)
            b = self._backend
            try:
                b.execute(
                    "INSERT INTO durable_records "
                    "(stream, record_id, status, ts, idem_key, company_id, "
                    " ref_id, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (stream, record_id, status, ts, idem_key, company_id,
                     ref_id, blob),
                )
                b.commit()
            except Exception as exc:  # unique-index race on idem_key
                b.rollback()
                if idem_key is not None:
                    existing = self._find_by_idem(stream, idem_key)
                    if existing is not None:
                        if _fingerprint(existing.payload) != _fingerprint(payload):
                            raise IdempotencyConflict(
                                f"idem_key {idem_key!r} in stream {stream!r} "
                                "was already used for different content"
                            ) from exc
                        return existing
                raise
            return self._find_by_idem(stream, idem_key) if idem_key is not None \
                else self._latest_row(stream, record_id)

    # -- read ----------------------------------------------------------------
    def read(
        self,
        stream: str,
        *,
        company_id: Optional[str] = None,
        ref_id: Optional[str] = None,
    ) -> List[DurableRecord]:
        """Full append-only history for a stream (oldest first) — replayable."""
        sql = ("SELECT seq, stream, record_id, status, ts, idem_key, "
               "company_id, ref_id, payload FROM durable_records WHERE stream = ?")
        params: List[Any] = [stream]
        if company_id is not None:
            sql += " AND company_id = ?"
            params.append(company_id)
        if ref_id is not None:
            sql += " AND ref_id = ?"
            params.append(ref_id)
        sql += " ORDER BY seq"
        with self._lock:
            cur = self._backend.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    def latest(
        self,
        stream: str,
        *,
        company_id: Optional[str] = None,
        ref_id: Optional[str] = None,
    ) -> List[DurableRecord]:
        """One row per record_id — the most recent (latest-wins collapsing)."""
        folded: Dict[str, DurableRecord] = {}
        for rec in self.read(stream, company_id=company_id, ref_id=ref_id):
            folded[rec.record_id] = rec  # read() is seq-ordered, last wins
        return list(folded.values())

    def get(self, stream: str, record_id: str) -> Optional[DurableRecord]:
        return self._latest_row(stream, record_id)

    def find_by_idem(self, stream: str, idem_key: str) -> Optional[DurableRecord]:
        return self._find_by_idem(stream, idem_key)

    def count(self, stream: str) -> int:
        with self._lock:
            cur = self._backend.execute(
                "SELECT COUNT(*) FROM durable_records WHERE stream = ?", (stream,)
            )
            return int(cur.fetchall()[0][0])

    def streams(self) -> List[str]:
        with self._lock:
            cur = self._backend.execute(
                "SELECT DISTINCT stream FROM durable_records ORDER BY stream", ()
            )
            return [r[0] for r in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._backend.close()

    # -- internals -----------------------------------------------------------
    def _find_by_idem(self, stream: str, idem_key: str) -> Optional[DurableRecord]:
        with self._lock:
            cur = self._backend.execute(
                "SELECT seq, stream, record_id, status, ts, idem_key, "
                "company_id, ref_id, payload FROM durable_records "
                "WHERE stream = ? AND idem_key = ? ORDER BY seq DESC",
                (stream, idem_key),
            )
            rows = cur.fetchall()
        return self._row_to_record(rows[0]) if rows else None

    def _latest_row(self, stream: str, record_id: str) -> Optional[DurableRecord]:
        with self._lock:
            cur = self._backend.execute(
                "SELECT seq, stream, record_id, status, ts, idem_key, "
                "company_id, ref_id, payload FROM durable_records "
                "WHERE stream = ? AND record_id = ? ORDER BY seq DESC",
                (stream, record_id),
            )
            rows = cur.fetchall()
        return self._row_to_record(rows[0]) if rows else None

    @staticmethod
    def _row_to_record(row) -> DurableRecord:
        (seq, stream, record_id, status, ts, idem_key, company_id, ref_id,
         payload) = row
        return DurableRecord(
            seq=int(seq), stream=stream, record_id=record_id, status=status,
            ts=ts, idem_key=idem_key, company_id=company_id, ref_id=ref_id,
            payload=json.loads(payload),
        )

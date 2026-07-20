"""Append-only row store (T016) — same flock + fsync + fingerprint
discipline as the event/CRM stores, deliberately standalone so the
knowledge subsystem depends on contracts, not other stores' internals.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from intent_engine.knowledge.records import KnowledgeError, Row

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False


class KnowledgeCorruptLogError(RuntimeError):
    pass


class RowStore:
    def __init__(self, path, allowed_types: set):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".jsonl.lock")
        self.allowed_types = allowed_types

    def _locked(self, fn):
        with open(self.lock_path, "a") as lock:
            if _HAVE_FCNTL:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                if _HAVE_FCNTL:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def read_all(self) -> list[Row]:
        if not self.path.exists():
            return []
        rows = []
        with open(self.path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    rows.append(Row.from_json(line))
                except KnowledgeError:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise KnowledgeCorruptLogError(
                        f"{self.path} line {lineno} is malformed: {exc}"
                    ) from exc
        return rows

    def find_by_idempotency_key(self, key: str) -> Row | None:
        for row in self.read_all():
            if row.idempotency_key == key:
                return row
        return None

    def for_subject(self, subject_id: str) -> list[Row]:
        return [r for r in self.read_all() if r.subject_id == subject_id]

    def append(self, row: Row) -> Row:
        row.validate(self.allowed_types)

        def _do():
            if row.idempotency_key:
                existing = self.find_by_idempotency_key(row.idempotency_key)
                if existing is not None:
                    if existing.content_fingerprint() != row.content_fingerprint():
                        raise ValueError(
                            f"idempotency_key {row.idempotency_key!r} was "
                            "already used for different content")
                    return existing
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(row.to_json() + "\n")
                f.flush()
                os.fsync(f.fileno())
            return row

        return self._locked(_do)

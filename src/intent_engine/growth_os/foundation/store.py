"""Append-only Growth-OS intelligence store.

Same durability discipline as the marketing / CRM / knowledge stores — flock,
fsync-before-success, fingerprint-checked idempotency, loud corruption, no
mutation API. Replayable by construction (`read_all` / `replay`). Generic over
`IntelRecord`; each module points it at its own `data/growth_os/<stream>.jsonl`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterable, Optional

from intent_engine.growth_os.foundation.records import GrowthOSError, IntelRecord

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False


class IntelCorruptLogError(RuntimeError):
    """The intelligence log contains a line that cannot be parsed."""


class IntelStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".jsonl.lock")

    def _locked(self, fn: Callable):
        with open(self.lock_path, "a") as lock:
            if _HAVE_FCNTL:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                if _HAVE_FCNTL:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    # -- read / replay -------------------------------------------------------
    def read_all(self) -> list[IntelRecord]:
        if not self.path.exists():
            return []
        rows: list[IntelRecord] = []
        with open(self.path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    rows.append(IntelRecord.from_json(line))
                except GrowthOSError:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise IntelCorruptLogError(
                        f"{self.path} line {lineno} is malformed: {exc}") from exc
        return rows

    def replay(self, fold: Callable, initial=None):
        """Deterministically fold the full history into a read model."""
        state = initial
        for row in self.read_all():
            state = fold(state, row)
        return state

    def for_event_type(self, event_type: str) -> list[IntelRecord]:
        return [r for r in self.read_all() if r.event_type == event_type]

    def where(self, predicate: Callable[[IntelRecord], bool]) -> list[IntelRecord]:
        return [r for r in self.read_all() if predicate(r)]

    def find_by_idempotency_key(self, key: str) -> Optional[IntelRecord]:
        for row in self.read_all():
            if row.idempotency_key == key:
                return row
        return None

    # -- write ---------------------------------------------------------------
    def append(self, row: IntelRecord) -> IntelRecord:
        """Durable, idempotent append. Same key + same content (ignoring the
        write stamp) returns the ORIGINAL and writes nothing; same key +
        genuinely different content is rejected. Returns after flush + fsync."""
        row.validate()

        def _do():
            if row.idempotency_key:
                existing = self.find_by_idempotency_key(row.idempotency_key)
                if existing is not None:
                    if existing.content_fingerprint() != row.content_fingerprint():
                        raise GrowthOSError(
                            f"idempotency_key {row.idempotency_key!r} was already "
                            "used for different content")
                    return existing
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(row.to_json() + "\n")
                f.flush()
                os.fsync(f.fileno())
            return row

        return self._locked(_do)

    def append_many(self, rows: Iterable[IntelRecord]) -> list[IntelRecord]:
        return [self.append(r) for r in rows]

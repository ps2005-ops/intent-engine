"""Append-only executive store (T021): `data/executive.jsonl`.

The established discipline, unchanged: flock, fsync before success,
fingerprint-checked idempotency, loud corruption, no mutation API, and the
(mtime_ns, size)-keyed parse cache — a queue build touches its own history
hundreds of times, which is O(n^2) in parses without it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from intent_engine.executive.records import ExecutiveError, ExecutiveEvent

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False

DEFAULT_EXECUTIVE_PATH = Path("data/executive.jsonl")


class ExecutiveCorruptLogError(RuntimeError):
    """The executive log contains a line that cannot be parsed."""


class ExecutiveStore:
    def __init__(self, path=DEFAULT_EXECUTIVE_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".jsonl.lock")
        self._cache_key = None
        self._cache_rows = None

    def _locked(self, fn):
        with open(self.lock_path, "a") as lock:
            if _HAVE_FCNTL:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                if _HAVE_FCNTL:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def _fingerprint(self):
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def read_all(self) -> list[ExecutiveEvent]:
        if not self.path.exists():
            return []
        key = self._fingerprint()
        if key is not None and key == self._cache_key:
            return list(self._cache_rows)
        rows = []
        with open(self.path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    rows.append(ExecutiveEvent.from_json(line))
                except ExecutiveError:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ExecutiveCorruptLogError(
                        f"{self.path} line {lineno} is malformed: {exc}"
                    ) from exc
        self._cache_key, self._cache_rows = key, list(rows)
        return rows

    def find_by_idempotency_key(self, key: str) -> ExecutiveEvent | None:
        for row in self.read_all():
            if row.idempotency_key == key:
                return row
        return None

    def for_field(self, field_name: str, value: str) -> list[ExecutiveEvent]:
        return [r for r in self.read_all() if getattr(r, field_name) == value]

    def for_candidate(self, candidate_id: str) -> list[ExecutiveEvent]:
        return self.for_field("candidate_id", candidate_id)

    def for_package(self, package_id: str) -> list[ExecutiveEvent]:
        return self.for_field("package_id", package_id)

    def ids(self, field_name: str) -> list[str]:
        return sorted({getattr(r, field_name) for r in self.read_all()
                       if getattr(r, field_name)})

    def append(self, row: ExecutiveEvent) -> ExecutiveEvent:
        row.validate()

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

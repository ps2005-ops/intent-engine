"""Append-only growth store (T018), namespaced.

Production and synthetic experiments use SEPARATE files and can never be
read together (improvement 6): the store is constructed for exactly one
namespace, rejects rows from any other, and refuses to parse a file whose
rows disagree with it.

Same durability discipline as the event / CRM / knowledge / marketing
stores: flock, fsync-before-success, fingerprint-checked idempotency,
loud corruption, no mutation API.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from intent_engine.growth.records import (
    NAMESPACE_PRODUCTION, NAMESPACES, GrowthError, GrowthEvent,
)

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False

DEFAULT_GROWTH_DIR = Path("data")
_FILENAMES = {"production": "growth.jsonl", "synthetic": "growth_synthetic.jsonl"}


class GrowthCorruptLogError(RuntimeError):
    """The growth log contains a line that cannot be parsed or that belongs
    to a different namespace."""


def store_path_for(namespace: str, base_dir=DEFAULT_GROWTH_DIR) -> Path:
    if namespace not in NAMESPACES:
        raise GrowthError(f"unknown namespace: {namespace!r}")
    return Path(base_dir) / _FILENAMES[namespace]


class GrowthStore:
    def __init__(self, base_dir=DEFAULT_GROWTH_DIR,
                 namespace: str = NAMESPACE_PRODUCTION):
        if namespace not in NAMESPACES:
            raise GrowthError(f"unknown namespace: {namespace!r}")
        self.namespace = namespace
        self.path = store_path_for(namespace, base_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".jsonl.lock")
        # Parse cache keyed on the file's (mtime_ns, size). An experiment
        # write path re-reads its own history several times per fact, so
        # without this the store is O(n^2) in parses for a long-running
        # experiment. Any change to the file — by us or by anyone else —
        # changes the key and invalidates the cache, so correctness and the
        # corruption checks are unaffected.
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

    def read_all(self) -> list[GrowthEvent]:
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
                    row = GrowthEvent.from_json(line)
                except GrowthError:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise GrowthCorruptLogError(
                        f"{self.path} line {lineno} is malformed: {exc}"
                    ) from exc
                if row.namespace != self.namespace:
                    raise GrowthCorruptLogError(
                        f"{self.path} line {lineno} belongs to namespace "
                        f"{row.namespace!r}, not {self.namespace!r} — "
                        "synthetic and production experiments never mix")
                rows.append(row)
        self._cache_key, self._cache_rows = key, list(rows)
        return rows

    def find_by_idempotency_key(self, key: str) -> GrowthEvent | None:
        for row in self.read_all():
            if row.idempotency_key == key:
                return row
        return None

    def for_experiment(self, experiment_id: str) -> list[GrowthEvent]:
        return [r for r in self.read_all() if r.experiment_id == experiment_id]

    def experiment_ids(self) -> list[str]:
        seen = []
        for row in self.read_all():
            if row.experiment_id not in seen:
                seen.append(row.experiment_id)
        return sorted(seen)

    def append(self, row: GrowthEvent) -> GrowthEvent:
        """Durable, idempotent append. Same key + same content returns the
        ORIGINAL row and writes nothing; same key + different content is
        rejected. Returns only after flush + fsync."""
        row.validate()
        if row.namespace != self.namespace:
            raise GrowthError(
                f"row namespace {row.namespace!r} does not match this store "
                f"({self.namespace!r})")

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

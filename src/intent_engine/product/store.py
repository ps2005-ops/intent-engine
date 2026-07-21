"""Append-only product store (T020): `data/product.jsonl`.

The established discipline, unchanged: flock, fsync before success,
fingerprint-checked idempotency, loud corruption, no mutation API, and the
(mtime_ns, size)-keyed parse cache — a portfolio rollup touches its own
history hundreds of times, which is O(n^2) in parses without it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from intent_engine.product.records import ProductError, ProductEvent

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False

DEFAULT_PRODUCT_PATH = Path("data/product.jsonl")


class ProductCorruptLogError(RuntimeError):
    """The product log contains a line that cannot be parsed."""


class ProductStore:
    def __init__(self, path=DEFAULT_PRODUCT_PATH):
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

    def read_all(self) -> list[ProductEvent]:
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
                    rows.append(ProductEvent.from_json(line))
                except ProductError:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ProductCorruptLogError(
                        f"{self.path} line {lineno} is malformed: {exc}"
                    ) from exc
        self._cache_key, self._cache_rows = key, list(rows)
        return rows

    def find_by_idempotency_key(self, key: str) -> ProductEvent | None:
        for row in self.read_all():
            if row.idempotency_key == key:
                return row
        return None

    def for_field(self, field_name: str, value: str) -> list[ProductEvent]:
        return [r for r in self.read_all() if getattr(r, field_name) == value]

    def for_proposal(self, proposal_id: str) -> list[ProductEvent]:
        return self.for_field("proposal_id", proposal_id)

    def for_problem(self, problem_id: str) -> list[ProductEvent]:
        return self.for_field("problem_id", problem_id)

    def for_opportunity(self, opportunity_id: str) -> list[ProductEvent]:
        return self.for_field("opportunity_id", opportunity_id)

    def ids(self, field_name: str) -> list[str]:
        return sorted({getattr(r, field_name) for r in self.read_all()
                       if getattr(r, field_name)})

    def append(self, row: ProductEvent) -> ProductEvent:
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

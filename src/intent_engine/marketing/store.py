"""Append-only marketing workflow store (T017): `data/marketing.jsonl`.

Same durability discipline as the event / CRM / knowledge stores — flock,
fsync-before-success, fingerprint-checked idempotency, loud corruption,
no mutation API. Deliberately standalone: marketing depends on other
subsystems' CONTRACTS, never on their storage internals.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from intent_engine.marketing.records import MarketingError, MarketingRow

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False


class MarketingCorruptLogError(RuntimeError):
    """The marketing log contains a line that cannot be parsed."""


class MarketingStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".jsonl.lock")

    def _locked(self, fn):
        with open(self.lock_path, "a") as lock:
            if _HAVE_FCNTL:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                if _HAVE_FCNTL:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def read_all(self) -> list[MarketingRow]:
        if not self.path.exists():
            return []
        rows = []
        with open(self.path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    rows.append(MarketingRow.from_json(line))
                except MarketingError:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise MarketingCorruptLogError(
                        f"{self.path} line {lineno} is malformed: {exc}"
                    ) from exc
        return rows

    def find_by_idempotency_key(self, key: str) -> MarketingRow | None:
        for row in self.read_all():
            if row.idempotency_key == key:
                return row
        return None

    def for_campaign(self, campaign_id: str) -> list[MarketingRow]:
        return [r for r in self.read_all() if r.campaign_id == campaign_id]

    def for_artifact(self, artifact_id: str) -> list[MarketingRow]:
        return [r for r in self.read_all() if r.artifact_id == artifact_id]

    def append(self, row: MarketingRow) -> MarketingRow:
        """Durable, idempotent append. Same key + same content returns the
        ORIGINAL row and writes nothing; same key + different content is
        rejected. Returns only after flush + fsync."""
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

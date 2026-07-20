"""Append-only CRM storage (T014): `marketing/crm/crm.jsonl` — the same
flock + fsync + idempotency discipline as the company event store, but
deliberately NOT importing it: the CRM depends on the Company Event
CONTRACT (envelope), never on its storage internals, so either side can
change transport without touching the other.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from intent_engine.crm.events import CRMEvent, CRMEnvelopeError

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False


class CRMCorruptLogError(RuntimeError):
    pass


class CRMStore:
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

    def read_all(self) -> list[CRMEvent]:
        if not self.path.exists():
            return []
        events = []
        with open(self.path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    events.append(CRMEvent.from_json(line))
                except CRMEnvelopeError:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise CRMCorruptLogError(
                        f"{self.path} line {lineno} is malformed: {exc}") from exc
        return events

    def find_by_idempotency_key(self, key: str) -> CRMEvent | None:
        for ev in self.read_all():
            if ev.idempotency_key == key:
                return ev
        return None

    def append(self, event: CRMEvent) -> CRMEvent:
        """Durable, idempotent append. Same key + same content returns the
        ORIGINAL event and writes nothing; same key + different content is
        rejected. Returns only after flush + fsync."""
        event.validate()

        def _do():
            if event.idempotency_key:
                existing = self.find_by_idempotency_key(event.idempotency_key)
                if existing is not None:
                    if existing.content_fingerprint() != event.content_fingerprint():
                        raise ValueError(
                            f"idempotency_key {event.idempotency_key!r} was "
                            "already used for different content")
                    return existing
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
                f.flush()
                os.fsync(f.fileno())
            return event

        return self._locked(_do)

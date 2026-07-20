"""Append-only company event storage (T013).

Layout under one directory (default `events/`):

    events.jsonl       the log — one event per line, append-only, fsync'd
    events.jsonl.lock  flock file guarding single-host concurrent appends
    checkpoints.json   per-consumer offsets, SEPARATE from the immutable log
    dead_letter.jsonl  append-only failure records (see consumer.py)

The public API has no update or delete. Malformed log lines fail loudly
(CorruptLogError) — there is no partial-line recovery convention in this
repository, so none is invented here. The JSONL file is the V1 transport;
a broker can replace it later without touching producers or consumers.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from intent_engine.events.envelope import CompanyEvent, EnvelopeError

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows fallback, single writer
    _HAVE_FCNTL = False


class CorruptLogError(RuntimeError):
    """The event log contains a line that cannot be parsed."""


class CheckpointError(RuntimeError):
    """The checkpoint file is unreadable — fail loudly, never guess."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EventStore:
    def __init__(self, dir_path):
        self.dir = Path(dir_path)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.dir / "events.jsonl"
        self.lock_path = self.dir / "events.jsonl.lock"
        self.checkpoint_path = self.dir / "checkpoints.json"
        self.dead_letter_path = self.dir / "dead_letter.jsonl"

    # --- the append-only log --------------------------------------------------
    def _locked(self, fn):
        with open(self.lock_path, "a") as lock:
            if _HAVE_FCNTL:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                if _HAVE_FCNTL:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def read_all(self) -> list[CompanyEvent]:
        if not self.log_path.exists():
            return []
        events = []
        with open(self.log_path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    events.append(CompanyEvent.from_json(line))
                except EnvelopeError:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise CorruptLogError(
                        f"{self.log_path} line {lineno} is malformed: {exc}"
                    ) from exc
        return events

    def find_by_idempotency_key(self, key: str) -> CompanyEvent | None:
        for ev in self.read_all():
            if ev.idempotency_key == key:
                return ev
        return None

    def find_by_event_id(self, event_id: str) -> CompanyEvent | None:
        for ev in self.read_all():
            if ev.event_id == event_id:
                return ev
        return None

    def append(self, event: CompanyEvent) -> CompanyEvent:
        """Validate, deduplicate on idempotency_key, then durably append.
        Only returns after flush + fsync — a successful return means the
        event cannot be lost. Same key + same content -> the ORIGINAL event
        is returned and zero lines are written; same key + different
        content -> ValueError."""
        event.validate()

        def _do():
            if event.idempotency_key:
                existing = self.find_by_idempotency_key(event.idempotency_key)
                if existing is not None:
                    if (existing.content_fingerprint()
                            != event.content_fingerprint()):
                        raise ValueError(
                            f"idempotency_key {event.idempotency_key!r} was "
                            "already used for different content — keys are "
                            "scoped to one logical event")
                    return existing
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
                f.flush()
                os.fsync(f.fileno())
            return event

        return self._locked(_do)

    # --- consumer checkpoints (separate from the log) -------------------------
    def read_checkpoints(self) -> dict:
        if not self.checkpoint_path.exists():
            return {}
        try:
            data = json.loads(self.checkpoint_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise CheckpointError(
                f"{self.checkpoint_path} is unreadable: {exc}") from exc
        if not isinstance(data, dict):
            raise CheckpointError(f"{self.checkpoint_path} is not an object")
        return data

    def get_checkpoint(self, consumer_name: str) -> int:
        entry = self.read_checkpoints().get(consumer_name)
        return int(entry["offset"]) if entry else 0

    def set_checkpoint(self, consumer_name: str, offset: int) -> None:
        """Atomic replace via temp file + rename; advancing is the CALLER's
        contract — only after successful processing (see consumer.drain)."""
        def _do():
            data = self.read_checkpoints()
            data[consumer_name] = {"offset": int(offset),
                                   "updated_at": _now()}
            tmp = self.checkpoint_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
            os.replace(tmp, self.checkpoint_path)
        self._locked(_do)

    # --- dead letters (append-only; see consumer.py for policy) ---------------
    def append_dead_letter(self, entry: dict) -> None:
        def _do():
            with open(self.dead_letter_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
        self._locked(_do)

    def read_dead_letters(self) -> list[dict]:
        if not self.dead_letter_path.exists():
            return []
        out = []
        with open(self.dead_letter_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
        return out

"""The one append-only store implementation (T022).

Extracted verbatim from `research/store.py`, `product/store.py`, and
`executive/store.py`, which held three byte-identical copies of this
discipline (flock, fsync before success, fingerprint-checked idempotency,
loud corruption, no mutation API, and the `(mtime_ns, size)`-keyed parse
cache). Each agent store now subclasses `AppendOnlyStore` and adds only
its domain query methods.

Behaviour is identical to the three originals — this class was written by
lifting the shared body, not by redesigning it. The only parameters a
subclass supplies are the event class it stores, the error its records
raise (re-raised untouched during a parse so a validation failure is not
mistaken for corruption), and the corruption error it raises for a
genuinely malformed line.

The subclass contract:

    class MyStore(AppendOnlyStore):
        event_cls = MyEvent          # has from_json, validate,
                                     # content_fingerprint, subject_id
        record_error = MyError       # re-raised as-is on a parse
        corrupt_error = MyCorruptLogError

`event_cls` must expose `subject_id` on its instances (every agent event
does), because `find_by_idempotency_key` returns the row and callers read
`.subject_id` off it — the `stable_id` helper depends on this.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False


class CorruptLogError(RuntimeError):
    """An append-only log contains a line that cannot be parsed.

    Agents subclass this so their corruption errors keep their own type
    name and remain catchable exactly as before extraction.
    """


class AppendOnlyStore:
    # --- subclass contract ---------------------------------------------------
    event_cls = None          # the event dataclass; set by the subclass
    record_error = ValueError  # re-raised untouched during a parse
    corrupt_error = CorruptLogError

    def __init__(self, path):
        if self.event_cls is None:  # pragma: no cover - programming error
            raise TypeError(
                f"{type(self).__name__} must set event_cls before use")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".jsonl.lock")
        self._cache_key = None
        self._cache_rows = None

    # --- the shared mechanics (identical across all three originals) ---------
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

    def read_all(self) -> list:
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
                    rows.append(self.event_cls.from_json(line))
                except self.record_error:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    raise self.corrupt_error(
                        f"{self.path} line {lineno} is malformed: {exc}"
                    ) from exc
        self._cache_key, self._cache_rows = key, list(rows)
        return rows

    def find_by_idempotency_key(self, key: str):
        for row in self.read_all():
            if row.idempotency_key == key:
                return row
        return None

    def append(self, row):
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

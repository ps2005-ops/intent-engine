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
        #: Byte offset the cached rows were parsed up to.
        self._cache_offset = None

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

    def _parse_from(self, offset: int, first_lineno: int) -> list:
        """Parse from a BYTE offset, which is why this reads binary.

        `seek()` on a text-mode file takes an opaque cookie from `tell()`,
        not a byte count -- passing `st_size` happens to work in CPython and
        is undefined behaviour. The offset here comes from `stat`, so the
        file is opened in binary and each line is decoded explicitly.
        """
        rows = []
        with open(self.path, "rb") as f:
            if offset:
                f.seek(offset)
            for lineno, raw in enumerate(f, first_lineno):
                line = raw.decode("utf-8").rstrip("\n")
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
        return rows

    def read_all(self) -> list:
        """Every row, parsed once.

        WHY THE CACHE WAS NOT ENOUGH. It is keyed on `(mtime_ns, size)`, which
        is exactly the pair that changes on every append -- so during the one
        activity that matters, an analysis writing documents, the cache missed
        on EVERY read and the whole log was re-parsed each time. `append`
        itself calls `read_all` for its idempotency check, so writing N
        documents cost O(N^2) parsing, and each `/progress` poll paid for a
        full re-parse of a file the run was still growing. Measured on a
        31 MB log: 35 ms per full parse, 153 ms for the four queries one
        progress poll makes, and both grow without bound as the file does.
        //
        AN APPEND-ONLY LOG NEVER REWRITES ITS PREFIX, which is what makes
        this safe: when the file has only grown, the rows already parsed are
        still correct and only the new bytes need reading. Anything else --
        the file shrinking, being replaced, or changing without growing --
        falls back to the full parse, so no assumption is made that the
        discipline is not already enforcing.
        """
        if not self.path.exists():
            self._cache_key = self._cache_rows = self._cache_offset = None
            return []
        key = self._fingerprint()
        if key is not None and key == self._cache_key:
            return list(self._cache_rows)
        size = key[1] if key else 0
        offset = getattr(self, "_cache_offset", None)
        if (self._cache_rows is not None and offset is not None
                and size > offset):
            # Grown only: parse the tail and keep what was already read.
            rows = list(self._cache_rows) + self._parse_from(
                offset, len(self._cache_rows) + 1)
        else:
            rows = self._parse_from(0, 1)
        self._cache_key, self._cache_rows, self._cache_offset = \
            key, list(rows), size
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

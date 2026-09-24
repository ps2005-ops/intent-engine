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
import logging
import os
from pathlib import Path

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False

_LOG = logging.getLogger(__name__)


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
        #: `_locked` is re-entrant because `append` holds the lock and then
        #: calls `read_all` for its idempotency check -- and `read_all` now
        #: repairs a torn tail, which is itself a write. `flock` is held per
        #: OPEN FILE DESCRIPTION, so a second `open`+`LOCK_EX` from inside
        #: the first would block on a lock this very thread owns. Counting
        #: the depth keeps the outermost acquisition the only real one.
        self._lock_depth = 0

    # --- the shared mechanics (identical across all three originals) ---------
    def _locked(self, fn):
        if self._lock_depth:            # already ours; see `_lock_depth`
            return fn()
        with open(self.lock_path, "a") as lock:
            if _HAVE_FCNTL:
                fcntl.flock(lock, fcntl.LOCK_EX)
            self._lock_depth += 1
            try:
                return fn()
            finally:
                self._lock_depth -= 1
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
        #: Where the FIRST unparseable line begins, and what it was. Scanning
        #: continues past it: whether this is a survivable torn tail or real
        #: interior corruption is decided by what comes AFTER, and raising on
        #: sight is what made a single bad line unanswerable.
        torn_at = torn_lineno = torn_exc = None
        good_after_torn = False
        pos = offset
        with open(self.path, "rb") as f:
            if offset:
                f.seek(offset)
            for lineno, raw in enumerate(f, first_lineno):
                start, pos = pos, pos + len(raw)
                try:
                    line = raw.decode("utf-8").rstrip("\n")
                except UnicodeDecodeError as exc:
                    # A HALF-WRITTEN LINE NEED NOT BE VALID UTF-8, and this
                    # was not in the caught set -- so a torn multi-byte
                    # character escaped as an unhandled 500 rather than as
                    # this store's own corruption error.
                    if torn_at is None:
                        torn_at, torn_lineno, torn_exc = start, lineno, exc
                    continue
                if not line:
                    continue
                try:
                    row = self.event_cls.from_json(line)
                except self.record_error:
                    raise
                except (json.JSONDecodeError, TypeError) as exc:
                    if torn_at is None:
                        torn_at, torn_lineno, torn_exc = start, lineno, exc
                    continue
                if torn_at is not None:
                    good_after_torn = True
                rows.append(row)
        if torn_at is None:
            return rows
        if good_after_torn:
            # INTERIOR CORRUPTION. Something rewrote the middle of a file
            # that is only ever appended to, so the damage is not bounded by
            # what was in flight and no record here can be assumed
            # unacknowledged. Refusing to read is still right, and the
            # caller now turns it into an honest answer instead of a 500.
            raise self.corrupt_error(
                f"{self.path} line {torn_lineno} is malformed: {torn_exc}"
            ) from torn_exc
        # A TORN TAIL, AND IT IS SAFE TO DROP.
        #
        # MEASURED IN PRODUCTION. `data/company_ingestion.jsonl` line 145
        # went malformed on the deployed preview and every POST /analyze
        # answered HTTP 500 from that moment on -- for hours, across the
        # whole 50-company batch -- because `read_all` parses the entire log
        # and raised on sight. `create_run` calls it, `/progress` calls it,
        # `/runs/<id>/conversation` calls it: one unparseable byte took the
        # product down and no restart could be counted on to clear it.
        #
        # Nothing after this offset parses, which is the signature of a write
        # that never completed -- an unclean kill, or ENOSPC on the free
        # tier's ephemeral disk. A trailing record that cannot be read was
        # never handed back to any caller as durable, and keeping the bytes
        # buys nothing: they are unreadable either way. Truncating restores
        # a log that is exactly the acknowledged prefix.
        #
        # This is NOT permission to skip malformed lines in general. The
        # branch above still refuses anything with a readable record after
        # the damage, which is the case where dropping would lose history.
        self._truncate_torn_tail(torn_at, torn_lineno, torn_exc)
        return rows

    def _truncate_torn_tail(self, offset: int, lineno, exc) -> None:
        """Drop an unreadable trailing region, under the store's own lock."""
        def _do():
            size = self.path.stat().st_size
            if offset >= size:                  # already repaired
                return
            os.truncate(self.path, offset)
            _LOG.warning(
                "append-only log %s had an unreadable tail from line %s "
                "(%s: %s); truncated %d byte(s) back to the last complete "
                "record", self.path, lineno, type(exc).__name__, exc,
                size - offset)
            self._cache_key = self._cache_rows = self._cache_offset = None
        self._locked(_do)

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
        # RE-STAT AFTER PARSING, because parsing may have REPAIRED the file:
        # a torn tail is truncated during the scan, and caching the size the
        # file had before that would leave `_cache_offset` past the new end
        # of the file -- an offset every later incremental read would seek to
        # and read nothing from.
        key = self._fingerprint()
        size = key[1] if key else 0
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
            # A WRITE THAT FAILS MUST LEAVE NOTHING BEHIND.
            #
            # The torn tail this store now recovers from had to be written by
            # something, and this is the only thing that writes it: a
            # `write`/`flush`/`fsync` that dies half-way -- ENOSPC on the
            # free tier's small ephemeral disk, or the process being killed
            # -- leaves a partial line, and the log is corrupt from then on.
            # Recording the size first makes the append all-or-nothing: on
            # any failure the file goes back to exactly the last complete
            # record, so the reader never sees the fragment.
            before = self.path.stat().st_size if self.path.exists() else 0
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(row.to_json() + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except BaseException:
                # BaseException deliberately: a KeyboardInterrupt or a
                # SystemExit between `write` and `fsync` corrupts the log
                # exactly as an OSError does.
                try:
                    if self.path.exists() and self.path.stat().st_size != before:
                        os.truncate(self.path, before)
                except OSError:                 # pragma: no cover
                    pass                        # already failing; say so below
                raise
            return row

        return self._locked(_do)

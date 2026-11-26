"""Single-execution job locking — restart-safe, duplicate-safe.

A scheduled job must never run twice concurrently (two workers, an overlap
after a slow run, a manual run during a scheduled one). This is an
flock-based advisory lock on a file under the run root, mirroring the event
store's own `_locked` pattern (stdlib fcntl, single-host). Acquisition is
non-blocking: a second holder fails fast with JobLockedError rather than
piling up.

The lock is process-scoped and released on exit OR process death (the OS
drops the flock when the fd closes), so a crashed job does not wedge the
next run — that is the "restart-safe" property.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows single-writer fallback
    _HAVE_FCNTL = False


class JobLockedError(RuntimeError):
    """Another holder owns this job lock right now."""


class JobLock:
    def __init__(self, name: str, *, root: Path):
        self.name = name
        self.dir = Path(root) / "locks"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{name}.lock"
        self._fh = None

    def __enter__(self):
        self._fh = open(self.path, "a")
        if _HAVE_FCNTL:
            try:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as exc:
                self._fh.close()
                self._fh = None
                raise JobLockedError(
                    f"job {self.name!r} is already running") from exc
        # The file is reused across runs and flock never touches its mtime, so
        # `lock_state` read the age of a file created in August as the age of
        # tonight's lock: every cycle's own health check reported its lock
        # "held 117 days, stale" and the runtime DEGRADED (2026-11-25). Mark
        # the acquisition, so the age is the holding time.
        try:
            os.utime(self.path, None)
        except OSError:  # pragma: no cover
            pass
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            if _HAVE_FCNTL:
                try:
                    fcntl.flock(self._fh, fcntl.LOCK_UN)
                except OSError:  # pragma: no cover
                    pass
            self._fh.close()
            self._fh = None
        return False

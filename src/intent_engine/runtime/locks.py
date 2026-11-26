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

import json
import os
import time
from pathlib import Path

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows single-writer fallback
    _HAVE_FCNTL = False


class JobLockedError(RuntimeError):
    """Another holder owns this job lock right now."""


class JobLock:
    """`wait_seconds` bounds how long to wait for a live holder (0 = fail
    fast, the original behaviour). The deadline is WALL-clock: on a laptop
    the holder may be suspended by system sleep, and a monotonic wait would
    stretch with it. `owner` is written beside the lock (never into it) so a
    refused caller can say who holds it."""

    def __init__(self, name: str, *, root: Path, wait_seconds: float = 0.0,
                 owner: dict = None, clock=time.time, sleep=time.sleep):
        self.name = name
        self.dir = Path(root) / "locks"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{name}.lock"
        self.owner_path = self.dir / f"{name}.owner.json"
        self.wait_seconds = max(0.0, float(wait_seconds or 0))
        self.owner = dict(owner or {})
        self.waited = 0.0
        self._clock, self._sleep = clock, sleep
        self._fh = None

    def holder(self) -> dict:
        try:
            return json.loads(self.owner_path.read_text())
        except (OSError, ValueError):
            return {}

    def __enter__(self):
        self._fh = open(self.path, "a")
        if _HAVE_FCNTL:
            start, slept = self._clock(), 0.0
            # Elapsed is the larger of the clock and the sleep requested, so
            # an injected (fake) sleep ends the wait instead of busy-spinning
            # against a real clock.
            elapsed = lambda: max(self._clock() - start, slept)  # noqa: E731
            while True:
                try:
                    fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (OSError, BlockingIOError) as exc:
                    left = self.wait_seconds - elapsed()
                    if left <= 0:
                        self.waited = elapsed()
                        self._fh.close()
                        self._fh = None
                        held = self.holder()
                        raise JobLockedError(
                            f"job {self.name!r} is already running"
                            + (f" (held by {held})" if held else "")) from exc
                    step = min(30.0, left)
                    self._sleep(step)
                    slept += step
            self.waited = elapsed()
        if self.owner:
            try:
                self.owner_path.write_text(json.dumps(
                    {**self.owner, "pid": os.getpid(),
                     "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime())}))
            except OSError:  # pragma: no cover
                pass
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

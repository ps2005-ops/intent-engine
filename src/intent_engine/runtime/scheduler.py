"""In-process scheduler — the deployable scheduling path for a file-based
platform on Render.

Why in-process: Render persistent disks attach to exactly ONE service and are
never shared, so separate Cron Job services cannot see the web service's
append-only stores. The correct topology for this disk-based design is a
single always-on web service that runs the schedule itself. Every job still
goes through run_job (JobLock + persistent events), so even two instances
cannot double-run a job.

The due-logic is a pure function (testable without threads or sleeping); the
daemon thread is a thin loop over it. State is a single atomic marker file
(status/scheduler.json = {job: last_fired_iso}), so scheduling is restart-safe
and idempotent: a job fires at most once per its period, and a fire whose
sub-jobs failed does NOT advance the marker, so the next tick retries it.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from intent_engine.runtime.market_calendar import is_market_day, now_ny

# job -> cadence. "daily" is the market composite (market-day gated);
# "synthetic-daily" runs every day (no market data needed).
SCHEDULE = {
    "daily": "market_day",
    "synthetic-daily": "daily",
    "weekly-eval": "weekly",
    "monthly-packet": "monthly",
}


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def is_due(cadence: str, now: datetime, last_fired: Optional[str], *,
           market_day: bool) -> bool:
    """Pure: is a job of this cadence due at `now`, given when it last fired?"""
    prev = _parse(last_fired)
    if cadence == "market_day":
        if not market_day:
            return False
        return prev is None or prev.date() < now.date()
    if cadence == "daily":
        return prev is None or prev.date() < now.date()
    if cadence == "weekly":
        if prev is None:
            return True
        return (now.year, now.isocalendar()[1]) != (prev.year, prev.isocalendar()[1])
    if cadence == "monthly":
        if prev is None:
            return True
        return (now.year, now.month) != (prev.year, prev.month)
    raise ValueError(f"unknown cadence {cadence!r}")


class MarkerStore:
    def __init__(self, root: Path):
        self.path = Path(root) / "status" / "scheduler.json"

    def read(self) -> Dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def advance(self, job: str, when: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self.read()
        data[job] = when
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        os.replace(tmp, self.path)      # atomic


def due_jobs(now: datetime, markers: Dict[str, str], *,
             market_day_fn: Callable[[], bool] = None) -> List[str]:
    market_day = (market_day_fn or (lambda: is_market_day(now.date())))()
    return [job for job, cadence in SCHEDULE.items()
            if is_due(cadence, now, markers.get(job), market_day=market_day)]


def run_due(root, *, now: Optional[datetime] = None,
            dispatch_fn: Callable = None,
            market_day_fn: Callable[[], bool] = None) -> Dict[str, str]:
    """Run every due job once. Advances a job's marker ONLY if all its
    sub-jobs succeeded (so a failure retries next tick). Returns {job: outcome}.
    Idempotent within a period and safe across instances (run_job holds the
    JobLock)."""
    now = now or now_ny()
    root = Path(root)
    markers = MarkerStore(root)
    if dispatch_fn is None:
        from intent_engine.runtime.__main__ import dispatch as dispatch_fn
    outcome: Dict[str, str] = {}
    for job in due_jobs(now, markers.read(), market_day_fn=market_day_fn):
        results = dispatch_fn(job, root, as_of=now.date().isoformat())
        ok = bool(results) and all(r.status == "succeeded" for r in results)
        if ok:
            markers.advance(job, now.isoformat(timespec="seconds"))
        outcome[job] = "fired" if ok else "failed_will_retry"
    return outcome


class Scheduler:
    """Daemon-thread loop over run_due. Disabled unless explicitly enabled, so
    tests and dev never spawn it."""

    def __init__(self, root, *, tick_seconds: int = 300):
        self.root = Path(root)
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("SCHEDULER_ENABLED", "").lower() in (
            "1", "true", "yes")

    def start(self) -> "Scheduler":
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="ie-scheduler")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:  # pragma: no cover - exercised via run_due in tests
        while not self._stop.wait(self.tick_seconds):
            try:
                run_due(self.root)
            except Exception:  # noqa: BLE001 - a tick error must not kill the loop
                continue

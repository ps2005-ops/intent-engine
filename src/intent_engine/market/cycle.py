"""Day and night operating cycles — the unattended runtime.

WHAT CHANGES ON DAY 17
----------------------
For sixteen days a cycle was "a human ran a script and read the output". The
human was doing four jobs that were never written down: deciding it was time to
run, noticing when a step failed, deciding whether a partial result was worth
keeping, and remembering what yesterday's run had already done. Unattended
operation has to do all four, and every one of them is a place where a system
can quietly lie to itself.

THE FOUR THINGS THIS MUST NOT DO
--------------------------------
1. **Count the same market bar twice.** The single highest-value guard here.
   Re-reading Friday's close on Saturday and Sunday would inflate the sample by
   40% and narrow every confidence interval, and nothing would error. Gated on
   `MarketSession.has_new_market_observation`, which is computed against what
   the previous cycle actually ingested.
2. **Record a success it did not have.** A step that failed makes the cycle
   PARTIAL or FAILED. There is no path that writes COMPLETED over a failed
   step, and PARTIAL names exactly which steps ran.
3. **Turn a failure into a zero.** `evidence: 0` because the feed was down is
   not the same measurement as `evidence: 0` because nothing was published, and
   the first must never enter a rolling mean. Failed steps contribute no
   counts.
4. **Run twice.** Two guards, deliberately different in kind: an flock (two
   processes at the same instant) and a durable run identity (the same
   operating day, hours apart, after a reboot).

RUN IDENTITY
------------
    YYYY-MM-DD:<cycle>:<timezone>        e.g. 2026-07-31:day:America/Toronto

The date is the operating day in `America/Toronto`, never the machine's local
day and never UTC. This is what makes duplicate protection survive a reboot, a
daylight-saving transition, and a laptop that changed timezone.

DAY VERSUS NIGHT
----------------
They are different cycles, not the same cycle run twice, and the difference is
principled: the day cycle runs pre-market and reads the PREVIOUS session's
completed bar; the night cycle runs after the close and reads TODAY's. When
they would read the same bar -- a weekend, a holiday, a vendor that has not
published -- the second one says so and does not count it. Neither is permitted
to present a re-read bar as a new market session.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from intent_engine.market import failures as F
from intent_engine.market import session as S
from intent_engine.market.trading_mode import assert_paper_only
from intent_engine.runtime.locks import JobLock, JobLockedError

DAY = "day"
NIGHT = "night"
CYCLES = (DAY, NIGHT)

# Scheduled local-time targets, in the operating timezone.
SCHEDULE = {DAY: (6, 30), NIGHT: (20, 30)}

# --- run statuses -----------------------------------------------------------
STARTED = "STARTED"
COMPLETED = "COMPLETED"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
SKIPPED_STALE_DATA = "SKIPPED_STALE_DATA"
SKIPPED_NO_NEW_MARKET_SESSION = "SKIPPED_NO_NEW_MARKET_SESSION"

STATUSES = (STARTED, COMPLETED, PARTIAL, FAILED, SKIPPED_DUPLICATE,
            SKIPPED_STALE_DATA, SKIPPED_NO_NEW_MARKET_SESSION)

# The lock is shared by BOTH cycles. A night run must not start while a slow
# day run is still going: they write the same funnel history and the same
# ledger, and interleaving them would corrupt both.
LOCK_NAME = "market-cycle"

RUNS_FILE = "status/market_cycles.jsonl"
REPORT_DIR = "reports/market"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_id(day: str, cycle: str, tz: str = S.TIMEZONE) -> str:
    """Deterministic identity. Same day + same cycle == same id, always."""
    if cycle not in CYCLES:
        raise ValueError(f"unknown cycle {cycle!r}; expected one of {CYCLES}")
    return f"{day[:10]}:{cycle}:{tz}"


@dataclass(frozen=True)
class Step:
    name: str
    status: str                 # ok | failed | skipped
    detail: dict = field(default_factory=dict)
    code: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status,
                "detail": self.detail, "code": self.code,
                "error": self.error, "attempts": self.attempts}


@dataclass(frozen=True)
class CycleResult:
    run_id: str
    cycle: str
    as_of: str
    timezone: str
    status: str
    reason: str = ""
    session: dict = field(default_factory=dict)
    steps: tuple = ()
    started_at: str = ""
    finished_at: str = ""
    trading_mode: str = ""
    dry_run: bool = False
    report_paths: dict = field(default_factory=dict)

    @property
    def failed_steps(self) -> List[Step]:
        return [s for s in self.steps if s.status == "failed"]

    @property
    def exit_code(self) -> int:
        """Nonzero on anything that is not a clean completion or a deliberate
        skip. launchd surfaces this, and a human's `status` reads it."""
        return 0 if self.status in (COMPLETED, SKIPPED_DUPLICATE,
                                    SKIPPED_NO_NEW_MARKET_SESSION) else 1

    def as_dict(self) -> dict:
        return {"run_id": self.run_id, "cycle": self.cycle,
                "as_of": self.as_of, "timezone": self.timezone,
                "status": self.status, "reason": self.reason,
                "session": self.session,
                "steps": [s.as_dict() for s in self.steps],
                "started_at": self.started_at, "finished_at": self.finished_at,
                "trading_mode": self.trading_mode, "dry_run": self.dry_run,
                "report_paths": dict(self.report_paths),
                "exit_code": self.exit_code}


class RunStore:
    """Append-only run records. The durable memory that makes duplicate
    protection survive a restart -- an flock only knows about right now."""

    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.path = self.root / RUNS_FILE

    def append(self, result: CycleResult) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(result.as_dict(), sort_keys=True,
                                default=str) + "\n")

    def all(self) -> List[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def find(self, rid: str) -> List[dict]:
        return [r for r in self.all() if r.get("run_id") == rid]

    def completed(self, rid: str) -> Optional[dict]:
        """A prior COMPLETED record for this identity, if one exists.

        Two exclusions, both deliberate:

        * Only COMPLETED counts. A previous PARTIAL or FAILED run must NOT
          block a retry -- that would make one bad night permanently
          unrecoverable, which is the opposite of restart-safe.
        * A DRY RUN never counts. A rehearsal is not an operating cycle, and
          letting one satisfy the duplicate check would mean rehearsing at
          06:00 silently cancels the real 06:30 run.
        """
        for row in self.find(rid):
            if row.get("status") == COMPLETED and not row.get("dry_run"):
                return row
        return None

    def latest(self, cycle: Optional[str] = None) -> Optional[dict]:
        rows = [r for r in self.all()
                if cycle is None or r.get("cycle") == cycle]
        return rows[-1] if rows else None

    def last_ingested_bar(self) -> Optional[str]:
        """The newest completed bar any prior cycle actually ingested.

        This is what makes "is this a NEW market observation?" answerable. It
        reads the recorded session of past runs rather than a price feed,
        because the question is about what THIS ENGINE has already counted.
        """
        for row in reversed(self.all()):
            if row.get("status") not in (COMPLETED, PARTIAL):
                continue
            if row.get("dry_run"):
                continue          # a rehearsal ingested nothing
            bar = (row.get("session") or {}).get("latest_bar")
            if bar:
                return bar
        return None


def lock_state(root) -> dict:
    """Is a cycle running right now, and how old is the lock file?

    Probed by ACQUIRING the lock, which is the only honest test: a lock file
    exists whether or not anyone holds it, so its presence proves nothing.
    flock is released by the OS when the holder dies, so a crashed run leaves a
    file but not a held lock -- and this reports exactly that difference.
    """
    root = pathlib.Path(root)
    path = root / "locks" / f"{LOCK_NAME}.lock"
    age = None
    if path.exists():
        age = round(time.time() - path.stat().st_mtime, 1)
    try:
        with JobLock(LOCK_NAME, root=root):
            held = False
    except JobLockedError:
        held = True
    except OSError:  # pragma: no cover - unwritable root
        held = False
    return {"path": str(path), "exists": path.exists(), "held": held,
            "age_seconds": age,
            # A file with no holder is not stale, it is just a leftover. The
            # word "stale" is reserved for a lock that IS held far longer than
            # any cycle should take, which is the case a human must act on.
            "stale": bool(held and age is not None and age > 6 * 3600)}


StepFn = Callable[["CycleContext"], dict]


@dataclass
class CycleContext:
    """Everything a step needs. Passed to each step so steps stay independent
    of each other and individually testable."""
    cycle: str
    as_of: str
    root: pathlib.Path
    session: S.MarketSession
    run_id: str
    dry_run: bool = False
    results: Dict[str, dict] = field(default_factory=dict)
    # Evidence handed from the research sweep to the learning step, in its
    # object form. Deliberately NOT part of `results`: only `results` is
    # serialised into the cycle report, and a few hundred full evidence rows
    # per company would bloat every report to no reader's benefit. The
    # durable copy of this evidence is the learning ledger, which the
    # learning step writes.
    learning_inbox: List[Any] = field(default_factory=list)
    # Bounded translation counts, accumulated across the sweep. Counts only —
    # this one IS reported, because an operator cannot otherwise tell a sweep
    # that found nothing from a sweep that dropped everything it found.
    translation_stats: Any = field(
        default_factory=lambda: __import__(
            "intent_engine.market.evidence_translation", fromlist=["x"]
        ).TranslationStats())


def run_step(name: str, fn: StepFn, ctx: CycleContext, *,
             attempts: int = 3, sleep: Callable[[float], None] = time.sleep
             ) -> Step:
    """One step, with retries for transient failures only.

    A failure is RECORDED and the cycle continues to the next step. That is
    what makes PARTIAL a real outcome rather than a label: an unreachable news
    feed must not stop the funnel, the stability report and the health record
    from being produced, because those are exactly what a human needs in order
    to see that the feed was unreachable.
    """
    detail, attempt = F.retry(lambda: fn(ctx), attempts=attempts, sleep=sleep)
    if attempt.ok:
        ctx.results[name] = detail or {}
        return Step(name, "ok", detail or {}, attempts=attempt.attempts)
    return Step(name, "failed", {}, code=attempt.code, error=attempt.error,
                attempts=attempt.attempts)


def run_cycle(cycle: str, *, root, steps: Sequence[Tuple[str, StepFn]],
              as_of: Optional[str] = None,
              latest_bar: Optional[str] = None,
              now: Optional[datetime] = None,
              dry_run: bool = False,
              env: Optional[dict] = None,
              enforce_window: bool = False,
              sleep: Callable[[float], None] = time.sleep) -> CycleResult:
    """Run one complete cycle. The order of the guards below is the design.

    1. **Trading mode** — before anything else. An unsupported mode stops the
       run rather than being coerced to something safe-looking.
    2. **Schedule window** (optional) — cheap, and checked BEFORE the lock so a
       mistimed fire costs nothing and cannot block a correctly-timed one.
    3. **Duplicate identity** — checked before the lock for the same reason.
    4. **Lock** — the concurrency guard.
    5. **Duplicate re-check under the lock** — the classic race: two processes
       both pass step 3, then serialise on the lock. Without this re-read the
       second one runs a full duplicate cycle.
    6. **Market session** — decides whether statistics may advance.
    """
    now = now or S.now_local()
    day = (as_of or now.date().isoformat())[:10]
    rid = run_id(day, cycle)
    started = _now_utc()
    store = RunStore(root)

    def finish(status: str, reason: str = "", session=None,
               steps_run: Sequence[Step] = (), mode: str = "",
               reports: Optional[dict] = None) -> CycleResult:
        result = CycleResult(
            run_id=rid, cycle=cycle, as_of=day, timezone=S.TIMEZONE,
            status=status, reason=reason,
            session=(session.as_dict() if session else {}),
            steps=tuple(steps_run), started_at=started, finished_at=_now_utc(),
            trading_mode=mode, dry_run=dry_run,
            report_paths=reports or {})
        store.append(result)
        return result

    # 1. PAPER ONLY. Raises on anything unsupported; recorded as FAILED with a
    #    configuration code, never silently downgraded.
    try:
        mode = assert_paper_only(env)
    except Exception as exc:  # noqa: BLE001
        return finish(FAILED, f"{F.CONFIGURATION_FAILURE}: {exc}")

    # 2. DST / mistimed-fire guard.
    if enforce_window:
        hour, minute = SCHEDULE[cycle]
        if not S.within_window(now, hour, minute):
            return finish(
                SKIPPED_DUPLICATE,
                f"fired at {now.strftime('%H:%M %Z')}, outside the "
                f"{hour:02d}:{minute:02d} {S.TIMEZONE} window — not running",
                mode=mode)

    # 3. Durable duplicate check.
    if store.completed(rid):
        return finish(SKIPPED_DUPLICATE,
                      f"{rid} already completed", mode=mode)

    try:
        with JobLock(LOCK_NAME, root=root):
            # 5. Re-check under the lock: two processes can both pass (3).
            if store.completed(rid):
                return finish(SKIPPED_DUPLICATE,
                              f"{rid} completed while waiting for the lock",
                              mode=mode)

            previous_bar = store.last_ingested_bar()
            session = S.classify(
                datetime.strptime(day, "%Y-%m-%d").date(),
                latest_bar=latest_bar, hour=now.hour,
                previous_cycle_bar=previous_bar)

            ctx = CycleContext(cycle=cycle, as_of=day, root=pathlib.Path(root),
                               session=session, run_id=rid, dry_run=dry_run)
            ran: List[Step] = []
            for name, fn in steps:
                ran.append(run_step(name, fn, ctx, sleep=sleep))

            reports = ctx.results.get("report", {}) or {}
            failed = [s for s in ran if s.status == "failed"]
            integrity = [s for s in failed
                         if s.code == F.INTEGRITY_VIOLATION]
            if integrity:
                # An integrity violation is never a partial success. Every
                # measurement in the run is suspect once a guarantee is broken.
                return finish(FAILED,
                              f"{F.INTEGRITY_VIOLATION}: "
                              f"{integrity[0].error}", session, ran, mode,
                              reports)
            if failed and len(failed) == len(ran):
                return finish(FAILED, f"all {len(ran)} steps failed",
                              session, ran, mode, reports)
            if failed:
                names = ", ".join(s.name for s in failed)
                return finish(PARTIAL, f"failed steps: {names}",
                              session, ran, mode, reports)
            if not session.has_new_market_observation:
                # COMPLETED work, explicitly NOT a new market observation. The
                # research ran; the statistics did not advance. Both facts are
                # true and both are recorded.
                return finish(SKIPPED_NO_NEW_MARKET_SESSION, session.reason,
                              session, ran, mode, reports)
            return finish(COMPLETED, session.reason, session, ran, mode,
                          reports)
    except JobLockedError:
        return finish(SKIPPED_DUPLICATE,
                      "another cycle holds the lock", mode=mode)
    except Exception as exc:  # noqa: BLE001 - never lose a failure
        return finish(FAILED, f"{F.classify(exc)}: {type(exc).__name__}: {exc}",
                      mode=mode)


# ---------------------------------------------------------------------------
# REPORTS — human and machine, per cycle, never overwritten.
# ---------------------------------------------------------------------------

def write_reports(root, *, run_id_: str, cycle: str, as_of: str,
                  markdown: str, payload: dict) -> dict:
    """Write both report forms and update the latest-pointer.

    An existing file for the same identity is ARCHIVED, not replaced. A rerun
    is a legitimate thing to do (a partial cycle retried, a fixed source) and
    the earlier attempt is evidence about the failure -- deleting it would
    destroy the only record of what the system saw when it went wrong.

    The pointer is a small file naming the current report. It is not a copy, so
    updating it cannot lose a report, and it is not a symlink, so it survives
    being copied between machines.
    """
    directory = pathlib.Path(root) / REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{as_of[:10]}_{cycle}"
    written = {}
    for suffix, content in ((".md", markdown),
                            (".json", json.dumps(payload, indent=1,
                                                 sort_keys=True,
                                                 default=str))):
        target = directory / f"{stem}{suffix}"
        if target.exists():
            n = 1
            while (directory / f"{stem}.{n}{suffix}").exists():
                n += 1
            os.replace(target, directory / f"{stem}.{n}{suffix}")
        target.write_text(content, encoding="utf-8")
        written[suffix.lstrip(".")] = str(target)
    pointer = directory / f"latest_{cycle}.json"
    tmp = pointer.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"run_id": run_id_, "as_of": as_of,
                               "cycle": cycle, "written_at": _now_utc(),
                               **written}, indent=1, sort_keys=True))
    os.replace(tmp, pointer)
    written["pointer"] = str(pointer)
    return written


def latest_report(root, cycle: str) -> Optional[dict]:
    pointer = pathlib.Path(root) / REPORT_DIR / f"latest_{cycle}.json"
    if not pointer.exists():
        return None
    try:
        return json.loads(pointer.read_text())
    except (json.JSONDecodeError, OSError):  # pragma: no cover
        return None

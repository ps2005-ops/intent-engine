"""Operational health — one command that says whether the engine is alive.

WHY A SEPARATE SURFACE
----------------------
The operating report answers "what did the engine learn?". This answers "is the
engine running at all?", and they fail independently in a way that is easy to
miss: a system whose night cycle stopped firing three weeks ago still has a
perfectly good report from three weeks ago sitting in `reports/`. The most
dangerous unattended failure is the silent one, so freshness is a first-class
measurement here rather than something a reader is expected to infer from a
date in a filename.

WHAT "MISSED" MEANS
-------------------
A run is missed when its scheduled time has passed by more than the grace
window and no record for that operating day exists. Computed from the run
store, not from launchd -- launchd can report a job as loaded and happy while
the job itself exits instantly every time.

EVERY FIELD DEGRADES, NOTHING RAISES
------------------------------------
A health check that crashes is worse than useless: it is the one thing that
must still work when everything else is broken. Every probe here is wrapped,
and an unavailable probe reports `None` with a reason rather than taking the
command down with it.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from intent_engine.market import cycle as C
from intent_engine.market import session as S
from intent_engine.market.trading_mode import ENV_VAR, PAPER, resolve

# launchd labels. Repository-owned so install/uninstall/status all agree.
LABEL_DAY = "com.intentengine.market.day"
LABEL_NIGHT = "com.intentengine.market.night"
LABEL_HEALTH = "com.intentengine.market.health"
LABELS = {C.DAY: LABEL_DAY, C.NIGHT: LABEL_NIGHT}

# How late a scheduled run may be before it counts as missed. Generous: a slow
# research sweep has taken over nine minutes, and a laptop asleep at 06:30 runs
# the job when it wakes. Flagging that as an outage would train the reader to
# ignore the field.
GRACE_HOURS = 6

OK, DEGRADED, DOWN, UNKNOWN = "OK", "DEGRADED", "DOWN", "UNKNOWN"


def _run(args: List[str], cwd=None, timeout: float = 10.0) -> Optional[str]:
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                             timeout=timeout, check=False)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def launchd_state(label: str) -> dict:
    """Installed (a plist exists) and loaded (launchd knows it) are DIFFERENT.

    Conflating them is the specific mistake that lets someone believe a
    template is a running service. A plist on disk that was never loaded
    schedules nothing.
    """
    plist = (pathlib.Path.home() / "Library" / "LaunchAgents"
             / f"{label}.plist")
    listing = _run(["launchctl", "list"])
    loaded = bool(listing and any(line.endswith(label) or f"\t{label}" in line
                                  for line in listing.splitlines()))
    return {"label": label, "installed": plist.exists(),
            "plist": str(plist), "loaded": loaded}


INSTALL_MARKER = "status/scheduler_installed.json"


def installed_at(root) -> Optional[str]:
    """When the scheduler was installed, if it ever was.

    Written by `ops/install_autonomous.sh`. Read rather than inferred from
    plist mtimes, which change on every reinstall and would silently reset the
    missed-run window.
    """
    path = pathlib.Path(root) / INSTALL_MARKER
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("installed_at")
    except (json.JSONDecodeError, OSError):  # pragma: no cover
        return None


def next_expected(cycle: str, now: Optional[datetime] = None) -> str:
    now = now or S.now_local()
    hour, minute = C.SCHEDULE[cycle]
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return target.isoformat(timespec="seconds")


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def missed_runs(store: C.RunStore, cycle: str,
                now: Optional[datetime] = None, days: int = 7) -> List[str]:
    """Operating days in the recent window with no record for this cycle.

    Today is excluded until its scheduled time plus grace has passed --
    otherwise every morning would report the night cycle as missed.
    """
    now = now or S.now_local()
    rows = store.all()
    # An engine that has NEVER run has not "missed" anything -- missing a run
    # presupposes it was supposed to be running. Reporting six missed days on
    # a fresh install is noise, and noise in a health check trains the reader
    # to stop looking at it.
    if not rows:
        return []
    seen = {r.get("as_of") for r in rows if r.get("cycle") == cycle}
    # Nor can a cycle be "missed" on a day BEFORE the engine ever ran. The
    # window starts at the first recorded run: reporting six missed nights
    # from before installation is noise, and noise here trains the reader to
    # stop reading the field that is supposed to catch a real outage.
    first = min((r.get("as_of") for r in rows if r.get("as_of")), default=None)
    # Nor before the SCHEDULER was installed. A slot that passed while nothing
    # was scheduled was never going to fire, and it can never be filled -- so
    # reporting it as missed means the supervisor cries wolf every hour for a
    # week over a gap no action can close. Same reasoning as the first-run
    # clamp above: a health check that is always red is a health check nobody
    # reads.
    installed = installed_at(store.root)
    if installed:
        first = max(first, installed[:10]) if first else installed[:10]
    hour, minute = C.SCHEDULE[cycle]
    out = []
    for back in range(days):
        day = (now - timedelta(days=back)).date()
        if first and day.isoformat() < first:
            continue
        due = now.replace(year=day.year, month=day.month, day=day.day,
                          hour=hour, minute=minute, second=0, microsecond=0)
        if (now - due).total_seconds() < GRACE_HOURS * 3600:
            continue
        if day.isoformat() not in seen:
            out.append(day.isoformat())
    return sorted(out)


def storage_health(root) -> dict:
    """Is the runtime root actually writable? Probed by writing.

    An unattended cycle that cannot write is a cycle whose every result is
    lost, and a permissions check that only reads the mode bits does not catch
    a full disk or a read-only mount.
    """
    root = pathlib.Path(root)
    probe = root / "status" / ".write_probe"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(str(datetime.now(timezone.utc)))
        probe.unlink()
        return {"writable": True, "root": str(root), "error": None}
    except OSError as exc:
        return {"writable": False, "root": str(root),
                "error": f"{type(exc).__name__}: {exc}"}


def source_reliability(store: C.RunStore, window: int = 14) -> dict:
    """Per-step success rate across recent runs.

    A step that has degraded from 100% to 60% is the earliest warning an
    unattended system gives, and it appears here before it shows up as a dip
    in any research metric.
    """
    rows = store.all()[-window:]
    totals: Dict[str, List[int]] = {}
    for row in rows:
        for step in row.get("steps") or ():
            name = step.get("name", "")
            bucket = totals.setdefault(name, [0, 0])
            bucket[1] += 1
            if step.get("status") == "ok":
                bucket[0] += 1
    return {name: {"ok": ok, "of": total,
                   "rate": round(ok / total, 3) if total else None}
            for name, (ok, total) in sorted(totals.items())}


def git_state(repo) -> dict:
    repo = str(repo)
    commit = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    porcelain = _run(["git", "status", "--porcelain"], cwd=repo)
    return {"commit": commit, "branch": branch,
            "clean": (porcelain == "") if porcelain is not None else None,
            "dirty_files": (len(porcelain.splitlines())
                            if porcelain else 0)}


@dataclass(frozen=True)
class Health:
    at: str
    root: str
    overall: str
    trading_mode: dict
    lock: dict
    cycles: dict
    scheduler: dict
    storage: dict
    sources: dict
    git: dict
    reports: dict
    latest_error: Optional[str]
    notes: tuple = ()

    def as_dict(self) -> dict:
        return {"at": self.at, "root": self.root, "overall": self.overall,
                "trading_mode": self.trading_mode, "lock": self.lock,
                "cycles": self.cycles, "scheduler": self.scheduler,
                "storage": self.storage, "sources": self.sources,
                "git": self.git, "reports": self.reports,
                "latest_error": self.latest_error, "notes": list(self.notes)}


def check(root, *, repo=None, now: Optional[datetime] = None,
          env: Optional[dict] = None) -> Health:
    now = now or S.now_local()
    root = pathlib.Path(root)
    store = C.RunStore(root)
    notes: List[str] = []

    try:
        mode = resolve(env)
        mode_ok = mode["mode"] == PAPER
    except Exception as exc:  # noqa: BLE001
        mode = {"mode": None, "source": "invalid", "error": str(exc)}
        mode_ok = False
        notes.append(f"{ENV_VAR} is misconfigured — cycles will refuse to run")

    cycles = {}
    for cycle in C.CYCLES:
        last = store.latest(cycle)
        completed = [r for r in store.all()
                     if r.get("cycle") == cycle
                     and r.get("status") in (C.COMPLETED,
                                             C.SKIPPED_NO_NEW_MARKET_SESSION)]
        missed = missed_runs(store, cycle, now)
        cycles[cycle] = {
            "last_run": (last or {}).get("started_at"),
            "last_status": (last or {}).get("status"),
            "last_as_of": (last or {}).get("as_of"),
            "last_success": (completed[-1].get("finished_at")
                             if completed else None),
            "next_expected": next_expected(cycle, now),
            "missed_recent": missed,
            "runs_recorded": sum(1 for r in store.all()
                                 if r.get("cycle") == cycle),
        }
        if missed:
            notes.append(f"{cycle} cycle missed {len(missed)} scheduled "
                         f"run(s): {', '.join(missed)}")

    lock = C.lock_state(root)
    if lock["stale"]:
        notes.append(f"a cycle lock has been held for "
                     f"{lock['age_seconds']}s — investigate before rerunning")

    scheduler = {name: launchd_state(label) for name, label in LABELS.items()}
    installed = all(s["installed"] for s in scheduler.values())
    loaded = all(s["loaded"] for s in scheduler.values())
    if not installed:
        notes.append("launchd jobs are NOT installed — the engine will not "
                     "run unattended (see docs/AUTONOMOUS_OPERATION.md)")
    elif not loaded:
        notes.append("launchd plists exist but are not loaded — nothing is "
                     "scheduled")

    storage = storage_health(root)
    if not storage["writable"]:
        notes.append(f"runtime root is NOT writable: {storage['error']}")

    reports = {c: C.latest_report(root, c) for c in C.CYCLES}
    latest_error = None
    for row in reversed(store.all()):
        if row.get("status") in (C.FAILED, C.PARTIAL):
            latest_error = f"{row.get('run_id')}: {row.get('reason')}"
            break

    # Overall. DOWN is reserved for conditions under which the engine CANNOT
    # operate; a missed run or an uninstalled scheduler is DEGRADED, because
    # the engine still runs correctly when it is invoked.
    never_run = not store.all()
    if never_run:
        # Stated regardless of what else is wrong. It is the first thing a
        # reader needs, and it changes how every other field should be read.
        notes.insert(0, "no cycle has run yet")
    if not mode_ok or not storage["writable"]:
        overall = DOWN
    elif never_run:
        overall = UNKNOWN
    elif notes:
        overall = DEGRADED
    else:
        overall = OK

    return Health(
        at=now.isoformat(timespec="seconds"), root=str(root), overall=overall,
        trading_mode={**mode, "enforced": mode_ok, "env_var": ENV_VAR},
        lock=lock, cycles=cycles,
        scheduler={"installed": installed, "loaded": loaded, **scheduler},
        storage=storage, sources=source_reliability(store),
        git=git_state(repo or pathlib.Path(__file__).resolve().parents[3]),
        reports=reports, latest_error=latest_error, notes=tuple(notes))


def render(health: Health) -> str:
    """The concise human status. Ordered by what a person actually asks:
    is it up, is it scheduled, did it run, is anything broken."""
    mark = {OK: "OK", DEGRADED: "DEGRADED", DOWN: "DOWN",
            UNKNOWN: "UNKNOWN"}[health.overall]
    lines = [
        f"INTENT ENGINE — MARKET OPERATING HEALTH        {mark}",
        f"checked      {health.at}  ({S.TIMEZONE})",
        f"root         {health.root}",
        "",
        f"trading mode {health.trading_mode.get('mode')} "
        f"({health.trading_mode.get('source')}) — "
        f"{'enforced' if health.trading_mode.get('enforced') else 'NOT ENFORCED'}",
        f"storage      {'writable' if health.storage['writable'] else 'NOT WRITABLE'}",
        f"lock         {'HELD' if health.lock['held'] else 'free'}"
        + (f"  age {health.lock['age_seconds']}s"
           if health.lock.get("age_seconds") is not None else ""),
        "",
        f"scheduler    installed={health.scheduler['installed']}  "
        f"loaded={health.scheduler['loaded']}",
    ]
    for cycle in C.CYCLES:
        info = health.cycles[cycle]
        lines.append(
            f"  {cycle:<6} last {info['last_status'] or '—'} "
            f"@ {info['last_as_of'] or '—'}   next {info['next_expected']}"
            + (f"   MISSED {len(info['missed_recent'])}"
               if info["missed_recent"] else ""))
    if health.sources:
        lines.append("")
        lines.append("step reliability (last 14 runs)")
        for name, stat in health.sources.items():
            rate = "—" if stat["rate"] is None else f"{stat['rate']:.0%}"
            lines.append(f"  {name:<22}{rate:>6}  ({stat['ok']}/{stat['of']})")
    git = health.git
    lines += ["", f"git          {(git.get('commit') or '—')[:12]} on "
                  f"{git.get('branch') or '—'}  "
                  f"{'clean' if git.get('clean') else 'dirty'}"]
    if health.latest_error:
        lines += ["", f"latest error {health.latest_error}"]
    if health.notes:
        lines.append("")
        for note in health.notes:
            lines.append(f"  ! {note}")
    return "\n".join(lines)

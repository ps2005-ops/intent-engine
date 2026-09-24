#!/usr/bin/env python3
"""ONE WRITER for the qualification state (§5).

WHY THIS EXISTS. Two live sessions wrote reports/next40_state.json during
cohort A and spent the same ten-analyses-per-hour demo quota. The collision
was benign that time -- both were running the same cohort and the second write
happened to be a re-run that improved a row -- but it was benign by luck. Two
writers racing and reconciling by timestamp afterwards is not a qualification;
the row that survives is the one that happened to be written last.

So ownership is CLAIMED, not assumed. A claim carries the owning session, the
process that made it, and a heartbeat. A second writer refuses while a live
claim is held, and takes over a stale one -- because a dead owner's lock must
never be able to stop the qualification finishing.

REFUSING IS THE POINT. A lock that logs a warning and proceeds is a comment.
"""
from __future__ import annotations

import json
import os
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCK = ROOT / "reports/next40_owner.json"

#: A claim older than this with no heartbeat is abandoned. Long enough to
#: cover the longest quota wait the runner takes (61 minutes) plus a paid
#: analysis, so a legitimately waiting owner is never evicted.
STALE_AFTER_S = 75 * 60


def _alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read() -> dict:
    try:
        return json.loads(LOCK.read_text())
    except Exception:                                        # noqa: BLE001
        return {}


def claim(session: str, *, force: bool = False) -> dict:
    """Take ownership, or raise if another live owner holds it."""
    held = read()
    if held and held.get("session") and held["session"] != session:
        age = time.time() - float(held.get("heartbeat") or 0)
        # REFUSE UNLESS THE CLAIM IS BOTH STALE AND DEAD.
        #
        # A first version required the claiming PID to still be running, and
        # the runner is a short-lived process: it claimed, finished a cohort,
        # exited -- and the very next second another session was granted
        # ownership. A lock that releases on normal exit is a comment. What
        # a live PID adds is immediacy: an owner that is RUNNING is refused
        # even if its heartbeat happens to be old (a long paid analysis).
        if not force and (age < STALE_AFTER_S
                          or _alive(int(held.get("pid") or 0))):
            raise SystemExit(
                f"REFUSED: the qualification state is owned by session "
                f"{held['session']} (pid {held.get('pid')}, last heartbeat "
                f"{age / 60:.1f} min ago). One writer only. Stop that runner, "
                f"or wait for its claim to go stale ({STALE_AFTER_S / 60:.0f} "
                f"min), or re-run with NEXT40_FORCE_OWNER=1 if you know it is "
                f"dead.")
    now = time.time()
    owner = {"contract": "next40_owner.v1", "session": session,
             "pid": os.getpid(), "claimed_at": held.get("claimed_at", now)
             if held.get("session") == session else now,
             "heartbeat": now,
             "previous_session": held.get("session") if
             held.get("session") != session else
             held.get("previous_session")}
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOCK.with_suffix(".tmp")
    tmp.write_text(json.dumps(owner, indent=1))
    tmp.replace(LOCK)
    return owner


def beat(session: str) -> None:
    """Refresh the claim. Called on every state write."""
    held = read()
    if held.get("session") != session:
        return
    held["heartbeat"] = time.time()
    try:
        tmp = LOCK.with_suffix(".tmp")
        tmp.write_text(json.dumps(held, indent=1))
        tmp.replace(LOCK)
    except Exception:                                        # noqa: BLE001
        pass


def session_id() -> str:
    """This session's identity, from the environment the harness provides."""
    for key in ("NEXT40_SESSION", "CLAUDE_SESSION_ID"):
        value = os.environ.get(key, "").strip()
        if value:
            return value[:36]
    # NO SILENT FALLBACK TO SOMETHING MEANINGLESS. A first version derived
    # the id from TMPDIR and produced the single character "T", which would
    # have made every session look like the same owner -- a lock that cannot
    # refuse. An unnamed caller gets a per-process id, which is distinct by
    # construction and therefore still enforces one writer.
    return f"unnamed-pid-{os.getpid()}"

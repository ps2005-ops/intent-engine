"""Is the runtime storage actually durable? Measured, never inferred.

WHY THIS CANNOT BE A JUDGEMENT CALL
-----------------------------------
`/readyz` reports `runtime_root: "data"`. It is tempting to read that relative
path as "no disk is mounted, therefore ephemeral" — and tempting the other way
too, because a platform that sets the working directory to the project root
would resolve `data` straight onto a mounted disk. Both readings are guesses
about someone else's deployment, and a guess is exactly what must not sit
underneath a success message telling a user their feedback was saved.

So nothing here infers durability from a path name.

THE THREE THINGS THAT CAN ACTUALLY BE MEASURED
----------------------------------------------
1. WRITABILITY. Write a file, read it back, delete it. A directory that cannot
   be written to has already settled the question.

2. DEVICE IDENTITY. `st_dev` for the runtime root versus `st_dev` for the
   filesystem root. A mounted disk is a different device; a directory inside
   the container image is the same one. This is evidence, not proof — a
   container can be laid out either way — so it is reported as what it is.

3. SURVIVAL, which is the only actual proof. Each process appends its boot id
   to a ledger inside the runtime root. Finding an earlier boot's id there
   means a previous process wrote a file, that process ended, and the file is
   still here. Nothing about mount configuration is required, and no claim is
   made that has not already been demonstrated on this exact deployment.

Until a second boot has been observed, the honest answer is UNPROVEN — not
"probably fine". UNPROVEN is why the feedback form can refuse to promise
anything rather than lying politely.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

STORAGE_PROBE_VERSION = "webapp_storage.v1"

# Durability states, from proven to disqualifying.
DURABLE_PROVEN = "DURABLE_PROVEN"
DURABLE_UNPROVEN = "DURABLE_UNPROVEN"
EPHEMERAL_LIKELY = "EPHEMERAL_LIKELY"
NOT_WRITABLE = "NOT_WRITABLE"

_BOOT_LEDGER = ".boot_ledger.jsonl"
# This process. Regenerated on import, which is precisely the point: a new
# value means a new process.
BOOT_ID = uuid.uuid4().hex[:16]


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def record_boot(runtime_root, *, boot_id: str = "", now=None) -> dict:
    """Append this process's boot id to the ledger and read back the history.

    Called once at startup. Idempotent per boot id, so a double call inside one
    process does not manufacture a second boot and turn UNPROVEN into PROVEN by
    accident — which would be the worst possible bug in this file.
    """
    root = Path(runtime_root)
    boot_id = boot_id or BOOT_ID
    ledger = root / _BOOT_LEDGER
    previous = read_boots(root)
    if boot_id not in {b.get("boot_id") for b in previous}:
        try:
            root.mkdir(parents=True, exist_ok=True)
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "boot_id": boot_id,
                    "at": now or _now(),
                    "pid": os.getpid(),
                    "probe_version": STORAGE_PROBE_VERSION}) + "\n")
        except OSError:
            return {"boots": previous, "recorded": False}
    return {"boots": read_boots(root), "recorded": True}


def read_boots(runtime_root) -> list:
    ledger = Path(runtime_root) / _BOOT_LEDGER
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue            # a torn line is not a reason to fail a probe
    return out


def _writable(root: Path) -> tuple:
    probe = root / f".storage_probe_{uuid.uuid4().hex[:8]}"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        readback = probe.read_text(encoding="utf-8") == "ok"
        probe.unlink()
        return (readback, "")
    except OSError as exc:
        try:
            probe.unlink()
        except OSError:
            pass
        return (False, type(exc).__name__)


def _device_evidence(root: Path) -> dict:
    """Whether the runtime root sits on its own filesystem."""
    try:
        root_dev = os.stat(root).st_dev
        fs_root_dev = os.stat(os.sep).st_dev
        return {"separate_filesystem": root_dev != fs_root_dev,
                "device_known": True}
    except OSError:
        return {"separate_filesystem": None, "device_known": False}


def _free_bytes(root: Path):
    try:
        usage = os.statvfs(root)
        return usage.f_bavail * usage.f_frsize
    except (OSError, AttributeError):
        return None


def probe_storage(runtime_root, *, boot_id: str = "") -> dict:
    """The full measured picture. Never raises."""
    root = Path(runtime_root)
    writable, write_error = _writable(root)
    device = _device_evidence(root)
    boots = read_boots(root) if writable else []
    distinct = {b.get("boot_id") for b in boots if b.get("boot_id")}
    current = boot_id or BOOT_ID
    earlier = distinct - {current}

    if not writable:
        state = NOT_WRITABLE
    elif earlier:
        # A previous process wrote here, ended, and its record is still
        # present. That is survival across a restart, demonstrated.
        state = DURABLE_PROVEN
    elif device.get("separate_filesystem"):
        state = DURABLE_UNPROVEN
    elif device.get("device_known"):
        # Same filesystem as the container image. Suggestive, not conclusive —
        # so the state says "likely", and callers must not treat it as proof.
        state = EPHEMERAL_LIKELY
    else:
        state = DURABLE_UNPROVEN

    return {
        "runtime_root": str(root),
        "absolute_path": str(root.resolve()) if root.exists() else str(root),
        "is_absolute": root.is_absolute(),
        "writable": writable,
        "write_error": write_error,
        "separate_filesystem": device.get("separate_filesystem"),
        "device_known": device.get("device_known"),
        "free_bytes": _free_bytes(root),
        "boot_count": len(distinct),
        "earlier_boots_observed": len(earlier),
        "current_boot_id": current,
        "durability": state,
        "durable": state == DURABLE_PROVEN,
        "probe_version": STORAGE_PROBE_VERSION,
    }


_EXPLANATION = {
    DURABLE_PROVEN: "Storage has been observed to survive a restart on this "
                    "deployment: a record written by an earlier process is "
                    "still present.",
    DURABLE_UNPROVEN: "Storage is writable and appears to be on its own "
                      "filesystem, but this process has not yet observed a "
                      "restart, so survival has not been demonstrated.",
    EPHEMERAL_LIKELY: "Storage is writable but sits on the same filesystem as "
                      "the application image, which is usually replaced on "
                      "redeploy. Survival has not been demonstrated.",
    NOT_WRITABLE: "Storage cannot be written to at all.",
}


def explain_storage(probe: dict) -> str:
    return _EXPLANATION.get(probe.get("durability"), "Storage state unknown.")


def may_promise_persistence(probe: dict) -> bool:
    """Whether the product is entitled to tell a user something was saved.

    Only DURABLE_PROVEN qualifies. UNPROVEN is deliberately not enough: the
    whole failure being fixed here is a success page asserting a fact nobody
    had checked.
    """
    return probe.get("durability") == DURABLE_PROVEN


# --- process identity -------------------------------------------------------
#
# WHY THIS IS NOT `boot_count`.
#
# `boot_count` reads a ledger INSIDE the runtime root. On an ephemeral
# filesystem the ledger dies with the process that wrote it, so the count is
# 1 on every boot and can never rise. It is a durability proof, and it is the
# WRONG instrument for the question "did this service restart while I was
# using it?" -- the very case it cannot report is the case that matters.
#
# A restart is observable from OUTSIDE with no storage at all: this process's
# BOOT_ID is generated at import and never changes, and its start time is
# monotonic within the process. A client that sees the pair change between two
# requests has watched a restart, with no guessing about mounts.
#
# Measured need: two live canary runs disappeared between the customer steps
# and the Q&A step, and the session that lost them had no way to tell a
# restart from an application bug. This is that way.
_PROCESS_STARTED = None


def process_identity(now=None) -> dict:
    """Who this process is and how long it has been running.

    Cheap, allocation-free in the steady state and safe on any host: nothing
    here touches the filesystem, so it reports honestly even when the runtime
    root is unwritable.
    """
    import time as _time
    global _PROCESS_STARTED
    if _PROCESS_STARTED is None:
        _PROCESS_STARTED = _time.time()
    moment = _time.time() if now is None else now
    return {"boot_id": BOOT_ID,
            "started_at": _PROCESS_STARTED,
            "uptime_seconds": round(max(0.0, moment - _PROCESS_STARTED), 1)}


def persistent_mount_candidates(paths=None) -> list:
    """Whether a persistent disk exists on this host, MEASURED not assumed.

    `/readyz` reports `durability: EPHEMERAL_LIKELY` and names the fix -- mount
    the disk and point RUNTIME_ROOT at it -- but from inside the application
    there was no way to tell "no disk is attached" from "a disk is attached
    and RUNTIME_ROOT was never set to it". Those have very different fixes and
    only one of them is a one-line dashboard change.

    This only LOOKS. It never changes the runtime root: a directory that
    happens to exist is not evidence that this service's data belongs in it,
    and silently relocating a store is how one deployment starts serving
    another's state.
    """
    candidates = paths or ("/var/data", "/data", "/mnt/data",
                           "/opt/render/project/data")
    try:
        root_dev = os.stat("/").st_dev
    except OSError:
        root_dev = None
    out = []
    for raw in candidates:
        path = Path(raw)
        entry = {"path": str(path), "exists": False, "writable": False,
                 "separate_filesystem": False}
        try:
            if path.is_dir():
                entry["exists"] = True
                entry["separate_filesystem"] = (
                    root_dev is not None and path.stat().st_dev != root_dev)
                probe = path / f".probe-{BOOT_ID}"
                try:
                    probe.write_text("probe", "utf-8")
                    entry["writable"] = probe.read_text("utf-8") == "probe"
                finally:
                    try:
                        probe.unlink()
                    except OSError:
                        pass
        except OSError:
            pass
        out.append(entry)
    return out

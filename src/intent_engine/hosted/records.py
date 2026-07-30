"""Durable scheduler-execution + failure records (sections 2 & 3).

Every hosted job runs through `run_job`, which persists a start/finish record to
the durable store — NOT to a runner's ephemeral disk — so the (possibly slept)
Render web service can show scheduler health, missed runs, and failures. Errors
are redacted before persistence (a fetcher exception can embed a credential in a
URL). Records are idempotent on a run id, so a re-fired workflow does not create
phantom duplicate runs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from intent_engine.core.decision_ids import new_ulid
from intent_engine.runtime.redaction import redact_secrets

EXEC_STREAM = "scheduler_execution"
FAILURE_STREAM = "job_failure"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_job(store, name: str, work: Callable[[], dict], *, as_of: str,
            run_id: Optional[str] = None) -> Dict:
    """Run a job, persisting a durable execution record. Returns the record.

    Each invocation gets a UNIQUE run_id (ULID) — so a job fired twice for the
    same day (a double-fired workflow, a manual re-run in the same second) is
    recorded as two distinct executions rather than colliding on the durable
    idem key. Work-level idempotency (orders, resolutions) is enforced
    separately by deterministic keys, so the double run still does no double
    work; it is just observed twice, which is what scheduler health wants."""
    run_id = run_id or f"{name}:{as_of}:{new_ulid()}"
    started = _now()
    store.append(EXEC_STREAM, run_id,
                 {"job": name, "as_of": as_of, "status": "started",
                  "started_at": started},
                 status="started", ref_id=name,
                 idem_key=f"exec-start:{run_id}")
    try:
        detail = work() or {}
        record = {"job": name, "as_of": as_of, "status": "succeeded",
                  "started_at": started, "finished_at": _now(),
                  "detail": detail, "run_id": run_id}
        store.append(EXEC_STREAM, run_id, record, status="succeeded",
                     ref_id=name, idem_key=f"exec-done:{run_id}")
        return record
    except Exception as exc:  # noqa: BLE001 - persist EVERY failure, redacted
        err = redact_secrets(f"{type(exc).__name__}: {exc}")
        record = {"job": name, "as_of": as_of, "status": "failed",
                  "started_at": started, "finished_at": _now(),
                  "error": err, "run_id": run_id}
        store.append(EXEC_STREAM, run_id, record, status="failed", ref_id=name,
                     idem_key=f"exec-done:{run_id}")
        store.append(FAILURE_STREAM, run_id,
                     {"job": name, "as_of": as_of, "error": err, "at": _now()},
                     status="failed", ref_id=name,
                     idem_key=f"fail:{run_id}")
        return record


def latest_executions(store) -> Dict[str, dict]:
    """Most recent execution per job (for the scheduler-health dashboard)."""
    latest: Dict[str, dict] = {}
    for r in store.read(EXEC_STREAM):
        p = r.payload
        job = p.get("job")
        if job and (job not in latest
                    or p.get("finished_at", p.get("started_at", ""))
                    >= latest[job].get("finished_at",
                                       latest[job].get("started_at", ""))):
            latest[job] = p
    return latest


def recent_failures(store, limit: int = 20) -> List[dict]:
    rows = [r.payload for r in store.read(FAILURE_STREAM)]
    return rows[-limit:][::-1]

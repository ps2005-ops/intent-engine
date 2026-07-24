"""Scheduled job entrypoints — locked, evented, idempotent, restart-safe.

Every scheduled job runs through `run_job`, which:
  - takes the single-execution JobLock (no duplicate concurrent runs);
  - publishes job.started / job.succeeded / job.failed (job.failed is a
    PERSISTENT failure record — nothing swallows a scheduled error);
  - writes an append-only status line + a latest-status file (observability);
  - retries a transient failure a bounded number of times.

The underlying work is itself idempotent (the market runtime only touches
unresolved/undue records; the learning ledger de-dupes candidates), so a
re-run after a crash is safe — the "restart-safe" property.

Credential-dependent jobs (open positions, resolve) preflight their required
keys and FAIL LOUDLY (persistent job.failed + config.preflight_failed) when
a key is missing — never a silent empty day.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from intent_engine.events import CompanyEventBus
from intent_engine.runtime.config_health import missing_required, preflight
from intent_engine.runtime.locks import JobLock, JobLockedError
from intent_engine.runtime.redaction import redact_secrets


@dataclass
class JobResult:
    name: str
    status: str          # succeeded | failed | locked
    detail: Optional[dict] = None
    error: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_status(root: Path, result: JobResult) -> None:
    root = Path(root)
    (root / "status").mkdir(parents=True, exist_ok=True)
    row = {"at": _now(), "job": result.name, "status": result.status,
           "error": result.error, "detail": result.detail}
    with open(root / "status" / "jobs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    (root / "status" / f"{result.name}.json").write_text(
        json.dumps(row, indent=2, sort_keys=True, default=str))


def run_job(name: str, work: Callable[[], dict], *, root, bus=None,
            retries: int = 1) -> JobResult:
    root = Path(root)
    try:
        lock = JobLock(name, root=root)
    except Exception as exc:  # pragma: no cover - mkdir failure
        result = JobResult(name, "failed", error=str(exc))
        _write_status(root, result)
        return result

    try:
        with lock:
            if bus is not None:
                bus.publish("job.started", subject_type="job", subject_id=name,
                            producer="scheduler", actor_type="system",
                            actor_id="scheduler", source="system",
                            payload={"job": name},
                            idempotency_key=f"job_start:{name}:{_now()}")
            last_error = None
            for attempt in range(retries + 1):
                try:
                    detail = work()
                    result = JobResult(name, "succeeded", detail=detail)
                    _write_status(root, result)
                    if bus is not None:
                        bus.publish("job.succeeded", subject_type="job",
                                    subject_id=name, producer="scheduler",
                                    actor_type="system", actor_id="scheduler",
                                    source="system",
                                    payload={"job": name, "attempt": attempt})
                    return result
                except Exception as exc:  # noqa: BLE001 - persist EVERY failure
                    # redact before ANYTHING persists it (event log, status
                    # file, dashboard) — a fetcher exception can embed a
                    # credential from a request URL.
                    last_error = redact_secrets(f"{type(exc).__name__}: {exc}")
            result = JobResult(name, "failed", error=last_error)
            _write_status(root, result)
            if bus is not None:
                bus.publish("job.failed", subject_type="job", subject_id=name,
                            producer="scheduler", actor_type="system",
                            actor_id="scheduler", source="system",
                            payload={"job": name, "error": last_error,
                                     "attempts": retries + 1})
            return result
    except JobLockedError:
        result = JobResult(name, "locked",
                           error="another run holds the job lock")
        _write_status(root, result)
        return result


def require_config(root: Path, bus, job_name: str, required_vars) -> None:
    """Preflight; raise if a required var is missing so run_job records a
    persistent job.failed. Also emits config.preflight_failed."""
    snapshot = preflight(bus=bus, root=root)
    missing = [v for v in missing_required(snapshot["report"]) if v in required_vars]
    if missing:
        raise RuntimeError(
            f"{job_name} requires configured credentials, missing: {missing}")


def latest_status(root) -> dict:
    """The most recent status of each job — for the health/dashboard surface."""
    root = Path(root)
    d = root / "status"
    if not d.exists():
        return {}
    out = {}
    for f in d.glob("*.json"):
        try:
            out[f.stem] = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
    return out

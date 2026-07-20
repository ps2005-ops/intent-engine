"""Company-event consumer health (T015) — read-only views over the T013
store: log, checkpoints, retry state, dead letters. Reading NEVER
modifies checkpoints; a consumer with no checkpoint is NEVER STARTED,
not healthy; zero dead letters proves delivery, not downstream
correctness (and the annotation says so).
"""
from __future__ import annotations

import json

from intent_engine.analytics.models import (
    METRIC_VERSIONS, MetricResult, Window, utc_now_iso,
)

_VERSION = METRIC_VERSIONS["consumer_health"]


def consumer_health(event_store, window: Window, as_of: str,
                    consumer_names=None) -> dict:
    computed_at = utc_now_iso()
    events = event_store.read_all()          # raises loudly on corruption
    checkpoints = event_store.read_checkpoints()
    dead_letters = event_store.read_dead_letters()
    retry_path = event_store.dir / "retries.json"
    retries = (json.loads(retry_path.read_text())
               if retry_path.exists() else {})
    window_dict = {"start": window.start, "end": window.end}
    total = len(events)
    provenance = {"source": "events.jsonl + checkpoints.json + retries.json "
                            "+ dead_letter.jsonl (all read-only)",
                  "high_watermark": {"event_log_offset": total}}

    names = sorted(set(list(checkpoints) + list(retries)
                       + [d["consumer_name"] for d in dead_letters]
                       + list(consumer_names or [])))
    per_consumer = {}
    for name in names:
        cp = checkpoints.get(name)
        dls = [d for d in dead_letters if d["consumer_name"] == name]
        pending = [d for d in dls if d.get("redrive_status") == "pending"]
        redriven = [d for d in dls if d.get("redrive_status") == "succeeded"]
        entry = {
            "checkpoint_offset": cp["offset"] if cp else None,
            "checkpoint_updated_at": cp["updated_at"] if cp else None,
            "lag_events": (total - cp["offset"]) if cp else None,
            "started": cp is not None,
            "retry_backlog": len(retries.get(name, {})),
            "dead_letters_total": len([d for d in dls
                                       if "redrive_of" not in d]),
            "dead_letters_unresolved": len(pending),
            "redrive_successes": len(redriven),
        }
        if not entry["started"]:
            entry["note"] = "NEVER STARTED — no checkpoint exists; this is " \
                            "not the same as healthy"
        per_consumer[name] = entry

    results = {
        "event_count": MetricResult(
            metric_name="event_count", metric_version=_VERSION,
            computed_at=computed_at, window=window_dict, value=total,
            source_count=total,
            annotations=("total events in the append-only log",),
            provenance=provenance),
        "latest_event_at": MetricResult(
            metric_name="latest_event_at", metric_version=_VERSION,
            computed_at=computed_at, window=window_dict,
            status="OK" if events else "UNAVAILABLE",
            value=events[-1].recorded_at if events else None,
            source_count=total, annotations=(
                ("recorded_at of the newest event",) if events else
                ("empty log — unavailable, not zero activity",)),
            provenance=provenance),
        "consumers": MetricResult(
            metric_name="consumers", metric_version=_VERSION,
            computed_at=computed_at, window=window_dict,
            value=per_consumer, source_count=len(per_consumer),
            annotations=(
                "per-consumer lag/retry/dead-letter views; zero dead "
                "letters proves delivery, not downstream correctness; "
                "reading modifies nothing",),
            provenance=provenance),
    }
    return results

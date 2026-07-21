"""Reproducible experiment snapshots (T018, improvement 9).

A snapshot freezes everything needed to reproduce a historical read
EXACTLY: the experiment version, every rule/statistic version in play,
and the source high-watermarks. A snapshot is never authoritative —
recomputation from the append-only log must reproduce it, and a test
proves that.
"""
from __future__ import annotations

from intent_engine.analytics.models import METRIC_VERSIONS
from intent_engine.growth.randomization import RANDOMIZATION_METHOD
from intent_engine.growth.records import now_iso
from intent_engine.growth.results import LABEL_RULE_VERSION
from intent_engine.growth.statistics import (
    COUNTS_STAT_VERSION, PROPORTION_STAT_VERSION,
)
from intent_engine.growth.service import REGISTRATION_RULE_VERSION

SNAPSHOT_VERSION = "growth_snapshot.v1"


def capture_snapshot(service, experiment_id: str, *, as_of: str,
                     actor_id: str = "founder",
                     actor_type: str = "human") -> dict:
    # A snapshot for a given as_of IS that snapshot: re-capturing returns
    # the original rather than minting a second one with a fresh
    # computed_at (which would look like conflicting content).
    key = f"snapshot:{experiment_id}:{as_of}"
    existing = service.store.find_by_idempotency_key(key)
    if existing is not None:
        return {**existing.payload, "snapshot_id": existing.subject_id}
    rows = service.store.for_experiment(experiment_id)
    state = service.get_state(experiment_id)
    result = service.get_result(experiment_id)
    snapshot = {
        "snapshot_version": SNAPSHOT_VERSION,
        "experiment_id": experiment_id,
        "namespace": service.namespace,
        "experiment_version": state.approved_version,
        "computed_at": now_iso(),
        "as_of": as_of,
        "label": result["label"],
        "modifiers": result["modifiers"],
        "reasons": result["reasons"],
        "per_arm": result["per_arm"],
        "participation_funnel": result["participation_funnel"],
        "statistic": result["statistic"],
        "stopping_rule_satisfied": state.stop_rule_satisfied,
        "interim_read_count": state.interim_read_count,
        # every version that could change a future recomputation
        "versions": {
            "label_rule_version": LABEL_RULE_VERSION,
            "registration_rule_version": REGISTRATION_RULE_VERSION,
            "randomization_method": RANDOMIZATION_METHOD,
            "counts_statistic_version": COUNTS_STAT_VERSION,
            "proportion_statistic_version": PROPORTION_STAT_VERSION,
            "analytics_metric_versions": dict(sorted(METRIC_VERSIONS.items())),
        },
        # high-watermarks that pin the exact inputs
        "source_high_watermarks": {
            "growth_rows": len(rows),
            "last_growth_event_id": rows[-1].growth_event_id if rows else None,
            "observations": sum(1 for r in rows
                                if r.event_type == "growth.observation_recorded"),
            "assignments": sum(1 for r in rows
                               if r.event_type == "growth.entity_assigned"),
        },
        "reproducibility_note": (
            "this snapshot is a record, not an authority — recomputing from "
            "the append-only log at the same high-watermarks must reproduce "
            "these values exactly"),
    }
    row = service._record(
        experiment_id, "growth.snapshot_captured", actor_type=actor_type,
        actor_id=actor_id, version=state.approved_version,
        subject_type="snapshot", subject_id=service._stable_id(key),
        payload=snapshot, idempotency_key=key)
    return {**snapshot, "snapshot_id": row.subject_id}


def get_snapshot(service, experiment_id: str, snapshot_id: str) -> dict:
    for row in service.store.for_experiment(experiment_id):
        if row.event_type == "growth.snapshot_captured" \
                and row.subject_id == snapshot_id:
            return {**row.payload, "snapshot_id": snapshot_id}
    raise KeyError(f"no such snapshot: {snapshot_id}")

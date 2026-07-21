"""Frozen, reproducible snapshots (T019) — of the PACKAGE and, separately,
of the EVIDENCE GRAPH.

Snapshotting the graph as well as the package (improvement 11) is what
makes a future contradiction debuggable: you can see exactly which
relations existed, over which sources, at which versions.
"""
from __future__ import annotations

from intent_engine.research.graph import RANK_VERSION, STANCE_VERSION
from intent_engine.research.index import INDEX_VERSION
from intent_engine.research.packages import CONCLUSION_VERSION, PACKAGE_VERSION
from intent_engine.research.records import now_iso
from intent_engine.research.sources import (
    CANONICALIZATION_VERSION, FRESHNESS_VERSION, SOURCE_QUALITY_VERSION,
)

SNAPSHOT_VERSION = "research_snapshot.v1"


def _versions(service) -> dict:
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "index_version": INDEX_VERSION,
        "package_version": PACKAGE_VERSION,
        "conclusion_version": CONCLUSION_VERSION,
        "source_quality_version": SOURCE_QUALITY_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "freshness_version": FRESHNESS_VERSION,
        "stance_version": STANCE_VERSION,
        "rank_version": RANK_VERSION,
        "extraction_prompt_version": "research_extraction.v1",
        "model_version": service.model_version,
    }


def capture_package_snapshot(service, request_id: str, package_id: str, *,
                             as_of: str, actor_id="founder") -> dict:
    key = f"package-snapshot:{package_id}:{as_of}"
    existing = service.store.find_by_idempotency_key(key)
    if existing is not None:
        return {**existing.payload, "snapshot_id": existing.subject_id}

    package = service.get_package(request_id, package_id)
    index = service.get_index(request_id, as_of=as_of)
    rows = service.store.for_request(request_id)
    state = service.get_state(request_id)
    snapshot = {
        "request_id": request_id, "package_id": package_id,
        "plan_version": state.approved_plan_version,
        "computed_at": now_iso(), "as_of": as_of,
        "coverage_totals": package["coverage"]["totals"],
        "contradictions": package["contradictions"],
        "sources": package["sources"],
        "freshness": package["freshness"],
        "budget": package["budget"],
        "research_debt": package["research_debt"],
        "versions": _versions(service),
        "source_high_watermarks": {
            "research_rows": len(rows),
            "sources": len(index.sources),
            "evidence": len(index.evidence),
            "claims": len(index.claims),
            "last_event_id": rows[-1].research_event_id if rows else None,
        },
        "reproducibility_note": (
            "a snapshot is a record, not an authority — rebuilding the index "
            "from the append-only log at these watermarks must reproduce it"),
    }
    row = service._record(request_id, "research.package_snapshot",
                          actor_type="human", actor_id=actor_id,
                          version=state.approved_plan_version,
                          subject_type="snapshot",
                          subject_id=service._stable_id(key),
                          payload=snapshot, idempotency_key=key)
    return {**snapshot, "snapshot_id": row.subject_id}


def capture_graph_snapshot(service, request_id: str, *, as_of: str,
                           actor_id="founder") -> dict:
    """The graph itself, frozen — every node, edge, and the versions that
    produced them."""
    key = f"graph-snapshot:{request_id}:{as_of}"
    existing = service.store.find_by_idempotency_key(key)
    if existing is not None:
        return {**existing.payload, "snapshot_id": existing.subject_id}

    index = service.get_index(request_id, as_of=as_of)
    state = service.get_state(request_id)
    snapshot = {
        "request_id": request_id, "as_of": as_of, "computed_at": now_iso(),
        "plan_version": state.approved_plan_version,
        "nodes": {
            "sources": sorted(index.sources),
            "evidence": sorted(index.evidence),
            "claims": sorted(index.claims),
        },
        "edges": [dict(r) for r in index.relations],
        "contradictions": [dict(c) for c in index.contradictions],
        "retired": {"sources": sorted(index.retired_sources),
                    "evidence": sorted(index.retired_evidence)},
        "independence_groups": {
            s["source_id"]: s.get("independence_group")
            for s in sorted(index.sources.values(),
                            key=lambda s: s["source_id"])},
        "versions": _versions(service),
        "invariants": index.assert_invariants(),
    }
    row = service._record(request_id, "research.graph_snapshot",
                          actor_type="human", actor_id=actor_id,
                          version=state.approved_plan_version,
                          subject_type="snapshot",
                          subject_id=service._stable_id(key),
                          payload=snapshot, idempotency_key=key)
    return {**snapshot, "snapshot_id": row.subject_id}

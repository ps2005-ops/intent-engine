"""Frozen, reproducible executive snapshots (T021).

A snapshot is a record, not an authority. Recapturing the same `as_of`
returns the ORIGINAL, and recomputing from the append-only log at the
recorded watermarks reproduces it. Every version that contributed is
frozen alongside it — across all eight subsystems this layer reads — so a
figure in an old snapshot stays explainable after the rules evolve.
"""
from __future__ import annotations

from intent_engine.executive.conflicts import CONFLICT_RULE_VERSION
from intent_engine.executive.context import (
    AGING_VERSION, CONTEXT_VERSION,
)
from intent_engine.executive.debt import DEBT_VERSION
from intent_engine.executive.graph import GRAPH_VERSION
from intent_engine.executive.index import DECISION_INDEX_VERSION
from intent_engine.executive.intake import INTAKE_VERSION
from intent_engine.executive.packages import PACKAGE_VERSION
from intent_engine.executive.portfolio import (
    DASHBOARD_VERSION, PORTFOLIO_VERSION,
)
from intent_engine.executive.queue import QUEUE_ORDER_VERSION
from intent_engine.executive.readiness import READINESS_VERSIONS
from intent_engine.executive.records import (
    EXECUTIVE_SCHEMA_VERSION, ESCALATION_RULE_VERSION, IMPACT_RULE_VERSION,
    now_iso,
)
from intent_engine.executive.traceability import TRACEABILITY_VERSION

SNAPSHOT_VERSION = "executive_snapshot.v1"


def _versions(service) -> dict:
    versions = {
        "snapshot_version": SNAPSHOT_VERSION,
        "executive_schema_version": EXECUTIVE_SCHEMA_VERSION,
        "decision_index_version": DECISION_INDEX_VERSION,
        "context_version": CONTEXT_VERSION,
        "aging_version": AGING_VERSION,
        "graph_version": GRAPH_VERSION,
        "intake_version": INTAKE_VERSION,
        "conflict_version": CONFLICT_RULE_VERSION,
        "debt_version": DEBT_VERSION,
        "readiness_versions": dict(READINESS_VERSIONS),
        "impact_version": IMPACT_RULE_VERSION,
        "escalation_version": ESCALATION_RULE_VERSION,
        "package_version": PACKAGE_VERSION,
        "queue_order_version": QUEUE_ORDER_VERSION,
        "portfolio_version": PORTFOLIO_VERSION,
        "dashboard_version": DASHBOARD_VERSION,
        "traceability_version": TRACEABILITY_VERSION,
        "model_version": service.model_version,
    }
    # Versions owned by other subsystems are READ from them, so a snapshot
    # records what actually produced its inputs rather than a local copy.
    if service.product is not None:
        try:
            from intent_engine.product.index import (
                OPPORTUNITY_INDEX_VERSION, PROBLEM_INDEX_VERSION,
            )
            from intent_engine.product.scoring import SCORE_VERSIONS
            versions["product_versions"] = {
                "problem_index_version": PROBLEM_INDEX_VERSION,
                "opportunity_index_version": OPPORTUNITY_INDEX_VERSION,
                "score_versions": dict(SCORE_VERSIONS)}
        except ImportError:                                 # pragma: no cover
            pass
    if service.research is not None:
        from intent_engine.research.index import (
            INDEX_VERSION as EVIDENCE_INDEX_VERSION,
        )
        versions["research_versions"] = {
            "evidence_index_version": EVIDENCE_INDEX_VERSION}
    if service.growth is not None:
        from intent_engine.growth.results import LABEL_RULE_VERSION
        versions["growth_versions"] = {"label_rule_version": LABEL_RULE_VERSION}
    try:
        from intent_engine.analytics.models import METRIC_VERSIONS
        versions["analytics_metric_versions"] = dict(METRIC_VERSIONS)
    except ImportError:                                     # pragma: no cover
        pass
    try:
        from intent_engine.core.prediction_ledger import (
            PREDICTION_SCHEMA_VERSION,
        )
        versions["prediction_version"] = PREDICTION_SCHEMA_VERSION
    except ImportError:                                     # pragma: no cover
        versions["prediction_version"] = "prediction_ledger.v1"
    return versions


def _watermarks(service, index) -> dict:
    rows = service.store.read_all()
    return {
        "executive_rows": len(rows),
        "candidates": len(index.candidates),
        "contexts": len(index.contexts),
        "packages": len(index.packages),
        "conflicts": len(index.conflicts),
        "last_event_id": rows[-1].executive_event_id if rows else None,
    }


def capture_snapshot(service, subject_id: str, *, as_of: str,
                     actor_id="founder", scope: str = "portfolio") -> dict:
    key = f"executive-snapshot:{scope}:{subject_id}:{as_of}"
    existing = service.store.find_by_idempotency_key(key)
    if existing is not None:
        return {**existing.payload, "snapshot_id": existing.subject_id}

    index = service.get_index()
    if scope == "package":
        detail = {"lineage": service.lineage(subject_id),
                  "trace": service.trace(subject_id)}
    else:
        detail = {"dashboard": service.health_dashboard(as_of=as_of)}

    snapshot = {
        "scope": scope, "subject_id": subject_id,
        "computed_at": now_iso(), "as_of": as_of,
        "detail": detail,
        "invariants": index.assert_invariants(),
        "versions": _versions(service),
        "source_high_watermarks": _watermarks(service, index),
        "reproducibility_note": (
            "a snapshot is a record, not an authority — rebuilding the "
            "Decision Index from the append-only log at these watermarks "
            "reproduces it"),
    }
    row = service._record(
        "executive.snapshot_captured", actor_type="human", actor_id=actor_id,
        subject_type="snapshot", subject_id=service._stable_id(key),
        payload=snapshot, idempotency_key=key)
    return {**snapshot, "snapshot_id": row.subject_id}

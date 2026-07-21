"""Frozen, reproducible product snapshots (T020).

A snapshot is a record, not an authority. Recapturing the same `as_of`
returns the ORIGINAL, and recomputing from the append-only log at the
recorded watermarks reproduces it. Every version that contributed is
frozen alongside it — product, research, growth, and analytics — so a
number in an old snapshot stays explainable after the rules evolve.
"""
from __future__ import annotations

from intent_engine.product.graph import GRAPH_VERSION
from intent_engine.product.index import (
    OPPORTUNITY_INDEX_VERSION, PROBLEM_INDEX_VERSION,
)
from intent_engine.product.intake import INTAKE_VERSION
from intent_engine.product.portfolio import (
    BALANCE_VERSION, READINESS_VERSION, ROLLUP_VERSION, SUMMARY_VERSION,
)
from intent_engine.product.problems import PROBLEM_DEDUP_VERSION
from intent_engine.product.proposals import PROPOSAL_VERSION
from intent_engine.product.records import PRODUCT_SCHEMA_VERSION, now_iso
from intent_engine.product.roadmap_diff import (
    CANDIDATE_VERSION, DIFF_VERSION,
)
from intent_engine.product.scoring import SCORE_VERSIONS
from intent_engine.product.specs import SPEC_CONTRACT_VERSION

SNAPSHOT_VERSION = "product_snapshot.v1"


def _versions(service) -> dict:
    versions = {
        "snapshot_version": SNAPSHOT_VERSION,
        "product_schema_version": PRODUCT_SCHEMA_VERSION,
        "problem_index_version": PROBLEM_INDEX_VERSION,
        "opportunity_index_version": OPPORTUNITY_INDEX_VERSION,
        "problem_dedup_version": PROBLEM_DEDUP_VERSION,
        "proposal_contract_version": PROPOSAL_VERSION,
        "spec_contract_version": SPEC_CONTRACT_VERSION,
        "graph_version": GRAPH_VERSION,
        "intake_version": INTAKE_VERSION,
        "rollup_version": ROLLUP_VERSION,
        "balance_version": BALANCE_VERSION,
        "readiness_version": READINESS_VERSION,
        "summary_version": SUMMARY_VERSION,
        "roadmap_candidate_version": CANDIDATE_VERSION,
        "roadmap_diff_version": DIFF_VERSION,
        "model_version": service.model_version,
        "score_versions": dict(SCORE_VERSIONS),
    }
    # Versions owned by other subsystems are READ from them, so a snapshot
    # records what actually produced its inputs rather than a local copy.
    if service.research is not None:
        from intent_engine.research.graph import RANK_VERSION, STANCE_VERSION
        from intent_engine.research.index import (
            INDEX_VERSION as EVIDENCE_INDEX_VERSION,
        )
        from intent_engine.research.packages import (
            CONCLUSION_VERSION, PACKAGE_VERSION,
        )
        versions["research_versions"] = {
            "evidence_index_version": EVIDENCE_INDEX_VERSION,
            "package_version": PACKAGE_VERSION,
            "conclusion_version": CONCLUSION_VERSION,
            "stance_version": STANCE_VERSION,
            "rank_version": RANK_VERSION,
        }
    if service.growth is not None:
        from intent_engine.growth.results import LABEL_RULE_VERSION
        versions["growth_versions"] = {"label_rule_version": LABEL_RULE_VERSION}
    try:
        from intent_engine.analytics.models import METRIC_VERSIONS
        versions["analytics_metric_versions"] = dict(METRIC_VERSIONS)
    except ImportError:                                     # pragma: no cover
        pass
    return versions


def _watermarks(service, index) -> dict:
    rows = service.store.read_all()
    return {
        "product_rows": len(rows),
        "problems": len(index.problem_index.problems),
        "opportunities": len(index.opportunities),
        "proposals": len(index.proposals),
        "evidence_references": sum(
            len(o["evidence_references"]) for o in index.opportunities.values()),
        "recorded_edges": len(index.edges),
        "last_event_id": rows[-1].product_event_id if rows else None,
    }


def capture_portfolio_snapshot(service, portfolio_id: str, *, as_of: str,
                               actor_id="founder") -> dict:
    key = f"portfolio-snapshot:{portfolio_id}:{as_of}"
    existing = service.store.find_by_idempotency_key(key)
    if existing is not None:
        return {**existing.payload, "snapshot_id": existing.subject_id}

    index = service.get_index()
    view = service.portfolio(portfolio_id, as_of=as_of)
    snapshot = {
        "portfolio_id": portfolio_id,
        "computed_at": now_iso(),
        "as_of": as_of,
        "totals": view["rollup"]["totals"],
        "initiatives": view["rollup"]["initiatives"],
        "balance": view["balance"],
        "executive_summary": view["executive_summary"],
        "priority_order": view["readiness"]["priority_order"],
        "sequence_order": view["readiness"]["sequence_order"],
        "unrankable": view["readiness"]["unrankable"],
        "versions": _versions(service),
        "source_high_watermarks": _watermarks(service, index),
        "invariants": index.assert_invariants(),
        "reproducibility_note": (
            "a snapshot is a record, not an authority — rebuilding the "
            "indexes from the append-only log at these watermarks reproduces "
            "it"),
    }
    row = service._record(
        "product.portfolio_snapshot", actor_type="human", actor_id=actor_id,
        portfolio_id=portfolio_id, subject_type="snapshot",
        subject_id=service._stable_id(key), payload=snapshot,
        idempotency_key=key)
    return {**snapshot, "snapshot_id": row.subject_id}


def capture_proposal_snapshot(service, proposal_id: str, *, as_of: str,
                              actor_id="founder") -> dict:
    key = f"proposal-snapshot:{proposal_id}:{as_of}"
    existing = service.store.find_by_idempotency_key(key)
    if existing is not None:
        return {**existing.payload, "snapshot_id": existing.subject_id}

    state = service.get_state()
    index = service.get_index()
    proposal = state.proposals[proposal_id]
    spec_id, spec = state.spec_for_current_version(proposal_id)
    snapshot = {
        "proposal_id": proposal_id,
        "proposal_version": proposal["version"],
        "spec_id": spec_id,
        "spec_version": spec["version"] if spec else None,
        "opportunity_id": proposal["opportunity_id"],
        "problem_id": proposal["problem_id"],
        "status": proposal["status"],
        "computed_at": now_iso(),
        "as_of": as_of,
        "scores": service.score_proposal(proposal_id, as_of=as_of,
                                         record=False),
        "lineage": service.lineage(proposal_id),
        "spec_debt": service.get_spec_debt(spec_id) if spec_id else None,
        "decision_debt": list(proposal.get("decision_debt") or []),
        "versions": _versions(service),
        "source_high_watermarks": _watermarks(service, index),
        "reproducibility_note": (
            "recapturing the same as_of returns this record; recomputing "
            "from the log at these watermarks reproduces it"),
    }
    row = service._record(
        "product.proposal_snapshot", actor_type="human", actor_id=actor_id,
        proposal_id=proposal_id, proposal_version=proposal["version"],
        subject_type="snapshot", subject_id=service._stable_id(key),
        payload=snapshot, idempotency_key=key)
    return {**snapshot, "snapshot_id": row.subject_id}

"""Reproducible workspace snapshots (T023).

A snapshot captures enough to reproduce a session AGAINST THE VERSIONS IT
SAW, not against latest live state: the workspace store high-watermark, the
source subsystems' high-watermarks / snapshot versions, the routing
contract version, the brief/report template versions, and the prompt/model
version where a model was used.

Two kinds of replay, distinguished honestly:

  * DETERMINISTIC artifacts (briefs, reports, the ClaimSet, explainability
    chains) replay byte-identically — they are pure compositions of the
    captured source reads.
  * MODEL-ASSISTED prose replays SEMANTICALLY: identical only when the
    stored NarrativeCandidate is reused or the same fake deterministic
    client is supplied. Exact conversational reproduction is not promised
    for free-running model prose, and this is stated rather than pretended.
"""
from __future__ import annotations

from intent_engine.personal.briefing import BRIEF_VERSION
from intent_engine.personal.conversation import (
    CONVERSATION_VERSION, NARRATIVE_PROMPT_VERSION,
)
from intent_engine.personal.records import (
    PERSONAL_SCHEMA_VERSION, ROUTING_CONTRACT_VERSION, SOURCE_CONTRACT_VERSION,
    now_iso,
)
from intent_engine.personal.reports import REPORT_VERSION

SNAPSHOT_VERSION = "personal_snapshot.v1"


def _versions(service) -> dict:
    versions = {
        "snapshot_version": SNAPSHOT_VERSION,
        "personal_schema_version": PERSONAL_SCHEMA_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "routing_contract_version": ROUTING_CONTRACT_VERSION,
        "conversation_version": CONVERSATION_VERSION,
        "brief_template_version": BRIEF_VERSION,
        "report_template_version": REPORT_VERSION,
        "narrative_prompt_version": NARRATIVE_PROMPT_VERSION,
        "model_version": service.model_version,
    }
    # source subsystem versions — READ from each, never copied as behaviour
    if service.research is not None:
        from intent_engine.research.index import INDEX_VERSION
        versions["research_evidence_index_version"] = INDEX_VERSION
    if service.product is not None:
        from intent_engine.product.index import (
            OPPORTUNITY_INDEX_VERSION, PROBLEM_INDEX_VERSION,
        )
        versions["product_index_versions"] = {
            "problem": PROBLEM_INDEX_VERSION,
            "opportunity": OPPORTUNITY_INDEX_VERSION}
    if service.executive is not None:
        from intent_engine.executive.index import DECISION_INDEX_VERSION
        versions["executive_decision_index_version"] = DECISION_INDEX_VERSION
    return versions


def _source_high_watermarks(service) -> dict:
    """Each source's high-watermark, so replay targets the versions the
    session saw. Read-only."""
    marks = {"personal_rows": len(service.store.read_all())}
    if service.research is not None:
        marks["research_rows"] = len(service.research.store.read_all())
    if service.product is not None:
        marks["product_rows"] = len(service.product.store.read_all())
    if service.executive is not None:
        marks["executive_rows"] = len(service.executive.store.read_all())
    return marks


def capture_snapshot(service, *, as_of: str, actor_id="founder") -> dict:
    key = f"personal-snapshot:{as_of}"
    existing = service.store.find_by_idempotency_key(key)
    if existing is not None:
        return {**existing.payload, "snapshot_id": existing.subject_id}

    snapshot = {
        "as_of": as_of,
        "computed_at": now_iso(),
        "versions": _versions(service),
        "source_high_watermarks": _source_high_watermarks(service),
        "durable_memory": service.durable_memory(),
        "replay_semantics": {
            "deterministic_artifacts": "byte-identical (briefs, reports, "
                                       "ClaimSets, explainability chains)",
            "model_prose": "semantic — identical only when the stored "
                           "NarrativeCandidate or the same fake client is "
                           "reused",
        },
        "reproducibility_note": (
            "replay reproduces against these captured versions and "
            "watermarks, not against the latest live state of the source "
            "subsystems"),
    }
    row = service._record(
        "personal.snapshot_captured", actor_type="human", actor_id=actor_id,
        source="workspace", subject_type="snapshot",
        subject_id=service._stable_id(key), payload=snapshot,
        idempotency_key=key)
    return {**snapshot, "snapshot_id": row.subject_id}

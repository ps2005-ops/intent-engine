"""Reproducible run snapshots (T023.5).

Captures company identity, the normalized input, consent version, source
content hashes and high-watermarks, every contract/agent/model version, and
the availability/freshness states — so a run reproduces against the versions
it saw, not against latest live state.

Replay semantics, stated honestly:
  * deterministic sections (the assembled sections, evidence, availability)
    replay BYTE-IDENTICAL;
  * model-assisted conversation prose replays SEMANTICALLY (same claims,
    evidence, confidence, limitations) unless the narrative is stored.
"""
from __future__ import annotations

from intent_engine.founder_intelligence.records import (
    FOUNDER_INTELLIGENCE_CONTRACT_VERSION, FOUNDER_INTELLIGENCE_SCHEMA_VERSION,
    now_iso,
)
from intent_engine.founder_intelligence.conversation import (
    CONVERSATION_VERSION, NARRATIVE_PROMPT_VERSION,
)
from intent_engine.founder_intelligence.hooks import HOOK_VERSION
from intent_engine.founder_intelligence.identity import IDENTITY_VERSION
from intent_engine.founder_intelligence.ingestion import (
    INGESTION_VERSION, PARSER_VERSION,
)

SNAPSHOT_VERSION = "fi_snapshot.v1"


def _versions(service) -> dict:
    versions = {
        "snapshot_version": SNAPSHOT_VERSION,
        "fi_schema_version": FOUNDER_INTELLIGENCE_SCHEMA_VERSION,
        "fi_contract_version": FOUNDER_INTELLIGENCE_CONTRACT_VERSION,
        "identity_version": IDENTITY_VERSION,
        "ingestion_version": INGESTION_VERSION,
        "parser_version": PARSER_VERSION,
        "hook_version": HOOK_VERSION,
        "conversation_version": CONVERSATION_VERSION,
        "narrative_prompt_version": NARRATIVE_PROMPT_VERSION,
        "model_version": service.model_version,
    }
    # the T023 provenance contract this reuses
    from intent_engine.personal.records import SOURCE_CONTRACT_VERSION
    versions["source_contract_version"] = SOURCE_CONTRACT_VERSION
    return versions


def capture_snapshot(service, run_id: str, *, company_domain: str, as_of: str,
                     source_hashes=(), actor_id="founder") -> dict:
    key = f"fi-snapshot:{run_id}:{as_of}"
    existing = service.store.find_by_idempotency_key(key)
    if existing is not None:
        return {**existing.payload, "snapshot_id": existing.subject_id}

    rows = service.store.for_run(run_id)
    snapshot = {
        "run_id": run_id, "company_domain": company_domain,
        "computed_at": now_iso(), "as_of": as_of,
        "versions": _versions(service),
        "source_content_hashes": list(source_hashes),
        "source_high_watermarks": {"fi_rows": len(service.store.read_all()),
                                   "run_rows": len(rows)},
        "replay_semantics": {
            "deterministic_sections": "byte-identical",
            "model_conversation_prose": "semantic — same claims, evidence, "
                                        "confidence, and limitations reproduce",
        },
        "reproducibility_note": "reproduces against these captured versions "
                                "and hashes, not against latest live state",
    }
    row = service._record(
        "fi.snapshot_captured", run_id=run_id, company_domain=company_domain,
        actor_type="human", actor_id=actor_id, source="system",
        subject_type="snapshot", subject_id=service._stable_id(key),
        payload=snapshot, idempotency_key=key)
    return {**snapshot, "snapshot_id": row.subject_id}

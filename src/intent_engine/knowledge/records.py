"""The canonical knowledge contract (T016): record envelopes, taxonomies,
consent states, honest markers.

Three layers, never collapsed: FEEDBACK (an observation) -> INSIGHT (a
proposed interpretation, a proposal until a human validates it) ->
KNOWLEDGE ITEM (a human-validated, cited, scoped, limited, versioned
lesson). Rejected and superseded items remain history forever.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.core.decision_ids import is_ulid, new_ulid

KNOWLEDGE_SCHEMA_VERSION = 1

FEEDBACK_TYPES = {
    "feedback.founder_outcome", "feedback.customer_reply",
    "feedback.report_review", "feedback.internal_review",
    "feedback.crm_observation",
    # T018: an experiment result enters the learning loop as FEEDBACK —
    # evidence, never a conclusion. Promotion stays human-gated exactly
    # as it is for every other feedback type.
    "feedback.experiment_result",
    # quote-consent facts (exact text + intended use; approval human-only)
    "feedback.quote_consent_requested", "feedback.quote_consent_approved",
    "feedback.quote_consent_rejected", "feedback.quote_consent_revoked",
}
CONSENT_EVENTS = {t for t in FEEDBACK_TYPES if "quote_consent" in t}
CONSENT_STATES = {"not_requested", "requested", "approved", "rejected",
                  "revoked"}
QUOTE_USES = {"public", "internal"}

# insight / knowledge / mechanism / privacy rows all live in ONE
# append-only knowledge.jsonl (one store, many item types — P9).
INSIGHT_EVENTS = {
    "insight.proposed", "insight.revised", "insight.validation_requested",
    "insight.validated", "insight.rejected", "insight.superseded",
    "insight.promotion_requested",
}
KNOWLEDGE_EVENTS = {
    "knowledge.promoted", "knowledge.rejected", "knowledge.superseded",
    "knowledge.retracted",
}
MECHANISM_EVENTS = {"mechanism.proposed", "mechanism.review"}
PRIVACY_EVENTS = {"knowledge.access_restricted", "knowledge.anonymized",
                  "knowledge.tombstoned"}
KNOWLEDGE_ROW_TYPES = (INSIGHT_EVENTS | KNOWLEDGE_EVENTS | MECHANISM_EVENTS
                       | PRIVACY_EVENTS)

KNOWLEDGE_CATEGORIES = {
    "decision_pattern", "execution_lesson", "customer_signal",
    "risk_pattern", "measurement_rule", "process_improvement",
    "mechanism_candidate",
}
RETRACTION_REASONS = {"incorrect", "outdated", "scope_violation",
                      "privacy_request", "source_invalidated"}
MECHANISM_STATUSES = {"proposed", "under_review",
                      "accepted_for_library_change", "rejected", "superseded"}

ACTOR_TYPES = {"human", "agent", "system"}

# Language wall: claim vocabulary that a claim/statement may not carry
# unless exact source evidence + an existing gate supports it (none does
# in V1, so these are rejected outright at propose/promote time).
BANNED_CLAIM_LANGUAGE = (
    "proven", "always", "guaranteed", "causes", "universally",
    "validated by data", "statistically significant", "customer-approved",
)

# Honest markers used across errors and read models.
MARKER_INSUFFICIENT = "INSUFFICIENT SUPPORT"
MARKER_NOT_VALIDATED = "NOT VALIDATED"
MARKER_CITATION_REQUIRED = "CITATION REQUIRED"
MARKER_CONSENT_REQUIRED = "QUOTE CONSENT REQUIRED"


class KnowledgeError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def assert_claim_language(text: str) -> None:
    import re
    lowered = (text or "").lower()
    hits = []
    for w in BANNED_CLAIM_LANGUAGE:
        # word boundaries for single words ('provenance' is not 'proven');
        # plain substring for multi-word phrases
        if " " in w:
            if w in lowered:
                hits.append(w)
        elif re.search(rf"\b{re.escape(w)}\b", lowered):
            hits.append(w)
    if hits:
        raise KnowledgeError(
            f"{MARKER_INSUFFICIENT}: claim language not supported by any "
            f"existing gate: {hits}")


@dataclass(frozen=True)
class Row:
    """One immutable line — used for both feedback.jsonl and
    knowledge.jsonl rows. `record_type` says what it is; `subject_id`
    is the feedback/insight/knowledge/proposal identity it concerns."""
    record_type: str
    subject_id: str
    actor_type: str
    actor_id: str
    source: str
    row_id: str = field(default_factory=new_ulid)
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    decision_id: str | None = None
    prediction_id: str | None = None
    crm_entity_id: str | None = None
    company_event_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = KNOWLEDGE_SCHEMA_VERSION
    payload: dict = field(default_factory=dict)

    def validate(self, allowed_types: set) -> None:
        if self.record_type not in allowed_types:
            raise KnowledgeError(f"unknown record_type: {self.record_type!r}")
        if not is_ulid(self.row_id):
            raise KnowledgeError("row_id must be a ULID")
        if self.actor_type not in ACTOR_TYPES:
            raise KnowledgeError(f"unknown actor_type: {self.actor_type!r}")
        for name in ("subject_id", "actor_id", "source"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise KnowledgeError(f"{name} must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise KnowledgeError("payload must be a dict")
        try:
            if json.loads(json.dumps(self.payload)) != self.payload:
                raise KnowledgeError("payload does not survive JSON round-trip")
        except (TypeError, ValueError) as exc:
            raise KnowledgeError(f"payload not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "Row":
        data = json.loads(line)
        v = data.get("schema_version")
        if isinstance(v, int) and v > KNOWLEDGE_SCHEMA_VERSION:
            raise KnowledgeError(
                f"row {data.get('row_id')} schema v{v} > supported "
                f"v{KNOWLEDGE_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("row_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)

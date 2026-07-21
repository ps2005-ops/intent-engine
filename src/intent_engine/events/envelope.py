"""The canonical company-event contract (T013).

This module is the ONE source of truth for the envelope and the taxonomy.
Docs cross-reference it; no other file restates the full contract.

Taxonomy discipline: an event type exists here only because a real current
producer emits it (see EVENT_PRODUCERS — exactly one authoritative
producer per type, enforced at publish time). No speculative types.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.core.decision_ids import is_ulid, new_ulid

COMPANY_EVENT_SCHEMA_VERSION = 1

# --- the closed taxonomy, with exactly one authoritative producer each -------
# decision.* is owned by the DecisionEvent bridge ONLY: the pipeline never
# publishes decision facts directly, so the same fact cannot arrive twice
# from two producers.
EVENT_PRODUCERS = {
    # Decision (bridged one-way from the authoritative DecisionEvent store)
    "decision.created":                   "decision_event_bridge",
    "decision.submitted":                 "decision_event_bridge",
    "decision.recommendation_issued":     "decision_event_bridge",
    "decision.approved":                  "decision_event_bridge",
    "decision.declined":                  "decision_event_bridge",
    "decision.cancelled":                 "decision_event_bridge",
    "decision.superseded":                "decision_event_bridge",
    "decision.resolved":                  "decision_event_bridge",
    "decision.calibrated":                "decision_event_bridge",
    "decision.analysis_failed":           "decision_event_bridge",
    "decision.prediction_logging_failed": "decision_event_bridge",
    "decision.report_generation_failed":  "decision_event_bridge",
    # Prediction (owned by the premortem pipeline's recording step)
    "prediction.recorded":                "premortem_pipeline",
    # Report (owned by the report renderer)
    "report.generated":                   "report_renderer",
    "report.generation_failed":           "report_renderer",
    # Approval walls (content) — requests may be automated; approval,
    # rejection, and publication are HUMAN transitions (enforced in
    # publisher.py, tested in test_approval_events.py).
    "content.approval_requested":         "approval_wall",
    "content.approved":                   "approval_wall",
    "content.rejected":                   "approval_wall",
    "content.published":                  "approval_wall",
    # Approval walls (claims) — distinct from content approval; the A-M5
    # calibration gate stays upstream of any claim.review_requested.
    "claim.review_requested":             "approval_wall",
    "claim.approved":                     "approval_wall",
    "claim.rejected":                     "approval_wall",
    # Growth (T018) — the experiment platform is the one authoritative
    # producer. These are NOTIFICATIONS: no consumer may infer experiment
    # state from them (the growth log is the source of truth), and there
    # is deliberately no "experiment_won" or rollout event in the
    # taxonomy, because no such fact exists in this architecture.
    "growth.experiment_started":          "growth_platform",
    "growth.experiment_stopped":          "growth_platform",
    "growth.result_labelled":             "growth_platform",
}
EVENT_TYPES = set(EVENT_PRODUCERS)

ACTOR_TYPES = {"human", "agent", "system"}
SUBJECT_TYPES = {"decision", "prediction", "report", "content", "claim",
                 "experiment"}
SOURCES = {"web_intake", "cli", "report_review", "crm", "api", "system",
           "bridge"}


class EnvelopeError(ValueError):
    """Raised when an event fails envelope validation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class CompanyEvent:
    event_type: str
    subject_type: str
    subject_id: str
    producer: str
    actor_type: str
    actor_id: str
    source: str
    event_id: str = field(default_factory=new_ulid)
    occurred_at: str = field(default_factory=_now)
    recorded_at: str = field(default_factory=_now)
    decision_id: str | None = None
    prediction_id: str | None = None
    prospect_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    payload_schema_version: int = COMPANY_EVENT_SCHEMA_VERSION
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise EnvelopeError(f"unknown event_type: {self.event_type!r}")
        if self.producer != EVENT_PRODUCERS[self.event_type]:
            raise EnvelopeError(
                f"{self.event_type} is owned by "
                f"{EVENT_PRODUCERS[self.event_type]!r}, not {self.producer!r} "
                "(one authoritative producer per event type)")
        if not is_ulid(self.event_id):
            raise EnvelopeError(f"event_id must be a ULID: {self.event_id!r}")
        if self.actor_type not in ACTOR_TYPES:
            raise EnvelopeError(f"unknown actor_type: {self.actor_type!r}")
        if self.subject_type not in SUBJECT_TYPES:
            raise EnvelopeError(f"unknown subject_type: {self.subject_type!r}")
        if self.source not in SOURCES:
            raise EnvelopeError(f"unknown source: {self.source!r}")
        for name in ("subject_id", "actor_id", "occurred_at", "recorded_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise EnvelopeError(f"{name} must be a non-empty string")
        if not isinstance(self.payload_schema_version, int) \
                or self.payload_schema_version < 1:
            raise EnvelopeError("payload_schema_version must be an int >= 1")
        if not isinstance(self.payload, dict):
            raise EnvelopeError("payload must be a dict")
        try:
            round_tripped = json.loads(json.dumps(self.payload))
        except (TypeError, ValueError) as exc:
            raise EnvelopeError(f"payload is not JSON-safe: {exc}") from exc
        if round_tripped != self.payload:
            raise EnvelopeError("payload does not survive JSON round-trip")

    # -- deterministic serialization ------------------------------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "CompanyEvent":
        data = json.loads(line)
        version = data.get("payload_schema_version")
        if isinstance(version, int) and version > COMPANY_EVENT_SCHEMA_VERSION:
            raise EnvelopeError(
                f"event {data.get('event_id')} payload schema v{version} > "
                f"supported v{COMPANY_EVENT_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        """The logical content an idempotency_key locks in: retrying the
        SAME publish returns the original; reusing the key for different
        content is a caller bug and is rejected."""
        core = {k: v for k, v in asdict(self).items()
                if k not in ("event_id", "recorded_at")}
        return json.dumps(core, sort_keys=True)

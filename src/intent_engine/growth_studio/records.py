"""V2.0 Growth Studio records — orchestration references, never copies.

Single-client boundary: every record carries product_id
"founder_intelligence". Facts, hypotheses, and creative ideas are
distinct types; a post idea can never become an accepted market insight
merely because it was generated.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.core.decision_ids import is_ulid, new_ulid

STUDIO_SCHEMA_VERSION = 1
PRODUCT_ID = "founder_intelligence"

# --- the Creative Strategy Loop state machine --------------------------------
LOOP_STATES = (
    "OBSERVED", "RESEARCHED", "HYPOTHESIS_PROPOSED", "STRATEGY_PROPOSED",
    "CONCEPT_PROPOSED", "DRAFTED", "AWAITING_REVIEW",
    "APPROVED_FOR_FUTURE_EXECUTION", "REJECTED",
    "PUBLISHED_EXTERNALLY_RECORDED", "MEASUREMENT_PENDING", "MEASURED",
    "LEARNING_PROPOSED", "LEARNING_ACCEPTED", "ARCHIVED",
)

LOOP_TRANSITIONS = {
    "OBSERVED": {"RESEARCHED"},
    "RESEARCHED": {"HYPOTHESIS_PROPOSED"},
    "HYPOTHESIS_PROPOSED": {"STRATEGY_PROPOSED", "REJECTED"},
    "STRATEGY_PROPOSED": {"CONCEPT_PROPOSED", "REJECTED"},
    "CONCEPT_PROPOSED": {"DRAFTED", "REJECTED"},
    "DRAFTED": {"AWAITING_REVIEW"},
    "AWAITING_REVIEW": {"APPROVED_FOR_FUTURE_EXECUTION", "REJECTED"},
    # TERMINAL in V2.0 unless publication is manually recorded or received
    # from an existing approved source — the Studio itself never publishes.
    "APPROVED_FOR_FUTURE_EXECUTION": {"PUBLISHED_EXTERNALLY_RECORDED"},
    "REJECTED": {"ARCHIVED"},
    "PUBLISHED_EXTERNALLY_RECORDED": {"MEASUREMENT_PENDING"},
    "MEASUREMENT_PENDING": {"MEASURED"},
    "MEASURED": {"LEARNING_PROPOSED", "ARCHIVED"},
    "LEARNING_PROPOSED": {"LEARNING_ACCEPTED", "ARCHIVED"},
    "LEARNING_ACCEPTED": {"ARCHIVED"},
    "ARCHIVED": set(),
}

# Only these actors may move an item out of the V2.0 terminal state.
MANUAL_PUBLICATION_ACTORS = frozenset({"human", "approved_source"})

# --- canonical funnel ---------------------------------------------------------
FUNNEL = (
    "landing_viewed", "analysis_started", "analysis_completed",
    "result_viewed", "evidence_expanded", "conversation_started",
    "report_created", "signup_intent", "retained_return",
)
FUNNEL_TRANSITIONS = tuple(
    f"{a}->{b}" for a, b in zip(FUNNEL, FUNNEL[1:]))

BRAND_RESEARCH_EXPERIMENT = "BRAND_RESEARCH"   # explicit non-funnel target

# --- canonical record kinds ---------------------------------------------------
RECORD_KINDS = (
    "GrowthObservation", "AudienceInsight", "GrowthHypothesis",
    "StrategyProposal", "CreativeConcept", "ChannelDraft",
    "ExperimentPlan", "PerformanceObservation", "LearningCandidate",
    "AcceptedLearning", "ExecutionManifest",
)

CHANNELS = ("linkedin", "x", "reddit", "hackernews", "newsletter",
            "producthunt", "seo", "website")

CLAIM_CLASSES = (
    "SUPPORTED_PRODUCT_FACT", "SUPPORTED_MARKET_OBSERVATION",
    "FOUNDER_OPINION", "HYPOTHESIS", "CUSTOMER_QUOTE", "UNSUPPORTED_REJECT",
)

STUDIO_EVENTS = frozenset({
    "studio.item_created",
    "studio.item_transitioned",
    "studio.observation_recorded",
    "studio.insight_recorded",
    "studio.hypothesis_proposed",
    "studio.strategy_proposed",
    "studio.concept_proposed",
    "studio.draft_referenced",
    "studio.experiment_planned",
    "studio.performance_recorded",
    "studio.learning_proposed",
    "studio.learning_accepted",
    "studio.learning_rejected",
    "studio.briefing_produced",
    "studio.manifest_created",
    "studio.publication_recorded",
})

ACTOR_TYPES = frozenset({"human", "system", "approved_source"})


class StudioError(ValueError):
    """A Growth Studio record or operation violated its contract."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StudioEvent:
    event_type: str
    actor_type: str
    actor_id: str
    studio_event_id: str = field(default_factory=new_ulid)
    product_id: str = PRODUCT_ID
    item_id: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    idempotency_key: str | None = None
    schema_version: int = STUDIO_SCHEMA_VERSION
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in STUDIO_EVENTS:
            raise StudioError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.studio_event_id):
            raise StudioError("studio_event_id must be a ULID")
        if self.actor_type not in ACTOR_TYPES:
            raise StudioError(f"unknown actor_type: {self.actor_type!r}")
        if self.product_id != PRODUCT_ID:
            raise StudioError(
                f"single-client boundary: product_id must be {PRODUCT_ID!r} "
                f"(got {self.product_id!r}) — no multi-tenant marketing")
        for name in ("actor_id", "occurred_at", "recorded_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise StudioError(f"{name} must be non-empty")
        if not isinstance(self.payload, dict):
            raise StudioError("payload must be a dict")
        try:
            if json.loads(json.dumps(self.payload)) != self.payload:
                raise StudioError("payload not round-trip safe")
        except (TypeError, ValueError) as exc:
            raise StudioError(f"payload not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "StudioEvent":
        data = json.loads(line)
        version = data.get("schema_version")
        if isinstance(version, int) and version > STUDIO_SCHEMA_VERSION:
            raise StudioError(
                f"row {data.get('studio_event_id')} is schema v{version} > "
                f"supported v{STUDIO_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("studio_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)


def require_scope(payload: dict, *, kind: str) -> None:
    """Every Studio record carries the single-client scope fields."""
    required = ("audience", "channel", "objective", "evidence_window",
                "approval_state", "measurement_state")
    missing = [f for f in required if not payload.get(f)]
    if missing:
        raise StudioError(f"{kind} missing scope fields: {missing}")
    if payload["channel"] not in CHANNELS:
        raise StudioError(f"unknown channel {payload['channel']!r}")
    target = payload.get("funnel_target")
    if kind in ("GrowthHypothesis", "ExperimentPlan"):
        if target not in FUNNEL_TRANSITIONS and \
                target != BRAND_RESEARCH_EXPERIMENT:
            raise StudioError(
                f"{kind} must target one measurable funnel transition "
                f"or declare itself {BRAND_RESEARCH_EXPERIMENT!r} "
                f"(got {target!r})")

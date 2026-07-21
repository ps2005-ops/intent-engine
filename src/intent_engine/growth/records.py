"""The canonical growth contract (T018): envelope, taxonomy, labels,
namespaces, terminal states.

An experiment is a PRE-REGISTERED COMMITMENT, not a query run against
data that already exists. Everything in this module exists to make the
dishonest version impossible rather than discouraged:

  * every assignment, exposure, observation, and analysis binds to an
    APPROVED experiment version (improvement 1);
  * the primary outcome metric can never be replaced after approval —
    only a new version can carry a different metric (improvement 2);
  * exactly one canonical analysis plan drives labels; anything else is
    EXPLORATORY and structurally cannot (improvement 3);
  * synthetic and production experiments live in separate namespaces and
    can never be mixed (improvement 6);
  * terminal states archive; they never delete (improvement 7);
  * a founder decision against the statistical read is a first-class
    immutable fact, not a silent relabel (improvement 8).

There is deliberately NO `winner` field anywhere in this contract.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.core.decision_ids import is_ulid, new_ulid

GROWTH_SCHEMA_VERSION = 1

# --- namespaces (improvement 6) ----------------------------------------------
# Production experiments and synthetic evaluation runs are separate worlds.
# They use separate store files, separate consumer checkpoints, and a row
# from one may never be read as a row of the other.
NAMESPACE_PRODUCTION = "production"
NAMESPACE_SYNTHETIC = "synthetic"
NAMESPACES = {NAMESPACE_PRODUCTION, NAMESPACE_SYNTHETIC}

# --- taxonomy -----------------------------------------------------------------
REGISTRATION_EVENTS = {
    "growth.experiment_drafted", "growth.hypothesis_defined",
    "growth.arms_defined", "growth.metric_defined",
    "growth.guardrails_defined", "growth.randomization_defined",
    "growth.stopping_rules_defined", "growth.analysis_plan_defined",
    "growth.registration_submitted", "growth.registration_approved",
    "growth.registration_rejected", "growth.registration_failed",
    "growth.experiment_amended",
}
EXECUTION_EVENTS = {
    "growth.experiment_started", "growth.entity_assigned",
    "growth.assignment_conflict_rejected", "growth.assignment_failed",
    "growth.entity_excluded_after_registration", "growth.exposure_recorded",
    "growth.observation_recorded", "growth.observation_rejected",
    "growth.observation_import_failed", "growth.guardrail_breached",
}
ANALYSIS_EVENTS = {
    "growth.interim_read_recorded", "growth.exploratory_analysis_recorded",
    "growth.stopping_rule_satisfied", "growth.stop_requested",
    "growth.experiment_stopped", "growth.founder_override_recorded",
    "growth.result_labelled", "growth.snapshot_captured",
}
REVIEW_EVENTS = {
    "growth.review_requested", "growth.reviewed", "growth.decision_linked",
    "growth.knowledge_candidate_requested", "growth.hypothesis_prediction_linked",
}
# Terminal states (improvement 7) — every one is an appended fact.
TERMINAL_EVENTS = {
    "growth.experiment_archived", "growth.experiment_superseded",
    "growth.experiment_invalidated", "growth.experiment_withdrawn",
    "growth.experiment_abandoned",
}

GROWTH_EVENT_TYPES = (REGISTRATION_EVENTS | EXECUTION_EVENTS | ANALYSIS_EVENTS
                      | REVIEW_EVENTS | TERMINAL_EVENTS)

# Human-only transitions. Nothing approves, starts, stops, or concludes
# itself — and nothing rolls out at all, at any actor level.
HUMAN_ONLY_EVENTS = {
    "growth.registration_approved", "growth.registration_rejected",
    "growth.experiment_started", "growth.experiment_stopped",
    "growth.reviewed", "growth.founder_override_recorded",
    "growth.experiment_abandoned", "growth.experiment_archived",
    "growth.experiment_invalidated", "growth.experiment_withdrawn",
    "growth.experiment_amended",
}

ACTOR_TYPES = {"human", "agent", "system"}

# --- result labels (§15) ------------------------------------------------------
LABEL_NOT_STARTED = "NOT_STARTED"
LABEL_RUNNING = "RUNNING"
LABEL_TOO_FEW = "TOO FEW OBSERVATIONS"
LABEL_OBSERVATIONAL = "OBSERVATIONAL ONLY"
LABEL_INCONCLUSIVE = "INCONCLUSIVE"
LABEL_DIFFERENCE = "DIFFERENCE OBSERVED"
LABEL_GUARDRAIL = "GUARDRAIL BREACHED"
LABEL_STOPPED_EARLY = "STOPPED EARLY — DEGRADED"
LABEL_ABANDONED = "ABANDONED"
LABEL_ARCHIVED = "ARCHIVED"
LABEL_INVALIDATED = "INVALIDATED"
LABEL_WITHDRAWN = "WITHDRAWN"
LABEL_SUPERSEDED = "SUPERSEDED"
MODIFIER_REVIEW_REQUIRED = "REVIEW REQUIRED"
MODIFIER_NO_CAUSAL_CLAIM = "NO CAUSAL CLAIM"
MODIFIER_FOUNDER_OVERRIDE = "FOUNDER OVERRIDE RECORDED"

RESULT_LABELS = {
    LABEL_NOT_STARTED, LABEL_RUNNING, LABEL_TOO_FEW, LABEL_OBSERVATIONAL,
    LABEL_INCONCLUSIVE, LABEL_DIFFERENCE, LABEL_GUARDRAIL,
    LABEL_STOPPED_EARLY, LABEL_ABANDONED, LABEL_ARCHIVED, LABEL_INVALIDATED,
    LABEL_WITHDRAWN, LABEL_SUPERSEDED,
}

STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_UNKNOWN = "UNKNOWN"

# --- language wall ------------------------------------------------------------
# A growth read model may never speak like a marketing deck. Single words
# are word-boundary matched ('provenance' is not 'proven'); phrases match
# literally.
BANNED_RESULT_LANGUAGE = (
    "winner", "won", "beat", "beats", "proves", "proven", "significant",
    "significance", "guaranteed", "caused", "causes", "outperform",
    "clear win", "definitely", "certain",
)


class GrowthError(ValueError):
    """A growth contract, wall, or pre-registration violation."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scan_banned_language(text: str) -> list:
    lowered = (text or "").lower()
    hits = []
    for term in BANNED_RESULT_LANGUAGE:
        if " " in term:
            if term in lowered:
                hits.append(term)
        elif re.search(rf"\b{re.escape(term)}\b", lowered):
            hits.append(term)
    return sorted(set(hits))


def json_normalize(payload: dict) -> dict:
    """Canonicalize a payload into its stored JSON form ONCE at the service
    boundary, so validation, fingerprinting, and storage see the same bytes."""
    try:
        return json.loads(json.dumps(payload, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise GrowthError(f"payload is not JSON-safe: {exc}") from exc


@dataclass(frozen=True)
class GrowthEvent:
    event_type: str
    experiment_id: str
    namespace: str
    actor_type: str
    actor_id: str
    source: str
    growth_event_id: str = field(default_factory=new_ulid)
    # The APPROVED experiment version this fact binds to (improvement 1).
    # Registration-phase facts carry the version being built; execution and
    # analysis facts carry the version that was approved when they occurred.
    experiment_version: int | None = None
    arm_id: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    crm_entity_id: str | None = None
    decision_id: str | None = None
    prediction_id: str | None = None
    campaign_id: str | None = None
    company_event_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = GROWTH_SCHEMA_VERSION
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in GROWTH_EVENT_TYPES:
            raise GrowthError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.growth_event_id):
            raise GrowthError("growth_event_id must be a ULID")
        if not is_ulid(self.experiment_id):
            raise GrowthError("experiment_id must be a ULID (opaque "
                              "identity — never a name or slug)")
        if self.namespace not in NAMESPACES:
            raise GrowthError(f"unknown namespace: {self.namespace!r}")
        if self.actor_type not in ACTOR_TYPES:
            raise GrowthError(f"unknown actor_type: {self.actor_type!r}")
        for name in ("actor_id", "source", "occurred_at", "recorded_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise GrowthError(f"{name} must be a non-empty string")
        if self.experiment_version is not None \
                and (not isinstance(self.experiment_version, int)
                     or self.experiment_version < 1):
            raise GrowthError("experiment_version must be an int >= 1")
        if not isinstance(self.payload, dict):
            raise GrowthError("payload must be a dict")
        try:
            if json.loads(json.dumps(self.payload)) != self.payload:
                raise GrowthError("payload does not survive JSON round-trip")
        except (TypeError, ValueError) as exc:
            raise GrowthError(f"payload not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "GrowthEvent":
        data = json.loads(line)
        v = data.get("schema_version")
        if isinstance(v, int) and v > GROWTH_SCHEMA_VERSION:
            raise GrowthError(
                f"row {data.get('growth_event_id')} schema v{v} > supported "
                f"v{GROWTH_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("growth_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)

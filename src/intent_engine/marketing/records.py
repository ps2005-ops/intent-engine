"""The canonical marketing contract (T017): envelope, taxonomy, claim
classes, honest markers.

Ownership boundary (load-bearing): marketing owns WORKFLOW ARTIFACTS only
— campaigns, audience selections, briefs, drafts, review packages,
publishing handoffs, and performance observations. It never owns decision
state (DecisionService), delivery (Company Event System), relationship
facts (CRM), metrics (Analytics), or quotes/knowledge (Knowledge). It
reads those systems and references their identities.

Drafting may be automated. Approval and publication may not.

C3–C8 mapping (PLAN_2026-07-21):
  C3 ledger→content hook ....... generators.fan_out_prediction (this task)
  C4 feedback loop ............. BUILT in T016 (knowledge/feedback + quote
                                 gate) — reused here, NOT reimplemented
  C5 lightweight CRM ........... BUILT in T014 — reused here via CRMService
  C6 commit-triggered content .. generators.drafts_from_commits
  C7 public pages .............. generators.render_public_pages
  C8 public roadmap page ....... generators.render_roadmap_page
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.core.decision_ids import is_ulid, new_ulid

MARKETING_SCHEMA_VERSION = 1

CAMPAIGN_EVENTS = {"marketing.campaign_created", "marketing.campaign_revised",
                   "marketing.campaign_archived"}
AUDIENCE_EVENTS = {"marketing.audience_defined",
                   "marketing.audience_resolution_failed"}
EVIDENCE_EVENTS = {"marketing.evidence_attached", "marketing.evidence_rejected"}
BRIEF_EVENTS = {"marketing.brief_created", "marketing.brief_revised"}
DRAFT_EVENTS = {"marketing.draft_created", "marketing.draft_revised",
                "marketing.draft_review_requested", "marketing.draft_approved",
                "marketing.draft_rejected", "marketing.draft_generation_failed"}
CLAIM_EVENTS = {"marketing.claim_flagged", "marketing.claim_review_requested"}
HANDOFF_EVENTS = {"marketing.publish_handoff_created",
                  "marketing.publish_handoff_approved",
                  "marketing.publish_handoff_rejected",
                  "marketing.handoff_blocked",
                  "marketing.publish_recorded"}
PERFORMANCE_EVENTS = {"marketing.performance_observation_recorded",
                      "marketing.feedback_linked",
                      "marketing.performance_import_failed"}

MARKETING_EVENT_TYPES = (CAMPAIGN_EVENTS | AUDIENCE_EVENTS | EVIDENCE_EVENTS
                         | BRIEF_EVENTS | DRAFT_EVENTS | CLAIM_EVENTS
                         | HANDOFF_EVENTS | PERFORMANCE_EVENTS)

# Only humans may make these transitions (no auto-approval anywhere).
HUMAN_ONLY_EVENTS = {"marketing.draft_approved", "marketing.draft_rejected",
                     "marketing.publish_handoff_approved",
                     "marketing.publish_handoff_rejected"}

ACTOR_TYPES = {"human", "agent", "system"}
CHANNELS = {"website", "linkedin", "x", "newsletter", "email", "changelog"}

# Claim classes. Anything not DESCRIPTIVE needs the EXISTING company-event
# claim gate (claim.review_requested -> human claim.approved) before a
# publishing handoff may be approved.
CLAIM_DESCRIPTIVE = "descriptive_factual"
CLAIM_DERIVED_METRIC = "derived_metric"
CLAIM_FORWARD_LOOKING = "forward_looking"
CLAIM_PERFORMANCE = "performance"
CLAIM_TESTIMONIAL = "testimonial"
CLAIM_UNCITED_OPINION = "uncited_opinion"
CLAIMS_REQUIRING_REVIEW = {CLAIM_DERIVED_METRIC, CLAIM_FORWARD_LOOKING,
                           CLAIM_PERFORMANCE, CLAIM_TESTIMONIAL,
                           CLAIM_UNCITED_OPINION}

# Honest markers (never replaced by optimistic values).
MARKER_UNAVAILABLE = "UNAVAILABLE"
MARKER_BLOCKED = "BLOCKED"
MARKER_REVIEW_REQUIRED = "CLAIM REVIEW REQUIRED"
MARKER_CONSENT_REQUIRED = "QUOTE CONSENT REQUIRED"

# Unsupported marketing language. Word-boundary matched for single words
# (so "provenance" is never read as "proven"); phrases matched literally.
# The content engine's own audit (audit_predictive_accuracy_claims) still
# runs on rendered assets — this wall is the draft-level complement.
BANNED_MARKETING_LANGUAGE = (
    "accurate", "accuracy", "proven", "validated performance",
    "well calibrated", "guaranteed", "always", "best", "market-leading",
    "statistically significant", "caused", "drove revenue",
    "customer-approved", "trusted by", "high-converting", "predicts",
)


class MarketingError(ValueError):
    """A marketing contract or wall violation."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scan_banned_language(text: str) -> list:
    lowered = (text or "").lower()
    hits = []
    for term in BANNED_MARKETING_LANGUAGE:
        if " " in term or "-" in term:
            if term in lowered:
                hits.append(term)
        elif re.search(rf"\b{re.escape(term)}\b", lowered):
            hits.append(term)
    return hits


def json_normalize(payload: dict) -> dict:
    """Canonicalize a payload into its stored JSON form (tuples become
    lists, etc.). Applied ONCE at the service boundary so what is
    validated, fingerprinted, and stored are the same bytes — the strict
    round-trip invariant in `MarketingRow.validate` then still catches
    genuinely non-serializable values."""
    try:
        return json.loads(json.dumps(payload, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise MarketingError(f"payload is not JSON-safe: {exc}") from exc


def claim_identity(claim_text: str) -> str:
    """Normalized identity for a claim: whitespace-collapsed, lowercased,
    hashed. Approval binds to this identity, so a meaning-changing edit
    produces a different identity and the old approval no longer applies."""
    normalized = " ".join((claim_text or "").lower().split())
    return "claim-" + hashlib.sha256(normalized.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class MarketingRow:
    event_type: str
    campaign_id: str
    actor_type: str
    actor_id: str
    source: str
    marketing_event_id: str = field(default_factory=new_ulid)
    artifact_id: str | None = None          # brief / draft / handoff / obs id
    revision_id: str | None = None          # exact revision this fact binds to
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    company_event_id: str | None = None
    crm_entity_id: str | None = None
    decision_id: str | None = None
    report_id: str | None = None
    knowledge_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = MARKETING_SCHEMA_VERSION
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in MARKETING_EVENT_TYPES:
            raise MarketingError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.marketing_event_id):
            raise MarketingError("marketing_event_id must be a ULID")
        if not is_ulid(self.campaign_id):
            raise MarketingError("campaign_id must be a ULID (opaque "
                                 "identity — never a title or slug)")
        if self.actor_type not in ACTOR_TYPES:
            raise MarketingError(f"unknown actor_type: {self.actor_type!r}")
        for name in ("actor_id", "source", "occurred_at", "recorded_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise MarketingError(f"{name} must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise MarketingError("payload must be a dict")
        try:
            if json.loads(json.dumps(self.payload)) != self.payload:
                raise MarketingError("payload does not survive JSON round-trip")
        except (TypeError, ValueError) as exc:
            raise MarketingError(f"payload not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "MarketingRow":
        data = json.loads(line)
        v = data.get("schema_version")
        if isinstance(v, int) and v > MARKETING_SCHEMA_VERSION:
            raise MarketingError(
                f"row {data.get('marketing_event_id')} schema v{v} > "
                f"supported v{MARKETING_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("marketing_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)

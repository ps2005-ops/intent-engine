"""The canonical research contract (T019): envelope, taxonomy, vocabularies.

An agent in this repository is not a thing that answers questions. It is
a CONSTRAINED PRODUCER OF REVIEWABLE ARTIFACTS. Everything here exists to
make the dishonest version impossible rather than discouraged.

Six separated layers, never collapsed:

    Request  ->  Plan  ->  Session  ->  Evidence Index  ->  Package
                                                              ->  Conclusion

The EVIDENCE INDEX is the research-memory backbone (`index.py`): it owns
normalized claims, source ids, evidence ids, contradiction links,
freshness and retirement state, and graph node ids. It is NEVER written
by a model — only by deterministic code — and every other layer
references it rather than restating it. Later agents (PM, Executive
Decision, AgentOS, Personal AI) read this substrate instead of
reconstructing their own.

Determinism boundary (load-bearing, see extraction.py):
    deterministic  registration, canonicalization, grading, independence,
                   freshness, retirement, ranking, contradiction
                   detection, coverage, stances, labels, every wall
    model-assisted candidate claim extraction, candidate claim->mechanism
                   links, narrative prose
    a model may NEVER emit a source, URL, citation, author, or date.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.agentos.language_wall import scan_banned_language as _kernel_scan
from intent_engine.core.decision_ids import is_ulid, new_ulid

RESEARCH_SCHEMA_VERSION = 1

# --- taxonomy -----------------------------------------------------------------
REQUEST_EVENTS = {"research.request_created", "research.request_reused",
                  "research.request_related_linked"}
PLAN_EVENTS = {"research.plan_drafted", "research.plan_submitted",
               "research.plan_approved", "research.plan_rejected",
               "research.plan_amended"}
SESSION_EVENTS = {"research.session_started", "research.session_closed",
                  "research.budget_consumed"}
SOURCE_EVENTS = {"research.source_registered", "research.source_rejected",
                 "research.source_verified", "research.source_unverified",
                 "research.source_retired", "research.source_canonicalized"}
EVIDENCE_EVENTS = {"research.evidence_indexed", "research.evidence_rejected",
                   "research.extraction_failed", "research.claim_indexed",
                   "research.relation_indexed", "research.evidence_retired"}
PACKAGE_EVENTS = {"research.package_assembled", "research.package_snapshot",
                  "research.graph_snapshot"}
CONCLUSION_EVENTS = {"research.conclusion_drafted",
                     "research.narrative_generated",
                     "research.review_requested", "research.reviewed"}
PROPOSAL_EVENTS = {"research.mechanism_draft_queued",
                   "research.knowledge_candidate_requested"}

RESEARCH_EVENT_TYPES = (REQUEST_EVENTS | PLAN_EVENTS | SESSION_EVENTS
                        | SOURCE_EVENTS | EVIDENCE_EVENTS | PACKAGE_EVENTS
                        | CONCLUSION_EVENTS | PROPOSAL_EVENTS)

# Human-only. The agent drafts; it never approves, reviews, or promotes.
HUMAN_ONLY_EVENTS = {"research.plan_approved", "research.plan_rejected",
                     "research.plan_amended", "research.reviewed",
                     "research.source_retired"}

ACTOR_TYPES = {"human", "agent", "system"}

# --- source classes (closed) --------------------------------------------------
SOURCE_CLASSES = {
    "primary_data", "peer_reviewed", "official_docs", "book",
    "reputable_press", "industry_report", "company_blog", "personal_blog",
    "forum_post", "social_post", "llm_generated", "unknown",
}
HIGH_CLASSES = {"primary_data", "peer_reviewed", "official_docs", "book"}
MEDIUM_CLASSES = {"reputable_press", "industry_report"}
LOW_CLASSES = {"company_blog", "personal_blog", "forum_post", "social_post",
               "llm_generated"}

QUALITY_HIGH, QUALITY_MEDIUM, QUALITY_LOW, QUALITY_UNKNOWN = (
    "HIGH", "MEDIUM", "LOW", "UNKNOWN")

# --- evidence classes (facts vs interpretations) ------------------------------
EVIDENCE_CLASSES = {"observation", "mechanism", "opinion", "prediction",
                    "recommendation", "methodology", "unknown"}
# An opinion never becomes a mechanism automatically; a recommendation may
# never support a conclusion.
NON_SUPPORTING_CLASSES = {"recommendation"}

# --- graph relations ----------------------------------------------------------
RELATIONS = {"supports", "contradicts", "qualifies", "insufficient",
             "addresses", "derived_from"}

# --- stance vocabulary --------------------------------------------------------
STANCE_SUPPORTED = "SUPPORTED"
STANCE_CONTRADICTED = "CONTRADICTED"
STANCE_MIXED = "MIXED"
STANCE_INSUFFICIENT = "INSUFFICIENT"
STANCE_UNKNOWN = "UNKNOWN"                 # looked, found nothing
STANCE_NOT_INVESTIGATED = "NOT INVESTIGATED"   # never searched — different
STANCES = {STANCE_SUPPORTED, STANCE_CONTRADICTED, STANCE_MIXED,
           STANCE_INSUFFICIENT, STANCE_UNKNOWN, STANCE_NOT_INVESTIGATED}

# Why a MIXED stance exists — a bare MIXED is not an answer.
CONFLICT_REASONS = {"different_populations", "different_dates",
                    "different_methodology", "different_definitions",
                    "unknown"}

# --- uncertainty vocabulary ---------------------------------------------------
UNCERTAINTY_KNOWN = "KNOWN"
UNCERTAINTY_LIKELY = "LIKELY"
UNCERTAINTY_SPECULATIVE = "SPECULATIVE"
UNCERTAINTY_CONFLICTING = "CONFLICTING"
UNCERTAINTY_UNKNOWN = "UNKNOWN"
UNCERTAINTY_LABELS = {UNCERTAINTY_KNOWN, UNCERTAINTY_LIKELY,
                      UNCERTAINTY_SPECULATIVE, UNCERTAINTY_CONFLICTING,
                      UNCERTAINTY_UNKNOWN}

# --- freshness / retirement ---------------------------------------------------
FRESHNESS_FRESH, FRESHNESS_STALE, FRESHNESS_RETIRED = ("FRESH", "STALE",
                                                       "RETIRED")
# Retirement is NOT staleness: stale means old, retired means unusable.
RETIREMENT_REASONS = {"known_false", "superseded", "retracted_by_publisher",
                      "removed_by_publisher", "source_invalidated"}

# --- research debt ------------------------------------------------------------
DEBT_KINDS = {"need_primary_source", "need_replication", "need_newer_evidence",
              "need_experiment", "need_customer_interview",
              "need_independent_corroboration", "need_methodology"}

# --- language wall ------------------------------------------------------------
BANNED_RESEARCH_LANGUAGE = (
    "proved", "proven", "obviously", "everyone knows", "always", "never",
    "best", "optimal", "definitively", "certain", "confirmed",
    "the answer is", "clearly shows",
)
REQUIRED_HEDGES = ("current evidence suggests", "conflicting evidence",
                   "limited evidence", "insufficient evidence",
                   "no source addresses")


class ResearchError(ValueError):
    """A research contract, wall, or pre-registration violation."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scan_banned_language(text: str) -> list:
    # The word-boundary + phrase matcher lives once in the kernel (T022);
    # research keeps its own banned-term vocabulary and passes it in.
    return _kernel_scan(text, BANNED_RESEARCH_LANGUAGE)


def assert_research_language(text: str, *, where: str = "text") -> None:
    hits = scan_banned_language(text)
    if hits:
        raise ResearchError(
            f"{where} overclaims: {hits} — research states what current "
            "evidence suggests, never what is proven")


def json_normalize(payload: dict) -> dict:
    try:
        return json.loads(json.dumps(payload, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ResearchError(f"payload is not JSON-safe: {exc}") from exc


@dataclass(frozen=True)
class ResearchEvent:
    event_type: str
    request_id: str
    actor_type: str
    actor_id: str
    source: str
    research_event_id: str = field(default_factory=new_ulid)
    plan_version: int | None = None
    session_id: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    decision_id: str | None = None
    campaign_id: str | None = None
    experiment_id: str | None = None
    knowledge_id: str | None = None
    company_event_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = RESEARCH_SCHEMA_VERSION
    provenance: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in RESEARCH_EVENT_TYPES:
            raise ResearchError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.research_event_id):
            raise ResearchError("research_event_id must be a ULID")
        if not is_ulid(self.request_id):
            raise ResearchError("request_id must be a ULID")
        if self.actor_type not in ACTOR_TYPES:
            raise ResearchError(f"unknown actor_type: {self.actor_type!r}")
        for name in ("actor_id", "source", "occurred_at", "recorded_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ResearchError(f"{name} must be a non-empty string")
        if self.plan_version is not None and (
                not isinstance(self.plan_version, int) or self.plan_version < 1):
            raise ResearchError("plan_version must be an int >= 1")
        for name in ("payload", "provenance"):
            value = getattr(self, name)
            if not isinstance(value, dict):
                raise ResearchError(f"{name} must be a dict")
            try:
                if json.loads(json.dumps(value)) != value:
                    raise ResearchError(f"{name} does not survive JSON round-trip")
            except (TypeError, ValueError) as exc:
                raise ResearchError(f"{name} not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "ResearchEvent":
        data = json.loads(line)
        v = data.get("schema_version")
        if isinstance(v, int) and v > RESEARCH_SCHEMA_VERSION:
            raise ResearchError(
                f"row {data.get('research_event_id')} schema v{v} > supported "
                f"v{RESEARCH_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("research_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)

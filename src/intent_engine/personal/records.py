"""The canonical Personal AI Workspace contract (T023).

The workspace is a **conductor, not an analyst**. It owns conversation,
memory, and orchestration, and **zero business intelligence**. Every fact
it presents came from an existing agent; it never computes a score, a
readiness, a conflict, a stance, or a metric. This module defines the
shapes that make that discipline structural.

The load-bearing contract is provenance. A workspace answer cites source
ARTIFACTS, not merely source agents — "Research" is too broad to trust;
"research conclusion CON-123 at replay R-42, as of 2026-06-30, STALE" is
trustworthy. Two dataclasses carry that:

    SourceRef     one artifact in one subsystem, with its replay handle,
                  snapshot/index version, as_of, freshness, and lineage
    SourceClaim   one claim the workspace presents, its SourceRefs, its
                  availability (SUPPORTED / CONFLICTED / UNAVAILABLE / …),
                  and how the workspace transformed the source (direct /
                  grouped / summarized) — never "derived", because the
                  workspace derives nothing

Built on the AgentOS kernel (T022): the event subclasses nothing but
reuses the kernel's language wall and JSON discipline, and the store
subclasses `AppendOnlyStore`.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.agentos.language_wall import scan_banned_language
from intent_engine.core.decision_ids import is_ulid, new_ulid

PERSONAL_SCHEMA_VERSION = 1

# =============================================================================
# Contract versions — captured in every snapshot so replay is reproducible
# =============================================================================
SOURCE_CONTRACT_VERSION = "personal_source.v1"
ROUTING_CONTRACT_VERSION = "personal_routing.v1"
BRIEF_TEMPLATE_VERSION = "personal_brief.v1"
REPORT_TEMPLATE_VERSION = "personal_report.v1"

# =============================================================================
# Taxonomy
# =============================================================================
SESSION_EVENTS = {"personal.session_opened", "personal.session_closed",
                  "personal.turn_recorded"}
MEMORY_EVENTS = {"personal.memory_pinned", "personal.goal_saved",
                 "personal.investigation_opened", "personal.investigation_closed",
                 "personal.preference_saved", "personal.memory_candidate_proposed"}
ARTIFACT_EVENTS = {"personal.brief_assembled", "personal.report_drafted"}
MODEL_EVENTS = {"personal.narrative_rejected", "personal.narrative_failed"}
SNAPSHOT_EVENTS = {"personal.snapshot_captured"}

PERSONAL_EVENT_TYPES = (SESSION_EVENTS | MEMORY_EVENTS | ARTIFACT_EVENTS
                        | MODEL_EVENTS | SNAPSHOT_EVENTS)

# Durable memory is created only by an explicit founder act. A conversation
# turn is NOT durable memory merely because it was said.
FOUNDER_ONLY_EVENTS = {"personal.memory_pinned", "personal.goal_saved",
                       "personal.investigation_opened",
                       "personal.investigation_closed",
                       "personal.preference_saved"}

ACTOR_TYPES = {"human", "agent", "system"}
SOURCES = {"cli", "api", "system", "workspace"}

# =============================================================================
# The three memory classes — distinct lifecycles, never conflated
# =============================================================================
MEMORY_EPHEMERAL = "ephemeral_session"     # the current conversation window
MEMORY_DURABLE = "durable_founder"         # goals, pins, investigations
MEMORY_ARTIFACT = "generated_artifact"     # briefs, report drafts
MEMORY_CLASSES = {MEMORY_EPHEMERAL, MEMORY_DURABLE, MEMORY_ARTIFACT}

# =============================================================================
# Field privacy classification
# =============================================================================
FIELD_REFERENCE = "reference"              # a pointer into a subsystem
FIELD_FOUNDER_AUTHORED = "founder_authored"  # the founder's own words
FIELD_GENERATED = "generated_narrative"    # model-drafted prose
FIELD_PROHIBITED = "sensitive_secret_prohibited"  # must never be stored
PRIVACY_CLASSES = {FIELD_REFERENCE, FIELD_FOUNDER_AUTHORED, FIELD_GENERATED,
                   FIELD_PROHIBITED}

# Patterns that must never reach the workspace store. Not a security
# system — a guard against creating a sensitive dumping ground.
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),                 # api keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                    # aws
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),                # github token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),      # private key
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b"),        # bearer token
    re.compile(r"\bpassword\s*[:=]\s*\S+", re.IGNORECASE),  # inline password
)

# =============================================================================
# Freshness — a perfectly cited but old claim is still dangerous
# =============================================================================
FRESH_CURRENT = "CURRENT"
FRESH_STALE = "STALE"
FRESH_HISTORICAL = "HISTORICAL"
FRESH_UNKNOWN = "UNKNOWN"
FRESHNESS_STATES = {FRESH_CURRENT, FRESH_STALE, FRESH_HISTORICAL,
                    FRESH_UNKNOWN}
DEFAULT_STALE_AFTER_DAYS = 90

# =============================================================================
# Availability / disagreement — never collapse to available/unavailable
# =============================================================================
AVAIL_SUPPORTED = "SUPPORTED"
AVAIL_PARTIAL = "PARTIALLY_SUPPORTED"
AVAIL_CONFLICTED = "CONFLICTED"
AVAIL_STALE = "STALE"
AVAIL_UNAVAILABLE = "UNAVAILABLE"
AVAIL_OUT_OF_SCOPE = "OUT_OF_SCOPE"
AVAILABILITY_STATES = {AVAIL_SUPPORTED, AVAIL_PARTIAL, AVAIL_CONFLICTED,
                       AVAIL_STALE, AVAIL_UNAVAILABLE, AVAIL_OUT_OF_SCOPE}

# How the workspace transformed the source. Deliberately excludes any word
# implying the workspace produced intelligence.
TRANSFORM_DIRECT = "direct"
TRANSFORM_GROUPED = "grouped"
TRANSFORM_SUMMARIZED = "summarized"
TRANSFORMATIONS = {TRANSFORM_DIRECT, TRANSFORM_GROUPED, TRANSFORM_SUMMARIZED}

# =============================================================================
# Language wall — the workspace speaks in the same honest register
# =============================================================================
BANNED_WORKSPACE_LANGUAGE = (
    "must", "best", "optimal", "obviously", "clearly", "guaranteed",
    "proven", "always", "never", "should definitely", "the right approach",
)
# Imperative verbs an investigation candidate may not use — an
# investigation is a thing to look into, not an instruction to act.
BANNED_INVESTIGATION_VERBS = ("conduct", "launch", "change", "ship", "execute",
                              "deploy", "roll out", "publish", "send")


class PersonalError(ValueError):
    """A workspace contract, wall, or provenance violation."""


class SecretRejected(PersonalError):
    """Content carrying a credential/secret was refused before storage."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def assert_workspace_language(text: str, *, where: str = "text") -> None:
    hits = scan_banned_language(text, BANNED_WORKSPACE_LANGUAGE)
    if hits:
        raise PersonalError(
            f"{where} overclaims: {hits} — the workspace presents what the "
            "agents report, in their register, and adds no certainty of its "
            "own")


def assert_no_secret(text: str, *, where: str = "text") -> None:
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text or ""):
            raise SecretRejected(
                f"{where} contains what looks like a credential or secret — "
                "the workspace refuses to store it; keep secrets in the "
                "environment, never in the founder log")


def json_normalize(payload: dict) -> dict:
    try:
        return json.loads(json.dumps(payload, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise PersonalError(f"payload is not JSON-safe: {exc}") from exc


# =============================================================================
# The provenance contract
# =============================================================================
@dataclass(frozen=True)
class SourceRef:
    """One artifact in one subsystem, with everything needed to reproduce
    it. This is what makes a workspace answer trustworthy: not "Research
    said so" but "research conclusion CON-123, replay R-42, as of
    2026-06-30, index evidence_index.v1"."""
    subsystem: str                 # "research" | "product" | "executive" | …
    artifact_type: str             # "conclusion" | "decision_package" | …
    artifact_id: str
    replay_id: str                 # the handle that reproduces it
    as_of: str                     # the session as_of this was read at
    snapshot_version: str | None = None
    observed_at: str | None = None  # when the underlying fact was observed
    freshness_status: str = FRESH_UNKNOWN
    lineage_ref: str | None = None  # a deeper lineage handle if the agent has one

    def validate(self) -> None:
        if not self.subsystem or not self.artifact_type or not self.artifact_id:
            raise PersonalError("a SourceRef names a subsystem, an artifact "
                                "type, and an artifact id")
        if not self.replay_id:
            raise PersonalError("a SourceRef carries a replay id")
        if self.freshness_status not in FRESHNESS_STATES:
            raise PersonalError(f"unknown freshness_status: "
                                f"{self.freshness_status!r}")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SourceClaim:
    """One claim the workspace presents. It cites artifacts (>= 1
    SourceRef) unless it is honestly UNAVAILABLE / OUT_OF_SCOPE. The
    workspace never authors the fact — it composes and, at most,
    summarizes."""
    claim_id: str
    text: str
    availability: str
    source_refs: tuple = ()
    confidence: dict | None = None      # a confidence VIEW read from an agent
    transformation: str = TRANSFORM_DIRECT
    freshness_status: str = FRESH_UNKNOWN

    def validate(self) -> None:
        if self.availability not in AVAILABILITY_STATES:
            raise PersonalError(f"unknown availability: {self.availability!r}")
        if self.transformation not in TRANSFORMATIONS:
            raise PersonalError(f"unknown transformation: "
                                f"{self.transformation!r}")
        assert_workspace_language(self.text, where="claim text")
        present = self.availability in (AVAIL_SUPPORTED, AVAIL_PARTIAL,
                                        AVAIL_CONFLICTED, AVAIL_STALE)
        if present and not self.source_refs:
            raise PersonalError(
                f"a {self.availability} claim cites at least one source "
                "artifact — a claim the workspace cannot attribute to an "
                "agent is not produced")
        for ref in self.source_refs:
            ref.validate()

    def as_dict(self) -> dict:
        return {"claim_id": self.claim_id, "text": self.text,
                "availability": self.availability,
                "transformation": self.transformation,
                "freshness_status": self.freshness_status,
                "confidence": self.confidence,
                "source_refs": [r.as_dict() for r in self.source_refs]}


def freshness_of(observed_at: str | None, as_of: str, *,
                 stale_after_days: int = DEFAULT_STALE_AFTER_DAYS) -> str:
    """Derive freshness from whatever timestamp the source exposed. With no
    timestamp it is UNKNOWN — never CURRENT (see dependency gap 3)."""
    if not observed_at:
        return FRESH_UNKNOWN
    try:
        age_days = (datetime.fromisoformat(as_of)
                    - datetime.fromisoformat(observed_at)).total_seconds() / 86400.0
    except (TypeError, ValueError):
        return FRESH_UNKNOWN
    if age_days < 0:
        return FRESH_UNKNOWN
    if age_days <= stale_after_days:
        return FRESH_CURRENT
    if age_days <= stale_after_days * 4:
        return FRESH_STALE
    return FRESH_HISTORICAL


@dataclass(frozen=True)
class PersonalEvent:
    event_type: str
    actor_type: str
    actor_id: str
    source: str
    personal_event_id: str = field(default_factory=new_ulid)
    session_id: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    memory_class: str | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = PERSONAL_SCHEMA_VERSION
    provenance: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in PERSONAL_EVENT_TYPES:
            raise PersonalError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.personal_event_id):
            raise PersonalError("personal_event_id must be a ULID")
        if self.actor_type not in ACTOR_TYPES:
            raise PersonalError(f"unknown actor_type: {self.actor_type!r}")
        if self.source not in SOURCES:
            raise PersonalError(f"unknown source: {self.source!r}")
        if self.memory_class is not None and self.memory_class not in MEMORY_CLASSES:
            raise PersonalError(f"unknown memory_class: {self.memory_class!r}")
        # Durable memory is a founder act — never a system/agent one.
        if self.event_type in FOUNDER_ONLY_EVENTS and self.actor_type != "human":
            raise PersonalError(
                f"{self.event_type} is durable founder memory; only a person "
                "creates it — the workspace may propose a candidate, not "
                "silently promote one")
        for name in ("actor_id", "occurred_at", "recorded_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise PersonalError(f"{name} must be a non-empty string")
        for name in ("payload", "provenance"):
            value = getattr(self, name)
            if not isinstance(value, dict):
                raise PersonalError(f"{name} must be a dict")
            try:
                if json.loads(json.dumps(value)) != value:
                    raise PersonalError(f"{name} is not JSON round-trip safe")
            except (TypeError, ValueError) as exc:
                raise PersonalError(f"{name} is not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "PersonalEvent":
        data = json.loads(line)
        version = data.get("schema_version")
        if isinstance(version, int) and version > PERSONAL_SCHEMA_VERSION:
            raise PersonalError(
                f"row {data.get('personal_event_id')} is schema v{version} > "
                f"supported v{PERSONAL_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("personal_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)

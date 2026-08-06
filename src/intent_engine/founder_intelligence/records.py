"""The canonical Founder Intelligence Experience contract (T023.5).

T023.5 is the first public-facing, sellable product: a founder enters a
company name + website and receives an evidence-backed executive
experience that must earn trust in one order — prove knowledge, then
reveal perspective, then invite investigation, then converse.

This module holds the contracts that make that discipline structural:

    CompanyInput          what the founder supplies + consent
    CompanyIdentity       the normalized, evidence-backed company identity
    IntelligenceRun       the append-only, replayable analysis run
    IntelligenceSection   one section of the trust-sequenced result
    InsightCard           one supported observation (never an invented one)
    EvidenceView          the expandable provenance behind a claim
    RunStatus             the deterministic lifecycle states

Everything composes the T023 provenance contract (`SourceRef` /
`SourceClaim`); nothing here computes business intelligence, and no leaf
exists without a supported claim. Built on the AgentOS kernel: the event
reuses the kernel language wall + JSON discipline, and the store subclasses
`AppendOnlyStore`.

Two safety walls live here because the public surface must never become a
secret-ingestion or SSRF vector:

    assert_no_secret        credentials/tokens are refused before storage
    validate_public_url     rejects non-HTTP, localhost, loopback,
                            link-local, and private/internal targets
"""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from intent_engine.agentos.language_wall import scan_banned_language
from intent_engine.core.decision_ids import is_ulid, new_ulid
# The provenance contract is T023's, reused unchanged.
from intent_engine.personal.records import (  # noqa: F401
    AVAIL_CONFLICTED, AVAIL_OUT_OF_SCOPE, AVAIL_PARTIAL, AVAIL_STALE,
    AVAIL_SUPPORTED, AVAIL_UNAVAILABLE, AVAILABILITY_STATES, FRESH_CURRENT,
    FRESH_HISTORICAL, FRESH_STALE, FRESH_UNKNOWN, FRESHNESS_STATES,
    SourceClaim, SourceRef, freshness_of,
)

FOUNDER_INTELLIGENCE_SCHEMA_VERSION = 1
FOUNDER_INTELLIGENCE_CONTRACT_VERSION = "founder_intelligence.v1"
CONSENT_VERSION = "founder_consent.v1"

# =============================================================================
# Run lifecycle — deterministic, append-only, replayable, idempotent
# =============================================================================
CREATED = "CREATED"
VALIDATING = "VALIDATING"
IDENTITY_RESOLVED = "IDENTITY_RESOLVED"
INGESTING = "INGESTING_APPROVED_INPUTS"
ANALYZING = "ANALYZING"
ASSEMBLING = "ASSEMBLING"
COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
REJECTED = "REJECTED"
RUN_STATES = (CREATED, VALIDATING, IDENTITY_RESOLVED, INGESTING, ANALYZING,
              ASSEMBLING, COMPLETE, PARTIAL, FAILED, REJECTED)
TERMINAL_STATES = {COMPLETE, PARTIAL, FAILED, REJECTED}
# The only legal forward transitions. A retry lands on the same state
# rather than advancing twice.
_ALLOWED = {
    CREATED: {VALIDATING, REJECTED},
    VALIDATING: {IDENTITY_RESOLVED, REJECTED, FAILED},
    IDENTITY_RESOLVED: {INGESTING, REJECTED, FAILED},
    INGESTING: {ANALYZING, PARTIAL, FAILED},
    ANALYZING: {ASSEMBLING, PARTIAL, FAILED},
    ASSEMBLING: {COMPLETE, PARTIAL, FAILED},
}


def transition_allowed(current: str, nxt: str) -> bool:
    return nxt in _ALLOWED.get(current, set())


# =============================================================================
# Identity confidence + section kinds
# =============================================================================
IDENTITY_HIGH = "High"
IDENTITY_MODERATE = "Moderate"
IDENTITY_LOW = "Low"
IDENTITY_UNRESOLVED = "Unresolved"
IDENTITY_MISMATCH = "Mismatch"
IDENTITY_CONFIDENCES = {IDENTITY_HIGH, IDENTITY_MODERATE, IDENTITY_LOW,
                        IDENTITY_UNRESOLVED, IDENTITY_MISMATCH}

# The trust sequence — the ONLY legal ordering of a completed result.
SECTION_UNDERSTANDING = "company_understanding"
SECTION_ANALYTICS = "evidence_and_analytics"
SECTION_STOOD_OUT = "what_stood_out"
SECTION_MARKET_VIEW = "market_view"
SECTION_BLIND_SPOTS = "possible_blind_spots"
SECTION_ASSUMPTIONS = "assumptions_to_investigate"
SECTION_ATTENTION = "executive_attention"
SECTION_CONFIDENCE = "executive_confidence"
SECTION_DONT_BELIEVE = "what_we_do_not_believe_yet"
SECTION_QUESTIONS = "leadership_questions"
SECTION_COMPETITORS = "competitors"
SECTION_OPPORTUNITIES = "opportunities"
SECTION_CONVERSATION = "conversation"
TRUST_SEQUENCE = (
    SECTION_UNDERSTANDING, SECTION_ANALYTICS, SECTION_STOOD_OUT,
    SECTION_MARKET_VIEW, SECTION_BLIND_SPOTS, SECTION_ASSUMPTIONS,
    SECTION_ATTENTION, SECTION_CONFIDENCE, SECTION_DONT_BELIEVE,
    SECTION_QUESTIONS, SECTION_COMPETITORS, SECTION_OPPORTUNITIES,
    SECTION_CONVERSATION,
)
# Sections that must never precede Proof of Understanding.
_PERSPECTIVE_SECTIONS = {SECTION_STOOD_OUT, SECTION_BLIND_SPOTS,
                         SECTION_ASSUMPTIONS, SECTION_ATTENTION}

# Opportunity honesty — three distinct states, never collapsed.
OPP_OBSERVED = "observed_opportunity"
OPP_HYPOTHESIS = "opportunity_hypothesis"
OPP_DECISION_READY = "decision_ready_proposal"
OPPORTUNITY_STATES = {OPP_OBSERVED, OPP_HYPOTHESIS, OPP_DECISION_READY}

# =============================================================================
# Events
# =============================================================================
RUN_EVENTS = {"fi.run_created", "fi.run_transitioned", "fi.identity_resolved",
              "fi.source_ingested", "fi.section_assembled", "fi.run_completed",
              "fi.run_rejected", "fi.run_failed", "fi.snapshot_captured",
              "fi.feedback_recorded", "fi.telemetry_event",
              "fi.narrative_rejected"}
ACTOR_TYPES = {"human", "agent", "system"}
SOURCES = {"cli", "api", "web", "system", "intake"}

# =============================================================================
# Supportive language wall — the product supports leadership, never commands
# =============================================================================
# Banned: unsupported imperatives + insults + false certainty. Word-boundary
# matched via the kernel; phrases match literally.
BANNED_PRODUCT_LANGUAGE = (
    "you must", "you should immediately", "is failing", "is broken",
    "strategy is wrong", "obviously", "guaranteed", "definitely",
    "fire ", "you are failing", "you are doing this wrong", "must fix",
)
# Preferred formulations are documented in the brief; the wall only rejects.
CERTAINTY_MARKERS = ("guaranteed", "definitely", "certainly", "no doubt",
                     "without question")

# Fields whose value is model-drafted prose vs a directly-observed fact vs
# an agent conclusion vs a question — surfaced so the UI never hides a
# summary behind the appearance of a raw fact.
TRANSFORM_DIRECTLY_OBSERVED = "directly_observed"
TRANSFORM_AGENT_CONCLUSION = "agent_conclusion"
TRANSFORM_WORKSPACE_SUMMARY = "workspace_summary"
TRANSFORM_QUESTION = "question_from_evidence"
DISPLAY_TRANSFORMS = {TRANSFORM_DIRECTLY_OBSERVED, TRANSFORM_AGENT_CONCLUSION,
                      TRANSFORM_WORKSPACE_SUMMARY, TRANSFORM_QUESTION}

# Secrets that must never reach the store (reused shape from T023, widened).
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
    re.compile(r"\bpassword\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bAuthorization:\s*\S+", re.IGNORECASE),
)

#: Candidate card numbers: 13-16 digits, optionally spaced or hyphenated the
#: way they are printed. Checked against Luhn before it counts — see below.
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def _luhn_ok(digits: str) -> bool:
    """The checksum every real payment card number satisfies."""
    total, double = 0, False
    for char in reversed(digits):
        value = int(char)
        if double:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        double = not double
    return total % 10 == 0


def _looks_like_card_number(text: str) -> bool:
    """A digit run that is actually shaped like a payment card number.

    The pattern alone is 13-16 digits with optional spaces or hyphens, and
    public documents are full of that shape. Measured live: a Datadog 8-K
    prints its commission file number beside its IRS employer number on the
    cover page — "001-39051 27-2825503" — and the whole filing was refused as
    a credential, so a real disclosure was dropped from a real analysis.

    Luhn is the difference between the shape and the thing. Every issued card
    number satisfies it; an arbitrary digit run satisfies it about one time in
    ten, and the concatenation above does not. This narrows FALSE positives
    only: nothing that was detected before stops being detected.
    """
    for match in _CARD_CANDIDATE.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 16 and _luhn_ok(digits):
            return True
    return False


class FounderIntelligenceError(ValueError):
    """A T023.5 contract, wall, security, or lifecycle violation."""


class SecretRejected(FounderIntelligenceError):
    """Content carrying a credential/secret was refused before storage."""


class UnsafeURLRejected(FounderIntelligenceError):
    """A URL failed the SSRF-safety check before any retrieval."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def assert_product_language(text: str, *, where: str = "text") -> None:
    hits = scan_banned_language(text, BANNED_PRODUCT_LANGUAGE)
    if hits:
        raise FounderIntelligenceError(
            f"{where} uses unsupported imperative or insulting language "
            f"{hits} — the product supports leadership and states what "
            "public evidence suggests, never a command or a verdict on the "
            "company")


def assert_no_certainty(text: str, availability: str, *,
                        where: str = "text") -> None:
    if availability in (AVAIL_SUPPORTED,):
        return
    hits = sorted({m for m in CERTAINTY_MARKERS
                   if re.search(rf"\b{re.escape(m)}\b", (text or "").lower())})
    if hits:
        raise FounderIntelligenceError(
            f"{where} uses certainty language {hits} while the evidence is "
            f"{availability} — uncertainty travels with the claim")


def assert_no_secret(text: str, *, where: str = "text") -> None:
    if any(pattern.search(text or "") for pattern in _SECRET_PATTERNS) or \
            _looks_like_card_number(text):
        raise SecretRejected(
            f"{where} contains what looks like a credential or sensitive "
            "identifier — the public experience refuses to store it")


def validate_public_url(url: str) -> str:
    """Reject non-HTTP schemes, localhost, loopback, link-local, and
    private/internal IP targets before any retrieval. Prevents SSRF."""
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLRejected("a company website URL is required")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLRejected(
            f"only http/https URLs are analyzed, not {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        raise UnsafeURLRejected(f"malformed or missing domain: {host!r}")
    if host in ("localhost", "localhost.localdomain"):
        raise UnsafeURLRejected("localhost is not an external company site")
    # if the host is a literal IP, it must be public
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local
                           or ip.is_reserved or ip.is_multicast
                           or ip.is_unspecified):
        raise UnsafeURLRejected(
            f"{host} is an internal / non-public address — refused to "
            "prevent SSRF")
    return url.strip()


def canonical_domain(url_or_domain: str) -> str:
    """Deterministic canonical domain: lowercase host, strip www., no port."""
    text = (url_or_domain or "").strip().lower()
    if "//" not in text:
        text = "https://" + text
    host = (urlparse(text).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def json_normalize(payload: dict) -> dict:
    try:
        return json.loads(json.dumps(payload, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise FounderIntelligenceError(f"payload not JSON-safe: {exc}") from exc


# =============================================================================
# The public-run contracts
# =============================================================================
@dataclass(frozen=True)
class CompanyInput:
    company_name: str
    website: str
    requester_role: str | None = None
    business_question: str | None = None
    approved_inputs: tuple = ()
    consent_version: str = CONSENT_VERSION

    def validate(self) -> None:
        if not str(self.company_name or "").strip():
            raise FounderIntelligenceError("a company name is required")
        validate_public_url(self.website)          # SSRF wall
        for text in (self.company_name, self.requester_role or "",
                     self.business_question or ""):
            assert_no_secret(text, where="company input")
        if self.consent_version != CONSENT_VERSION:
            raise FounderIntelligenceError(
                "the founder must approve the current consent version before "
                "analysis")

    def as_dict(self) -> dict:
        return {"company_name": self.company_name.strip(),
                "website": self.website.strip(),
                "canonical_domain": canonical_domain(self.website),
                "requester_role": self.requester_role,
                "business_question": self.business_question,
                "approved_inputs": list(self.approved_inputs),
                "consent_version": self.consent_version}


@dataclass(frozen=True)
class CompanyIdentity:
    normalized_name: str
    canonical_domain: str
    identity_confidence: str
    identity_evidence: tuple = ()

    def validate(self) -> None:
        if self.identity_confidence not in IDENTITY_CONFIDENCES:
            raise FounderIntelligenceError(
                f"unknown identity confidence: {self.identity_confidence!r}")
        for ref in self.identity_evidence:
            ref.validate()

    def as_dict(self) -> dict:
        return {"normalized_name": self.normalized_name,
                "canonical_domain": self.canonical_domain,
                "identity_confidence": self.identity_confidence,
                "identity_evidence": [r.as_dict()
                                      for r in self.identity_evidence]}


@dataclass(frozen=True)
class InsightCard:
    """One supported observation. Never an invented one: a card without a
    supporting SourceClaim is rejected, and a card that reveals a
    perspective carries its alternative explanation and a question."""
    insight_id: str
    kind: str                       # a SECTION_* the card belongs to
    headline: str
    availability: str
    claims: tuple = ()              # tuple[SourceClaim]
    confidence: str | None = None
    why_it_matters: str = ""
    alternative_explanation: str = ""
    what_would_change_the_view: str = ""
    question_to_investigate: str = ""

    def validate(self) -> None:
        if self.availability not in AVAILABILITY_STATES:
            raise FounderIntelligenceError(
                f"unknown availability: {self.availability!r}")
        assert_product_language(self.headline, where="insight headline")
        assert_no_certainty(self.headline, self.availability,
                            where="insight headline")
        present = self.availability in (AVAIL_SUPPORTED, AVAIL_PARTIAL,
                                        AVAIL_CONFLICTED, AVAIL_STALE)
        if present and not self.claims:
            raise FounderIntelligenceError(
                f"a {self.availability} insight cites at least one supported "
                "claim — an insight the product cannot attribute is not "
                "produced")
        for claim in self.claims:
            claim.validate()
        # a perspective card must carry an alternative explanation + a
        # question — it is an observation to investigate, not a verdict
        if self.kind in _PERSPECTIVE_SECTIONS and present:
            if not self.alternative_explanation.strip():
                raise FounderIntelligenceError(
                    f"a {self.kind} insight states an alternative explanation "
                    "— it is a possible interpretation, not a verdict")
            if not self.question_to_investigate.strip():
                raise FounderIntelligenceError(
                    f"a {self.kind} insight states a question to investigate")

    def as_dict(self) -> dict:
        return {"insight_id": self.insight_id, "kind": self.kind,
                "headline": self.headline, "availability": self.availability,
                "confidence": self.confidence,
                "why_it_matters": self.why_it_matters,
                "alternative_explanation": self.alternative_explanation,
                "what_would_change_the_view": self.what_would_change_the_view,
                "question_to_investigate": self.question_to_investigate,
                "claims": [c.as_dict() for c in self.claims]}


@dataclass(frozen=True)
class IntelligenceSection:
    kind: str
    title: str
    cards: tuple = ()
    availability: str = AVAIL_SUPPORTED
    limitations: tuple = ()
    note: str = ""

    def validate(self) -> None:
        if self.kind not in TRUST_SEQUENCE:
            raise FounderIntelligenceError(f"unknown section kind: "
                                           f"{self.kind!r}")
        for card in self.cards:
            card.validate()

    def as_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title,
                "availability": self.availability,
                "limitations": list(self.limitations), "note": self.note,
                "cards": [c.as_dict() for c in self.cards]}


def assert_trust_sequence(sections) -> None:
    """The completed result must follow the trust sequence exactly — no
    perspective section may precede Proof of Understanding."""
    kinds = [s.kind for s in sections]
    order = {k: i for i, k in enumerate(TRUST_SEQUENCE)}
    positions = [order[k] for k in kinds if k in order]
    if positions != sorted(positions):
        raise FounderIntelligenceError(
            "sections are out of the trust sequence — prove understanding "
            "before revealing perspective")
    if SECTION_UNDERSTANDING in kinds:
        u = kinds.index(SECTION_UNDERSTANDING)
        for perspective in _PERSPECTIVE_SECTIONS:
            if perspective in kinds and kinds.index(perspective) < u:
                raise FounderIntelligenceError(
                    f"{perspective} appears before company understanding — "
                    "the product must prove it knows the company first")


@dataclass(frozen=True)
class FounderIntelligenceEvent:
    event_type: str
    actor_type: str
    actor_id: str
    source: str
    fi_event_id: str = field(default_factory=new_ulid)
    run_id: str | None = None
    company_domain: str | None = None       # scopes every row to a company
    subject_type: str | None = None
    subject_id: str | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = FOUNDER_INTELLIGENCE_SCHEMA_VERSION
    provenance: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in RUN_EVENTS:
            raise FounderIntelligenceError(f"unknown event_type: "
                                           f"{self.event_type!r}")
        if not is_ulid(self.fi_event_id):
            raise FounderIntelligenceError("fi_event_id must be a ULID")
        if self.actor_type not in ACTOR_TYPES:
            raise FounderIntelligenceError(f"unknown actor_type: "
                                           f"{self.actor_type!r}")
        if self.source not in SOURCES:
            raise FounderIntelligenceError(f"unknown source: {self.source!r}")
        for name in ("actor_id", "occurred_at", "recorded_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise FounderIntelligenceError(f"{name} must be non-empty")
        for name in ("payload", "provenance"):
            value = getattr(self, name)
            if not isinstance(value, dict):
                raise FounderIntelligenceError(f"{name} must be a dict")
            try:
                if json.loads(json.dumps(value)) != value:
                    raise FounderIntelligenceError(f"{name} not round-trip safe")
            except (TypeError, ValueError) as exc:
                raise FounderIntelligenceError(f"{name} not JSON-safe: "
                                               f"{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "FounderIntelligenceEvent":
        data = json.loads(line)
        version = data.get("schema_version")
        if isinstance(version, int) and version > FOUNDER_INTELLIGENCE_SCHEMA_VERSION:
            raise FounderIntelligenceError(
                f"row {data.get('fi_event_id')} is schema v{version} > "
                f"supported v{FOUNDER_INTELLIGENCE_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("fi_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)

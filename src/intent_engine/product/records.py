"""The canonical product contract (T020): envelope, taxonomy, vocabularies.

This subsystem owns PROPOSALS, not decisions. The founder accepts,
rejects, merges, defers, withdraws, or supersedes; the agent produces
reviewable artifacts and stops there.

Five separated layers, deliberately not collapsed:

    Problem  ->  Opportunity  ->  Proposal  ->  Spec Draft  ->  Founder Review

`problems.py` and `index.py` keep Problem and Opportunity apart because
one problem routinely carries several competing opportunities, and
collapsing them destroys that fan-out. `proposals.py` and `specs.py` keep
Solution and Spec apart for the same reason.

Determinism boundary (load-bearing, see scoring.py and service.py):
    deterministic  problem dedup, problem/opportunity indexing, every
                   score, evidence-reference resolution, coverage,
                   dependency graph, lifecycle transitions, portfolio
                   rollup, roadmap-diff generation, every wall
    model-assisted problem-statement prose, candidate solution options,
                   spec-draft wording
    a model may NEVER emit an evidence reference, a customer id, a score,
                   a priority, a decision id, or a citation.

Canonical product contract: this file.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.agentos.language_wall import scan_banned_language as _kernel_scan
from intent_engine.agentos.model_boundary import (
    find_forbidden_fields as _kernel_forbidden_fields,
)
from intent_engine.core.decision_ids import is_ulid, new_ulid

PRODUCT_SCHEMA_VERSION = 1

# =============================================================================
# Product principles — the constraints this package exists to make structural
# =============================================================================
PRODUCT_PRINCIPLES = (
    "Every proposal solves one problem.",
    "Every problem has evidence.",
    "Every opportunity is reproducible.",
    "Every proposal is reviewable.",
    "Every score is explainable.",
    "Every roadmap suggestion is non-binding.",
    "Every unknown is explicit.",
    "Every proposal traces to customer impact.",
    "Every portfolio traces to strategic themes.",
    "Nothing executes automatically.",
    "Scores describe proposals; they do not shape them.",
)

# =============================================================================
# Taxonomy
# =============================================================================
PORTFOLIO_EVENTS = {
    "product.portfolio_created", "product.theme_declared",
    "product.initiative_created", "product.alignment_declared",
    "product.balance_target_declared",
}
PROBLEM_EVENTS = {
    "product.problem_recorded", "product.problem_evidence_linked",
    "product.problem_split", "product.problem_merged",
    "product.problem_retired", "product.problem_superseded",
    "product.problem_rejected",
}
OPPORTUNITY_EVENTS = {
    "product.opportunity_registered", "product.opportunity_evidence_linked",
    "product.opportunity_attached", "product.opportunity_superseded",
    "product.opportunity_rejected",
}
INTAKE_EVENTS = {"product.intake_scanned", "product.intake_rejected"}
PROPOSAL_EVENTS = {
    "product.solution_set_opened", "product.proposal_drafted",
    "product.proposal_revised", "product.proposal_edge_recorded",
    "product.proposal_scored", "product.proposal_retired",
    "product.review_requested", "product.reviewed",
    "product.decision_linked", "product.execution_candidate_marked",
    "product.decision_debt_recorded",
}
SPEC_EVENTS = {"product.spec_drafted", "product.spec_revised",
               "product.spec_debt_recorded", "product.spec_rejected"}
BUNDLE_EVENTS = {"product.bundle_assembled"}
ROADMAP_EVENTS = {"product.roadmap_candidate_drafted",
                  "product.roadmap_diff_emitted"}
SNAPSHOT_EVENTS = {"product.portfolio_snapshot", "product.proposal_snapshot"}
MODEL_EVENTS = {"product.draft_rejected", "product.draft_failed"}

PRODUCT_EVENT_TYPES = (PORTFOLIO_EVENTS | PROBLEM_EVENTS | OPPORTUNITY_EVENTS
                       | INTAKE_EVENTS | PROPOSAL_EVENTS | SPEC_EVENTS
                       | BUNDLE_EVENTS | ROADMAP_EVENTS | SNAPSHOT_EVENTS
                       | MODEL_EVENTS)

# Human-only transitions. Strategy, review, and the link to a Decision
# Record are founder acts; the agent drafts and requests.
HUMAN_ONLY_EVENTS = {
    "product.portfolio_created", "product.theme_declared",
    "product.initiative_created", "product.alignment_declared",
    "product.balance_target_declared", "product.reviewed",
    "product.decision_linked", "product.execution_candidate_marked",
    "product.problem_retired", "product.opportunity_rejected",
}

ACTOR_TYPES = {"human", "agent", "system"}
SOURCES = {"cli", "api", "system", "company_event_consumer", "intake",
           "founder_review"}

# =============================================================================
# Problem evolution — problems change, so they are not modelled as static
# =============================================================================
PROBLEM_ACTIVE = "active"
PROBLEM_SPLIT = "split"
PROBLEM_MERGED = "merged"
PROBLEM_RETIRED = "retired"
PROBLEM_SUPERSEDED = "superseded"
PROBLEM_STATES = {PROBLEM_ACTIVE, PROBLEM_SPLIT, PROBLEM_MERGED,
                  PROBLEM_RETIRED, PROBLEM_SUPERSEDED}

# =============================================================================
# Opportunity + proposal lifecycle
# =============================================================================
OPPORTUNITY_CANDIDATE = "candidate"
OPPORTUNITY_INDEXED = "indexed"
OPPORTUNITY_ATTACHED = "attached"
OPPORTUNITY_SUPERSEDED = "superseded"
OPPORTUNITY_REJECTED = "rejected"
OPPORTUNITY_STATES = {OPPORTUNITY_CANDIDATE, OPPORTUNITY_INDEXED,
                      OPPORTUNITY_ATTACHED, OPPORTUNITY_SUPERSEDED,
                      OPPORTUNITY_REJECTED}

STATUS_DRAFTED = "drafted"
STATUS_SCORED = "scored"
STATUS_REVIEW_REQUESTED = "review_requested"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_MERGED_INTO = "merged_into"
STATUS_DEFERRED = "deferred"
STATUS_SUPERSEDED = "superseded"
STATUS_WITHDRAWN = "withdrawn"
STATUS_RETIRED = "retired"
STATUS_EXECUTION_CANDIDATE = "execution_candidate"

# The six real founder answers. `merged_into` and `deferred` are here
# because a system that models only accept/reject distorts the choice the
# founder actually made.
TERMINAL_PROPOSAL_STATUSES = {
    STATUS_ACCEPTED, STATUS_REJECTED, STATUS_MERGED_INTO, STATUS_DEFERRED,
    STATUS_SUPERSEDED, STATUS_WITHDRAWN,
}
# Retirement is separate from rejection: a retired proposal was once sound
# and stopped being so (invalidated / outdated / replaced).
RETIREMENT_REASONS = {"invalidated", "outdated", "replaced"}

PROPOSAL_STATUSES = (TERMINAL_PROPOSAL_STATUSES
                     | {STATUS_DRAFTED, STATUS_SCORED, STATUS_REVIEW_REQUESTED,
                        STATUS_RETIRED, STATUS_EXECUTION_CANDIDATE})

REVIEW_DISPOSITIONS = {STATUS_ACCEPTED, STATUS_REJECTED, STATUS_MERGED_INTO,
                       STATUS_DEFERRED, STATUS_WITHDRAWN}

# =============================================================================
# Graph edges (mirrors the research graph's typed-edge discipline)
# =============================================================================
EDGE_ADDRESSES = "addresses"              # proposal -> problem
EDGE_SUPPORTS = "supports"                # opportunity -> proposal
EDGE_DEPENDS_ON = "depends_on"            # proposal -> proposal
EDGE_BLOCKS = "blocks"                    # proposal -> proposal
EDGE_ALTERNATIVE_TO = "alternative_to"    # proposal -> proposal
EDGE_IMPLEMENTS = "implements"            # proposal -> knowledge mechanism
EDGE_SUPPORTED_BY = "supported_by"        # opportunity -> evidence
EDGE_SUPERSEDES = "supersedes"            # proposal -> proposal
EDGE_ARISES_FROM = "arises_from"          # opportunity -> problem
PROPOSAL_EDGES = {EDGE_ADDRESSES, EDGE_SUPPORTS, EDGE_DEPENDS_ON,
                  EDGE_BLOCKS, EDGE_ALTERNATIVE_TO, EDGE_IMPLEMENTS,
                  EDGE_SUPPORTED_BY, EDGE_SUPERSEDES, EDGE_ARISES_FROM}

# =============================================================================
# Evidence reference kinds — references, not copies. Every one of these
# resolves into a subsystem that already owns the fact.
# =============================================================================
REF_EVIDENCE = "evidence"                 # T019 Evidence Index entry
REF_RESEARCH_CONCLUSION = "research_conclusion"
REF_RESEARCH_DEBT = "research_debt"
REF_EXPERIMENT = "experiment"             # T018 result + label
REF_CRM_FACT = "crm_fact"                 # T014 lifecycle fact
REF_ANALYTICS_METRIC = "analytics_metric"  # T015 MetricResult
REF_KNOWLEDGE = "knowledge_item"          # T016 active knowledge
REF_DECISION = "decision"                 # T010 Decision Record
REFERENCE_KINDS = {REF_EVIDENCE, REF_RESEARCH_CONCLUSION, REF_RESEARCH_DEBT,
                   REF_EXPERIMENT, REF_CRM_FACT, REF_ANALYTICS_METRIC,
                   REF_KNOWLEDGE, REF_DECISION}

# Recorded alongside every alignment declaration so a historical row stays
# readable after the vocabulary evolves.
ALIGNMENT_LEVELS_DOC = (
    "core / adjacent / exploratory, declared by a person; an agent reads "
    "this declaration and does not author one")

# =============================================================================
# Work categories — the axes a portfolio can be out of balance along
# =============================================================================
WORK_CATEGORIES = {"customer_work", "growth_bet", "technical_debt",
                   "research", "speculative", "compliance", "unknown"}

# =============================================================================
# Debt vocabularies
# =============================================================================
# Decision debt: what a proposal is waiting on that only a human resolves.
DECISION_DEBT_KINDS = {
    "waiting_for_experiment", "waiting_for_customer_interview",
    "waiting_for_pricing", "waiting_for_legal", "waiting_for_founder",
    "waiting_for_research", "waiting_for_decision_record",
}
# Spec debt: what a spec draft still lacks before implementation is sane.
SPEC_DEBT_KINDS = {"need_ux", "need_architecture", "need_research",
                   "need_experiment", "need_customer_validation"}

# =============================================================================
# Spec drafts — bounded on purpose
# =============================================================================
SPEC_SECTIONS = ("goals", "non_goals", "requirements", "constraints",
                 "acceptance_criteria", "unknowns", "dependencies", "risks",
                 "open_questions")
# A spec draft that carries any of these is rejected: they are execution
# concerns, and this subsystem has no execution authority.
FORBIDDEN_SPEC_FIELDS = (
    "implementation", "implementation_notes", "file_paths", "files", "code",
    "schema", "schemas", "estimate", "estimates", "effort", "story_points",
    "assignee", "assignees", "owner", "due_date", "dates", "timeline",
    "sprint", "milestone_date", "start_date",
)
# Acceptance criteria that state a feeling rather than an observation.
UNFALSIFIABLE_MARKERS = (
    "works well", "is fast", "is intuitive", "user-friendly", "user friendly",
    "seamless", "easy to use", "performant", "scalable", "robust",
    "high quality", "as expected", "makes sense", "feels", "delightful",
    "polished", "looks good", "is better",
)
# At least one of these makes a criterion checkable by somebody other than
# its author.
CHECKABLE_MARKERS = (
    "returns", "emits", "records", "rejects", "raises", "equals", "contains",
    "exit code", "within", "at least", "at most", "==", "<=", ">=",
    "is present", "is absent", "appears in", "count of", "byte-identical",
    "resolves to", "no more than", "fewer than", "greater than", "matches",
    "logs", "exists", "does not exist", "status is", "is recorded",
)

# =============================================================================
# Language wall
# =============================================================================
# Single words are word-boundary matched ('provenance' is not 'proven');
# phrases match literally. This distinction has cost four sessions.
BANNED_PRODUCT_LANGUAGE = (
    "must", "optimal", "best", "correct", "obviously", "clearly",
    "guaranteed", "proven", "always", "never",
    "should definitely", "the right approach",
)
REQUIRED_PRODUCT_HEDGES = ("current evidence suggests", "candidate",
                           "proposal", "review required",
                           "insufficient evidence", "unknown")
# Certainty phrasing is additionally blocked wherever the underlying
# evidence is one of these.
UNCERTAIN_EVIDENCE_LABELS = {"CONFLICTING", "INSUFFICIENT", "UNKNOWN",
                             "NOT INVESTIGATED"}
CERTAINTY_MARKERS = ("certain", "certainly", "definitely", "no doubt",
                     "beyond question", "settled", "conclusive",
                     "unambiguous", "without question")

# A model may never author any of these. Checked structurally, not trusted.
MODEL_FORBIDDEN_FIELDS = (
    "evidence_references", "affected_customers", "crm_entity_id",
    "crm_entity_ids", "evidence_id", "evidence_ids", "priority",
    "priority_rank", "score", "scores", "opportunity_score", "confidence",
    "decision_id", "citation", "citations", "source_id", "experiment_id",
    "knowledge_id", "cost_of_delay", "strategic_alignment",
)


class ProductError(ValueError):
    """A product contract, wall, or lifecycle violation."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scan_banned_language(text: str) -> list:
    # The matcher lives once in the kernel (T022); product keeps its own
    # banned-term vocabulary and passes it in.
    return _kernel_scan(text, BANNED_PRODUCT_LANGUAGE)


def assert_product_language(text: str, *, where: str = "text") -> None:
    hits = scan_banned_language(text)
    if hits:
        raise ProductError(
            f"{where} overclaims: {hits} — a product artifact states what "
            "current evidence suggests and what review is required, not what "
            "is settled")


def assert_no_certainty(text: str, label: str, *, where: str = "text") -> None:
    """Certainty phrasing is blocked where the underlying evidence cannot
    bear it."""
    if label not in UNCERTAIN_EVIDENCE_LABELS:
        return
    lowered = (text or "").lower()
    hits = sorted({m for m in CERTAINTY_MARKERS
                   if re.search(rf"\b{re.escape(m)}\b", lowered)})
    if hits:
        raise ProductError(
            f"{where} uses certainty language {hits} while the underlying "
            f"evidence is {label} — uncertainty travels with the artifact")


def find_forbidden_fields(value, found=None) -> list:
    """Fields a model or an author may not supply, at any nesting depth.

    The recursive scan lives once in the kernel (T022); product passes its
    own `MODEL_FORBIDDEN_FIELDS` set. Used by both the model boundary and
    the scoring wall, so there is a single implementation of the rule."""
    return _kernel_forbidden_fields(value, MODEL_FORBIDDEN_FIELDS)


def json_normalize(payload: dict) -> dict:
    try:
        return json.loads(json.dumps(payload, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ProductError(f"payload is not JSON-safe: {exc}") from exc


@dataclass(frozen=True)
class ProductEvent:
    event_type: str
    actor_type: str
    actor_id: str
    source: str
    product_event_id: str = field(default_factory=new_ulid)
    portfolio_id: str | None = None
    theme_id: str | None = None
    initiative_id: str | None = None
    problem_id: str | None = None
    opportunity_id: str | None = None
    proposal_id: str | None = None
    spec_id: str | None = None
    bundle_id: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    proposal_version: int | None = None
    spec_version: int | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    decision_id: str | None = None
    experiment_id: str | None = None
    research_request_id: str | None = None
    crm_entity_id: str | None = None
    knowledge_id: str | None = None
    company_event_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = PRODUCT_SCHEMA_VERSION
    provenance: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in PRODUCT_EVENT_TYPES:
            raise ProductError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.product_event_id):
            raise ProductError("product_event_id must be a ULID")
        if self.actor_type not in ACTOR_TYPES:
            raise ProductError(f"unknown actor_type: {self.actor_type!r}")
        if self.source not in SOURCES:
            raise ProductError(f"unknown source: {self.source!r}")
        for name in ("actor_id", "occurred_at", "recorded_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ProductError(f"{name} must be a non-empty string")
        for name in ("proposal_version", "spec_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 1):
                raise ProductError(f"{name} must be an int >= 1")
        for name in ("payload", "provenance"):
            value = getattr(self, name)
            if not isinstance(value, dict):
                raise ProductError(f"{name} must be a dict")
            try:
                if json.loads(json.dumps(value)) != value:
                    raise ProductError(
                        f"{name} does not survive a JSON round-trip")
            except (TypeError, ValueError) as exc:
                raise ProductError(f"{name} is not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "ProductEvent":
        data = json.loads(line)
        version = data.get("schema_version")
        if isinstance(version, int) and version > PRODUCT_SCHEMA_VERSION:
            raise ProductError(
                f"row {data.get('product_event_id')} is schema v{version} > "
                f"supported v{PRODUCT_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("product_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)

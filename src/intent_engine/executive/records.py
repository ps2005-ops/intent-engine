"""The canonical executive contract (T021): envelope, taxonomy, vocabularies.

This subsystem owns exactly one thing: **decision candidates**. It owns no
Decision Record (T010 owns those), no prediction (the ledger owns those),
no proposal (T020), and no metric (T015).

The question it answers is a TRIAGE question — *given everything we know,
what decision deserves the founder's attention next?* — so the primary
artifact is a queue, and a decision package is what opening one yields.

Six separated layers, deliberately not collapsed:

    Candidate -> Context -> Package -> Founder Review -> Decision Record
                                                      -> Outcome
                                                      -> Knowledge

`context.py` sits between candidate and package because a package is a
RENDERING of a context at a version. Keeping them apart is what lets a
later layer answer "why is this in my queue today when it was not
yesterday?" — the context records which load-bearing inputs changed.

Determinism boundary (load-bearing, see readiness.py and service.py):
    deterministic  the Decision Index, every readiness dimension, impact,
                   reversibility aggregation, queue partitioning and
                   ordering, conflict detection and classification,
                   decision-debt derivation, aging, expiry, traceability,
                   portfolio rollup, the health dashboard, every wall
    model-assisted package prose, option descriptions, next-review notes
    a model may NEVER emit a decision id, a prediction id, an evidence
                   reference, a customer id, a score, a readiness value,
                   an impact, a reversibility, a priority, or a citation.

Canonical executive contract: this file.
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

EXECUTIVE_SCHEMA_VERSION = 1

# =============================================================================
# Decision principles — the constraints this package makes structural
# =============================================================================
DECISION_PRINCIPLES = (
    "Every recommendation has alternatives.",
    "Every recommendation exposes disagreement.",
    "Every recommendation is replayable.",
    "Every recommendation is reversibility-aware.",
    "Every recommendation cites evidence.",
    "Every recommendation cites assumptions.",
    "Every recommendation cites uncertainty.",
    "Every recommendation cites its predictions.",
    "Every recommendation is reviewable.",
    "Nothing executes automatically.",
    "Readiness describes decisions; it does not shape them.",
    "Declining to recommend is a legitimate outcome.",
)

# =============================================================================
# Taxonomy
# =============================================================================
CANDIDATE_EVENTS = {
    "executive.candidate_registered", "executive.candidate_linked",
    "executive.candidate_superseded", "executive.candidate_dismissed",
    "executive.intake_scanned", "executive.intake_rejected",
}
CONTEXT_EVENTS = {"executive.context_built", "executive.context_rebuilt"}
CONFLICT_EVENTS = {"executive.conflict_detected"}
DEBT_EVENTS = {"executive.decision_debt_recorded",
               "executive.decision_debt_cleared"}
READINESS_EVENTS = {"executive.readiness_computed"}
PACKAGE_EVENTS = {
    "executive.package_drafted", "executive.package_revised",
    "executive.option_recorded", "executive.no_recommendation_recorded",
    "executive.escalation_assigned", "executive.review_requested",
    "executive.reviewed", "executive.override_recorded",
    "executive.decision_linked", "executive.outcome_observed",
    "executive.knowledge_candidate_requested",
}
GRAPH_EVENTS = {"executive.decision_edge_recorded"}
EXPIRY_EVENTS = {"executive.decision_expired"}
PORTFOLIO_EVENTS = {"executive.alignment_declared",
                    "executive.budget_declared"}
SNAPSHOT_EVENTS = {"executive.snapshot_captured"}
MODEL_EVENTS = {"executive.draft_rejected", "executive.draft_failed"}

EXECUTIVE_EVENT_TYPES = (CANDIDATE_EVENTS | CONTEXT_EVENTS | CONFLICT_EVENTS
                         | DEBT_EVENTS | READINESS_EVENTS | PACKAGE_EVENTS
                         | GRAPH_EVENTS | EXPIRY_EVENTS | PORTFOLIO_EVENTS
                         | SNAPSHOT_EVENTS | MODEL_EVENTS)

# Human-only transitions. Review, override, the link to a Decision Record,
# and every declaration of strategy or money are founder acts.
HUMAN_ONLY_EVENTS = {
    "executive.reviewed", "executive.override_recorded",
    "executive.decision_linked", "executive.alignment_declared",
    "executive.budget_declared", "executive.candidate_dismissed",
}

ACTOR_TYPES = {"human", "agent", "system"}
SOURCES = {"cli", "api", "system", "company_event_consumer", "intake",
           "founder_review"}

# =============================================================================
# Decision horizon — so a bug fix and an acquisition stop competing
# =============================================================================
HORIZON_IMMEDIATE = "immediate"
HORIZON_SHORT = "short_term"
HORIZON_MEDIUM = "medium_term"
HORIZON_LONG = "long_term"
HORIZON_STRATEGIC = "strategic"
DECISION_HORIZONS = (HORIZON_IMMEDIATE, HORIZON_SHORT, HORIZON_MEDIUM,
                     HORIZON_LONG, HORIZON_STRATEGIC)

# =============================================================================
# Decision class
# =============================================================================
DECISION_CLASSES = {"strategic", "operational", "financial", "product",
                    "marketing", "hiring", "technical", "risk", "governance"}

# =============================================================================
# The three queues. One ordering would put a pricing change, a dependency
# bump, and an acquisition in the same list, which is not a ranking anybody
# can act on. Partition first, order within.
# =============================================================================
QUEUE_STRATEGIC = "strategic"
QUEUE_OPERATIONAL = "operational"
QUEUE_MAINTENANCE = "maintenance"
QUEUES = (QUEUE_STRATEGIC, QUEUE_OPERATIONAL, QUEUE_MAINTENANCE)
QUEUE_ASSIGNMENT_VERSION = "queue_assignment.v1"


def assign_queue(horizon: str, decision_class: str) -> tuple[str, str]:
    """Deterministic partition, stated rather than implied.

    Returns (queue, reason). The rule is a table, not a judgment: the same
    (horizon, class) pair always lands in the same queue.
    """
    if horizon in (HORIZON_STRATEGIC, HORIZON_LONG) \
            or decision_class in ("strategic", "governance"):
        return (QUEUE_STRATEGIC,
                f"horizon={horizon}, class={decision_class} — long-range or "
                "governance work is triaged apart from day-to-day work")
    if decision_class == "technical" and horizon in (HORIZON_IMMEDIATE,
                                                     HORIZON_SHORT):
        return (QUEUE_MAINTENANCE,
                f"horizon={horizon}, class=technical — routine upkeep is "
                "triaged apart so it does not compete with product choices")
    return (QUEUE_OPERATIONAL,
            f"horizon={horizon}, class={decision_class} — day-to-day work")


# =============================================================================
# Escalation — deciding WHO should decide, which is a separate question
# from what to recommend. Not every candidate deserves founder attention.
# =============================================================================
ESCALATION_MONITOR = "monitor"
ESCALATION_REVIEW_SCHEDULED = "review_scheduled"
ESCALATION_NEEDS_FOUNDER = "needs_founder"
ESCALATION_NEEDS_BOARD = "needs_board"
ESCALATION_LEVELS = (ESCALATION_MONITOR, ESCALATION_REVIEW_SCHEDULED,
                     ESCALATION_NEEDS_FOUNDER, ESCALATION_NEEDS_BOARD)
ESCALATION_RULE_VERSION = "escalation.v1"
# A stated cadence, not an invented date. Same discipline as T014's
# _HEALTHY_WINDOW_DAYS: a policy constant lives in the contract where it
# can be read, versioned, and argued with.
REVIEW_CADENCE_DAYS = {ESCALATION_MONITOR: 90,
                       ESCALATION_REVIEW_SCHEDULED: 30}

# =============================================================================
# Impact — computed from recorded scope, never asked of a model
# =============================================================================
IMPACT_SMALL = "small"
IMPACT_MEDIUM = "medium"
IMPACT_LARGE = "large"
IMPACT_TRANSFORMATIONAL = "transformational"
IMPACT_LEVELS = (IMPACT_SMALL, IMPACT_MEDIUM, IMPACT_LARGE,
                 IMPACT_TRANSFORMATIONAL)
IMPACT_RULE_VERSION = "decision_impact.v1"

# =============================================================================
# Reversibility — Type 1 / Type 2. DECLARED, never inferred: whether a
# thing can be undone is a judgment about the world, and an agent that
# guesses it wrong guesses in the most expensive direction.
# =============================================================================
REVERSIBILITY_EASY = "easy"
REVERSIBILITY_MODERATE = "moderate"
REVERSIBILITY_HARD = "hard"
REVERSIBILITY_IRREVERSIBLE = "irreversible"
REVERSIBILITY_LEVELS = (REVERSIBILITY_EASY, REVERSIBILITY_MODERATE,
                        REVERSIBILITY_HARD, REVERSIBILITY_IRREVERSIBLE)
# Ordered worst-last, so aggregating a set of options takes the max.
_REVERSIBILITY_ORDER = {level: i for i, level in
                        enumerate(REVERSIBILITY_LEVELS)}


def least_reversible(levels) -> str | None:
    """A candidate is as reversible as its least reversible option. With
    no option declaring one, this is UNKNOWN rather than optimistic."""
    declared = [lvl for lvl in levels if lvl in _REVERSIBILITY_ORDER]
    if not declared:
        return None
    return max(declared, key=lambda lvl: _REVERSIBILITY_ORDER[lvl])


# =============================================================================
# Conflict taxonomy (closed). Averaging a disagreement destroys it, so
# every conflict is typed and stated.
# =============================================================================
CONFLICT_EVIDENCE = "evidence_conflict"
CONFLICT_METRIC = "metric_conflict"
CONFLICT_PRIORITY = "priority_conflict"
CONFLICT_TIMELINE = "timeline_conflict"
CONFLICT_STALENESS = "staleness_conflict"
CONFLICT_STRATEGY = "strategy_conflict"
CONFLICT_DEPENDENCY = "dependency_conflict"
CONFLICT_RESOURCE = "resource_conflict"
CONFLICT_UNKNOWN = "unknown_conflict"
CONFLICT_KINDS = {CONFLICT_EVIDENCE, CONFLICT_METRIC, CONFLICT_PRIORITY,
                  CONFLICT_TIMELINE, CONFLICT_STALENESS, CONFLICT_STRATEGY,
                  CONFLICT_DEPENDENCY, CONFLICT_RESOURCE, CONFLICT_UNKNOWN}
# staleness_conflict is kept apart from timeline_conflict on purpose: two
# inputs that were true at different times and were never reconciled is a
# different problem from two inputs that disagree about scheduling.

# =============================================================================
# Decision debt — the counterpart of research debt (T019) and spec debt
# (T020). What a decision waits on that only a person resolves.
# =============================================================================
DECISION_DEBT_KINDS = {
    "need_founder_choice", "need_legal_review", "need_pricing",
    "need_experiment", "need_customer_validation", "need_research",
    "need_budget", "need_engineering_estimate",
}

# =============================================================================
# Readiness — six independent dimensions, never one overall score
# =============================================================================
READINESS_DIMENSIONS = ("evidence_readiness", "execution_readiness",
                        "strategic_readiness", "financial_readiness",
                        "operational_readiness", "decision_readiness")

# =============================================================================
# The decision graph — cascading effects made explicit
# =============================================================================
EDGE_DEPENDS_ON = "depends_on"        # decision -> decision
EDGE_INVALIDATES = "invalidates"      # decision -> decision
EDGE_ENABLES = "enables"              # decision -> decision
EDGE_SUPERSEDES = "supersedes"        # decision -> decision
EDGE_ADDRESSES = "addresses"          # candidate -> opportunity  (derived)
EDGE_RENDERS = "renders"              # package   -> context      (derived)
EDGE_CONTEXTUALIZES = "contextualizes"  # context -> candidate    (derived)
DECISION_EDGES = {EDGE_DEPENDS_ON, EDGE_INVALIDATES, EDGE_ENABLES,
                  EDGE_SUPERSEDES, EDGE_ADDRESSES, EDGE_RENDERS,
                  EDGE_CONTEXTUALIZES}
RECORDED_EDGES = {EDGE_DEPENDS_ON, EDGE_INVALIDATES, EDGE_ENABLES,
                  EDGE_SUPERSEDES}

# =============================================================================
# Reference kinds — references into the subsystem that owns each fact
# =============================================================================
REF_PROPOSAL = "product_proposal"
REF_OPPORTUNITY = "product_opportunity"
REF_PROBLEM = "product_problem"
REF_EVIDENCE = "research_evidence"
REF_RESEARCH_PACKAGE = "research_package"
REF_EXPERIMENT = "growth_experiment"
REF_CRM_FACT = "crm_fact"
REF_METRIC = "analytics_metric"
REF_KNOWLEDGE = "knowledge_item"
REF_DECISION = "decision_record"
REF_PREDICTION = "prediction"
REFERENCE_KINDS = {REF_PROPOSAL, REF_OPPORTUNITY, REF_PROBLEM, REF_EVIDENCE,
                   REF_RESEARCH_PACKAGE, REF_EXPERIMENT, REF_CRM_FACT,
                   REF_METRIC, REF_KNOWLEDGE, REF_DECISION, REF_PREDICTION}

# =============================================================================
# Package outcomes. "No recommendation" is a first-class successful
# outcome, not a failure to produce one.
# =============================================================================
OUTCOME_RECOMMENDATION = "recommendation"
OUTCOME_NO_RECOMMENDATION = "no_recommendation"
PACKAGE_OUTCOMES = (OUTCOME_RECOMMENDATION, OUTCOME_NO_RECOMMENDATION)

# Founder dispositions, bound to an exact package version.
DISPOSITION_ACCEPTED = "accepted"
DISPOSITION_REJECTED = "rejected"
DISPOSITION_DEFERRED = "deferred"
DISPOSITION_MERGED = "merged_into"
REVIEW_DISPOSITIONS = {DISPOSITION_ACCEPTED, DISPOSITION_REJECTED,
                       DISPOSITION_DEFERRED, DISPOSITION_MERGED}
# Terminal states for the traceability invariant. Declining a
# recommendation is an answer, so `rejected` and `deferred` terminate the
# chain legitimately.
TERMINAL_DISPOSITIONS = REVIEW_DISPOSITIONS

# Every option carries all six. An option missing one has had it omitted
# rather than examined.
REQUIRED_OPTION_PARTS = ("benefits", "costs", "risks", "unknowns",
                         "dependencies", "reversibility")

# =============================================================================
# Recommendation wall
# =============================================================================
# Single words are word-boundary matched ('provenance' is not 'proven');
# phrases match literally. This distinction has cost five sessions.
BANNED_RECOMMENDATION_LANGUAGE = (
    "must", "best", "optimal", "correct", "obviously", "clearly",
    "guaranteed", "proven", "always", "never",
    "do this", "should definitely", "the right approach", "no question",
)
REQUIRED_RECOMMENDATION_HEDGES = ("current evidence suggests", "tradeoff",
                                  "review required", "option", "candidate")
UNCERTAIN_EVIDENCE_LABELS = {"CONFLICTING", "INSUFFICIENT", "UNKNOWN",
                             "NOT INVESTIGATED", "INCONCLUSIVE"}
CERTAINTY_MARKERS = ("certain", "certainly", "definitely", "no doubt",
                     "beyond question", "settled", "conclusive",
                     "unambiguous", "without question")

# A model may never author any of these. Checked structurally at any
# nesting depth, not trusted.
MODEL_FORBIDDEN_FIELDS = (
    "decision_id", "decision_ids", "prediction_id", "prediction_ids",
    "crm_entity_id", "crm_entity_ids", "evidence_id", "evidence_ids",
    "evidence_references", "opportunity_id", "problem_id", "proposal_id",
    "experiment_id", "knowledge_id", "citation", "citations", "source_id",
    "readiness", "decision_readiness", "evidence_readiness",
    "execution_readiness", "strategic_readiness", "financial_readiness",
    "operational_readiness", "score", "scores", "priority", "priority_rank",
    "impact", "reversibility", "escalation", "queue_position",
)


class ExecutiveError(ValueError):
    """An executive contract, wall, or lifecycle violation."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scan_banned_language(text: str) -> list:
    # The matcher lives once in the kernel (T022); executive keeps its own
    # banned-term vocabulary and passes it in.
    return _kernel_scan(text, BANNED_RECOMMENDATION_LANGUAGE)


def assert_recommendation_language(text: str, *, where: str = "text") -> None:
    hits = scan_banned_language(text)
    if hits:
        raise ExecutiveError(
            f"{where} overclaims: {hits} — a recommendation states what "
            "current evidence suggests, which tradeoff it accepts, and what "
            "review is required")


def assert_no_certainty(text: str, label: str, *, where: str = "text") -> None:
    if label not in UNCERTAIN_EVIDENCE_LABELS:
        return
    lowered = (text or "").lower()
    hits = sorted({m for m in CERTAINTY_MARKERS
                   if re.search(rf"\b{re.escape(m)}\b", lowered)})
    if hits:
        raise ExecutiveError(
            f"{where} uses certainty language {hits} while the underlying "
            f"evidence is {label} — uncertainty travels with the artifact")


def find_forbidden_fields(value, found=None) -> list:
    """Fields a model or an author may not supply, at any nesting depth.

    The recursive scan lives once in the kernel (T022); executive passes
    its own `MODEL_FORBIDDEN_FIELDS` set. Used by the model boundary and by
    the readiness wall, so there is a single implementation of the rule."""
    return _kernel_forbidden_fields(value, MODEL_FORBIDDEN_FIELDS)


def json_normalize(payload: dict) -> dict:
    try:
        return json.loads(json.dumps(payload, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ExecutiveError(f"payload is not JSON-safe: {exc}") from exc


def validate_reference(ref) -> dict:
    """A reference points INTO the subsystem that owns the fact. It is
    never a copy of what that subsystem holds."""
    if not isinstance(ref, dict):
        raise ExecutiveError(
            "a reference is a mapping of kind + ref_id, so it resolves back "
            "to the subsystem that owns the fact")
    kind, ref_id = ref.get("kind"), ref.get("ref_id")
    if kind not in REFERENCE_KINDS:
        raise ExecutiveError(
            f"unknown reference kind: {kind!r} — one of "
            f"{sorted(REFERENCE_KINDS)}")
    if not isinstance(ref_id, str) or not ref_id.strip():
        raise ExecutiveError("a reference requires a non-empty ref_id")
    out = {"kind": kind, "ref_id": ref_id}
    for optional in ("request_id", "experiment_id", "crm_entity_id",
                     "metric_name", "detail", "label", "stance", "observed_at",
                     "version"):
        if ref.get(optional) is not None:
            out[optional] = ref[optional]
    return out


@dataclass(frozen=True)
class ExecutiveEvent:
    event_type: str
    actor_type: str
    actor_id: str
    source: str
    executive_event_id: str = field(default_factory=new_ulid)
    candidate_id: str | None = None
    context_id: str | None = None
    package_id: str | None = None
    option_id: str | None = None
    conflict_id: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    context_version: int | None = None
    package_version: int | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    decision_id: str | None = None
    prediction_id: str | None = None
    proposal_id: str | None = None
    opportunity_id: str | None = None
    problem_id: str | None = None
    experiment_id: str | None = None
    research_request_id: str | None = None
    crm_entity_id: str | None = None
    knowledge_id: str | None = None
    company_event_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = EXECUTIVE_SCHEMA_VERSION
    provenance: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in EXECUTIVE_EVENT_TYPES:
            raise ExecutiveError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.executive_event_id):
            raise ExecutiveError("executive_event_id must be a ULID")
        if self.actor_type not in ACTOR_TYPES:
            raise ExecutiveError(f"unknown actor_type: {self.actor_type!r}")
        if self.source not in SOURCES:
            raise ExecutiveError(f"unknown source: {self.source!r}")
        for name in ("actor_id", "occurred_at", "recorded_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ExecutiveError(f"{name} must be a non-empty string")
        for name in ("context_version", "package_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 1):
                raise ExecutiveError(f"{name} must be an int >= 1")
        for name in ("payload", "provenance"):
            value = getattr(self, name)
            if not isinstance(value, dict):
                raise ExecutiveError(f"{name} must be a dict")
            try:
                if json.loads(json.dumps(value)) != value:
                    raise ExecutiveError(
                        f"{name} does not survive a JSON round-trip")
            except (TypeError, ValueError) as exc:
                raise ExecutiveError(f"{name} is not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "ExecutiveEvent":
        data = json.loads(line)
        version = data.get("schema_version")
        if isinstance(version, int) and version > EXECUTIVE_SCHEMA_VERSION:
            raise ExecutiveError(
                f"row {data.get('executive_event_id')} is schema v{version} > "
                f"supported v{EXECUTIVE_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("executive_event_id", "recorded_at",
                             "occurred_at")}
        return json.dumps(core, sort_keys=True)

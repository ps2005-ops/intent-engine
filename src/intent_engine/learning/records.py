"""Learning & Promotion Ledger — record contracts (unified-learning platform).

This is the platform-wide generalization of the wall first proven in
`growth_studio/learning.py`: the boundary between "a signal looked good"
and "we now change the system". Marketing keeps its domain-specific
acceptance rules; this ledger is the *shared* primitive every subsystem
(paper trading, synthetic worlds, calibration, marketing) feeds, so no new
subsystem has to reinvent candidate → evaluation → promotion.

Three append-only record types, mirroring the prediction ledger's
discipline (pydantic-validated at write time; code decides, models only
propose):

    Candidate          a proposed improvement. Carries a *versioned*
                       param_diff that this ledger NEVER applies to
                       production — it only records the proposal.
    Evaluation         one comparison of a candidate against the current
                       system, on a rolling backtest or a synthetic
                       scenario, against the candidate's own PREDEFINED
                       success criteria (no moving the goalposts).
    PromotionDecision  the terminal act. `promoted` is only reachable when
                       the predefined criteria are met across evaluations
                       AND a human authorizes it (the promotion wall).

Scope wall, stated in code: nothing here mutates any other subsystem's
store or any generation prompt/weight. Promotion records a DECISION; a
separate, human-owned deploy step is what would ever act on it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from pydantic import BaseModel, Field

from intent_engine.core.decision_ids import new_ulid

# Where a candidate came from. Closed set — a new source is a real code
# change (a new bridge), never a free-text label, so the ledger can always
# attribute a learning to the system that discovered it.
CandidateSource = Literal[
    "synthetic_world",   # a stress-test discovered a blind spot
    "paper_trade",       # the shadow portfolio found a recurring mistake
    "calibration",       # the prediction ledger's Brier/calibration drift
    "marketing",         # a campaign-performance learning (growth_studio)
    "manual",            # a human-proposed improvement
]

CandidateStatus = Literal["proposed", "evaluated", "promoted", "rejected"]
EvaluationKind = Literal["rolling_backtest", "synthetic_scenario"]
EvaluationVerdict = Literal["outperforms", "inconclusive", "underperforms"]


class LearningError(ValueError):
    """A learning-ledger contract was violated."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SuccessCriterion(BaseModel):
    """A single PREDEFINED bar the candidate must clear to be promotable.
    Defined when the candidate is proposed and frozen thereafter — an
    Evaluation reports the observed value, it does not get to redefine the
    bar (that is the anti-metric-gaming rule, enforced in the ledger)."""
    metric: str                       # e.g. "brier", "sharpe", "hit_rate"
    comparator: Literal[">=", "<=", ">", "<"]
    threshold: float
    # "higher is better" (sharpe) vs "lower is better" (brier). Used by the
    # ledger to decide whether an observed value clears the bar AND whether
    # the candidate beat the baseline, deterministically.
    direction: Literal["higher_better", "lower_better"] = "higher_better"


class Candidate(BaseModel):
    id: str = Field(default_factory=new_ulid)
    created_at: str = Field(default_factory=_now)
    source: CandidateSource
    # What the candidate proposes to change, as a stable target string
    # (e.g. "confidence_mapping", "regime_thresholds"). Free text is fine;
    # it is a label for humans, never executed.
    target: str
    statement: str                    # the proposed learning, one sentence
    hypothesis: str                   # why it should help
    baseline_ref: str                 # what "the current system" is here
    success_criteria: List[SuccessCriterion]
    # The versioned proposed change. RECORDED ONLY — this ledger has no
    # code path that applies it. Kept as an opaque dict so any subsystem
    # can describe its own change without this module knowing the shape.
    param_diff: Dict[str, Any] = Field(default_factory=dict)
    # Optional links back into the platform's existing primitives, so a
    # candidate is never orphaned from what produced it.
    decision_id: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)
    status: CandidateStatus = "proposed"

    def require_promotable_shape(self) -> None:
        if not self.success_criteria:
            raise LearningError(
                "a candidate with no predefined success_criteria can never "
                "be promoted — define what 'better' means before proposing")
        if not self.statement.strip():
            raise LearningError("candidate.statement must be non-empty")


class Evaluation(BaseModel):
    id: str = Field(default_factory=new_ulid)
    candidate_id: str
    created_at: str = Field(default_factory=_now)
    kind: EvaluationKind
    # The observation window this evaluation covered — start/end ISO dates
    # or a scenario identifier. Recorded so a later reader can see the
    # candidate and baseline were compared over the same ground.
    window: Dict[str, Any] = Field(default_factory=dict)
    # Observed metric values for the candidate and the baseline it was
    # compared against, keyed by the SAME metric names the criteria use.
    candidate_metrics: Dict[str, float] = Field(default_factory=dict)
    baseline_metrics: Dict[str, float] = Field(default_factory=dict)
    verdict: EvaluationVerdict
    notes: str = ""
    sample_size: int = 0


class PromotionDecision(BaseModel):
    id: str = Field(default_factory=new_ulid)
    candidate_id: str
    decided_at: str = Field(default_factory=_now)
    decision: Literal["promoted", "rejected"]
    actor_type: Literal["human", "agent", "system"]
    rationale: str
    evaluation_ids: List[str] = Field(default_factory=list)
    # Per-criterion audit: {criterion_metric: bool}. Recorded so the
    # promotion is explainable — which bars were met, on the evidence.
    criteria_audit: Dict[str, bool] = Field(default_factory=dict)


def clears(criterion: SuccessCriterion, value: float) -> bool:
    """Does an observed value clear a predefined criterion? Pure, in code —
    never asked of a model, same discipline as the Brier computation."""
    c = criterion.comparator
    t = criterion.threshold
    if c == ">=":
        return value >= t
    if c == "<=":
        return value <= t
    if c == ">":
        return value > t
    if c == "<":
        return value < t
    raise LearningError(f"unknown comparator {c!r}")


def beats_baseline(criterion: SuccessCriterion, cand: float, base: float) -> bool:
    """Did the candidate value beat the baseline on this metric's own
    directionality? A promotion needs BOTH: clear the absolute bar and
    beat the incumbent — 'promote only if objectively better'."""
    if criterion.direction == "higher_better":
        return cand > base
    return cand < base

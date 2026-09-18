"""Durable, human-gated learning candidates (sections 12, 13).

Candidates are GENERATED daily from company + paper outcomes, but NOTHING here
promotes one — promotion stays a human wall (matching the repo's existing
LearningLedger discipline). `promote()` exists but is never called by any job;
only a human action flips a candidate to promoted. No candidate is proposed from
a single trade, a single day, or in-sample/synthetic-only performance.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import List, Optional

from pydantic import BaseModel, Field

STREAM = "learning_candidate"

# The floor below which we never even PROPOSE a candidate (section 13).
_MIN_SAMPLE = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LearningCandidate(BaseModel):
    id: str
    scope: str                          # "company" | "cross_company"
    company_id: Optional[str] = None
    source: str                         # company_scoring | paper_trade | cross_company
    statement: str
    hypothesis: str
    evidence: dict = Field(default_factory=dict)
    sample_size: int = 0
    status: str = "proposed"            # proposed | evaluated | promoted | rejected
    created_at: str = Field(default_factory=_now)


class CandidateStore:
    def __init__(self, store):
        self.store = store

    def propose(self, cand: LearningCandidate) -> Optional[LearningCandidate]:
        if cand.sample_size < _MIN_SAMPLE:
            return None                 # never propose below the sample floor
        # A candidate is append-only + latest-wins by id: its EVIDENCE changes
        # as outcomes accrue (accuracy, Brier, P&L drift daily), so the idem key
        # is a signature of the MEANINGFUL content (not the frozen id and not
        # the volatile created_at). Re-proposing identical content is a no-op;
        # updated evidence appends a new latest row. (Freezing on the id alone
        # made the nightly job raise IdempotencyConflict every day after day 1.)
        sig = sha256(json.dumps(
            {"statement": cand.statement, "hypothesis": cand.hypothesis,
             "evidence": cand.evidence, "sample_size": cand.sample_size,
             "status": cand.status, "source": cand.source},
            sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        self.store.append(STREAM, cand.id, cand.model_dump(mode="json"),
                          status=cand.status, company_id=cand.company_id,
                          idem_key=f"cand:{cand.id}:{sig}", ts=cand.created_at)
        return cand

    def record_evaluation(self, candidate_id: str, evaluation: dict) -> None:
        cand = self.get(candidate_id)
        if cand is None:
            return
        updated = cand.model_copy(update={"status": "evaluated"})
        # Idempotent on the evaluation's MEANINGFUL content (not a wall-clock
        # second — two evaluations within one second must not collide, and an
        # identical re-evaluation must be a no-op).
        sig = sha256(json.dumps(
            {k: evaluation.get(k) for k in (
                "in_sample_accuracy", "out_of_sample_accuracy",
                "weakness_holds_out_of_sample", "in_sample_n", "out_sample_n")},
            sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        self.store.append(STREAM, candidate_id, updated.model_dump(mode="json"),
                          status="evaluated", company_id=cand.company_id,
                          idem_key=f"cand-eval:{candidate_id}:{sig}")
        self.store.append("candidate_evaluation", candidate_id, evaluation,
                          status="evaluated", ref_id=candidate_id,
                          idem_key=f"eval:{candidate_id}:{sig}")

    def get(self, candidate_id: str) -> Optional[LearningCandidate]:
        rec = self.store.get(STREAM, candidate_id)
        return LearningCandidate(**rec.payload) if rec else None

    def open(self) -> List[LearningCandidate]:
        return [c for c in self.all_latest()
                if c.status in ("proposed", "evaluated")]

    def all_latest(self) -> List[LearningCandidate]:
        return [LearningCandidate(**r.payload) for r in self.store.latest(STREAM)]

    # HUMAN-ONLY: never called by a job. Present so the surface exists, gated.
    def promote(self, candidate_id: str, *, approved_by: str) -> LearningCandidate:
        cand = self.get(candidate_id)
        if cand is None:
            raise ValueError(f"no candidate {candidate_id!r}")
        promoted = cand.model_copy(update={"status": "promoted"})
        self.store.append(STREAM, candidate_id, promoted.model_dump(mode="json"),
                          status="promoted", company_id=cand.company_id,
                          idem_key=f"cand-promote:{candidate_id}")
        self.store.append("candidate_promotion", candidate_id,
                          {"candidate_id": candidate_id, "approved_by": approved_by,
                           "at": _now()}, status="promoted", ref_id=candidate_id)
        return promoted


def candidate_from_company_state(state) -> Optional[LearningCandidate]:
    """Propose a company candidate when its OWN record shows a recurring,
    sample-backed weakness (overconfidence or a losing paper book)."""
    if state.resolved_count < _MIN_SAMPLE:
        return None
    overconfident = (state.calibration_error is not None
                     and state.avg_confidence is not None
                     and state.directional_accuracy is not None
                     and state.avg_confidence - state.directional_accuracy > 0.15)
    losing = state.paper_pnl < 0 and state.resolved_count >= _MIN_SAMPLE
    if not (overconfident or losing):
        return None
    reason = "overconfidence" if overconfident else "losing_paper_book"
    return LearningCandidate(
        id=f"cand:{state.company_id}:{reason}", scope="company",
        company_id=state.company_id, source="company_scoring",
        statement=(f"{state.company_id}: {reason.replace('_', ' ')} over "
                   f"{state.resolved_count} resolved predictions"),
        hypothesis=("confidence mapping or direction for this company is "
                    "systematically miscalibrated"),
        evidence={"directional_accuracy": state.directional_accuracy,
                  "avg_confidence": state.avg_confidence,
                  "brier": state.brier, "paper_pnl": state.paper_pnl},
        sample_size=state.resolved_count)

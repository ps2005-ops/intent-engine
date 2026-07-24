"""Learning & Promotion Ledger — the orchestration + the walls.

This is the "brain" the platform records into: every subsystem that learns
proposes a Candidate here; evidence accrues as Evaluations; and only a
human-authorized, criteria-met PromotionDecision ever declares a candidate
`promoted`. The cadence the founder specified is enforced as a state
machine, not a comment:

    propose   (DAILY)    proposed     — anyone/any bridge may propose
    evaluate  (WEEKLY)   evaluated    — compare candidate vs current system
    promote / (MONTHLY / promoted /   — HUMAN wall + predefined criteria met
    reject     on evidence) rejected     consistently across evaluations

Two hard walls, in code:
  1. Promotion wall — `promote()` refuses unless the actor is a human AND
     every predefined success criterion is met (cleared its absolute bar
     and beat the baseline) across the required number of evaluations.
     Publishing `learning.candidate_promoted` is itself gated to human
     actors by the event bus (publisher._HUMAN_ONLY_EVENTS), so this is
     defence in depth.
  2. No-production-mutation wall — this service has NO code path that
     applies a candidate's param_diff to any generation prompt, weight, or
     other subsystem store. It records decisions. Acting on a promoted
     decision is a separate, human-owned deploy step outside this module.

Events are published through the existing CompanyEventBus (T013) — this
subsystem invents no new transport, and the ledger (not the event log) is
the source of truth for candidate state.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from intent_engine.events import CompanyEventBus
from intent_engine.learning.ledger import DEFAULT_LEARNING_PATH, LearningStore
from intent_engine.learning.records import (
    Candidate, CandidateSource, Evaluation, EvaluationKind,
    EvaluationVerdict, LearningError, PromotionDecision, SuccessCriterion,
    beats_baseline, clears,
)

# How much evidence a candidate needs before a human may promote it. One
# evaluation is a fluke; the weekly cadence is expected to accrue several.
# Kept small and explicit; a stricter policy is a config change, not a
# rewrite.
MIN_EVALUATIONS_TO_PROMOTE = 2

PRODUCER = "learning_ledger"


class LearningLedger:
    """The one write path into the learning ledger."""

    def __init__(self, path: Union[str, Path] = DEFAULT_LEARNING_PATH,
                 *, bus: Optional[CompanyEventBus] = None):
        self.store = LearningStore(path)
        self.bus = bus

    # --- DAILY: propose ------------------------------------------------------
    def propose(
        self, *, source: CandidateSource, target: str, statement: str,
        hypothesis: str, baseline_ref: str,
        success_criteria: List[Union[SuccessCriterion, Dict[str, Any]]],
        param_diff: Optional[Dict[str, Any]] = None,
        decision_id: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
        actor_type: str = "agent", actor_id: str = "learning_bridge",
        source_channel: str = "system",
        idempotency_key: Optional[str] = None,
    ) -> Candidate:
        criteria = [c if isinstance(c, SuccessCriterion)
                    else SuccessCriterion(**c) for c in success_criteria]
        candidate = Candidate(
            source=source, target=target, statement=statement,
            hypothesis=hypothesis, baseline_ref=baseline_ref,
            success_criteria=criteria, param_diff=dict(param_diff or {}),
            decision_id=decision_id, provenance=dict(provenance or {}),
            status="proposed",
        )
        candidate.require_promotable_shape()
        self.store.append_candidate(candidate)
        self._publish("learning.candidate_proposed", candidate.id,
                      actor_type=actor_type, actor_id=actor_id,
                      source=source_channel, decision_id=decision_id,
                      payload={"source": source, "target": target,
                               "statement": statement},
                      idempotency_key=idempotency_key)
        return candidate

    # --- WEEKLY: evaluate ----------------------------------------------------
    def evaluate(
        self, candidate_id: str, *, kind: EvaluationKind,
        candidate_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float],
        window: Optional[Dict[str, Any]] = None,
        notes: str = "", sample_size: int = 0,
        actor_type: str = "system", actor_id: str = "evaluation_harness",
        idempotency_key: Optional[str] = None,
    ) -> Evaluation:
        candidate = self._require(candidate_id)
        if candidate.status in ("promoted", "rejected"):
            raise LearningError(
                f"candidate {candidate_id} is already {candidate.status}; "
                "evaluations are only meaningful before the terminal decision")
        verdict = self._verdict(candidate, candidate_metrics, baseline_metrics)
        evaluation = Evaluation(
            candidate_id=candidate_id, kind=kind, window=dict(window or {}),
            candidate_metrics=dict(candidate_metrics),
            baseline_metrics=dict(baseline_metrics), verdict=verdict,
            notes=notes, sample_size=sample_size,
        )
        self.store.append_evaluation(evaluation)
        # Advance status proposed -> evaluated (append-only: a new candidate
        # row with the same id and updated status).
        if candidate.status == "proposed":
            self.store.append_candidate(candidate.model_copy(
                update={"status": "evaluated"}))
        self._publish("learning.candidate_evaluated", candidate_id,
                      actor_type=actor_type, actor_id=actor_id, source="system",
                      decision_id=candidate.decision_id,
                      payload={"kind": kind, "verdict": verdict,
                               "sample_size": sample_size},
                      idempotency_key=idempotency_key)
        return evaluation

    # --- MONTHLY / on-evidence: promote or reject ---------------------------
    def evaluate_promotion_readiness(self, candidate_id: str) -> Dict[str, Any]:
        """Deterministic, read-only: is this candidate promotable on the
        evidence recorded so far? Returns the full audit so a human sees
        exactly why (never a bare yes/no). This is the code that 'decides';
        promote() only records the human's authorization on top of it."""
        candidate = self._require(candidate_id)
        evaluations = self.store.evaluations_for(candidate_id)
        criteria_audit: Dict[str, bool] = {}
        reasons: List[str] = []

        if len(evaluations) < MIN_EVALUATIONS_TO_PROMOTE:
            reasons.append(
                f"only {len(evaluations)} evaluation(s); "
                f"need >= {MIN_EVALUATIONS_TO_PROMOTE}")

        for criterion in candidate.success_criteria:
            met_everywhere = bool(evaluations)
            for ev in evaluations:
                cand = ev.candidate_metrics.get(criterion.metric)
                base = ev.baseline_metrics.get(criterion.metric)
                if cand is None:
                    met_everywhere = False
                    reasons.append(
                        f"evaluation {ev.id} is missing metric "
                        f"{criterion.metric!r}")
                    continue
                if not clears(criterion, cand):
                    met_everywhere = False
                if base is not None and not beats_baseline(criterion, cand, base):
                    met_everywhere = False
            criteria_audit[criterion.metric] = met_everywhere
            if not met_everywhere:
                reasons.append(
                    f"criterion on {criterion.metric!r} not met consistently")

        ready = (len(evaluations) >= MIN_EVALUATIONS_TO_PROMOTE
                 and all(criteria_audit.values()) and bool(criteria_audit))
        return {
            "candidate_id": candidate_id,
            "ready": ready,
            "criteria_audit": criteria_audit,
            "evaluation_ids": [e.id for e in evaluations],
            "evaluation_count": len(evaluations),
            "reasons": reasons,
        }

    def promote(self, candidate_id: str, *, actor_type: str, actor_id: str,
                rationale: str, source: str = "cli") -> PromotionDecision:
        if actor_type != "human":
            raise LearningError(
                "promotion authorizes a change to production and is a HUMAN "
                f"wall; actor_type={actor_type!r} may not promote")
        readiness = self.evaluate_promotion_readiness(candidate_id)
        if not readiness["ready"]:
            raise LearningError(
                "candidate is not promotable on the evidence: "
                + "; ".join(readiness["reasons"]))
        decision = PromotionDecision(
            candidate_id=candidate_id, decision="promoted",
            actor_type=actor_type, rationale=rationale,
            evaluation_ids=readiness["evaluation_ids"],
            criteria_audit=readiness["criteria_audit"],
        )
        self.store.append_promotion(decision)
        self.store.append_candidate(self._require(candidate_id).model_copy(
            update={"status": "promoted"}))
        # HUMAN wall enforced again at the bus.
        self._publish("learning.candidate_promoted", candidate_id,
                      actor_type=actor_type, actor_id=actor_id, source=source,
                      payload={"rationale": rationale,
                               "evaluation_ids": readiness["evaluation_ids"]})
        return decision

    def reject(self, candidate_id: str, *, actor_type: str = "system",
               actor_id: str = "learning_ledger", rationale: str = "",
               source: str = "system") -> PromotionDecision:
        candidate = self._require(candidate_id)
        decision = PromotionDecision(
            candidate_id=candidate_id, decision="rejected",
            actor_type=actor_type if actor_type in ("human", "agent", "system")
            else "system",
            rationale=rationale,
            evaluation_ids=[e.id for e in self.store.evaluations_for(candidate_id)],
        )
        self.store.append_promotion(decision)
        self.store.append_candidate(candidate.model_copy(
            update={"status": "rejected"}))
        self._publish("learning.candidate_rejected", candidate_id,
                      actor_type=actor_type, actor_id=actor_id, source=source,
                      payload={"rationale": rationale})
        return decision

    # --- reads ---------------------------------------------------------------
    def get(self, candidate_id: str) -> Optional[Candidate]:
        return self.store.get_candidate(candidate_id)

    def list(self, *, status: Optional[str] = None,
             source: Optional[str] = None) -> List[Candidate]:
        return self.store.list_candidates(status=status, source=source)

    def evaluations_for(self, candidate_id: str) -> List[Evaluation]:
        return self.store.evaluations_for(candidate_id)

    # --- internals -----------------------------------------------------------
    def _require(self, candidate_id: str) -> Candidate:
        candidate = self.store.get_candidate(candidate_id)
        if candidate is None:
            raise LearningError(f"no candidate {candidate_id!r}")
        return candidate

    @staticmethod
    def _verdict(candidate: Candidate, cand: Dict[str, float],
                 base: Dict[str, float]) -> EvaluationVerdict:
        """Code decides the verdict from the predefined criteria — the
        harness reports numbers, it does not get to assert the verdict."""
        cleared, beat, seen = 0, 0, 0
        for criterion in candidate.success_criteria:
            v = cand.get(criterion.metric)
            if v is None:
                continue
            seen += 1
            if clears(criterion, v):
                cleared += 1
            b = base.get(criterion.metric)
            if b is not None and beats_baseline(criterion, v, b):
                beat += 1
        if seen == 0:
            return "inconclusive"
        if cleared == seen and beat == seen:
            return "outperforms"
        if cleared == 0:
            return "underperforms"
        return "inconclusive"

    def _publish(self, event_type: str, candidate_id: str, **kw) -> None:
        if self.bus is None:
            return
        payload = kw.pop("payload", {})
        decision_id = kw.pop("decision_id", None)
        idempotency_key = kw.pop("idempotency_key", None)
        self.bus.publish(
            event_type, subject_type="candidate", subject_id=candidate_id,
            producer=PRODUCER, payload=payload, decision_id=decision_id,
            idempotency_key=idempotency_key, **kw)

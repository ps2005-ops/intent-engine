"""KnowledgeService (T016) — the only write path for feedback, consent,
insights, knowledge items, and mechanism proposals; plus deterministic
reads. All history is append-only rows; every current state is a fold.
"""
from __future__ import annotations

from pathlib import Path

from intent_engine.core.decision_ids import new_ulid
from intent_engine.knowledge.citations import validate_citations
from intent_engine.knowledge.records import (
    CONSENT_EVENTS, FEEDBACK_TYPES, KNOWLEDGE_CATEGORIES,
    KNOWLEDGE_ROW_TYPES, MARKER_CONSENT_REQUIRED, MARKER_NOT_VALIDATED,
    MECHANISM_STATUSES, QUOTE_USES, RETRACTION_REASONS, KnowledgeError, Row,
    assert_claim_language,
)
from intent_engine.knowledge.store import RowStore

DEFAULT_FEEDBACK_PATH = Path("data/feedback.jsonl")
DEFAULT_KNOWLEDGE_PATH = Path("knowledge/knowledge.jsonl")

_HUMAN_ONLY = (CONSENT_EVENTS - {"feedback.quote_consent_requested"}) | {
    "insight.validated", "insight.rejected", "knowledge.promoted",
    "knowledge.rejected", "knowledge.retracted", "mechanism.review",
}


class KnowledgeService:
    def __init__(self, feedback_path=DEFAULT_FEEDBACK_PATH,
                 knowledge_path=DEFAULT_KNOWLEDGE_PATH, resolvers=None):
        self.feedback = RowStore(feedback_path, FEEDBACK_TYPES)
        self.rows = RowStore(knowledge_path, KNOWLEDGE_ROW_TYPES)
        self.resolvers = dict(resolvers or {})
        self.resolvers.setdefault("feedback_store", self.feedback)

    # --- internal -------------------------------------------------------------
    def _append(self, store, record_type, subject_id, *, actor_type, actor_id,
                source="cli", payload=None, occurred_at=None,
                idempotency_key=None, **refs) -> Row:
        if record_type in _HUMAN_ONLY and actor_type != "human":
            raise KnowledgeError(
                f"{record_type} is a human wall transition; "
                f"actor_type={actor_type!r} cannot emit it")
        kwargs = dict(record_type=record_type, subject_id=subject_id,
                      actor_type=actor_type, actor_id=actor_id, source=source,
                      payload=dict(payload or {}),
                      idempotency_key=idempotency_key, **refs)
        if occurred_at is not None:
            kwargs["occurred_at"] = occurred_at
        return store.append(Row(**kwargs))

    # --- feedback -------------------------------------------------------------
    def record_feedback(self, feedback_type: str, content: str, *,
                        actor_type: str, actor_id: str, source="cli",
                        structured_fields=None, decision_id=None,
                        prediction_id=None, crm_entity_id=None,
                        company_event_id=None, correlation_id=None,
                        confidentiality="internal", occurred_at=None,
                        idempotency_key=None) -> str:
        if feedback_type in CONSENT_EVENTS:
            raise KnowledgeError("consent facts go through the quote-gate API")
        feedback_id = new_ulid()
        if idempotency_key:
            existing = self.feedback.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                # retry of the same fact: reuse its identity so the store's
                # fingerprint check compares like-for-like (and still
                # rejects same-key-different-content)
                feedback_id = existing.subject_id
        self._append(
            self.feedback, feedback_type, feedback_id, actor_type=actor_type,
            actor_id=actor_id, source=source, occurred_at=occurred_at,
            idempotency_key=idempotency_key, decision_id=decision_id,
            prediction_id=prediction_id, crm_entity_id=crm_entity_id,
            company_event_id=company_event_id, correlation_id=correlation_id,
            payload={"content": content,
                     "structured_fields": dict(structured_fields or {}),
                     "confidentiality": confidentiality,
                     "quote_consent": "not_requested"})
        return feedback_id

    def get_feedback(self, feedback_id: str) -> list[Row]:
        rows = self.feedback.for_subject(feedback_id)
        if not rows:
            raise KeyError(f"no such feedback: {feedback_id}")
        return rows

    def get_feedback_for_decision(self, decision_id: str) -> list[Row]:
        return [r for r in self.feedback.read_all()
                if r.decision_id == decision_id
                and r.record_type not in CONSENT_EVENTS]

    # --- quote-consent gate ---------------------------------------------------
    def record_quote_consent(self, feedback_id: str, action: str,
                             quote_text: str, intended_use: str, *,
                             actor_type: str, actor_id: str,
                             source="cli") -> Row:
        """action: requested | approved | rejected | revoked. Consent binds
        to the EXACT text span and the intended use; approval/rejection/
        revocation are human-only (enforced by _HUMAN_ONLY)."""
        if intended_use not in QUOTE_USES:
            raise KnowledgeError(f"unknown intended_use: {intended_use!r}")
        if not quote_text or not quote_text.strip():
            raise KnowledgeError("consent requires the exact quote text")
        self.get_feedback(feedback_id)
        return self._append(
            self.feedback, f"feedback.quote_consent_{action}", feedback_id,
            actor_type=actor_type, actor_id=actor_id, source=source,
            payload={"quote_text": quote_text, "intended_use": intended_use})

    def can_publish_quote(self, feedback_id: str, quote_text: str,
                          intended_use: str = "public") -> dict:
        """Deterministic: latest consent fact for this EXACT text + use
        wins. No consent -> not publishable; internal consent never implies
        public consent."""
        rows = self.get_feedback(feedback_id)
        state = "not_requested"
        for r in rows:
            if r.record_type in CONSENT_EVENTS \
                    and r.payload.get("quote_text") == quote_text \
                    and r.payload.get("intended_use") == intended_use:
                state = r.record_type.rsplit("_", 1)[-1]
        allowed = state == "approved"
        return {"allowed": allowed, "consent_state": state,
                "reason": ("consent approved for this exact text and use"
                           if allowed else
                           f"{MARKER_CONSENT_REQUIRED}: consent state is "
                           f"{state!r} for this exact text and use")}

    # --- insights -------------------------------------------------------------
    def propose_insight(self, title: str, claim: str, *, scope: str,
                        limitations: str, source_feedback_ids: list,
                        citations: list, proposed_by: str,
                        actor_type: str = "system", source="system",
                        idempotency_key=None) -> str:
        assert_claim_language(claim)
        validate_citations(citations, self.resolvers)
        for fid in source_feedback_ids:
            self.get_feedback(fid)
        insight_id = new_ulid()
        self._append(
            self.rows, "insight.proposed", insight_id, actor_type=actor_type,
            actor_id=proposed_by, source=source,
            idempotency_key=idempotency_key,
            payload={"revision": 1, "title": title, "claim": claim,
                     "scope": scope, "limitations": limitations,
                     "source_feedback_ids": list(source_feedback_ids),
                     "citations": list(citations)})
        return insight_id

    def revise_insight(self, insight_id: str, *, actor_type, actor_id,
                       **changes) -> int:
        """A revision is a NEW fact; validation attaches to a revision, so
        any revision after validation leaves the current revision
        NOT VALIDATED until a human validates it again."""
        current = self._insight_fold(insight_id)
        if "claim" in changes:
            assert_claim_language(changes["claim"])
        if "citations" in changes:
            validate_citations(changes["citations"], self.resolvers)
        revision = current["revision"] + 1
        payload = {**{k: current[k] for k in
                      ("title", "claim", "scope", "limitations",
                       "source_feedback_ids", "citations")},
                   **changes, "revision": revision}
        self._append(self.rows, "insight.revised", insight_id,
                     actor_type=actor_type, actor_id=actor_id,
                     payload=payload)
        return revision

    def validate_insight(self, insight_id: str, revision: int, *,
                         actor_id: str, actor_type: str = "human") -> Row:
        current = self._insight_fold(insight_id)
        if current["status"] == "rejected":
            raise KnowledgeError("a rejected insight needs a new revision "
                                 "before validation")
        if revision != current["revision"]:
            raise KnowledgeError(
                f"validation must reference the exact current revision "
                f"({current['revision']}), got {revision}")
        assert_claim_language(current["claim"])
        validate_citations(current["citations"], self.resolvers)
        return self._append(self.rows, "insight.validated", insight_id,
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"revision": revision})

    def reject_insight(self, insight_id: str, reason: str, *, actor_id: str,
                       actor_type: str = "human") -> Row:
        self._insight_fold(insight_id)
        return self._append(self.rows, "insight.rejected", insight_id,
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"reason": reason})

    def _insight_fold(self, insight_id: str) -> dict:
        rows = self.rows.for_subject(insight_id)
        content_rows = [r for r in rows if r.record_type in
                        ("insight.proposed", "insight.revised")]
        if not content_rows:
            raise KeyError(f"no such insight: {insight_id}")
        state = dict(content_rows[-1].payload)
        state["status"] = "proposed"
        state["validated_revision"] = None
        for r in rows:
            if r.record_type == "insight.validated":
                state["validated_revision"] = r.payload["revision"]
                state["status"] = "validated"
            elif r.record_type == "insight.rejected":
                state["status"] = "rejected"
            elif r.record_type == "insight.revised":
                if state.get("validated_revision") is not None \
                        and r.payload["revision"] > state["validated_revision"]:
                    state["status"] = "proposed"    # revalidation required
        state["current_is_validated"] = (
            state["validated_revision"] == state["revision"]
            and state["status"] == "validated")
        return state

    def get_insight(self, insight_id: str) -> dict:
        return self._insight_fold(insight_id)

    def get_insight_history(self, insight_id: str) -> list[Row]:
        rows = self.rows.for_subject(insight_id)
        if not rows:
            raise KeyError(f"no such insight: {insight_id}")
        return rows

    def list_pending_validations(self) -> list[str]:
        ids = {r.subject_id for r in self.rows.read_all()
               if r.record_type == "insight.proposed"}
        return sorted(i for i in ids
                      if not self._insight_fold(i)["current_is_validated"]
                      and self._insight_fold(i)["status"] != "rejected")

    # --- knowledge promotion --------------------------------------------------
    def promote_knowledge(self, insight_id: str, revision: int, *,
                          category: str, actor_id: str,
                          actor_type: str = "human",
                          applicability_conditions: str = "",
                          counterexamples: str = "") -> str:
        insight = self._insight_fold(insight_id)
        if not insight["current_is_validated"] \
                or insight["validated_revision"] != revision:
            raise KnowledgeError(
                f"{MARKER_NOT_VALIDATED}: promotion requires the exact "
                "human-validated current revision")
        if category not in KNOWLEDGE_CATEGORIES:
            raise KnowledgeError(f"unknown category: {category!r}")
        for field_name in ("scope", "limitations"):
            if not insight.get(field_name, "").strip():
                raise KnowledgeError(f"{field_name} is mandatory for promotion")
        assert_claim_language(insight["claim"])
        validate_citations(insight["citations"], self.resolvers)
        knowledge_id = new_ulid()
        self._append(
            self.rows, "knowledge.promoted", knowledge_id,
            actor_type=actor_type, actor_id=actor_id,
            payload={"version": 1, "category": category,
                     "title": insight["title"],
                     "statement": insight["claim"],
                     "scope": insight["scope"],
                     "limitations": insight["limitations"],
                     "applicability_conditions": applicability_conditions,
                     "counterexamples": counterexamples,
                     "citations": insight["citations"],
                     "source_insight_id": insight_id,
                     "source_insight_revision": revision})
        return knowledge_id

    def supersede_knowledge(self, knowledge_id: str, *, actor_id: str,
                            actor_type: str = "human", **changes) -> int:
        current = self.get_knowledge_item(knowledge_id)
        if "statement" in changes:
            assert_claim_language(changes["statement"])
        version = current["version"] + 1
        payload = {**current, **changes, "version": version}
        payload.pop("status", None)
        self._append(self.rows, "knowledge.superseded", knowledge_id,
                     actor_type=actor_type, actor_id=actor_id,
                     payload=payload)
        return version

    def retract_knowledge(self, knowledge_id: str, reason: str, *,
                          actor_id: str, actor_type: str = "human") -> Row:
        if reason not in RETRACTION_REASONS:
            raise KnowledgeError(f"unknown retraction reason: {reason!r}")
        self.get_knowledge_item(knowledge_id)
        return self._append(self.rows, "knowledge.retracted", knowledge_id,
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"reason": reason})

    def get_knowledge_item(self, knowledge_id: str, version=None) -> dict:
        rows = [r for r in self.rows.for_subject(knowledge_id)
                if r.record_type in ("knowledge.promoted",
                                     "knowledge.superseded")]
        if not rows:
            raise KeyError(f"no such knowledge item: {knowledge_id}")
        if version is not None:
            for r in rows:
                if r.payload["version"] == version:
                    return {**r.payload, "status": "historical"}
            raise KeyError(f"no version {version} of {knowledge_id}")
        current = dict(rows[-1].payload)
        retracted = any(r.record_type == "knowledge.retracted"
                        for r in self.rows.for_subject(knowledge_id))
        current["status"] = "retracted" if retracted else "active"
        return current

    def get_current_knowledge(self, knowledge_id: str) -> dict | None:
        item = self.get_knowledge_item(knowledge_id)
        return item if item["status"] == "active" else None

    def search_knowledge(self, category=None) -> list[dict]:
        ids = sorted({r.subject_id for r in self.rows.read_all()
                      if r.record_type == "knowledge.promoted"})
        out = []
        for kid in ids:
            item = self.get_knowledge_item(kid)
            if category is None or item["category"] == category:
                out.append({"knowledge_id": kid, **item})
        return sorted(out, key=lambda i: (i["category"], i["title"],
                                          i["knowledge_id"]))

    # --- mechanism proposal queue (frozen library NEVER touched) --------------
    def propose_mechanism(self, candidate_name: str, hypothesis: str, *,
                          trigger_conditions: list, expected_effects: str,
                          scope: str, counterexamples: str, citations: list,
                          source_knowledge_ids: list, proposed_by: str,
                          actor_type: str = "system") -> str:
        assert_claim_language(hypothesis)
        validate_citations(citations, self.resolvers)
        existing = [r for r in self.rows.read_all()
                    if r.record_type == "mechanism.proposed"
                    and r.payload.get("candidate_name") == candidate_name]
        if existing:
            statuses = {self.get_mechanism_proposal(r.subject_id)["status"]
                        for r in existing}
            if statuses - {"rejected", "superseded"}:
                raise KnowledgeError(
                    f"a live proposal for {candidate_name!r} already exists "
                    "(deterministic duplicate detection)")
        proposal_id = new_ulid()
        self._append(
            self.rows, "mechanism.proposed", proposal_id,
            actor_type=actor_type, actor_id=proposed_by, source="system",
            payload={"candidate_name": candidate_name,
                     "hypothesis": hypothesis,
                     "trigger_conditions": list(trigger_conditions),
                     "expected_effects": expected_effects, "scope": scope,
                     "counterexamples": counterexamples,
                     "citations": list(citations),
                     "source_knowledge_ids": list(source_knowledge_ids),
                     "status": "proposed"})
        return proposal_id

    def review_mechanism(self, proposal_id: str, status: str, notes: str, *,
                         actor_id: str, actor_type: str = "human") -> Row:
        if status not in MECHANISM_STATUSES - {"proposed"}:
            raise KnowledgeError(f"invalid review status: {status!r}")
        self.get_mechanism_proposal(proposal_id)
        return self._append(self.rows, "mechanism.review", proposal_id,
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"status": status, "notes": notes})

    def get_mechanism_proposal(self, proposal_id: str) -> dict:
        rows = self.rows.for_subject(proposal_id)
        proposed = [r for r in rows if r.record_type == "mechanism.proposed"]
        if not proposed:
            raise KeyError(f"no such mechanism proposal: {proposal_id}")
        state = dict(proposed[-1].payload)
        for r in rows:
            if r.record_type == "mechanism.review":
                state["status"] = r.payload["status"]
                state["review_notes"] = r.payload["notes"]
        return state

    def list_mechanism_proposals(self, status=None) -> list[dict]:
        ids = sorted({r.subject_id for r in self.rows.read_all()
                      if r.record_type == "mechanism.proposed"})
        out = [{"proposal_id": pid, **self.get_mechanism_proposal(pid)}
               for pid in ids]
        if status is not None:
            out = [p for p in out if p["status"] == status]
        return sorted(out, key=lambda p: (p["candidate_name"],
                                          p["proposal_id"]))

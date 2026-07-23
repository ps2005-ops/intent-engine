"""ExecutiveService (T021) — the only write path.

The agent triages, contextualizes, drafts packages, and recommends. It
never accepts, rejects, defers, merges, creates a Decision Record, records
a prediction, promotes knowledge, starts an experiment, writes another
subsystem's store, or writes `ROADMAP.md`.

Every other subsystem is READ through its own public surface and is never
reimplemented: the Problem and Opportunity Indexes (T020), the Evidence
Index (T019), T018 for experiment labels, T014 for customer facts, T015
for metrics, T016 for knowledge items, and — the load-bearing one for this
subsystem — `DecisionService` for decision state, which is RESOLVED at read
time and never mirrored into the executive log.
"""
from __future__ import annotations

import hashlib

from intent_engine.agentos.identity import stable_id as _kernel_stable_id
from intent_engine.agentos.model_boundary import model_provenance
from intent_engine.executive.conflicts import (
    conflict_summary, detect_conflicts,
)
from intent_engine.executive.context import (
    build_context, decision_age, expiry_check,
)
from intent_engine.executive.debt import debt_report, derive_decision_debt
from intent_engine.executive.index import build_index
from intent_engine.executive.intake import (
    candidate_from_accepted_proposal, candidate_from_decision_debt,
    candidate_from_expired_decision,
)
from intent_engine.executive.packages import (
    assign_escalation, build_no_recommendation, build_option, build_package,
    cross_agent_provenance,
)
from intent_engine.executive.portfolio import (
    executive_portfolio, health_dashboard,
)
from intent_engine.executive.queue import build_entry, build_queues
from intent_engine.executive.readiness import (
    assert_not_readiness_shaped, readiness_block,
)
from intent_engine.executive.records import (
    DECISION_CLASSES, DECISION_HORIZONS, ESCALATION_LEVELS, HUMAN_ONLY_EVENTS,
    RECORDED_EDGES, REF_CRM_FACT, REF_DECISION, REF_EXPERIMENT, REF_METRIC,
    REF_OPPORTUNITY, REF_PROPOSAL, REF_RESEARCH_PACKAGE, REVIEW_DISPOSITIONS,
    ExecutiveError, ExecutiveEvent, assert_recommendation_language,
    find_forbidden_fields, json_normalize, now_iso, validate_reference,
)
from intent_engine.executive.state import (
    ExecutiveState, fold_executive, validate_executive_event,
)
from intent_engine.executive.store import DEFAULT_EXECUTIVE_PATH, ExecutiveStore
from intent_engine.executive.traceability import (
    assert_no_dead_ends, trace_package,
)

PROMPT_VERSIONS = {
    "package_prose": "executive_package_prose.v1",
    "option_prose": "executive_option_prose.v1",
    "next_review": "executive_next_review.v1",
}

# A model may return prose in these fields and nothing else. A whitelist,
# not a blacklist: an unanticipated field is rejected, not stored.
MODEL_ALLOWED_FIELDS = {
    "decision_question", "summary", "narrative", "label", "benefits", "costs",
    "risks", "unknowns", "recommended_next_review", "reason", "evidence_gap",
    "rationale", "notes", "options",
}


class ModelOverreach(ExecutiveError):
    """A model draft attempted to author something only code or a person
    may author. Recorded as a typed fact, never silently dropped."""


def _unexpected_fields(draft: dict) -> list:
    return sorted({key for key in (draft or {})
                   if key not in MODEL_ALLOWED_FIELDS})


class ExecutiveService:
    def __init__(self, path=DEFAULT_EXECUTIVE_PATH, *, product_service=None,
                 research_service=None, growth_service=None, crm_service=None,
                 decision_service=None, knowledge_service=None,
                 analytics_reader=None, prediction_ledger_path=None,
                 event_bus=None, llm_client=None, model_version="fake-model.v0"):
        self.store = ExecutiveStore(path)
        self.product = product_service
        self.research = research_service
        self.growth = growth_service
        self.crm = crm_service
        self.decisions = decision_service
        self.knowledge = knowledge_service
        self.analytics = analytics_reader
        self.prediction_ledger_path = prediction_ledger_path
        self.bus = event_bus
        self.llm_client = llm_client
        self.model_version = model_version

    # =====================================================================
    # Write path
    # =====================================================================
    def _stable_id(self, key: str) -> str:
        # The stable-id helper lives once in the kernel (T022).
        return _kernel_stable_id(self.store, key)

    def _record(self, event_type, *, actor_type, actor_id, source="cli",
                payload=None, provenance=None, idempotency_key=None,
                **fields) -> ExecutiveEvent:
        if event_type in HUMAN_ONLY_EVENTS and actor_type != "human":
            raise ExecutiveError(
                f"{event_type} is a human wall transition; "
                f"actor_type={actor_type!r} cannot emit it — the agent "
                "recommends, and the founder decides")
        candidate = ExecutiveEvent(
            event_type=event_type, actor_type=actor_type, actor_id=actor_id,
            source=source, payload=json_normalize(dict(payload or {})),
            provenance=json_normalize(dict(provenance or {})),
            idempotency_key=idempotency_key, **fields)
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.content_fingerprint() != candidate.content_fingerprint():
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was already "
                        "used for different content")
                return existing
        ok, reason = validate_executive_event(self.get_state(), candidate)
        if not ok:
            raise ExecutiveError(f"{event_type}: {reason}")
        return self.store.append(candidate)

    # =====================================================================
    # Candidates
    # =====================================================================
    def register_candidate(self, *, references, origin=None,
                           input_fingerprint=None, actor_type="agent",
                           actor_id="executive_agent", source="cli") -> str:
        refs = [validate_reference(r) for r in references]
        if not refs:
            raise ExecutiveError(
                "a decision candidate carries at least one reference — one "
                "that resolves to nothing is invalid")
        origin_id = (origin or {}).get("origin_id") or hashlib.sha256(
            "|".join(sorted(f"{r['kind']}:{r['ref_id']}" for r in refs))
            .encode()).hexdigest()[:16]
        key = f"candidate:{(origin or {}).get('kind', 'manual')}:{origin_id}"
        candidate_id = self._stable_id(key)
        self._record("executive.candidate_registered", actor_type=actor_type,
                     actor_id=actor_id, source=source, candidate_id=candidate_id,
                     subject_type="candidate", subject_id=candidate_id,
                     payload={"references": refs, "origin": dict(origin or {}),
                              "input_fingerprint": input_fingerprint},
                     idempotency_key=key)
        return candidate_id

    def dismiss_candidate(self, candidate_id: str, *, reason: str,
                          actor_id: str, actor_type="human"):
        return self._record(
            "executive.candidate_dismissed", actor_type=actor_type,
            actor_id=actor_id, candidate_id=candidate_id,
            subject_type="candidate", subject_id=candidate_id,
            payload={"reason": reason},
            idempotency_key=f"dismiss:{candidate_id}")

    def _absorb_candidate(self, candidate: dict, *, actor_id) -> str:
        key = f"candidate:{candidate['origin']['kind']}:" \
              f"{candidate['origin']['origin_id']}"
        existing = self.store.find_by_idempotency_key(key)
        if existing is not None:
            return existing.candidate_id
        candidate_id = self._stable_id(key)
        self._record("executive.candidate_registered", actor_type="system",
                     actor_id=actor_id, source="intake",
                     candidate_id=candidate_id, subject_type="candidate",
                     subject_id=candidate_id,
                     payload={"references": candidate["references"],
                              "origin": {**candidate["origin"],
                                         "intake_kind": candidate["intake_kind"],
                                         "title": candidate["title"]},
                              "input_fingerprint": candidate.get(
                                  "input_fingerprint")},
                     idempotency_key=key)
        self._record("executive.intake_scanned", actor_type="system",
                     actor_id=actor_id, source="intake",
                     candidate_id=candidate_id, subject_type="candidate",
                     subject_id=candidate_id,
                     payload={"intake_kind": candidate["intake_kind"],
                              "intake_version": candidate["intake_version"],
                              "candidate": True,
                              "disposition": "enters the index and a triage "
                                             "queue"},
                     idempotency_key=f"intake:{candidate['dedup_key']}")
        return candidate_id

    # =====================================================================
    # Intake — deterministic, idempotent, origin-citing
    # =====================================================================
    def intake_from_accepted_proposals(self, *, actor_id="executive_intake"
                                       ) -> list:
        if self.product is None:
            raise ExecutiveError("no product service configured for intake")
        created = []
        for proposal_id in self.product.accepted_proposals():
            proposal = self.product.get_proposal(proposal_id)
            state = self.product.get_state()
            decision_id = state.proposals[proposal_id].get("decision_id")
            candidate = candidate_from_accepted_proposal(
                proposal, proposal_id=proposal_id, decision_id=decision_id)
            created.append(self._absorb_candidate(candidate, actor_id=actor_id))
        return created

    def intake_from_expired_decision(self, decision_id: str, *,
                                     recorded_fingerprints: dict,
                                     current_fingerprints: dict, as_of: str,
                                     references=None,
                                     actor_id="executive_intake") -> str | None:
        expiry = expiry_check(recorded_fingerprints=recorded_fingerprints,
                              current_fingerprints=current_fingerprints,
                              as_of=as_of)
        if not expiry["expired"]:
            return None
        candidate = candidate_from_expired_decision(
            decision_id=decision_id, expiry=expiry,
            references=[validate_reference(r) for r in (references or [])])
        candidate_id = self._absorb_candidate(candidate, actor_id=actor_id)
        self._record("executive.decision_expired", actor_type="system",
                     actor_id=actor_id, source="intake",
                     candidate_id=candidate_id, subject_type="candidate",
                     subject_id=candidate_id,
                     payload={"decision_id": decision_id,
                              "changed_inputs": expiry["changed_inputs"],
                              "reasons": expiry["reasons"]},
                     decision_id=decision_id,
                     idempotency_key=f"expired:{decision_id}")
        return candidate_id

    # =====================================================================
    # Context
    # =====================================================================
    def build_context(self, candidate_id: str, *, decision_horizon: str,
                      decision_class: str, resolved_inputs: dict,
                      current_assumptions=None, external_constraints=None,
                      relevant_history=None, open_dependencies=None,
                      actor_type="agent", actor_id="executive_agent") -> str:
        state = self.get_state()
        if candidate_id not in state.candidates:
            raise ExecutiveError(f"no such candidate: {candidate_id}")
        context_id, prior = state.current_context(candidate_id)
        prior_fingerprints = None
        if prior is not None:
            prior_row = self._latest_context_payload(context_id)
            prior_fingerprints = (prior_row or {}).get("input_fingerprints")
        body = build_context(
            candidate_id=candidate_id, decision_horizon=decision_horizon,
            decision_class=decision_class, resolved_inputs=resolved_inputs,
            current_assumptions=current_assumptions,
            external_constraints=external_constraints,
            relevant_history=relevant_history,
            open_dependencies=open_dependencies,
            prior_fingerprints=prior_fingerprints)
        if context_id is None:
            key = f"context:{candidate_id}"
            context_id = self._stable_id(key)
            self._record("executive.context_built", actor_type=actor_type,
                         actor_id=actor_id, candidate_id=candidate_id,
                         context_id=context_id, context_version=1,
                         subject_type="context", subject_id=context_id,
                         payload=body, idempotency_key=key)
        else:
            version = prior["version"] + 1
            self._record("executive.context_rebuilt", actor_type=actor_type,
                         actor_id=actor_id, candidate_id=candidate_id,
                         context_id=context_id, context_version=version,
                         subject_type="context", subject_id=context_id,
                         payload=body,
                         idempotency_key=f"context-rebuild:{context_id}:{version}")
        return context_id

    def _latest_context_payload(self, context_id: str) -> dict | None:
        rows = [r for r in self.store.read_all()
                if r.context_id == context_id
                and r.event_type in ("executive.context_built",
                                     "executive.context_rebuilt")]
        return dict(rows[-1].payload) if rows else None

    # =====================================================================
    # Conflicts, debt, readiness — deterministic reads recorded as facts
    # =====================================================================
    def record_conflicts(self, candidate_id: str, facts: dict, *,
                         actor_id="executive_agent") -> dict:
        conflicts = detect_conflicts(facts)
        summary = conflict_summary(conflicts)
        for conflict in conflicts:
            conflict_id = self._stable_id(
                f"conflict:{candidate_id}:{conflict['kind']}:{conflict['detail']}")
            self._record("executive.conflict_detected", actor_type="system",
                         actor_id=actor_id, candidate_id=candidate_id,
                         conflict_id=conflict_id, subject_type="conflict",
                         subject_id=conflict_id, payload=conflict,
                         idempotency_key=f"conflict:{candidate_id}:"
                                         f"{conflict['kind']}:{conflict['detail']}")
        return summary

    def record_decision_debt(self, candidate_id: str, facts: dict, *,
                             actor_id="executive_agent") -> dict:
        items = derive_decision_debt(facts)
        for item in items:
            self._record("executive.decision_debt_recorded",
                         actor_type="system", actor_id=actor_id,
                         candidate_id=candidate_id, subject_type="candidate",
                         subject_id=candidate_id,
                         payload={"kind": item["kind"], "detail": item["detail"],
                                  "clears_when": item["clears_when"]},
                         idempotency_key=f"debt:{candidate_id}:{item['kind']}:"
                                         f"{item['detail']}")
        return debt_report(items)

    def clear_decision_debt(self, candidate_id: str, kind: str, *, reason: str,
                            actor_id="executive_agent"):
        return self._record(
            "executive.decision_debt_cleared", actor_type="system",
            actor_id=actor_id, candidate_id=candidate_id,
            subject_type="candidate", subject_id=candidate_id,
            payload={"kind": kind, "reason": reason},
            idempotency_key=f"debt-clear:{candidate_id}:{kind}")

    def compute_readiness(self, candidate_id: str, facts: dict, options=None, *,
                          record=True, actor_id="executive_agent") -> dict:
        block = readiness_block(facts, options=options)
        if record:
            self._record("executive.readiness_computed", actor_type="system",
                         actor_id=actor_id, candidate_id=candidate_id,
                         subject_type="candidate", subject_id=candidate_id,
                         payload={"unavailable_dimensions":
                                      block["unavailable_dimensions"],
                                  "decision_ready":
                                      block["dimensions"]["decision_readiness"]["value"],
                                  "impact": block["impact"]["value"],
                                  "reversibility": block["reversibility"]["value"]},
                         idempotency_key=f"readiness:{candidate_id}")
        return block

    # =====================================================================
    # Strategy + money declarations (human only)
    # =====================================================================
    def declare_alignment(self, candidate_id: str, level: str, *, actor_id: str,
                          rationale: str = "", actor_type="human"):
        return self._record(
            "executive.alignment_declared", actor_type=actor_type,
            actor_id=actor_id, candidate_id=candidate_id,
            subject_type="candidate", subject_id=candidate_id,
            payload={"level": level, "rationale": rationale},
            idempotency_key=f"alignment:{candidate_id}:{level}")

    def declare_budget(self, candidate_id: str, *, amount_available,
                       currency="USD", actor_id: str, actor_type="human"):
        return self._record(
            "executive.budget_declared", actor_type=actor_type,
            actor_id=actor_id, candidate_id=candidate_id,
            subject_type="candidate", subject_id=candidate_id,
            payload={"amount_available": amount_available, "currency": currency},
            idempotency_key=f"budget:{candidate_id}")

    # =====================================================================
    # Packages, options, escalation, no-recommendation
    # =====================================================================
    def draft_package(self, candidate_id: str, *, decision_question: str,
                      references, unknowns, dependencies=None, risks=None,
                      prediction_references=None, conflict_summary=None,
                      research_debt=None, spec_debt=None, decision_debt=None,
                      recommended_next_review: str = "",
                      contributing=None, evidence_label="UNKNOWN",
                      provenance=None, actor_type="agent",
                      actor_id="executive_agent") -> str:
        state = self.get_state()
        context_id, context = state.current_context(candidate_id)
        if context_id is None:
            raise ExecutiveError(
                "a package renders a context; build the context first")
        refs = [validate_reference(r) for r in references]
        provenance = provenance or cross_agent_provenance(
            versions={}, contributing=contributing or [])
        body = build_package(
            decision_question=decision_question, references=refs,
            unknowns=unknowns, dependencies=dependencies, risks=risks,
            prediction_references=prediction_references,
            conflict_summary=conflict_summary, research_debt=research_debt,
            spec_debt=spec_debt, decision_debt=decision_debt,
            recommended_next_review=recommended_next_review,
            provenance=provenance, evidence_label=evidence_label)
        assert_not_readiness_shaped(body, where="package body")
        key = f"package:{candidate_id}:{context['version']}"
        package_id = self._stable_id(key)
        self._record("executive.package_drafted", actor_type=actor_type,
                     actor_id=actor_id, candidate_id=candidate_id,
                     context_id=context_id, context_version=context["version"],
                     package_id=package_id, package_version=1,
                     subject_type="package", subject_id=package_id,
                     payload=body, idempotency_key=key)
        return package_id

    def add_option(self, package_id: str, *, label: str, benefits, costs, risks,
                   unknowns, dependencies=None, reversibility: str,
                   evidence_label="UNKNOWN", actor_type="agent",
                   actor_id="executive_agent") -> str:
        state = self.get_state()
        package = state.packages.get(package_id)
        if package is None:
            raise ExecutiveError(f"no such package: {package_id}")
        option = build_option(
            label=label, benefits=benefits, costs=costs, risks=risks,
            unknowns=unknowns, dependencies=dependencies,
            reversibility=reversibility, evidence_label=evidence_label)
        key = f"option:{package_id}:{package['version']}:{label}"
        option_id = self._stable_id(key)
        self._record("executive.option_recorded", actor_type=actor_type,
                     actor_id=actor_id, package_id=package_id,
                     package_version=package["version"], option_id=option_id,
                     subject_type="option", subject_id=option_id,
                     payload={**option, "label": label}, idempotency_key=key)
        return option_id

    def record_no_recommendation(self, package_id: str, *, reason: str,
                                 evidence_gap: str, review_date: str,
                                 actor_type="agent",
                                 actor_id="executive_agent"):
        body = build_no_recommendation(reason=reason, evidence_gap=evidence_gap,
                                       review_date=review_date)
        state = self.get_state()
        package = state.packages.get(package_id)
        if package is None:
            raise ExecutiveError(f"no such package: {package_id}")
        return self._record(
            "executive.no_recommendation_recorded", actor_type=actor_type,
            actor_id=actor_id, package_id=package_id,
            package_version=package["version"], subject_type="package",
            subject_id=package_id, payload=body,
            idempotency_key=f"no-rec:{package_id}:{package['version']}")

    def assign_escalation(self, package_id: str, readiness: dict, *,
                          conflict_summary=None, decision_class: str = "operational",
                          actor_type="agent", actor_id="executive_agent") -> dict:
        from intent_engine.executive.packages import assign_escalation as _assign
        result = _assign(readiness_block=readiness, impact=readiness["impact"],
                         conflict_summary=conflict_summary or {"total": 0},
                         decision_class=decision_class)
        state = self.get_state()
        package = state.packages.get(package_id)
        if package is None:
            raise ExecutiveError(f"no such package: {package_id}")
        self._record("executive.escalation_assigned", actor_type=actor_type,
                     actor_id=actor_id, package_id=package_id,
                     package_version=package["version"], subject_type="package",
                     subject_id=package_id, payload=result,
                     idempotency_key=f"escalation:{package_id}:{package['version']}")
        return result

    # =====================================================================
    # Review, override, decision link, outcome — the founder's side
    # =====================================================================
    def request_review(self, package_id: str, *, actor_type="agent",
                       actor_id="executive_agent"):
        state = self.get_state()
        package = state.packages.get(package_id)
        if package is None:
            raise ExecutiveError(f"no such package: {package_id}")
        return self._record(
            "executive.review_requested", actor_type=actor_type,
            actor_id=actor_id, package_id=package_id,
            package_version=package["version"], subject_type="package",
            subject_id=package_id, payload={},
            idempotency_key=f"review-req:{package_id}:{package['version']}")

    def record_review(self, package_id: str, *, disposition: str, actor_id: str,
                      notes: str = "", chosen_option_id=None, merged_into=None,
                      deferred_until_condition=None, actor_type="human"):
        assert_recommendation_language(notes, where="review notes")
        state = self.get_state()
        package = state.packages.get(package_id)
        if package is None:
            raise ExecutiveError(f"no such package: {package_id}")
        return self._record(
            "executive.reviewed", actor_type=actor_type, actor_id=actor_id,
            source="founder_review", package_id=package_id,
            package_version=package["version"], subject_type="package",
            subject_id=package_id,
            payload={"disposition": disposition, "notes": notes,
                     "chosen_option_id": chosen_option_id,
                     "merged_into": merged_into,
                     "deferred_until_condition": deferred_until_condition,
                     "reviewer": actor_id},
            idempotency_key=f"review:{package_id}:{package['version']}")

    def record_override(self, package_id: str, *, chosen_option_id: str,
                        preferred_option_id: str, reason: str, actor_id: str,
                        actor_type="human"):
        """The founder chose against the recorded preference. Both are
        kept, immutably, with the reason. Later prediction scoring reads
        these; nothing is overwritten."""
        state = self.get_state()
        package = state.packages.get(package_id)
        if package is None:
            raise ExecutiveError(f"no such package: {package_id}")
        return self._record(
            "executive.override_recorded", actor_type=actor_type,
            actor_id=actor_id, package_id=package_id,
            package_version=package["version"], subject_type="package",
            subject_id=package_id,
            payload={"chosen_option_id": chosen_option_id,
                     "preferred_option_id": preferred_option_id,
                     "reason": reason},
            idempotency_key=f"override:{package_id}:{package['version']}")

    def link_decision(self, package_id: str, decision_id: str, *, actor_id: str,
                      actor_type="human"):
        """The Decision Record is created by the founder through
        DecisionService. This records the reference and nothing else — the
        decision store is never written or mirrored here."""
        if self.decisions is not None:
            if self.decisions.get_decision(decision_id) is None:
                raise ExecutiveError(
                    f"no such Decision Record: {decision_id} — a decision is "
                    "created through DecisionService by a person, and this "
                    "subsystem only references one")
        return self._record(
            "executive.decision_linked", actor_type=actor_type,
            actor_id=actor_id, package_id=package_id, decision_id=decision_id,
            subject_type="package", subject_id=package_id,
            payload={"decision_id": decision_id},
            idempotency_key=f"decision-link:{package_id}:{decision_id}")

    def observe_outcome(self, package_id: str, *, observation: str,
                        actor_id="executive_agent", actor_type="human"):
        state = self.get_state()
        package = state.packages.get(package_id)
        if package is None:
            raise ExecutiveError(f"no such package: {package_id}")
        return self._record(
            "executive.outcome_observed", actor_type=actor_type,
            actor_id=actor_id, package_id=package_id,
            decision_id=package.get("decision_id"), subject_type="package",
            subject_id=package_id, payload={"observation": observation},
            idempotency_key=f"outcome:{package_id}")

    def request_knowledge_candidate(self, package_id: str, *, content: str,
                                    actor_id="executive_agent"):
        assert_recommendation_language(content, where="knowledge candidate")
        return self._record(
            "executive.knowledge_candidate_requested", actor_type="agent",
            actor_id=actor_id, package_id=package_id, subject_type="package",
            subject_id=package_id, payload={"content": content},
            idempotency_key=f"knowledge:{package_id}")

    # =====================================================================
    # Decision graph edges
    # =====================================================================
    def record_edge(self, edge: str, from_id: str, to_id: str, *,
                    reason: str = "", actor_type="agent",
                    actor_id="executive_agent"):
        if edge not in RECORDED_EDGES:
            raise ExecutiveError(f"unknown recorded edge type: {edge!r}")
        return self._record(
            "executive.decision_edge_recorded", actor_type=actor_type,
            actor_id=actor_id, subject_type="edge",
            subject_id=f"{edge}:{from_id}:{to_id}",
            payload={"edge": edge, "from": from_id, "to": to_id,
                     "reason": reason},
            idempotency_key=f"edge:{edge}:{from_id}:{to_id}")

    # =====================================================================
    # Model-assisted drafting — isolated, versioned, budgeted, recorded
    # =====================================================================
    def draft_with_model(self, kind: str, *, context: str,
                         actor_id="executive_agent", **refs) -> dict:
        if kind not in PROMPT_VERSIONS:
            raise ExecutiveError(f"unknown draft kind: {kind!r}")
        if self.llm_client is None:
            raise ExecutiveError("no model client is configured for drafting")
        provenance = model_provenance(
            PROMPT_VERSIONS[kind], self.model_version,
            authority="a candidate; a rule or a person accepts it")
        try:
            draft = self.llm_client.call_tool(
                prompt_version=PROMPT_VERSIONS[kind], user_message=context)
        except Exception as exc:                            # noqa: BLE001
            self._record("executive.draft_failed", actor_type="system",
                         actor_id="model_boundary", source="system",
                         subject_type="draft",
                         payload={"kind": kind, "error_type": type(exc).__name__,
                                  "note": "a model failure is a typed fact, "
                                          "not an empty success"},
                         provenance=provenance, **refs)
            raise

        forbidden = find_forbidden_fields(draft)
        unexpected = _unexpected_fields(draft)
        if forbidden or unexpected:
            self._record("executive.draft_rejected", actor_type="system",
                         actor_id="model_boundary", source="system",
                         subject_type="draft",
                         payload={"kind": kind, "forbidden_fields": forbidden,
                                  "unexpected_fields": unexpected,
                                  "note": "a model draft that authors a "
                                          "reference, an identifier, a "
                                          "readiness, or a score is rejected "
                                          "whole"},
                         provenance=provenance, **refs)
            raise ModelOverreach(
                f"model draft for {kind!r} attempted to author "
                f"{forbidden + unexpected} — prose only")

        assert_not_readiness_shaped(draft, where=f"model draft ({kind})")
        return {"draft": draft, "provenance": provenance, "candidate": True}

    # =====================================================================
    # Reads
    # =====================================================================
    def get_state(self) -> ExecutiveState:
        return fold_executive(self.store.read_all(), validate=True)

    def get_index(self):
        return build_index(self.store.read_all())

    def _decision_resolver(self):
        if self.decisions is None:
            return None

        def resolve(decision_id):
            record = self.decisions.get_decision(decision_id)
            if record is None:
                return {"decision_id": decision_id,
                        "resolution": "DecisionService holds no such record"}
            state = self.decisions.get_current_state(decision_id)
            return {"resolved_by": "decision_service.get_current_state",
                    "decision_id": decision_id,
                    "decision_status": state.decision_status,
                    "execution_status": state.execution_status,
                    "evaluation_status": state.evaluation_status,
                    "owner": state.owner}
        return resolve

    def _reference_resolver(self):
        def resolve(ref):
            kind = ref.get("kind")
            if kind in (REF_PROPOSAL, REF_OPPORTUNITY) and self.product is not None:
                try:
                    index = self.product.get_index()
                    if kind == REF_PROPOSAL:
                        return {"resolved_by": "product.get_proposal",
                                "present": ref["ref_id"] in index.proposals}
                    return {"resolved_by": "product opportunity index",
                            "present": ref["ref_id"] in index.opportunities}
                except Exception:                           # noqa: BLE001
                    return False
            if kind == REF_RESEARCH_PACKAGE and self.research is not None:
                return {"resolved_by": "research.get_package",
                        "request_id": ref.get("request_id")}
            return {"resolved_by": "reference kind owned by another subsystem",
                    "kind": kind, "ref_id": ref.get("ref_id")}
        return resolve

    def lineage(self, package_id: str) -> dict:
        return self.get_index().lineage(
            package_id, decision_resolver=self._decision_resolver(),
            reference_resolver=self._reference_resolver())

    def trace(self, package_id: str) -> dict:
        return trace_package(self.get_index(), package_id)

    def assert_no_dead_ends(self) -> dict:
        return assert_no_dead_ends(self.get_index())

    def triage_queues(self, *, as_of: str) -> dict:
        """The primary artifact: three partitioned, ordered queues."""
        index = self.get_index()
        entries = []
        for candidate in index.open_candidates():
            cid = candidate["candidate_id"]
            context_id, context = self._context_for(index, cid)
            readiness_row = self._latest_readiness(cid)
            debt = [i for i in index.debt.get(cid, []) if not i["cleared"]]
            conflicts = index.conflicts_for(cid)
            horizon = (context or {}).get("decision_horizon", "short_term")
            decision_class = (context or {}).get("decision_class", "operational")
            # The queue is DERIVED from (horizon, class) deterministically
            # rather than read from a stored field: assign_queue is a pure
            # table, so recomputing it here keeps the partition reproducible
            # from the folded state and cannot drift from a stale copy.
            from intent_engine.executive.records import assign_queue
            queue, _ = assign_queue(horizon, decision_class) if context \
                else ("operational", "")
            rankable = readiness_row is not None and context is not None
            gaps = []
            if context is None:
                gaps.append("no decision context has been built")
            if readiness_row is None:
                gaps.append("readiness has not been computed")
            entries.append(build_entry(
                candidate_id=cid, queue=queue,
                decision_ready=bool(readiness_row and
                                    readiness_row.get("decision_ready")),
                escalation=self._latest_escalation(index, cid),
                conflict_count=len(conflicts),
                impact=(readiness_row or {}).get("impact"),
                open_debt_count=len(debt),
                age_days=decision_age(candidate["created_at"], as_of)["age_days"],
                horizon=horizon, decision_class=decision_class,
                rankable=rankable, gaps=gaps))
        return build_queues(entries)

    def _context_for(self, index, candidate_id):
        for context_id, context in sorted(index.contexts.items()):
            if context["candidate_id"] == candidate_id:
                return context_id, context
        return None, None

    def _latest_readiness(self, candidate_id: str) -> dict | None:
        rows = [r for r in self.store.for_candidate(candidate_id)
                if r.event_type == "executive.readiness_computed"]
        return dict(rows[-1].payload) if rows else None

    def _latest_escalation(self, index, candidate_id: str) -> str | None:
        for package_id, package in sorted(index.packages.items()):
            if package["candidate_id"] == candidate_id:
                return package.get("escalation")
        return None

    def health_dashboard(self, *, as_of: str) -> dict:
        index = self.get_index()
        research_debt = spec_debt = 0
        return health_dashboard(index, research_debt=research_debt,
                                spec_debt=spec_debt)

    def portfolio(self, *, as_of: str, portfolio_id: str = None) -> dict:
        index = self.get_index()
        rollup = None
        if self.product is not None and portfolio_id is not None:
            try:
                rollup = self.product.portfolio(portfolio_id,
                                                as_of=as_of)["rollup"]
            except Exception:                               # noqa: BLE001
                rollup = None
        return executive_portfolio(index, product_rollup=rollup)

    def get_package(self, package_id: str, version=None) -> dict:
        rows = [r for r in self.store.for_package(package_id)
                if r.event_type in ("executive.package_drafted",
                                    "executive.package_revised")]
        if not rows:
            raise KeyError(f"no such package: {package_id}")
        if version is not None:
            for row in rows:
                if row.package_version == version:
                    return dict(row.payload)
            raise KeyError(f"no version {version} of package {package_id}")
        return dict(rows[-1].payload)

    def list_review_queue(self) -> list:
        index = self.get_index()
        return [{"package_id": p["package_id"],
                 "package_version": p["version"],
                 "candidate_id": p["candidate_id"]}
                for p in index.review_packages()]

    def get_history(self, **selector) -> list:
        rows = self.store.read_all()
        for field_name, value in selector.items():
            rows = [r for r in rows if getattr(r, field_name) == value]
        return rows

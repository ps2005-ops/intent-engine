"""ProductService (T020) — the only write path.

The agent drafts, indexes, scores, and proposes. It never accepts,
rejects, merges, defers, promotes, schedules, creates a Decision Record,
starts an experiment, writes another subsystem's store, or writes
`ROADMAP.md`.

Every other subsystem is READ through its own public surface and is never
reimplemented here: the Evidence Index for evidence, T019 packages for
coverage and research debt, T018 for experiment labels, T014 for customer
facts, T015 for metrics, T016 for knowledge items, and DecisionService
for decisions.
"""
from __future__ import annotations

import hashlib

from intent_engine.core.decision_ids import new_ulid
from intent_engine.product.bundles import assemble_bundle
from intent_engine.product.index import build_index
from intent_engine.product.intake import (
    intake_candidates_from_crm, intake_candidates_from_growth,
    intake_candidates_from_research_debt,
)
from intent_engine.product.portfolio import (
    balance_report, executive_summary, portfolio_rollup, readiness_report,
)
from intent_engine.product.problems import (
    assert_solution_free, build_problem_statement, problem_dedup_key,
    validate_reference,
)
from intent_engine.product.proposals import build_proposal, validate_retirement
from intent_engine.product.records import (
    ALIGNMENT_LEVELS_DOC, DECISION_DEBT_KINDS, HUMAN_ONLY_EVENTS,
    PROPOSAL_EDGES, REF_CRM_FACT, REF_EXPERIMENT, REF_RESEARCH_CONCLUSION,
    REF_RESEARCH_DEBT, SPEC_DEBT_KINDS, STATUS_ACCEPTED,
    STATUS_REVIEW_REQUESTED, ProductError, ProductEvent,
    assert_product_language, find_forbidden_fields, json_normalize,
)
from intent_engine.product.roadmap_diff import (
    build_roadmap_candidate, render_roadmap_diff,
)
from intent_engine.product.scoring import (
    ALIGNMENT_LEVELS, assert_not_score_shaped, score_block,
)
from intent_engine.product.specs import (
    build_spec_draft, derive_spec_debt, spec_debt_report,
)
from intent_engine.product.state import (
    ProductState, fold_product, validate_product_event,
)
from intent_engine.product.store import DEFAULT_PRODUCT_PATH, ProductStore

PROMPT_VERSIONS = {
    "problem_statement": "product_problem_prose.v1",
    "candidate_solutions": "product_candidate_solutions.v1",
    "spec_wording": "product_spec_wording.v1",
}

# A model may return prose in these fields and nothing else. A whitelist,
# not a blacklist: a field nobody anticipated is rejected rather than
# quietly stored.
MODEL_ALLOWED_FIELDS = {
    "statement", "why_now", "what_changes_if_ignored", "candidate_solution",
    "tradeoffs", "risks", "known", "unknown", "assumptions", "open_questions",
    "goals", "non_goals", "requirements", "constraints", "acceptance_criteria",
    "unknowns", "dependencies", "options", "notes",
}


class ModelOverreach(ProductError):
    """A model draft attempted to author something only code or a person
    may author. Recorded as a typed fact, never silently dropped."""


def _unexpected_fields(draft: dict) -> list:
    return sorted({key for key in (draft or {})
                   if key not in MODEL_ALLOWED_FIELDS})


class ProductService:
    def __init__(self, path=DEFAULT_PRODUCT_PATH, *, research_service=None,
                 growth_service=None, crm_service=None, decision_service=None,
                 knowledge_service=None, analytics_reader=None,
                 event_bus=None, llm_client=None,
                 model_version="fake-model.v0"):
        self.store = ProductStore(path)
        self.research = research_service
        self.growth = growth_service
        self.crm = crm_service
        self.decisions = decision_service
        self.knowledge = knowledge_service
        self.analytics = analytics_reader
        self.bus = event_bus
        self.llm_client = llm_client
        self.model_version = model_version

    # =====================================================================
    # Write path
    # =====================================================================
    def _stable_id(self, key: str) -> str:
        """One helper, used everywhere an id is minted alongside an
        idempotency key. A retry returns the SAME id."""
        existing = self.store.find_by_idempotency_key(key)
        return existing.subject_id if existing is not None else new_ulid()

    def _record(self, event_type, *, actor_type, actor_id, source="cli",
                payload=None, provenance=None, idempotency_key=None,
                **fields) -> ProductEvent:
        if event_type in HUMAN_ONLY_EVENTS and actor_type != "human":
            raise ProductError(
                f"{event_type} is a human wall transition; "
                f"actor_type={actor_type!r} cannot emit it — the agent "
                "proposes, and the founder disposes")
        candidate = ProductEvent(
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
        ok, reason = validate_product_event(self.get_state(), candidate)
        if not ok:
            raise ProductError(f"{event_type}: {reason}")
        return self.store.append(candidate)

    # =====================================================================
    # Portfolio, themes, initiatives — human-declared
    # =====================================================================
    def create_portfolio(self, name: str, *, actor_id: str,
                         actor_type="human") -> str:
        key = f"portfolio:{name}"
        portfolio_id = self._stable_id(key)
        self._record("product.portfolio_created", actor_type=actor_type,
                     actor_id=actor_id, portfolio_id=portfolio_id,
                     subject_type="portfolio", subject_id=portfolio_id,
                     payload={"name": name}, idempotency_key=key)
        return portfolio_id

    def declare_theme(self, portfolio_id: str, name: str, *, actor_id: str,
                      rationale: str = "", actor_type="human") -> str:
        """Strategic themes are human-created. An agent may report that a
        theme is empty; it does not decide what the themes are."""
        key = f"theme:{portfolio_id}:{name}"
        theme_id = self._stable_id(key)
        self._record("product.theme_declared", actor_type=actor_type,
                     actor_id=actor_id, portfolio_id=portfolio_id,
                     theme_id=theme_id, subject_type="theme",
                     subject_id=theme_id,
                     payload={"name": name, "rationale": rationale,
                              "declared_by": actor_id},
                     idempotency_key=key)
        return theme_id

    def create_initiative(self, theme_id: str, name: str, *, actor_id: str,
                          actor_type="human") -> str:
        state = self.get_state()
        theme = state.themes.get(theme_id)
        if theme is None:
            raise ProductError(f"no such strategic theme: {theme_id}")
        key = f"initiative:{theme_id}:{name}"
        initiative_id = self._stable_id(key)
        self._record("product.initiative_created", actor_type=actor_type,
                     actor_id=actor_id, portfolio_id=theme["portfolio_id"],
                     theme_id=theme_id, initiative_id=initiative_id,
                     subject_type="initiative", subject_id=initiative_id,
                     payload={"name": name}, idempotency_key=key)
        return initiative_id

    def declare_alignment(self, subject_id: str, level: str, *, actor_id: str,
                          rationale: str = "", theme_id: str = None,
                          actor_type="human"):
        """Strategic alignment comes from a person. With no declaration
        recorded, the dimension stays UNAVAILABLE."""
        if level not in ALIGNMENT_LEVELS:
            raise ProductError(
                f"alignment level {level!r} is outside the recorded "
                f"vocabulary {sorted(ALIGNMENT_LEVELS)}")
        return self._record(
            "product.alignment_declared", actor_type=actor_type,
            actor_id=actor_id, theme_id=theme_id, subject_type="alignment",
            subject_id=subject_id,
            payload={"level": level, "rationale": rationale,
                     "declared_by": actor_id, "levels_doc": ALIGNMENT_LEVELS_DOC},
            idempotency_key=f"alignment:{subject_id}:{level}")

    def declare_balance_target(self, portfolio_id: str, bands: dict, *,
                               actor_id: str, actor_type="human"):
        """What counts as a lopsided portfolio is a strategy judgment, so
        the bands are declared rather than assumed."""
        return self._record(
            "product.balance_target_declared", actor_type=actor_type,
            actor_id=actor_id, portfolio_id=portfolio_id,
            subject_type="balance_target", subject_id=portfolio_id,
            payload={"bands": bands, "declared_by": actor_id},
            idempotency_key=f"balance:{portfolio_id}")

    # =====================================================================
    # Problems
    # =====================================================================
    def record_problem(self, *, statement: str, evidence_references,
                       why_now: str, what_changes_if_ignored: str,
                       first_observed_at: str, affected_customers=None,
                       scope: str = "", actor_type="agent",
                       actor_id="product_agent", source="cli") -> dict:
        """Deterministic exact-match dedup: an identical dedup_key returns
        the PRIOR problem rather than creating a second record of it."""
        assert_solution_free(statement)
        dedup_key = problem_dedup_key(statement, scope)
        state = self.get_state()
        prior = state.dedup_keys.get(dedup_key)
        if prior is not None:
            return {"problem_id": prior, "reused": True,
                    "dedup_key": dedup_key}

        body = build_problem_statement(
            statement=statement, evidence_references=evidence_references,
            why_now=why_now, what_changes_if_ignored=what_changes_if_ignored,
            affected_customers=affected_customers, scope=scope,
            first_observed_at=first_observed_at)
        key = f"problem:{dedup_key}"
        problem_id = self._stable_id(key)
        self._record("product.problem_recorded", actor_type=actor_type,
                     actor_id=actor_id, source=source, problem_id=problem_id,
                     subject_type="problem", subject_id=problem_id,
                     payload=body, idempotency_key=key)
        return {"problem_id": problem_id, "reused": False,
                "dedup_key": dedup_key}

    def record_problem_rejection(self, *, reason: str, statement: str = "",
                                 actor_type="system",
                                 actor_id="problem_wall"):
        """A refusal is a recorded fact, so the log shows what was refused
        and why rather than showing nothing at all."""
        return self._record(
            "product.problem_rejected", actor_type=actor_type,
            actor_id=actor_id, source="system", subject_type="problem",
            payload={"reason": reason, "statement": statement})

    def link_problem_evidence(self, problem_id: str, evidence_references, *,
                              actor_type="agent", actor_id="product_agent"):
        refs = [validate_reference(r) for r in evidence_references]
        digest = hashlib.sha256(
            "|".join(sorted(f"{r['kind']}:{r['ref_id']}" for r in refs))
            .encode()).hexdigest()[:16]
        return self._record(
            "product.problem_evidence_linked", actor_type=actor_type,
            actor_id=actor_id, problem_id=problem_id, subject_type="problem",
            subject_id=problem_id, payload={"evidence_references": refs},
            idempotency_key=f"problem-evidence:{problem_id}:{digest}")

    def split_problem(self, problem_id: str, children, *, reason: str,
                      actor_type="agent", actor_id="product_agent"):
        return self._record(
            "product.problem_split", actor_type=actor_type, actor_id=actor_id,
            problem_id=problem_id, subject_type="problem",
            subject_id=problem_id,
            payload={"children": sorted(children), "reason": reason},
            idempotency_key=f"problem-split:{problem_id}")

    def merge_problem(self, problem_id: str, merged_into: str, *, reason: str,
                      actor_type="agent", actor_id="product_agent"):
        return self._record(
            "product.problem_merged", actor_type=actor_type,
            actor_id=actor_id, problem_id=problem_id, subject_type="problem",
            subject_id=problem_id,
            payload={"merged_into": merged_into, "reason": reason},
            idempotency_key=f"problem-merge:{problem_id}:{merged_into}")

    def retire_problem(self, problem_id: str, *, reason: str, actor_id: str,
                       actor_type="human"):
        return self._record(
            "product.problem_retired", actor_type=actor_type,
            actor_id=actor_id, problem_id=problem_id, subject_type="problem",
            subject_id=problem_id, payload={"reason": reason},
            idempotency_key=f"problem-retire:{problem_id}")

    def supersede_problem(self, problem_id: str, successor: str, *,
                          reason: str, actor_type="agent",
                          actor_id="product_agent"):
        return self._record(
            "product.problem_superseded", actor_type=actor_type,
            actor_id=actor_id, problem_id=problem_id, subject_type="problem",
            subject_id=problem_id,
            payload={"successor": successor, "reason": reason},
            idempotency_key=f"problem-supersede:{problem_id}:{successor}")

    # =====================================================================
    # Opportunities
    # =====================================================================
    def register_opportunity(self, problem_id: str, *, title: str,
                             evidence_references, work_category="unknown",
                             origin=None, actor_type="agent",
                             actor_id="product_agent", source="cli") -> str:
        refs = [validate_reference(r) for r in evidence_references]
        if not refs:
            raise ProductError(
                "an opportunity with no evidence reference is invalid — the "
                "index rejects orphans")
        assert_product_language(title, where="opportunity title")
        key = f"opportunity:{problem_id}:{title}"
        opportunity_id = self._stable_id(key)
        self._record("product.opportunity_registered", actor_type=actor_type,
                     actor_id=actor_id, source=source, problem_id=problem_id,
                     opportunity_id=opportunity_id, subject_type="opportunity",
                     subject_id=opportunity_id,
                     payload={"title": title, "evidence_references": refs,
                              "work_category": work_category,
                              "origin": dict(origin or {}), "candidate": True},
                     idempotency_key=key)
        return opportunity_id

    def link_opportunity_evidence(self, opportunity_id: str,
                                  evidence_references, *, actor_type="agent",
                                  actor_id="product_agent", **refs):
        validated = [validate_reference(r) for r in evidence_references]
        digest = hashlib.sha256(
            "|".join(sorted(f"{r['kind']}:{r['ref_id']}" for r in validated))
            .encode()).hexdigest()[:16]
        return self._record(
            "product.opportunity_evidence_linked", actor_type=actor_type,
            actor_id=actor_id, opportunity_id=opportunity_id,
            subject_type="opportunity", subject_id=opportunity_id,
            payload={"evidence_references": validated},
            idempotency_key=f"opportunity-evidence:{opportunity_id}:{digest}",
            **refs)

    def link_research_package(self, opportunity_id: str, *, request_id: str,
                              package_id: str, actor_type="agent",
                              actor_id="product_agent"):
        """A reference into T019, resolved through ResearchService. The
        package's coverage and debt are read there, never recomputed."""
        return self.link_opportunity_evidence(
            opportunity_id,
            [{"kind": REF_RESEARCH_CONCLUSION, "ref_id": package_id,
              "request_id": request_id}],
            actor_type=actor_type, actor_id=actor_id,
            research_request_id=request_id)

    def attach_opportunity(self, opportunity_id: str, initiative_id: str, *,
                           actor_type="agent", actor_id="product_agent"):
        state = self.get_state()
        initiative = state.initiatives.get(initiative_id)
        if initiative is None:
            raise ProductError(f"no such initiative: {initiative_id}")
        return self._record(
            "product.opportunity_attached", actor_type=actor_type,
            actor_id=actor_id, opportunity_id=opportunity_id,
            initiative_id=initiative_id, theme_id=initiative["theme_id"],
            portfolio_id=initiative["portfolio_id"],
            subject_type="opportunity", subject_id=opportunity_id, payload={},
            idempotency_key=f"attach:{opportunity_id}:{initiative_id}")

    def supersede_opportunity(self, opportunity_id: str, successor: str, *,
                              reason: str, actor_type="agent",
                              actor_id="product_agent"):
        return self._record(
            "product.opportunity_superseded", actor_type=actor_type,
            actor_id=actor_id, opportunity_id=opportunity_id,
            subject_type="opportunity", subject_id=opportunity_id,
            payload={"successor": successor, "reason": reason},
            idempotency_key=f"opportunity-supersede:{opportunity_id}")

    def reject_opportunity(self, opportunity_id: str, *, reason: str,
                           actor_id: str, actor_type="human"):
        return self._record(
            "product.opportunity_rejected", actor_type=actor_type,
            actor_id=actor_id, opportunity_id=opportunity_id,
            subject_type="opportunity", subject_id=opportunity_id,
            payload={"reason": reason},
            idempotency_key=f"opportunity-reject:{opportunity_id}")

    # =====================================================================
    # Intake — deterministic, idempotent, origin-citing
    # =====================================================================
    def _absorb_candidates(self, candidates, *, actor_id) -> list:
        created = []
        for candidate in candidates:
            problem_part = candidate["problem"]
            problem = self.record_problem(
                statement=problem_part["statement"],
                evidence_references=problem_part["evidence_references"],
                why_now=problem_part["why_now"],
                what_changes_if_ignored=problem_part["what_changes_if_ignored"],
                first_observed_at=problem_part["first_observed_at"],
                affected_customers=problem_part["affected_customers"],
                scope=problem_part["scope"], actor_type="system",
                actor_id=actor_id, source="intake")
            opportunity_part = candidate["opportunity"]
            opportunity_id = self.register_opportunity(
                problem["problem_id"], title=opportunity_part["title"],
                evidence_references=opportunity_part["evidence_references"],
                work_category=opportunity_part["work_category"],
                origin=opportunity_part["origin"], actor_type="system",
                actor_id=actor_id, source="intake")
            self._record("product.intake_scanned", actor_type="system",
                         actor_id=actor_id, source="intake",
                         problem_id=problem["problem_id"],
                         opportunity_id=opportunity_id,
                         subject_type="opportunity", subject_id=opportunity_id,
                         payload={"intake_kind": candidate["intake_kind"],
                                  "intake_version": candidate["intake_version"],
                                  "origin": opportunity_part["origin"],
                                  "candidate": True,
                                  "disposition": "enters the index and the "
                                                 "review queue"},
                         idempotency_key=f"intake:{candidate['dedup_key']}")
            created.append({"opportunity_id": opportunity_id,
                            "problem_id": problem["problem_id"],
                            "intake_kind": candidate["intake_kind"],
                            "problem_reused": problem["reused"]})
        return created

    def intake_from_research_package(self, *, request_id: str,
                                     package_id: str, as_of: str,
                                     actor_id="product_intake") -> list:
        if self.research is None:
            raise ProductError("no research service configured for intake")
        package = self.research.get_package(request_id, package_id)
        candidates = intake_candidates_from_research_debt(
            package, request_id=request_id, as_of=as_of)
        return self._absorb_candidates(candidates, actor_id=actor_id)

    def intake_from_growth_result(self, experiment_id: str, *, as_of: str,
                                  actor_id="product_intake") -> list:
        if self.growth is None:
            raise ProductError("no growth service configured for intake")
        result = self.growth.get_result(experiment_id)
        candidates = intake_candidates_from_growth(result, as_of=as_of)
        return self._absorb_candidates(candidates, actor_id=actor_id)

    def intake_from_crm(self, crm_entity_ids, *, as_of: str,
                        minimum_entities: int = 1,
                        actor_id="product_intake") -> list:
        if self.crm is None:
            raise ProductError("no CRM service configured for intake")
        facts = []
        for entity_id in sorted(set(crm_entity_ids)):
            for event in self.crm.get_history(entity_id):
                facts.append({"event_type": event.event_type,
                              "crm_entity_id": event.crm_entity_id,
                              "occurred_at": event.occurred_at})
        candidates = intake_candidates_from_crm(
            facts, as_of=as_of, minimum_entities=minimum_entities)
        return self._absorb_candidates(candidates, actor_id=actor_id)

    def record_intake_rejection(self, *, reason: str, origin: dict,
                                actor_id="product_intake"):
        return self._record("product.intake_rejected", actor_type="system",
                            actor_id=actor_id, source="intake",
                            subject_type="opportunity",
                            payload={"reason": reason, "origin": origin})

    # =====================================================================
    # Solution sets and proposals
    # =====================================================================
    def open_solution_set(self, problem_id: str, *, name: str,
                          actor_type="agent",
                          actor_id="product_agent") -> str:
        key = f"solution-set:{problem_id}:{name}"
        set_id = self._stable_id(key)
        self._record("product.solution_set_opened", actor_type=actor_type,
                     actor_id=actor_id, problem_id=problem_id,
                     subject_type="solution_set", subject_id=set_id,
                     payload={"name": name}, idempotency_key=key)
        return set_id

    def draft_proposal(self, opportunity_id: str, *, candidate_solution: str,
                       tradeoffs, risks, known, unknown, assumptions,
                       open_questions=None, dependencies=None,
                       work_category="unknown", solution_set_id=None,
                       evidence_label="UNKNOWN", provenance=None,
                       actor_type="agent", actor_id="product_agent") -> str:
        index = self.get_index()
        opportunity = index.opportunities.get(opportunity_id)
        if opportunity is None:
            raise ProductError(
                f"no such opportunity: {opportunity_id} — a proposal requires "
                "an indexed opportunity")
        if not opportunity["evidence_references"]:
            raise ProductError(
                f"opportunity {opportunity_id} carries no evidence reference, "
                "so it is not indexed and cannot carry a proposal")

        body = build_proposal(
            candidate_solution=candidate_solution, tradeoffs=tradeoffs,
            risks=risks, known=known, unknown=unknown, assumptions=assumptions,
            open_questions=open_questions, dependencies=dependencies,
            work_category=work_category, solution_set_id=solution_set_id,
            evidence_label=evidence_label)
        assert_not_score_shaped(body, where="proposal body")

        key = f"proposal:{opportunity_id}:{candidate_solution}"
        proposal_id = self._stable_id(key)
        self._record("product.proposal_drafted", actor_type=actor_type,
                     actor_id=actor_id, opportunity_id=opportunity_id,
                     problem_id=opportunity["problem_id"],
                     proposal_id=proposal_id, proposal_version=1,
                     subject_type="proposal", subject_id=proposal_id,
                     payload=body, provenance=dict(provenance or {}),
                     idempotency_key=key)
        return proposal_id

    def revise_proposal(self, proposal_id: str, *, candidate_solution: str,
                        tradeoffs, risks, known, unknown, assumptions,
                        open_questions=None, dependencies=None,
                        reason: str = "", evidence_label="UNKNOWN",
                        provenance=None, actor_type="agent",
                        actor_id="product_agent") -> int:
        """A revision is a NEW version. Prior versions stay retrievable, and
        a review of version N does not carry to version N+1."""
        state = self.get_state()
        proposal = state.proposals.get(proposal_id)
        if proposal is None:
            raise ProductError(f"no such proposal: {proposal_id}")
        version = proposal["version"] + 1
        body = build_proposal(
            candidate_solution=candidate_solution, tradeoffs=tradeoffs,
            risks=risks, known=known, unknown=unknown, assumptions=assumptions,
            open_questions=open_questions, dependencies=dependencies,
            work_category=proposal.get("work_category", "unknown"),
            solution_set_id=proposal.get("solution_set_id"),
            evidence_label=evidence_label)
        assert_not_score_shaped(body, where="proposal body")
        self._record("product.proposal_revised", actor_type=actor_type,
                     actor_id=actor_id, proposal_id=proposal_id,
                     opportunity_id=proposal["opportunity_id"],
                     problem_id=proposal["problem_id"],
                     proposal_version=version, subject_type="proposal",
                     subject_id=proposal_id,
                     payload={**body, "revision_reason": reason},
                     provenance=dict(provenance or {}),
                     idempotency_key=f"proposal-rev:{proposal_id}:{version}")
        return version

    def record_edge(self, edge: str, from_id: str, to_id: str, *,
                    reason: str = "", actor_type="agent",
                    actor_id="product_agent"):
        if edge not in PROPOSAL_EDGES:
            raise ProductError(f"unknown edge type: {edge!r}")
        return self._record(
            "product.proposal_edge_recorded", actor_type=actor_type,
            actor_id=actor_id, proposal_id=from_id, subject_type="edge",
            subject_id=f"{edge}:{from_id}:{to_id}",
            payload={"edge": edge, "from": from_id, "to": to_id,
                     "reason": reason},
            idempotency_key=f"edge:{edge}:{from_id}:{to_id}")

    def record_alternative(self, proposal_a: str, proposal_b: str, *,
                           reason: str = "", actor_type="agent",
                           actor_id="product_agent"):
        """`alternative_to` is symmetric, so both directions are recorded
        rather than one being inferred at read time."""
        self.record_edge("alternative_to", proposal_a, proposal_b,
                         reason=reason, actor_type=actor_type,
                         actor_id=actor_id)
        self.record_edge("alternative_to", proposal_b, proposal_a,
                         reason=reason, actor_type=actor_type,
                         actor_id=actor_id)

    def retire_proposal(self, proposal_id: str, *, reason: str,
                        detail: str = "", actor_type="agent",
                        actor_id="product_agent"):
        """Retirement is not rejection: a retired proposal was sound and
        stopped being so."""
        validate_retirement(reason)
        return self._record(
            "product.proposal_retired", actor_type=actor_type,
            actor_id=actor_id, proposal_id=proposal_id,
            subject_type="proposal", subject_id=proposal_id,
            payload={"reason": reason, "detail": detail},
            idempotency_key=f"proposal-retire:{proposal_id}:{reason}")

    def record_decision_debt(self, proposal_id: str, *, kind: str,
                             detail: str = "", actor_type="agent",
                             actor_id="product_agent"):
        """What this proposal is waiting on that only a person resolves."""
        if kind not in DECISION_DEBT_KINDS:
            raise ProductError(
                f"unknown decision-debt kind {kind!r} — one of "
                f"{sorted(DECISION_DEBT_KINDS)}")
        return self._record(
            "product.decision_debt_recorded", actor_type=actor_type,
            actor_id=actor_id, proposal_id=proposal_id,
            subject_type="proposal", subject_id=proposal_id,
            payload={"kind": kind, "detail": detail},
            idempotency_key=f"decision-debt:{proposal_id}:{kind}")

    # =====================================================================
    # Spec drafts
    # =====================================================================
    def draft_spec(self, proposal_id: str, sections: dict, *,
                   evidence_label="UNKNOWN", provenance=None,
                   actor_type="agent", actor_id="product_agent") -> str:
        state = self.get_state()
        proposal = state.proposals.get(proposal_id)
        if proposal is None:
            raise ProductError(f"no such proposal: {proposal_id}")
        draft = build_spec_draft(sections, evidence_label=evidence_label)
        key = f"spec:{proposal_id}:{proposal['version']}"
        spec_id = self._stable_id(key)
        self._record("product.spec_drafted", actor_type=actor_type,
                     actor_id=actor_id, proposal_id=proposal_id,
                     proposal_version=proposal["version"], spec_id=spec_id,
                     spec_version=1, subject_type="spec", subject_id=spec_id,
                     payload=draft, provenance=dict(provenance or {}),
                     idempotency_key=key)
        for item in derive_spec_debt(draft):
            self._record("product.spec_debt_recorded", actor_type="system",
                         actor_id="spec_debt", spec_id=spec_id,
                         proposal_id=proposal_id, subject_type="spec",
                         subject_id=spec_id, payload=item,
                         idempotency_key=f"spec-debt:{spec_id}:"
                                         f"{item['kind']}:{item['detail']}")
        return spec_id

    def record_spec_rejection(self, *, reason: str, proposal_id: str = None,
                              actor_type="system", actor_id="spec_wall"):
        return self._record("product.spec_rejected", actor_type=actor_type,
                            actor_id=actor_id, source="system",
                            proposal_id=proposal_id, subject_type="spec",
                            payload={"reason": reason})

    def record_spec_debt(self, spec_id: str, *, kind: str, detail: str = "",
                         actor_type="agent", actor_id="product_agent"):
        if kind not in SPEC_DEBT_KINDS:
            raise ProductError(
                f"unknown spec-debt kind {kind!r} — one of "
                f"{sorted(SPEC_DEBT_KINDS)}")
        return self._record(
            "product.spec_debt_recorded", actor_type=actor_type,
            actor_id=actor_id, spec_id=spec_id, subject_type="spec",
            subject_id=spec_id, payload={"kind": kind, "detail": detail},
            idempotency_key=f"spec-debt:{spec_id}:{kind}:{detail}")

    # =====================================================================
    # Review, decisions, execution — the founder's side
    # =====================================================================
    def request_review(self, proposal_id: str, *, actor_type="agent",
                       actor_id="product_agent"):
        state = self.get_state()
        proposal = state.proposals.get(proposal_id)
        if proposal is None:
            raise ProductError(f"no such proposal: {proposal_id}")
        spec_id, spec = state.spec_for_current_version(proposal_id)
        return self._record(
            "product.review_requested", actor_type=actor_type,
            actor_id=actor_id, proposal_id=proposal_id,
            proposal_version=proposal["version"], spec_id=spec_id,
            spec_version=spec["version"] if spec else None,
            subject_type="proposal", subject_id=proposal_id, payload={},
            idempotency_key=f"review-req:{proposal_id}:{proposal['version']}")

    def record_review(self, proposal_id: str, *, disposition: str,
                      actor_id: str, notes: str = "", merged_into=None,
                      deferred_until_condition=None, actor_type="human"):
        """HUMAN only, bound to an exact proposal version and an exact spec
        version. `merged_into` and `deferred` are first-class answers."""
        assert_product_language(notes, where="review notes")
        state = self.get_state()
        proposal = state.proposals.get(proposal_id)
        if proposal is None:
            raise ProductError(f"no such proposal: {proposal_id}")
        spec_id, spec = state.spec_for_current_version(proposal_id)
        return self._record(
            "product.reviewed", actor_type=actor_type, actor_id=actor_id,
            source="founder_review", proposal_id=proposal_id,
            proposal_version=proposal["version"], spec_id=spec_id,
            spec_version=spec["version"] if spec else None,
            subject_type="proposal", subject_id=proposal_id,
            payload={"disposition": disposition, "notes": notes,
                     "merged_into": merged_into,
                     "deferred_until_condition": deferred_until_condition,
                     "reviewer": actor_id},
            idempotency_key=f"review:{proposal_id}:{proposal['version']}")

    def link_decision(self, proposal_id: str, decision_id: str, *,
                      actor_id: str, actor_type="human"):
        """The Decision Record is created by the founder through
        DecisionService. This records the link and nothing else."""
        if self.decisions is not None:
            if self.decisions.get_decision(decision_id) is None:
                raise ProductError(
                    f"no such Decision Record: {decision_id} — a decision is "
                    "created through DecisionService by a person, and this "
                    "subsystem only references one")
        return self._record(
            "product.decision_linked", actor_type=actor_type,
            actor_id=actor_id, proposal_id=proposal_id,
            decision_id=decision_id, subject_type="proposal",
            subject_id=proposal_id, payload={"decision_id": decision_id},
            idempotency_key=f"decision-link:{proposal_id}:{decision_id}")

    def mark_execution_candidate(self, proposal_id: str, *, actor_id: str,
                                 actor_type="human"):
        state = self.get_state()
        proposal = state.proposals.get(proposal_id)
        if proposal is None:
            raise ProductError(f"no such proposal: {proposal_id}")
        return self._record(
            "product.execution_candidate_marked", actor_type=actor_type,
            actor_id=actor_id, proposal_id=proposal_id,
            decision_id=proposal.get("decision_id"), subject_type="proposal",
            subject_id=proposal_id,
            payload={"note": "an execution candidate is a proposal a person "
                             "accepted and linked to a Decision Record; this "
                             "subsystem executes nothing"},
            idempotency_key=f"execution-candidate:{proposal_id}")

    # =====================================================================
    # Scoring — deterministic, from recorded facts only
    # =====================================================================
    def _facts_for(self, proposal_id: str, *, as_of: str,
                   freshness_policy_days: int = 90) -> dict:
        index = self.get_index()
        state = self.get_state()
        proposal = state.proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"no such proposal: {proposal_id}")
        opportunity = index.opportunities[proposal["opportunity_id"]]
        problem = index.problem_index.problems[proposal["problem_id"]]
        body = self.get_proposal(proposal_id)

        refs = list(problem["evidence_references"]) \
            + list(opportunity["evidence_references"])

        experiments, crm_facts, timestamps = [], [], []
        coverage_totals, stances = {}, []
        for ref in refs:
            kind = ref.get("kind")
            if kind == REF_EXPERIMENT:
                label = ref.get("label")
                if self.growth is not None and ref.get("experiment_id"):
                    try:
                        label = self.growth.get_result(
                            ref["experiment_id"])["label"]
                    except Exception:                       # noqa: BLE001
                        pass
                experiments.append({"experiment_id": ref.get("experiment_id"),
                                    "label": label})
            elif kind == REF_CRM_FACT:
                crm_facts.append({
                    "crm_entity_id": ref.get("crm_entity_id"),
                    "event_type": ref["ref_id"].split(":", 1)[0]})
            elif kind == REF_RESEARCH_CONCLUSION and self.research is not None:
                try:
                    package = self.research.get_package(ref["request_id"],
                                                        ref["ref_id"])
                except Exception:                           # noqa: BLE001
                    continue
                totals = package["coverage"]["totals"]
                for bucket, count in totals.items():
                    coverage_totals[bucket] = coverage_totals.get(bucket, 0) \
                        + count
                for detail in package["coverage"]["per_question"].values():
                    stances.extend(s["stance"] for s in detail["stances"])
            if ref.get("observed_at"):
                timestamps.append(ref["observed_at"])
        if problem.get("first_observed_at"):
            timestamps.append(problem["first_observed_at"])

        spec_id, spec_state = state.spec_for_current_version(proposal_id)
        spec_body = self.get_spec(spec_id) if spec_id else {}
        dependencies = index.graph.dependencies_of(proposal_id)
        unmet = [d for d in dependencies
                 if state.proposals.get(d, {}).get("status")
                 not in ("accepted", "execution_candidate")]

        return {
            "as_of": as_of,
            "freshness_policy_days": freshness_policy_days,
            "evidence_references": refs,
            "affected_customers": sorted(
                set(problem["affected_customers"])
                | {f["crm_entity_id"] for f in crm_facts if f["crm_entity_id"]}),
            "crm_facts": crm_facts,
            "experiments": experiments,
            "research": {"coverage_totals": coverage_totals,
                         "stances": stances},
            "origin": dict(opportunity.get("origin") or {}),
            "alignment": state.alignments.get(proposal["opportunity_id"]),
            "input_timestamps": sorted(set(timestamps)),
            "unknowns": list(body.get("unknown") or []),
            "assumptions": list(body.get("assumptions") or []),
            "open_questions": list(body.get("open_questions") or []),
            "risks": list(body.get("risks") or []),
            "revenue_at_risk_declared": (
                state.alignments.get(proposal["opportunity_id"], {})
                .get("revenue_at_risk")),
            "spec": {"exists": spec_id is not None,
                     "debt": list(spec_state["debt"]) if spec_state else [],
                     "acceptance_criteria": len(
                         spec_body.get("acceptance_criteria") or [])},
            "dependencies_unmet": len(unmet),
            "decision_id": proposal.get("decision_id"),
        }

    def score_proposal(self, proposal_id: str, *, as_of: str,
                       freshness_policy_days: int = 90, record: bool = True,
                       actor_type="system", actor_id="product_scoring") -> dict:
        facts = self._facts_for(proposal_id, as_of=as_of,
                                freshness_policy_days=freshness_policy_days)
        block = score_block(facts)
        if record:
            state = self.get_state()
            version = state.proposals[proposal_id]["version"]
            self._record("product.proposal_scored", actor_type=actor_type,
                         actor_id=actor_id, source="system",
                         proposal_id=proposal_id, proposal_version=version,
                         subject_type="proposal", subject_id=proposal_id,
                         payload={**block, "as_of": as_of},
                         idempotency_key=f"score:{proposal_id}:{version}:{as_of}")
        return block

    def scores_by_proposal(self, *, as_of: str) -> dict:
        return {pid: self.score_proposal(pid, as_of=as_of, record=False)
                for pid in sorted(self.get_state().proposals)}

    # =====================================================================
    # Model-assisted drafting — isolated, versioned, budgeted, recorded
    # =====================================================================
    def draft_with_model(self, kind: str, *, context: str,
                         actor_id="product_agent", **refs) -> dict:
        """A model may draft PROSE. It may never author an evidence
        reference, a customer id, a score, a priority, a decision id, or a
        citation — checked structurally, at any nesting depth, and a
        violation is recorded as a typed fact rather than silently
        dropped."""
        if kind not in PROMPT_VERSIONS:
            raise ProductError(f"unknown draft kind: {kind!r}")
        if self.llm_client is None:
            raise ProductError("no model client is configured for drafting")
        provenance = {"prompt_version": PROMPT_VERSIONS[kind],
                      "model_version": self.model_version,
                      "authority": "a candidate; a rule or a person accepts it"}
        try:
            draft = self.llm_client.call_tool(
                prompt_version=PROMPT_VERSIONS[kind], user_message=context)
        except Exception as exc:                            # noqa: BLE001
            self._record("product.draft_failed", actor_type="system",
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
            self._record("product.draft_rejected", actor_type="system",
                         actor_id="model_boundary", source="system",
                         subject_type="draft",
                         payload={"kind": kind,
                                  "forbidden_fields": forbidden,
                                  "unexpected_fields": unexpected,
                                  "note": "a model draft that authors a "
                                          "reference, an identifier, or a "
                                          "score is rejected whole"},
                         provenance=provenance, **refs)
            raise ModelOverreach(
                f"model draft for {kind!r} attempted to author "
                f"{forbidden + unexpected} — prose only")

        assert_not_score_shaped(draft, where=f"model draft ({kind})")
        return {"draft": draft, "provenance": provenance, "candidate": True}

    # =====================================================================
    # Roadmap candidates and the proposed diff
    # =====================================================================
    def draft_roadmap_candidate(self, proposal_id: str, *, title: str,
                                size: str = "M", priority: int = None,
                                actor_type="agent",
                                actor_id="product_agent") -> dict:
        state = self.get_state()
        proposal = state.proposals.get(proposal_id)
        if proposal is None:
            raise ProductError(f"no such proposal: {proposal_id}")
        spec_id, spec_state = state.spec_for_current_version(proposal_id)
        if spec_id is None:
            raise ProductError(
                "a roadmap candidate requires a spec draft on the proposal's "
                "current version")
        candidate = build_roadmap_candidate(
            proposal_id=proposal_id, proposal_version=proposal["version"],
            spec_id=spec_id, spec_version=spec_state["version"], title=title,
            spec=self.get_spec(spec_id),
            opportunity_id=proposal["opportunity_id"],
            problem_id=proposal["problem_id"], size=size, priority=priority)
        self._record("product.roadmap_candidate_drafted",
                     actor_type=actor_type, actor_id=actor_id,
                     proposal_id=proposal_id,
                     proposal_version=proposal["version"], spec_id=spec_id,
                     spec_version=spec_state["version"],
                     subject_type="roadmap_candidate", subject_id=proposal_id,
                     payload=candidate,
                     idempotency_key=f"roadmap-candidate:{proposal_id}:"
                                     f"{proposal['version']}")
        return candidate

    def emit_roadmap_diff(self, proposal_id: str, roadmap_text: str, *,
                          actor_type="agent", actor_id="product_agent") -> dict:
        """Emitted, never applied. `roadmap_text` is passed in; this
        service holds no path to ROADMAP.md."""
        state = self.get_state()
        candidate_state = state.roadmap_candidates.get(proposal_id)
        if candidate_state is None:
            raise ProductError("a diff requires a drafted roadmap candidate")
        candidate = self.get_roadmap_candidate(proposal_id)
        diff = render_roadmap_diff(candidate, roadmap_text)
        self._record("product.roadmap_diff_emitted", actor_type=actor_type,
                     actor_id=actor_id, proposal_id=proposal_id,
                     proposal_version=candidate["proposal_version"],
                     spec_id=candidate["spec_id"],
                     spec_version=candidate["spec_version"],
                     subject_type="roadmap_diff", subject_id=proposal_id,
                     payload=diff,
                     idempotency_key=f"roadmap-diff:{proposal_id}:"
                                     f"{candidate['proposal_version']}")
        return diff

    # =====================================================================
    # Bundles
    # =====================================================================
    def assemble_bundle(self, name: str, proposal_ids, *, as_of: str,
                        actor_type="agent", actor_id="product_agent") -> dict:
        state = self.get_state()
        index = self.get_index()
        bundle = assemble_bundle(
            state, index, name=name, proposal_ids=proposal_ids,
            scores_by_proposal=self.scores_by_proposal(as_of=as_of))
        key = f"bundle:{name}"
        bundle_id = self._stable_id(key)
        self._record("product.bundle_assembled", actor_type=actor_type,
                     actor_id=actor_id, bundle_id=bundle_id,
                     subject_type="bundle", subject_id=bundle_id,
                     payload={**bundle, "bundle_id": bundle_id},
                     idempotency_key=key)
        return {**bundle, "bundle_id": bundle_id}

    # =====================================================================
    # Reads
    # =====================================================================
    def get_state(self) -> ProductState:
        return fold_product(self.store.read_all(), validate=True)

    def get_index(self):
        return build_index(self.store.read_all())

    def get_problem(self, problem_id: str) -> dict:
        for row in self.store.for_problem(problem_id):
            if row.event_type == "product.problem_recorded":
                return dict(row.payload)
        raise KeyError(f"no such problem: {problem_id}")

    def get_proposal(self, proposal_id: str, version: int = None) -> dict:
        """Prior versions stay retrievable — a revision adds a version, it
        does not overwrite one."""
        rows = [r for r in self.store.for_proposal(proposal_id)
                if r.event_type in ("product.proposal_drafted",
                                    "product.proposal_revised")]
        if not rows:
            raise KeyError(f"no such proposal: {proposal_id}")
        if version is not None:
            for row in rows:
                if row.proposal_version == version:
                    return {**row.payload, "proposal_version": version}
            raise KeyError(f"no version {version} of proposal {proposal_id}")
        return {**rows[-1].payload, "proposal_version": rows[-1].proposal_version}

    def get_spec(self, spec_id: str, version: int = None) -> dict:
        rows = [r for r in self.store.read_all()
                if r.spec_id == spec_id
                and r.event_type in ("product.spec_drafted",
                                     "product.spec_revised")]
        if not rows:
            raise KeyError(f"no such spec: {spec_id}")
        if version is not None:
            for row in rows:
                if row.spec_version == version:
                    return dict(row.payload)
            raise KeyError(f"no version {version} of spec {spec_id}")
        return dict(rows[-1].payload)

    def get_spec_debt(self, spec_id: str) -> dict:
        return spec_debt_report(self.get_spec(spec_id))

    def get_roadmap_candidate(self, proposal_id: str) -> dict:
        rows = [r for r in self.store.for_proposal(proposal_id)
                if r.event_type == "product.roadmap_candidate_drafted"]
        if not rows:
            raise KeyError(f"no roadmap candidate for {proposal_id}")
        return dict(rows[-1].payload)

    def lineage(self, proposal_id: str) -> dict:
        """proposal -> opportunity -> problem -> evidence -> source ->
        request. The last hops are resolved by T019, not rebuilt here."""
        resolver = None
        if self.research is not None:
            def resolver(ref):                              # noqa: F811
                if ref.get("kind") == REF_RESEARCH_CONCLUSION:
                    package = self.research.get_package(ref["request_id"],
                                                        ref["ref_id"])
                    return {"resolved_by": "research_service.get_package",
                            "request_id": ref["request_id"],
                            "package_version": package.get("package_version"),
                            "index_version": package.get("index_version"),
                            "sources": package["sources"]["accepted"]}
                if ref.get("kind") == REF_RESEARCH_DEBT:
                    return {"resolved_by": "research package debt item",
                            "request_id": ref.get("request_id"),
                            "detail": ref.get("detail", "")}
                return {"resolved_by": "reference kind is owned by another "
                                       "subsystem",
                        "kind": ref.get("kind"), "ref_id": ref.get("ref_id")}
        return self.get_index().lineage(proposal_id, evidence_resolver=resolver)

    def portfolio(self, portfolio_id: str, *, as_of: str) -> dict:
        """The single deterministic call. One read gives T021 the whole
        product picture."""
        state = self.get_state()
        index = self.get_index()
        scores = self.scores_by_proposal(as_of=as_of)
        debt_by_opportunity = {}
        for opportunity_id, opportunity in index.opportunities.items():
            for ref in opportunity["evidence_references"]:
                if ref.get("kind") == REF_RESEARCH_CONCLUSION \
                        and self.research is not None:
                    try:
                        package = self.research.get_package(ref["request_id"],
                                                            ref["ref_id"])
                    except Exception:                       # noqa: BLE001
                        continue
                    debt_by_opportunity.setdefault(opportunity_id, []).extend(
                        package.get("research_debt", []))
        rollup = portfolio_rollup(
            state, index, portfolio_id=portfolio_id, scores_by_proposal=scores,
            research_debt_by_opportunity=debt_by_opportunity, as_of=as_of)
        readiness = readiness_report(state, index, scores_by_proposal=scores)
        return {
            "rollup": rollup,
            "readiness": readiness,
            "balance": balance_report(state, index, portfolio_id=portfolio_id,
                                      scores_by_proposal=scores),
            "executive_summary": executive_summary(
                state, index, portfolio_id=portfolio_id,
                scores_by_proposal=scores, readiness=readiness, rollup=rollup),
        }

    def list_pending_reviews(self) -> list:
        state = self.get_state()
        out = []
        for proposal_id, proposal in sorted(state.proposals.items()):
            if proposal["status"] == STATUS_REVIEW_REQUESTED:
                spec_id, spec = state.spec_for_current_version(proposal_id)
                out.append({"proposal_id": proposal_id,
                            "proposal_version": proposal["version"],
                            "spec_id": spec_id,
                            "spec_version": spec["version"] if spec else None,
                            "opportunity_id": proposal["opportunity_id"],
                            "problem_id": proposal["problem_id"]})
        return out

    def list_execution_candidates(self) -> list:
        state = self.get_state()
        return [{"proposal_id": pid, "decision_id": proposal.get("decision_id")}
                for pid, proposal in sorted(state.proposals.items())
                if proposal["status"] == "execution_candidate"]

    def get_history(self, **selector) -> list:
        rows = self.store.read_all()
        for field_name, value in selector.items():
            rows = [r for r in rows if getattr(r, field_name) == value]
        return rows

    def accepted_proposals(self) -> list:
        state = self.get_state()
        return sorted(pid for pid, proposal in state.proposals.items()
                      if proposal["status"] == STATUS_ACCEPTED)

"""ResearchService (T019) — the only write path.

The agent drafts. It never approves a plan, never reviews, never
validates an insight, never promotes knowledge, never writes the
mechanism library, and never fetches anything on its own.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from intent_engine.core.decision_ids import new_ulid
from intent_engine.research.extraction import (
    ExtractionRejected, extract_candidates,
)
from intent_engine.research.index import build_index, claim_key, normalize_claim
from intent_engine.research.packages import (
    assemble_package, draft_conclusion, render_narrative,
)
from intent_engine.research.records import (
    CONFLICT_REASONS, HUMAN_ONLY_EVENTS, ResearchError, ResearchEvent,
    assert_research_language, json_normalize,
)
from intent_engine.research.sources import (
    canonicalize_locator, content_hash, grade_source,
)
from intent_engine.research.state import (
    REQUIRED_PLAN_PARTS, ResearchState, fold_research, validate_research_event,
)
from intent_engine.research.store import DEFAULT_RESEARCH_PATH, ResearchStore

REQUEST_FINGERPRINT_VERSION = "request_fingerprint.v1"


def fingerprint_request(question: str, constraints=None, scope: str = "") -> str:
    """Deterministic EXACT-match fingerprint. Near-duplicates are never
    auto-merged: 'close enough' silently answers a different question."""
    payload = "|".join([normalize_claim(question),
                        "|".join(sorted(constraints or [])),
                        normalize_claim(scope)])
    return "req-" + hashlib.sha256(payload.encode()).hexdigest()[:32]


class ResearchService:
    def __init__(self, path=DEFAULT_RESEARCH_PATH, *, knowledge_service=None,
                 decision_service=None, event_bus=None, llm_client=None,
                 model_version="fake-model.v0"):
        self.store = ResearchStore(path)
        self.knowledge = knowledge_service
        self.decisions = decision_service
        self.bus = event_bus
        self.llm_client = llm_client
        self.model_version = model_version

    # --- write path -----------------------------------------------------------
    def _stable_id(self, key: str) -> str:
        existing = self.store.find_by_idempotency_key(key)
        return existing.subject_id if existing is not None else new_ulid()

    def _record(self, request_id, event_type, *, actor_type, actor_id,
                source="cli", payload=None, provenance=None, version=None,
                session_id=None, subject_type=None, subject_id=None,
                occurred_at=None, idempotency_key=None, **refs) -> ResearchEvent:
        if event_type in HUMAN_ONLY_EVENTS and actor_type != "human":
            raise ResearchError(
                f"{event_type} is a human wall transition; "
                f"actor_type={actor_type!r} cannot emit it — the agent "
                "drafts, it never approves or reviews")
        kwargs = dict(event_type=event_type, request_id=request_id,
                      actor_type=actor_type, actor_id=actor_id, source=source,
                      payload=json_normalize(dict(payload or {})),
                      provenance=json_normalize(dict(provenance or {})),
                      plan_version=version, session_id=session_id,
                      subject_type=subject_type, subject_id=subject_id,
                      idempotency_key=idempotency_key, **refs)
        if occurred_at is not None:
            kwargs["occurred_at"] = occurred_at
        candidate = ResearchEvent(**kwargs)
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.content_fingerprint() != candidate.content_fingerprint():
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was already "
                        "used for different content")
                return existing
        state = (self.get_state(request_id)
                 if event_type != "research.request_created"
                 else ResearchState())
        ok, reason = validate_research_event(state, event_type, payload or {},
                                             version, session_id)
        if not ok:
            raise ResearchError(f"{event_type}: {reason}")
        return self.store.append(candidate)

    # =====================================================================
    # LAYER 1 — Requests (with freshness-aware reuse)
    # =====================================================================
    def create_request(self, question: str, *, motivation: str,
                       constraints=None, scope: str = "",
                       originating_decision_id=None, campaign_id=None,
                       experiment_id=None, requested_by: str = "founder",
                       actor_type: str = "human") -> dict:
        fingerprint = fingerprint_request(question, constraints, scope)
        prior = self._find_by_fingerprint(fingerprint)
        if prior is not None:
            return {"request_id": prior, "reused": True,
                    "fingerprint": fingerprint}
        request_id = new_ulid()
        self._record(request_id, "research.request_created",
                     actor_type=actor_type, actor_id=requested_by,
                     subject_type="request", subject_id=request_id,
                     decision_id=originating_decision_id,
                     campaign_id=campaign_id, experiment_id=experiment_id,
                     payload={"question": question, "motivation": motivation,
                              "constraints": sorted(constraints or []),
                              "scope": scope, "fingerprint": fingerprint,
                              "fingerprint_version": REQUEST_FINGERPRINT_VERSION,
                              "requested_by": requested_by})
        return {"request_id": request_id, "reused": False,
                "fingerprint": fingerprint}

    def _find_by_fingerprint(self, fingerprint: str):
        for row in self.store.read_all():
            if row.event_type == "research.request_created" \
                    and (row.payload or {}).get("fingerprint") == fingerprint:
                return row.request_id
        return None

    def reuse_request(self, request_id: str, prior_id: str, *, as_of: str,
                      actor_id: str = "founder") -> dict:
        """Reuse respects freshness: a stale package is returned WITH its
        age, never silently."""
        packages = self.list_packages(prior_id)
        stale = []
        for package_id in packages:
            package = self.get_package(prior_id, package_id)
            if package["freshness"]["stale_sources"]:
                stale.append({"package_id": package_id,
                              "oldest_age_days":
                                  package["freshness"]["oldest_load_bearing_age_days"]})
        self._record(request_id, "research.request_reused",
                     actor_type="human", actor_id=actor_id,
                     payload={"reused_from": prior_id, "as_of": as_of,
                              "stale_packages": stale})
        return {"reused_from": prior_id, "packages": packages,
                "stale": stale,
                "marker": "STALE" if stale else "FRESH"}

    def link_related_request(self, request_id: str, other_id: str, *,
                             reason: str, actor_id: str = "founder") -> None:
        self._record(request_id, "research.request_related_linked",
                     actor_type="human", actor_id=actor_id,
                     payload={"related_request_id": other_id,
                              "reason": reason},
                     idempotency_key=f"related:{request_id}:{other_id}")

    # =====================================================================
    # LAYER 2 — Plans (pre-registration)
    # =====================================================================
    def draft_plan(self, request_id: str, *, goal: str, questions: list,
                   evidence_requirements: dict, stopping_conditions: dict,
                   failure_definition: str, tool_allowlist: list,
                   budget: dict, expected_source_classes=None,
                   excluded_sources=None, success_definition: str = "",
                   actor_type: str = "agent",
                   actor_id: str = "research_agent") -> int:
        if not questions:
            raise ResearchError("a plan needs at least one question")
        if not stopping_conditions:
            raise ResearchError("stopping conditions must be declared")
        if not failure_definition.strip():
            raise ResearchError(
                "a failure_definition is mandatory — 'we could not answer "
                "this' must be a pre-authorized outcome, not a state to avoid")
        if not tool_allowlist:
            raise ResearchError("a tool allowlist must be declared")
        if not budget:
            raise ResearchError("a budget must be declared")
        state = self.get_state(request_id)
        version = state.draft_plan_version
        self._record(request_id, "research.plan_drafted", actor_type=actor_type,
                     actor_id=actor_id, version=version, subject_type="plan",
                     subject_id=f"plan-{version}",
                     payload={"plan_version": version, "goal": goal,
                              "questions": list(questions),
                              "evidence_requirements": dict(evidence_requirements),
                              "stopping_conditions": dict(stopping_conditions),
                              "failure_definition": failure_definition,
                              "tool_allowlist": sorted(tool_allowlist),
                              "budget": dict(budget),
                              "expected_source_classes":
                                  sorted(expected_source_classes or []),
                              "excluded_sources": list(excluded_sources or []),
                              "success_definition": success_definition,
                              "parts": list(REQUIRED_PLAN_PARTS)})
        return version

    def submit_plan(self, request_id: str, *, actor_type="agent",
                    actor_id="research_agent"):
        return self._record(request_id, "research.plan_submitted",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={})

    def approve_plan(self, request_id: str, *, actor_id: str,
                     actor_type="human", note: str = ""):
        return self._record(request_id, "research.plan_approved",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"approver": actor_id, "note": note})

    def reject_plan(self, request_id: str, reason: str, *, actor_id: str,
                    actor_type="human"):
        return self._record(request_id, "research.plan_rejected",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"reason": reason})

    def get_plan(self, request_id: str, version=None) -> dict:
        rows = [r for r in self.store.for_request(request_id)
                if r.event_type in ("research.plan_drafted",
                                    "research.plan_amended")]
        if not rows:
            raise KeyError(f"no plan for request {request_id}")
        if version is not None:
            for row in rows:
                if row.payload.get("plan_version") == version:
                    return dict(row.payload)
            raise KeyError(f"no plan version {version}")
        return dict(rows[-1].payload)

    # =====================================================================
    # LAYER 3 — Sessions
    # =====================================================================
    def start_session(self, request_id: str, *, actor_type="agent",
                      actor_id="research_agent") -> str:
        state = self.get_state(request_id)
        session_id = new_ulid()
        self._record(request_id, "research.session_started",
                     actor_type=actor_type, actor_id=actor_id,
                     version=state.approved_plan_version,
                     session_id=session_id, subject_type="session",
                     subject_id=session_id, payload={})
        return session_id

    def close_session(self, request_id: str, session_id: str, *,
                      actor_type="agent", actor_id="research_agent"):
        state = self.get_state(request_id)
        return self._record(request_id, "research.session_closed",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_plan_version,
                            session_id=session_id, payload={})

    # =====================================================================
    # Sources
    # =====================================================================
    def register_source(self, request_id: str, session_id: str, *,
                        source_class: str, title: str, text: str,
                        locator: str, retrieved_at: str,
                        acquisition_method: str, acquisition_tool: str,
                        author=None, publisher=None, published_date=None,
                        domain=None, source_family=None,
                        derived_from_source=None, methodology=None,
                        population=None, definition=None,
                        actor_type="agent", actor_id="research_agent") -> str:
        plan = self.get_plan(request_id)
        if acquisition_tool not in plan["tool_allowlist"]:
            self._record(request_id, "research.source_rejected",
                         actor_type="system", actor_id="tool_gate",
                         version=self.get_state(request_id).approved_plan_version,
                         session_id=session_id,
                         payload={"locator": locator,
                                  "reason": f"tool {acquisition_tool!r} is not "
                                            "on the plan's allowlist"})
            raise ResearchError(
                f"acquisition tool {acquisition_tool!r} is not on the "
                f"approved plan's allowlist {plan['tool_allowlist']}")
        canonical = canonicalize_locator(locator)
        key = f"source:{request_id}:{canonical}"
        source_id = self._stable_id(key)
        record = {
            "source_id": source_id, "source_class": source_class,
            "title": title, "author": author, "publisher": publisher,
            "published_date": published_date, "retrieved_at": retrieved_at,
            "locator": locator, "canonical_locator": canonical,
            "content_hash": content_hash(text),
            "acquisition_method": acquisition_method,
            "acquisition_tool": acquisition_tool, "domain": domain,
            "source_family": source_family,
            "derived_from_source": derived_from_source,
            "methodology": methodology, "population": population,
            "definition": definition, "verified": True,
        }
        record.update(grade_source(record))
        state = self.get_state(request_id)
        self._record(request_id, "research.source_registered",
                     actor_type=actor_type, actor_id=actor_id,
                     version=state.approved_plan_version, session_id=session_id,
                     subject_type="source", subject_id=source_id,
                     payload=record, idempotency_key=key,
                     provenance={"acquisition_tool": acquisition_tool,
                                 "retrieved_at": retrieved_at})
        return source_id

    def mark_source_unverified(self, request_id, source_id, reason, *,
                               actor_type="system", actor_id="verifier"):
        state = self.get_state(request_id)
        return self._record(request_id, "research.source_unverified",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_plan_version,
                            subject_type="source", subject_id=source_id,
                            payload={"reason": reason},
                            idempotency_key=f"unverified:{source_id}")

    def retire_source(self, request_id, source_id, reason, *, actor_id,
                      actor_type="human"):
        state = self.get_state(request_id)
        return self._record(request_id, "research.source_retired",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_plan_version,
                            subject_type="source", subject_id=source_id,
                            payload={"reason": reason},
                            idempotency_key=f"retired:{source_id}")

    # =====================================================================
    # LAYER 4 — Evidence Index (deterministic writes only)
    # =====================================================================
    def extract_evidence(self, request_id: str, session_id: str,
                         source_id: str, source_text: str, *,
                         question: str = "", stance: str = "supports",
                         actor_id="research_agent") -> dict:
        """Model proposes; deterministic code decides. Every rejection and
        every failure is a recorded fact."""
        if self.llm_client is None:
            raise ResearchError("no model client configured for extraction")
        index = self.get_index(request_id, as_of="9999-12-31T00:00:00+00:00")
        source = index.sources.get(source_id)
        if source is None:
            raise ResearchError(f"unregistered source: {source_id}")
        state = self.get_state(request_id)
        try:
            result = extract_candidates(self.llm_client, source, source_text,
                                        model_version=self.model_version)
        except Exception as exc:
            self._record(request_id, "research.extraction_failed",
                         actor_type="system", actor_id="extraction",
                         version=state.approved_plan_version,
                         session_id=session_id, subject_type="source",
                         subject_id=source_id,
                         payload={"error_type": type(exc).__name__,
                                  "note": "an extraction failure is a typed "
                                          "fact, not a report of no evidence"})
            raise

        accepted = []
        for candidate in result["accepted"]:
            key = claim_key(candidate["claim_text"])
            self._index_claim(request_id, session_id, key,
                              candidate["claim_text"], question)
            evidence_id = self._stable_id(
                f"evidence:{source_id}:{key}")
            self._record(
                request_id, "research.evidence_indexed", actor_type="agent",
                actor_id=actor_id, version=state.approved_plan_version,
                session_id=session_id, subject_type="evidence",
                subject_id=evidence_id,
                payload={**candidate, "evidence_id": evidence_id,
                         "claim_key": key, "stance": stance,
                         "question": question},
                provenance=result["provenance"],
                idempotency_key=f"evidence:{source_id}:{key}")
            accepted.append(evidence_id)

        for rejection in result["rejected"]:
            self._record(request_id, "research.evidence_rejected",
                         actor_type="system", actor_id="extraction_wall",
                         version=state.approved_plan_version,
                         session_id=session_id, subject_type="source",
                         subject_id=source_id, payload=rejection,
                         provenance=result["provenance"])
        return {"accepted": accepted, "rejected": len(result["rejected"]),
                "usage": result["usage"]}

    def _index_claim(self, request_id, session_id, key, text, question):
        state = self.get_state(request_id)
        self._record(request_id, "research.claim_indexed", actor_type="system",
                     actor_id="evidence_index",
                     version=state.approved_plan_version, session_id=session_id,
                     subject_type="claim", subject_id=key,
                     payload={"claim_key": key, "normalized": normalize_claim(text),
                              "question": question},
                     idempotency_key=f"claim:{request_id}:{key}")

    def record_contradiction(self, request_id, session_id, *, claim_key_,
                             evidence_id, counterpart, conflict_reason,
                             actor_id="research_agent") -> None:
        if conflict_reason not in CONFLICT_REASONS:
            raise ResearchError(f"unknown conflict reason: {conflict_reason!r}")
        state = self.get_state(request_id)
        relation_id = self._stable_id(
            f"relation:{evidence_id}:{counterpart}")
        self._record(request_id, "research.relation_indexed",
                     actor_type="system", actor_id="evidence_index",
                     version=state.approved_plan_version, session_id=session_id,
                     subject_type="relation", subject_id=relation_id,
                     payload={"relation": "contradicts", "claim_key": claim_key_,
                              "evidence_id": evidence_id,
                              "counterpart": counterpart,
                              "conflict_reason": conflict_reason},
                     idempotency_key=f"relation:{evidence_id}:{counterpart}")

    def get_index(self, request_id: str, *, as_of: str):
        return build_index(self.store.for_request(request_id), request_id,
                           as_of=as_of)

    def lineage(self, request_id: str, evidence_id: str, *, as_of: str) -> dict:
        return self.get_index(request_id, as_of=as_of).lineage(evidence_id)

    # =====================================================================
    # LAYER 5 — Packages, LAYER 6 — Conclusions
    # =====================================================================
    def assemble_package(self, request_id: str, session_id: str, *,
                         claim_map: dict, as_of: str,
                         actor_id="research_agent") -> str:
        state = self.get_state(request_id)
        index = self.get_index(request_id, as_of=as_of)
        plan = self.get_plan(request_id)
        session_rows = [r for r in self.store.for_request(request_id)
                        if r.session_id == session_id]
        package = assemble_package(index, plan, claim_map, session_rows,
                                   as_of=as_of)
        key = f"package:{session_id}"
        package_id = self._stable_id(key)
        self._record(request_id, "research.package_assembled",
                     actor_type="agent", actor_id=actor_id,
                     version=state.approved_plan_version, session_id=session_id,
                     subject_type="package", subject_id=package_id,
                     payload={**package, "package_id": package_id},
                     idempotency_key=key)
        return package_id

    def get_package(self, request_id: str, package_id: str) -> dict:
        for row in self.store.for_request(request_id):
            if row.event_type == "research.package_assembled" \
                    and row.subject_id == package_id:
                return dict(row.payload)
        raise KeyError(f"no such package: {package_id}")

    def list_packages(self, request_id: str) -> list:
        return [r.subject_id for r in self.store.for_request(request_id)
                if r.event_type == "research.package_assembled"]

    def draft_conclusion(self, request_id: str, package_id: str, *,
                         question: str, actor_id="research_agent") -> dict:
        state = self.get_state(request_id)
        package = self.get_package(request_id, package_id)
        conclusion = draft_conclusion(package, question=question)
        key = f"conclusion:{package_id}:{question}"
        conclusion_id = self._stable_id(key)
        self._record(request_id, "research.conclusion_drafted",
                     actor_type="agent", actor_id=actor_id,
                     version=state.approved_plan_version,
                     subject_type="conclusion", subject_id=conclusion_id,
                     payload={**conclusion, "package_id": package_id,
                              "conclusion_id": conclusion_id},
                     idempotency_key=key)
        return {**conclusion, "conclusion_id": conclusion_id}

    def generate_narrative(self, request_id: str, conclusion: dict, *,
                           actor_id="research_agent") -> str:
        """Regenerable prose. The structured conclusion remains the record."""
        text = render_narrative(conclusion)
        state = self.get_state(request_id)
        self._record(request_id, "research.narrative_generated",
                     actor_type="agent", actor_id=actor_id,
                     version=state.approved_plan_version,
                     subject_type="conclusion",
                     subject_id=conclusion["conclusion_id"],
                     payload={"narrative": text, "regenerable": True,
                              "authority": "the structured conclusion is the "
                                           "record; this prose is not"})
        return text

    # =====================================================================
    # Review + proposals (draft only)
    # =====================================================================
    def request_review(self, request_id, *, actor_type="agent",
                       actor_id="research_agent"):
        return self._record(request_id, "research.review_requested",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={})

    def record_review(self, request_id, *, notes: str, actor_id: str,
                      actor_type="human"):
        assert_research_language(notes, where="review notes")
        return self._record(request_id, "research.reviewed",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"notes": notes, "reviewer": actor_id})

    def queue_mechanism_draft(self, request_id: str, package_id: str, *,
                              candidate_name: str, hypothesis: str,
                              trigger_conditions: list, expected_effects: str,
                              scope: str, claim_key_: str, as_of: str,
                              actor_id="research_agent") -> str:
        """Draft ONLY, into the T016 review queue. A contradicted or mixed
        claim must say so in the proposal body."""
        if self.knowledge is None:
            raise ResearchError("no knowledge service configured")
        assert_research_language(hypothesis, where="mechanism hypothesis")
        package = self.get_package(request_id, package_id)
        index = self.get_index(request_id, as_of=as_of)
        plan = self.get_plan(request_id)

        stances = [s for detail in package["coverage"]["per_question"].values()
                   for s in detail["stances"]]
        relevant = [s for s in stances if claim_key_ in
                    (s.get("supporting", []) + s.get("contradicting", [])
                     + [claim_key_])]
        evidence = [e for e in index.usable_evidence()
                    if e.get("claim_key") == claim_key_]
        if not evidence:
            raise ResearchError("a mechanism draft needs indexed evidence")
        if all(e.get("evidence_class") == "opinion" for e in evidence):
            raise ResearchError(
                "a mechanism drawn only from opinion-class evidence is "
                "rejected — opinion never becomes mechanism automatically")

        requirements = plan.get("evidence_requirements", {})
        from intent_engine.research.graph import stance_for_claim
        stance = stance_for_claim(index, claim_key_, requirements=requirements)
        caveat = ""
        if stance["stance"] in ("MIXED", "CONTRADICTED"):
            caveat = (f" NOTE: current evidence is {stance['stance']} for this "
                      f"claim ({stance.get('conflict_reason', 'see package')}); "
                      "this contradiction is part of the proposal, not omitted "
                      "from it.")
        elif stance["stance"] in ("INSUFFICIENT", "UNKNOWN"):
            raise ResearchError(
                f"stance is {stance['stance']}: a mechanism draft requires "
                "the plan's minimum corroboration at its quality floor")

        citations = [{"source_type": "external_source",
                      "source_id": index.sources[e["source_id"]]["canonical_locator"],
                      "title": index.sources[e["source_id"]]["title"],
                      "url": index.sources[e["source_id"]]["locator"],
                      "publisher": index.sources[e["source_id"]].get("publisher")}
                     for e in evidence
                     if index.sources[e["source_id"]]["locator"].startswith("http")]
        if not citations:
            citations = [{"source_type": "feedback_record",
                          "source_id": e["evidence_id"]} for e in evidence[:1]]

        proposal_id = self.knowledge.propose_mechanism(
            candidate_name, hypothesis + caveat,
            trigger_conditions=trigger_conditions,
            expected_effects=expected_effects, scope=scope,
            counterexamples=("; ".join(stance.get("contradicting", []))
                             or "none recorded"),
            citations=citations, source_knowledge_ids=[],
            proposed_by="research_agent")
        state = self.get_state(request_id)
        self._record(request_id, "research.mechanism_draft_queued",
                     actor_type="agent", actor_id=actor_id,
                     version=state.approved_plan_version,
                     subject_type="proposal", subject_id=proposal_id,
                     payload={"proposal_id": proposal_id,
                              "claim_key": claim_key_,
                              "stance_at_draft": stance["stance"]},
                     idempotency_key=f"mechanism-draft:{package_id}:{claim_key_}")
        return proposal_id

    # =====================================================================
    # Reads
    # =====================================================================
    def get_state(self, request_id: str) -> ResearchState:
        return fold_research(self.store.for_request(request_id), validate=True)

    def get_history(self, request_id: str) -> list:
        rows = self.store.for_request(request_id)
        if not rows:
            raise KeyError(f"no such request: {request_id}")
        return rows

    def list_pending_reviews(self) -> list:
        return [{"request_id": rid}
                for rid in self.store.request_ids()
                if self.get_state(rid).review_status == "requested"]

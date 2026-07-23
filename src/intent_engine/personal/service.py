"""PersonalService (T023) — the only write path.

The workspace may summarize, prioritize (by preserving an owner's
ordering), explain, organize, and DRAFT. It may NOT publish, email, modify
business state, create a decision / proposal / experiment / candidate /
campaign, or execute any external action. This service exposes no such
surface at all — a test asserts it.

It composes the read adapters (which it owns) into briefs, answers,
reports, and explanations, and it writes only `data/personal.jsonl`: the
founder's session, questions, briefs, and — on an explicit founder act —
durable memory. It writes no other subsystem's store.
"""
from __future__ import annotations

from intent_engine.agentos.identity import stable_id as _kernel_stable_id
from intent_engine.personal.briefing import assemble_brief
from intent_engine.personal.conversation import (
    answer as _answer, challenge_assumption as _challenge,
)
from intent_engine.personal.explain import explain_decision
from intent_engine.personal.records import (
    PersonalError, PersonalEvent, assert_no_secret, assert_workspace_language,
    json_normalize, now_iso,
)
from intent_engine.personal.reports import assemble_report
from intent_engine.personal.router import classify
from intent_engine.personal.state import (
    WorkspaceState, fold_personal, validate_personal_event,
)
from intent_engine.personal.store import DEFAULT_PERSONAL_PATH, PersonalStore


class PersonalService:
    def __init__(self, path=DEFAULT_PERSONAL_PATH, *, research_service=None,
                 product_service=None, executive_service=None,
                 crm_service=None, analytics_reader=None,
                 knowledge_service=None, decision_service=None,
                 llm_client=None, model_version="fake-model.v0"):
        self.store = PersonalStore(path)
        self.research = research_service
        self.product = product_service
        self.executive = executive_service
        self.crm = crm_service
        self.analytics = analytics_reader
        self.knowledge = knowledge_service
        self.decisions = decision_service
        self.llm_client = llm_client
        self.model_version = model_version

    # --- write path (the only one) ------------------------------------------
    def _stable_id(self, key: str) -> str:
        return _kernel_stable_id(self.store, key)

    def _record(self, event_type, *, actor_type, actor_id, source="cli",
                payload=None, provenance=None, idempotency_key=None,
                **fields) -> PersonalEvent:
        candidate = PersonalEvent(
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
        ok, reason = validate_personal_event(self.get_state(), candidate)
        if not ok:
            raise PersonalError(f"{event_type}: {reason}")
        return self.store.append(candidate)

    # --- adapters (owned by personal/, the composition seam) ----------------
    def _adapters(self, as_of: str) -> dict:
        from intent_engine.personal.adapters import (
            AnalyticsAdapter, CRMAdapter, DecisionsAdapter, ExecutiveAdapter,
            KnowledgeAdapter, ProductAdapter, ResearchAdapter,
        )
        return {
            "research": ResearchAdapter(self.research, as_of=as_of),
            "product": ProductAdapter(self.product, as_of=as_of),
            "executive": ExecutiveAdapter(self.executive, as_of=as_of),
            "crm": CRMAdapter(self.crm, as_of=as_of),
            "analytics": AnalyticsAdapter(self.analytics, as_of=as_of),
            "knowledge": KnowledgeAdapter(self.knowledge, as_of=as_of),
            "decisions": DecisionsAdapter(self.decisions, as_of=as_of),
        }

    # --- sessions ------------------------------------------------------------
    def open_session(self, *, actor_id="founder") -> str:
        key = f"session:{now_iso()}:{actor_id}"
        session_id = self._stable_id(key)
        self._record("personal.session_opened", actor_type="human",
                     actor_id=actor_id, session_id=session_id,
                     subject_type="session", subject_id=session_id,
                     idempotency_key=key)
        return session_id

    def close_session(self, session_id: str, *, actor_id="founder"):
        return self._record("personal.session_closed", actor_type="human",
                            actor_id=actor_id, session_id=session_id,
                            subject_type="session", subject_id=session_id,
                            idempotency_key=f"session-close:{session_id}")

    def ask(self, session_id: str, question: str, *, as_of: str,
            package_id: str = None, portfolio_id: str = None,
            actor_id="founder") -> dict:
        """A conversation turn. Records the question (ephemeral session —
        NOT durable memory) and returns a cited answer."""
        assert_no_secret(question, where="question")
        intent = classify(question)
        turn_id = self._stable_id(f"turn:{session_id}:{question}")
        self._record("personal.turn_recorded", actor_type="human",
                     actor_id=actor_id, session_id=session_id,
                     subject_type="turn", subject_id=turn_id,
                     payload={"question": question, "intent": intent},
                     idempotency_key=f"turn:{session_id}:{question}")
        return _answer(question, adapters=self._adapters(as_of),
                       llm_client=self.llm_client,
                       model_version=self.model_version, package_id=package_id,
                       portfolio_id=portfolio_id)

    def challenge_assumption(self, *, as_of: str, subject: str = "") -> dict:
        return _challenge(subject, adapters=self._adapters(as_of))

    def explain(self, package_id: str, *, as_of: str) -> dict:
        return explain_decision(self._adapters(as_of)["executive"], package_id)

    # --- briefs + reports (generated artifacts) -----------------------------
    def morning_brief(self, *, as_of: str, portfolio_id: str = None,
                      record: bool = True) -> dict:
        adapters = self._adapters(as_of)
        brief = assemble_brief(research_adapter=adapters["research"],
                               executive_adapter=adapters["executive"],
                               product_adapter=adapters["product"], as_of=as_of,
                               portfolio_id=portfolio_id)
        if record:
            brief_id = self._stable_id(f"brief:{as_of}")
            self._record("personal.brief_assembled", actor_type="system",
                         actor_id="workspace", source="workspace",
                         subject_type="brief", subject_id=brief_id,
                         payload={"as_of": as_of,
                                  "gaps_named": brief["gaps_named"]},
                         idempotency_key=f"brief:{as_of}")
            brief["brief_id"] = brief_id
        return brief

    def report(self, profile: str, *, as_of: str, portfolio_id: str = None,
               record: bool = True) -> dict:
        adapters = self._adapters(as_of)
        result = assemble_report(profile, research_adapter=adapters["research"],
                                 executive_adapter=adapters["executive"],
                                 product_adapter=adapters["product"],
                                 as_of=as_of, portfolio_id=portfolio_id)
        if record and result.get("available"):
            report_id = self._stable_id(f"report:{profile}:{as_of}")
            self._record("personal.report_drafted", actor_type="system",
                         actor_id="workspace", source="workspace",
                         subject_type="report", subject_id=report_id,
                         payload={"profile": profile, "as_of": as_of},
                         idempotency_key=f"report:{profile}:{as_of}")
            result["report_id"] = report_id
        return result

    # --- durable memory (founder-only acts) ---------------------------------
    def pin_finding(self, reference: dict, *, note: str = "",
                    actor_id="founder") -> str:
        """Pin a REFERENCE, never a copy of operational data."""
        assert_no_secret(note, where="pin note")
        assert_workspace_language(note, where="pin note")
        pin_id = self._stable_id(f"pin:{reference}")
        self._record("personal.memory_pinned", actor_type="human",
                     actor_id=actor_id, subject_type="pin", subject_id=pin_id,
                     memory_class="durable_founder",
                     payload={"reference": reference, "note": note},
                     idempotency_key=f"pin:{reference}")
        return pin_id

    def save_goal(self, goal: str, *, actor_id="founder") -> str:
        assert_no_secret(goal, where="goal")
        goal_id = self._stable_id(f"goal:{goal}")
        self._record("personal.goal_saved", actor_type="human",
                     actor_id=actor_id, subject_type="goal", subject_id=goal_id,
                     memory_class="durable_founder", payload={"goal": goal},
                     idempotency_key=f"goal:{goal}")
        return goal_id

    def open_investigation(self, question: str, *, origin_reference=None,
                           actor_id="founder") -> str:
        assert_no_secret(question, where="investigation")
        iid = self._stable_id(f"investigation:{question}")
        self._record("personal.investigation_opened", actor_type="human",
                     actor_id=actor_id, subject_type="investigation",
                     subject_id=iid, memory_class="durable_founder",
                     payload={"question": question,
                              "origin_reference": origin_reference},
                     idempotency_key=f"investigation:{question}")
        return iid

    def propose_memory_candidate(self, kind: str, detail: str) -> str:
        """The workspace may PROPOSE; a person promotes. Recorded as a
        candidate, never as durable memory."""
        cid = self._stable_id(f"memcand:{kind}:{detail}")
        self._record("personal.memory_candidate_proposed", actor_type="agent",
                     actor_id="workspace", source="workspace",
                     subject_type="memory_candidate", subject_id=cid,
                     payload={"kind": kind, "detail": detail},
                     idempotency_key=f"memcand:{kind}:{detail}")
        return cid

    # --- reads ---------------------------------------------------------------
    def get_state(self) -> WorkspaceState:
        return fold_personal(self.store.read_all(), validate=True)

    def durable_memory(self) -> dict:
        return self.get_state().durable_memory()

    def get_history(self, **selector) -> list:
        rows = self.store.read_all()
        for field_name, value in selector.items():
            rows = [r for r in rows if getattr(r, field_name) == value]
        return rows

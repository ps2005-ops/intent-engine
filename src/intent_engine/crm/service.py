"""CRMService — the only write path and read model for CRM facts (T014).

Writes: validate the envelope, the actor rules (the outreach wall's
human-only transitions), and the lifecycle transition against the folded
state, then append. Reads: deterministic folds and filtered histories.
Nothing here mutates a line, ever.
"""
from __future__ import annotations

from pathlib import Path

from intent_engine.core.decision_ids import new_ulid
from intent_engine.crm.events import (
    DECISION_LINK_TYPES, CRMEvent, CRMEnvelopeError,
)
from intent_engine.crm.state import (
    CRMState, CRMTransitionError, fold_crm, validate_crm_event,
)
from intent_engine.crm.store import CRMStore

DEFAULT_CRM_PATH = Path("marketing/crm/crm.jsonl")

# The wall + deliberate-action transitions a human must make. Drafting and
# consumer-observed facts may be automated; these may not.
_HUMAN_ONLY = {"crm.outreach_approved", "crm.outreach_rejected",
               "crm.reopened"}


class CRMService:
    def __init__(self, path=DEFAULT_CRM_PATH):
        self.store = CRMStore(path)

    # --- writes ---------------------------------------------------------------
    def create_prospect(self, *, name: str = None, email: str = None,
                        domain: str = None, actor_type: str = "human",
                        actor_id: str = "founder", source: str = "cli",
                        idempotency_key: str = None) -> str:
        """Mint ONE opaque identity for a person/company relationship. The
        attributes are payload, never keys. Idempotent on idempotency_key
        (the existing entity id is returned; zero new rows)."""
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing.crm_entity_id
        entity_id = new_ulid()
        payload = {k: v for k, v in
                   (("name", name), ("email", email), ("domain", domain))
                   if v}
        self._record(entity_id, "crm.prospect_created", actor_type=actor_type,
                     actor_id=actor_id, source=source, payload=payload,
                     idempotency_key=idempotency_key)
        return entity_id

    def record(self, crm_entity_id: str, event_type: str, *,
               actor_type: str, actor_id: str, source: str = "cli",
               payload: dict = None, decision_id: str = None,
               company_event_id: str = None, correlation_id: str = None,
               occurred_at: str = None,
               idempotency_key: str = None) -> CRMEvent:
        if event_type == "crm.prospect_created":
            raise CRMEnvelopeError("use create_prospect() to mint identities")
        self._require_entity(crm_entity_id)
        return self._record(crm_entity_id, event_type, actor_type=actor_type,
                            actor_id=actor_id, source=source, payload=payload,
                            decision_id=decision_id,
                            company_event_id=company_event_id,
                            correlation_id=correlation_id,
                            occurred_at=occurred_at,
                            idempotency_key=idempotency_key)

    def link_decision(self, crm_entity_id: str, decision_id: str,
                      link_type: str = "subject", *, decision_service=None,
                      actor_type: str = "human", actor_id: str = "founder",
                      source: str = "cli") -> CRMEvent:
        """Reference a Decision Record (typed). The Decision Record stays
        authoritative — the CRM stores the reference and CRM-side context
        ONLY, never decision state or intake content. With a
        decision_service, existence is verified; a bad id fails clearly.
        Idempotent per (entity, decision, link_type)."""
        if link_type not in DECISION_LINK_TYPES:
            raise CRMEnvelopeError(f"unknown decision link_type: {link_type!r}")
        if decision_service is not None:
            if decision_service.get_decision(decision_id) is None:
                raise KeyError(f"no such decision: {decision_id}")
        return self.record(
            crm_entity_id, "crm.decision_linked", actor_type=actor_type,
            actor_id=actor_id, source=source, decision_id=decision_id,
            payload={"decision_id": decision_id, "link_type": link_type},
            idempotency_key=f"decision-link:{crm_entity_id}:{decision_id}:{link_type}")

    def _record(self, crm_entity_id, event_type, *, actor_type, actor_id,
                source, payload=None, decision_id=None, company_event_id=None,
                correlation_id=None, occurred_at=None, idempotency_key=None
                ) -> CRMEvent:
        if event_type in _HUMAN_ONLY and actor_type != "human":
            raise CRMTransitionError(
                f"{event_type} is a human wall transition; "
                f"actor_type={actor_type!r} cannot emit it (no auto-approval)")
        if event_type in ("crm.owner_assigned", "crm.owner_transferred"):
            owner = (payload or {}).get("owner")
            if not isinstance(owner, str) or not owner.strip():
                raise CRMEnvelopeError(f"{event_type} requires payload['owner']")
        if event_type.startswith("crm.outreach"):
            if not (payload or {}).get("draft_id"):
                raise CRMEnvelopeError(f"{event_type} requires payload['draft_id']")

        kwargs = dict(
            crm_entity_id=crm_entity_id, event_type=event_type,
            actor_type=actor_type, actor_id=actor_id, source=source,
            payload=dict(payload or {}), decision_id=decision_id,
            company_event_id=company_event_id, correlation_id=correlation_id,
            idempotency_key=idempotency_key)
        if occurred_at is not None:
            kwargs["occurred_at"] = occurred_at
        candidate = CRMEvent(**kwargs)
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                # A replay must be the SAME fact: reuse for different
                # content is rejected; a true retry returns the original
                # (before transition validation, which the fact already
                # passed when first written).
                if existing.content_fingerprint() != candidate.content_fingerprint():
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was already "
                        "used for different content")
                return existing
        history = self._events(crm_entity_id)
        state = fold_crm(history, validate=True)
        ok, reason = validate_crm_event(state, event_type, payload or {})
        if not ok:
            raise CRMTransitionError(f"{event_type}: {reason}")
        return self.store.append(candidate)

    # --- reads ----------------------------------------------------------------
    def _events(self, crm_entity_id: str) -> list[CRMEvent]:
        return [ev for ev in self.store.read_all()
                if ev.crm_entity_id == crm_entity_id]

    def _require_entity(self, crm_entity_id: str) -> None:
        if not any(ev.event_type == "crm.prospect_created"
                   for ev in self._events(crm_entity_id)):
            raise KeyError(f"no such CRM entity: {crm_entity_id}")

    def get_entity(self, id_or_external_ref: str) -> str | None:
        """Resolve an entity id, an explicitly linked external ref, or an
        exact email attribute. Deterministic and conservative: no fuzzy
        matching; ambiguity (two entities, same ref) raises for explicit
        human resolution instead of silently merging."""
        matches = set()
        for ev in self.store.read_all():
            if ev.crm_entity_id == id_or_external_ref:
                matches.add(ev.crm_entity_id)
            elif ev.event_type == "crm.identity_linked" \
                    and ev.payload.get("external_ref") == id_or_external_ref:
                matches.add(ev.crm_entity_id)
            elif ev.event_type == "crm.prospect_created" \
                    and ev.payload.get("email") == id_or_external_ref:
                matches.add(ev.crm_entity_id)
        if len(matches) > 1:
            raise CRMEnvelopeError(
                f"{id_or_external_ref!r} matches {len(matches)} entities — "
                "conflicting identities require explicit resolution")
        return matches.pop() if matches else None

    def get_history(self, crm_entity_id: str) -> list[CRMEvent]:
        self._require_entity(crm_entity_id)
        return self._events(crm_entity_id)

    def get_current_state(self, crm_entity_id: str) -> CRMState:
        self._require_entity(crm_entity_id)
        return fold_crm(self._events(crm_entity_id), validate=True)

    def get_decisions(self, crm_entity_id: str) -> list[dict]:
        return [{"decision_id": ev.payload["decision_id"],
                 "link_type": ev.payload.get("link_type", "subject"),
                 "occurred_at": ev.occurred_at}
                for ev in self.get_history(crm_entity_id)
                if ev.event_type == "crm.decision_linked"]

    def get_pending_approvals(self, crm_entity_id: str) -> list[str]:
        state = self.get_current_state(crm_entity_id)
        return sorted(d for d, s in state.outreach.items() if s == "drafted")

    def get_health(self, crm_entity_id: str, now: str = None) -> dict:
        from intent_engine.crm.signals import health_signal
        return health_signal(self.get_history(crm_entity_id),
                             self.get_current_state(crm_entity_id), now=now)

    def get_conversion_signal(self, crm_entity_id: str) -> dict:
        from intent_engine.crm.signals import conversion_signal
        return conversion_signal(self.get_history(crm_entity_id),
                                 self.get_current_state(crm_entity_id))

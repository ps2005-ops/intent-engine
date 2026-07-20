"""The CRM's Company Event consumer (T014) — the first real consumer of
the T013 log, using its protocol (checkpointed drain, at-least-once,
idempotent processing).

Identity policy: the consumer NEVER guesses who a company event is about.
It maps decision_id -> crm_entity_id ONLY through explicit, pre-existing
crm.decision_linked facts. Events with no mapped identity are skipped
with a counted reason; the company event itself is never modified.

Mapping (one company event -> at most one logical CRM fact):

    decision.*        -> crm.decision_activity   (observational)
    report.generated  -> crm.report_generated    (observational)

Idempotency key `company-event:<event_id>` makes replay produce zero
duplicate CRM rows.
"""
from __future__ import annotations

_DECISION_EVENT_TYPES = {
    "decision.created", "decision.submitted",
    "decision.recommendation_issued", "decision.approved",
    "decision.declined", "decision.cancelled", "decision.superseded",
    "decision.resolved", "decision.calibrated",
}
_HANDLED = _DECISION_EVENT_TYPES | {"report.generated"}


class CRMCompanyEventConsumer:
    consumer_name = "crm"

    def __init__(self, crm_service):
        self.crm = crm_service
        self.skipped_no_identity = 0

    def handles(self, event_type: str) -> bool:
        return event_type in _HANDLED

    def _entity_for_decision(self, decision_id: str):
        for ev in self.crm.store.read_all():
            if ev.event_type == "crm.decision_linked" \
                    and ev.payload.get("decision_id") == decision_id:
                return ev.crm_entity_id
        return None

    def process(self, event) -> None:
        if not event.decision_id:
            self.skipped_no_identity += 1
            return
        entity_id = self._entity_for_decision(event.decision_id)
        if entity_id is None:
            # No explicit link -> no guessing. Skipping is the policy, and
            # it is safe: a later explicit link + replay can backfill.
            self.skipped_no_identity += 1
            return
        crm_type = ("crm.report_generated"
                    if event.event_type == "report.generated"
                    else "crm.decision_activity")
        self.crm.record(
            entity_id, crm_type, actor_type="system",
            actor_id="crm_company_event_consumer",
            source="company_event_consumer",
            decision_id=event.decision_id,
            company_event_id=event.event_id,
            correlation_id=event.correlation_id,
            occurred_at=event.occurred_at,
            payload={"company_event_type": event.event_type,
                     "company_event_id": event.event_id},
            idempotency_key=f"company-event:{event.event_id}")

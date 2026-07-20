"""Knowledge/feedback Company Event consumer (T016) — observations only,
never auto-promotion. Uses the T013 protocol (checkpoint "knowledge").
"""
from __future__ import annotations

# Explicit mapping: one company event -> at most one feedback observation.
_MAPPING = {
    "decision.resolved": "feedback.founder_outcome",
    "decision.calibrated": "feedback.internal_review",
    "report.generation_failed": "feedback.internal_review",
}


class KnowledgeCompanyEventConsumer:
    consumer_name = "knowledge"

    def __init__(self, knowledge_service):
        self.svc = knowledge_service
        self.skipped = 0

    def handles(self, event_type: str) -> bool:
        return event_type in _MAPPING

    def process(self, event) -> None:
        # Observation only: event type + identities. No payload copying —
        # confidential source content never enters the feedback ledger
        # through this path. Idempotent per company event.
        self.svc.record_feedback(
            _MAPPING[event.event_type],
            content=f"observed company event {event.event_type}",
            actor_type="system", actor_id="knowledge_company_event_consumer",
            source="system", decision_id=event.decision_id,
            company_event_id=event.event_id,
            correlation_id=event.correlation_id,
            occurred_at=event.occurred_at,
            idempotency_key=f"company-event:{event.event_id}")

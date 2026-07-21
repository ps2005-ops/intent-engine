"""Research company-event consumer (T019).

A consumed event may SUGGEST a research request — and suggesting is all
it may do. It may never create a plan, start a session, acquire a source,
or extract anything. Checkpoint: "research".
"""
from __future__ import annotations

_HANDLED = {"growth.result_labelled", "decision.resolved",
            "report.generation_failed"}


class ResearchCompanyEventConsumer:
    consumer_name = "research"

    def __init__(self, research_service):
        self.svc = research_service
        self.suggested = []
        self.skipped = 0

    def handles(self, event_type: str) -> bool:
        return event_type in _HANDLED

    def process(self, event) -> None:
        subject = event.decision_id or event.subject_id
        if not subject:
            self.skipped += 1
            return
        question = (f"What does current evidence say about the outcome "
                    f"observed in {event.event_type} for {subject}?")
        result = self.svc.create_request(
            question, motivation=f"suggested by {event.event_type}",
            constraints=[f"company_event:{event.event_id}"],
            scope=event.event_type,
            originating_decision_id=event.decision_id,
            requested_by="research_company_event_consumer",
            actor_type="system")
        # A suggestion creates a REQUEST DRAFT only. No plan, no session,
        # no acquisition — those all require human plan approval.
        self.suggested.append(result["request_id"])

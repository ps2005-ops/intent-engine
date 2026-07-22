"""Executive company-event consumer (T021). Checkpoint: "executive".

A consumed event may create at most ONE decision candidate. It may never
create a package, a review, a decision link, or a roadmap entry — those
sit behind steps a person takes.

Replay creates zero duplicates, because every candidate's key derives from
its origin rather than from when it was scanned. A failure here cannot
break any upstream system: the executive log is separate, and the
consumer's checkpoint is its own.

`decision.resolved` is consumed because a resolved decision often implies
a follow-on decision — the same pattern the T019 research consumer uses.

A deliberate NON-consumption, recorded so it reads as a decision rather
than an omission: there is no `product.proposal_ready` company event.
T020's bars anticipated one ("publish only if a real consumer exists —
T021 will be one"), but adding it means modifying a CLOSED taxonomy and
T020's service, and the proposal-driven intake this subsystem needs is
already available deterministically and idempotently through
`ExecutiveService.intake_from_accepted_proposals`, which reads the Product
subsystem directly. Reading the owning subsystem is the same discipline
the CRM path used in T020 rather than inventing an event with a thin
producer story. Adding the event remains a clean, small follow-up when a
second consumer justifies it.
"""
from __future__ import annotations

from intent_engine.executive.records import REF_DECISION

_HANDLED = {"decision.resolved"}


class ExecutiveCompanyEventConsumer:
    consumer_name = "executive"

    def __init__(self, executive_service):
        self.svc = executive_service
        self.candidates = []
        self.skipped = 0

    def handles(self, event_type: str) -> bool:
        return event_type in _HANDLED

    def process(self, event) -> None:
        if event.event_type == "decision.resolved":
            self._from_resolved_decision(event)
        else:                                               # pragma: no cover
            self.skipped += 1

    def _from_resolved_decision(self, event) -> None:
        decision_id = event.decision_id or event.subject_id
        if not decision_id:
            self.skipped += 1
            return
        candidate_id = self.svc.register_candidate(
            references=[{"kind": REF_DECISION, "ref_id": decision_id}],
            origin={"kind": "resolved_decision", "origin_id": decision_id,
                    "event_type": event.event_type},
            actor_type="system",
            actor_id="executive_company_event_consumer", source="intake")
        self.candidates.append(candidate_id)

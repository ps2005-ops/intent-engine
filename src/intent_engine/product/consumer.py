"""Product company-event consumer (T020). Checkpoint: "product".

A consumed event may create at most ONE candidate opportunity. It may
never create a proposal, a spec, a review, a decision link, or a roadmap
entry — those all sit behind steps a person takes.

Replay creates zero duplicates, because every candidate's dedup key is
derived from its origin rather than from when it was scanned. A failure
here cannot break any upstream system: the product log is separate, and
the consumer's checkpoint is its own.

`crm.churned` and `crm.customer_at_risk` are deliberately NOT consumed
from the company-event bus: they are not in that taxonomy (they are CRM
store facts, per `crm/events.py`), and adding speculative event types to
a closed taxonomy with no real producer is the drift the taxonomy
discipline exists to prevent. CRM intake reads the CRM store directly —
see `ProductService.intake_from_crm`.
"""
from __future__ import annotations

from intent_engine.product.intake import intake_candidates_from_growth
from intent_engine.product.records import REF_DECISION, REF_EXPERIMENT

_HANDLED = {"growth.result_labelled", "decision.resolved"}


class ProductCompanyEventConsumer:
    consumer_name = "product"

    def __init__(self, product_service):
        self.svc = product_service
        self.candidates = []
        self.skipped = 0

    def handles(self, event_type: str) -> bool:
        return event_type in _HANDLED

    def process(self, event) -> None:
        if event.event_type == "growth.result_labelled":
            self._from_growth(event)
        elif event.event_type == "decision.resolved":
            self._from_decision(event)
        else:                                               # pragma: no cover
            self.skipped += 1

    def _from_growth(self, event) -> None:
        experiment_id = event.subject_id
        result = None
        if self.svc.growth is not None:
            try:
                result = self.svc.growth.get_result(experiment_id)
            except Exception:                               # noqa: BLE001
                result = None
        if result is None:
            # The notification carries the label; the growth log stays the
            # source of truth, so nothing is inferred beyond what is here.
            label = (event.payload or {}).get("label")
            result = {"experiment_id": experiment_id, "label": label,
                      "reasons": []}
        candidates = intake_candidates_from_growth(
            result, as_of=event.occurred_at)
        if not candidates:
            self.skipped += 1
            return
        created = self.svc._absorb_candidates(
            candidates[:1], actor_id="product_company_event_consumer")
        self.candidates.extend(c["opportunity_id"] for c in created)

    def _from_decision(self, event) -> None:
        decision_id = event.decision_id or event.subject_id
        if not decision_id:
            self.skipped += 1
            return
        statement = (f"A resolved decision has no recorded product follow-up: "
                     f"{decision_id}")
        problem = self.svc.record_problem(
            statement=statement,
            evidence_references=[{"kind": REF_DECISION,
                                  "ref_id": decision_id}],
            why_now=("the decision resolved and its product consequences are "
                     "not yet recorded"),
            what_changes_if_ignored=(
                "what the decision implied for the product stays unexamined "
                "and is rediscovered later at a higher cost"),
            first_observed_at=event.occurred_at,
            scope=f"decision:{decision_id}", actor_type="system",
            actor_id="product_company_event_consumer", source="intake")
        opportunity_id = self.svc.register_opportunity(
            problem["problem_id"],
            title=f"Record the product follow-up for decision {decision_id}",
            evidence_references=[{"kind": REF_DECISION,
                                  "ref_id": decision_id}],
            work_category="unknown",
            origin={"kind": "company_event", "event_type": event.event_type,
                    "decision_id": decision_id, "label": "UNKNOWN"},
            actor_type="system", actor_id="product_company_event_consumer",
            source="intake")
        self.candidates.append(opportunity_id)


__all__ = ["ProductCompanyEventConsumer", "REF_EXPERIMENT"]

"""Growth company-event consumer (T018).

Observation only: consuming an event never assigns, exposes, starts,
stops, or concludes anything. Checkpoints are namespaced so synthetic and
production replay independently (improvement 6).
"""
from __future__ import annotations

_HANDLED = {"crm.qualified", "crm.won", "crm.churned", "prediction.resolved"}


class GrowthCompanyEventConsumer:
    """Records that an outcome-relevant company fact occurred for an entity
    already assigned to a running experiment. It NEVER creates assignments
    (no identity guessing) and NEVER records an observation for an
    unregistered metric."""

    def __init__(self, growth_service, *, outcome_event_types=None):
        self.svc = growth_service
        self.consumer_name = f"growth_{growth_service.namespace}"
        self.outcome_event_types = set(outcome_event_types or _HANDLED)
        self.observed = 0
        self.skipped = 0

    def handles(self, event_type: str) -> bool:
        return event_type in self.outcome_event_types

    def process(self, event) -> None:
        entity = getattr(event, "crm_entity_id", None) or (
            event.subject_id if event.subject_type == "crm_entity" else None)
        if entity is None:
            self.skipped += 1
            return
        for experiment_id in self.svc.store.experiment_ids():
            state = self.svc.get_state(experiment_id)
            if not state.started or state.stopped:
                continue
            if entity not in state.assignments:
                continue                      # no guessing: not our subject
            reg = self.svc.get_registration(experiment_id)
            metric = (reg.get("primary_metric") or {}).get("metric_name")
            if metric != event.event_type:
                self.skipped += 1             # not the registered metric
                continue
            self.svc.record_observation(
                experiment_id, entity, metric_name=metric, outcome_value=True,
                source=f"company_event:{event.event_id}",
                window_start=event.occurred_at, window_end=event.occurred_at,
                occurred_at=event.occurred_at)
            self.observed += 1
            return
        self.skipped += 1

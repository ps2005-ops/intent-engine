"""CRM funnel metrics (T015) — computed from CRM event rows (historical
transitions) and folded state (current distribution). The two views stay
distinct: history counts what HAPPENED in the window; the distribution is
where entities ARE now. Ratios refuse empty denominators. Readiness is
never called a prediction.
"""
from __future__ import annotations

from intent_engine.analytics.models import (
    METRIC_VERSIONS, MetricResult, Window, ratio_metric, sample_ids,
    utc_now_iso,
)
from intent_engine.crm.state import fold_crm

_VERSION = METRIC_VERSIONS["crm_funnel"]

_TRANSITION_EVENTS = [
    "crm.prospect_created", "crm.qualified", "crm.opportunity_opened",
    "crm.proposal_sent", "crm.won", "crm.lost", "crm.disqualified",
    "crm.customer_activated", "crm.customer_at_risk",
    "crm.customer_recovered", "crm.churned",
    "crm.outreach_drafted", "crm.outreach_approved", "crm.outreach_sent",
]


def crm_funnel_metrics(crm_service, window: Window, as_of: str) -> dict:
    computed_at = utc_now_iso()
    events = crm_service.store.read_all()
    window_dict = {"start": window.start, "end": window.end}
    provenance = {"source": "marketing/crm/crm.jsonl (append-only rows; "
                            "folded via crm.state.fold_crm)",
                  "high_watermark": {"total_rows": len(events)}}

    # historical transition counts: entities deduplicated per metric
    entity_sets = {t: set() for t in _TRANSITION_EVENTS}
    for ev in events:
        if ev.event_type in entity_sets and window.contains(ev.occurred_at):
            entity_sets[ev.event_type].add(ev.crm_entity_id)

    results = {}
    for etype in _TRANSITION_EVENTS:
        name = etype.replace("crm.", "crm_")
        ids = entity_sets[etype]
        results[name] = MetricResult(
            metric_name=name, metric_version=_VERSION, computed_at=computed_at,
            window=window_dict, value=len(ids), source_count=len(events),
            annotations=("distinct crm_entity_id values with this fact "
                         "occurring in the window",),
            provenance={**provenance, "contributors": sample_ids(list(ids))})

    # stage-to-stage conversion ratios (historical, deduplicated)
    for name, num, den in (
            ("crm_ratio_qualified_to_won", "crm.won", "crm.qualified"),
            ("crm_ratio_contact_to_qualified", "crm.qualified",
             "crm.prospect_created"),
            ("crm_ratio_approved_to_sent", "crm.outreach_sent",
             "crm.outreach_approved")):
        results[name] = ratio_metric(
            name, _VERSION, computed_at, window,
            numerator=len(entity_sets[num]), denominator=len(entity_sets[den]),
            annotations=("historical transition ratio over distinct "
                         "entities; a readiness ratio, NOT a prediction",),
            provenance=provenance)

    # current-state distribution (as of now; separate view from history)
    by_entity = {}
    for ev in events:
        by_entity.setdefault(ev.crm_entity_id, []).append(ev)
    dist = {"relationship": {}, "opportunity": {}, "customer": {}}
    for entity_events in by_entity.values():
        st = fold_crm(entity_events)
        for axis in dist:
            v = getattr(st, axis)
            dist[axis][v] = dist[axis].get(v, 0) + 1
    results["crm_current_stage_distribution"] = MetricResult(
        metric_name="crm_current_stage_distribution",
        metric_version=_VERSION, computed_at=computed_at, window=window_dict,
        value={axis: dict(sorted(v.items())) for axis, v in dist.items()},
        source_count=len(by_entity),
        annotations=("current folded state per entity (all three axes); "
                     "distinct from historical transition counts above; "
                     "lost and churned stay visible",),
        provenance=provenance)
    return results

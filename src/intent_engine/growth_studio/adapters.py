"""V2.0 read adapters — product events and Marketing/Growth records flow
in as references. Raw events are never rewritten or reinterpreted:
Product event → Analytics metric → Growth observation → Hypothesis.
"""
from __future__ import annotations

from intent_engine.growth_studio.records import FUNNEL


def funnel_metrics_from_fi_store(fi_store, *, window: dict) -> list:
    """Fold T023.5 telemetry events into funnel-stage counts.

    Read-only over the FI store; returns observation inputs (metric,
    value, evidence refs = the exact event ids). An absent stage is
    reported as availability UNAVAILABLE with value None — never zero."""
    counts: dict = {stage: [] for stage in FUNNEL}
    for row in fi_store.read_all():
        if row.event_type != "fi.telemetry_event":
            continue
        event = row.payload.get("event")
        if event in counts:
            counts[event].append(row.fi_event_id)
    out = []
    for stage in FUNNEL:
        refs = counts[stage]
        if refs:
            out.append({"metric": stage, "value": len(refs),
                        "availability": "SUPPORTED",
                        "evidence_refs": refs, "window": dict(window)})
        else:
            out.append({"metric": stage, "value": None,
                        "availability": "UNAVAILABLE",
                        "evidence_refs": [], "window": dict(window)})
    return out


def marketing_portfolio(marketing_service) -> list:
    """Campaign references (ids and states) — never copied campaign bodies."""
    out = []
    for campaign_id in getattr(marketing_service, "list_campaign_ids",
                               lambda: [])():
        state = marketing_service.get_state(campaign_id)
        out.append({"campaign_id": campaign_id,
                    "state": getattr(state, "value", str(state))})
    return out


def growth_experiment_refs(growth_service, experiment_ids) -> list:
    """Experiment references (id + registration) — the science stays in
    the Growth subsystem."""
    out = []
    for experiment_id in experiment_ids:
        registration = growth_service.get_registration(experiment_id)
        out.append({"experiment_id": experiment_id,
                    "registered": bool(registration)})
    return out

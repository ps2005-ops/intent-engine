"""DecisionEvent -> Company Event bridge (T013).

One-way and deterministic. The DecisionEvent store stays the ONLY source
of truth for decision state; this bridge notifies the integration log that
those authoritative facts happened. Nothing here mutates, reinterprets, or
re-folds decision state.

Idempotency key: `decision-event:<decision_event_id>` — replaying the
bridge over the full history publishes zero duplicates, which is also what
makes it independently replayable without a separate checkpoint file.
"""
from __future__ import annotations

from intent_engine.events.publisher import CompanyEventBus

# Deterministic mapping. Every DecisionEvent type is either bridged or
# EXPLICITLY skipped — nothing falls through silently (tested).
BRIDGED_EVENT_TYPES = {
    "DecisionCreated":          "decision.created",
    "DecisionSubmitted":        "decision.submitted",
    "RecommendationIssued":     "decision.recommendation_issued",
    "DecisionApproved":         "decision.approved",
    "DecisionDeclined":         "decision.declined",
    "DecisionCancelled":        "decision.cancelled",
    "DecisionSuperseded":       "decision.superseded",
    "DecisionResolved":         "decision.resolved",
    "DecisionCalibrated":       "decision.calibrated",
    "AnalysisFailed":           "decision.analysis_failed",
    "PredictionLoggingFailed":  "decision.prediction_logging_failed",
    "ReportGenerationFailed":   "decision.report_generation_failed",
}
# Skipped on purpose:
#  - owner/execution/assumption events: internal state detail with no
#    current company-log consumer (add when one exists, not before);
#  - retry/recovery/delivery: operational detail of the decision store;
#  - privacy events: privacy-ONLY facts never leave the authoritative
#    store (the integration log fans out broadly by design).
SKIPPED_EVENT_TYPES = {
    "OwnerAssigned", "OwnerTransferred", "ExecutionStarted",
    "ExecutionPaused", "ExecutionResumed", "ExecutionCompleted",
    "AssumptionChanged", "DeliveryFailed", "RetryScheduled",
    "RecoveryCompleted", "RedactionRequested", "AccessRestricted",
    "Anonymized", "Tombstoned",
}


def bridge_decision_events(decision_service, bus: CompanyEventBus,
                           decision_id: str | None = None) -> dict:
    """Publish every eligible DecisionEvent (for one decision, or all) into
    the company log, at most once each. Returns counts. Re-running is a
    no-op for already-bridged events (idempotency key per source event)."""
    from intent_engine.core.decision_record import EVENT_TYPES as DOMAIN_TYPES
    unmapped = DOMAIN_TYPES - set(BRIDGED_EVENT_TYPES) - SKIPPED_EVENT_TYPES
    if unmapped:
        raise RuntimeError(
            f"decision event types with no bridge policy: {sorted(unmapped)} "
            "— map or explicitly skip them before bridging")

    ids = ([decision_id] if decision_id
           else decision_service.list_decision_ids())
    published = duplicates = skipped = 0
    for did in ids:
        record = decision_service.get_decision(did)
        for ev in decision_service.get_events(did):
            if ev["event_type"] in SKIPPED_EVENT_TYPES:
                skipped += 1
                continue
            company_type = BRIDGED_EVENT_TYPES[ev["event_type"]]
            payload = dict(ev.get("payload") or {})
            payload["source_event_id"] = ev["event_id"]
            payload["sequence_number"] = ev["sequence_number"]
            payload["decision_key"] = record.decision_key
            result = bus.publish(
                company_type, subject_type="decision", subject_id=did,
                producer="decision_event_bridge",
                actor_type=ev["actor_type"], actor_id=ev["actor_id"],
                source="bridge", payload=payload, decision_id=did,
                correlation_id=did, causation_id=ev["event_id"],
                idempotency_key=f"decision-event:{ev['event_id']}",
                occurred_at=ev["occurred_at"])
            if result.duplicate:
                duplicates += 1
            else:
                published += 1
    return {"published": published, "duplicates": duplicates,
            "skipped": skipped}

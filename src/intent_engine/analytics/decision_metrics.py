"""Decision lifecycle metrics (T015) — derived from the authoritative
DecisionEvent history via DecisionService reads, never from copied status
fields. Durations use occurred_at (when the fact happened), so a
late-recorded event lands in the window it belongs to.
"""
from __future__ import annotations

from datetime import datetime

from intent_engine.analytics.models import (
    METRIC_VERSIONS, MetricResult, Window, median_days, sample_ids,
    utc_now_iso,
)

_VERSION = METRIC_VERSIONS["decision_metrics"]

_COUNTED_EVENTS = {
    "DecisionCreated": "decisions_created",
    "RecommendationIssued": "recommendations_issued",
    "DecisionApproved": "decisions_approved",
    "DecisionDeclined": "decisions_declined",
    "DecisionCancelled": "decisions_cancelled",
    "DecisionSuperseded": "decisions_superseded",
    "ExecutionStarted": "execution_started",
    "DecisionResolved": "decisions_resolved",
    "DecisionCalibrated": "decisions_calibrated",
}

# Stalled rule v1 (explicit + versioned): a decision still in
# draft/under_review whose LAST event occurred more than 14 days before
# as_of. Not a score — a named, testable boundary.
STALLED_RULE = "stalled.v1: decision_status in (draft, under_review) and no event for > 14 days"
_STALLED_DAYS = 14


def decision_metrics(decision_service, window: Window, as_of: str) -> dict:
    computed_at = utc_now_iso()
    counts = {v: 0 for v in _COUNTED_EVENTS.values()}
    contributors = {v: [] for v in _COUNTED_EVENTS.values()}
    durations = {"median_days_to_recommendation": [],
                 "median_days_to_decision": [],
                 "median_days_to_execution": [],
                 "median_days_to_resolution": []}
    stage_distribution = {}
    stalled = []
    n_events = 0
    latest_seq = {}

    ids = decision_service.list_decision_ids()
    for did in ids:
        events = decision_service.get_events(did)
        n_events += len(events)
        if events:
            latest_seq[did] = events[-1]["sequence_number"]
        by_type = {}
        for ev in events:
            by_type.setdefault(ev["event_type"], ev["occurred_at"])
            if ev["event_type"] in _COUNTED_EVENTS \
                    and window.contains(ev["occurred_at"]):
                key = _COUNTED_EVENTS[ev["event_type"]]
                counts[key] += 1
                contributors[key].append(did)
        created = by_type.get("DecisionCreated")
        if created:
            for target, key in (("RecommendationIssued",
                                 "median_days_to_recommendation"),
                                ("DecisionResolved",
                                 "median_days_to_resolution")):
                if by_type.get(target) and window.contains(by_type[target]):
                    durations[key].append((created, by_type[target]))
            decided = by_type.get("DecisionApproved") or by_type.get("DecisionDeclined")
            if decided and window.contains(decided):
                durations["median_days_to_decision"].append((created, decided))
        approved = by_type.get("DecisionApproved")
        if approved and by_type.get("ExecutionStarted") \
                and window.contains(by_type["ExecutionStarted"]):
            durations["median_days_to_execution"].append(
                (approved, by_type["ExecutionStarted"]))

        # current-state distribution + stalled (as_of view; superseded and
        # other terminal decisions stay visible — nothing disappears)
        state = decision_service.get_current_state(did)
        stage_distribution[state.decision_status] = \
            stage_distribution.get(state.decision_status, 0) + 1
        if state.decision_status in ("draft", "under_review") and events:
            last = max(ev["occurred_at"] for ev in events)
            age_days = (datetime.fromisoformat(as_of)
                        - datetime.fromisoformat(last)).total_seconds() / 86400
            if age_days > _STALLED_DAYS:
                stalled.append(did)

    provenance = {"source": "DecisionService (decision_events fold + history)",
                  "decisions_scanned": len(ids),
                  "events_scanned": n_events,
                  "high_watermark": {"latest_sequence_by_decision":
                                     dict(sorted(latest_seq.items())[:10]),
                                     "total_decisions": len(ids)}}

    results = {}
    for key, value in sorted(counts.items()):
        results[key] = MetricResult(
            metric_name=key, metric_version=_VERSION, computed_at=computed_at,
            window={"start": window.start, "end": window.end}, value=value,
            source_count=len(ids),
            annotations=("counted from event occurred_at within the window",),
            provenance={**provenance,
                        "contributors": sample_ids(contributors[key])})
    for key, pairs in sorted(durations.items()):
        m = median_days(pairs)
        results[key] = MetricResult(
            metric_name=key, metric_version=_VERSION, computed_at=computed_at,
            window={"start": window.start, "end": window.end},
            status="OK" if m is not None else "UNAVAILABLE",
            value=m, source_count=len(pairs),
            annotations=(("median over event-derived durations (occurred_at)",)
                         if m is not None else
                         ("no completed pairs in window — unavailable, not zero",)),
            provenance=provenance)
    results["decision_stage_distribution"] = MetricResult(
        metric_name="decision_stage_distribution", metric_version=_VERSION,
        computed_at=computed_at,
        window={"start": window.start, "end": window.end},
        value=dict(sorted(stage_distribution.items())),
        source_count=len(ids),
        annotations=("current folded decision_status per decision, as of "
                     "computation; superseded decisions remain visible",),
        provenance=provenance)
    results["stalled_decisions"] = MetricResult(
        metric_name="stalled_decisions", metric_version=_VERSION,
        computed_at=computed_at,
        window={"start": window.start, "end": window.end},
        value=len(stalled), source_count=len(ids),
        annotations=(STALLED_RULE,),
        provenance={**provenance, "contributors": sample_ids(stalled)})
    return results

"""Founder-report activity metrics (T015) — from company events
(report.generated / report.generation_failed) + DecisionService reads.
Generation is generation: there is NO reading/engagement observation
source, and this module says so instead of inventing one.
"""
from __future__ import annotations

from intent_engine.analytics.models import (
    METRIC_VERSIONS, NO_OBSERVATION_SOURCE, MetricResult, Window, sample_ids,
    utc_now_iso,
)

_VERSION = METRIC_VERSIONS["report_metrics"]


def report_metrics(event_store, decision_service, window: Window,
                   as_of: str) -> dict:
    computed_at = utc_now_iso()
    events = event_store.read_all()
    window_dict = {"start": window.start, "end": window.end}
    provenance = {"source": "company event log (report.* events, producer "
                            "report_renderer) + DecisionService ids",
                  "high_watermark": {"event_log_offset": len(events)}}

    generated = [e for e in events if e.event_type == "report.generated"
                 and window.contains(e.occurred_at)]
    failed = [e for e in events if e.event_type == "report.generation_failed"
              and window.contains(e.occurred_at)]
    per_decision = {}
    for e in generated:
        if e.decision_id:
            per_decision[e.decision_id] = per_decision.get(e.decision_id, 0) + 1
    decision_ids = (decision_service.list_decision_ids()
                    if decision_service else [])
    without_reports = [d for d in decision_ids if d not in per_decision]

    def result(name, value, note, extra_prov=None, status="OK"):
        return MetricResult(
            metric_name=name, metric_version=_VERSION, computed_at=computed_at,
            window=window_dict, status=status, value=value,
            source_count=len(events), annotations=(note,),
            provenance={**provenance, **(extra_prov or {})})

    results = {
        "reports_generated": result(
            "reports_generated", len(generated),
            "report.generated events in window (generation, NOT reading)"),
        "report_generation_failures": result(
            "report_generation_failures", len(failed),
            "failures stay visible; zero here does not prove quality"),
        "reports_per_decision_max": result(
            "reports_per_decision_max",
            max(per_decision.values()) if per_decision else 0,
            "a decision may legitimately have several report passes"),
        "decisions_without_reports": result(
            "decisions_without_reports", len(without_reports),
            "decisions with no report.generated event in the log",
            {"contributors": sample_ids(without_reports)}),
        "report_engagement": result(
            "report_engagement", None,
            "no reading/sharing observation source exists — engagement is "
            "not invented from generation facts",
            status=NO_OBSERVATION_SOURCE),
    }
    return results

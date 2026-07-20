"""AnalyticsService (T015) — the one read-side interface. Read-only
dependencies on the authoritative stores; deterministic for a fixed
as_of; a missing source yields an explicit UNAVAILABLE section, never
misleading zeroes.
"""
from __future__ import annotations

from dataclasses import asdict

from intent_engine.analytics.calibration import calibration_metrics
from intent_engine.analytics.consumer_health import consumer_health
from intent_engine.analytics.crm_metrics import crm_funnel_metrics
from intent_engine.analytics.decision_metrics import decision_metrics
from intent_engine.analytics.models import (
    METRIC_VERSIONS, UNAVAILABLE, MetricResult, make_window, utc_now_iso,
)
from intent_engine.analytics.report_metrics import report_metrics


def _unavailable_section(name: str, reason: str, window, computed_at) -> dict:
    return {name: MetricResult(
        metric_name=name, metric_version=METRIC_VERSIONS.get(
            name, f"{name}.v1"),
        computed_at=computed_at, window={"start": window.start,
                                         "end": window.end},
        status=UNAVAILABLE, value=None,
        annotations=(reason,), provenance={})}


class AnalyticsService:
    """All dependencies optional and read-only: pass the stores you have;
    each absent store produces an honest UNAVAILABLE section."""

    def __init__(self, decision_service=None, crm_service=None,
                 event_store=None, ledger_path=None):
        self.decision_service = decision_service
        self.crm_service = crm_service
        self.event_store = event_store
        self.ledger_path = ledger_path

    def decision_metrics(self, window_spec="all", as_of=None) -> dict:
        as_of = as_of or utc_now_iso()
        window = make_window(window_spec, as_of)
        if self.decision_service is None:
            return _unavailable_section(
                "decision_metrics", "no DecisionService configured",
                window, utc_now_iso())
        return decision_metrics(self.decision_service, window, as_of)

    def calibration_metrics(self, window_spec="all", as_of=None,
                            source=None) -> dict:
        as_of = as_of or utc_now_iso()
        window = make_window(window_spec, as_of)
        if self.ledger_path is None:
            return _unavailable_section(
                "calibration_metrics", "no prediction ledger configured",
                window, utc_now_iso())
        return calibration_metrics(self.ledger_path, window, as_of,
                                   source=source)

    def crm_funnel_metrics(self, window_spec="all", as_of=None) -> dict:
        as_of = as_of or utc_now_iso()
        window = make_window(window_spec, as_of)
        if self.crm_service is None:
            return _unavailable_section(
                "crm_funnel", "no CRMService configured", window,
                utc_now_iso())
        return crm_funnel_metrics(self.crm_service, window, as_of)

    def report_metrics(self, window_spec="all", as_of=None) -> dict:
        as_of = as_of or utc_now_iso()
        window = make_window(window_spec, as_of)
        if self.event_store is None:
            return _unavailable_section(
                "report_metrics", "no company event store configured",
                window, utc_now_iso())
        return report_metrics(self.event_store, self.decision_service,
                              window, as_of)

    def consumer_health(self, window_spec="all", as_of=None) -> dict:
        as_of = as_of or utc_now_iso()
        window = make_window(window_spec, as_of)
        if self.event_store is None:
            return _unavailable_section(
                "consumer_health", "no company event store configured",
                window, utc_now_iso())
        return consumer_health(self.event_store, window, as_of)

    def snapshot(self, window_spec="all", as_of=None) -> dict:
        """One combined summary; sections reuse the section methods (no
        duplicated computation). JSON-safe via MetricResult.to_json."""
        as_of = as_of or utc_now_iso()
        sections = {
            "decisions": self.decision_metrics(window_spec, as_of),
            "calibration": self.calibration_metrics(window_spec, as_of),
            "crm_funnel": self.crm_funnel_metrics(window_spec, as_of),
            "reports": self.report_metrics(window_spec, as_of),
            "consumer_health": self.consumer_health(window_spec, as_of),
        }
        return {
            "as_of": as_of,
            "window_spec": window_spec,
            "metric_versions": dict(sorted(METRIC_VERSIONS.items())),
            "sections": {name: {k: asdict(v) for k, v in metrics.items()}
                         for name, metrics in sections.items()},
        }

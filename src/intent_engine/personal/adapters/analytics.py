"""Analytics read adapter (T023).

Translates a `MetricResult` into a SourceClaim, preserving the honest
status the analytics subsystem set — a metric marked UNAVAILABLE stays
UNAVAILABLE; it is never smoothed into a number. The adapter computes no
metric.
"""
from __future__ import annotations

from intent_engine.personal.adapters.base import Adapter, unavailable_claim
from intent_engine.personal.records import (
    AVAIL_SUPPORTED, AVAIL_UNAVAILABLE, SourceClaim, SourceRef, freshness_of,
)


class AnalyticsAdapter(Adapter):
    subsystem = "analytics"

    def metric_claim(self, metric_result) -> SourceClaim:
        """`metric_result` is a MetricResult (or a dict of one). The
        adapter names its status and value; it never recomputes it."""
        if metric_result is None:
            return unavailable_claim("analytics.metric",
                                     "no metric result was supplied")
        m = metric_result if isinstance(metric_result, dict) else \
            metric_result.__dict__
        status = m.get("status", "UNAVAILABLE")
        name = m.get("metric_name", "metric")
        window = m.get("window", {}) or {}
        observed = window.get("end")
        fresh = freshness_of(observed, self.as_of)
        if status != "OK":
            # An UNAVAILABLE / TOO FEW metric is preserved as such.
            return SourceClaim(
                claim_id=f"analytics.{name}",
                text=f"{name}: {status}"
                     + (f" — {'; '.join(m.get('annotations', []))}"
                        if m.get("annotations") else ""),
                availability=AVAIL_UNAVAILABLE, source_refs=(),
                freshness_status=fresh)
        return SourceClaim(
            claim_id=f"analytics.{name}",
            text=f"{name} = {m.get('value')}",
            availability=AVAIL_SUPPORTED,
            source_refs=(SourceRef(
                subsystem="analytics", artifact_type="metric_result",
                artifact_id=name,
                replay_id=f"analytics:{name}:{self.as_of}", as_of=self.as_of,
                observed_at=observed, freshness_status=fresh,
                snapshot_version=str(m.get("metric_version"))),),
            transformation="direct", freshness_status=fresh)

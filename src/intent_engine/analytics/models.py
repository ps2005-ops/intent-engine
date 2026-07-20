"""The canonical analytics contract (T015): MetricResult + versions +
window semantics.

Analytics derives facts; it never creates them. Zero is a value;
UNAVAILABLE means the value cannot honestly be computed. Every result
carries its metric version, explicit UTC window, and provenance, so any
number can be recomputed from the authoritative stores that produced it.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

# The metric version registry — one place, no anonymous version strings.
METRIC_VERSIONS = {
    "decision_metrics": "decision_metrics.v1",
    "calibration_metrics": "calibration_metrics.v1",
    "crm_funnel": "crm_funnel.v1",
    "report_metrics": "report_metrics.v1",
    "consumer_health": "consumer_health.v1",
}

# Honest statuses — never replaced by optimistic zeroes.
OK = "OK"
UNAVAILABLE = "UNAVAILABLE"
TOO_FEW = "TOO FEW RESOLVED TO CLAIM CALIBRATION"
NO_OBSERVATION_SOURCE = "NO OBSERVATION SOURCE"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Window:
    """[start, end] inclusive on both boundaries, UTC. `None` start means
    all time. Built from an explicit as_of — never the local clock inside
    metric code."""
    start: str | None
    end: str

    def contains(self, iso_ts: str | None) -> bool:
        if not iso_ts:
            return False
        if self.start is not None and iso_ts < self.start:
            return False
        return iso_ts <= self.end


def make_window(spec: str, as_of: str) -> Window:
    """spec: 'all' | '7d' | '30d' | '90d' | 'start..end' (custom,
    inclusive)."""
    if spec == "all":
        return Window(start=None, end=as_of)
    if spec.endswith("d") and spec[:-1].isdigit():
        end_dt = datetime.fromisoformat(as_of)
        start_dt = end_dt - timedelta(days=int(spec[:-1]))
        return Window(start=start_dt.isoformat(timespec="seconds"), end=as_of)
    if ".." in spec:
        start, end = spec.split("..", 1)
        return Window(start=start, end=end)
    raise ValueError(f"unknown window spec: {spec!r}")


@dataclass(frozen=True)
class MetricResult:
    metric_name: str
    metric_version: str
    computed_at: str
    window: dict                 # {"start": ..., "end": ...}
    status: str = OK             # OK | UNAVAILABLE | TOO FEW ... | NO OBSERVATION SOURCE
    value: object = None
    numerator: int | None = None
    denominator: int | None = None
    source_count: int = 0
    scope: str = "all"
    annotations: tuple = ()      # visible reasons / caveats, order-stable
    provenance: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def ratio_metric(name: str, version: str, computed_at: str, window: Window,
                 numerator: int, denominator: int, *, scope: str = "all",
                 annotations: tuple = (), provenance: dict = None
                 ) -> MetricResult:
    """A ratio that refuses to fabricate a percentage: an empty denominator
    is UNAVAILABLE, never 0%."""
    if denominator == 0:
        return MetricResult(
            metric_name=name, metric_version=version, computed_at=computed_at,
            window=asdict(window), status=UNAVAILABLE, value=None,
            numerator=numerator, denominator=0, scope=scope,
            annotations=annotations + (
                "empty denominator — a ratio cannot honestly be computed",),
            provenance=provenance or {})
    return MetricResult(
        metric_name=name, metric_version=version, computed_at=computed_at,
        window=asdict(window), status=OK,
        value=round(numerator / denominator, 4),
        numerator=numerator, denominator=denominator,
        source_count=denominator, scope=scope, annotations=annotations,
        provenance=provenance or {})


def _median(values: list) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def median_days(pairs: list) -> float | None:
    """Median of (start_iso, end_iso) durations in days; None when empty."""
    diffs = []
    for start, end in pairs:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
        diffs.append((b - a).total_seconds() / 86400.0)
    m = _median(diffs)
    return round(m, 3) if m is not None else None


def sample_ids(ids: list, limit: int = 10) -> dict:
    """Bounded contributor exposure: sample + total, never an unbounded
    list by default."""
    ordered = sorted(ids)
    return {"total_contributing": len(ordered),
            "sample_ids": ordered[:limit]}

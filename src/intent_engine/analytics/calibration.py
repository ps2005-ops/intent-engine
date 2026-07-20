"""Prediction calibration views (T015). `prediction_ledger.brier_summary`
remains the ONE authoritative grading computation — this module reuses
it and adds honest counting around it. The A-M5 evidence gate is
load-bearing: below 30 resolved eligible predictions (per scope) the view
says TOO FEW RESOLVED TO CLAIM CALIBRATION, and even at/above the gate no
external accuracy claim is made here — clearing the count threshold still
requires the founder calibration review (A-M5's second half).
"""
from __future__ import annotations

from intent_engine.analytics.models import (
    METRIC_VERSIONS, TOO_FEW, UNAVAILABLE, MetricResult, Window, utc_now_iso,
)
from intent_engine.core.prediction_ledger import brier_summary, list_predictions

_VERSION = METRIC_VERSIONS["calibration_metrics"]
CALIBRATION_GATE_RESOLVED = 30       # A-M5: per source, before ANY claim


def calibration_metrics(ledger_path, window: Window, as_of: str,
                        source=None) -> dict:
    computed_at = utc_now_iso()
    preds = list_predictions(path=ledger_path, source=source)
    in_window = [p for p in preds if window.contains(p.created_at)]
    resolved = [p for p in preds
                if p.outcome in ("happened", "did_not_happen")]
    unresolvable = [p for p in preds if p.outcome == "unresolvable"]
    unresolved = [p for p in preds if p.outcome is None]
    overdue = [p for p in unresolved if p.resolve_by < as_of[:10]]

    provenance = {"source": "prediction_ledger (append-only; grading by "
                            "resolve_prediction, summarized by brier_summary "
                            "— reused, never forked)",
                  "scope_source": source or "all",
                  "high_watermark": {"total_rows": len(preds)}}
    window_dict = {"start": window.start, "end": window.end}

    def count(name, value, note, ids=None):
        return MetricResult(
            metric_name=name, metric_version=_VERSION, computed_at=computed_at,
            window=window_dict, value=value, source_count=len(preds),
            scope=source or "all", annotations=(note,), provenance=provenance)

    results = {
        "predictions_total": count(
            "predictions_total", len(preds), "all ledger rows in scope"),
        "predictions_created_in_window": count(
            "predictions_created_in_window", len(in_window),
            "created_at within window"),
        "predictions_resolved": count(
            "predictions_resolved", len(resolved),
            "outcome in (happened, did_not_happen) — the only rows Brier "
            "scoring may use"),
        "predictions_unresolved": count(
            "predictions_unresolved", len(unresolved),
            "outcome still open — never counted in any Brier score"),
        "predictions_excluded_unresolvable": count(
            "predictions_excluded_unresolvable", len(unresolvable),
            "explicitly unresolvable — excluded from scoring, counted "
            "separately, never treated as a miss"),
        "predictions_overdue_unresolved": count(
            "predictions_overdue_unresolved", len(overdue),
            "resolve_by date has passed with no resolution recorded"),
    }

    if not preds:
        results["calibration"] = MetricResult(
            metric_name="calibration", metric_version=_VERSION,
            computed_at=computed_at, window=window_dict, status=UNAVAILABLE,
            value=None, scope=source or "all",
            annotations=("no predictions in scope — nothing to summarize",),
            provenance=provenance)
        return results

    if len(resolved) < CALIBRATION_GATE_RESOLVED:
        results["calibration"] = MetricResult(
            metric_name="calibration", metric_version=_VERSION,
            computed_at=computed_at, window=window_dict, status=TOO_FEW,
            value=None, numerator=len(resolved),
            denominator=CALIBRATION_GATE_RESOLVED, scope=source or "all",
            annotations=(
                f"{len(resolved)} resolved of the {CALIBRATION_GATE_RESOLVED} "
                "required by the A-M5 gate — no calibration statement is made",
                "the ledger accumulates from here; counting continues honestly",),
            provenance=provenance)
        return results

    summary = brier_summary(source=source, path=ledger_path)
    bands = {k: {"count": b.count, "observed_rate": round(b.realized_rate, 4)}
             for k, b in sorted(summary.calibration_buckets.items())}
    results["calibration"] = MetricResult(
        metric_name="calibration", metric_version=_VERSION,
        computed_at=computed_at, window=window_dict, status="OK",
        value={"resolved_count": summary.count,
               "mean_brier": round(summary.mean_brier, 4),
               "confidence_bands": bands},
        numerator=len(resolved), denominator=CALIBRATION_GATE_RESOLVED,
        scope=source or "all",
        annotations=(
            "computed by the authoritative brier_summary over resolved rows",
            "count gate met; per A-M5 the founder calibration review is "
            "still required before any external claim — this view states "
            "probability quality only, nothing more",),
        provenance=provenance)
    return results

"""Typed citations (T016). Every promoted lesson must cite something that
actually exists; a citation never broadens scope, and an analytics metric
whose status is UNAVAILABLE / TOO FEW / NO OBSERVATION SOURCE can never
support a positive claim.
"""
from __future__ import annotations

from intent_engine.knowledge.records import (
    MARKER_CITATION_REQUIRED, KnowledgeError,
)

CITATION_TYPES = {"decision_event", "prediction_ledger_row", "crm_event",
                  "feedback_record", "analytics_metric", "report",
                  "external_source"}

_NEGATIVE_METRIC_STATUSES = {"UNAVAILABLE",
                             "TOO FEW RESOLVED TO CLAIM CALIBRATION",
                             "NO OBSERVATION SOURCE"}


def validate_citations(citations, resolvers) -> None:
    """`resolvers` is a dict of optional read-only lookups:
    decision_service, ledger_path, crm_service, feedback_store,
    event_store, metric_lookup (callable name->MetricResult-or-dict)."""
    if not citations:
        raise KnowledgeError(f"{MARKER_CITATION_REQUIRED}: at least one "
                             "valid citation is mandatory")
    for c in citations:
        ctype = c.get("source_type")
        sid = c.get("source_id")
        if ctype not in CITATION_TYPES:
            raise KnowledgeError(f"unknown citation source_type: {ctype!r}")
        if not sid:
            raise KnowledgeError("citation requires a stable source_id")
        if ctype == "external_source":
            for fld in ("title", "url"):
                if not c.get(fld):
                    raise KnowledgeError(
                        f"external citation requires {fld!r} (no fabricated "
                        "references)")
            continue
        _resolve_internal(ctype, sid, c, resolvers)


def _resolve_internal(ctype, sid, citation, resolvers) -> None:
    if ctype == "decision_event":
        svc = resolvers.get("decision_service")
        if svc is not None:
            did = citation.get("decision_id") or sid
            events = svc.get_events(did) if svc.get_decision(did) else []
            if citation.get("decision_id") and not events:
                raise KnowledgeError(f"citation decision {did!r} not found")
            if not citation.get("decision_id") and not any(
                    e["event_id"] == sid for e in
                    (events or _all_events(svc))):
                raise KnowledgeError(f"citation decision_event {sid!r} not found")
    elif ctype == "prediction_ledger_row":
        path = resolvers.get("ledger_path")
        if path is not None:
            from intent_engine.core.prediction_ledger import list_predictions
            if not any(p.id == sid for p in list_predictions(path=path)):
                raise KnowledgeError(f"citation prediction {sid!r} not found")
    elif ctype == "crm_event":
        crm = resolvers.get("crm_service")
        if crm is not None and not any(
                r.crm_event_id == sid for r in crm.store.read_all()):
            raise KnowledgeError(f"citation crm_event {sid!r} not found")
    elif ctype == "feedback_record":
        store = resolvers.get("feedback_store")
        if store is not None and not any(
                r.row_id == sid for r in store.read_all()):
            raise KnowledgeError(f"citation feedback {sid!r} not found")
    elif ctype == "report":
        store = resolvers.get("event_store")
        if store is not None and not any(
                e.event_type == "report.generated"
                and (e.subject_id == sid or e.event_id == sid)
                for e in store.read_all()):
            raise KnowledgeError(f"citation report {sid!r} not found")
    elif ctype == "analytics_metric":
        lookup = resolvers.get("metric_lookup")
        if lookup is not None:
            metric = lookup(sid)
            if metric is None:
                raise KnowledgeError(f"citation metric {sid!r} not found")
            status = (metric.get("status") if isinstance(metric, dict)
                      else getattr(metric, "status", "OK"))
            if status in _NEGATIVE_METRIC_STATUSES:
                raise KnowledgeError(
                    f"analytics metric {sid!r} has status {status!r} — it "
                    "cannot support a positive claim (the metric's own "
                    "honesty is load-bearing)")


def _all_events(svc):
    out = []
    for did in svc.list_decision_ids():
        out.extend(svc.get_events(did))
    return out

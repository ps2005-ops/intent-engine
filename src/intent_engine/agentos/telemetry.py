"""Shared telemetry (T022) — read-only derivations over any store.

Every agent store already carries the facts a founder or an operator would
want to observe; nothing new is recorded. `store_telemetry` DERIVES a
handful of counts from the append-only rows that are already there — total
rows, model-produced rows (those stamped with a `model_version` in
provenance), typed model failures and rejections, and the last event id —
so a future dashboard (T023) reads one shape rather than four.

This is a read model. It writes nothing, changes no behaviour, and knows
nothing domain-specific: it looks only at fields every agent event shares
(event_type, provenance, the event-id attribute).
"""
from __future__ import annotations

TELEMETRY_VERSION = "agentos_telemetry.v1"

# Substrings that mark a typed model failure/rejection event across agents:
# research.extraction_failed, product.draft_failed/draft_rejected,
# executive.draft_failed/draft_rejected.
_FAILURE_MARKERS = ("extraction_failed", "draft_failed")
_REJECTION_MARKERS = ("evidence_rejected", "draft_rejected")


def _event_id(row):
    for attr in ("research_event_id", "product_event_id",
                 "executive_event_id", "event_id", "id"):
        value = getattr(row, attr, None)
        if value:
            return value
    return None


def store_telemetry(store) -> dict:
    """Counts derived from `store.read_all()`. Deterministic and
    read-only."""
    rows = store.read_all()
    model_rows = sum(1 for r in rows
                     if (getattr(r, "provenance", None) or {}).get("model_version"))
    failures = sum(1 for r in rows
                   if any(m in r.event_type for m in _FAILURE_MARKERS))
    rejections = sum(1 for r in rows
                     if any(m in r.event_type for m in _REJECTION_MARKERS))
    return {
        "telemetry_version": TELEMETRY_VERSION,
        "rows": len(rows),
        "model_rows": model_rows,
        "typed_model_failures": failures,
        "typed_model_rejections": rejections,
        "distinct_event_types": len({r.event_type for r in rows}),
        "last_event_id": _event_id(rows[-1]) if rows else None,
        "note": ("a read-only derivation over the append-only log; it "
                 "records nothing and changes no behaviour"),
    }

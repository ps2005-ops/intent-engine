#!/usr/bin/env python3
"""Two breaker waves, side by side, at the levels that decide the batch.

    PYTHONPATH=src python3 scripts/v5_breaker_compare.py BEFORE.json AFTER.json

WHAT THIS REFUSES TO DO
------------------------
Print an improvement against a baseline that was never measured. Batch 12's
own comparison summed a BEFORE wave that predated the independence producer
and was about to report "0 → 9 improved", inventing a starting point for a
number nothing had counted. A field absent on one side is UNAVAILABLE on that
side and the delta is UNAVAILABLE — never the value itself, and never zero.

A RISE IS NOT THE POINT
-----------------------
Raw yield can stay flat while independent external evidence rises and
concentration falls, and that is the stronger result. Every metric is printed
with the population it is a share of, so a reader can tell which happened.
"""
from __future__ import annotations

import json
import pathlib
import sys

UNAVAILABLE = "UNAVAILABLE"


def _dig(payload, *path, default=None):
    node = payload
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _numeric(value) -> bool:
    """A number a delta may be taken over. `bool` is deliberately excluded:
    it is an `int` in Python, and "True → False (-1)" is not a change of one,
    it is a change of state."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _show(value) -> str:
    """A value as it actually is. ABSENT is the only thing rendered
    UNAVAILABLE.

    An earlier version of this function collapsed every non-numeric value to
    UNAVAILABLE so it could return a uniform pair — which printed a live
    `BLOCKED_EXTERNAL_CREDITS` and a live `STABLE` as though nothing had been
    measured. That is the same missing-vs-present error this instrument
    exists to police, committed by the instrument.
    """
    return UNAVAILABLE if value is None else str(value)


def _delta(before, after):
    """The change, or why there is not one. Never invents a baseline."""
    if not (_numeric(before) and _numeric(after)):
        return f"{_show(before)} → {_show(after)}", UNAVAILABLE
    return f"{before} → {after}", round(after - before, 4)


ROWS = (
    ("documents", ("evidence", "documents")),
    ("retrieval yield", ("retrieval", "retrieval_yield")),
    ("attempted", ("retrieval", "attempted")),
    ("HTTP 403", ("retrieval", "http_status_counts", "HTTP 403")),
    ("HTTP 404", ("retrieval", "http_status_counts", "HTTP 404")),
    ("fetch seconds", ("retrieval", "fetch_seconds")),
    ("independent documents", ("independence", "independent_documents")),
    ("independent share", ("independence", "independent_document_share")),
    ("company self reports", ("independence", "company_self_reports")),
    ("duplicates", ("independence", "duplicate_documents")),
    ("republications", ("independence", "republications")),
    ("unknown lineage", ("independence", "unknown_lineage")),
    ("mean concentration", ("independence", "mean_source_concentration")),
    ("seconds / independent doc",
     ("independence", "seconds_per_independent_document")),
    ("learning conversion",
     ("learning_conversion", "learning_conversion")),
    ("attribution state", ("learning_conversion", "state")),
    ("HALL detected", ("high_activity_low_learning", "detected")),
    ("HALL status", ("high_activity_low_learning", "status")),
    ("first starved conversion",
     ("high_activity_low_learning", "first_starved_conversion")),
)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    before = json.loads(pathlib.Path(sys.argv[1]).read_text())
    after = json.loads(pathlib.Path(sys.argv[2]).read_text())
    bs, as_ = before.get("cohort_summary", {}), after.get("cohort_summary", {})

    print(f"\nBEFORE {_dig(before, 'frozen', 'runtime_sha', default='?')[:12]}"
          f"   AFTER {_dig(after, 'frozen', 'runtime_sha', default='?')[:12]}")
    print("=" * 78)
    for label, path in ROWS:
        text, delta = _delta(_dig(bs, *path), _dig(as_, *path))
        suffix = "" if delta == UNAVAILABLE else f"   ({delta:+})" \
            if isinstance(delta, (int, float)) else ""
        print(f"{label:<28} {text}{suffix}")

    # PER COMPANY (§32). A cohort total can improve while a company loses
    # every document, and that is the failure a ten-case wave exists to find.
    print("\n" + "=" * 78)
    print(f"{'company':<26}{'docs':>10}{'independent':>14}{'corroboration':>26}")
    print("=" * 78)
    b_by = {r["company_id"]: r for r in before.get("results", [])}
    lost = []
    for record in after.get("results", []):
        cid = record["company_id"]
        prior = b_by.get(cid, {})
        bd = _dig(prior, "evidence", "documents_retrieved", default=0)
        ad = _dig(record, "evidence", "documents_retrieved", default=0)
        bi = _dig(prior, "evidence", "independence",
                  "independent_evidence_count")
        ai = _dig(record, "evidence", "independence",
                  "independent_evidence_count")
        state = _dig(record, "evidence", "independence",
                     "corroboration_state", default="?")
        if ad < bd:
            lost.append((cid, bd, ad))
        bi_s = bi if isinstance(bi, int) else UNAVAILABLE
        ai_s = ai if isinstance(ai, int) else UNAVAILABLE
        print(f"{cid:<26}{f'{bd} → {ad}':>10}{f'{bi_s} → {ai_s}':>14}"
              f"{state:>26}")

    print("\ncompanies losing documents:", len(lost) or "0")
    for cid, bd, ad in lost:
        print(f"  {cid}: {bd} → {ad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

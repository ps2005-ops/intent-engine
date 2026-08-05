"""Bounded operator view of the evidence-translation stage.

WHY THIS IS NOT JUST `rows`
---------------------------
The research rows already carried `evidence_translated` and
`evidence_unclassifiable`, and the report serializer dropped them:
`report.py` writes `{k: v for k, v in research.items() if k != "rows"}`. That
was the right instinct badly aimed. A row carries a whole document's worth of
free text per company, and serialising 28 of them into every cycle JSON would
put raw page bodies in an operator artifact forever.

But the consequence was that a cycle translating 0 evidence out of 500
candidate sentences looked exactly like a cycle that found nothing to
translate — and those are opposite problems. One is a broken pipeline; the
other is a quiet week.

So the fix is aggregation, not exposure. The counts cross into the report; the
text never does. `assert_bounded` is the guard, and it is checked on the way
out rather than trusted at the call site.

NEVER FOUNDER-FACING
--------------------
This is operator telemetry. A founder reading a dossier does not benefit from
knowing that 92% of candidate sentences were dropped, and telling them would
be the engine talking about itself instead of about their market. Nothing here
is allowlisted in `strategic_export`, and a test drives that.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

REPORT_VERSION = "translation_observability.v1"

#: keys a per-company summary may carry. Counts and identifiers only.
_COMPANY_KEYS = ("company", "documents", "candidate_sentences",
                 "evidence_translated", "evidence_unclassifiable",
                 "furniture_rejected", "subject_mismatch")

#: the longest free-text value allowed anywhere in the payload. A company id
#: and a rejection reason fit; a sentence does not.
MAX_TEXT = 64

#: at most this many per-company rows. The universe is bounded, but a config
#: change should not be able to turn the report into a data dump.
MAX_COMPANIES = 60


class UnboundedTelemetry(RuntimeError):
    """The translation report tried to carry document text."""


def summarise(rows: Sequence[dict], stats: Any = None) -> dict:
    """Aggregate the sweep's translation behaviour into bounded counts."""
    per_company: List[dict] = []
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        per_company.append({
            "company": str(row.get("company", ""))[:MAX_TEXT],
            "documents": int(row.get("evidence", 0) or 0),
            "candidate_sentences": int(row.get("candidate_sentences", 0) or 0),
            "evidence_translated": int(row.get("evidence_translated", 0) or 0),
            "evidence_unclassifiable": int(
                row.get("evidence_unclassifiable", 0) or 0),
            "furniture_rejected": int(row.get("furniture_rejected", 0) or 0),
            "subject_mismatch": int(row.get("subject_mismatch", 0) or 0),
        })
    per_company.sort(key=lambda r: (-r["evidence_translated"], r["company"]))

    totals = stats.as_dict() if stats is not None else {}
    payload = {
        "contract": REPORT_VERSION,
        "companies_processed": len(per_company),
        "documents_considered": sum(r["documents"] for r in per_company),
        "candidate_sentences": totals.get(
            "candidate_sentences",
            sum(r["candidate_sentences"] for r in per_company)),
        "translated_evidence": totals.get(
            "translated", sum(r["evidence_translated"] for r in per_company)),
        "unclassifiable_candidates": totals.get(
            "unclassifiable",
            sum(r["evidence_unclassifiable"] for r in per_company)),
        "furniture_rejected": totals.get(
            "furniture_rejected",
            sum(r["furniture_rejected"] for r in per_company)),
        "duplicate_candidates": totals.get("duplicates", 0),
        "subject_mismatch": totals.get(
            "subject_mismatch", sum(r["subject_mismatch"]
                                    for r in per_company)),
        "classification_by_type": dict(totals.get("by_type", {})),
        "rejection_reasons": dict(totals.get("by_reason", {})),
        "per_company": per_company[:MAX_COMPANIES],
    }
    considered = payload["candidate_sentences"]
    payload["translation_rate"] = (
        round(payload["translated_evidence"] / float(considered), 4)
        if considered else 0.0)
    payload["companies_with_evidence"] = sum(
        1 for r in per_company if r["evidence_translated"])
    # THE LINE AN OPERATOR ACTUALLY READS. A rate of 0.0 over a nonzero
    # candidate count is a broken pipeline; a rate of 0.0 over zero candidates
    # is a retrieval problem; no candidates and no documents is a quiet day.
    # Three different faults, one number each, stated rather than inferred.
    payload["verdict"] = _verdict(payload)
    assert_bounded(payload)
    return payload


def _verdict(p: dict) -> str:
    if not p["documents_considered"]:
        return ("no document reached translation; the failure is upstream in "
                "retrieval, not in classification")
    if not p["candidate_sentences"]:
        return ("documents were retrieved but produced no candidate "
                "sentence; every sentence was page furniture or a fragment")
    if not p["translated_evidence"]:
        return (f"{p['candidate_sentences']} candidate sentence(s) reached "
                f"the classifier and NONE carried a commercial event; a 100% "
                f"translation drop is a defect until proven otherwise")
    return (f"{p['translated_evidence']} of {p['candidate_sentences']} "
            f"candidate sentence(s) carried a commercial event "
            f"({p['translation_rate']:.1%})")


def assert_bounded(payload: Any, path: str = "") -> None:
    """Refuse to emit anything that could be a document body."""
    if isinstance(payload, str):
        if len(payload) > MAX_TEXT and not path.endswith("verdict"):
            raise UnboundedTelemetry(
                f"{path or 'root'}: {len(payload)} characters of free text in "
                f"operator telemetry; aggregate it or drop it")
    elif isinstance(payload, dict):
        for key, value in payload.items():
            assert_bounded(value, f"{path}.{key}" if path else str(key))
    elif isinstance(payload, (list, tuple)):
        if len(payload) > MAX_COMPANIES:
            raise UnboundedTelemetry(
                f"{path}: {len(payload)} entries exceeds the bound")
        for i, item in enumerate(payload):
            assert_bounded(item, f"{path}[{i}]")


def render(payload: dict) -> List[str]:
    """The markdown block. Short by design: an operator scans this."""
    lines = ["## EVIDENCE TRANSLATION", "",
             payload.get("verdict", ""), "",
             f"- companies processed: {payload['companies_processed']} "
             f"({payload['companies_with_evidence']} produced evidence)",
             f"- documents considered: {payload['documents_considered']}",
             f"- candidate sentences: {payload['candidate_sentences']}",
             f"- translated evidence: {payload['translated_evidence']}",
             f"- furniture rejected: {payload['furniture_rejected']}",
             f"- unclassifiable: {payload['unclassifiable_candidates']}",
             f"- duplicates: {payload['duplicate_candidates']}",
             f"- subject not named in source: {payload['subject_mismatch']}"]
    by_type = payload.get("classification_by_type") or {}
    if by_type:
        lines += ["", "By event type: " + ", ".join(
            f"{k} {v}" for k, v in sorted(by_type.items()))]
    reasons = payload.get("rejection_reasons") or {}
    if reasons:
        top = sorted(reasons.items(), key=lambda kv: -kv[1])[:6]
        lines += ["", "Top rejection reasons: " + ", ".join(
            f"{k} {v}" for k, v in top)]
    return lines + [""]

"""Draft claim classification and deterministic validation (T017).

Validation is not approval. A draft may be VALID FOR REVIEW (a human may
look at it) while remaining INVALID FOR HANDOFF (it may not be queued for
publication). Warnings never become approvals.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from intent_engine.marketing.records import (
    CLAIM_DERIVED_METRIC, CLAIM_DESCRIPTIVE, CLAIM_FORWARD_LOOKING,
    CLAIM_PERFORMANCE, CLAIM_TESTIMONIAL, CLAIM_UNCITED_OPINION,
    CLAIMS_REQUIRING_REVIEW, claim_identity, scan_banned_language,
)

VALIDATOR_VERSION = "draft_validator.v1"

_PERFORMANCE_MARKERS = ("accuracy", "accurate", "hit rate", "win rate",
                        "track record", "success rate", "well calibrated",
                        "outperform", "beats the market", "roi")
_FORWARD_MARKERS = ("will ", "going to ", "expect to ", "predicts",
                    "forecast", "guaranteed")
_METRIC_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s?%|\b\d{2,}\b")


def classify_claim(sentence: str, *, has_quote: bool = False) -> str:
    lowered = sentence.lower()
    if has_quote:
        return CLAIM_TESTIMONIAL
    if any(m in lowered for m in _PERFORMANCE_MARKERS):
        return CLAIM_PERFORMANCE
    if any(m in lowered for m in _FORWARD_MARKERS):
        return CLAIM_FORWARD_LOOKING
    if _METRIC_PATTERN.search(sentence):
        return CLAIM_DERIVED_METRIC
    return CLAIM_DESCRIPTIVE


def detect_claims(body: str, quotes=None) -> list:
    """Split into sentences and classify each. Deterministic and ordered."""
    quotes = list(quotes or [])
    claims = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", body or ""):
        sentence = raw.strip()
        if not sentence:
            continue
        has_quote = any(q and q in sentence for q in quotes)
        claim_class = classify_claim(sentence, has_quote=has_quote)
        claims.append({"claim_id": claim_identity(sentence),
                       "text": sentence, "claim_class": claim_class,
                       "requires_review": claim_class in CLAIMS_REQUIRING_REVIEW})
    return claims


@dataclass(frozen=True)
class DraftValidationResult:
    valid_for_review: bool
    valid_for_handoff: bool
    blocking_issues: tuple = ()
    warnings: tuple = ()
    claim_references: tuple = ()
    quote_references: tuple = ()
    evidence_references: tuple = ()
    validator_version: str = VALIDATOR_VERSION

    def as_payload(self) -> dict:
        return asdict(self)


def validate_draft(body: str, *, quotes=None, evidence_snapshots=None,
                   knowledge_service=None, approved_claim_ids=None
                   ) -> DraftValidationResult:
    """Deterministic wall pass. `approved_claim_ids` comes from the EXISTING
    company-event claim gate (human `claim.approved` facts) — this module
    never approves anything itself."""
    quotes = list(quotes or [])
    evidence_snapshots = list(evidence_snapshots or [])
    approved = set(approved_claim_ids or [])
    blocking, warnings = [], []

    claims = detect_claims(body, quotes=[q["quote_text"] for q in quotes])
    for claim in claims:
        if claim["requires_review"] and claim["claim_id"] not in approved:
            blocking.append(
                f"CLAIM REVIEW REQUIRED ({claim['claim_class']}): "
                f"{claim['text'][:80]!r}")

    banned = scan_banned_language(body)
    if banned:
        blocking.append(f"unsupported marketing language: {sorted(set(banned))}")

    # Quotes: consent is checked against the T016 gate, never inferred here.
    quote_refs = []
    for q in quotes:
        if knowledge_service is None:
            blocking.append("QUOTE CONSENT REQUIRED: no knowledge service "
                            "available to verify consent")
            continue
        verdict = knowledge_service.can_publish_quote(
            q["feedback_id"], q["quote_text"], q.get("intended_use", "public"))
        quote_refs.append({**q, "consent_state": verdict["consent_state"],
                           "allowed": verdict["allowed"]})
        if not verdict["allowed"]:
            blocking.append(f"QUOTE CONSENT REQUIRED: {verdict['reason']}")
        elif q["quote_text"] not in (body or ""):
            blocking.append("approved quote text does not appear verbatim in "
                            "the draft (paraphrase is not covered)")

    # Knowledge evidence must still be active at draft time.
    for snap in evidence_snapshots:
        if snap.get("evidence_type") == "knowledge_item" \
                and knowledge_service is not None:
            item = knowledge_service.get_knowledge_item(snap["source_id"])
            if item["status"] == "retracted":
                blocking.append(
                    f"cited knowledge {snap['source_id']} is retracted")

    if not evidence_snapshots:
        warnings.append("no evidence attached — descriptive copy only")

    return DraftValidationResult(
        valid_for_review=True,          # a human may always look at a draft
        valid_for_handoff=not blocking,
        blocking_issues=tuple(blocking),
        warnings=tuple(warnings),
        claim_references=tuple(claims),
        quote_references=tuple(quote_refs),
        evidence_references=tuple(
            s.get("source_id") for s in evidence_snapshots),
    )

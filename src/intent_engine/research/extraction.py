"""Model-assisted extraction and the anti-hallucination wall (T019).

This module is the ONLY place a model touches research, and it is
deliberately the smallest possible surface. The wall, restated because it
is the single most important rule in the subsystem:

    A MODEL MAY NEVER EMIT A SOURCE, URL, CITATION, AUTHOR, OR DATE.

Those come only from the registered source. A model proposes candidate
claims; deterministic code decides which become evidence. A candidate
whose text is not locatable in its source is rejected. An extraction
failure is a TYPED FACT, never an empty result that reads as "no
evidence found".
"""
from __future__ import annotations

import re

from intent_engine.research.records import (
    EVIDENCE_CLASSES, ResearchError, scan_banned_language,
)

EXTRACTION_PROMPT_VERSION = "research_extraction.v1"
MAX_CANDIDATES_PER_SOURCE = 12
MAX_CLAIM_CHARS = 400

EXTRACTION_SYSTEM_PROMPT = """You are extracting candidate factual claims from \
one supplied document.

Rules:
- Extract only claims that appear in the supplied text. Do not add context \
from memory.
- Never invent a URL, citation, author, publication, or date. You are not \
permitted to output any of those fields at all.
- Prefer the document's own wording; a claim must be locatable in the text.
- Classify each claim as one of: observation, mechanism, opinion, prediction, \
recommendation, methodology, unknown.
- If the document supports no checkable claim, return an empty list. An empty \
list is a valid, useful answer."""

# The model's schema deliberately has NO field for a URL, author, date, or
# citation — it cannot emit one even if it tries (structurally, not by
# instruction alone).
EXTRACTION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "maxItems": MAX_CANDIDATES_PER_SOURCE,
            "items": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string",
                                   "maxLength": MAX_CLAIM_CHARS},
                    "evidence_class": {"type": "string",
                                       "enum": sorted(EVIDENCE_CLASSES)},
                    "quote_span": {"type": "string", "maxLength": 600},
                },
                "required": ["claim_text", "evidence_class"],
            },
        },
    },
    "required": ["candidates"],
}

# Fields a model is never allowed to contribute. Presence of any of these
# in a candidate is treated as a hallucination attempt.
FORBIDDEN_CANDIDATE_FIELDS = {"url", "locator", "source", "source_id",
                              "citation", "author", "publisher", "doi",
                              "published_date", "date", "retrieved_at"}
_URL_RE = re.compile(r"https?://|www\.|doi\.org|10\.\d{4,9}/", re.I)


class ExtractionRejected(ResearchError):
    """A model candidate violated the extraction wall."""


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def validate_candidate(candidate: dict, source_text: str,
                       source: dict) -> dict:
    """Deterministic acceptance. Raises ExtractionRejected with the exact
    reason, which the caller records as a typed fact."""
    if not isinstance(candidate, dict):
        raise ExtractionRejected("candidate is not an object")

    leaked = sorted(set(candidate) & FORBIDDEN_CANDIDATE_FIELDS)
    if leaked:
        raise ExtractionRejected(
            f"model emitted forbidden provenance fields {leaked} — sources, "
            "citations, authors and dates come only from the registered "
            "source, never from a model")

    claim = candidate.get("claim_text", "")
    if not claim.strip():
        raise ExtractionRejected("empty claim text")
    if len(claim) > MAX_CLAIM_CHARS:
        raise ExtractionRejected("claim exceeds the bounded length")
    if _URL_RE.search(claim):
        raise ExtractionRejected(
            "claim text contains a URL or DOI — a model-authored reference "
            "may never enter the evidence store")

    klass = candidate.get("evidence_class")
    if klass not in EVIDENCE_CLASSES:
        raise ExtractionRejected(f"unknown evidence_class: {klass!r}")

    overclaims = scan_banned_language(claim)
    if overclaims:
        raise ExtractionRejected(
            f"claim language overclaims {overclaims}; restate what the "
            "source says")

    # Locatability: the claim, or its quoted span, must appear in the source.
    haystack = _normalize(source_text)
    span = candidate.get("quote_span") or claim
    if _normalize(span) not in haystack:
        raise ExtractionRejected(
            "claim is not locatable in the supplied source text — an "
            "unlocatable claim is a paraphrase of nothing")

    return {"claim_text": claim.strip(), "evidence_class": klass,
            "locator_in_source": candidate.get("quote_span", "")[:600],
            "extraction_method": "model_assisted",
            "source_id": source["source_id"]}


def extract_candidates(client, source: dict, source_text: str, *,
                       model_version: str,
                       prompt_version: str = EXTRACTION_PROMPT_VERSION) -> dict:
    """Run ONE bounded, isolated model call and validate every candidate.

    Returns {"accepted": [...], "rejected": [{candidate, reason}], "usage":
    {...}}. A transport/model failure raises so the caller can record a
    typed `research.extraction_failed` fact — an exception is never
    converted into "no evidence found"."""
    result = client.call_tool(
        system=EXTRACTION_SYSTEM_PROMPT,
        user_message=("Document to extract from:\n\n" + source_text),
        tool_name="record_candidate_claims",
        tool_description="Record candidate factual claims found in the text.",
        input_schema=EXTRACTION_TOOL_SCHEMA,
        max_tokens=1200)

    candidates = (result or {}).get("candidates", [])
    if not isinstance(candidates, list):
        raise ExtractionRejected("model returned a malformed candidate list")

    accepted, rejected = [], []
    for candidate in candidates[:MAX_CANDIDATES_PER_SOURCE]:
        try:
            accepted.append(validate_candidate(candidate, source_text, source))
        except ExtractionRejected as exc:
            rejected.append({"candidate": _safe_echo(candidate),
                             "reason": str(exc)})
    return {"accepted": accepted, "rejected": rejected,
            "provenance": {"prompt_version": prompt_version,
                           "model_version": model_version,
                           "extraction_module": "research.extraction"},
            "usage": {"candidates_returned": len(candidates),
                      "accepted": len(accepted), "rejected": len(rejected)}}


def _safe_echo(candidate) -> dict:
    """Echo a rejected candidate WITHOUT its forbidden fields, so a
    hallucinated URL never reaches storage even inside a rejection row."""
    if not isinstance(candidate, dict):
        return {"claim_text": "(malformed candidate)"}
    return {"claim_text": str(candidate.get("claim_text", ""))[:200],
            "evidence_class": str(candidate.get("evidence_class", ""))[:40]}

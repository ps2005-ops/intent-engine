"""Approved-input ingestion (T023.5) — no autonomous crawling.

T023.5 uses ONLY one of: founder-pasted/uploaded approved source material,
or a deterministic demo fixture. It does NOT crawl. Live company-website
retrieval is a recorded dependency gap (`docs/T0235_DEPENDENCY_GAPS.md`,
Gap 1); no external network call is made in this build.

Every ingested source records: id, type, origin, received time, content
hash, company identity, consent/run id, parser version, freshness — so a
source failure is a recorded fact, never absence of the real-world fact
("no supported review source was retrieved", not "the company has no
reviews").
"""
from __future__ import annotations

import hashlib

from intent_engine.founder_intelligence.records import (
    FounderIntelligenceError, assert_no_secret, freshness_of, now_iso,
    validate_public_url,
)

INGESTION_VERSION = "fi_ingestion.v1"
PARSER_VERSION = "fi_parser.v1"

SOURCE_PASTED = "founder_pasted"
SOURCE_UPLOADED = "founder_uploaded"
SOURCE_FIXTURE = "demo_fixture"
SOURCE_TYPES = {SOURCE_PASTED, SOURCE_UPLOADED, SOURCE_FIXTURE}


def _content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode()).hexdigest()[:32]


def ingest_approved_text(*, run_id: str, company_domain: str, origin: str,
                         source_type: str, text: str, as_of: str,
                         observed_at: str = None) -> dict:
    """Record ONE approved text source. Refuses secrets before storage;
    url-checks a URL origin. Fetches nothing."""
    if source_type not in SOURCE_TYPES:
        raise FounderIntelligenceError(f"unknown source type: {source_type!r}")
    assert_no_secret(text, where="ingested source content")
    assert_no_secret(origin, where="ingested source origin")
    if origin.lower().startswith(("http://", "https://")):
        validate_public_url(origin)         # SSRF wall even for recorded origin
    source_id = _content_hash(f"{run_id}|{origin}|{text[:200]}")
    return {
        "source_id": source_id,
        "source_type": source_type,
        "origin": origin,
        "received_at": now_iso(),
        "content_hash": _content_hash(text),
        "company_domain": company_domain,
        "run_id": run_id,
        "parser_version": PARSER_VERSION,
        "ingestion_version": INGESTION_VERSION,
        "observed_at": observed_at,
        "freshness_status": freshness_of(observed_at, as_of),
        "char_count": len(text or ""),
    }


def retrieval_gap(origin: str, kind: str) -> dict:
    """An honest 'source not retrieved' record — never 'the fact is
    absent'. E.g. a review source that could not be fetched."""
    return {
        "origin": origin,
        "kind": kind,
        "retrieved": False,
        "reason": f"no supported {kind} source was retrieved (live "
                  "ingestion is a recorded dependency gap, Gap 1)",
        "note": "a source failure is not the absence of the real-world fact",
    }

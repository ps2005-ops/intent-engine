"""V1.1 company-ingestion records — candidates, approvals, retrievals,
failures, documents. Append-only, run- and company-scoped, no secrets.

The ingestion layer creates clean, traceable source material. It never
creates business conclusions — that stays with claims.py composition
into the existing Founder Intelligence contract.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.core.decision_ids import is_ulid, new_ulid
from intent_engine.founder_intelligence.records import assert_no_secret

INGESTION_SCHEMA_VERSION = 1
PARSER_VERSION = "ingest-parse.v1"

SOURCE_TYPES = (
    "homepage", "product", "pricing", "about", "customers", "blog",
    "careers", "external_approved", "pasted", "uploaded",
)

DISCOVERY_METHODS = ("entered", "homepage_link", "known_path",
                     "user_external", "user_pasted")

RUN_STATES = (
    "VALIDATING_COMPANY", "DISCOVERING_SOURCES", "AWAITING_SOURCE_APPROVAL",
    "FETCHING_APPROVED_SOURCES", "PARSING_SOURCES",
    "BUILDING_SOURCE_ARTIFACTS", "ASSEMBLING_COMPANY_UNDERSTANDING",
    "ASSEMBLING_REPORT", "COMPLETE", "PARTIAL", "FAILED", "REJECTED",
)

RETRIEVAL_STATUSES = ("OK", "FAILED", "UNAVAILABLE", "SKIPPED")

FAILURE_TYPES = ("timeout", "connection", "http_status", "too_large",
                 "bad_mime", "unsafe_redirect", "blocked", "parse_error")

PRIVACY_CLASSES = ("public", "user_public_excerpt", "user_internal")

# Bounds (§41) — explicit and enforced.
MAX_CANDIDATES_SHOWN = 20
MAX_HOMEPAGE_LINKS = 20
MAX_KNOWN_PATHS = 10
MAX_APPROVED_SOURCES = 10
MAX_RESPONSE_BYTES = 2_000_000
MAX_TOTAL_BYTES_PER_RUN = 15_000_000
MAX_REDIRECTS = 5
CONNECT_TIMEOUT_S = 8
READ_TIMEOUT_S = 12
USER_AGENT = ("FounderIntelligenceBot/1.1 "
              "(outside-in company analysis; approved-source retrieval)")
ACCEPTED_MIME_PREFIXES = ("text/html", "application/xhtml",
                          "text/plain", "text/markdown")

INGESTION_EVENTS = frozenset({
    "ci.run_created", "ci.run_transitioned",
    "ci.candidate_discovered", "ci.approval_recorded",
    "ci.source_retrieved", "ci.retrieval_failed",
    "ci.pasted_evidence_added", "ci.claims_built",
})


class IngestionError(ValueError):
    """A company-ingestion record or operation violated its contract."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IngestionEvent:
    event_type: str
    actor_type: str
    actor_id: str
    ci_event_id: str = field(default_factory=new_ulid)
    run_id: str | None = None
    company_domain: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    idempotency_key: str | None = None
    schema_version: int = INGESTION_SCHEMA_VERSION
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in INGESTION_EVENTS:
            raise IngestionError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.ci_event_id):
            raise IngestionError("ci_event_id must be a ULID")
        if self.actor_type not in ("human", "system"):
            raise IngestionError(f"unknown actor_type: {self.actor_type!r}")
        for name in ("actor_id", "occurred_at", "recorded_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise IngestionError(f"{name} must be non-empty")
        if not isinstance(self.payload, dict):
            raise IngestionError("payload must be a dict")
        try:
            if json.loads(json.dumps(self.payload)) != self.payload:
                raise IngestionError("payload not round-trip safe")
        except (TypeError, ValueError) as exc:
            raise IngestionError(f"payload not JSON-safe: {exc}") from exc
        flat = json.dumps(self.payload).lower()
        for marker in ("authorization:", "set-cookie", "x-api-key"):
            if marker in flat:
                raise IngestionError(
                    "raw credentials / auth headers must never be persisted")

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "IngestionEvent":
        data = json.loads(line)
        version = data.get("schema_version")
        if isinstance(version, int) and version > INGESTION_SCHEMA_VERSION:
            raise IngestionError(
                f"row {data.get('ci_event_id')} is schema v{version} > "
                f"supported v{INGESTION_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("ci_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)


def candidate_record(*, candidate_id, company_id, url, canonical_url,
                     source_type, title, discovery_method, same_domain,
                     availability="PROPOSED") -> dict:
    if source_type not in SOURCE_TYPES:
        raise IngestionError(f"unknown source_type {source_type!r}")
    if discovery_method not in DISCOVERY_METHODS:
        raise IngestionError(f"unknown discovery_method {discovery_method!r}")
    return {"candidate_id": candidate_id, "company_id": company_id,
            "url": url, "canonical_url": canonical_url,
            "source_type": source_type, "title": title,
            "discovery_method": discovery_method,
            "same_domain": bool(same_domain),
            "proposed_at": now_iso(), "availability": availability}


def retrieved_record(*, source_id, run_id, company_id, original_url,
                     final_url, source_type, status_code, mime_type,
                     content_hash, byte_count, title, text_content,
                     meta_description="", freshness="CURRENT",
                     retrieval_status="OK", privacy="public",
                     origin_note="") -> dict:
    assert_no_secret(text_content[:20000], where="retrieved source text")
    if privacy not in PRIVACY_CLASSES:
        raise IngestionError(f"unknown privacy class {privacy!r}")
    if retrieval_status not in RETRIEVAL_STATUSES:
        raise IngestionError(f"unknown retrieval_status {retrieval_status!r}")
    return {"source_id": source_id, "run_id": run_id,
            "company_id": company_id, "original_url": original_url,
            "final_url": final_url, "source_type": source_type,
            "retrieved_at": now_iso(), "status_code": status_code,
            "mime_type": mime_type, "content_hash": content_hash,
            "byte_count": byte_count, "title": title,
            "text_content": text_content,
            "meta_description": meta_description,
            "parser_version": PARSER_VERSION,
            "freshness": freshness, "retrieval_status": retrieval_status,
            "privacy": privacy, "origin_note": origin_note}


def failure_record(*, failure_id, run_id, candidate_id, failure_type,
                   safe_message, retryable) -> dict:
    if failure_type not in FAILURE_TYPES:
        raise IngestionError(f"unknown failure_type {failure_type!r}")
    return {"failure_id": failure_id, "run_id": run_id,
            "candidate_id": candidate_id, "failure_type": failure_type,
            "safe_message": safe_message[:500], "occurred_at": now_iso(),
            "retryable": bool(retryable)}

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
                     "user_external", "user_pasted", "external_proposed")

# Strategic source classes (mirrors strategic_intelligence.records.SOURCE_CLASSES
# minus the non-ingestible members). Every candidate and retrieved document
# carries one so the strategic layer can reason across evidence classes rather
# than treating everything as a company-owned page.
SOURCE_CLASSES = (
    "company_owned", "executive_statement", "investor_material",
    "customer_voice", "competitor", "independent_reporting",
)
# classes that represent a vantage point OUTSIDE the company's own publishing —
# a COMPLETE strategic report needs at least one of these (cross-source).
INDEPENDENT_CLASSES = ("independent_reporting", "customer_voice", "competitor")

RUN_STATES = (
    "VALIDATING_COMPANY", "DISCOVERING_SOURCES", "AWAITING_SOURCE_APPROVAL",
    "FETCHING_APPROVED_SOURCES", "PARSING_SOURCES",
    "BUILDING_SOURCE_ARTIFACTS", "ASSEMBLING_COMPANY_UNDERSTANDING",
    "ASSEMBLING_REPORT", "COMPLETE", "PARTIAL", "FAILED", "REJECTED",
)

RETRIEVAL_STATUSES = ("OK", "FAILED", "UNAVAILABLE", "SKIPPED")

FAILURE_TYPES = ("timeout", "connection", "http_status", "too_large",
                 "bad_mime", "unsafe_redirect", "blocked", "parse_error",
                 "javascript_only",
                 # The source was never dialled because the analysis ran out
                 # of its interactive budget first. Emphatically NOT a
                 # finding about the company or the host: it is a fact about
                 # how long we were willing to wait, and it is retryable.
                 "deadline_exceeded",
                 # The page WAS retrieved, but its text tripped the credential
                 # scanner and was refused before storage. Reporting that as
                 # "blocked" told the reader the address failed a safety check,
                 # which is a different and more alarming thing than "we read
                 # this page and chose not to keep it".
                 "content_rejected",
                 # The host had ALREADY refused to answer earlier in this run,
                 # so this candidate was never dialled. Distinct from
                 # "timeout" on purpose: a timeout is a thing that happened to
                 # this URL, this is a decision we made about the host, and
                 # the reader must be able to tell "we waited and nobody
                 # answered" from "we stopped waiting". Retryable, and never a
                 # finding about the company.
                 "host_unreachable")

PRIVACY_CLASSES = ("public", "user_public_excerpt", "user_internal")

# Bounds (§41) — explicit and enforced.
MAX_CANDIDATES_SHOWN = 32
MAX_HOMEPAGE_LINKS = 20
# Known-path probes must cover the evidence families (identity, product, docs,
# customers, pricing, strategy, investor, talent). A JavaScript-rendered site
# exposes no usable homepage links, so these probes are the ONLY route to
# company evidence — capping them at 10 starved the report of coverage.
MAX_KNOWN_PATHS = 28
# Eight evidence families take eight of these on the first pass, so a cap of 10
# left the product family a single slot — one page to describe a company with
# three named platforms AND two named market segments. Fourteen lets the
# highest-value families (product, customers, investor) take their quota
# without starving the rest, and stays far inside MAX_TOTAL_BYTES_PER_RUN.
MAX_APPROVED_SOURCES = 14
#: The budget for ONE untrusted web response. SEC filings are fetched against
#: `edgar.MAX_FILING_BYTES` instead — see the reasoning there.
MAX_RESPONSE_BYTES = 2_000_000
#: The budget for a whole run.
#:
#: This had to move with the filing budget, not after it. At 15MB a single
#: JPMorgan 10-K (12.9MB measured 2026-08-05) would consume 86% of the run and
#: every remaining source would fail with "run byte budget exhausted" — the
#: analysis would trade nine ordinary pages for one filing and come out worse
#: than before. 48MB carries the realistic worst case: three statutory filings
#: (annual, quarterly, current — the families are served round-robin, so at
#: most a few land) plus the ordinary pages, none of which can exceed 2MB.
#:
#: The cost is bounded and was measured before raising it: JPMorgan's 12.9MB
#: 10-K downloads in ~1s and parses in ~2s.
MAX_TOTAL_BYTES_PER_RUN = 48_000_000
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
    # WHAT THE RUN DID NOT HAVE TO DO. A warm run skips discovery entirely,
    # which is invisible in every other event: the candidates it stores look
    # exactly like a cold run's, because they are written through the same
    # path on purpose. Without this row a reader cannot tell a reused source
    # list from a rediscovered one, and the whole point of the snapshot is
    # the difference between them.
    "ci.snapshot_reused",
    # WHAT CHANGED AFTER THE READER ALREADY HAD AN ANSWER. CORE stops
    # blocking once the readiness contract is met and the remaining approved
    # sources are acquired afterwards; when that wider evidence moves the
    # thesis, the decision implications or the result state, the change is
    # recorded here and shown as a CHANGE. Rewriting the page under a reader
    # who has acted on it is worse than making them wait.
    #
    # REGISTERED WITH THE HANDLER, NOT AFTER IT. The last new event type in
    # this file was added to the producer and not to this set: `_append`
    # raised, a broad `except` swallowed it, and every "warm" run silently
    # performed a full cold discovery while reporting nothing wrong.
    "ci.analysis_updated",
    # report-quality diagnostics (operator observability)
    "ci.quality_assessed",
    # Operator-only: did the RICH path actually land? "The reasoning backend
    # is configured" and "a grounded analysis was accepted" proved to be very
    # different things, and nothing recorded the difference.
    "ci.reasoning_assessed",
    # WHO the run is about, asserted before synthesis and independently of
    # whatever the run manages to retrieve.
    "ci.entity_identified",
    # WHOSE DOCUMENTS THE RUN DECIDED IT WAS READING, recorded at the moment
    # it decided. Four deploys were spent on a defect whose whole difficulty
    # was that `subject_cik` was unobservable after the fact: a run that
    # produced a wrong attribution could not be asked whether it had had a
    # CIK at all, and the run that would have settled it was gone by the time
    # the question was framed. An append-only event outlives the run, the
    # process and the deploy, which a live route does not.
    "ci.ownership_resolved",
    # WHEN each lifecycle boundary was crossed, recorded where it happened.
    # The interactive SLO is written against CORE_READY, and CORE_READY was
    # being measured by watching a progress page stop redirecting -- a UI
    # side effect, in a harness, over a network, with a 4s poll granularity
    # that alone is 13% of a 30s budget. An append-only marker outlives the
    # process, is exact, and cannot be changed by a template edit.
    "ci.lifecycle_marked",
    # WHERE THE TIME WENT, recorded per stage rather than argued from
    # end-to-end ratios. Two hypotheses about the deployed latency were
    # reasoned from totals and both were wrong; an aggregate cannot say which
    # stage owns the seconds.
    "ci.trace_recorded",
})

#: The boundaries worth timing. Deliberately short: a marker nobody divides
#: by is a row in a ledger that has to be maintained forever.
LIFECYCLE_MARKERS = ("accepted", "core_ready", "deep_started", "deep_ready",
                     "terminal")


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
                     availability="PROPOSED", source_class="company_owned",
                     why_relevant="") -> dict:
    if source_type not in SOURCE_TYPES:
        raise IngestionError(f"unknown source_type {source_type!r}")
    if discovery_method not in DISCOVERY_METHODS:
        raise IngestionError(f"unknown discovery_method {discovery_method!r}")
    if source_class not in SOURCE_CLASSES:
        raise IngestionError(f"unknown source_class {source_class!r}")
    return {"candidate_id": candidate_id, "company_id": company_id,
            "url": url, "canonical_url": canonical_url,
            "source_type": source_type, "title": title,
            "discovery_method": discovery_method,
            "same_domain": bool(same_domain), "source_class": source_class,
            "why_relevant": why_relevant,
            "proposed_at": now_iso(), "availability": availability}


def retrieved_record(*, source_id, run_id, company_id, original_url,
                     final_url, source_type, status_code, mime_type,
                     content_hash, byte_count, title, text_content,
                     meta_description="", freshness="CURRENT",
                     retrieval_status="OK", privacy="public",
                     origin_note="", source_class="company_owned",
                     extraction_mode="body", blocks_found=0,
                     filing=None) -> dict:
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
            "privacy": privacy, "origin_note": origin_note,
            "source_class": source_class,
            # WHERE the text came from. A document recovered only from
            # og:description is not the same evidence as a document whose body
            # was read, and every gate downstream was blind to the difference.
            "extraction_mode": extraction_mode, "blocks_found": blocks_found,
            # WHAT WAS READ, for a regulatory filing: the quality verdict, the
            # sections located, and the span each retained excerpt was cut
            # from. Absent (None) for every other kind of document, so no
            # existing consumer changes shape.
            #
            # This exists so nothing downstream has to re-derive from one
            # front-truncated blob what the parser already established. "We
            # retrieved the 10-K" and "we can read the 10-K" were the same
            # fact to every gate, which is how a cover page travelled as an
            # annual report.
            **({"filing": filing} if filing else {})}


def failure_record(*, failure_id, run_id, candidate_id, failure_type,
                   safe_message, retryable) -> dict:
    if failure_type not in FAILURE_TYPES:
        raise IngestionError(f"unknown failure_type {failure_type!r}")
    return {"failure_id": failure_id, "run_id": run_id,
            "candidate_id": candidate_id, "failure_type": failure_type,
            "safe_message": safe_message[:500], "occurred_at": now_iso(),
            "retryable": bool(retryable)}

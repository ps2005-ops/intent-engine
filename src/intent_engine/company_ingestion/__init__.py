"""V1.1 — Approved Live Company Analysis: the smallest safe, evidence-
backed path from a real public domain to a useful outside-in report.
Every source is explicitly approved before retrieval; every claim
resolves to real source material; no synthetic evidence may enter a
real run."""
from intent_engine.company_ingestion.claims import (
    REAL_SUBSYSTEM, SYNTHETIC_SUBSYSTEM, assert_quotes_exist,
    assert_real_claims, build_claims, executive_overview, real_ref,
)
from intent_engine.company_ingestion.discovery import (
    KNOWN_PATHS, classify_path, discover_candidates,
)
from intent_engine.company_ingestion.fetch import FetchResult, safe_fetch
from intent_engine.company_ingestion.parsing import parse_html
from intent_engine.company_ingestion.pasted import pasted_source
from intent_engine.company_ingestion.records import (
    IngestionError, IngestionEvent, MAX_APPROVED_SOURCES,
    MAX_CANDIDATES_SHOWN, MAX_REDIRECTS, MAX_RESPONSE_BYTES,
    PARSER_VERSION, RUN_STATES, SOURCE_TYPES, USER_AGENT,
)
from intent_engine.company_ingestion.service import (
    CONSENT_VERSION, CompanyIngestionService,
)
from intent_engine.company_ingestion.store import (
    DEFAULT_CI_PATH, IngestionCorruptLogError, IngestionStore,
)
from intent_engine.company_ingestion.validation import (
    redirect_allowed, registrable, resolve_public_addresses, same_domain,
    validate_candidate_url,
)

__all__ = [
    "CONSENT_VERSION", "CompanyIngestionService", "DEFAULT_CI_PATH",
    "FetchResult", "IngestionCorruptLogError", "IngestionError",
    "IngestionEvent", "IngestionStore", "KNOWN_PATHS",
    "MAX_APPROVED_SOURCES", "MAX_CANDIDATES_SHOWN", "MAX_REDIRECTS",
    "MAX_RESPONSE_BYTES", "PARSER_VERSION", "REAL_SUBSYSTEM", "RUN_STATES",
    "SOURCE_TYPES", "SYNTHETIC_SUBSYSTEM", "USER_AGENT",
    "assert_quotes_exist", "assert_real_claims", "build_claims",
    "classify_path", "discover_candidates", "executive_overview",
    "parse_html", "pasted_source", "real_ref", "redirect_allowed",
    "registrable", "resolve_public_addresses", "safe_fetch", "same_domain",
    "validate_candidate_url",
]

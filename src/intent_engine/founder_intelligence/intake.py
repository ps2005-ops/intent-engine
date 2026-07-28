"""Intake (T023.5) — validates founder input, records consent.

The public surface must never become a secret-ingestion vector, so intake
runs the SSRF URL wall and the secret wall before anything is recorded. It
records what the founder approved for analysis; it fetches nothing and
accepts no credentials in free text.
"""
from __future__ import annotations

from intent_engine.founder_intelligence.records import (
    CONSENT_VERSION, CompanyInput, FounderIntelligenceError, assert_no_secret,
    validate_public_url,
)

INTAKE_VERSION = "fi_intake.v1"


def validate_input(*, company_name: str, website: str, requester_role=None,
                   business_question=None, approved_inputs=(),
                   consent_version=CONSENT_VERSION) -> CompanyInput:
    """Build and validate a CompanyInput. Raises before any storage on an
    unsafe URL or a secret in free text."""
    company_input = CompanyInput(
        company_name=company_name, website=website,
        requester_role=requester_role, business_question=business_question,
        # Sorted deliberately. The approved source SET defines the analysis;
        # the order discovery happened to return them in is incidental. Two
        # analyses that retrieved the same sources in a different order were
        # otherwise recorded with different content under the same identity,
        # which raised an idempotency conflict and surfaced to the user as
        # HTTP 500 — the failure the external tester hit on Palantir.
        approved_inputs=tuple(sorted(approved_inputs)),
        consent_version=consent_version)
    company_input.validate()
    # each approved input origin is also url-checked (no internal targets)
    for origin in approved_inputs:
        if isinstance(origin, str) and origin.lower().startswith(("http://",
                                                                  "https://")):
            validate_public_url(origin)
        if isinstance(origin, str):
            assert_no_secret(origin, where="approved input origin")
    return company_input


CONSENT_STATEMENT = (
    "I approve analysis of the company information and supported public "
    "sources shown here. I understand the product analyzes founder-approved "
    "company information and supported public signals, does not inspect "
    "internal systems unless explicitly connected, and is not legal, "
    "financial, or investment advice.")


def consent_record(company_input: CompanyInput) -> dict:
    return {"consent_version": company_input.consent_version,
            "consent_statement": CONSENT_STATEMENT,
            "approved_inputs": list(company_input.approved_inputs),
            "note": "founder-approved analysis of company information and "
                    "supported public signals only"}

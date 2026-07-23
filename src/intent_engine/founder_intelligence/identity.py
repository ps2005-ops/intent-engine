"""Company identity resolution (T023.5) — deterministic, evidence-backed.

Normalizes a company name + website into a `CompanyIdentity` with a
canonical domain and an identity confidence. It does NOT attempt broad
entity resolution or fetch anything live: confidence is derived from the
consistency of the founder-supplied name/website and whatever approved
identity evidence exists. A website that resolves (by the run's approved
inputs) to a different organization is flagged as a MISMATCH rather than
merged — the product never silently merges two companies.
"""
from __future__ import annotations

import re

from intent_engine.founder_intelligence.records import (
    IDENTITY_HIGH, IDENTITY_LOW, IDENTITY_MISMATCH, IDENTITY_MODERATE,
    IDENTITY_UNRESOLVED, CompanyIdentity, SourceRef, canonical_domain,
    now_iso,
)

IDENTITY_VERSION = "fi_identity.v1"

_TOKEN = re.compile(r"[a-z0-9]+")


def normalize_name(name: str) -> str:
    return " ".join((name or "").lower().split())


def _name_tokens(text: str) -> set:
    stop = {"inc", "llc", "ltd", "co", "corp", "company", "the", "io", "ai",
            "app", "labs", "hq"}
    return {t for t in _TOKEN.findall((text or "").lower()) if t not in stop}


def resolve_identity(*, company_name: str, website: str, as_of: str,
                     resolved_domain: str | None = None,
                     approved_identity_evidence=None) -> CompanyIdentity:
    """Deterministic identity + confidence.

    `resolved_domain` is what the run's APPROVED inputs say the site
    actually resolves to (e.g. a founder-confirmed redirect target). If it
    disagrees with the entered website's canonical domain, that is a
    MISMATCH — stop and confirm, never merge.
    """
    domain = canonical_domain(website)
    normalized = normalize_name(company_name)

    if resolved_domain and canonical_domain(resolved_domain) != domain:
        return CompanyIdentity(
            normalized_name=normalized, canonical_domain=domain,
            identity_confidence=IDENTITY_MISMATCH,
            identity_evidence=tuple(approved_identity_evidence or ()))

    # confidence from name/domain agreement + whether identity evidence exists
    name_tokens = _name_tokens(company_name)
    domain_tokens = _name_tokens(domain.split(".")[0] if domain else "")
    overlap = name_tokens & domain_tokens
    has_evidence = bool(approved_identity_evidence)

    if not domain:
        confidence = IDENTITY_UNRESOLVED
    elif overlap and has_evidence:
        confidence = IDENTITY_HIGH
    elif overlap or has_evidence:
        confidence = IDENTITY_MODERATE
    else:
        confidence = IDENTITY_LOW

    evidence = tuple(approved_identity_evidence or ())
    if not evidence and domain:
        # the entered website is itself a (weak) identity reference
        evidence = (SourceRef(subsystem="founder_input",
                              artifact_type="entered_website",
                              artifact_id=domain,
                              replay_id=f"fi:identity:{domain}:{as_of}",
                              as_of=as_of),)

    identity = CompanyIdentity(normalized_name=normalized,
                               canonical_domain=domain,
                               identity_confidence=confidence,
                               identity_evidence=evidence)
    identity.validate()
    return identity


def is_duplicate(a: CompanyIdentity, b: CompanyIdentity) -> bool:
    """Exact-match dedup on canonical domain — never fuzzy, so two distinct
    companies are never collapsed."""
    return bool(a.canonical_domain) and a.canonical_domain == b.canonical_domain

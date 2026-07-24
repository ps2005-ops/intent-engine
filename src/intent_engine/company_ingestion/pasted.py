"""V1.1 pasted evidence — the simplest approved external-market source.

Pasted text is labelled founder/user-provided, never treated as
independently verified public truth. Secrets are refused. The user must
confirm authorization to provide it.
"""
from __future__ import annotations

import hashlib

from intent_engine.company_ingestion.records import (
    IngestionError, PRIVACY_CLASSES, retrieved_record,
)

PASTED_LABELS = {
    "public": "User-provided public excerpt",
    "user_public_excerpt": "User-provided public excerpt",
    "user_internal": "Founder-provided evidence (internal)",
}


def pasted_source(*, run_id, company_id, label: str, origin: str,
                  text: str, privacy: str, authorized: bool,
                  date_known: str = "") -> dict:
    if not authorized:
        raise IngestionError(
            "pasted evidence requires confirmation that the user is "
            "authorized to provide it")
    if privacy not in PRIVACY_CLASSES:
        raise IngestionError(f"privacy must be one of {PRIVACY_CLASSES}")
    if not (text or "").strip():
        raise IngestionError("pasted evidence is empty")
    if not (label or "").strip() or not (origin or "").strip():
        raise IngestionError("pasted evidence needs a source label and an "
                             "origin description")
    text = text.strip()[:100_000]
    source_id = f"pasted-{hashlib.sha256(text.encode()).hexdigest()[:16]}"
    return retrieved_record(
        source_id=source_id, run_id=run_id, company_id=company_id,
        original_url=f"user:{label}", final_url=f"user:{label}",
        source_type="pasted", status_code=0, mime_type="text/plain",
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        byte_count=len(text.encode()), title=label, text_content=text,
        freshness="CURRENT" if date_known else "UNKNOWN",
        retrieval_status="OK", privacy=privacy,
        origin_note=f"{PASTED_LABELS.get(privacy, 'User-provided')} — "
                    f"origin: {origin}"
                    + (f"; date: {date_known}" if date_known else ""))

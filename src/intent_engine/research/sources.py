"""Source canonicalization, quality grading, independence, freshness, and
retirement (T019). All deterministic, all versioned, none model-assisted.

Three properties are load-bearing and separately tested:

  * a grade depends ONLY on recorded source properties — never on whether
    the source agrees with anything;
  * three outlets quoting one wire report are ONE independent source, not
    three (independence_group);
  * quality outranks recency: a 2014 peer-reviewed result grades HIGH
    while a 2026 blog grades LOW. Freshness labels; it does not promote.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from intent_engine.research.records import (
    FRESHNESS_FRESH, FRESHNESS_RETIRED, FRESHNESS_STALE, HIGH_CLASSES,
    LOW_CLASSES, MEDIUM_CLASSES, QUALITY_HIGH, QUALITY_LOW, QUALITY_MEDIUM,
    QUALITY_UNKNOWN, RETIREMENT_REASONS, SOURCE_CLASSES, ResearchError,
)

SOURCE_QUALITY_VERSION = "source_quality.v1"
CANONICALIZATION_VERSION = "source_canonical.v1"
FRESHNESS_VERSION = "freshness.v1"

# Tracking / delivery parameters that never change the identity of a source.
_STRIP_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                 "utm_content", "download", "ref", "fbclid", "gclid",
                 "mc_cid", "mc_eid", "s", "share"}
_STRIP_SUFFIXES = (".pdf", "/amp", "/print")

# Freshness policy by domain. Unknown domain gets the MOST conservative
# policy, never the most permissive.
FRESHNESS_POLICY_DAYS = {
    "market_data": 7,
    "vendor_pricing": 30,
    "financial_regulation": 30,
    "model_capabilities": 90,
    "ai_research": 180,
    "company_own_data": 180,
    "mathematics": None,          # never expires
    "historical_event": None,
}
CONSERVATIVE_FRESHNESS_DAYS = 7   # unknown domain


def canonicalize_locator(locator: str) -> str:
    """Different URLs for one artifact resolve to ONE canonical source.

    doi.org/10.1/x, the publisher mirror, `?download=1`, an AMP page and a
    utm-tagged share link are the same source, so they must not be counted
    as separate corroboration."""
    if not locator:
        raise ResearchError("a source requires a locator")
    raw = locator.strip()
    if "://" not in raw:
        return raw                      # file path or "founder-supplied"
    parts = urlsplit(raw.lower())
    netloc = parts.netloc[4:] if parts.netloc.startswith("www.") else parts.netloc
    path = parts.path.rstrip("/")
    for suffix in _STRIP_SUFFIXES:
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    # a DOI is the canonical identity wherever it is hosted
    doi = re.search(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", raw.lower())
    if doi:
        return f"doi:{doi.group(0).rstrip('.')}"
    query = "&".join(f"{k}={v}" for k, v in sorted(parse_qsl(parts.query))
                     if k not in _STRIP_PARAMS)
    return urlunsplit(("https", netloc, path, query, ""))


def content_hash(text: str) -> str:
    normalized = " ".join((text or "").split())
    return "sha256:" + hashlib.sha256(normalized.encode()).hexdigest()


def grade_source(source: dict) -> dict:
    """Rule-based, versioned, reason-carrying. Never sees agreement."""
    cls = source.get("source_class")
    if cls not in SOURCE_CLASSES:
        raise ResearchError(f"unknown source_class: {cls!r}")
    reasons = []
    attributed = bool(source.get("author") or source.get("publisher"))
    dated = bool(source.get("published_date"))
    hashed = bool(source.get("content_hash"))
    retrieved = bool(source.get("retrieved_at"))

    if not (hashed and retrieved):
        raise ResearchError("a source requires a content hash and a retrieval "
                            "timestamp before it can be graded or cited")

    if cls == "llm_generated":
        return {"source_quality": QUALITY_LOW,
                "quality_version": SOURCE_QUALITY_VERSION,
                "model_written": True,
                "reasons": ["model-written text is capped at LOW and is "
                            "flagged as model-written, including our own"]}

    if cls == "unknown":
        grade, reasons = QUALITY_UNKNOWN, ["source class is unknown"]
    elif cls in HIGH_CLASSES:
        if attributed and dated:
            grade = QUALITY_HIGH
            reasons.append(f"{cls}: attributed, dated, and content-hashed")
        elif attributed:
            grade = QUALITY_MEDIUM
            reasons.append(f"{cls} but undated — downgraded to MEDIUM")
        else:
            grade = QUALITY_UNKNOWN
            reasons.append(f"{cls} without attribution — cannot be graded")
    elif cls in MEDIUM_CLASSES:
        if attributed and dated:
            grade = QUALITY_MEDIUM
            reasons.append(f"{cls}: named author and date")
        else:
            grade = QUALITY_UNKNOWN
            reasons.append(f"{cls} missing author or date")
    elif cls in LOW_CLASSES:
        grade = QUALITY_LOW
        reasons.append(f"{cls} is a low-authority class regardless of content")
    else:                                            # pragma: no cover
        grade, reasons = QUALITY_UNKNOWN, ["unclassified"]

    return {"source_quality": grade,
            "quality_version": SOURCE_QUALITY_VERSION,
            "model_written": False,
            "reasons": reasons}


def independence_group(source: dict) -> str:
    """Sources that are not independent share a group.

    Reuters, plus NYT and CNN both citing Reuters, is ONE independent
    source. The group is the ORIGIN: an explicitly declared
    `derived_from_source` wins, else the declared `source_family`, else the
    source's own canonical locator.
    """
    # A derived source belongs to its ORIGIN's group — the same group the
    # origin computes for itself — so the wire report and the three
    # outlets repeating it collapse to one.
    origin = source.get("derived_from_source")
    if origin:
        return f"self:{origin}"
    family = source.get("source_family")
    if family:
        return f"family:{family}"
    return f"self:{source.get('canonical_locator') or source.get('source_id')}"


def count_independent(sources: list) -> dict:
    """Independent-source count plus the groups it collapsed."""
    groups = {}
    for src in sources:
        groups.setdefault(independence_group(src), []).append(
            src.get("source_id"))
    return {"independent_count": len(groups),
            "total_sources": len(sources),
            "groups": {g: sorted(ids) for g, ids in sorted(groups.items())},
            "collapsed": {g: sorted(ids) for g, ids in sorted(groups.items())
                          if len(ids) > 1}}


def freshness_of(source: dict, *, as_of: str) -> dict:
    """FRESH / STALE / RETIRED, with the policy that produced it.

    Retirement is not staleness: stale means old, retired means unusable.
    Neither ever deletes anything.
    """
    if source.get("retired_reason"):
        reason = source["retired_reason"]
        if reason not in RETIREMENT_REASONS:
            raise ResearchError(f"unknown retirement reason: {reason!r}")
        return {"freshness": FRESHNESS_RETIRED, "reason": reason,
                "policy_version": FRESHNESS_VERSION,
                "note": "retired evidence is unusable regardless of age"}

    domain = source.get("domain")
    if domain in FRESHNESS_POLICY_DAYS:
        limit = FRESHNESS_POLICY_DAYS[domain]
        policy_note = f"domain policy: {domain}"
    else:
        limit = CONSERVATIVE_FRESHNESS_DAYS
        policy_note = ("unknown domain — the most conservative policy "
                       "applies, never the most permissive")
    if limit is None:
        return {"freshness": FRESHNESS_FRESH, "age_days": None,
                "policy_version": FRESHNESS_VERSION,
                "reason": f"{policy_note}: does not expire"}

    published = source.get("published_date") or source.get("retrieved_at")
    try:
        age = (datetime.fromisoformat(as_of)
               - datetime.fromisoformat(published)).days
    except (TypeError, ValueError):
        return {"freshness": FRESHNESS_STALE, "age_days": None,
                "policy_version": FRESHNESS_VERSION,
                "reason": "undated source — treated as stale, not fresh"}
    return {"freshness": FRESHNESS_FRESH if age <= limit else FRESHNESS_STALE,
            "age_days": age, "limit_days": limit,
            "policy_version": FRESHNESS_VERSION, "reason": policy_note}


def outranks(a: dict, b: dict) -> bool:
    """Anti-recency bias, stated explicitly: QUALITY outranks recency.

    A 2014 peer-reviewed result outranks a 2026 blog post. Recency only
    breaks ties WITHIN a quality band.
    """
    order = {QUALITY_HIGH: 3, QUALITY_MEDIUM: 2, QUALITY_LOW: 1,
             QUALITY_UNKNOWN: 0}
    qa, qb = order[a["source_quality"]], order[b["source_quality"]]
    if qa != qb:
        return qa > qb
    return (a.get("published_date") or "") > (b.get("published_date") or "")

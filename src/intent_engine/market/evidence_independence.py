"""Independence of ORIGIN, and what a re-observation is actually worth.

TWO AXES, AND MARKET ALREADY HAD ONE
-------------------------------------
`micro_evidence.INDEPENDENCE` maps a source ROLE to a weight — company_owned
0.25, government_statistic 0.95 — and `self_authored` marks a subject speaking
about itself. That is the VANTAGE axis and it is reused here unchanged; this
module does not define a second notion of independence.

What Market lacked is the ORIGIN axis. Two items can both be
`independent_reporting` at 0.90 and still be one wire story republished twice.
Vantage is a property of a single item; syndication is a relation BETWEEN
items, so no per-item weight can see it. Independence needs both: an outside
vantage point AND an origin nothing else in the set already supplied.

WHY THIS MATTERS TO BELIEFS, NOT JUST TO REPORTS
-------------------------------------------------
Ten syndicated copies each carrying 0.90 would update a belief as though ten
outlets had checked the claim independently. `independent_groups` exists so a
consumer can count ORIGINS rather than rows.

RE-OBSERVATION IS NOT WASTE
----------------------------
The weekly report measured 84% of arrivals as already-known and called it the
bottleneck. That number is not a defect on its own: re-reading a page to see
whether a preregistered expectation came true, or to revalidate an ageing
belief, is exactly what a serious intelligence system does. Optimising it to
zero would blind the engine to change.

So re-observations are CLASSIFIED rather than counted. The finding worth
acting on is the low-value share, not the repeat share.
"""
from __future__ import annotations

import collections
import hashlib
import re
from typing import Dict, List, Sequence
from urllib.parse import urlparse

from .micro_evidence import INDEPENDENCE, SELF_AUTHORED

CONTRACT = "market_evidence_independence.v1"

# --- independence states (closed, §10) ---------------------------------------
INDEPENDENT = "INDEPENDENT"
PARTIALLY_INDEPENDENT = "PARTIALLY_INDEPENDENT"
DERIVED = "DERIVED"
SAME_ORIGIN = "SAME_ORIGIN"
UNKNOWN = "UNKNOWN"
UNAVAILABLE = "UNAVAILABLE"
STATES = (INDEPENDENT, PARTIALLY_INDEPENDENT, DERIVED, SAME_ORIGIN, UNKNOWN,
          UNAVAILABLE)

#: Weight at or above which a source role counts as an outside vantage point.
#: Taken from the existing table rather than invented: executive_statement
#: (0.35) and company_owned (0.25) sit below it, everything else above.
OUTSIDE_VANTAGE_FLOOR = 0.60

# --- re-observation classes (closed, §12) ------------------------------------
EXACT_DUPLICATE = "EXACT_DUPLICATE"
SAME_DOCUMENT_NEW_FETCH = "SAME_DOCUMENT_NEW_FETCH"
USEFUL_REVALIDATION = "USEFUL_REVALIDATION"
REQUIRED_MONITORING = "REQUIRED_MONITORING"
STALE_RECHECK = "STALE_RECHECK"
LOW_VALUE_REPEAT = "LOW_VALUE_REPEAT"
REOBSERVATION_CLASSES = (EXACT_DUPLICATE, SAME_DOCUMENT_NEW_FETCH,
                         USEFUL_REVALIDATION, REQUIRED_MONITORING,
                         STALE_RECHECK, LOW_VALUE_REPEAT)

#: Classes that earn their retrieval. A re-observation is valuable when it is
#: testing something: an open expectation, a belief due for review, or a
#: source under deliberate watch.
VALUABLE_REOBSERVATION = frozenset({USEFUL_REVALIDATION, REQUIRED_MONITORING,
                                    STALE_RECHECK})

_WORD = re.compile(r"[a-z0-9]+")


def _host(source: str) -> str:
    text = str(source or "")
    if "://" not in text:
        return ""
    try:
        return (urlparse(text).hostname or "").lower()
    except ValueError:
        return ""


def origin_id(row: dict) -> str:
    """The publishing ORIGIN of one evidence row.

    A URL collapses to its registrable-ish host; a non-URL `source` (the
    role-style values this ledger also uses, e.g. `company_owned`) collapses
    to role plus subject, because ten company-owned pages about one company
    are one origin however many paths they have.

    Coarse on purpose and NEVER a security decision — this decides whether two
    rows corroborate each other, not whether anything may be fetched.
    """
    host = _host(row.get("source"))
    if host:
        labels = [p for p in host.split(".") if p]
        return ".".join(labels[-2:]) if len(labels) > 2 else ".".join(labels)
    role = str(row.get("source_role") or row.get("source") or "").strip()
    subject = str(row.get("subject_company") or "").strip()
    return f"{role}@{subject}" if role or subject else ""


def _claim_key(row: dict) -> str:
    """A normalised fingerprint of the CLAIM, for syndication detection."""
    words = _WORD.findall(str(row.get("fact") or "").lower())[:40]
    if len(words) < 5:
        return ""
    return hashlib.blake2b(" ".join(words).encode(), digest_size=12).hexdigest()


def _vantage(row: dict) -> float:
    role = str(row.get("source_role") or row.get("source") or "")
    value = row.get("independence")
    if isinstance(value, (int, float)):
        return float(value)
    return INDEPENDENCE.get(role, 0.5)


def _self_authored(row: dict) -> bool:
    if isinstance(row.get("self_authored"), bool):
        return bool(row["self_authored"])
    return str(row.get("source_role") or row.get("source")) in SELF_AUTHORED


def classify(rows: Sequence[dict]) -> List[dict]:
    """Label each evidence row with its independence state and origin.

    Order matters and is the retrieval order: the FIRST row to establish a
    claim at an origin anchors it, and later rows are measured against that.
    """
    seen_claim_origin: Dict[tuple, int] = {}
    claim_first: Dict[str, int] = {}
    origins_used: Dict[str, int] = {}
    out: List[dict] = []

    for index, row in enumerate(rows):
        origin = origin_id(row)
        claim = _claim_key(row)
        vantage = _vantage(row)
        outside = vantage >= OUTSIDE_VANTAGE_FLOOR and not _self_authored(row)

        state, anchor = None, None
        if claim and (claim, origin) in seen_claim_origin:
            state, anchor = SAME_ORIGIN, seen_claim_origin[(claim, origin)]
        elif claim and claim in claim_first:
            # Same words, different origin: a republication of one claim, not
            # a second outlet checking it.
            state, anchor = DERIVED, claim_first[claim]
        elif not origin:
            state = UNKNOWN
        elif origin in origins_used and not claim:
            state, anchor = SAME_ORIGIN, origins_used[origin]
        elif outside:
            state = INDEPENDENT
        else:
            # An identified origin whose vantage is the subject itself.
            state = PARTIALLY_INDEPENDENT

        if claim:
            seen_claim_origin.setdefault((claim, origin), index)
            claim_first.setdefault(claim, index)
        if origin:
            origins_used.setdefault(origin, index)

        out.append({
            "index": index,
            "evidence_id": str(row.get("evidence_id") or ""),
            "origin_id": origin,
            "claim_key": claim,
            "vantage": round(vantage, 3),
            "self_authored": _self_authored(row),
            "state": state,
            "anchor_index": anchor,
            # Only these two add a genuinely separate observation.
            "counts_as_independent": state == INDEPENDENT,
        })
    return out


def assess(rows: Sequence[dict]) -> dict:
    """Independence over one evidence set. UNKNOWN never becomes independent."""
    if not rows:
        return {"contract": CONTRACT, "state": "MEASURED", "evidence_rows": 0,
                "corroboration_state": UNAVAILABLE,
                "reason": "no evidence rows to assess"}
    labelled = classify(rows)
    states = collections.Counter(r["state"] for r in labelled)
    independent_origins = sorted({r["origin_id"] for r in labelled
                                  if r["counts_as_independent"]
                                  and r["origin_id"]})
    origins = sorted({r["origin_id"] for r in labelled if r["origin_id"]})
    sizes = collections.Counter(r["origin_id"] for r in labelled
                                if r["origin_id"])
    return {
        "contract": CONTRACT,
        # The producer RAN. A caller that omits it must report UNAVAILABLE —
        # "measured, and it is zero" and "nothing measured it" are different.
        "state": "MEASURED",
        "evidence_rows": len(labelled),
        "unique_origins": len(origins),
        "independent_groups": len(independent_origins),
        "independent_rows": states.get(INDEPENDENT, 0),
        "partially_independent_rows": states.get(PARTIALLY_INDEPENDENT, 0),
        "derived_rows": states.get(DERIVED, 0),
        "same_origin_rows": states.get(SAME_ORIGIN, 0),
        "unknown_rows": states.get(UNKNOWN, 0),
        "by_state": dict(sorted(states.items())),
        "concentration_ratio": (round(max(sizes.values()) / len(labelled), 4)
                                if sizes else None),
        "corroboration_state": _corroboration(len(independent_origins),
                                              states, len(labelled)),
        "independent_origins": independent_origins,
    }


def _corroboration(independent: int, states, rows: int) -> str:
    if states.get(UNKNOWN, 0) == rows:
        return UNAVAILABLE
    if independent >= 2:
        return INDEPENDENT
    if independent == 1:
        return PARTIALLY_INDEPENDENT
    if states.get(DERIVED, 0):
        return DERIVED
    return SAME_ORIGIN


#: How close an expectation's evaluation window must be before re-reading a
#: page counts as TESTING it. An expectation whose window closes in eleven
#: months is not being tested by today's fetch, and calling that
#: REQUIRED_MONITORING marks every repeat as valuable — which is how a
#: classifier reports a clean bill of health on the exact bottleneck it was
#: built to diagnose. Measured: the first naive version returned
#: REQUIRED_MONITORING for 301 of 301 sightings.
MONITORING_HORIZON_DAYS = 45


def _days_until(target: str, as_of: str):
    import datetime as _dt
    try:
        a = _dt.date.fromisoformat(str(target)[:10])
        b = _dt.date.fromisoformat(str(as_of)[:10])
    except ValueError:
        return None
    return (a - b).days


def classify_reobservations(sightings: Sequence[dict], *, as_of: str,
                            open_expectations: Sequence[dict] = (),
                            beliefs_due_subjects=(),
                            monitored_sources=()) -> dict:
    """What each re-observation was FOR (§12/§13).

    Takes EXPECTATION RECORDS, not subject names. The distinction is the whole
    point: a re-read is REQUIRED_MONITORING only when an expectation on that
    subject is actually close to (or past) its evaluation window, because only
    then can the re-read resolve anything. Matching on subject alone marked
    every one of 301 live sightings as valuable and reported a 0% low-value
    rate against a measured 84% repeat rate.

    Nothing defaults to LOW_VALUE_REPEAT without the inputs that could have
    proven otherwise; absent them the whole classification is UNMEASURABLE.
    """
    due = set(beliefs_due_subjects)
    monitored = set(monitored_sources)
    testable: Dict[str, int] = {}
    for row in open_expectations:
        subject = str(row.get("subject") or row.get("subject_company") or "")
        days = _days_until(row.get("evaluation_window_ends") or "", as_of)
        if subject and days is not None and days <= MONITORING_HORIZON_DAYS:
            testable[subject] = min(testable.get(subject, days), days)

    if not (testable or due or monitored):
        return {"contract": CONTRACT, "state": "UNMEASURABLE",
                "sightings": len(sightings),
                "open_expectations": len(open_expectations),
                "testable_subjects": 0,
                "reason": (
                    f"no expectation window closes within "
                    f"{MONITORING_HORIZON_DAYS} days, no belief is due for "
                    f"review, and no source is under explicit watch — so "
                    f"nothing here can distinguish a purposeful re-read from "
                    f"a wasted one")}

    labelled, seen_ids = [], set()
    for row in sightings:
        subject = str(row.get("subject_company") or "")
        evidence_id = str(row.get("evidence_id") or "")
        first = str(row.get("occurrence_first_seen") or "")
        again = str(row.get("seen_at") or "")
        if evidence_id and evidence_id in seen_ids and first == again:
            kind = EXACT_DUPLICATE
        elif subject in testable:
            kind = REQUIRED_MONITORING
        elif subject in due:
            kind = USEFUL_REVALIDATION
        elif str(row.get("source")) in monitored:
            kind = STALE_RECHECK
        elif first and again and first != again:
            kind = SAME_DOCUMENT_NEW_FETCH
        else:
            kind = LOW_VALUE_REPEAT
        seen_ids.add(evidence_id)
        labelled.append({"evidence_id": evidence_id, "subject": subject,
                         "class": kind})

    counts = collections.Counter(r["class"] for r in labelled)
    valuable = sum(counts[k] for k in VALUABLE_REOBSERVATION)
    total = len(labelled)
    return {
        "contract": CONTRACT,
        "state": "MEASURED",
        "sightings": total,
        "open_expectations": len(open_expectations),
        "testable_subjects": len(testable),
        "by_class": {k: counts.get(k, 0) for k in REOBSERVATION_CLASSES},
        "valuable": valuable,
        "low_value": counts.get(LOW_VALUE_REPEAT, 0),
        "useful_reobservation_rate": (round(valuable / total, 4)
                                      if total else None),
        "low_value_repeat_rate": (round(counts.get(LOW_VALUE_REPEAT, 0)
                                        / total, 4) if total else None),
        "note": ("a high repeat share is only a defect to the extent it is "
                 "LOW_VALUE_REPEAT; monitoring and revalidation are the "
                 "system doing its job"),
    }

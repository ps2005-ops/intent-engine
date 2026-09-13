"""WHY this run could not produce a full report, in one classified reason.

WHAT WAS WRONG WITH ONE REASON. Every bounded abstention reached the reader
and the operator as the same thing: not enough evidence. Measured across the
50-company requalification, 23 of 50 runs took that path, and the single label
could not separate

    "SEC answered 429 to us specifically, this minute"
    "this company's own website refuses automated access"
    "the interactive time budget was spent before the sources were read"
    "we read plenty and none of it was independent"
    "the reasoning step raised"

which are four operational problems and one product problem. A cohort that
reports them as one number cannot be acted on, and a qualification run that
counts them together cannot tell a healthy product under a degraded network
from a broken one.

WHAT THIS IS NOT. It is NOT the sentence the customer reads. The reader gets
prose that names the hosts and says what is missing; this is the machine-side
label beside it, for telemetry and qualification. Keeping them separate is
deliberate: a Chief Strategy Officer must never have to understand the string
`EXTERNAL_RATE_LIMIT`.

PRECEDENCE IS THE WHOLE DESIGN. A run usually has several of these at once --
a 403 here, a timeout there, and thin evidence at the end. The reason reported
is the one that most explains the outcome, and external causes outrank
internal ones ONLY when they actually removed evidence. A run that was rate
limited on two sources and still read nine documents did not abstain because
of the rate limit.
"""
from __future__ import annotations

from urllib.parse import urlparse

# --- the taxonomy -----------------------------------------------------------
EXTERNAL_RATE_LIMIT = "EXTERNAL_RATE_LIMIT"
EXTERNAL_ACCESS_REFUSED = "EXTERNAL_ACCESS_REFUSED"
EXTERNAL_TIMEOUT = "EXTERNAL_TIMEOUT"
DISCOVERY_INSUFFICIENT = "DISCOVERY_INSUFFICIENT"
SOURCE_DIVERSITY_INSUFFICIENT = "SOURCE_DIVERSITY_INSUFFICIENT"
PRIMARY_EVIDENCE_MISSING = "PRIMARY_EVIDENCE_MISSING"
EVIDENCE_CONFLICT_UNRESOLVED = "EVIDENCE_CONFLICT_UNRESOLVED"
REASONING_FAILURE = "REASONING_FAILURE"
MODEL_REFUSAL = "MODEL_REFUSAL"
INTERNAL_FAILURE = "INTERNAL_FAILURE"
CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
NOT_ABSTAINED = "NOT_ABSTAINED"

ABSTENTION_REASONS = (
    EXTERNAL_RATE_LIMIT, EXTERNAL_ACCESS_REFUSED, EXTERNAL_TIMEOUT,
    BUDGET_EXCEEDED, DISCOVERY_INSUFFICIENT, SOURCE_DIVERSITY_INSUFFICIENT,
    PRIMARY_EVIDENCE_MISSING, EVIDENCE_CONFLICT_UNRESOLVED,
    REASONING_FAILURE, MODEL_REFUSAL, INTERNAL_FAILURE, CAPACITY_EXCEEDED,
    IDENTITY_UNRESOLVED, NOT_ABSTAINED,
)

#: Below this many usable documents, an external cause that removed sources is
#: what explains the outcome. Above it, the run had evidence to work with and
#: the abstention is about the evidence's SHAPE, not about our access to it.
_THIN = 4


def _status_in(message: str, codes) -> bool:
    text = str(message or "")
    return any(str(code) in text for code in codes)


def classify(*, readiness_state: str = "", failures=(), documents=(),
             unmet_checks=(), reasoning_error: str = "",
             capacity_refused: bool = False,
             budget_gaps=()) -> dict:
    """The one reason that most explains why this run did not report.

    Returns {reason, detail, counts, hosts}. Pure and deterministic: it reads
    what the run recorded and never re-derives it from the network.
    """
    failures = list(failures or ())
    documents = list(documents or ())
    unmet = set(unmet_checks or ())

    counts = {"rate_limited": 0, "refused": 0, "timed_out": 0,
              "not_found": 0, "budget": 0, "other": 0}
    hosts: dict = {}
    for failure in failures:
        kind = failure.get("failure_type") or ""
        message = failure.get("safe_message") or ""
        url = failure.get("url") or failure.get("original_url") or ""
        host = (urlparse(url).hostname or "") if url else ""
        if host:
            hosts[host] = hosts.get(host, 0) + 1
        if kind == "deadline_exceeded":
            counts["budget"] += 1
        elif _status_in(message, (429,)):
            counts["rate_limited"] += 1
        elif _status_in(message, (401, 402, 403, 451)):
            counts["refused"] += 1
        elif kind in ("timeout", "connection", "host_unreachable"):
            counts["timed_out"] += 1
        elif _status_in(message, (404, 410)):
            counts["not_found"] += 1
        else:
            counts["other"] += 1
    counts["budget"] += len(list(budget_gaps or ()))

    def out(reason, detail):
        return {"reason": reason, "detail": detail, "counts": counts,
                "hosts": dict(sorted(hosts.items(),
                                     key=lambda kv: -kv[1])[:6]),
                "documents": len(documents)}

    # 1. Causes that are not about evidence at all.
    if capacity_refused:
        return out(CAPACITY_EXCEEDED,
                   "the analysis was refused before it started")
    if reasoning_error:
        lowered = reasoning_error.lower()
        if "refus" in lowered or "declin" in lowered:
            return out(MODEL_REFUSAL, reasoning_error[:200])
        return out(REASONING_FAILURE, reasoning_error[:200])
    if readiness_state == "IDENTITY_UNRESOLVED":
        return out(IDENTITY_UNRESOLVED,
                   "the company this report would be about was not established")
    if not readiness_state:
        return out(INTERNAL_FAILURE, "no readiness verdict was recorded")
    if readiness_state in ("READY_FOR_FULL_REPORT",):
        return out(NOT_ABSTAINED, "")

    # 2. External causes, but ONLY where they actually removed evidence.
    #    A run holding nine documents did not abstain because two sources
    #    were rate limited.
    if len(documents) < _THIN:
        if counts["budget"]:
            return out(BUDGET_EXCEEDED,
                       f"{counts['budget']} source(s) were not requested "
                       f"before the interactive time budget was spent")
        if counts["rate_limited"]:
            return out(EXTERNAL_RATE_LIMIT,
                       f"{counts['rate_limited']} source(s) were rate limited")
        if counts["refused"]:
            return out(EXTERNAL_ACCESS_REFUSED,
                       f"{counts['refused']} source(s) refused automated "
                       f"access")
        if counts["timed_out"]:
            return out(EXTERNAL_TIMEOUT,
                       f"{counts['timed_out']} source(s) did not answer")
        if not failures and not documents:
            return out(DISCOVERY_INSUFFICIENT,
                       "no candidate source could be proposed")

    # 3. The evidence arrived; its SHAPE is what refuses the report.
    if "identity_resolved" in unmet:
        return out(IDENTITY_UNRESOLVED,
                   "the company could not be identified confidently")
    if unmet & {"official_identity_or_product", "direction_source"}:
        return out(PRIMARY_EVIDENCE_MISSING,
                   "no authoritative account of what this company is and "
                   "where it says it is going")
    if unmet & {"market_source", "no_dominant_family", "evidence_families"}:
        return out(SOURCE_DIVERSITY_INSUFFICIENT,
                   "the evidence is too narrow to check the company's own "
                   "account of itself")
    if unmet & {"source_count", "presentable_material", "dated_evidence",
                "readable_language"}:
        return out(DISCOVERY_INSUFFICIENT,
                   "too little readable, dated material was found")
    return out(DISCOVERY_INSUFFICIENT, f"readiness is {readiness_state}")

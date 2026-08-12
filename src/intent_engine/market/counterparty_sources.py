"""Acquiring documents that NAME the other party — and measuring whether they do.

WHAT IS ALREADY SETTLED, AND MUST NOT BE RE-MEASURED
----------------------------------------------------
Three source families have been measured across ~11,000 sentences:

    news headlines      219 items    ~1 named counterparty
    10-K / 10-Q       3,959 sents     0
    8-K + exhibits    7,247 sents     0

Large-cap periodic disclosure systematically writes "our competitors", "third
parties", "our top ten customers accounted for 43% of net sales". That is a
retrieval finding, it is canonical, and asking those three families harder is
the one thing this module exists NOT to do.

WHY A FAMILY IS A MEASURED THING, NOT A PLAUSIBLE ONE
-----------------------------------------------------
The obvious next move is to add every source that sounds promising. That is
how the previous three got added. So no family is integrated on argument: each
one runs, and reports what it actually produced per document. A family with a
measured yield of zero is a REJECTED family, recorded as such, and the record
is the reason nobody spends another wave rediscovering it.

`yield_per_document` is the number that decides, and it is deliberately per
DOCUMENT rather than per request: a source that returns a thousand documents
containing one relationship is worse than one returning three documents with
one each, and a per-request rate would rank them the other way round.

STRUCTURED BEATS PROSE, WHEN IT EXISTS
--------------------------------------
A federal contract award names both parties in typed fields. No sentence has
to be parsed, so nothing can be fabricated by a regex that matched the wrong
clause — the failure mode this project has hit repeatedly. Where an official
structured source exists it is preferred over scraping the prose that
describes the same fact.

THE EVENT IS NOT THE RELATIONSHIP
---------------------------------
A single award proves a transaction happened. It does not prove dependence,
materiality, renewal, or that the buyer will still be there next year. So an
award admits `SELLS_TO`, bounded by the contract's own dates, and never
`DEPENDS_ON`. Same rule for the other families: keep the WEAKEST accurate
relation, and represent durability separately if something states it.
"""
from __future__ import annotations

import collections
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

CONTRACT = "counterparty_source.v1"

# --- families ---------------------------------------------------------------
GOVERNMENT_AWARD = "government_award"
PARTNERSHIP_RELEASE = "partnership_release"
CUSTOMER_CASE_STUDY = "customer_case_study"
REGISTRATION_STATEMENT = "registration_statement"     # S-1 / F-1
SUPPLIER_ANNOUNCEMENT = "supplier_announcement"
MERGER_FILING = "merger_filing"
RESELLER_ANNOUNCEMENT = "reseller_announcement"
MARKETPLACE_PARTNERSHIP = "marketplace_partnership"

#: Settled by measurement, listed so nothing re-adds them by accident.
CLOSED_FAMILIES = {
    "news_headline": "219 items, ~1 named counterparty",
    "periodic_report": "3,959 10-K/10-Q sentences, 0 named counterparties",
    "current_report": "7,247 8-K + exhibit sentences, 0 named counterparties",
}

# --- integration verdicts ---------------------------------------------------
INTEGRATE = "INTEGRATE"
REJECT = "REJECT"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
UNREACHABLE = "UNREACHABLE"
VERDICTS = (INTEGRATE, REJECT, INSUFFICIENT_SAMPLE, UNREACHABLE)

#: Below this many documents, a zero means "we did not look hard enough" and
#: a hit means "we got lucky". Neither is a verdict.
MIN_DOCUMENTS_FOR_VERDICT = 5

#: One accepted relationship per twenty documents. Deliberately low: the
#: incumbent families measured 0.0000, so anything that clears a rounding
#: error is a strict improvement on what production has.
INTEGRATE_ABOVE_YIELD = 0.05


@dataclass(frozen=True)
class Document:
    """One retrieved thing, with enough provenance to argue about it later."""
    document_id: str
    family: str
    subject: str
    title: str
    text: str
    url: str
    published_at: str = ""
    fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class Yield:
    """What a source family actually produced. Every field is a count.

    `identity_resolved` is separated from `relationship_candidates` on
    purpose. A family can produce plenty of candidate pairs and still be
    useless if neither end can be tied to a company the engine tracks, and
    the two failures need different fixes: more documents versus a better
    resolver.
    """
    family: str
    #: SUBJECTS asked about — one per company in the sweep. Named for the
    #: population it counts. It was called `documents_attempted`, which made
    #: `documents_retrieved / documents_attempted` look like a retrieval
    #: yield; it is not, and it exceeded 1.0 in 22 of 40 live rows because one
    #: subject routinely returns several documents.
    subjects_attempted: int = 0
    #: DOCUMENT fetch attempts. This is the denominator a document-level yield
    #: actually needs, and it did not exist before.
    document_attempts: int = 0
    documents_retrieved: int = 0
    named_actor_mentions: int = 0
    relationship_candidates: int = 0
    identity_resolved: int = 0
    #: Of those, how many matched a NAMED PART of the company rather than the
    #: company. Tracked apart because a family that only ever reaches
    #: subsidiaries is telling you the parent does not transact under its own
    #: name, which is a fact about the company, not about the source.
    identity_resolved_via_subsidiary: int = 0
    relationships_accepted: int = 0
    relationships_refused: int = 0
    duplicates: int = 0
    latency_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    refusal_reasons: Dict[str, int] = field(default_factory=dict)

    @property
    def yield_per_document(self) -> float:
        if not self.documents_retrieved:
            return 0.0
        return self.relationships_accepted / self.documents_retrieved

    @property
    def duplicate_rate(self) -> float:
        seen = self.relationships_accepted + self.duplicates
        return (self.duplicates / seen) if seen else 0.0

    def verdict(self) -> Tuple[str, str]:
        """Integrate on measured yield, never on how promising it sounded."""
        if self.errors and not self.documents_retrieved:
            return UNREACHABLE, (
                f"{len(self.errors)} error(s) and no documents retrieved: "
                f"{self.errors[0][:120]}")
        if self.documents_retrieved < MIN_DOCUMENTS_FOR_VERDICT:
            return INSUFFICIENT_SAMPLE, (
                f"{self.documents_retrieved} document(s) is below the "
                f"{MIN_DOCUMENTS_FOR_VERDICT} needed for a zero to mean "
                f"anything")
        if self.yield_per_document > INTEGRATE_ABOVE_YIELD:
            return INTEGRATE, (
                f"{self.relationships_accepted} accepted relationship(s) "
                f"from {self.documents_retrieved} documents "
                f"({self.yield_per_document:.3f}/doc)")
        return REJECT, (
            f"{self.documents_retrieved} documents produced "
            f"{self.relationships_accepted} accepted relationships "
            f"({self.yield_per_document:.3f}/doc); the documents do not "
            f"name counterparties often enough to be worth the request")

    def as_dict(self) -> dict:
        verdict, why = self.verdict()
        return {
            "contract": CONTRACT, "family": self.family,
            "subjects_attempted": self.subjects_attempted,
            "document_attempts": self.document_attempts,
            "documents_retrieved": self.documents_retrieved,
            "named_actor_mentions": self.named_actor_mentions,
            "relationship_candidates": self.relationship_candidates,
            "identity_resolved": self.identity_resolved,
            "identity_resolved_via_subsidiary":
                self.identity_resolved_via_subsidiary,
            "relationships_accepted": self.relationships_accepted,
            "relationships_refused": self.relationships_refused,
            "yield_per_document": round(self.yield_per_document, 4),
            "duplicate_rate": round(self.duplicate_rate, 4),
            "latency_seconds": round(self.latency_seconds, 2),
            "verdict": verdict, "verdict_reason": why,
            "refusal_reasons": dict(sorted(self.refusal_reasons.items())),
            "errors": self.errors[:5],
        }


# --- identity resolution ----------------------------------------------------
#
# `Linear Minerals Corp.` once satisfied the alias `Linear`. A resolver that
# accepts a substring will happily bind a relationship to the wrong company
# and there is no downstream check that catches it, because the edge looks
# perfectly well-formed. So matching is on WHOLE TOKENS, after corporate
# suffixes are removed from both sides.
_SUFFIX = re.compile(
    r"\b(?:inc|corp|corporation|company|co|ltd|limited|llc|l\.l\.c|plc|"
    r"s\.a|n\.v|nv|ag|se|gmbh|holdings?|group|technologies|systems|"
    r"international|worldwide|the)\b\.?", re.I)


def normalise_actor(name: str) -> str:
    """A comparable form of a company name. Suffixes and punctuation go."""
    text = _SUFFIX.sub(" ", (name or "").lower())
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


# How a name matched, because the three kinds are not equally strong.
EXACT = "EXACT"
#: "Johnson & Johnson Health Care Systems Inc." under alias "Johnson &
#: Johnson". A real subsidiary, a DIFFERENT legal entity, and the graph keeps
#: it as its own node — resolution only decides which subject's sweep the row
#: is attributed to, never that the two entities are the same actor.
SUBSIDIARY_OR_DIVISION = "SUBSIDIARY_OR_DIVISION"
NO_MATCH = ""


def resolution(candidate: str, aliases: Sequence[str]) -> str:
    """How `candidate` matched these aliases: exactly, as a subsidiary, or not.

    Whole-token matching, never substring. `Linear Minerals Corp.` once
    satisfied the alias `Linear`, and the resulting edge was perfectly
    well-formed and about the wrong company — which is why a one-token alias
    may only ever match a one-token name.
    """
    got = normalise_actor(candidate)
    if not got:
        return NO_MATCH
    got_tokens = got.split()
    best = NO_MATCH
    for alias in aliases:
        want = normalise_actor(alias)
        if not want:
            continue
        want_tokens = want.split()
        if got_tokens == want_tokens:
            return EXACT
        if len(want_tokens) == 1 or len(got_tokens) == 1:
            # One token on either side is too little to license an extension.
            continue
        if _is_prefix(want_tokens, got_tokens) or \
                _is_prefix(got_tokens, want_tokens):
            best = SUBSIDIARY_OR_DIVISION
    return best


def resolves_to(candidate: str, aliases: Sequence[str]) -> bool:
    """Whether `candidate` names this company or a named part of it."""
    return resolution(candidate, aliases) != NO_MATCH


def _is_prefix(short: Sequence[str], long: Sequence[str]) -> bool:
    return len(short) <= len(long) and list(short) == list(long[:len(short)])


# --- running a family -------------------------------------------------------
Adapter = Callable[[str, Sequence[str], str], Sequence[Document]]
#: An extractor returns (relationships, refusals) and MAY return a third
#: element of per-document counts. The counts are what distinguish "this
#: family produced no candidates" from "it produced candidates that no
#: resolver could tie to a company we track" — two findings with opposite
#: fixes, which a bare accepted-count collapses into one number.
COUNTED = ("named_actor_mentions", "relationship_candidates",
           "identity_resolved", "identity_resolved_via_subsidiary")
Extractor = Callable[[Document, str, Sequence[str]], tuple]


def measure(family: str, *, subjects: Sequence[Tuple[str, Sequence[str]]],
            fetch: Adapter, extract: Extractor, as_of: str = "",
            ) -> Tuple[Tuple, Yield]:
    """Run one family over real subjects and report what it produced.

    Errors are counted, never raised: a family that fails for one company has
    still been measured on the others, and a sweep that stops at the first
    unreachable host measures nothing.
    """
    if family in CLOSED_FAMILIES:
        raise ValueError(
            f"{family!r} is settled: {CLOSED_FAMILIES[family]}. Re-measuring "
            f"it is the one thing this module exists not to do")
    report = Yield(family=family)
    started = time.monotonic()
    accepted: List = []
    seen: set = set()

    for subject, aliases in subjects:
        report.subjects_attempted += 1
        try:
            documents = list(fetch(subject, aliases, as_of))
            report.document_attempts += len(documents)
        except Exception as exc:  # noqa: BLE001 - one subject, not the sweep
            report.errors.append(f"{subject}: {type(exc).__name__}: {exc}")
            continue
        for document in documents:
            report.documents_retrieved += 1
            try:
                result = extract(document, subject, aliases)
            except Exception as exc:  # noqa: BLE001 - see above
                report.errors.append(
                    f"{document.document_id}: {type(exc).__name__}: {exc}")
                continue
            found, refused = result[0], result[1]
            counts = result[2] if len(result) > 2 else {}
            for name in COUNTED:
                setattr(report, name,
                        getattr(report, name) + int(counts.get(name, 0)))
            for reason, count in (refused or {}).items():
                report.refusal_reasons[reason] = (
                    report.refusal_reasons.get(reason, 0) + int(count))
                report.relationships_refused += int(count)
            for row in found:
                key = getattr(row, "relationship_id", None) or str(row)
                if key in seen:
                    report.duplicates += 1
                    continue
                seen.add(key)
                accepted.append(row)
                report.relationships_accepted += 1
    report.latency_seconds = time.monotonic() - started
    return tuple(accepted), report


def summarise(reports: Sequence[Yield]) -> dict:
    """Which families earned their request budget, and which are now closed."""
    rows = [r.as_dict() for r in reports]
    integrate = [r for r in rows if r["verdict"] == INTEGRATE]
    best = max(rows, key=lambda r: r["yield_per_document"], default=None)
    return {
        "contract": CONTRACT,
        "families_measured": len(rows),
        "families_integrated": len(integrate),
        "by_family": {r["family"]: r for r in rows},
        "best_yield": (best or {}).get("family", ""),
        "best_yield_per_document": (best or {}).get("yield_per_document", 0.0),
        "documents_retrieved": sum(r["documents_retrieved"] for r in rows),
        "relationships_accepted": sum(r["relationships_accepted"]
                                      for r in rows),
        "closed_families": dict(CLOSED_FAMILIES),
        "note": ("a family is integrated on measured yield per document, "
                 "never on how promising it sounded; a measured zero is a "
                 "closed family, recorded so it is not rediscovered"),
    }


def counts_by_predicate(relationships: Sequence) -> Dict[str, int]:
    return dict(collections.Counter(
        getattr(r, "predicate", "") for r in relationships))

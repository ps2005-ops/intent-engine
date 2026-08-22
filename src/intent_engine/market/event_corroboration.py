"""Several accounts of one event — and how many of them are really separate.

THE DISTINCTION THAT MUST NEVER COLLAPSE
----------------------------------------
Two sources describing the same occurrence make that occurrence more
reliable. They do not make it two tests of anything.

A belief opened by an event is TESTED by what happens next. Corroboration is
what happened at the same moment, seen twice. Wave 7 separated the two and
this module keeps them separate on purpose: `EventCorroboration` carries no
field that a reconciliation could read, and `resolves_expectation` is a
function that exists only to return False and say why.

The failure it prevents is the one the self-test guard already caught once
at the evidence layer — a belief confirming itself — reappearing one level
up, where three rewrites of a press release would look like three
confirmations of the belief that release opened.

WHY DEPENDENCY IS A CLASS AND NOT A COEFFICIENT
-----------------------------------------------
The honest statistical object here is a design effect, and computing one
would need a sample of known-independent accounts that this corpus does not
contain. So the module reports bounded CLASSES and refuses to turn them into
a number that would imply a precision nobody has:

    SAME_ORIGIN            one wire story on several sites
    DERIVED                a rewrite of the company's own release
    PARTIALLY_INDEPENDENT  different outlets, one underlying feed
    INDEPENDENT            a filing and somebody who read it separately
    UNKNOWN               the corpus cannot say

WHAT THE LIVE CORPUS FORCED
---------------------------
135 of 249 rows carry `news.google.com` as their host, because the
aggregator IS the host and the real publisher is hidden behind an opaque
redirect. Host-based independence would score all 135 as one outlet. The
publisher is instead recovered from the headline's own trailing attribution
— "… - Yahoo Finance" — which is the only place the corpus states it.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
from typing import Mapping
from urllib.parse import urlparse

from . import event_identity as EI

CONTRACT = "event_corroboration.v1"

# --- dependency classes -----------------------------------------------------
SAME_ORIGIN = "SAME_ORIGIN"
DERIVED = "DERIVED"
PARTIALLY_INDEPENDENT = "PARTIALLY_INDEPENDENT"
INDEPENDENT = "INDEPENDENT"
UNKNOWN = "UNKNOWN"
DEPENDENCY_CLASSES = (SAME_ORIGIN, DERIVED, PARTIALLY_INDEPENDENT,
                      INDEPENDENT, UNKNOWN)

#: How much each class may contribute to an independent-account count. A
#: SAME_ORIGIN pair adds nothing; only a genuinely independent one adds a
#: whole account. These are weights on a count, not probabilities.
_CONTRIBUTION = {
    SAME_ORIGIN: 0.0,
    DERIVED: 0.0,
    PARTIALLY_INDEPENDENT: 0.5,
    INDEPENDENT: 1.0,
    UNKNOWN: 0.0,
}

#: Roles that originate a fact rather than relay one.
_ORIGINATING = frozenset({"regulatory_filing", "company_owned"})

#: A Google News headline states its publisher after the last " - ".
_ATTRIBUTION = re.compile(r"\s[-–]\s([^-–]{2,40})\.?$")

#: Aggregators and syndicators. A story appearing on several of these is one
#: story, not several accounts.
_AGGREGATORS = frozenset({
    "yahoo finance", "marketscreener.com", "tradingview", "stock titan",
    "marketbeat", "investing.com", "seeking alpha", "quiver quantitative",
    "msn", "nasdaq", "benzinga", "simply wall st", "insider monkey",
    "zacks investment research", "gurufocus",
})


def _field(row, name: str, default: str = "") -> str:
    """Shape-agnostic read, shared with `event_identity`.

    These two modules consume the SAME rows, so if one reads mappings and
    the other does not, a dict-fed ledger silently becomes 155 single-account
    events with no publisher — corroboration that reports nothing wrong.
    """
    return EI._field(row, name) or default


def _flag(row, name: str) -> bool:
    if isinstance(row, Mapping):
        return bool(row.get(name, False))
    return bool(getattr(row, name, False))


def publisher_of(row) -> str:
    """Who actually published this, not who redirected to it.

    The host is the aggregator for over half the corpus, so the headline's
    own trailing attribution is preferred where it exists.
    """
    fact = _field(row, "fact")
    hit = _ATTRIBUTION.search(fact.strip())
    if hit:
        candidate = hit.group(1).strip().strip(".").lower()
        # An attribution is a NAME. A clause that happens to follow a dash
        # is not, and the corpus contains several of those.
        if len(candidate.split()) <= 4 and not candidate.endswith(" of"):
            return candidate
    host = urlparse(_field(row, "source")).hostname or ""
    return host.lower().replace("www.", "")


def _tokens(text: str) -> set:
    return {t for t in re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()
                              ).split() if len(t) > 3}


def classify(row_a, row_b) -> Tuple[str, str]:
    """How dependent two accounts of one event are, and why."""
    pub_a, pub_b = publisher_of(row_a), publisher_of(row_b)
    role_a = _field(row_a, "source_role")
    role_b = _field(row_b, "source_role")
    src_a = _field(row_a, "source")
    src_b = _field(row_b, "source")

    if src_a and src_a == src_b:
        return SAME_ORIGIN, "the same URL, read twice"
    if pub_a and pub_a == pub_b:
        return SAME_ORIGIN, f"both published by {pub_a}"

    fact_a = _tokens(_field(row_a, "fact"))
    fact_b = _tokens(_field(row_b, "fact"))
    overlap = (len(fact_a & fact_b) / len(fact_a | fact_b)) if (
        fact_a | fact_b) else 0.0

    self_a = _flag(row_a, "self_authored")
    self_b = _flag(row_b, "self_authored")
    if (self_a != self_b) and overlap >= 0.6:
        return DERIVED, (
            "one account is the company's own and the other repeats its "
            "wording; a rewrite of a release is not a second witness")

    both_relay = not (_ORIGINATING & {role_a, role_b})
    if both_relay and pub_a in _AGGREGATORS and pub_b in _AGGREGATORS:
        return PARTIALLY_INDEPENDENT, (
            f"{pub_a} and {pub_b} are different outlets carrying what is "
            f"probably one feed; different bylines, one origin")
    if role_a and role_b and role_a != role_b and (
            _ORIGINATING & {role_a, role_b}):
        return INDEPENDENT, (
            f"{role_a} and {role_b} are different kinds of witness, and at "
            f"least one of them originates the fact rather than relaying it")
    if overlap >= 0.8:
        return SAME_ORIGIN, "near-identical wording"
    if not (role_a and role_b):
        return UNKNOWN, "the corpus does not state what one of these is"
    return PARTIALLY_INDEPENDENT, (
        "different outlets and no evidence either originated the fact")


@dataclass(frozen=True)
class EventCorroboration:
    event_id: str
    subject: str
    accounts: int
    independent_accounts: int
    #: The dependency-aware count. Three rewrites of one release corroborate
    #: once, and this is the number that says so.
    effective_accounts: float
    source_roles: Tuple[str, ...]
    publishers: Tuple[str, ...]
    source_diversity: str
    dependency_classes: Dict[str, int]
    corroborated_fields: Tuple[str, ...]
    conflicting_fields: Tuple[str, ...]
    standing: str

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "event_id": self.event_id,
            "subject": self.subject, "accounts": self.accounts,
            "independent_accounts": self.independent_accounts,
            "effective_accounts": round(self.effective_accounts, 2),
            "source_roles": list(self.source_roles),
            "publishers": list(self.publishers),
            "source_diversity": self.source_diversity,
            "dependency_classes": dict(sorted(
                self.dependency_classes.items())),
            "corroborated_fields": list(self.corroborated_fields),
            "conflicting_fields": list(self.conflicting_fields),
            "standing": self.standing,
            "caution": ("corroboration raises how much this event is "
                        "believed to have happened; it never counts as a "
                        "later test of a belief the event opened"),
        }


# --- standing ---------------------------------------------------------------
SINGLE_ACCOUNT = "SINGLE_ACCOUNT"
DEPENDENT_ACCOUNTS = "DEPENDENT_ACCOUNTS"
CORROBORATED = "CORROBORATED"
CONFLICTED = "CONFLICTED"

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?%?")


def assess(event, rows: Sequence) -> EventCorroboration:
    """Weigh the accounts of one event against each other."""
    rows = list(rows)
    publishers = tuple(dict.fromkeys(publisher_of(r) for r in rows if
                                     publisher_of(r)))
    roles = tuple(dict.fromkeys(_field(r, "source_role") for r in rows))
    classes: Dict[str, int] = collections.Counter()
    contribution = 1.0 if rows else 0.0
    for index in range(len(rows)):
        for other in range(index + 1, len(rows)):
            kind, _why = classify(rows[index], rows[other])
            classes[kind] += 1
    # Each pair beyond the first account adds at most what its class allows.
    # Taking the BEST class per additional account keeps one dependent pair
    # from cancelling a genuinely independent one.
    for index in range(1, len(rows)):
        best = max((_CONTRIBUTION[classify(rows[index], rows[other])[0]]
                    for other in range(index)), default=0.0)
        contribution += best

    numbers = [set(_NUMBER.findall(_field(r, "fact"))) for r in rows]
    shared = set.intersection(*numbers) if numbers and all(numbers) else set()
    union = set().union(*numbers) if numbers else set()
    conflicting = tuple(sorted(union - shared)) if len(rows) > 1 else ()

    independent = len(set(roles) - {""})
    if len(rows) <= 1:
        standing, diversity = SINGLE_ACCOUNT, "NONE"
    elif contribution >= 2.0 and independent >= 2:
        standing, diversity = CORROBORATED, "INDEPENDENT_ROLES"
    elif conflicting and shared:
        standing, diversity = CONFLICTED, "CONFLICTING"
    else:
        standing, diversity = DEPENDENT_ACCOUNTS, "SAME_ORIGIN_OR_DERIVED"

    return EventCorroboration(
        event_id=_field(event, "event_id"),
        subject=_field(event, "subject"),
        accounts=len(rows), independent_accounts=independent,
        effective_accounts=contribution, source_roles=roles,
        publishers=publishers, source_diversity=diversity,
        dependency_classes=dict(classes),
        corroborated_fields=tuple(sorted(shared)),
        conflicting_fields=conflicting, standing=standing)


def resolves_expectation(corroboration: EventCorroboration) -> Tuple[bool, str]:
    """Always False. The function exists so the answer is written down.

    Kept as a callable rather than a comment because a comment cannot be
    asserted on, and this is the distinction the wave asked to make
    permanent.
    """
    return False, (
        "corroboration is several accounts of ONE occurrence, and an "
        "expectation is resolved by a LATER one. Counting "
        f"{corroboration.accounts} accounts of the opening event as tests of "
        f"the belief it opened is the self-test failure one level up")


def summarise(corroborations: Sequence[EventCorroboration]) -> dict:
    by_standing = collections.Counter(c.standing for c in corroborations)
    classes: Dict[str, int] = collections.Counter()
    for entry in corroborations:
        classes.update(entry.dependency_classes)
    multi = [c for c in corroborations if c.accounts > 1]
    return {
        "contract": CONTRACT,
        "events": len(corroborations),
        "multi_account_events": len(multi),
        "genuinely_corroborated": by_standing.get(CORROBORATED, 0),
        "dependent_only": by_standing.get(DEPENDENT_ACCOUNTS, 0),
        "conflicted": by_standing.get(CONFLICTED, 0),
        "by_standing": dict(by_standing),
        "dependency_classes": dict(sorted(classes.items())),
        "accounts_claimed": sum(c.accounts for c in multi),
        "accounts_effective": round(sum(c.effective_accounts for c in multi),
                                    2),
        "note": ("accounts_effective is what accounts_claimed becomes once "
                 "syndication is discounted; the gap between them is the "
                 "corpus's redundancy, and neither number tests a belief"),
    }

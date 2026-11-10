"""Who is asking, established by the caller and never by a document.

THE ATTACK THIS CLOSES
----------------------
`internal_state.readable(facts, for_company=...)` is a real permission wall:
it filters by owner, refuses an unnamed reader, and offers no function that
crosses companies. Its weakness is not in what it checks. It is in the TYPE of
what it checks — a bare string.

A bare string has no memory of where it came from. The engine reads filings,
press releases and competitor web pages, and every one of those contains
company names; `evidence_translation` extracts them, `subject_binding` matches
them, and any of those values is a `str` that fits `for_company=` perfectly.
The day a caller writes

    readable(facts, for_company=evidence.actor)

nothing raises, nothing logs, and a document has just chosen whose private
records to open. That is the whole class of indirect prompt injection, and it
does not need a language model to work — it needs a string to travel from an
untrusted parser into a trusted parameter, which is a single plausible line.

WHAT THIS ADDS
--------------
A `TenantScope` that cannot be built from evidence. It is constructible only
from a caller that names its own authority — a configured tenant, an operator
request, the synthetic demonstration company — and every construction records
which. External text has no constructor at all: `from_evidence` exists and
raises, so the path a future caller would reach for is a refusal with an
explanation rather than an absence they route around.

WHY A TYPE RATHER THAN A CHECK
------------------------------
A check has to be remembered at every call site. A type is remembered by the
signature. `permitted_facts` accepts nothing else, so the wall is enforced by
the thing that fails at import rather than by the thing that fails in review.

WHAT THIS IS NOT
----------------
Not multi-tenant infrastructure. There is one tenant on this branch and the
tenant unit is the company. This is the boundary that has to be right BEFORE a
second tenant exists, because retrofitting an identity type through call sites
written against strings is the migration nobody schedules.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Sequence, Tuple

CONTRACT = "tenant_scope.v1"


class ScopeRejected(ValueError):
    """An identity that did not come from an authority this engine trusts."""


class UntrustedScope(ScopeRejected):
    """An identity that came, directly or indirectly, from a document."""


# --- who established this identity ------------------------------------------
CONFIGURED = "CONFIGURED"      # a tenant in the engine's own configuration
OPERATOR = "OPERATOR"          # a human asked for this company by name
DEMONSTRATION = "DEMONSTRATION"  # the synthetic company, for demos and tests
AUTHORITIES = (CONFIGURED, OPERATOR, DEMONSTRATION)


@dataclass(frozen=True)
class TenantScope:
    """One company's identity, and the authority that established it.

    Frozen, and deliberately not constructible from a plain string by the
    normal route: the constructors below are the only ones that name an
    authority, and `authority` is required.
    """

    company_id: str
    authority: str

    def __post_init__(self) -> None:
        if not str(self.company_id).strip():
            raise ScopeRejected(
                "a scope with no company reads every company's records")
        if self.authority not in AUTHORITIES:
            raise ScopeRejected(
                f"unknown authority {self.authority!r}; an identity whose "
                "origin cannot be named is not one this engine will act on")

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, **dataclasses.asdict(self)}


def configured(company_id: str) -> TenantScope:
    """A tenant the engine is configured to serve."""
    return TenantScope(company_id=company_id, authority=CONFIGURED)


def operator(company_id: str) -> TenantScope:
    """A company a human named in a request."""
    return TenantScope(company_id=company_id, authority=OPERATOR)


def demonstration(company_id: str) -> TenantScope:
    """The synthetic company. Kept separate so a demo cannot pose as a tenant."""
    return TenantScope(company_id=company_id, authority=DEMONSTRATION)


def from_evidence(*args: Any, **kwargs: Any) -> TenantScope:
    """The constructor that refuses, and the reason it is written down.

    A company name lifted from a filing, a headline or a competitor's page is
    the highest-value thing an attacker can put in a document, because it is
    the parameter that decides whose private records are opened. This function
    exists so that the obvious line — "the evidence says which company, use
    that" — lands on a refusal that explains itself instead of on a missing
    helper somebody writes in thirty seconds.
    """
    raise UntrustedScope(
        "a company identity read out of evidence is chosen by whoever wrote "
        "the document. Private records are opened by an authority — a "
        "configured tenant, or an operator asking by name — never by the text "
        "being analysed. If a document names a company you want to analyse, "
        "that is a retrieval decision, not a permission decision")


def permitted_facts(facts: Sequence[Any], scope: TenantScope) -> Tuple[Any, ...]:
    """This scope's own internal facts. Nothing else, and no aggregate.

    Delegates the filtering to `internal_state.readable`, which already refuses
    an unnamed reader and has no cross-company path. What is added here is the
    TYPE: a caller holding only a string cannot reach this function, so the
    string has to pass through an authority first and be seen doing it.
    """
    if not isinstance(scope, TenantScope):
        raise UntrustedScope(
            f"permitted_facts needs a TenantScope, got "
            f"{type(scope).__name__}. A bare string has no memory of where it "
            "came from, and the values this engine has most of are company "
            "names parsed out of documents")
    from . import internal_state as IS

    return IS.readable(facts, for_company=scope.company_id)


def assert_same_scope(scope: TenantScope, *records: Any,
                      field: str = "company_id") -> None:
    """Refuse a set of records that does not all belong to this scope.

    The join is where cross-tenant contamination actually happens: not by
    reading another company's file, but by combining one company's private
    figure with another's analysis and rendering the result as one finding.
    """
    strangers = sorted({
        str(getattr(r, field, "") or (r.get(field) if isinstance(r, dict)
                                      else ""))
        for r in records
    } - {scope.company_id, ""})
    if strangers:
        raise ScopeRejected(
            f"records for {', '.join(strangers)} reached a computation scoped "
            f"to {scope.company_id}; a figure that crosses companies is a leak "
            "whether or not anybody reads it")

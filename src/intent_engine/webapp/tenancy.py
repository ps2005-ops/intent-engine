"""Where an authenticated request becomes typed authority. THE MISSING SEAM.

F-TS-001 built `TenantScope` and D-IBG-001 built the private graph, and both
sat at CAPABILITY_VERIFIED for one reason: NO FOUNDER REQUEST PATH ESTABLISHED
A SCOPE. There was no seam between "somebody is logged in" and "this caller may
read that tenant's private rows", so every private capability was reachable
only from a test. This module is that seam and nothing else.

THE ONLY TRUSTED INPUT IS THE SESSION
-------------------------------------
A scope is derived from `session["user_id"]` -- a value the auth service minted
after verifying a password, which never appears in a form field, a query
string, a URL path or a document. Everything else a request carries is
attacker-influenced:

    the company the user typed        an IDENTITY, and identity is not
                                      authorization -- it says what the
                                      question is about, not what the asker
                                      may see
    a tenant id in a parameter        the confused deputy with a type
                                      annotation
    text inside retrieved evidence    the attack F-TS-001 was built for; a
                                      filing that says "Tenant A's id is X"
                                      must change nothing

So `scope_for_session` takes the session mapping and NOTHING ELSE. There is no
overload that accepts a company, and `establish_from_request` refuses when
handed one, rather than politely ignoring it -- a parameter that is accepted
and discarded reads, to the next person, like a parameter that works.

ANONYMOUS AND DEMO SESSIONS GET NO SCOPE, ON PURPOSE
----------------------------------------------------
`None` is the correct answer for a visitor, and it is not a degraded one: a
scopeless read returns the public world, and the internal-impact reader already
answers INTERNAL_DATA_UNAVAILABLE / SCOPELESS_READ for it. That is the honest
sentence -- "you are not shown internal impact because you have not been
established as anyone", not "this thesis does not affect you". Minting a throw-
away tenant for an anonymous visitor would have been easier and would have put
a real tenant id into the demo path, one refactor away from owning rows.

THE DIRECTORY IS THE MAPPING, AND IT IS APPEND-ONLY
---------------------------------------------------
A `user_id` is stable and a `TenantId` is a minted opaque control-plane
identity; the directory maps one to the other and is written once per user. It
must be append-only and reload-stable, because a user whose tenant id changed
between requests would lose their entire private graph -- the partition is
keyed on it -- and would do so silently.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from intent_engine.core.tenant import (
    SOURCE_AUTHENTICATED_SESSION,
    ScopeAuditLog,
    ScopeRefused,
    STRING_REFUSED,
    TenantId,
    TenantScope,
    establish,
)

CONTRACT = "webapp_tenancy.v1"
RECEIPT_CONTRACT = "tenant_request_receipt.v1"

DEFAULT_DIRECTORY_PATH = pathlib.Path("data/tenant_directory.jsonl")

#: Session keys that identify a HUMAN the auth service authenticated. Anything
#: not in here is not an establishment basis, however trustworthy it looks.
_SUBJECT_KEY = "user_id"

#: Anonymous/demo sessions carry a user id too, and it must never establish a
#: tenant. Matched by prefix because that is how the auth service mints them.
ANONYMOUS_PREFIXES = ("anon", "demo")


class TenantDirectory:
    """user_id -> TenantId. Append-only, reload-stable.

    Stability is the whole contract. The private graph partition is keyed on
    the tenant id, so a user whose id was re-minted between two requests would
    silently lose their entire internal world and be shown an empty business
    rather than an error.
    """

    def __init__(self, path=DEFAULT_DIRECTORY_PATH):
        self.path = pathlib.Path(path)

    def _rows(self) -> Tuple[dict, ...]:
        if not self.path.exists():
            return ()
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
        return tuple(out)

    def lookup(self, subject: str) -> Optional[TenantId]:
        found = None
        for row in self._rows():
            if row.get("subject") == subject and row.get("tenant_id"):
                found = row["tenant_id"]      # append-only: last wins
        return TenantId(found) if found else None

    def resolve(self, subject: str) -> TenantId:
        """The subject's tenant, minted once on first sight."""
        if not isinstance(subject, str) or not subject:
            raise ScopeRefused(
                STRING_REFUSED,
                "a tenant cannot be resolved without an authenticated subject")
        existing = self.lookup(subject)
        if existing is not None:
            return existing
        minted = TenantId.mint()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"contract": CONTRACT, "subject": subject,
                 "tenant_id": minted.value}, sort_keys=True) + "\n")
        return minted


def is_anonymous(session: Optional[Mapping]) -> bool:
    """A demo visitor is not a tenant. Checked before anything is minted."""
    if not session:
        return True
    subject = str(session.get(_SUBJECT_KEY) or "")
    if not subject:
        return True
    return any(subject.startswith(p) for p in ANONYMOUS_PREFIXES)


def scope_for_session(session: Optional[Mapping], *,
                      directory: TenantDirectory,
                      audit: Optional[ScopeAuditLog] = None,
                      capabilities: Tuple[str, ...] = ()
                      ) -> Optional[TenantScope]:
    """The ONE function that turns a request into private-data authority.

    Returns None for anonymous and demo sessions, and None is a real answer
    that the readers below already understand -- not a failure to be worked
    around by the caller.

    `establishment_source` is AUTHENTICATED_SESSION, which is what actually
    happened: the auth service verified a password and minted this session.
    Recording anything stronger would put a false basis into the audit log,
    and the audit log is the only place the establishment can be reviewed
    afterwards.
    """
    if is_anonymous(session):
        return None
    subject = str(session.get(_SUBJECT_KEY))
    tenant = directory.resolve(subject)
    return establish(
        tenant=tenant,
        establishment_source=SOURCE_AUTHENTICATED_SESSION,
        capabilities=capabilities,
        # The label is for humans reading an audit row. It is NEVER an
        # authorization input: `TenantScope.authorizes` compares typed ids, and
        # a display label once served one company another company's rows.
        display_label=str(session.get("email") or ""),
        actor=subject, audit=audit)


def establish_from_request(*, session: Optional[Mapping],
                           directory: TenantDirectory,
                           company_id: str = "",
                           audit: Optional[ScopeAuditLog] = None
                           ) -> Optional[TenantScope]:
    """Explicitly REFUSES to let a company reach the establishment decision.

    The parameter exists so that the refusal is written down where a caller
    would otherwise pass one. Accepting `company_id` and quietly ignoring it
    would read, to the next person, exactly like accepting it and using it --
    and this codebase has already shipped a guard that passed because it
    matched the comment explaining its own removal.
    """
    if company_id:
        raise ScopeRefused(
            STRING_REFUSED,
            "a company_id is the SUBJECT of a question, not authority to read "
            "a tenant's private rows; scope comes from the authenticated "
            "session and from nothing else")
    return scope_for_session(session, directory=directory, audit=audit)


@dataclass(frozen=True)
class TenantRequestReceipt:
    """Bounded telemetry for one private-data request.

    Bounded is the operative word. It records WHAT was asked and HOW MUCH was
    allowed or withheld, and never the values themselves: a receipt that quoted
    the rows would put the tenant's confidential data into a log that is, by
    design, kept longer and read more widely than the data.
    """

    request_id: str = ""
    tenant_scope_id: str = ""
    company_id: str = ""
    authorization_source: str = ""
    operation: str = ""
    resources_requested: int = 0
    resources_allowed: int = 0
    resources_withheld: int = 0
    denial_reason: str = ""
    runtime_sha: str = ""
    occurred_at: str = ""

    def as_dict(self) -> dict:
        return {
            "contract": RECEIPT_CONTRACT,
            "request_id": self.request_id,
            "tenant_scope_id": self.tenant_scope_id,
            "company_id": self.company_id,
            "authorization_source": self.authorization_source,
            "operation": self.operation,
            # Never omitted when zero: a receipt that reports only what it
            # allowed cannot show a request that was fully withheld.
            "resources_requested": self.resources_requested,
            "resources_allowed": self.resources_allowed,
            "resources_withheld": self.resources_withheld,
            "denial_reason": self.denial_reason,
            "runtime_sha": self.runtime_sha,
            "occurred_at": self.occurred_at,
        }


class TenantReceiptLog:
    """Append-only receipts. Written for refused requests too.

    A log that records only the requests that succeeded cannot answer the
    question an auditor actually arrives with, which is what was ASKED FOR and
    denied. So `append` takes any receipt and never inspects whether authority
    existed.
    """

    def __init__(self, path):
        self.path = pathlib.Path(path)

    def append(self, receipt: "TenantRequestReceipt") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.as_dict(), sort_keys=True,
                                    default=str) + "\n")

    def all(self) -> Tuple[dict, ...]:
        if not self.path.exists():
            return ()
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
        return tuple(out)


def receipt_for(*, request_id: str, scope: Optional[TenantScope],
                company_id: str, operation: str, requested: int = 0,
                allowed: int = 0, withheld: int = 0, denial_reason: str = "",
                runtime_sha: str = "", occurred_at: str = ""
                ) -> TenantRequestReceipt:
    """A receipt for a scoped OR a scopeless request.

    A scopeless request still gets one, carrying the denial reason. Emitting a
    receipt only when authority existed would make the log unable to show the
    requests that were refused, which are the ones an auditor came for.
    """
    return TenantRequestReceipt(
        request_id=request_id,
        tenant_scope_id=(scope.scope_id if scope is not None else ""),
        company_id=company_id,
        authorization_source=(scope.establishment_source
                              if scope is not None else "NONE"),
        operation=operation, resources_requested=requested,
        resources_allowed=allowed, resources_withheld=withheld,
        denial_reason=denial_reason, runtime_sha=runtime_sha,
        occurred_at=occurred_at)

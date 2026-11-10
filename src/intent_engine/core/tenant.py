"""Tenant authority — a scope is ISSUED by a trusted context, never inferred.

WHY THIS EXISTS
---------------
Every private capability in V5 is an authorization decision. Today the product
carries tenant identity the way it carries everything else: as a string that
came from somewhere. A string that came from somewhere is exactly the shape of
a confused deputy — the system cannot tell the difference between "the signed-in
enterprise is Acme" and "a page we scraped said the word Acme", so it will
eventually act on the second as if it were the first.

The whole design here is one sentence: **authority is a type, and the type can
only be minted from a trusted context.** A scraped company name cannot become an
authorization subject because it cannot become a `TenantId` — the identity space
(`tnt_` + ULID) is disjoint from the name space, so there is no string a
document can contain that is also a tenant identity.

WHAT IS DELIBERATELY ABSENT
---------------------------
There is no `from_evidence`, no `from_company_name`, no `resolve(name)`, and
there never will be. This is not a naming convention — `tests/test_tenant_scope.py`
asserts the EXACT attribute set of `TenantScope` and the exact public surface of
this module, so any added constructor fails the suite whatever it is called.
A grep-based guard was considered and rejected: this program has already shipped
a structural guard that matched the comment explaining a removal, so it passed
while the thing existed. A guard must read the class, not the prose.

There is also no name-based lookup. The real incident this prevents: the alias
"Linear" was satisfied by "Linear Minerals Corp." Substring, prefix and alias
matching are not weakened here, they are absent — `display_label` exists for
humans, is excluded from equality, from the cache key and from the storage
partition, and `authorizes()` compares only the opaque id.

THE THREE FAILURE STATES ARE A VOCABULARY, NOT A MESSAGE
--------------------------------------------------------
    NO_ESTABLISHMENT_SOURCE  nobody trusted said this scope should exist
    STRING_REFUSED           an untyped identity was offered where a typed one
                             is required (a bare string is the canonical case)
    EXPIRED                  the scope was real and is no longer

`authorizes()` on an expired scope RAISES rather than returning False, because a
False there reads as "different tenant" and sends the next reader looking for
the wrong bug.

EMPTY STATE
-----------
`visible_rows()` with no scope returns PUBLIC rows only, and says so. It never
silently returns private rows, and it never silently returns *nothing* either:
`ScopedRead` separates "no rows exist" from "rows exist and were withheld" from
"rows exist and were refused for being untagged". MISSING is not ZERO, and an
untagged row is neither public nor private — it is refused and counted.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
from dataclasses import dataclass, field, fields as dataclass_fields
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Mapping, Optional, Sequence, Tuple

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.core.decision_ids import is_ulid, new_ulid

__all__ = [
    # contract + vocabulary
    "TENANT_SCOPE_CONTRACT",
    "TENANT_ID_PREFIX",
    "NO_ESTABLISHMENT_SOURCE",
    "STRING_REFUSED",
    "EXPIRED",
    "FAILURE_STATES",
    "SOURCE_AUTHENTICATED_SESSION",
    "SOURCE_SIGNED_SERVICE_TOKEN",
    "SOURCE_OPERATOR_GRANT",
    "SOURCE_SYNTHETIC_FIXTURE",
    "TRUSTED_ESTABLISHMENT_SOURCES",
    "NEVER_TRUSTED_SOURCES",
    "PUBLIC",
    "TENANT_PRIVATE",
    "VISIBILITIES",
    "SCOPED",
    "SCOPELESS_PUBLIC_ONLY",
    "EMPTY_NO_ROWS",
    "EMPTY_PRIVATE_WITHHELD",
    "EMPTY_UNTAGGED_REFUSED",
    "NON_EMPTY",
    "DEFAULT_SCOPE_AUDIT_PATH",
    # types
    "ScopeRefused",
    "TenantId",
    "TenantScope",
    "ScopedRead",
    "ScopeAuditEvent",
    "ScopeAuditLog",
    "SeamRegistry",
    "TenantScoped",
    # the only entry point, plus the shared reader and the seams
    "establish",
    "coerce_scope",
    "visible_rows",
    "export_partition",
    "partition_path",
    "scope_cache_key",
    "requires_tenant_scope",
    "SECURITY_SEAMS",
    # the guards other nodes are expected to reuse
    "scope_producers",
    "assert_no_evidence_constructors",
]

TENANT_SCOPE_CONTRACT = "tenant_scope.v1"

# --- the failure vocabulary --------------------------------------------------
NO_ESTABLISHMENT_SOURCE = "NO_ESTABLISHMENT_SOURCE"
STRING_REFUSED = "STRING_REFUSED"
EXPIRED = "EXPIRED"
FAILURE_STATES = frozenset({NO_ESTABLISHMENT_SOURCE, STRING_REFUSED, EXPIRED})

# --- who is allowed to establish authority -----------------------------------
# The list is short on purpose. Each entry is a context that already
# authenticated a principal; none of them can be produced by content the system
# merely READ. Growing this list is a security decision, not an integration
# detail, and the suite asserts the exact membership.
SOURCE_AUTHENTICATED_SESSION = "authenticated_session"
SOURCE_SIGNED_SERVICE_TOKEN = "signed_service_token"
SOURCE_OPERATOR_GRANT = "operator_grant"
#: Synthetic tenants (D-SYN-001) are real authority over fake data. They are
#: trusted to establish a scope and are tagged so a projection can never count
#: their rows as a customer's.
SOURCE_SYNTHETIC_FIXTURE = "synthetic_fixture"
TRUSTED_ESTABLISHMENT_SOURCES = frozenset({
    SOURCE_AUTHENTICATED_SESSION, SOURCE_SIGNED_SERVICE_TOKEN,
    SOURCE_OPERATOR_GRANT, SOURCE_SYNTHETIC_FIXTURE,
})

#: Named so the refusal is legible in an audit row rather than appearing as a
#: generic "unknown source". Every one of these is a thing the system read, and
#: a thing the system read has no authority over the system. This tuple is
#: documentation and telemetry — the actual rule is the allowlist above, so a
#: source nobody thought to name here is still refused.
NEVER_TRUSTED_SOURCES = (
    "evidence", "scraped_page", "web_page", "document", "filing",
    "model_output", "llm", "company_name", "user_supplied_text", "prompt",
)

# --- visibility and read states ----------------------------------------------
PUBLIC = "public"
TENANT_PRIVATE = "tenant_private"
VISIBILITIES = frozenset({PUBLIC, TENANT_PRIVATE})

SCOPED = "SCOPED"
SCOPELESS_PUBLIC_ONLY = "SCOPELESS_PUBLIC_ONLY"

# The four things an empty result can mean. Collapsing them is how a system
# tells a customer "you have no internal data" when the truth is "you have no
# permission" or "your rows arrived untagged".
EMPTY_NO_ROWS = "NO_ROWS_EXIST"
EMPTY_PRIVATE_WITHHELD = "PRIVATE_WITHHELD"
EMPTY_UNTAGGED_REFUSED = "UNTAGGED_REFUSED"
NON_EMPTY = "NON_EMPTY"

#: Same convention as prediction_ledger / decision_record: the one real store
#: lives under data/ (git-ignored); tests always pass a tmp path.
DEFAULT_SCOPE_AUDIT_PATH = Path("data/tenant_scope_audit.jsonl")

TENANT_ID_PREFIX = "tnt_"
_TENANT_ID_RE = re.compile(r"^tnt_[0-9A-HJKMNP-TV-Z]{26}$")


class ScopeRefused(Exception):
    """Authority was asked for and not granted.

    Deliberately NOT a ValueError. Refusals here travel through code that
    parses rows and coerces types, and a `except ValueError` written for a bad
    integer would swallow an authorization failure and continue. This program
    has already lost a run to a bare except that kept a broken step COMPLETE.
    """

    def __init__(self, failure_state: str, message: str):
        if failure_state not in FAILURE_STATES:
            raise AssertionError(
                f"{failure_state!r} is not one of the named failure states "
                f"{sorted(FAILURE_STATES)}; a refusal without a state cannot "
                f"be counted in telemetry")
        super().__init__(f"{failure_state}: {message}")
        self.failure_state = failure_state
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_iso(value: str, *, what: str) -> datetime:
    """Strict, timezone-aware only.

    A naive timestamp is refused rather than assumed UTC: an expiry that is
    wrong by the reader's offset expires early or, worse, late.
    """
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (ValueError, TypeError) as exc:
        raise ScopeRefused(
            NO_ESTABLISHMENT_SOURCE,
            f"{what} {value!r} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ScopeRefused(
            NO_ESTABLISHMENT_SOURCE,
            f"{what} {value!r} has no timezone; an expiry without an offset "
            f"expires at a different instant for every reader")
    return parsed


# =============================================================================
# TenantId — the identity space is disjoint from the name space
# =============================================================================
@dataclass(frozen=True)
class TenantId:
    """An opaque tenant identifier issued by the control plane.

    `tnt_` + a 26-char Crockford-base32 ULID. The format is the security
    property, not a style choice:

      * no company name, alias, domain or free-text string can satisfy it, so
        scraped content can never become an authorization subject;
      * the alphabet excludes I, L, O and U, and lowercase is REFUSED rather
        than normalized — normalizing would create two spellings of one
        authority, which is an id collision with extra steps;
      * `/`, `.` and `..` are outside the alphabet, so a tenant id can never
        become a path traversal when it is used to partition storage.

    Equality is exact on the opaque value. There is no fuzzy match, no prefix
    match and no alias table, because "Linear" once matched "Linear Minerals
    Corp." and authorized the wrong company.
    """

    value: str = ""

    def __post_init__(self):
        if isinstance(self.value, TenantId):  # pragma: no cover - defensive
            raise ScopeRefused(STRING_REFUSED, "TenantId is not re-wrappable")
        if not isinstance(self.value, str):
            raise ScopeRefused(
                STRING_REFUSED,
                f"a tenant id must be a control-plane identifier, got "
                f"{type(self.value).__name__}")
        if not _TENANT_ID_RE.match(self.value):
            raise ScopeRefused(
                STRING_REFUSED,
                f"{self.value!r} is not a tenant identity; a tenant id is "
                f"{TENANT_ID_PREFIX!r} + a 26-char uppercase Crockford ULID "
                f"issued by the control plane. Names, domains and anything "
                f"read from a document are refused here by construction.")

    @classmethod
    def mint(cls) -> "TenantId":
        """Issue a new identity. The control plane calls this; nothing that
        parses external content ever does."""
        return cls(TENANT_ID_PREFIX + new_ulid())

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# =============================================================================
# TenantScope
# =============================================================================
#: Handed to `TenantScope.__init__` by `establish()` and by `from_row()`, which
#: are the only two ways a scope may come into existence. Direct construction
#: reaches `__post_init__` without it and is refused, so there is no path to a
#: scope that skipped the audit row.
_ESTABLISHED = object()


@dataclass(frozen=True)
class TenantScope:
    """Authority to see one tenant's private world, and where it came from.

    Frozen because a scope that can be re-pointed mid-request is a confused
    deputy with a mutation operator. Every field has a default so that any
    partial or hostile construction lands in `__post_init__` and is refused
    with a NAMED failure state, rather than raising a bare TypeError that
    telemetry cannot count.
    """

    tenant: Optional[TenantId] = None
    establishment_source: str = ""
    issued_at: str = ""
    expires_at: Optional[str] = None
    #: What this scope may do. An EMPTY tuple grants nothing; it is not
    #: "unrestricted". A row that omits the key entirely is refused rather
    #: than defaulted, because absent and empty are different claims.
    capabilities: Tuple[str, ...] = ()
    #: For humans only. Excluded from equality, from `scope_cache_key` and
    #: from `partition_path`, and never consulted by `authorizes`.
    display_label: str = field(default="", compare=False)
    scope_id: str = ""
    _established_by: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        # Order matters: the identity check runs first so that the canonical
        # attack -- TenantScope("acme") -- reports STRING_REFUSED and not a
        # confusing complaint about a missing establishment source.
        if self.tenant is None:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "a scope with no tenant identity is not a scope")
        if not isinstance(self.tenant, TenantId):
            kind = type(self.tenant).__name__
            raise ScopeRefused(
                STRING_REFUSED,
                f"tenant identity must be a TenantId, got {kind}. A bare "
                f"string is refused here on purpose: it is the shape a "
                f"scraped company name arrives in.")
        if self._established_by is not _ESTABLISHED:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "TenantScope cannot be constructed directly; establish() is "
                "the only entry point and it is the thing that writes the "
                "audit row. A scope with no audit row is unaccountable "
                "authority.")
        if self.establishment_source not in TRUSTED_ESTABLISHMENT_SOURCES:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                f"{self.establishment_source!r} cannot establish authority; "
                f"trusted sources are "
                f"{sorted(TRUSTED_ESTABLISHMENT_SOURCES)}")
        _parse_iso(self.issued_at, what="issued_at")
        if self.expires_at is not None:
            _parse_iso(self.expires_at, what="expires_at")
        if not is_ulid(self.scope_id):
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                f"scope_id {self.scope_id!r} is not a ULID; an establishment "
                f"that cannot be named cannot be audited")
        if isinstance(self.capabilities, (str, bytes)):
            raise ScopeRefused(
                STRING_REFUSED,
                "capabilities must be a sequence of capability names, not a "
                "string (a string would iterate as characters)")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))

    # --- authorization -------------------------------------------------------
    def authorizes(self, tenant: TenantId) -> bool:
        """Exact identity match. Raises on an expired scope.

        Returning False for an expiry would be indistinguishable from "this is
        someone else's data" and would send the next reader to the wrong file.
        """
        if not isinstance(tenant, TenantId):
            raise ScopeRefused(
                STRING_REFUSED,
                f"authorizes() compares typed identities; got "
                f"{type(tenant).__name__}. Comparing against a name is the "
                f"alias-collision bug, not a convenience.")
        self.assert_live()
        return self.tenant == tenant

    def permits(self, capability: str) -> bool:
        """Deny by default. An empty capability tuple permits nothing."""
        return capability in self.capabilities

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        moment = now if now is not None else _now()
        if moment.tzinfo is None:
            raise ScopeRefused(
                EXPIRED,
                "expiry cannot be evaluated against a naive clock")
        return _parse_iso(self.expires_at, what="expires_at") <= moment

    def assert_live(self, now: Optional[datetime] = None) -> None:
        if self.is_expired(now):
            raise ScopeRefused(
                EXPIRED,
                f"scope {self.scope_id} for {self.tenant.value} expired at "
                f"{self.expires_at}")

    # --- persistence ---------------------------------------------------------
    def as_row(self) -> dict:
        """The persisted shape. Carries the establishment source, because a
        scope that reloads without one reloads as unaccountable authority."""
        return {
            "contract": TENANT_SCOPE_CONTRACT,
            "scope_id": self.scope_id,
            "tenant_id": self.tenant.value,
            "establishment_source": self.establishment_source,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "capabilities": list(self.capabilities),
            "display_label": self.display_label,
        }

    @classmethod
    def from_row(cls, row: Mapping) -> "TenantScope":
        """Reload. Required keys are required — a missing one is refused, not
        defaulted, because a defaulted authority field is an invented one."""
        if not isinstance(row, Mapping):
            state = (STRING_REFUSED if isinstance(row, (str, bytes))
                     else NO_ESTABLISHMENT_SOURCE)
            raise ScopeRefused(
                state,
                f"a persisted scope is a mapping, got {type(row).__name__}")
        contract = row.get("contract")
        if contract != TENANT_SCOPE_CONTRACT:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                f"row declares contract {contract!r}, this reader is "
                f"{TENANT_SCOPE_CONTRACT!r}; a scope is never silently "
                f"upgraded across versions")
        for key in ("scope_id", "tenant_id", "establishment_source",
                    "issued_at", "capabilities"):
            if key not in row:
                raise ScopeRefused(
                    NO_ESTABLISHMENT_SOURCE,
                    f"persisted scope is missing required key {key!r}; "
                    f"missing is not empty")
            if row[key] is None:
                raise ScopeRefused(
                    NO_ESTABLISHMENT_SOURCE,
                    f"persisted scope has an explicit null for required key "
                    f"{key!r}; null is not empty")
        return cls(
            tenant=TenantId(row["tenant_id"]),
            establishment_source=row["establishment_source"],
            issued_at=row["issued_at"],
            # Optional: absent and explicit null both mean "does not expire".
            expires_at=row.get("expires_at"),
            capabilities=tuple(row["capabilities"]),
            display_label=row.get("display_label", ""),
            scope_id=row["scope_id"],
            _established_by=_ESTABLISHED,
        )


# =============================================================================
# The shared reader — one coercion, three shapes
# =============================================================================
#: Every attribute a transported scope must carry. Read from a mapping as keys
#: and from an object as attributes, by ONE function, so a producer and a
#: consumer cannot drift into two readers that disagree.
_ROW_KEYS = ("contract", "scope_id", "tenant_id", "establishment_source",
             "issued_at", "capabilities")


def coerce_scope(obj) -> TenantScope:
    """Accept the live object, the persisted row, or a transported DTO.

    Mappings are read as mappings BEFORE anything is read as an object: a
    getattr-only reader silently folds a dict into a single garbage record,
    which is how a ledger of many events once read as one.

    A `str` is always refused and never parsed, even if it happens to contain
    valid JSON. Decoding a transport is the transport's job; if this function
    parsed strings, the one thing it exists to refuse would have a bypass.
    """
    if isinstance(obj, TenantScope):
        return obj
    if isinstance(obj, (str, bytes)):
        raise ScopeRefused(
            STRING_REFUSED,
            "a scope cannot be reconstituted from a string; decode the "
            "transport first and pass the row")
    if isinstance(obj, Mapping):
        return TenantScope.from_row(obj)
    if all(hasattr(obj, key) for key in _ROW_KEYS):
        row = {key: getattr(obj, key) for key in _ROW_KEYS}
        for optional in ("expires_at", "display_label"):
            if hasattr(obj, optional):
                row[optional] = getattr(obj, optional)
        return TenantScope.from_row(row)
    raise ScopeRefused(
        NO_ESTABLISHMENT_SOURCE,
        f"{type(obj).__name__} carries no scope; required fields are "
        f"{list(_ROW_KEYS)}")


# =============================================================================
# The audit log — establishment is persisted, refusals included
# =============================================================================
@dataclass(frozen=True)
class ScopeAuditEvent:
    """One establishment attempt. Refusals are rows too.

    Telemetry needs "scopes by source" AND "refusals by state"; a log that only
    records successes can never show that an attack was turned away, and a
    metric with no negative control is not a metric.
    """

    event_id: str
    event_type: str          # scope.established | scope.refused
    occurred_at: str
    tenant_id: str           # "" when the identity itself was refused
    establishment_source: str
    scope_id: str = ""
    failure_state: str = ""
    detail: str = ""
    actor: str = ""
    idempotency_key: str = ""

    EVENT_TYPES = ("scope.established", "scope.refused")

    @property
    def subject_id(self) -> str:
        return self.scope_id or self.event_id

    def validate(self) -> None:
        if self.event_type not in self.EVENT_TYPES:
            raise ValueError(f"unknown scope audit event {self.event_type!r}")
        if not self.event_id or not self.occurred_at:
            raise ValueError("a scope audit row needs an id and a timestamp")
        if self.event_type == "scope.refused" and not self.failure_state:
            raise ValueError(
                "a refusal with no failure state cannot be counted")
        if self.failure_state and self.failure_state not in FAILURE_STATES:
            raise ValueError(
                f"{self.failure_state!r} is not a named failure state")

    def content_fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in dataclass_fields(self)}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "ScopeAuditEvent":
        data = json.loads(line)
        known = {f.name for f in dataclass_fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"scope audit row carries unknown fields {sorted(unknown)}")
        row = cls(**data)
        row.validate()
        return row


class ScopeAuditLog(AppendOnlyStore):
    """Append-only, fsynced, flocked — inherited from the one store."""

    event_cls = ScopeAuditEvent
    record_error = ValueError
    corrupt_error = CorruptLogError

    def for_tenant(self, tenant: TenantId) -> list:
        if not isinstance(tenant, TenantId):
            raise ScopeRefused(
                STRING_REFUSED,
                "the audit log is queried by typed identity, not by name")
        return [row for row in self.read_all() if row.tenant_id == tenant.value]

    def refusals(self) -> list:
        return [r for r in self.read_all() if r.event_type == "scope.refused"]


def _default_audit_log() -> ScopeAuditLog:
    return ScopeAuditLog(
        os.environ.get("INTENT_ENGINE_SCOPE_AUDIT", DEFAULT_SCOPE_AUDIT_PATH))


# =============================================================================
# establish() — the only entry point
# =============================================================================
def establish(*, tenant: TenantId, establishment_source: str,
              issued_at: Optional[str] = None,
              expires_at: Optional[str] = None,
              capabilities: Sequence[str] = (),
              display_label: str = "",
              actor: str = "",
              audit: Optional[ScopeAuditLog] = None) -> TenantScope:
    """Issue a scope from a trusted context and record that it happened.

    Keyword-only on purpose. `establish("acme", "evidence")` is a sentence a
    caller can write by accident; `establish(tenant=..., ...)` is not.

    Every refusal is audited before it is raised, so an attack shows up in the
    log as a refusal row rather than as an absence.
    """
    log = audit if audit is not None else _default_audit_log()

    def _refuse(state: str, detail: str, tenant_value: str = ""):
        log.append(ScopeAuditEvent(
            event_id=new_ulid(), event_type="scope.refused",
            occurred_at=_now_iso(), tenant_id=tenant_value,
            establishment_source=str(establishment_source),
            failure_state=state, detail=detail, actor=actor))
        raise ScopeRefused(state, detail)

    if not isinstance(tenant, TenantId):
        kind = type(tenant).__name__
        _refuse(STRING_REFUSED,
                f"establish() requires a TenantId, got {kind}. There is no "
                f"constructor from a name, a domain or any evidence.")
    if establishment_source not in TRUSTED_ESTABLISHMENT_SOURCES:
        _refuse(NO_ESTABLISHMENT_SOURCE,
                f"{establishment_source!r} cannot establish authority; "
                f"trusted sources are {sorted(TRUSTED_ESTABLISHMENT_SOURCES)}",
                tenant.value)

    scope = TenantScope(
        tenant=tenant,
        establishment_source=establishment_source,
        issued_at=issued_at or _now_iso(),
        expires_at=expires_at,
        capabilities=tuple(capabilities),
        display_label=display_label,
        scope_id=new_ulid(),
        _established_by=_ESTABLISHED,
    )
    log.append(ScopeAuditEvent(
        event_id=new_ulid(), event_type="scope.established",
        occurred_at=_now_iso(), tenant_id=scope.tenant.value,
        establishment_source=scope.establishment_source,
        scope_id=scope.scope_id, actor=actor,
        detail=f"capabilities={list(scope.capabilities)}"))
    return scope


# =============================================================================
# The security seam
# =============================================================================
class TenantScoped:
    """Protocol marker: this object carries the authority it acts under.

    A plain class rather than typing.Protocol so that `isinstance` means
    "declared itself scoped", not "happens to have an attribute named scope".
    Structural typing is the alias-collision bug in another costume.
    """

    scope: TenantScope


class SeamRegistry:
    """Every security-sensitive seam in the process, and whether it refuses.

    The registry exists so the guard can be a property of the SYSTEM rather
    than a test somebody remembers to write next to each new seam. A seam that
    is registered without the decorator is reported as a violation without
    being called — auditing an unprotected seam by invoking it is exactly the
    thing the audit is trying to prevent.
    """

    def __init__(self):
        self._seams = []

    def register(self, fn):
        self._seams.append(fn)
        return fn

    def discard(self, fn) -> None:
        """Test support: unregister a deliberately-wrong seam. Production
        never calls this — a seam does not stop being a seam."""
        self._seams = [s for s in self._seams if s is not fn]

    def __iter__(self):
        return iter(tuple(self._seams))

    def __len__(self) -> int:
        return len(self._seams)

    def audit(self, seams=None) -> Tuple[str, ...]:
        """Return the seams a bare string can reach. Empty tuple is the pass.

        `seams` is injectable so a test can prove the audit reports a
        violation when one exists — an audit that has never returned a
        non-empty result is an untested audit.
        """
        violations = []
        for fn in (self._seams if seams is None else list(seams)):
            name = getattr(fn, "__qualname__", repr(fn))
            if not getattr(fn, "__tenant_seam__", False):
                violations.append(
                    f"{name}: registered as a security seam but not wrapped "
                    f"by @requires_tenant_scope")
                continue
            probe = _probe_kwargs(fn)
            if probe is None:
                violations.append(
                    f"{name}: has positional-only parameters, so the guard "
                    f"cannot probe it; a seam that cannot be audited is not "
                    f"a guarded seam")
                continue
            try:
                fn(**probe)
            except ScopeRefused as exc:
                if exc.failure_state != STRING_REFUSED:
                    violations.append(
                        f"{name}: refused a bare string with "
                        f"{exc.failure_state}, expected {STRING_REFUSED}")
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                violations.append(
                    f"{name}: a bare string raised "
                    f"{type(exc).__name__}({exc}) instead of ScopeRefused")
            else:
                violations.append(
                    f"{name}: ACCEPTED a bare string as a tenant scope")
        return tuple(violations)


def _probe_kwargs(fn):
    """The call the guard uses to prove a seam refuses a bare string.

    Everything is passed BY KEYWORD. Passing placeholders positionally looks
    simpler and is wrong: a seam declared `f(scope, rows)` would receive the
    placeholder as `scope` and then `scope=` again, and the resulting TypeError
    would be reported as a violation of a seam that is in fact correct — a
    guard that cries wolf gets disabled.

    Returns None when the seam has positional-only parameters, which cannot be
    supplied by keyword; the caller reports that as its own violation rather
    than skipping the seam silently.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return {"scope": "acme"}
    probe = {}
    for param in sig.parameters.values():
        if param.kind is param.POSITIONAL_ONLY:
            return None
        if param.name == "scope" or param.kind in (param.VAR_POSITIONAL,
                                                   param.VAR_KEYWORD):
            continue
        if param.default is param.empty:
            probe[param.name] = None
    probe["scope"] = "acme"
    return probe


SECURITY_SEAMS = SeamRegistry()


def requires_tenant_scope(fn):
    """Mark a function a security-sensitive seam and enforce the type at it.

    Enforcement is at the seam, not at the caller. Every caller getting it
    right is a hope; the seam refusing is a property. A bare string never
    reaches the body — it is refused during the bind, which is also what makes
    `SeamRegistry.audit` safe to run against production seams.
    """
    sig = inspect.signature(fn)
    if "scope" not in sig.parameters:
        raise TypeError(
            f"{fn.__qualname__} is declared a security seam but takes no "
            f"`scope` parameter; the seam is where authority is checked")

    @wraps(fn)
    def guarded(*args, **kwargs):
        bound = sig.bind_partial(*args, **kwargs)
        if "scope" not in bound.arguments:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                f"{fn.__qualname__} was called without a scope")
        scope = bound.arguments["scope"]
        if isinstance(scope, (str, bytes)):
            raise ScopeRefused(
                STRING_REFUSED,
                f"{fn.__qualname__} received a bare string where a "
                f"TenantScope is required")
        if not isinstance(scope, TenantScope):
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                f"{fn.__qualname__} received {type(scope).__name__}, which "
                f"is not an established scope")
        scope.assert_live()
        return fn(*args, **kwargs)

    guarded.__tenant_seam__ = True
    guarded.__wrapped_seam__ = fn
    SECURITY_SEAMS.register(guarded)
    return guarded


# =============================================================================
# Readers — one implementation, and an empty state that says which empty
# =============================================================================
@dataclass(frozen=True)
class ScopedRead:
    """What a reader saw, and what it could not see.

    `withheld_private` and `refused` are the difference between "you have no
    internal data" and "you have internal data and no authority over it".
    """

    rows: Tuple[dict, ...]
    scope_state: str
    withheld_private: int = 0
    refused: Tuple[int, ...] = ()

    def empty_state(self) -> str:
        if self.rows:
            return NON_EMPTY
        if self.withheld_private:
            return EMPTY_PRIVATE_WITHHELD
        if self.refused:
            return EMPTY_UNTAGGED_REFUSED
        return EMPTY_NO_ROWS


def visible_rows(rows: Sequence[Mapping], *,
                 scope: Optional[TenantScope] = None) -> ScopedRead:
    """The empty state of the whole private world.

    No scope means PUBLIC rows only — never a silent private row, and never a
    silent nothing either. A row with no `visibility` is refused rather than
    assumed: untagged is not public, and treating it as public is how a
    private row escapes on the day someone forgets a field.
    """
    if isinstance(scope, (str, bytes)):
        raise ScopeRefused(
            STRING_REFUSED,
            "visible_rows() takes an established scope or None; a string is "
            "not a weaker scope, it is no scope at all")
    if scope is not None and not isinstance(scope, TenantScope):
        raise ScopeRefused(
            NO_ESTABLISHMENT_SOURCE,
            f"visible_rows() received {type(scope).__name__}")
    if scope is not None:
        scope.assert_live()

    kept, withheld, refused = [], 0, []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            refused.append(index)
            continue
        visibility = row.get("visibility")
        if visibility not in VISIBILITIES:
            refused.append(index)
            continue
        if visibility == PUBLIC:
            kept.append(dict(row))
            continue
        owner = row.get("tenant_id")
        if not isinstance(owner, str) or not owner:
            refused.append(index)
            continue
        if scope is None or owner != scope.tenant.value:
            withheld += 1
            continue
        kept.append(dict(row))
    state = SCOPED if scope is not None else SCOPELESS_PUBLIC_ONLY
    return ScopedRead(tuple(kept), state, withheld, tuple(refused))


@requires_tenant_scope
def export_partition(rows: Sequence[Mapping], *,
                     scope: TenantScope) -> ScopedRead:
    """Everything one tenant may carry out of the system.

    Shares `visible_rows` rather than filtering again: an export path with its
    own predicate is the second reader that drifts, and the drift is only ever
    discovered by the tenant who receives someone else's row.
    """
    return visible_rows(rows, scope=scope)


@requires_tenant_scope
def partition_path(root, *, scope: TenantScope) -> Path:
    """Where one tenant's rows live on disk.

    Built from the opaque id, never from the label. The containment assertion
    is belt-and-braces: `TenantId` already refuses every character that could
    escape, so if this ever fires the identity guard has been weakened.
    """
    base = Path(root).resolve()
    candidate = (base / scope.tenant.value).resolve()
    if base != candidate and base not in candidate.parents:
        raise ScopeRefused(  # pragma: no cover - unreachable by construction
            STRING_REFUSED,
            f"tenant partition {candidate} escapes {base}")
    return candidate


def scope_cache_key(scope: TenantScope) -> str:
    """A cache key that cannot serve one tenant another's rows.

    Keyed on the opaque identity and the contract version. Two scopes for the
    same tenant SHARE a key — otherwise the cache is useless — and no two
    tenants ever do. `display_label` is absent on purpose: a label-keyed cache
    is how "Linear" is served "Linear Minerals Corp."'s rows.
    """
    if not isinstance(scope, TenantScope):
        state = (STRING_REFUSED if isinstance(scope, (str, bytes))
                 else NO_ESTABLISHMENT_SOURCE)
        raise ScopeRefused(
            state, "a cache key is derived from an established scope")
    scope.assert_live()
    return f"{TENANT_SCOPE_CONTRACT}|{scope.tenant.value}"


# =============================================================================
# The guards — they read the class, not the prose
# =============================================================================
#: The only callables permitted to produce authority. `establish` is the
#: audited entry point; `from_row` and `coerce_scope` reload something
#: `establish` already created and re-validate its establishment source;
#: `TenantId.mint` is the control plane issuing a new identity from entropy,
#: which is the one origin that cannot be influenced by anything we read.
SCOPE_PRODUCER_ALLOWLIST = frozenset({
    "establish", "coerce_scope", "TenantScope.from_row", "TenantId.mint",
})

#: Tokens that mark a name as evidence-derived. Used by the SECOND net only;
#: the primary guard is the exact attribute set asserted in the suite, which
#: catches an added constructor whatever it is called.
_EVIDENCE_TOKENS = frozenset({
    "evidence", "scrape", "scraped", "page", "document", "doc", "html",
    "text", "name", "names", "company", "alias", "label", "llm", "model",
    "prompt", "inferred", "infer", "guess", "observation", "claim", "filing",
    "web", "url", "domain", "content", "string", "str",
})
_CONSTRUCTION_VERBS = frozenset({
    "from", "of", "for", "parse", "make", "create", "build", "new", "derive",
    "derived", "infer", "inferred", "resolve", "lookup", "find", "get",
    "coerce", "establish", "mint", "issue",
})


def _return_annotation(obj) -> str:
    target = obj
    if isinstance(target, (classmethod, staticmethod)):
        target = target.__func__
    annotation = getattr(target, "__annotations__", None)
    if not isinstance(annotation, dict):
        return ""
    return str(annotation.get("return", "")).strip("'\" ")


def scope_producers(module=None) -> frozenset:
    """Every callable that DECLARES it returns a TenantScope or a TenantId.

    Reads `__annotations__` off the live objects — module level and off the
    classes — so a `from_evidence` renamed to `hydrate` is still found. This is
    the net that does not care what the author called it.
    """
    import sys
    mod = module if module is not None else sys.modules[__name__]
    found = set()

    def _scan(namespace, prefix: str):
        for name, obj in list(vars(namespace).items()):
            if name.startswith("__"):
                continue
            if not callable(obj) and not isinstance(
                    obj, (classmethod, staticmethod, property)):
                continue
            if _return_annotation(obj) in ("TenantScope", "TenantId"):
                found.add(prefix + name)

    _scan(mod, "")
    for cls_name in ("TenantScope", "TenantId"):
        cls = getattr(mod, cls_name, None)
        if cls is not None:
            _scan(cls, cls_name + ".")
    return frozenset(found)


def assert_no_evidence_constructors(module=None) -> None:
    """Raise if anything here can build authority out of something we read.

    Two nets, and they fail differently on purpose:

      1. `scope_producers()` — anything DECLARING a TenantScope/TenantId return
         type that is not on the allowlist. Catches a renamed constructor.
      2. the name-token net below — anything whose name pairs a construction
         verb with an evidence noun, annotated or not. Catches an unannotated
         `from_evidence`.

    Known and stated: a constructor that is BOTH renamed to something innocent
    AND unannotated escapes both nets here. That case is covered by the suite's
    exact-attribute-set assertion, which is the primary guard.
    """
    import sys
    mod = module if module is not None else sys.modules[__name__]

    stray = scope_producers(mod) - SCOPE_PRODUCER_ALLOWLIST
    if stray:
        raise AssertionError(
            f"these callables declare they produce authority and are not on "
            f"the allowlist: {sorted(stray)}. TenantScope is established from "
            f"a trusted context, never derived.")

    suspects = []

    def _scan(namespace, prefix: str):
        for name in list(vars(namespace)):
            if name.startswith("__"):
                continue
            tokens = set(name.lower().strip("_").split("_"))
            if tokens & _EVIDENCE_TOKENS and tokens & _CONSTRUCTION_VERBS:
                suspects.append(prefix + name)

    _scan(mod, "")
    for cls_name in ("TenantScope", "TenantId"):
        cls = getattr(mod, cls_name, None)
        if cls is not None:
            _scan(cls, cls_name + ".")
    if suspects:
        raise AssertionError(
            f"these names pair a construction verb with an evidence noun: "
            f"{sorted(suspects)}. Scraped content is not an authorization "
            f"subject.")

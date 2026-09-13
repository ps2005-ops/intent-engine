"""The tenant's internal world -- private nodes on the CANONICAL graph.

WHY THIS IS NOT A SECOND GRAPH
------------------------------
Everything here is a `Node` and an `Edge` in `business_graph.model`, stored in
the same `BusinessGraph`, read through the same `read()`. That was the design
decision, and it was the expensive one to get right: a separate "internal
graph" would have been far easier to write and would have handed every
consumer two readers. Two readers drift. The drift is always discovered late,
and in this domain it is discovered by the tenant who receives somebody else's
row.

So the internal world is the same substrate with three additions:

    a DISJOINT kind vocabulary   `private.` prefixed, so `of_kind(PRODUCT)`
                                 can never return an internal product line and
                                 a private kind cannot be built as a public
                                 `Node` at all;
    a TENANT on every node/edge  a typed `TenantId`, never a name;
    a NAMESPACED node id         `<tenant>::<local id>`, so two tenants both
                                 using the local id "seg-enterprise" get two
                                 distinct nodes. Without this, the second
                                 tenant to use an id would either overwrite
                                 the first (a leak) or be refused (a denial of
                                 service that also discloses that the id is
                                 taken).

WHY THE KINDS ARE PREFIXED AND NOT REUSED
-----------------------------------------
`product`, `decision`, `action` and `outcome` ALREADY EXIST as public kinds.
Reusing them would have made `graph.of_kind(PRODUCT)` return a mixture of
public product nodes and one tenant's confidential product line, filtered only
by whoever remembered to filter. PUBLIC != PRIVATE has to be a property of the
type, not of the caller's attention.

THREE FAILURE VOCABULARIES, THREE CONCERNS
------------------------------------------
    GraphError            this is not a well-formed node or edge (bad kind,
                          missing label, unparseable timestamp). A ValueError,
                          like the rest of the model's construction errors.
    PrivateGraphRefused   this crosses a boundary, or this stored row cannot
                          be trusted. NOT a ValueError, so a parser's
                          `except ValueError` cannot swallow it.
    ScopeRefused          this is an authority problem. Raised by `core.tenant`
                          and re-used unchanged, so a refusal counts in one
                          telemetry bucket rather than two.

WHAT THE TENANT BINDING DOES AND DOES NOT DO
--------------------------------------------
Each persisted row carries `tenant_binding`, a digest over every field that
carries identity -- which is all of them except the two genuinely optional ones
(see `_binding`). A row whose `tenant_id` was edited by hand is refused on
reload, and so is a row whose company, sensitivity or attributes were edited,
and so is a row somebody added a key to. It is TAMPER-EVIDENT,
not unforgeable: someone who can write to the store AND knows the binding rule
can mint a consistent row for their own tenant. Making that impossible needs a
keyed MAC and key infrastructure that does not exist at this layer, and
claiming it without one would be worse than the gap. Two independent checks
narrow it anyway -- the digest, and the node id's tenant prefix -- so an
alteration has to be consistent in three places to survive, and even then the
row it forges is one its own tenant could have written legitimately.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence, Tuple

from intent_engine.business_graph.model import (
    CROSS_TENANT,
    EXPLICIT_NULL,
    MISSING_REQUIRED_FIELD,
    STALE_CONTRACT,
    TENANT_BINDING_BROKEN,
    BusinessGraph,
    Edge,
    GraphError,
    Node,
    PrivateGraphRefused,
    TenantOwned,
    read_scope,
)
from intent_engine.core.tenant import (
    NO_ESTABLISHMENT_SOURCE,
    PUBLIC,
    STRING_REFUSED,
    TENANT_PRIVATE,
    ScopeRefused,
    TenantId,
    TenantScope,
    requires_tenant_scope,
    scope_cache_key,
)

# =============================================================================
# The private vocabulary -- disjoint from the public one, by construction
# =============================================================================
#: Every private kind carries this prefix. It is not decoration: the public
#: vocabulary already contains `product`, `decision`, `action` and `outcome`,
#: and a private node answering to one of those names would be returned by
#: every existing `of_kind` call in the product.
PRIVATE_KIND_PREFIX = "private."

CUSTOMER_SEGMENT = "private.customer_segment"
PRIVATE_PRODUCT = "private.product"
CONTRACT = "private.contract"
PIPELINE_OPPORTUNITY = "private.pipeline_opportunity"
COHORT = "private.cohort"
CHANNEL = "private.channel"
INTERNAL_METRIC = "private.internal_metric"
INITIATIVE = "private.initiative"
EXPERIMENT = "private.experiment"
INTERNAL_ASSUMPTION = "private.internal_assumption"
PRIVATE_DECISION = "private.decision"
PRIVATE_ACTION = "private.action"
PRIVATE_OUTCOME = "private.outcome"

PRIVATE_NODE_KINDS = frozenset({
    CUSTOMER_SEGMENT, PRIVATE_PRODUCT, CONTRACT, PIPELINE_OPPORTUNITY, COHORT,
    CHANNEL, INTERNAL_METRIC, INITIATIVE, EXPERIMENT, INTERNAL_ASSUMPTION,
    PRIVATE_DECISION, PRIVATE_ACTION, PRIVATE_OUTCOME,
})

SEGMENT_BUYS_PRODUCT = "private.segment_buys_product"
CONTRACT_WITH_SEGMENT = "private.contract_with_segment"
PIPELINE_FOR_PRODUCT = "private.pipeline_for_product"
INITIATIVE_AFFECTS_METRIC = "private.initiative_affects_metric"
EXPERIMENT_TESTS_ASSUMPTION = "private.experiment_tests_assumption"
DECISION_AUTHORIZES_ACTION = "private.decision_authorizes_action"
ACTION_AFFECTS_METRIC = "private.action_affects_metric"
OUTCOME_RESOLVES_DECISION = "private.outcome_resolves_decision"

#: One table, and the graph enforces it generically. A
#: `SEGMENT_BUYS_PRODUCT` edge from a Contract to a Cohort is not a
#: relationship anybody can render, and a graph that stores it will be asked to
#: explain it months later.
PRIVATE_EDGE_ENDPOINTS = {
    SEGMENT_BUYS_PRODUCT: (CUSTOMER_SEGMENT, PRIVATE_PRODUCT),
    CONTRACT_WITH_SEGMENT: (CONTRACT, CUSTOMER_SEGMENT),
    PIPELINE_FOR_PRODUCT: (PIPELINE_OPPORTUNITY, PRIVATE_PRODUCT),
    INITIATIVE_AFFECTS_METRIC: (INITIATIVE, INTERNAL_METRIC),
    EXPERIMENT_TESTS_ASSUMPTION: (EXPERIMENT, INTERNAL_ASSUMPTION),
    DECISION_AUTHORIZES_ACTION: (PRIVATE_DECISION, PRIVATE_ACTION),
    ACTION_AFFECTS_METRIC: (PRIVATE_ACTION, INTERNAL_METRIC),
    OUTCOME_RESOLVES_DECISION: (PRIVATE_OUTCOME, PRIVATE_DECISION),
}
PRIVATE_EDGE_KINDS = frozenset(PRIVATE_EDGE_ENDPOINTS)

#: How exposed one node is INSIDE the tenant. Orthogonal to the tenant
#: boundary -- everything here is already private to exactly one tenant --
#: and required rather than defaulted, because a default would be this layer
#: deciding that somebody's contract terms are ordinary internal data.
SENSITIVITY_INTERNAL = "internal"
SENSITIVITY_CONFIDENTIAL = "confidential"
SENSITIVITY_RESTRICTED = "restricted"
SENSITIVITIES = frozenset({
    SENSITIVITY_INTERNAL, SENSITIVITY_CONFIDENTIAL, SENSITIVITY_RESTRICTED})

#: `<tenant id>::<local id>`. The separator is outside the Crockford alphabet a
#: `TenantId` is made of, so the prefix can always be split back off exactly.
NODE_ID_SEPARATOR = "::"

PRIVATE_NODE_CONTRACT = "business_graph_private_node.v1"
PRIVATE_EDGE_CONTRACT = "business_graph_private_edge.v1"
PRIVATE_EXPORT_CONTRACT = "business_graph_private_export.v1"
PRIVATE_INVENTORY_CONTRACT = "business_graph_private_inventory.v1"
GRAPH_VIEW_CACHE_CONTRACT = "business_graph_view.v1"
#: The cache namespace a SCOPELESS read uses. A distinct literal rather than an
#: empty segment, so a scopeless key can never be confused with a scoped one by
#: a reader doing string surgery on the key.
PUBLIC_CACHE_NAMESPACE = "public-only"

#: Handed to `__init__` by the two functions permitted to stamp a private
#: thing: the factory (which holds a scope) and `from_row` (which checks one).
#: Direct construction reaches `__post_init__` without it and is refused, so
#: there is no path to a private node that nobody authorized. Same device, and
#: the same reason, as `core.tenant._ESTABLISHED`.
_ISSUED = object()


def _parse_time(value: str, *, what: str) -> datetime:
    """Strict, timezone-aware only.

    Deliberately not `core.tenant`'s parser: that one raises `ScopeRefused`,
    which would report a typo in a timestamp as an authorization failure and
    send the next reader to the wrong file.
    """
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (ValueError, TypeError) as exc:
        raise GraphError(
            f"{what} {value!r} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise GraphError(
            f"{what} {value!r} has no timezone; a naive timestamp is a "
            f"different instant for every reader")
    return parsed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(payload: dict) -> dict:
    """The row exactly as it will come back off a disk.

    Everything is round-tripped through JSON before it is hashed OR returned,
    so a tuple in `attrs` does not hash differently from the list it becomes in
    a file. Without this the binding would report tampering on an untouched
    row, and a guard that cries wolf gets switched off.
    """
    return json.loads(_dump(payload))


def _dump(payload) -> str:
    try:
        return json.dumps(payload, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise GraphError(
            f"a private graph row must be JSON-serializable; {exc}") from exc


def _binding(row: Mapping, *, unbound: frozenset = frozenset()) -> str:
    """The digest a row carries, over everything except the digest itself and
    the fields named `unbound`.

    An UNBOUND field is one a producer may legitimately omit or leave null.
    Binding those would make an older writer's perfectly good row
    indistinguishable from a tampered one, and a guard that cries wolf gets
    switched off. Everything else is bound, INCLUDING keys nobody expected:
    an extra key changes the digest, so a row cannot be quietly extended.
    """
    payload = {k: v for k, v in row.items()
               if k != "tenant_binding" and k not in unbound}
    return hashlib.sha256(
        _dump(_canonical(payload)).encode("utf-8")).hexdigest()


def _require_keys(row: Mapping, keys: Sequence[str], *, what: str) -> None:
    """Missing and null are DIFFERENT refusals, and both are refusals.

    A defaulted identity field is an invented one. Reporting them under one
    state would hide which of the two a producer is actually doing wrong.
    """
    for key in keys:
        if key not in row:
            raise PrivateGraphRefused(
                MISSING_REQUIRED_FIELD,
                f"persisted {what} is missing required key {key!r}; missing "
                f"is not empty")
        if row[key] is None:
            raise PrivateGraphRefused(
                EXPLICIT_NULL,
                f"persisted {what} has an explicit null for required key "
                f"{key!r}; null is not empty")


def _check_row(row, *, contract: str, keys: Sequence[str], what: str,
               unbound: frozenset = frozenset()) -> None:
    """Contract, then required keys, then integrity. The order is the message.

    A v0 row is reported as a stale contract rather than as tampering: it was
    not altered, it was written by an older producer, and telling an operator
    the wrong one costs an afternoon. A missing required key is likewise
    reported as missing rather than as a broken digest, even though it would
    also break the digest.
    """
    if not isinstance(row, Mapping):
        raise PrivateGraphRefused(
            MISSING_REQUIRED_FIELD,
            f"a persisted {what} is a mapping, got {type(row).__name__}")
    declared = row.get("contract")
    if declared != contract:
        raise PrivateGraphRefused(
            STALE_CONTRACT,
            f"row declares contract {declared!r}, this reader is "
            f"{contract!r}; a private row is never silently upgraded across "
            f"versions")
    _require_keys(row, keys, what=what)
    if _binding(row, unbound=unbound) != row["tenant_binding"]:
        raise PrivateGraphRefused(
            TENANT_BINDING_BROKEN,
            f"persisted {what} {row.get('node_id') or row.get('src')!r} does "
            f"not match its tenant binding; the row was altered after it was "
            f"written and is refused rather than read")


def _authorize_row(row: Mapping, scope: TenantScope, *, what: str) -> TenantId:
    """The row's owner, checked against the reader's authority.

    `TenantId(...)` refuses anything that is not a control-plane identity, so a
    row whose tenant field was replaced with a company name never reaches the
    comparison at all.
    """
    tenant = TenantId(row["tenant_id"])
    if not scope.authorizes(tenant):
        raise PrivateGraphRefused(
            CROSS_TENANT,
            f"a persisted {what} owned by {tenant.value} cannot be read under "
            f"a scope for {scope.tenant.value}")
    return tenant


# =============================================================================
# PrivateNode
# =============================================================================
@dataclass(frozen=True)
class PrivateNode(Node, TenantOwned):
    """One thing inside a tenant's business, and who is allowed to see it.

    Every field has a default so that any partial or hostile construction
    lands in `__post_init__` and is refused with a NAMED state, rather than
    raising a bare `TypeError` that telemetry cannot count. That is the same
    reason `core.tenant.TenantScope` is built that way.

    BITEMPORAL ON PURPOSE. `observed_at` is when the fact was true in the
    business; `known_at` is when we found out. Collapsing them is a defect this
    program has already shipped once -- a batch of actions inherited their
    retrieval date, and twenty-three records shared one timestamp, which made
    every question about sequence unanswerable.
    """

    # Re-declared with defaults so hostile construction reaches __post_init__.
    node_id: str = ""
    kind: str = ""
    label: str = ""
    source: str = ""
    tenant: Optional[TenantId] = None
    company_id: str = ""
    observed_at: str = ""
    known_at: str = ""
    sensitivity: str = ""
    created_at: str = ""
    _issued_by: object = field(default=None, repr=False, compare=False)

    @classmethod
    def permitted_kinds(cls) -> frozenset:
        return PRIVATE_NODE_KINDS

    @property
    def node_type(self) -> str:
        """`kind` under the name the private contract uses for it."""
        return self.kind

    @property
    def local_id(self) -> str:
        """The id the tenant chose, with the tenant prefix taken back off."""
        return self.node_id.split(NODE_ID_SEPARATOR, 1)[-1]

    def __post_init__(self):
        # Identity first, so the canonical attack -- a private node built with
        # a company name where a tenant belongs -- reports STRING_REFUSED and
        # not a confusing complaint about a missing label.
        if self.tenant is None:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "a private node with no tenant identity is not private; it is "
                "a public node that nobody has noticed yet")
        if not isinstance(self.tenant, TenantId):
            raise ScopeRefused(
                STRING_REFUSED,
                f"a private node's owner must be a TenantId, got "
                f"{type(self.tenant).__name__}. A bare string is refused here "
                f"on purpose: it is the shape a company name arrives in.")
        if self._issued_by is not _ISSUED:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "a PrivateNode cannot be constructed directly; "
                "private_node(scope=...) and PrivateNode.from_row(scope=...) "
                "are the only two ways, and both of them hold a TenantScope. "
                "A private node nobody authorized is a private node nobody "
                "can be held to.")
        super().__post_init__()
        prefix = self.tenant.value + NODE_ID_SEPARATOR
        if not self.node_id.startswith(prefix) or self.node_id == prefix:
            # The second tamper detector, and the one that needs no secret:
            # editing `tenant_id` in a stored row leaves the node id naming
            # the tenant it used to belong to.
            raise PrivateGraphRefused(
                CROSS_TENANT,
                f"node id {self.node_id!r} does not belong to "
                f"{self.tenant.value}; a private node id is "
                f"<tenant>{NODE_ID_SEPARATOR}<local id>")
        if not self.company_id:
            raise GraphError(
                f"private node {self.node_id!r} has no company_id; a private "
                f"fact about nobody in particular cannot be reasoned about")
        if self.company_id.startswith("tnt_"):
            # company_id is a NAME-SPACE and can be attacker-influenced.
            # A company_id shaped like a tenant id is either a confusion
            # about which field authorizes, or an attempt to create one.
            raise ScopeRefused(
                STRING_REFUSED,
                f"company_id {self.company_id!r} is shaped like a tenant "
                f"identity; a company id names a subject and authorizes "
                f"nothing, and the two must not be confusable")
        if self.sensitivity not in SENSITIVITIES:
            raise GraphError(
                f"sensitivity {self.sensitivity!r} is not one of "
                f"{sorted(SENSITIVITIES)}; it is required rather than "
                f"defaulted, because a default decides for the customer how "
                f"exposed their data is")
        observed = _parse_time(self.observed_at, what="observed_at")
        known = _parse_time(self.known_at, what="known_at")
        if known < observed:
            raise GraphError(
                f"known_at {self.known_at} precedes observed_at "
                f"{self.observed_at}; we cannot have learned a fact before it "
                f"was true")
        _parse_time(self.created_at, what="created_at")
        object.__setattr__(self, "attrs", dict(self.attrs or {}))
        _dump(self.attrs)   # fail where the mistake is, not at write time

    # --- persistence -------------------------------------------------------
    #: Missing is refused. `attributes` is required and MAY be `{}`: absent and
    #: empty are different claims, exactly as `capabilities` is on a scope.
    ROW_KEYS = ("contract", "visibility", "node_id", "tenant_id", "company_id",
                "node_type", "label", "provenance", "sensitivity",
                "observed_at", "known_at", "created_at", "attributes",
                "tenant_binding")
    #: The only two fields a producer may omit or null. They carry no identity
    #: and no authority, so they are outside the binding -- see `_binding`.
    UNBOUND_KEYS = frozenset({"confidence", "as_of"})

    def as_row(self) -> dict:
        row = _canonical({
            "contract": PRIVATE_NODE_CONTRACT,
            # Tagged so the exported rows can be handed straight to
            # `core.tenant.visible_rows` without a second classifier.
            "visibility": TENANT_PRIVATE,
            "node_id": self.node_id,
            "tenant_id": self.tenant.value,
            "company_id": self.company_id,
            "node_type": self.kind,
            "label": self.label,
            "provenance": self.source,
            "sensitivity": self.sensitivity,
            "observed_at": self.observed_at,
            "known_at": self.known_at,
            "created_at": self.created_at,
            "attributes": dict(self.attrs),
            "confidence": self.confidence,
            "as_of": self.as_of,
        })
        row["tenant_binding"] = _binding(row, unbound=self.UNBOUND_KEYS)
        return row

    #: `Node.as_dict` produces an UNTAGGED row -- no tenant, no visibility --
    #: which is exactly the shape a reader treats as public. Anything that
    #: serializes nodes generically would therefore have emitted a private node
    #: as a public one. Pointed at `as_row` so there is no shape of this class
    #: that loses its owner on the way out.
    as_dict = as_row

    @classmethod
    def from_row(cls, row: Mapping, *, scope: TenantScope) -> "PrivateNode":
        """Reload one private node under an authority that may read it."""
        scope = _require_scope(scope, what="PrivateNode.from_row")
        _check_row(row, contract=PRIVATE_NODE_CONTRACT, keys=cls.ROW_KEYS,
                   what="private node", unbound=cls.UNBOUND_KEYS)
        tenant = _authorize_row(row, scope, what="private node")
        return cls(
            node_id=row["node_id"], kind=row["node_type"], label=row["label"],
            source=row["provenance"], tenant=tenant,
            company_id=row["company_id"], sensitivity=row["sensitivity"],
            observed_at=row["observed_at"], known_at=row["known_at"],
            created_at=row["created_at"], attrs=dict(row["attributes"]),
            # Genuinely optional: absent and explicit null both mean "".
            confidence=row.get("confidence") or "",
            as_of=row.get("as_of") or "",
            _issued_by=_ISSUED)


# =============================================================================
# PrivateEdge
# =============================================================================
@dataclass(frozen=True)
class PrivateEdge(Edge, TenantOwned):
    """A relationship inside one tenant. Both ends are always that tenant's.

    The tenant boundary is checked twice and the redundancy is deliberate: on
    the edge itself, where `src` and `dst` must both carry the owner's prefix,
    and again in `BusinessGraph.add_private_edge`, which can see the nodes and
    so can also check that they exist and are of the right kinds. The first
    check makes a cross-tenant edge impossible to CONSTRUCT; the second makes
    it impossible to STORE even if the first is ever weakened.
    """

    src: str = ""
    dst: str = ""
    kind: str = ""
    derived: bool = False
    source: str = ""
    tenant: Optional[TenantId] = None
    created_at: str = ""
    _issued_by: object = field(default=None, repr=False, compare=False)

    @classmethod
    def permitted_kinds(cls) -> frozenset:
        return PRIVATE_EDGE_KINDS

    def __post_init__(self):
        if self.tenant is None:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "a private edge with no tenant identity is not private")
        if not isinstance(self.tenant, TenantId):
            raise ScopeRefused(
                STRING_REFUSED,
                f"a private edge's owner must be a TenantId, got "
                f"{type(self.tenant).__name__}")
        if self._issued_by is not _ISSUED:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "a PrivateEdge cannot be constructed directly; "
                "private_edge(scope=...) and PrivateEdge.from_row(scope=...) "
                "are the only two ways")
        super().__post_init__()
        prefix = self.tenant.value + NODE_ID_SEPARATOR
        for end, name in ((self.src, "src"), (self.dst, "dst")):
            if not end.startswith(prefix) or end == prefix:
                raise PrivateGraphRefused(
                    CROSS_TENANT,
                    f"{self.kind} edge owned by {self.tenant.value} has {name} "
                    f"{end!r}, which is not one of its nodes; an edge cannot "
                    f"cross the tenant boundary")
        _parse_time(self.created_at, what="created_at")

    ROW_KEYS = ("contract", "visibility", "src", "dst", "kind", "derived",
                "source", "tenant_id", "created_at", "tenant_binding")

    def as_row(self) -> dict:
        row = _canonical({
            "contract": PRIVATE_EDGE_CONTRACT,
            "visibility": TENANT_PRIVATE,
            "src": self.src, "dst": self.dst, "kind": self.kind,
            "derived": self.derived, "source": self.source,
            "tenant_id": self.tenant.value, "created_at": self.created_at,
        })
        row["tenant_binding"] = _binding(row)
        return row

    #: Same reason as `PrivateNode.as_dict`: an untagged edge row is a public
    #: edge row to every reader that receives one.
    as_dict = as_row

    @classmethod
    def from_row(cls, row: Mapping, *, scope: TenantScope) -> "PrivateEdge":
        scope = _require_scope(scope, what="PrivateEdge.from_row")
        _check_row(row, contract=PRIVATE_EDGE_CONTRACT, keys=cls.ROW_KEYS,
                   what="private edge")
        tenant = _authorize_row(row, scope, what="private edge")
        return cls(src=row["src"], dst=row["dst"], kind=row["kind"],
                   derived=bool(row["derived"]), source=row["source"],
                   tenant=tenant, created_at=row["created_at"],
                   _issued_by=_ISSUED)


def _require_scope(scope, *, what: str) -> TenantScope:
    """A scope, or a named refusal. Never a string, never a `TenantId`.

    `read_scope` allows `None` because a scopeless PUBLIC read is a real thing
    to want. Here it is not: there is no such thing as reading a private row
    without authority, so `None` is refused too.
    """
    if scope is None:
        raise ScopeRefused(
            NO_ESTABLISHMENT_SOURCE,
            f"{what} was called without a scope; there is no scopeless read "
            f"of a private row")
    got = read_scope(scope)
    return got


# =============================================================================
# The only two ways to stamp a private thing
# =============================================================================
@requires_tenant_scope
def private_node(*, scope: TenantScope, kind: str, local_id: str, label: str,
                 company_id: str, source: str, observed_at: str,
                 known_at: str, sensitivity: str,
                 attrs: Optional[dict] = None, confidence: str = "",
                 as_of: str = "", created_at: str = "") -> PrivateNode:
    """Stamp one private node with the authority that is writing it.

    Keyword-only, like `core.tenant.establish`, for the same reason:
    `private_node(scope, "acme", ...)` is a sentence somebody can write by
    accident and `private_node(scope=..., company_id=...)` is not.

    `local_id` is the id the TENANT chose. The stored `node_id` prefixes it
    with the tenant, which is what lets two customers both call their biggest
    segment "enterprise" without one of them overwriting the other.
    """
    if not isinstance(local_id, str) or not local_id:
        raise GraphError("a private node needs a local id")
    if NODE_ID_SEPARATOR in local_id:
        raise GraphError(
            f"local id {local_id!r} contains {NODE_ID_SEPARATOR!r}, which "
            f"separates the tenant prefix; the split back would be ambiguous")
    return PrivateNode(
        node_id=scope.tenant.value + NODE_ID_SEPARATOR + local_id,
        kind=kind, label=label, source=source, tenant=scope.tenant,
        company_id=company_id, observed_at=observed_at, known_at=known_at,
        sensitivity=sensitivity, created_at=created_at or _now_iso(),
        attrs=dict(attrs or {}), confidence=confidence, as_of=as_of,
        _issued_by=_ISSUED)


@requires_tenant_scope
def private_edge(*, scope: TenantScope, kind: str, src_local_id: str,
                 dst_local_id: str, derived: bool, source: str = "",
                 created_at: str = "") -> PrivateEdge:
    """Stamp one private edge. `derived` has no default on purpose.

    DERIVED versus RECORDED is the model's oldest discipline and it applies
    unchanged inside a tenant: a contract-to-segment link recomputed from a CRM
    export cannot drift from the rows that made it, while an
    initiative-affects-metric link is somebody's judgment and carries their
    name. Defaulting `derived` would let a judgment be stored as a fact.
    """
    prefix = scope.tenant.value + NODE_ID_SEPARATOR
    return PrivateEdge(
        src=prefix + str(src_local_id), dst=prefix + str(dst_local_id),
        kind=kind, derived=derived, source=source, tenant=scope.tenant,
        created_at=created_at or _now_iso(), _issued_by=_ISSUED)


# =============================================================================
# One shared reader -- mappings before objects
# =============================================================================
def _coerce(obj, cls, *, scope: TenantScope, what: str):
    """Accept the live object, the persisted row, or a transported DTO.

    Mappings are read as mappings BEFORE anything is read as an object. A
    getattr-only reader silently folds a dict into a single garbage record,
    which is how a ledger of many events once read as one -- and here it would
    fold a dict into a record with no tenant, which is worse.

    A `str` is always refused and never parsed, even when it holds valid JSON.
    Decoding a transport is the transport's job; if this parsed strings, the
    one thing it exists to refuse would have a bypass.
    """
    scope = _require_scope(scope, what=what)
    if isinstance(obj, cls):
        if not scope.authorizes(obj.tenant):
            raise PrivateGraphRefused(
                CROSS_TENANT,
                f"a live {what} owned by {obj.tenant_id} cannot be read under "
                f"a scope for {scope.tenant.value}")
        return obj
    if isinstance(obj, (str, bytes)):
        raise ScopeRefused(
            STRING_REFUSED,
            f"a {what} cannot be reconstituted from a string; decode the "
            f"transport first and pass the row")
    if isinstance(obj, Mapping):
        return cls.from_row(obj, scope=scope)
    if all(hasattr(obj, key) for key in cls.ROW_KEYS):
        return cls.from_row({key: getattr(obj, key) for key in cls.ROW_KEYS},
                            scope=scope)
    raise PrivateGraphRefused(
        MISSING_REQUIRED_FIELD,
        f"{type(obj).__name__} carries no {what}; required fields are "
        f"{list(cls.ROW_KEYS)}")


@requires_tenant_scope
def coerce_private_node(obj, *, scope: TenantScope) -> PrivateNode:
    return _coerce(obj, PrivateNode, scope=scope, what="private node")


@requires_tenant_scope
def coerce_private_edge(obj, *, scope: TenantScope) -> PrivateEdge:
    return _coerce(obj, PrivateEdge, scope=scope, what="private edge")


# =============================================================================
# Export, inventory, cache key
# =============================================================================
@requires_tenant_scope
def export_private_partition(graph: BusinessGraph, *,
                             scope: TenantScope) -> dict:
    """Everything one tenant may carry out of the graph.

    Shares `BusinessGraph.read` rather than filtering again. An export path
    with its own predicate is the second reader that drifts, and that drift is
    only ever discovered by the tenant who receives somebody else's row.

    Rows are tagged with `visibility`, so what comes out can be handed to
    `core.tenant.visible_rows` unchanged -- the two layers agree because they
    are the same vocabulary, not because somebody kept them in step.
    """
    read = graph.read(scope=scope)
    nodes, edges = [], []
    for node in read.nodes:
        nodes.append(node.as_row() if isinstance(node, TenantOwned)
                     else dict(node.as_dict(), visibility=PUBLIC))
    for edge in read.edges:
        edges.append(edge.as_row() if isinstance(edge, TenantOwned)
                     else dict(edge.as_dict(), visibility=PUBLIC))
    return {
        "contract": PRIVATE_EXPORT_CONTRACT,
        "tenant_id": scope.tenant.value,
        "scope_state": read.scope_state,
        "empty_state": read.empty_state(),
        "nodes": nodes,
        "edges": edges,
        # Never omitted when zero: an export that says nothing about what it
        # left behind cannot distinguish "you have no internal data" from
        # "your data is here and none of it is yours".
        "withheld": read.withheld_private,
        "refused": list(read.refused),
    }


def private_inventory(graph: BusinessGraph, *,
                      scope: Optional[TenantScope] = None) -> dict:
    """How much of the private world this reader can see, by kind.

    EVERY private kind is a key, zero included, and so are `withheld` and
    `refused`. A counter that appears only when it is non-zero cannot report
    that nothing happened, and the three states a founder must be able to tell
    apart are exactly:

        an EMPTY graph                     empty_state NO_ROWS_EXIST
        a graph that is all somebody else's  empty_state PRIVATE_WITHHELD
        a graph with none of THIS kind      empty_state NON_EMPTY, count 0

    Scopeless is allowed and reports the public-only view, with every private
    count at zero and `withheld` carrying the true total. That is the honest
    answer to "what is in there?" from someone holding no authority.
    """
    read = graph.read(scope=scope)
    nodes = {kind: 0 for kind in sorted(PRIVATE_NODE_KINDS)}
    edges = {kind: 0 for kind in sorted(PRIVATE_EDGE_KINDS)}
    public_nodes = 0
    for node in read.nodes:
        if node.kind in nodes:
            nodes[node.kind] += 1
        else:
            public_nodes += 1
    for edge in read.edges:
        if edge.kind in edges:
            edges[edge.kind] += 1
    return {
        "contract": PRIVATE_INVENTORY_CONTRACT,
        "scope_state": read.scope_state,
        "empty_state": read.empty_state(),
        "nodes": nodes,
        "edges": edges,
        "public_nodes": public_nodes,
        "withheld": read.withheld_private,
        "refused": len(read.refused),
    }


def graph_cache_key(*, view: str,
                    scope: Optional[TenantScope] = None) -> str:
    """A cache key that cannot serve one tenant another tenant's view.

    Built on `core.tenant.scope_cache_key`, so the opaque identity is the only
    thing that varies and `display_label` and `company_id` are absent by
    construction. A company-keyed cache is how the same `company_id` under two
    tenants would be served one answer, and a label-keyed cache is how "Linear"
    was once served "Linear Minerals Corp."'s rows.

    A scopeless view gets its OWN namespace rather than a missing segment, so
    a public read can never collide with a scoped one.
    """
    if not view:
        raise GraphError("a cache key needs a view name")
    got = read_scope(scope)
    if got is None:
        return (f"{GRAPH_VIEW_CACHE_CONTRACT}|{PUBLIC_CACHE_NAMESPACE}"
                f"|{view}")
    return f"{GRAPH_VIEW_CACHE_CONTRACT}|{scope_cache_key(got)}|{view}"


def private_kinds_are_disjoint_from_public() -> Tuple[str, ...]:
    """Any private kind that also exists in the public vocabulary.

    Empty tuple is the pass. Exposed as a function rather than asserted once
    at import so the suite can prove it reports a violation when one exists --
    a guard that has never returned a non-empty result is an untested guard.
    """
    from intent_engine.business_graph.model import EDGE_KINDS, NODE_KINDS

    return tuple(sorted((PRIVATE_NODE_KINDS & NODE_KINDS)
                        | (PRIVATE_EDGE_KINDS & EDGE_KINDS)))

"""The business graph — one substrate every part of the product reads and writes.

WHY THIS EXISTS
---------------
The product has been growing as a set of excellent parts that do not share a
world: company ingestion knows evidence, the strategic layer knows hypotheses,
the executive layer knows decisions, the market engine knows calibration, and
none of them can answer "which assumption did that decision rest on, and did
the outcome confirm it?" -- because no two of them name the same thing the
same way.

That question is the product. A founder asking "should we hire?" needs
evidence, the assumption it supports, the decision that assumption fed, what
actually happened, and how wrong we were last time. Every one of those already
exists somewhere in this repo. None of them are connected.

So this is deliberately NOT a new feature. It is the substrate the existing
subsystems project into, and the thing connectors populate. A Salesforce
connector must produce Customers and Events here; it must never carry
Salesforce-shaped reasoning any further into the product than this file.

DERIVED VERSUS RECORDED -- INHERITED, NOT INVENTED
--------------------------------------------------
`product/graph.py` and `executive/graph.py` already settled this and it is the
right discipline, so it is generalised here rather than redesigned:

    DERIVED   edges are computed from the rows that created their nodes. They
              cannot drift from the thing they describe, because they are not
              stored -- recomputing is the only way to obtain them.
    RECORDED  edges are judgments somebody asserted. They are stored, they
              carry provenance, and they are the only kind a human or a model
              can be wrong about.

Keeping them apart is what stops a model's guess from becoming indistinguishable
from a fact six months later.

EVERY NODE CARRIES PROVENANCE
-----------------------------
`source` is required and is not decorative. The master spec's absolute rules --
never fake evidence, never invent numbers, never hide uncertainty -- are only
enforceable if every node can say where it came from. A node with no provenance
is a claim with no author, and this module refuses to construct one.

THE PRIVATE WORLD IS THIS GRAPH, NOT A SECOND ONE
-------------------------------------------------
A tenant's internal world -- segments, contracts, pipeline, initiatives,
experiments, the decisions and outcomes underneath them -- lives HERE, as
nodes of private kinds carrying a tenant identity. It is deliberately not a
parallel store: two stores means every consumer needs two readers, and two
readers drift until the day one of them answers a question the other cannot.

That decision moves the whole risk into one place: a graph that holds both
worlds can leak one into the other. So the filter is a property of the READ,
not of the caller's good manners:

    every read takes `scope` and every read DEFAULTS IT TO None, and a
    node that declares itself `TenantOwned` is never SHOWN to a `None`
    scope.

Public-only is therefore what a caller gets by forgetting, which is the only
default worth having. There is no `scope="all"`, no admin bypass and no
`include_private=True`; the sole way to see a private node is to hold a
`TenantScope` that `authorizes()` its typed identity.

Three separations do the work, and they are different things on purpose:

    IDENTITY        `company_id` says WHICH company a private node is about.
                    It is a name-space, it can be attacker-influenced, and it
                    authorizes nothing.
    AUTHORIZATION   `TenantScope` says WHO may read it. It is issued by a
                    trusted context (`core.tenant`) and can never be minted
                    from anything the system merely read.
    VISIBILITY      PUBLIC and TENANT_PRIVATE are disjoint vocabularies --
                    `Node.permitted_kinds()` and `PrivateNode.permitted_kinds()`
                    do not intersect -- so a private kind cannot be smuggled
                    into a public node, and `of_kind(PRODUCT)` can never
                    return somebody's internal product line.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from intent_engine.core.tenant import (
    EMPTY_NO_ROWS,
    EMPTY_PRIVATE_WITHHELD,
    EMPTY_UNTAGGED_REFUSED,
    NO_ESTABLISHMENT_SOURCE,
    NON_EMPTY,
    SCOPED,
    SCOPELESS_PUBLIC_ONLY,
    STRING_REFUSED,
    ScopeRefused,
    TenantId,
    TenantScope,
    requires_tenant_scope,
)

# --- node kinds -------------------------------------------------------------
# The vocabulary is fixed on purpose. A connector that needs a new kind is
# usually a connector trying to keep its own shape; the answer is almost always
# to map onto an existing kind. Growing this list is a design decision, not an
# integration detail.
PERSON = "person"
TEAM = "team"
CUSTOMER = "customer"
COMPETITOR = "competitor"
#: The company an analysis is ABOUT. Added when external intelligence was
#: projected and there was nothing to attach it to: a market observation, a
#: macro exposure and a competitor all say something about the subject, and
#: every one of those edges needs the subject to exist. `competitor` was
#: already here, which made the omission easy to miss -- the graph could hold
#: a rival and not the company it rivalled.
#:
#: Deliberately distinct from `customer` and `competitor`, which are companies
#: in a RELATION to the subject. There is exactly one of these per analysis.
COMPANY = "company"
MARKET = "market"
PRODUCT = "product"
PROJECT = "project"
DOCUMENT = "document"
MEETING = "meeting"
RISK = "risk"
KPI = "kpi"
DECISION = "decision"
EVIDENCE = "evidence"
ASSUMPTION = "assumption"
EVENT = "event"
ACTION = "action"
OUTCOME = "outcome"
HYPOTHESIS = "hypothesis"
SCENARIO = "scenario"

NODE_KINDS = frozenset({
    PERSON, TEAM, CUSTOMER, COMPETITOR, COMPANY, MARKET, PRODUCT, PROJECT,
    DOCUMENT, MEETING, RISK, KPI, DECISION, EVIDENCE, ASSUMPTION, EVENT,
    ACTION, OUTCOME, HYPOTHESIS, SCENARIO,
})

# --- edge kinds -------------------------------------------------------------
# The closed loop the product is built around:
#   evidence -> assumption -> hypothesis -> decision -> action -> outcome
# and then `calibrates`, which is the edge that makes the system learn rather
# than merely record.
SUPPORTS = "supports"              # evidence   -> assumption | hypothesis
CONTRADICTS = "contradicts"        # evidence   -> assumption | hypothesis
ASSUMES = "assumes"                # hypothesis -> assumption
INFORMS = "informs"                # hypothesis -> decision
DECIDES = "decides"                # decision   -> action
PRODUCES = "produces"              # action     -> outcome
CALIBRATES = "calibrates"          # outcome    -> assumption | hypothesis
MEASURES = "measures"              # kpi        -> anything
AFFECTS = "affects"                # event | market | scenario -> anything
OWNS = "owns"                      # person | team -> anything
CONCERNS = "concerns"              # document | meeting -> anything
COMPETES_WITH = "competes_with"    # competitor <-> product | market
SUPERSEDES = "supersedes"          # any -> same kind

EDGE_KINDS = frozenset({
    SUPPORTS, CONTRADICTS, ASSUMES, INFORMS, DECIDES, PRODUCES, CALIBRATES,
    MEASURES, AFFECTS, OWNS, CONCERNS, COMPETES_WITH, SUPERSEDES,
})

# Edges whose direction encodes time or causation. A cycle in any of these is
# a modelling error -- an outcome cannot calibrate an assumption that the
# outcome itself produced.
ACYCLIC_EDGES = frozenset({ASSUMES, INFORMS, DECIDES, PRODUCES, SUPERSEDES})


class GraphError(ValueError):
    """The graph was asked to hold something it cannot honestly hold."""


# =============================================================================
# The tenant boundary, inside the canonical graph
# =============================================================================
class TenantOwned:
    """Declaration marker: this node or edge belongs to exactly one tenant.

    A plain class, and `isinstance` against it, for the same reason
    `core.tenant.TenantScoped` is one: it must mean "declared itself private",
    never "happens to have an attribute named tenant". A thing that becomes
    private by accident of shape is a thing that becomes PUBLIC by accident of
    shape the day somebody renames a field, and that day the failure is silent.

    The marker lives HERE, in the canonical model, rather than beside the
    private node kinds. The filter that keeps private nodes out of a scopeless
    read is part of the graph, and a graph that had to import the private layer
    to know what to hide would be the second reader this design exists to
    avoid.
    """

    tenant: TenantId

    @property
    def tenant_id(self) -> str:
        """The opaque owner, or "" when this thing declared privacy and then
        failed to carry an identity. "" is REFUSED by every reader below --
        it is never treated as public, and never treated as anyone's."""
        tenant = getattr(self, "tenant", None)
        return tenant.value if isinstance(tenant, TenantId) else ""


# --- what a reader decided about one node or edge ---------------------------
# Three outcomes, never two. Collapsing WITHHELD into "not in the result" is
# how a system tells a founder "you have no pipeline" when the truth is "you
# have pipeline and no authority over it".
SHOWN = "SHOWN"
WITHHELD = "WITHHELD"
REFUSED = "REFUSED"
READ_DECISIONS = frozenset({SHOWN, WITHHELD, REFUSED})

# --- the closed refusal vocabulary for the private layer ---------------------
# Named states, not messages, for the same reason `core.tenant.FAILURE_STATES`
# is closed: telemetry cannot count a bucket nobody named. Deliberately a
# SEPARATE vocabulary from tenant.FAILURE_STATES -- these are things that go
# wrong with a stored graph row, not with an authority -- and deliberately one
# closed set defined once, even though the persistence states are raised from
# `internal.py` rather than from here.
CROSS_TENANT = "CROSS_TENANT"
CROSS_VISIBILITY = "CROSS_VISIBILITY"
TENANT_BINDING_BROKEN = "TENANT_BINDING_BROKEN"
STALE_CONTRACT = "STALE_CONTRACT"
MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
EXPLICIT_NULL = "EXPLICIT_NULL"
UNKNOWN_ENDPOINT = "UNKNOWN_ENDPOINT"
PRIVATE_GRAPH_FAILURE_STATES = frozenset({
    CROSS_TENANT, CROSS_VISIBILITY, TENANT_BINDING_BROKEN, STALE_CONTRACT,
    MISSING_REQUIRED_FIELD, EXPLICIT_NULL, UNKNOWN_ENDPOINT,
})


class PrivateGraphRefused(Exception):
    """The private layer refused to hold or return something.

    Deliberately NOT a `ValueError`, and therefore deliberately NOT a
    `GraphError`. Refusals here travel through code that parses rows and
    coerces types, and an `except GraphError` written for a dangling edge would
    swallow a cross-tenant violation and carry on. `core.tenant.ScopeRefused`
    made the same choice for the same reason; a caller that wants to catch a
    boundary violation has to say so.
    """

    def __init__(self, failure_state: str, message: str):
        if failure_state not in PRIVATE_GRAPH_FAILURE_STATES:
            raise AssertionError(
                f"{failure_state!r} is not one of the named private-graph "
                f"failure states {sorted(PRIVATE_GRAPH_FAILURE_STATES)}; a "
                f"refusal without a state cannot be counted in telemetry")
        super().__init__(f"{failure_state}: {message}")
        self.failure_state = failure_state
        self.message = message


def read_scope(scope) -> Optional[TenantScope]:
    """The ONE place a caller's `scope` argument is turned into authority.

    `None` is a legitimate answer -- it means "read the public world" -- and it
    is the default of every reader on the graph. Everything else must be a
    live `TenantScope`.

    A bare string is refused rather than looked up, and that is the whole point
    of hard requirement 2: a tenant id string and a company id string are both
    IDENTITIES, and an identity is not an authorization. Accepting
    `scope="tnt_01J..."` would mean anyone who can read a node id can read the
    node, which is the confused deputy with a type annotation. A `TenantId` is
    refused here too, for exactly the same reason -- knowing who you are is not
    the same as having been told you may.
    """
    if scope is None:
        return None
    if isinstance(scope, (str, bytes)):
        raise ScopeRefused(
            STRING_REFUSED,
            "a graph read takes an established TenantScope or None; a tenant "
            "id string is an identity, not an authorization, and a company id "
            "is not even an identity")
    if not isinstance(scope, TenantScope):
        raise ScopeRefused(
            NO_ESTABLISHMENT_SOURCE,
            f"a graph read received {type(scope).__name__}, which is not an "
            f"established scope")
    scope.assert_live()
    return scope


def read_decision(item, scope: Optional[TenantScope]) -> str:
    """SHOWN / WITHHELD / REFUSED for one node or edge. THE mechanism.

    Everything that keeps a private node away from a scopeless caller is these
    six lines, and every reader on `BusinessGraph` routes through them -- one
    predicate, so an export path and a traversal path cannot drift into two
    filters that disagree. The drift is only ever discovered by the tenant who
    receives somebody else's row.

    A thing that declared itself `TenantOwned` and carries no typed identity is
    REFUSED, not shown. Untagged is not public: treating it as public is how a
    private node escapes the day a field is forgotten.
    """
    if not isinstance(item, TenantOwned):
        return SHOWN
    tenant = getattr(item, "tenant", None)
    if not isinstance(tenant, TenantId):
        return REFUSED
    if scope is None:
        return WITHHELD
    return SHOWN if scope.authorizes(tenant) else WITHHELD


@dataclass(frozen=True)
class GraphRead:
    """What a reader saw, and what it could not see.

    Mirrors `core.tenant.ScopedRead` on purpose, down to the empty-state
    vocabulary, because they answer the same question about two substrates and
    a founder-facing surface must not have to learn both.

    `withheld_private` and `refused` are the difference between an empty graph
    and a graph whose relevant nodes belong to somebody else. MISSING is not
    ZERO, and ABSENT is not NO_CHANGE.
    """

    nodes: Tuple[Node, ...] = ()
    edges: Tuple[Edge, ...] = ()
    scope_state: str = SCOPELESS_PUBLIC_ONLY
    withheld_private: int = 0
    refused: Tuple[str, ...] = ()

    def empty_state(self) -> str:
        if self.nodes or self.edges:
            return NON_EMPTY
        if self.withheld_private:
            return EMPTY_PRIVATE_WITHHELD
        if self.refused:
            return EMPTY_UNTAGGED_REFUSED
        return EMPTY_NO_ROWS


@dataclass(frozen=True)
class Node:
    """One thing the business contains, and where we learned about it."""
    node_id: str
    kind: str
    label: str
    source: str
    confidence: str = ""
    as_of: str = ""
    attrs: dict = field(default_factory=dict)

    @classmethod
    def permitted_kinds(cls) -> frozenset:
        """The vocabulary THIS class may be constructed with.

        Overridden by `PrivateNode` to a DISJOINT set. That disjointness is
        what makes PUBLIC != PRIVATE structural rather than a naming
        convention: `Node(kind="private.product", ...)` is refused, so a
        private kind cannot arrive wearing a public node's type, and
        `of_kind(PRODUCT)` cannot return an internal product line.
        """
        return NODE_KINDS

    def __post_init__(self):
        if self.kind not in self.permitted_kinds():
            raise GraphError(f"unknown node kind {self.kind!r}")
        if not self.node_id or not self.label:
            raise GraphError("a node needs an id and a label")
        # Provenance is the whole point. A node that cannot say where it came
        # from is indistinguishable from one the product made up, and the
        # absolute rules are unenforceable the moment one exists.
        if not self.source:
            raise GraphError(
                f"node {self.node_id!r} has no source; every node must say "
                f"where it came from")

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "kind": self.kind,
                "label": self.label, "source": self.source,
                "confidence": self.confidence, "as_of": self.as_of,
                "attrs": dict(self.attrs)}


@dataclass(frozen=True)
class Edge:
    """A relationship. `derived` says whether anyone could be wrong about it."""
    src: str
    dst: str
    kind: str
    derived: bool
    source: str = ""

    @classmethod
    def permitted_kinds(cls) -> frozenset:
        """Disjoint from `PrivateEdge.permitted_kinds()`, same reason as
        `Node.permitted_kinds()`: a private relationship cannot arrive
        wearing a public edge's type."""
        return EDGE_KINDS

    def __post_init__(self):
        if self.kind not in self.permitted_kinds():
            raise GraphError(f"unknown edge kind {self.kind!r}")
        if self.src == self.dst:
            raise GraphError(f"{self.kind} edge from {self.src!r} to itself")
        # A recorded edge is a judgment. Judgments have authors.
        if not self.derived and not self.source:
            raise GraphError(
                f"recorded {self.kind} edge {self.src}->{self.dst} has no "
                f"source; only derived edges may omit one")

    def key(self) -> Tuple[str, str, str]:
        return (self.src, self.dst, self.kind)

    def as_dict(self) -> dict:
        return {"src": self.src, "dst": self.dst, "kind": self.kind,
                "derived": self.derived, "source": self.source}


class BusinessGraph:
    """Nodes and edges, with the invariants that keep them honest.

    Deliberately in-memory and rebuildable. The durable record stays in the
    append-only event logs the subsystems already own; this is the projection
    they share. Making the graph the system of record would mean two sources
    of truth, and the older one would win every disagreement.
    """

    def __init__(self, nodes: Iterable[Node] = (),
                 edges: Iterable[Edge] = ()):
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[Tuple[str, str, str], Edge] = {}
        for node in nodes:
            self.add_node(node)
        for edge in edges:
            self.add_edge(edge)

    # -- construction -------------------------------------------------------
    def add_node(self, node: Node) -> Node:
        # A private node needs authority to be written, so it cannot come in
        # through the door that needs none. Refused rather than quietly
        # accepted-and-hidden: a caller that reached for the public door is a
        # caller who has not thought about which tenant this belongs to.
        if isinstance(node, TenantOwned):
            raise PrivateGraphRefused(
                CROSS_VISIBILITY,
                f"{node.node_id!r} is tenant-private; add it through "
                f"add_private_node(node, scope=...), which checks that the "
                f"scope authorizes its tenant")
        existing = self._nodes.get(node.node_id)
        if existing and existing.kind != node.kind:
            raise GraphError(
                f"{node.node_id!r} is already a {existing.kind}, cannot also "
                f"be a {node.kind}")
        self._nodes[node.node_id] = node
        return node

    def add_edge(self, edge: Edge) -> Edge:
        if isinstance(edge, TenantOwned):
            raise PrivateGraphRefused(
                CROSS_VISIBILITY,
                f"{edge.kind} edge {edge.src}->{edge.dst} is tenant-private; "
                f"add it through add_private_edge(edge, scope=...)")
        # A dangling edge is worse than a missing one: it renders as a real
        # relationship and resolves to nothing.
        for end in (edge.src, edge.dst):
            if end not in self._nodes:
                raise GraphError(
                    f"{edge.kind} edge references unknown node {end!r}")
            # A PUBLIC edge onto a private node is a leak with no attacker in
            # it: the edge is visible to everyone, so a scopeless traversal
            # would reach -- and name -- a node it may not read.
            if isinstance(self._nodes[end], TenantOwned):
                raise PrivateGraphRefused(
                    CROSS_VISIBILITY,
                    f"public {edge.kind} edge references private node {end!r}; "
                    f"a public edge onto a private node makes the private "
                    f"node reachable from a scopeless traversal")
        self._edges[edge.key()] = edge
        return edge

    @requires_tenant_scope
    def add_private_node(self, node: Node, *, scope: TenantScope) -> Node:
        """Write one tenant-private node. Authority is checked HERE.

        At the seam, not at the caller: every caller getting it right is a
        hope, the seam refusing is a property.
        """
        if not isinstance(node, TenantOwned) or not isinstance(node, Node):
            raise PrivateGraphRefused(
                CROSS_VISIBILITY,
                f"add_private_node received {type(node).__name__}, which is "
                f"not a tenant-owned graph node; a public node goes through "
                f"add_node")
        if not scope.authorizes(node.tenant):
            raise PrivateGraphRefused(
                CROSS_TENANT,
                f"scope for {scope.tenant.value} cannot write a node owned by "
                f"{node.tenant_id}")
        existing = self._nodes.get(node.node_id)
        if existing is not None and read_decision(existing, scope) != SHOWN:
            # Unreachable while node ids carry their tenant prefix, and kept
            # anyway: if that namespacing is ever weakened, this is the line
            # that stops one tenant overwriting another's node by id.
            raise PrivateGraphRefused(  # pragma: no cover - defence in depth
                CROSS_TENANT,
                f"{node.node_id!r} already exists and is not this tenant's")
        if existing is not None and existing.kind != node.kind:
            raise GraphError(
                f"{node.node_id!r} is already a {existing.kind}, cannot also "
                f"be a {node.kind}")
        self._nodes[node.node_id] = node
        return node

    @requires_tenant_scope
    def add_private_edge(self, edge: Edge, *, scope: TenantScope) -> Edge:
        """Write one tenant-private edge. Both ends must be this tenant's.

        The endpoint kinds are checked against one table rather than by any
        per-edge code: `SEGMENT_BUYS_PRODUCT` from a Contract to a Cohort is
        not a relationship anybody can render, and a graph that stores it will
        be asked to explain it later.
        """
        from intent_engine.business_graph.internal import (
            PRIVATE_EDGE_ENDPOINTS,
        )

        if not isinstance(edge, TenantOwned) or not isinstance(edge, Edge):
            raise PrivateGraphRefused(
                CROSS_VISIBILITY,
                f"add_private_edge received {type(edge).__name__}, which is "
                f"not a tenant-owned graph edge")
        if not scope.authorizes(edge.tenant):
            raise PrivateGraphRefused(
                CROSS_TENANT,
                f"scope for {scope.tenant.value} cannot write an edge owned "
                f"by {edge.tenant_id}")
        for end in (edge.src, edge.dst):
            node = self._nodes.get(end)
            if node is None:
                raise PrivateGraphRefused(
                    UNKNOWN_ENDPOINT,
                    f"{edge.kind} edge references unknown node {end!r}")
            if not isinstance(node, TenantOwned):
                raise PrivateGraphRefused(
                    CROSS_VISIBILITY,
                    f"private {edge.kind} edge references PUBLIC node "
                    f"{end!r}; the private edge kinds relate private things "
                    f"to private things, and a mixed edge is a new design "
                    f"decision rather than an integration detail")
            if node.tenant_id != edge.tenant_id:
                raise PrivateGraphRefused(
                    CROSS_TENANT,
                    f"{edge.kind} edge owned by {edge.tenant_id} references "
                    f"node {end!r} owned by {node.tenant_id}")
        want = PRIVATE_EDGE_ENDPOINTS[edge.kind]
        got = (self._nodes[edge.src].kind, self._nodes[edge.dst].kind)
        if got != want:
            raise GraphError(
                f"{edge.kind} relates {want[0]} -> {want[1]}, got "
                f"{got[0]} -> {got[1]}")
        self._edges[edge.key()] = edge
        return edge

    # -- reading ------------------------------------------------------------
    # Every reader below takes `scope` and DEFAULTS IT TO None, so public-only
    # is what a caller gets by forgetting. See `read_decision` for the filter
    # itself; nothing here re-implements it.
    def read(self, *, scope: Optional[TenantScope] = None) -> GraphRead:
        """Everything one reader may see, plus what it was not shown.

        The single reader. `nodes`, `of_kind`, `node`, the edge accessors and
        `provenance_of` are all views over this one call, which is why an
        export cannot filter differently from a traversal.

        An edge is shown only when the edge itself is shown AND both its
        endpoints are: that is what makes a traversal STOP at the tenant
        boundary instead of returning an edge whose far end resolves to
        nothing.
        """
        scope = read_scope(scope)
        shown_nodes, withheld, refused = [], 0, []
        for node in self._nodes.values():
            decision = read_decision(node, scope)
            if decision == SHOWN:
                shown_nodes.append(node)
            elif decision == WITHHELD:
                withheld += 1
            else:
                refused.append(node.node_id)
        visible = {n.node_id for n in shown_nodes}
        shown_edges = []
        for edge in self._edges.values():
            if read_decision(edge, scope) != SHOWN:
                withheld += 1
                continue
            if edge.src in visible and edge.dst in visible:
                shown_edges.append(edge)
        return GraphRead(
            nodes=tuple(shown_nodes), edges=tuple(shown_edges),
            scope_state=SCOPED if scope is not None else SCOPELESS_PUBLIC_ONLY,
            withheld_private=withheld, refused=tuple(sorted(refused)))

    def _all_nodes(self) -> List[Node]:
        """Every node regardless of tenant. NOT a query surface.

        Structural integrity is not a tenant question -- a dangling edge is a
        bug whoever owns it, and checking integrity over the public subset
        alone would report every private edge as dangling. Underscored, never
        exported, and used only by `assert_graph_invariants` below; the suite
        asserts that no public reader can reach it.
        """
        return list(self._nodes.values())

    def _all_edges(self) -> List[Edge]:
        return list(self._edges.values())

    @property
    def nodes(self) -> List[Node]:
        return list(self.read().nodes)

    @property
    def edges(self) -> List[Edge]:
        return list(self.read().edges)

    def node(self, node_id: str, *,
             scope: Optional[TenantScope] = None) -> Optional[Node]:
        """None for a node this reader may not see.

        Knowing a node id is not authorization. `None` here is the same answer
        a caller gets for a node that does not exist, on purpose: telling an
        unauthorized caller that the id EXISTS is itself a disclosure. The
        distinction a legitimate caller needs -- withheld versus absent -- is
        on `read().empty_state()`, where it is scoped.
        """
        found = self._nodes.get(node_id)
        if found is None:
            return None
        return found if read_decision(found, read_scope(scope)) == SHOWN else None

    def of_kind(self, kind: str, *,
                scope: Optional[TenantScope] = None) -> List[Node]:
        return [n for n in self.read(scope=scope).nodes if n.kind == kind]

    def out_edges(self, node_id: str, kind: str = "", *,
                  scope: Optional[TenantScope] = None) -> List[Edge]:
        return [e for e in self.read(scope=scope).edges
                if e.src == node_id and (not kind or e.kind == kind)]

    def in_edges(self, node_id: str, kind: str = "", *,
                 scope: Optional[TenantScope] = None) -> List[Edge]:
        return [e for e in self.read(scope=scope).edges
                if e.dst == node_id and (not kind or e.kind == kind)]

    def neighbours(self, node_id: str, kind: str = "", *,
                   scope: Optional[TenantScope] = None) -> List[Node]:
        read = self.read(scope=scope)
        by_id = {n.node_id: n for n in read.nodes}
        ids = {e.dst for e in read.edges
               if e.src == node_id and (not kind or e.kind == kind)}
        ids |= {e.src for e in read.edges
                if e.dst == node_id and (not kind or e.kind == kind)}
        return [by_id[i] for i in sorted(ids) if i in by_id]

    # -- the question the product exists to answer --------------------------
    def provenance_of(self, decision_id: str, *,
                      scope: Optional[TenantScope] = None) -> dict:
        """Everything a decision rests on, and what happened after it.

        This is the query the founder assistant needs and no subsystem could
        answer alone: which hypotheses informed a decision, which assumptions
        those hypotheses made, which evidence supported or CONTRADICTED each
        one, and which outcomes have since calibrated them.

        Contradicting evidence is returned beside supporting evidence rather
        than filtered out. Hiding it would be the single most damaging thing
        this structure could do, and it is explicitly forbidden.

        Scoped, and the walk uses ONE read: a traversal that re-queried per
        hop could pick up a node the first hop was not allowed to see, and an
        unknown id is refused whether it is absent or merely invisible.
        """
        read = self.read(scope=scope)
        if not any(n.node_id == decision_id for n in read.nodes):
            raise GraphError(f"unknown decision {decision_id!r}")
        edges = read.edges

        def _in(dst, kind):
            return [e.src for e in edges if e.dst == dst and e.kind == kind]

        def _out(src, kind):
            return [e.dst for e in edges if e.src == src and e.kind == kind]

        hypotheses = _in(decision_id, INFORMS)
        assumptions: List[str] = []
        for hypothesis in hypotheses:
            assumptions += _out(hypothesis, ASSUMES)

        supporting, contradicting = [], []
        for target in hypotheses + assumptions:
            supporting += _in(target, SUPPORTS)
            contradicting += _in(target, CONTRADICTS)

        actions = _out(decision_id, DECIDES)
        outcomes: List[str] = []
        for action in actions:
            outcomes += _out(action, PRODUCES)
        calibrated = [d for o in outcomes for d in _out(o, CALIBRATES)]

        uniq = lambda xs: sorted(set(xs))          # noqa: E731
        return {"decision": decision_id,
                "hypotheses": uniq(hypotheses),
                "assumptions": uniq(assumptions),
                "supporting_evidence": uniq(supporting),
                "contradicting_evidence": uniq(contradicting),
                "actions": uniq(actions),
                "outcomes": uniq(outcomes),
                "calibrates": uniq(calibrated)}

    def unsupported(self, kind: str = ASSUMPTION, *,
                    scope: Optional[TenantScope] = None) -> List[Node]:
        """Nodes of a kind that no evidence supports.

        The founder-facing value is the honest one: these are the beliefs the
        company is carrying without having checked. Surfacing them is the
        product; quietly treating them as established is the failure mode.
        """
        read = self.read(scope=scope)
        supported = {e.dst for e in read.edges if e.kind == SUPPORTS}
        return [n for n in read.nodes
                if n.kind == kind and n.node_id not in supported]

    def contested(self, *,
                  scope: Optional[TenantScope] = None) -> List[Node]:
        """Nodes with evidence on BOTH sides -- never silently resolved."""
        read = self.read(scope=scope)
        supported = {e.dst for e in read.edges if e.kind == SUPPORTS}
        against = {e.dst for e in read.edges if e.kind == CONTRADICTS}
        both = supported & against
        return [n for n in read.nodes if n.node_id in both]


def detect_cycles_in_mappings(edges, edge_type: str,
                              *, kind_key: str = "edge",
                              src_key: str = "from",
                              dst_key: str = "to") -> list:
    """Cycle detection over dict-shaped edges, for the domain graphs.

    `product/graph.py` and `executive/graph.py` each carried a byte-identical
    copy of this algorithm -- the same concept implemented three times in one
    repository, which is exactly what "one concept, exactly once" forbids. The
    two domain graphs keep their own edge VOCABULARY, which is legitimately
    theirs; they do not each need their own depth-first search.

    Deliberately preserves the legacy contract exactly -- a sorted list of
    tuples, each closing on the node it started from -- because the point is to
    remove duplication without changing behaviour their callers depend on.
    """
    adjacency: dict = {}
    for edge in edges:
        if edge[kind_key] == edge_type:
            adjacency.setdefault(edge[src_key], set()).add(edge[dst_key])
    cycles, visiting, visited = [], set(), set()

    def _walk(node, stack):
        if node in visiting:
            cycles.append(tuple(stack[stack.index(node):] + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        for nxt in sorted(adjacency.get(node, ())):
            _walk(nxt, stack + [nxt])
        visiting.discard(node)
        visited.add(node)

    for node in sorted(adjacency):
        _walk(node, [node])
    return sorted(set(cycles))


def detect_cycles(edges: Sequence[Edge], kind: str) -> List[List[str]]:
    """Cycles among edges of one kind. Same contract as the two graphs
    this generalises, so their callers can move over unchanged."""
    adjacency: Dict[str, List[str]] = {}
    for edge in edges:
        if edge.kind == kind:
            adjacency.setdefault(edge.src, []).append(edge.dst)

    cycles: List[List[str]] = []
    seen: Set[str] = set()
    stack: List[str] = []
    on_stack: Set[str] = set()

    def walk(node: str) -> None:
        seen.add(node)
        stack.append(node)
        on_stack.add(node)
        for nxt in sorted(adjacency.get(node, ())):
            if nxt in on_stack:
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif nxt not in seen:
                walk(nxt)
        stack.pop()
        on_stack.discard(node)

    for node in sorted(adjacency):
        if node not in seen:
            walk(node)
    return cycles


def assert_graph_invariants(graph: BusinessGraph) -> dict:
    """Everything that must be true, checked in one place.

    Returns a report rather than raising on the soft findings: an unsupported
    assumption is a real state of the world worth showing a founder, not a bug.
    Structural impossibilities -- dangling edges, causal cycles -- do raise,
    because nothing downstream can render them meaningfully.

    TWO AUDIENCES, TWO LEVELS OF DETAIL
    -----------------------------------
    Structure is checked over EVERY node and edge, private ones included: a
    dangling edge is a bug whoever owns it, and integrity checked over the
    public subset would report every private edge as dangling. The soft
    findings stay PUBLIC, and the private world is reported only as COUNTS --
    this report is a founder-facing artifact, and a private node id in it is a
    disclosure while a count is not.

    `private_nodes` and `private_edges` are always present, zero included.
    A counter that appears only when it is non-zero cannot say that nothing
    happened, and "no private nodes" is a thing a reader needs to be told.
    """
    all_nodes = {n.node_id for n in graph._all_nodes()}
    all_edges = graph._all_edges()
    for edge in all_edges:
        for end in (edge.src, edge.dst):
            if end not in all_nodes:
                raise GraphError(f"dangling edge end {end!r}")

    cycles: Dict[str, List[List[str]]] = {}
    for kind in sorted(ACYCLIC_EDGES):
        found = detect_cycles(all_edges, kind)
        if found:
            cycles[kind] = found
    if cycles:
        raise GraphError(f"causal cycles: {cycles}")

    public = graph.read()
    return {
        "nodes": len(public.nodes),
        "edges": len(public.edges),
        "derived_edges": sum(1 for e in public.edges if e.derived),
        "recorded_edges": sum(1 for e in public.edges if not e.derived),
        "unsupported_assumptions": [n.node_id
                                    for n in graph.unsupported(ASSUMPTION)],
        "contested_nodes": [n.node_id for n in graph.contested()],
        # Counts, never ids, and never omitted when zero.
        "private_nodes": sum(1 for n in graph._all_nodes()
                             if isinstance(n, TenantOwned)),
        "private_edges": sum(1 for e in all_edges
                             if isinstance(e, TenantOwned)),
    }

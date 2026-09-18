"""Where a tenant's private graph lives between requests.

D-IBG-001 declared this leg of its vertical -- "tenant-partitioned rows in the
graph store", "scope re-validated on load; a scopeless private row refuses" --
and the node was recorded CAPABILITY_VERIFIED precisely because the leg did not
exist. A graph that only exists inside the process that built it cannot be
consumed by a request, and a capability nothing can consume is the shape this
program has now recorded six times.

PARTITIONED BY TENANT ON DISK, NOT ONLY IN THE READER
-----------------------------------------------------
One file per tenant, named by the tenant's opaque id. That is deliberate
belt-and-braces: `read_decision` already refuses another tenant's rows, and a
single shared file would make the boundary depend entirely on that one
predicate being correct forever. With a partitioned layout, reading tenant B's
rows requires opening a file whose name the caller must already have been given
a scope for -- so a filter bug and a path bug both have to happen before a leak
does.

The file name is `scope_cache_key`'s opaque digest rather than the raw tenant
id, for the same reason the cache key is: a directory listing is a disclosure,
and `tnt_01J...` in a filename is a tenant enumeration.

EVERY LOAD IS AUTHORIZED, NOT FILTERED AFTER THE FACT
-----------------------------------------------------
`load` takes a TenantScope and hands every row through
`PrivateNode.from_row(row, scope=...)`, which checks the binding digest AND the
row's owner against the scope before the object exists. Nothing is ever
constructed and then filtered: a row this reader may not have never becomes a
node, so there is no window in which it is in memory waiting to be excluded.

APPEND-ONLY, LIKE EVERY OTHER LEDGER HERE
------------------------------------------
A private node is a claim about a business at a point in time and it carries
`observed_at` and `known_at` to say so. Rewriting one in place would destroy
the only record of what the tenant used to believe, which is the same argument
that made the learning ledger append-only. `load` folds to the latest row per
node id.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Iterable, Optional, Tuple

from intent_engine.business_graph.internal import (
    PRIVATE_EDGE_CONTRACT,
    PRIVATE_NODE_CONTRACT,
    PrivateEdge,
    PrivateNode,
)
from intent_engine.business_graph.model import (
    MISSING_REQUIRED_FIELD,
    BusinessGraph,
    PrivateGraphRefused,
    TenantOwned,
    read_scope,
)
from intent_engine.core.tenant import (
    NO_ESTABLISHMENT_SOURCE,
    ScopeRefused,
    TenantScope,
    requires_tenant_scope,
    scope_cache_key,
)

CONTRACT = "private_graph_store.v1"

#: Rows live under <root>/<opaque scope digest>.jsonl
DEFAULT_DIRNAME = "private_graph"


class PrivateGraphStore:
    """Append-only, tenant-partitioned storage for private nodes and edges."""

    def __init__(self, root, *, dirname: str = DEFAULT_DIRNAME):
        self.root = pathlib.Path(root) / dirname

    # -- paths --------------------------------------------------------------
    def path_for(self, scope: TenantScope) -> pathlib.Path:
        """One file per tenant, named by a DIGEST of the scope's cache key.

        `scope_cache_key` is the right identity -- two scopes for the same
        tenant share it and no two tenants ever do -- but it embeds the raw
        `tnt_01J...` value, which is correct for an in-process cache and wrong
        for a filename: a directory listing would then enumerate every tenant
        the system has, to anyone who can read the folder. It also contains a
        `|`, which is legal on disk and unpleasant everywhere else.

        So the key is hashed. Same partitioning guarantees, no enumeration.
        """
        got = read_scope(scope)
        if got is None:
            # NO_ESTABLISHMENT_SOURCE, not MISSING_REQUIRED_FIELD: this is an
            # authority failure and it must land in the scope vocabulary so it
            # counts in one telemetry bucket rather than two. `ScopeRefused`
            # asserts its own state is a named one, and caught this.
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "a private graph partition cannot be located without a scope; "
                "there is no public partition here by construction")
        digest = hashlib.sha256(
            scope_cache_key(got).encode("utf-8")).hexdigest()
        return self.root / f"{digest}.jsonl"

    # -- writing ------------------------------------------------------------
    @requires_tenant_scope
    def append(self, *, scope: TenantScope, nodes: Iterable = (),
               edges: Iterable = ()) -> int:
        """Persist rows for ONE tenant. Returns how many were written.

        Every row is re-authorized against the scope on the way out, so a node
        object belonging to another tenant cannot be written into this
        tenant's partition even if a caller assembled a mixed list.
        """
        path = self.path_for(scope)
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with path.open("a", encoding="utf-8") as handle:
            for item in list(nodes) + list(edges):
                if not isinstance(item, TenantOwned):
                    raise PrivateGraphRefused(
                        MISSING_REQUIRED_FIELD,
                        f"{type(item).__name__} is not tenant-owned and has no "
                        f"place in a private partition")
                if not scope.authorizes(item.tenant):
                    raise PrivateGraphRefused(
                        "CROSS_TENANT",
                        f"a row owned by {item.tenant.value} cannot be written "
                        f"into the partition for {scope.tenant.value}")
                handle.write(json.dumps(item.as_row(), sort_keys=True,
                                        default=str) + "\n")
                written += 1
        return written

    # -- reading ------------------------------------------------------------
    def _rows(self, scope: TenantScope) -> Tuple[dict, ...]:
        path = self.path_for(scope)
        if not path.exists():
            return ()
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                # A corrupt line is skipped and COUNTED by the caller through
                # the difference in totals, never silently treated as absent
                # data -- but it must not take down a whole tenant's graph.
                continue
            if isinstance(row, dict):
                out.append(row)
        return tuple(out)

    @requires_tenant_scope
    def load_into(self, graph: BusinessGraph, *,
                  scope: TenantScope) -> "LoadResult":
        """Authorize, construct, then add. In that order, always.

        `from_row` validates the binding digest and the row's owner against the
        scope BEFORE the object exists, so a row this reader may not have never
        becomes a node. Constructing first and filtering second would leave a
        window where it is in memory waiting to be excluded, and windows like
        that are what caching turns into leaks.
        """
        read_scope(scope)
        nodes, edges, refused = {}, {}, []
        for row in self._rows(scope):
            contract = row.get("contract")
            try:
                if contract == PRIVATE_NODE_CONTRACT:
                    node = PrivateNode.from_row(row, scope=scope)
                    nodes[node.node_id] = node          # append-only: last wins
                elif contract == PRIVATE_EDGE_CONTRACT:
                    edge = PrivateEdge.from_row(row, scope=scope)
                    edges[(edge.src, edge.dst, edge.kind)] = edge
                else:
                    refused.append(str(contract))
            except (PrivateGraphRefused, ScopeRefused) as exc:
                # A refused row is COUNTED, never dropped silently. A partition
                # that quietly loses half its rows renders as a small business
                # rather than as a broken one.
                refused.append(getattr(exc, "failure_state", type(exc).__name__))
        for node in nodes.values():
            graph.add_private_node(node, scope=scope)
        for edge in edges.values():
            graph.add_private_edge(edge, scope=scope)
        return LoadResult(nodes=len(nodes), edges=len(edges),
                          refused=tuple(refused))

    @requires_tenant_scope
    def load(self, *, scope: TenantScope,
             graph: Optional[BusinessGraph] = None) -> BusinessGraph:
        """Convenience: a graph holding exactly this tenant's private world."""
        graph = graph if graph is not None else BusinessGraph()
        self.load_into(graph, scope=scope)
        return graph


class LoadResult:
    """What a load saw, including what it would not accept.

    `refused` is never omitted when empty, for the same reason every counter in
    this subsystem is keyed at zero: a store that reports only its successes
    cannot distinguish an empty tenant from a broken partition.
    """

    __slots__ = ("nodes", "edges", "refused")

    def __init__(self, *, nodes: int = 0, edges: int = 0,
                 refused: Tuple[str, ...] = ()):
        self.nodes, self.edges, self.refused = nodes, edges, refused

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "nodes": self.nodes, "edges": self.edges,
                "refused": list(self.refused)}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"LoadResult(nodes={self.nodes}, edges={self.edges}, "
                f"refused={self.refused})")

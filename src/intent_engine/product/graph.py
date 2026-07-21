"""The proposal graph (T020) — typed edges, mirroring the research graph.

    addresses       proposal    -> problem        (derived)
    supports        opportunity -> proposal       (derived)
    arises_from     opportunity -> problem        (derived)
    supported_by    opportunity -> evidence       (derived)
    depends_on      proposal    -> proposal       (recorded)
    blocks          proposal    -> proposal       (recorded)
    alternative_to  proposal    -> proposal       (recorded, symmetric)
    implements      proposal    -> knowledge item (recorded)
    supersedes      proposal    -> proposal       (recorded)

Structural edges are DERIVED from the rows that created the nodes, so they
cannot drift from the thing they describe. Only judgment edges — the ones
a person or a rule actually asserts — are recorded.
"""
from __future__ import annotations

from dataclasses import dataclass

from intent_engine.product.records import (
    EDGE_ADDRESSES, EDGE_ALTERNATIVE_TO, EDGE_ARISES_FROM, EDGE_BLOCKS,
    EDGE_DEPENDS_ON, EDGE_IMPLEMENTS, EDGE_SUPERSEDES, EDGE_SUPPORTED_BY,
    EDGE_SUPPORTS, PROPOSAL_EDGES, ProductError,
)

GRAPH_VERSION = "proposal_graph.v1"
_RECORDED_EDGES = {EDGE_DEPENDS_ON, EDGE_BLOCKS, EDGE_ALTERNATIVE_TO,
                   EDGE_IMPLEMENTS, EDGE_SUPERSEDES}


@dataclass(frozen=True)
class ProposalGraph:
    graph_version: str = GRAPH_VERSION
    nodes: dict = None            # node_id -> {"type": ...}
    edges: tuple = ()             # ({"edge","from","to"}, ...)

    def out_edges(self, node_id: str, edge_type: str = None) -> list:
        return [e for e in self.edges
                if e["from"] == node_id
                and (edge_type is None or e["edge"] == edge_type)]

    def in_edges(self, node_id: str, edge_type: str = None) -> list:
        return [e for e in self.edges
                if e["to"] == node_id
                and (edge_type is None or e["edge"] == edge_type)]

    def dependencies_of(self, proposal_id: str) -> list:
        return sorted(e["to"] for e in self.out_edges(proposal_id,
                                                      EDGE_DEPENDS_ON))

    def blockers_of(self, proposal_id: str) -> list:
        """What blocks this proposal: its own unmet dependencies plus any
        proposal that declares it blocks this one."""
        return sorted(set(self.dependencies_of(proposal_id))
                      | {e["from"] for e in self.in_edges(proposal_id,
                                                          EDGE_BLOCKS)})

    def alternatives_of(self, proposal_id: str) -> list:
        return sorted({e["to"] for e in self.out_edges(proposal_id,
                                                       EDGE_ALTERNATIVE_TO)}
                      | {e["from"] for e in self.in_edges(proposal_id,
                                                          EDGE_ALTERNATIVE_TO)})


def detect_cycles(edges, edge_type: str = EDGE_DEPENDS_ON) -> list:
    """Deterministic cycle detection over one edge type. Returns the
    cycles found, sorted, so the report is reproducible."""
    adjacency = {}
    for edge in edges:
        if edge["edge"] == edge_type:
            adjacency.setdefault(edge["from"], set()).add(edge["to"])
    cycles, visiting, visited = [], set(), set()

    def _walk(node, stack):
        if node in visiting:
            start = stack.index(node)
            cycles.append(tuple(stack[start:] + [node]))
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


def build_graph(state, opportunities: dict, problems: dict,
                recorded_edges) -> ProposalGraph:
    """Derived structure + recorded judgment, assembled deterministically."""
    nodes, edges = {}, []

    for problem_id in sorted(problems):
        nodes[problem_id] = {"type": "problem"}
    for opportunity_id, opportunity in sorted(opportunities.items()):
        nodes[opportunity_id] = {"type": "opportunity"}
        edges.append({"edge": EDGE_ARISES_FROM, "from": opportunity_id,
                      "to": opportunity["problem_id"]})
        for ref in opportunity.get("evidence_references", []):
            ref_node = f"{ref['kind']}:{ref['ref_id']}"
            nodes.setdefault(ref_node, {"type": "evidence_reference",
                                        "kind": ref["kind"]})
            edges.append({"edge": EDGE_SUPPORTED_BY, "from": opportunity_id,
                          "to": ref_node})
    for proposal_id, proposal in sorted(state.proposals.items()):
        nodes[proposal_id] = {"type": "proposal"}
        edges.append({"edge": EDGE_ADDRESSES, "from": proposal_id,
                      "to": proposal["problem_id"]})
        edges.append({"edge": EDGE_SUPPORTS, "from": proposal["opportunity_id"],
                      "to": proposal_id})

    for edge in recorded_edges:
        if edge["edge"] not in _RECORDED_EDGES:
            raise ProductError(
                f"{edge['edge']!r} is a derived edge; it is not recorded "
                "separately, so it cannot drift from the rows that created it")
        nodes.setdefault(edge["to"], {"type": "knowledge_item"
                                      if edge["edge"] == EDGE_IMPLEMENTS
                                      else "proposal"})
        edges.append(dict(edge))

    return ProposalGraph(nodes=nodes, edges=tuple(edges))


def assert_graph_invariants(graph: ProposalGraph) -> dict:
    """Structural guarantees, checked rather than assumed."""
    problems = []
    proposals = [n for n, meta in graph.nodes.items()
                 if meta["type"] == "proposal"]
    opportunities = [n for n, meta in graph.nodes.items()
                     if meta["type"] == "opportunity"]

    for edge in graph.edges:
        if edge["edge"] not in PROPOSAL_EDGES:
            problems.append(f"unknown edge type {edge['edge']!r}")

    for proposal_id in proposals:
        addressed = graph.out_edges(proposal_id, EDGE_ADDRESSES)
        if len(addressed) != 1:
            problems.append(
                f"proposal {proposal_id} addresses {len(addressed)} problems; "
                "one proposal solves one problem")
        if not graph.in_edges(proposal_id, EDGE_SUPPORTS):
            problems.append(f"proposal {proposal_id} has no supporting "
                            "opportunity (orphan node)")

    for opportunity_id in opportunities:
        if not graph.out_edges(opportunity_id, EDGE_SUPPORTED_BY):
            problems.append(
                f"opportunity {opportunity_id} has no evidence reference "
                "(orphan node)")
        if len(graph.out_edges(opportunity_id, EDGE_ARISES_FROM)) != 1:
            problems.append(f"opportunity {opportunity_id} arises from "
                            "other than exactly one problem")

    cycles = detect_cycles(graph.edges, EDGE_DEPENDS_ON)
    if cycles:
        problems.append(f"dependency cycles among proposals: {cycles}")

    # alternative_to is symmetric, and is not combined with depends_on:
    # two proposals cannot both be interchangeable and sequenced.
    alternatives = {(e["from"], e["to"]) for e in graph.edges
                    if e["edge"] == EDGE_ALTERNATIVE_TO}
    for a, b in sorted(alternatives):
        if (b, a) not in alternatives:
            problems.append(
                f"alternative_to {a} -> {b} has no matching {b} -> {a}; the "
                "relation is symmetric")
    dependencies = {(e["from"], e["to"]) for e in graph.edges
                    if e["edge"] in (EDGE_DEPENDS_ON, EDGE_BLOCKS)}
    for a, b in sorted(alternatives):
        if (a, b) in dependencies or (b, a) in dependencies:
            problems.append(
                f"{a} and {b} are recorded as both alternatives and "
                "dependency-linked; a pair is one or the other")

    for node_id, meta in sorted(graph.nodes.items()):
        if meta["type"] == "problem":
            continue
        if not graph.out_edges(node_id) and not graph.in_edges(node_id):
            problems.append(f"node {node_id} has no edges (orphan node)")

    if problems:
        raise ProductError(f"proposal graph invariants violated: {problems}")
    return {"graph_version": graph.graph_version,
            "nodes": len(graph.nodes), "edges": len(graph.edges),
            "proposals": len(proposals), "opportunities": len(opportunities),
            "invariants": "ok"}


def sequence(graph: ProposalGraph, proposal_ids) -> list:
    """A deterministic build ORDER, which is a different question from
    priority. Highest priority does not imply first: a dependency can put
    a lower-priority proposal ahead of it.

    Kahn's algorithm with a stable tie-break, so the same graph always
    yields the same order.
    """
    wanted = set(proposal_ids)
    incoming = {pid: {d for d in graph.dependencies_of(pid) if d in wanted}
                for pid in wanted}
    ordered, remaining = [], dict(incoming)
    while remaining:
        ready = sorted(pid for pid, deps in remaining.items() if not deps)
        if not ready:
            raise ProductError(
                f"cannot sequence: a dependency cycle remains among "
                f"{sorted(remaining)}")
        for pid in ready:
            ordered.append(pid)
            remaining.pop(pid)
        for deps in remaining.values():
            deps.difference_update(ready)
    return ordered

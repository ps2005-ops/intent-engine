"""The decision graph (T021) — cascading effects made explicit.

    contextualizes  context   -> candidate     (derived)
    renders         package   -> context       (derived)
    addresses       candidate -> reference     (derived)
    depends_on      decision  -> decision      (recorded)
    enables         decision  -> decision      (recorded)
    invalidates     decision  -> decision      (recorded)
    supersedes      decision  -> decision      (recorded)

Structural edges are DERIVED from the rows that created the nodes, so they
cannot drift from the thing they describe. Only judgment edges — the ones
a person or a rule actually asserts — are recorded.

`invalidates` is the edge that makes a cascade visible: when one decision
lands, the decisions it invalidates stop being current, and a queue that
does not know this keeps offering the founder work that is already moot.
"""
from __future__ import annotations

from dataclasses import dataclass

from intent_engine.executive.records import (
    DECISION_EDGES, EDGE_ADDRESSES, EDGE_CONTEXTUALIZES, EDGE_DEPENDS_ON,
    EDGE_ENABLES, EDGE_INVALIDATES, EDGE_RENDERS, EDGE_SUPERSEDES,
    RECORDED_EDGES, ExecutiveError,
)
from intent_engine.business_graph.model import (
    detect_cycles_in_mappings,
)

GRAPH_VERSION = "decision_graph.v1"


@dataclass(frozen=True)
class DecisionGraph:
    graph_version: str = GRAPH_VERSION
    nodes: dict = None
    edges: tuple = ()

    def out_edges(self, node_id: str, edge_type: str = None) -> list:
        return [e for e in self.edges
                if e["from"] == node_id
                and (edge_type is None or e["edge"] == edge_type)]

    def in_edges(self, node_id: str, edge_type: str = None) -> list:
        return [e for e in self.edges
                if e["to"] == node_id
                and (edge_type is None or e["edge"] == edge_type)]

    def dependencies_of(self, node_id: str) -> list:
        return sorted(e["to"] for e in self.out_edges(node_id,
                                                      EDGE_DEPENDS_ON))

    def invalidated_by(self, node_id: str) -> list:
        """What this node would make moot if it landed."""
        return sorted(e["to"] for e in self.out_edges(node_id,
                                                      EDGE_INVALIDATES))

    def enabled_by(self, node_id: str) -> list:
        return sorted(e["to"] for e in self.out_edges(node_id, EDGE_ENABLES))

    def cascade_from(self, node_id: str) -> dict:
        """One hop of consequence, reported rather than applied. This
        subsystem states what a choice would set in motion; it sets
        nothing in motion itself."""
        return {"node_id": node_id,
                "would_invalidate": self.invalidated_by(node_id),
                "would_enable": self.enabled_by(node_id),
                "waits_on": self.dependencies_of(node_id),
                "note": ("a reported consequence, not an applied one — "
                         "nothing here changes another record")}


def detect_cycles(edges, edge_type: str = EDGE_DEPENDS_ON) -> list:
    """Deterministic cycle detection over one edge type.

    Delegates to the canonical implementation. This module previously carried
    its own byte-identical copy; the edge VOCABULARY below is legitimately
    this subsystem's, the depth-first search was not.
    """
    return detect_cycles_in_mappings(edges, edge_type)


def build_graph(state, recorded_edges) -> DecisionGraph:
    nodes, edges = {}, []

    for candidate_id, candidate in sorted(state.candidates.items()):
        nodes[candidate_id] = {"type": "candidate"}
        for ref in candidate.get("references", []):
            ref_node = f"{ref['kind']}:{ref['ref_id']}"
            nodes.setdefault(ref_node, {"type": "reference",
                                        "kind": ref["kind"]})
            edges.append({"edge": EDGE_ADDRESSES, "from": candidate_id,
                          "to": ref_node})
    for context_id, context in sorted(state.contexts.items()):
        nodes[context_id] = {"type": "context"}
        edges.append({"edge": EDGE_CONTEXTUALIZES, "from": context_id,
                      "to": context["candidate_id"]})
    for package_id, package in sorted(state.packages.items()):
        nodes[package_id] = {"type": "package"}
        edges.append({"edge": EDGE_RENDERS, "from": package_id,
                      "to": package["context_id"]})

    for edge in recorded_edges:
        if edge["edge"] not in RECORDED_EDGES:
            raise ExecutiveError(
                f"{edge['edge']!r} is a derived edge; it is not recorded "
                "separately, so it cannot drift from the rows that created it")
        for endpoint in (edge["from"], edge["to"]):
            nodes.setdefault(endpoint, {"type": "candidate"})
        edges.append(dict(edge))

    return DecisionGraph(nodes=nodes, edges=tuple(edges))


def assert_graph_invariants(graph: DecisionGraph) -> dict:
    """Structural guarantees, checked rather than assumed."""
    problems = []
    packages = [n for n, m in graph.nodes.items() if m["type"] == "package"]
    contexts = [n for n, m in graph.nodes.items() if m["type"] == "context"]
    candidates = [n for n, m in graph.nodes.items() if m["type"] == "candidate"]

    for edge in graph.edges:
        if edge["edge"] not in DECISION_EDGES:
            problems.append(f"unknown edge type {edge['edge']!r}")

    for package_id in packages:
        rendered = graph.out_edges(package_id, EDGE_RENDERS)
        if len(rendered) != 1:
            problems.append(
                f"package {package_id} renders {len(rendered)} contexts; a "
                "package renders exactly one")
    for context_id in contexts:
        held = graph.out_edges(context_id, EDGE_CONTEXTUALIZES)
        if len(held) != 1:
            problems.append(
                f"context {context_id} contextualizes {len(held)} candidates; "
                "a context belongs to exactly one")
    for candidate_id in candidates:
        if not graph.out_edges(candidate_id, EDGE_ADDRESSES) \
                and not graph.in_edges(candidate_id):
            problems.append(
                f"candidate {candidate_id} addresses no reference and has no "
                "incoming edge (orphan node)")

    cycles = detect_cycles(graph.edges, EDGE_DEPENDS_ON)
    if cycles:
        problems.append(f"dependency cycles among decisions: {cycles}")

    # A pair cannot both depend on and invalidate each other: waiting for a
    # thing that would make you moot is not a state anybody can act on.
    dependencies = {(e["from"], e["to"]) for e in graph.edges
                    if e["edge"] == EDGE_DEPENDS_ON}
    invalidations = {(e["from"], e["to"]) for e in graph.edges
                     if e["edge"] == EDGE_INVALIDATES}
    for a, b in sorted(invalidations):
        if (a, b) in dependencies or (b, a) in dependencies:
            problems.append(
                f"{a} and {b} are recorded as both dependency-linked and "
                "invalidating; a pair is one or the other")
        if (b, a) in invalidations:
            problems.append(
                f"{a} and {b} each invalidate the other, which resolves to "
                "nothing actionable")

    for node_id, meta in sorted(graph.nodes.items()):
        if meta["type"] == "reference":
            continue
        if not graph.out_edges(node_id) and not graph.in_edges(node_id):
            problems.append(f"node {node_id} has no edges (orphan node)")

    if problems:
        raise ExecutiveError(f"decision graph invariants violated: {problems}")
    return {"graph_version": graph.graph_version, "nodes": len(graph.nodes),
            "edges": len(graph.edges), "packages": len(packages),
            "contexts": len(contexts), "candidates": len(candidates),
            "invariants": "ok"}


def order_by_dependency(graph: DecisionGraph, node_ids) -> list:
    """A deterministic order the dependency graph permits — a different
    question from which decision deserves attention first."""
    wanted = set(node_ids)
    incoming = {nid: {d for d in graph.dependencies_of(nid) if d in wanted}
                for nid in wanted}
    ordered, remaining = [], dict(incoming)
    while remaining:
        ready = sorted(nid for nid, deps in remaining.items() if not deps)
        if not ready:
            raise ExecutiveError(
                f"cannot order: a dependency cycle remains among "
                f"{sorted(remaining)}")
        for nid in ready:
            ordered.append(nid)
            remaining.pop(nid)
        for deps in remaining.values():
            deps.difference_update(ready)
    return ordered


__all__ = ["DecisionGraph", "GRAPH_VERSION", "assert_graph_invariants",
           "build_graph", "detect_cycles", "order_by_dependency",
           "EDGE_ENABLES", "EDGE_SUPERSEDES"]

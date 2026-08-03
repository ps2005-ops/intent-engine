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
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# --- node kinds -------------------------------------------------------------
# The vocabulary is fixed on purpose. A connector that needs a new kind is
# usually a connector trying to keep its own shape; the answer is almost always
# to map onto an existing kind. Growing this list is a design decision, not an
# integration detail.
PERSON = "person"
TEAM = "team"
CUSTOMER = "customer"
COMPETITOR = "competitor"
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
    PERSON, TEAM, CUSTOMER, COMPETITOR, MARKET, PRODUCT, PROJECT, DOCUMENT,
    MEETING, RISK, KPI, DECISION, EVIDENCE, ASSUMPTION, EVENT, ACTION,
    OUTCOME, HYPOTHESIS, SCENARIO,
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

    def __post_init__(self):
        if self.kind not in NODE_KINDS:
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

    def __post_init__(self):
        if self.kind not in EDGE_KINDS:
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
        existing = self._nodes.get(node.node_id)
        if existing and existing.kind != node.kind:
            raise GraphError(
                f"{node.node_id!r} is already a {existing.kind}, cannot also "
                f"be a {node.kind}")
        self._nodes[node.node_id] = node
        return node

    def add_edge(self, edge: Edge) -> Edge:
        # A dangling edge is worse than a missing one: it renders as a real
        # relationship and resolves to nothing.
        for end in (edge.src, edge.dst):
            if end not in self._nodes:
                raise GraphError(
                    f"{edge.kind} edge references unknown node {end!r}")
        self._edges[edge.key()] = edge
        return edge

    # -- reading ------------------------------------------------------------
    @property
    def nodes(self) -> List[Node]:
        return list(self._nodes.values())

    @property
    def edges(self) -> List[Edge]:
        return list(self._edges.values())

    def node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def of_kind(self, kind: str) -> List[Node]:
        return [n for n in self._nodes.values() if n.kind == kind]

    def out_edges(self, node_id: str, kind: str = "") -> List[Edge]:
        return [e for e in self._edges.values()
                if e.src == node_id and (not kind or e.kind == kind)]

    def in_edges(self, node_id: str, kind: str = "") -> List[Edge]:
        return [e for e in self._edges.values()
                if e.dst == node_id and (not kind or e.kind == kind)]

    def neighbours(self, node_id: str, kind: str = "") -> List[Node]:
        ids = {e.dst for e in self.out_edges(node_id, kind)}
        ids |= {e.src for e in self.in_edges(node_id, kind)}
        return [self._nodes[i] for i in sorted(ids) if i in self._nodes]

    # -- the question the product exists to answer --------------------------
    def provenance_of(self, decision_id: str) -> dict:
        """Everything a decision rests on, and what happened after it.

        This is the query the founder assistant needs and no subsystem could
        answer alone: which hypotheses informed a decision, which assumptions
        those hypotheses made, which evidence supported or CONTRADICTED each
        one, and which outcomes have since calibrated them.

        Contradicting evidence is returned beside supporting evidence rather
        than filtered out. Hiding it would be the single most damaging thing
        this structure could do, and it is explicitly forbidden.
        """
        if decision_id not in self._nodes:
            raise GraphError(f"unknown decision {decision_id!r}")
        hypotheses = [e.src for e in self.in_edges(decision_id, INFORMS)]
        assumptions: List[str] = []
        for hypothesis in hypotheses:
            assumptions += [e.dst for e in self.out_edges(hypothesis, ASSUMES)]

        supporting, contradicting = [], []
        for target in hypotheses + assumptions:
            supporting += [e.src for e in self.in_edges(target, SUPPORTS)]
            contradicting += [e.src for e in self.in_edges(target, CONTRADICTS)]

        actions = [e.dst for e in self.out_edges(decision_id, DECIDES)]
        outcomes: List[str] = []
        for action in actions:
            outcomes += [e.dst for e in self.out_edges(action, PRODUCES)]
        calibrated = [e.dst for o in outcomes
                      for e in self.out_edges(o, CALIBRATES)]

        uniq = lambda xs: sorted(set(xs))          # noqa: E731
        return {"decision": decision_id,
                "hypotheses": uniq(hypotheses),
                "assumptions": uniq(assumptions),
                "supporting_evidence": uniq(supporting),
                "contradicting_evidence": uniq(contradicting),
                "actions": uniq(actions),
                "outcomes": uniq(outcomes),
                "calibrates": uniq(calibrated)}

    def unsupported(self, kind: str = ASSUMPTION) -> List[Node]:
        """Nodes of a kind that no evidence supports.

        The founder-facing value is the honest one: these are the beliefs the
        company is carrying without having checked. Surfacing them is the
        product; quietly treating them as established is the failure mode.
        """
        return [n for n in self.of_kind(kind)
                if not self.in_edges(n.node_id, SUPPORTS)]

    def contested(self) -> List[Node]:
        """Nodes with evidence on BOTH sides -- never silently resolved."""
        out = []
        for node in self._nodes.values():
            if (self.in_edges(node.node_id, SUPPORTS)
                    and self.in_edges(node.node_id, CONTRADICTS)):
                out.append(node)
        return out


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
    """
    for edge in graph.edges:
        for end in (edge.src, edge.dst):
            if graph.node(end) is None:
                raise GraphError(f"dangling edge end {end!r}")

    cycles: Dict[str, List[List[str]]] = {}
    for kind in sorted(ACYCLIC_EDGES):
        found = detect_cycles(graph.edges, kind)
        if found:
            cycles[kind] = found
    if cycles:
        raise GraphError(f"causal cycles: {cycles}")

    return {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "derived_edges": sum(1 for e in graph.edges if e.derived),
        "recorded_edges": sum(1 for e in graph.edges if not e.derived),
        "unsupported_assumptions": [n.node_id
                                    for n in graph.unsupported(ASSUMPTION)],
        "contested_nodes": [n.node_id for n in graph.contested()],
    }

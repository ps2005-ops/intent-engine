"""Causal-engine pillar #1, smallest honest scale: the scrap supply-web
graph, v0. Task 6 of the overnight execution plan (2026-07-15).

Nodes and edges, populated DETERMINISTICALLY (no LLM anywhere in this
module) from existing scrap-check and weigh-in EntityMemoryRecords --
scrap_estimate.py already writes these two real record shapes (marked
with `_SCRAP_CHECK_MARKER`/`_WEIGHIN_MARKER` prefixes on decision_text)
every time a real photo gets estimated or a real weigh-in gets logged.
This module reads that existing real data; it writes nothing new to
entity_memory.

Real, honest population, stated plainly: a scrap-check record's entity_id
becomes a "supplier" node (the yard/account a lot was checked against),
and its classified lot_type becomes a "material" node; a "supplies" edge
connects them, citing the record_id as provenance. A weigh-in for the
same (entity_id, lot_type) pair adds its own record_id as ADDITIONAL
provenance on that same edge (real confirming evidence, not a new
relationship). "buyer" nodes and "buys_from"/"ships_material" edges are
schema-supported (per the task's own NamedTuple shape) but have ZERO real
population source anywhere in this codebase today -- no "who bought the
processed scrap" concept exists yet. Left empty honestly, not fabricated
to look populated.

SCOPE WALLS, per Task 6's own spec: no news ingestion, no LLM population,
no shock semantics (mechanism integration is later, supervised work). No
rendering in any CLI yet.
"""

import json
from pathlib import Path
from typing import Dict, List, NamedTuple, Set, Union

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from .db import get_connection
from .entity_memory import DEFAULT_PATH, normalize_entity_id, read_records

DEFAULT_GRAPH_PATH = Path("data/entity_graph.db")

_SCRAP_CHECK_MARKER = "[scrap-metal check] "
_WEIGHIN_MARKER = "[scrap-metal weigh-in] "

NodeKind = Literal["supplier", "material", "buyer", "entity"]
EdgeKind = Literal["supplies", "buys_from", "ships_material"]


class Node(NamedTuple):
    node_id: str
    kind: NodeKind
    label: str


class Edge(NamedTuple):
    src: str
    dst: str
    kind: EdgeKind
    first_seen: str
    source_record_ids: List[str]


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            label TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS edges (
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            kind TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            source_record_ids TEXT NOT NULL,
            PRIMARY KEY (src, dst, kind)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst)")
    conn.commit()


def _material_node_id(lot_type: str) -> str:
    return f"material:{lot_type}"


def _supplier_node_id(entity_id: str) -> str:
    return f"supplier:{normalize_entity_id(entity_id)}"


def build_graph_from_entity_memory(
    supplier_entity_ids: List[str],
    entity_memory_path: Union[str, Path] = DEFAULT_PATH,
    graph_path: Union[str, Path] = DEFAULT_GRAPH_PATH,
) -> Dict[str, int]:
    """Scans real EntityMemoryRecords for the given supplier_entity_ids
    (a caller-supplied list, since entity_memory has no "list all real
    entities" index today -- this function does not invent one, it
    consumes what's already there per entity) for scrap-check and
    weigh-in markers, and derives supplier/material nodes plus "supplies"
    edges. Deterministic parsing only -- no LLM call anywhere in this
    function. Returns real counts (nodes_added, edges_added) for the
    caller to report, not silently swallowed."""
    conn = get_connection(graph_path)
    _ensure_schema(conn)

    nodes: Dict[str, Node] = {}
    edges: Dict[tuple, Edge] = {}

    for entity_id in supplier_entity_ids:
        records = read_records(entity_id, path=entity_memory_path)
        for record in records:
            lot_type = None
            if record.decision_text.startswith(_SCRAP_CHECK_MARKER):
                raw = record.decision_text[len(_SCRAP_CHECK_MARKER):]
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, AttributeError):
                    continue
                if not isinstance(parsed, dict) or parsed.get("is_scrap_metal_lot") is False:
                    continue  # malformed, or a real photo that wasn't scrap metal at all -- no material to graph
                lot_type = parsed.get("lot_type")
            elif record.decision_text.startswith(_WEIGHIN_MARKER):
                raw = record.decision_text[len(_WEIGHIN_MARKER):]
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, AttributeError):
                    continue
                if not isinstance(parsed, dict):
                    continue
                lot_type = parsed.get("lot_type")
            else:
                continue

            # "unclear"/"not_applicable" are real, honest hedge values in the
            # closed LotType taxonomy, not real material categories -- never
            # graphed as if they were a specific material.
            if not lot_type or lot_type in ("unclear", "not_applicable"):
                continue

            supplier_id = _supplier_node_id(entity_id)
            material_id = _material_node_id(lot_type)
            nodes.setdefault(supplier_id, Node(supplier_id, "supplier", normalize_entity_id(entity_id)))
            nodes.setdefault(material_id, Node(material_id, "material", lot_type))

            edge_key = (supplier_id, material_id, "supplies")
            if edge_key in edges:
                existing = edges[edge_key]
                if record.record_id not in existing.source_record_ids:
                    edges[edge_key] = existing._replace(
                        source_record_ids=existing.source_record_ids + [record.record_id]
                    )
            else:
                edges[edge_key] = Edge(
                    src=supplier_id, dst=material_id, kind="supplies",
                    first_seen=record.timestamp, source_record_ids=[record.record_id],
                )

    conn.execute("DELETE FROM nodes")
    conn.execute("DELETE FROM edges")
    for node in nodes.values():
        conn.execute("INSERT INTO nodes (node_id, kind, label) VALUES (?, ?, ?)", node)
    for edge in edges.values():
        conn.execute(
            "INSERT INTO edges (src, dst, kind, first_seen, source_record_ids) VALUES (?, ?, ?, ?, ?)",
            (edge.src, edge.dst, edge.kind, edge.first_seen, json.dumps(edge.source_record_ids)),
        )
    conn.commit()
    conn.close()

    return {"nodes_added": len(nodes), "edges_added": len(edges)}


def _read_all_nodes(graph_path: Union[str, Path]) -> List[Node]:
    graph_path = Path(graph_path)
    if not graph_path.exists():
        return []
    conn = get_connection(graph_path)
    _ensure_schema(conn)
    rows = conn.execute("SELECT node_id, kind, label FROM nodes").fetchall()
    conn.close()
    return [Node(*row) for row in rows]


def _read_all_edges(graph_path: Union[str, Path]) -> List[Edge]:
    graph_path = Path(graph_path)
    if not graph_path.exists():
        return []
    conn = get_connection(graph_path)
    _ensure_schema(conn)
    rows = conn.execute("SELECT src, dst, kind, first_seen, source_record_ids FROM edges").fetchall()
    conn.close()
    return [Edge(row[0], row[1], row[2], row[3], json.loads(row[4])) for row in rows]


class ReachableNode(NamedTuple):
    node_id: str
    hops: int
    path_edges: List[Edge]  # the real edge(s) connecting this node back toward the origin


def affected_by(node_id: str, hops: int = 2, graph_path: Union[str, Path] = DEFAULT_GRAPH_PATH) -> List[ReachableNode]:
    """Real, deterministic breadth-first reachability over the (undirected,
    for propagation purposes -- a shock at a material can propagate back
    to every supplier of it, and a shock at a supplier can propagate to
    every material it supplies) graph, capped at `hops`. Every returned
    node carries the real edge(s) that connect it back toward the
    origin -- provenance, not just a bare id list."""
    if hops < 0:
        raise ValueError(f"hops must be >= 0, got {hops}")

    all_edges = _read_all_edges(graph_path)
    adjacency: Dict[str, List[Edge]] = {}
    for edge in all_edges:
        adjacency.setdefault(edge.src, []).append(edge)
        adjacency.setdefault(edge.dst, []).append(edge)

    visited: Set[str] = {node_id}
    frontier: List[str] = [node_id]
    results: List[ReachableNode] = []

    for current_hop in range(1, hops + 1):
        next_frontier = []
        for current_node in frontier:
            for edge in adjacency.get(current_node, []):
                neighbor = edge.dst if edge.src == current_node else edge.src
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                next_frontier.append(neighbor)
                results.append(ReachableNode(node_id=neighbor, hops=current_hop, path_edges=[edge]))
        frontier = next_frontier
        if not frontier:
            break

    return results

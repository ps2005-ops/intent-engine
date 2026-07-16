import json

from intent_engine.core.entity_graph import (
    _SCRAP_CHECK_MARKER,
    _WEIGHIN_MARKER,
    _read_all_edges,
    _read_all_nodes,
    affected_by,
    build_graph_from_entity_memory,
)
from intent_engine.core.entity_memory import EntityMemoryRecord, SqliteEntityMemoryWriter


def _scrap_check_record(entity_id, lot_type, is_scrap_metal_lot=True, timestamp="2026-01-01T00:00:00+00:00"):
    # Minimal but real-shaped: only the keys build_graph_from_entity_memory
    # actually reads, matching the real fields scrap_estimate.py's
    # ScrapEstimate.model_dump_json() would include (is_scrap_metal_lot,
    # lot_type) among many others this module doesn't need.
    payload = json.dumps({"is_scrap_metal_lot": is_scrap_metal_lot, "lot_type": lot_type})
    return EntityMemoryRecord(
        entity_id=entity_id, source="voice", decision_text=f"{_SCRAP_CHECK_MARKER}{payload}",
        goals=[], constraints=[], timestamp=timestamp,
    )


def _weighin_record(entity_id, lot_type, timestamp="2026-01-02T00:00:00+00:00"):
    payload = json.dumps({"lot_type": lot_type})
    return EntityMemoryRecord(
        entity_id=entity_id, source="voice", decision_text=f"{_WEIGHIN_MARKER}{payload}",
        goals=[], constraints=[], timestamp=timestamp,
    )


def _seed(entity_memory_path, records):
    writer = SqliteEntityMemoryWriter(path=entity_memory_path)
    for r in records:
        writer.write(r)


# --- Bar (a): real record shapes, hand-derived expected counts -------------


def test_build_graph_from_real_record_shapes_matches_hand_derived_counts(tmp_path):
    """3 real-shaped scrap-check records (2 suppliers x overlapping
    material types) + 1 weigh-in reinforcing an existing edge. Hand-derived
    expectation, computed independently of the graph-building code:
    - suppliers: "Ace Metals", "Best Scrap Yard" -> 2 supplier nodes
    - materials: "sealed_motors_alternators_starters", "loose_mixed_steel" -> 2 material nodes
    - total nodes: 4
    - edges: (Ace Metals -> sealed_motors), (Ace Metals -> loose_mixed_steel),
      (Best Scrap Yard -> sealed_motors) -> 3 edges
    """
    entity_path = tmp_path / "entity_memory.db"
    graph_path = tmp_path / "entity_graph.db"

    _seed(entity_path, [
        _scrap_check_record("Ace Metals", "sealed_motors_alternators_starters"),
        _scrap_check_record("Ace Metals", "loose_mixed_steel"),
        _scrap_check_record("Best Scrap Yard", "sealed_motors_alternators_starters"),
        _weighin_record("Ace Metals", "sealed_motors_alternators_starters"),  # reinforces edge 1, not a new one
    ])

    result = build_graph_from_entity_memory(["Ace Metals", "Best Scrap Yard"], entity_memory_path=entity_path, graph_path=graph_path)

    assert result == {"nodes_added": 4, "edges_added": 3}
    nodes = _read_all_nodes(graph_path)
    edges = _read_all_edges(graph_path)
    assert len(nodes) == 4
    assert len(edges) == 3
    assert {n.kind for n in nodes} == {"supplier", "material"}


def test_build_graph_excludes_non_scrap_metal_photos(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    graph_path = tmp_path / "entity_graph.db"
    _seed(entity_path, [
        _scrap_check_record("Ace Metals", lot_type="not_applicable", is_scrap_metal_lot=False),
    ])
    result = build_graph_from_entity_memory(["Ace Metals"], entity_memory_path=entity_path, graph_path=graph_path)
    assert result == {"nodes_added": 0, "edges_added": 0}


def test_build_graph_excludes_unclear_and_not_applicable_lot_types(tmp_path):
    """"unclear"/"not_applicable" are real hedge values, not material
    categories -- never graphed as a specific material."""
    entity_path = tmp_path / "entity_memory.db"
    graph_path = tmp_path / "entity_graph.db"
    _seed(entity_path, [
        _scrap_check_record("Ace Metals", lot_type="unclear"),
        _scrap_check_record("Ace Metals", lot_type="not_applicable"),
    ])
    result = build_graph_from_entity_memory(["Ace Metals"], entity_memory_path=entity_path, graph_path=graph_path)
    assert result == {"nodes_added": 0, "edges_added": 0}


def test_every_edge_carries_real_source_record_ids(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    graph_path = tmp_path / "entity_graph.db"
    _seed(entity_path, [
        _scrap_check_record("Ace Metals", "sealed_motors_alternators_starters"),
        _weighin_record("Ace Metals", "sealed_motors_alternators_starters"),
    ])
    build_graph_from_entity_memory(["Ace Metals"], entity_memory_path=entity_path, graph_path=graph_path)

    edges = _read_all_edges(graph_path)
    assert len(edges) == 1
    assert len(edges[0].source_record_ids) == 2  # both the scrap-check AND the weigh-in


def test_build_graph_against_the_real_repo_data_is_honest_when_empty():
    """Smoke test against this repo's ACTUAL entity_memory.db -- confirmed
    (2026-07-15) to have zero real scrap-check records yet. Proves the
    function handles real-but-empty input honestly (0 nodes, 0 edges),
    never fabricating content to look populated."""
    from intent_engine.core.entity_memory import DEFAULT_PATH
    result = build_graph_from_entity_memory(["Ace Metals", "Best Scrap Yard", "Anyone"], entity_memory_path=DEFAULT_PATH)
    assert result == {"nodes_added": 0, "edges_added": 0}


# --- Bar (b): affected_by() on a constructed, hand-checkable 6-node graph --


def _build_six_node_graph(graph_path):
    """A -- supplies --> M1 <-- supplies -- B -- supplies --> M2 <-- supplies -- C
    Hand-checkable reachability from A, undirected, capped at hops:
    hops=1: {M1}
    hops=2: {M1, B} (B reached via M1)
    hops=3: {M1, B, M2} (M2 reached via B)
    """
    entity_path = graph_path.parent / "entity_memory_for_6node.db"
    _seed(entity_path, [
        _scrap_check_record("A", "sealed_motors_alternators_starters"),
        _scrap_check_record("B", "sealed_motors_alternators_starters"),
        _scrap_check_record("B", "loose_mixed_steel"),
        _scrap_check_record("C", "loose_mixed_steel"),
    ])
    build_graph_from_entity_memory(["A", "B", "C"], entity_memory_path=entity_path, graph_path=graph_path)


def test_affected_by_returns_correct_reachable_set_at_hops_1(tmp_path):
    graph_path = tmp_path / "entity_graph.db"
    _build_six_node_graph(graph_path)

    from intent_engine.core.entity_graph import _supplier_node_id
    result = affected_by(_supplier_node_id("A"), hops=1, graph_path=graph_path)
    reached_ids = {r.node_id for r in result}
    assert reached_ids == {"material:sealed_motors_alternators_starters"}
    assert all(r.hops == 1 for r in result)


def test_affected_by_returns_correct_reachable_set_at_hops_2(tmp_path):
    graph_path = tmp_path / "entity_graph.db"
    _build_six_node_graph(graph_path)

    from intent_engine.core.entity_graph import _supplier_node_id
    result = affected_by(_supplier_node_id("A"), hops=2, graph_path=graph_path)
    reached_ids = {r.node_id for r in result}
    assert reached_ids == {"material:sealed_motors_alternators_starters", "supplier:b"}


def test_affected_by_returns_correct_reachable_set_at_hops_3(tmp_path):
    graph_path = tmp_path / "entity_graph.db"
    _build_six_node_graph(graph_path)

    from intent_engine.core.entity_graph import _supplier_node_id
    result = affected_by(_supplier_node_id("A"), hops=3, graph_path=graph_path)
    reached_ids = {r.node_id for r in result}
    assert reached_ids == {"material:sealed_motors_alternators_starters", "supplier:b", "material:loose_mixed_steel"}
    # material:loose_mixed_steel reached via supplier:b, real provenance carried
    loose_steel = next(r for r in result if r.node_id == "material:loose_mixed_steel")
    assert loose_steel.hops == 3
    assert loose_steel.path_edges[0].src == "supplier:b" or loose_steel.path_edges[0].dst == "supplier:b"


def test_affected_by_stops_expanding_when_frontier_is_exhausted(tmp_path):
    """C is 4 hops from A -- with hops=3, C must NOT appear (it's beyond
    the cap), proving the BFS actually respects the cap rather than
    walking the whole graph regardless."""
    graph_path = tmp_path / "entity_graph.db"
    _build_six_node_graph(graph_path)

    from intent_engine.core.entity_graph import _supplier_node_id
    result = affected_by(_supplier_node_id("A"), hops=3, graph_path=graph_path)
    reached_ids = {r.node_id for r in result}
    assert _supplier_node_id("C") not in reached_ids


def test_affected_by_raises_for_negative_hops(tmp_path):
    graph_path = tmp_path / "entity_graph.db"
    _build_six_node_graph(graph_path)
    import pytest
    from intent_engine.core.entity_graph import _supplier_node_id
    with pytest.raises(ValueError):
        affected_by(_supplier_node_id("A"), hops=-1, graph_path=graph_path)

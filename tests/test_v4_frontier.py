"""The executor is held to the product's standard.

The first frontier ranked on dependencies alone and promoted three policy nodes
to READY whose data gate stood at 2 against 100. A human noticed and reset them
by hand. A planner that needs manual correction every session is a document
that happens to be executable, so the gate is now mechanical and these are its
proofs.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent
FRONTIER = HERE.parent / "docs" / "execution" / "v4" / "frontier.py"
GRAPH = HERE.parent / "docs" / "execution" / "v4" / "TASK_GRAPH.yaml"


def _load():
    spec = importlib.util.spec_from_file_location("v4_frontier", FRONTIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = _load()


def task(tid, *, deps=(), gates=None, status="DERIVED", priority=3):
    out = {"id": tid, "dependencies": list(deps), "status": status,
           "priority": priority, "title": tid}
    if gates:
        out["minimum_data"] = gates
    return out


# --- the gate --------------------------------------------------------------

def test_dependency_satisfied_but_data_insufficient_is_blocked():
    tasks = [task("A", status="COMPLETE"),
             task("B", deps=["A"], gates={"prospective_decisions": 100})]
    got = F.effective(tasks, {"prospective_decisions": 2})
    assert got["B"][0] == "BLOCKED_DATA"


def test_dependency_satisfied_and_data_sufficient_is_ready():
    tasks = [task("A", status="COMPLETE"),
             task("B", deps=["A"], gates={"prospective_decisions": 100})]
    got = F.effective(tasks, {"prospective_decisions": 100})
    assert got["B"][0] == "READY"


def test_a_node_with_no_gate_is_ready_once_dependencies_clear():
    tasks = [task("A", status="COMPLETE"), task("B", deps=["A"])]
    assert F.effective(tasks, {})["B"][0] == "READY"


def test_every_gate_must_be_satisfied_not_just_one():
    tasks = [task("B", gates={"a": 10, "b": 10})]
    got = F.effective(tasks, {"a": 50, "b": 1})
    assert got["B"][0] == "BLOCKED_DATA"
    unmet = [d for d in got["B"][1] if not d["satisfied"]]
    assert [d["metric"] for d in unmet] == ["b"]


def test_a_missing_metric_blocks_and_never_passes():
    """'We looked and there are none' and 'we could not look' differ."""
    got = F.effective([task("B", gates={"never_measured": 1})], {})
    assert got["B"][0] == "BLOCKED_DATA"
    assert got["B"][1][0]["current"] is None


def test_a_zero_measurement_is_not_the_same_as_unmeasured():
    got = F.effective([task("B", gates={"m": 1})], {"m": 0})
    assert got["B"][0] == "BLOCKED_DATA"
    assert got["B"][1][0]["current"] == 0


def test_a_node_becomes_ready_automatically_when_data_arrives():
    """No manual edit. This is the whole repair."""
    tasks = [task("B", gates={"prospective_decisions": 100})]
    assert F.effective(tasks, {"prospective_decisions": 99})["B"][0] \
        == "BLOCKED_DATA"
    assert F.effective(tasks, {"prospective_decisions": 100})["B"][0] \
        == "READY"


def test_a_node_reverts_honestly_when_data_is_invalidated():
    tasks = [task("B", gates={"prospective_decisions": 100})]
    assert F.effective(tasks, {"prospective_decisions": 120})["B"][0] == "READY"
    assert F.effective(tasks, {"prospective_decisions": 3})["B"][0] \
        == "BLOCKED_DATA"


# --- dependency semantics ---------------------------------------------------

def test_only_complete_satisfies_a_dependency():
    """A blocked node is terminal for itself and still parks its dependents."""
    for parent in ("BLOCKED_DATA", "BLOCKED_EXTERNAL", "INVALIDATED",
                   "NEEDS_REPAIR", "IN_PROGRESS"):
        tasks = [task("A", status=parent), task("B", deps=["A"])]
        assert F.effective(tasks, {})["B"][0] == "WAITING_DEPENDENCY"


def test_a_declared_terminal_state_is_not_overruled_by_a_measurement():
    tasks = [task("B", status="COMPLETE", gates={"m": 100})]
    assert F.effective(tasks, {"m": 0})["B"][0] == "COMPLETE"


def test_an_owner_blocker_is_respected_over_a_satisfied_gate():
    tasks = [task("B", status="BLOCKED_OWNER", gates={"m": 1})]
    assert F.effective(tasks, {"m": 999})["B"][0] == "BLOCKED_OWNER"


# --- no special cases -------------------------------------------------------

def test_the_frontier_contains_no_task_identifiers():
    """The bug was fixed generically or it was not fixed."""
    source = FRONTIER.read_text(encoding="utf-8")
    for tid in ("B-POL-002", "B-HACK-001", "B-VOI-002", "K-CYC",
                "A-RD-", "prospective_decisions"):
        assert tid not in source, (
            f"{tid} is named in frontier.py; the data gate must be generic")


# --- the real graph ---------------------------------------------------------

def test_the_real_graph_parses_and_has_no_dangling_dependencies():
    tasks = F.load_graph(GRAPH)
    ids = {t["id"] for t in tasks}
    dangling = [(t["id"], d) for t in tasks
                for d in (t.get("dependencies") or ()) if d not in ids]
    assert dangling == []


def test_the_real_graph_stores_no_derivable_status():
    """Derived state written into the graph is the drift class itself."""
    tasks = F.load_graph(GRAPH)
    stored = [t["id"] for t in tasks
              if t.get("status") in ("READY", "WAITING_DEPENDENCY",
                                     "BLOCKED_DATA")]
    assert stored == [], (
        f"{stored} store a status the frontier derives; remove it and let the "
        "calculator own it, or TASK_GRAPH and BLOCKERS will disagree again")


def test_every_declared_gate_is_a_mapping_of_metric_to_number():
    tasks = F.load_graph(GRAPH)
    for t in tasks:
        gate = t.get("minimum_data")
        if gate in (None, "none"):
            continue
        assert isinstance(gate, dict), (
            f"{t['id']} declares minimum_data as prose; a gate a machine "
            f"cannot evaluate is a gate a human has to remember: {gate!r}")
        for metric, need in gate.items():
            assert isinstance(need, (int, float)), (metric, need)

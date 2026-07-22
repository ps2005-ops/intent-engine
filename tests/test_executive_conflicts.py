"""T021 the typed conflict taxonomy and the Conflict Summary.

Every conflict detected from real upstream facts, typed, and stated —
never averaged. 0 model calls. 0 network.
"""
import ast
import inspect
from pathlib import Path

import pytest

from intent_engine.executive import conflict_summary, detect_conflicts
from intent_engine.executive.conflicts import classify_unknown
from intent_engine.executive.records import CONFLICT_KINDS

REPO_ROOT = Path(__file__).resolve().parents[1]
OLD = "2025-01-01T00:00:00+00:00"
NOW = "2026-07-21T00:00:00+00:00"


def test_evidence_conflict_research_disputes_growth_asserts():
    conflicts = detect_conflicts({
        "research": {"stances": ["CONFLICTING"]},
        "experiments": [{"experiment_id": "E1", "label": "DIFFERENCE OBSERVED"}]})
    kinds = {c["kind"] for c in conflicts}
    assert "evidence_conflict" in kinds
    conflict = next(c for c in conflicts if c["kind"] == "evidence_conflict")
    subsystems = {s["subsystem"] for s in conflict["sides"]}
    assert subsystems == {"research", "growth"}


def test_metric_conflict_when_the_settling_metric_is_unavailable():
    conflicts = detect_conflicts({
        "research": {"stances": ["CONFLICTING"]},
        "metrics": [{"metric_name": "activation", "status": "UNAVAILABLE"}]})
    assert "metric_conflict" in {c["kind"] for c in conflicts}


def test_staleness_conflict_is_distinct_from_timeline_conflict():
    """Two inputs true at different times, never reconciled — a different
    problem from a scheduling disagreement."""
    conflicts = detect_conflicts({"input_timestamps": [OLD, NOW]})
    kinds = {c["kind"] for c in conflicts}
    assert "staleness_conflict" in kinds
    assert "timeline_conflict" not in kinds
    # and the timeline conflict arises from a different fact entirely
    timeline = detect_conflicts({
        "decision_horizon": "immediate",
        "unmet_dependencies": ["D1", "D2"]})
    assert "timeline_conflict" in {c["kind"] for c in timeline}
    assert "staleness_conflict" not in {c["kind"] for c in timeline}


def test_priority_conflict_urgency_without_supporting_evidence():
    conflicts = detect_conflicts({
        "crm": {"category": "AT_RISK"},
        "research": {"stances": ["UNKNOWN"]}})
    assert "priority_conflict" in {c["kind"] for c in conflicts}


def test_strategy_conflict_urgent_work_with_no_alignment():
    conflicts = detect_conflicts({"crm": {"category": "AT_RISK"},
                                  "alignment": None})
    assert "strategy_conflict" in {c["kind"] for c in conflicts}


def test_dependency_conflict_ready_but_unmet():
    conflicts = detect_conflicts({"decision_ready": True,
                                  "unmet_dependencies": ["D1"]})
    assert "dependency_conflict" in {c["kind"] for c in conflicts}


def test_resource_conflict_needs_budget_none_declared():
    conflicts = detect_conflicts({"needs_budget": True,
                                  "budget_declared": False})
    assert "resource_conflict" in {c["kind"] for c in conflicts}


def test_every_detected_conflict_is_in_the_closed_taxonomy():
    conflicts = detect_conflicts({
        "research": {"stances": ["CONFLICTING"]},
        "experiments": [{"experiment_id": "E1", "label": "DIFFERENCE OBSERVED"}],
        "metrics": [{"status": "UNAVAILABLE"}],
        "crm": {"category": "AT_RISK"}, "alignment": None,
        "input_timestamps": [OLD, NOW],
        "needs_budget": True, "budget_declared": False,
        "decision_horizon": "immediate", "unmet_dependencies": ["D1"]})
    for conflict in conflicts:
        assert conflict["kind"] in CONFLICT_KINDS


def test_detection_is_deterministic():
    facts = {"research": {"stances": ["CONFLICTING"]},
             "experiments": [{"experiment_id": "E1",
                              "label": "DIFFERENCE OBSERVED"}]}
    assert detect_conflicts(facts) == detect_conflicts(facts)


def test_an_unclassifiable_disagreement_is_still_recorded():
    conflict = classify_unknown([{"subsystem": "x", "position": "a"}],
                                "two sources disagree and no rule fits")
    assert conflict["kind"] == "unknown_conflict"


# =============================================================================
# The Conflict Summary — a report, not a resolution
# =============================================================================

def test_the_summary_names_both_sides_and_produces_no_average():
    summary = conflict_summary(detect_conflicts({
        "research": {"stances": ["CONFLICTING"]},
        "experiments": [{"experiment_id": "E1",
                         "label": "DIFFERENCE OBSERVED"}]}))
    assert summary["total"] >= 1
    assert summary["resolution"] == "none — a disagreement is reported, not " \
                                    "averaged"
    for kind, entries in summary["by_kind"].items():
        for entry in entries:
            assert entry["sides"]           # both sides named


def test_a_conflict_with_an_unavailable_side_is_still_classified():
    """Analytics UNAVAILABLE is a side, not a reason to drop the conflict."""
    conflicts = detect_conflicts({
        "research": {"stances": ["CONFLICTING"]},
        "metrics": [{"status": "UNAVAILABLE"}]})
    metric = [c for c in conflicts if c["kind"] == "metric_conflict"]
    assert metric
    positions = {tuple(s.get("position")) if isinstance(s.get("position"), list)
                 else s.get("position") for s in metric[0]["sides"]}
    assert any("UNAVAILABLE" in str(p) for p in positions)


def test_no_conflict_module_code_computes_an_average():
    """Refusal A: no mean/weighted average/overall score over conflicting
    inputs exists in the conflicts module."""
    from intent_engine.executive import conflicts as module
    tree = ast.parse(inspect.getsource(module))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for banned in ("mean", "average", "weighted", "blend", "overall_score",
                   "combined_score"):
        assert banned not in names, banned
    # the only division in the module is the seconds-to-days unit
    # conversion in staleness detection, never a combination of two
    # conflicting values into one
    divisors = [n.right for n in ast.walk(tree)
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)]
    assert all(isinstance(d, ast.Constant) and d.value == 86400.0
               for d in divisors), "the only division is the day conversion"
    # and the summary carries no combined numeric verdict
    summary = conflict_summary(detect_conflicts({
        "research": {"stances": ["CONFLICTING"]},
        "experiments": [{"experiment_id": "E1",
                         "label": "DIFFERENCE OBSERVED"}]}))
    assert "score" not in summary and "verdict" not in summary
    assert summary["resolution"].startswith("none")

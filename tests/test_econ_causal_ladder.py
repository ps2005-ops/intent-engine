"""The causal ladder, the shock engine, and the controls that make them real.

Section 32's causal block: synthetic known-DAG recovery, a spurious-
correlation control, lag recovery, and shock propagation.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import causal as C
from intent_engine.econ import seed as SEED
from intent_engine.econ import shock as SH
from intent_engine.econ.vocabulary import EconError


def _edge(cause="a", effect="b", level=C.L1_LAGGED, **kw):
    base = dict(cause=cause, effect=effect, sign=C.UP,
                mechanism="a stated path from a to b",
                evidence_level=level, evidence="lagged co-movement at 5 days",
                falsifier="b does not move after a for a full quarter",
                lag_days=5, sample_start="2024-01-01", sample_end="2026-01-01",
                sample_n=100, confidence=0.6)
    if level >= C.CAUSAL_LANGUAGE_FLOOR:
        base["competing_explanation"] = "a common driver moves both"
    base.update(kw)
    return C.edge(**base)


# --- the ladder -------------------------------------------------------------
def test_causal_language_is_refused_below_level_three():
    for level in (C.L0_CORRELATION, C.L1_LAGGED, C.L2_INFORMATION):
        e = _edge(level=level, evidence="something at this level")
        assert not e.may_state_causation
        assert "causes" not in e.statement()
        assert "ASSOCIATED WITH" in e.statement()


def test_causal_language_is_permitted_at_level_three_and_above():
    for level in (C.L3_STRUCTURAL, C.L4_EXPERIMENT, C.L5_SYNTHETIC):
        e = _edge(level=level, evidence="an identifying restriction")
        assert e.may_state_causation
        assert "causes" in e.statement()


def test_transfer_entropy_alone_does_not_license_causation():
    """The specific error the ladder exists to prevent."""
    e = _edge(level=C.L2_INFORMATION,
              evidence="directional transfer entropy from a to b, 0.31 "
                       "against a shuffled null of 0.04")
    assert not e.may_state_causation
    assert "does not establish direction" in e.statement()


def test_an_identified_edge_must_name_its_competing_explanation():
    with pytest.raises(EconError, match="competing explanation"):
        _edge(level=C.L3_STRUCTURAL, competing_explanation="")


def test_a_level_is_not_reached_by_repeating_the_evidence_below_it():
    e = _edge(level=C.L0_CORRELATION, evidence="they move together")
    with pytest.raises(EconError, match="attrition"):
        C.raise_level(e, to=C.L3_STRUCTURAL, evidence="they move together",
                      competing_explanation="a common driver")


def test_an_edge_cannot_be_silently_demoted():
    g = C.StructuralCausalGraph([_edge(level=C.L4_EXPERIMENT,
                                       evidence="a policy change on a date")])
    with pytest.raises(EconError, match="would demote it"):
        g.add(_edge(level=C.L0_CORRELATION, evidence="they move together"))


def test_an_edge_that_cannot_be_wrong_is_refused():
    with pytest.raises(EconError, match="not a finding"):
        _edge(falsifier="")


def test_an_edge_with_no_mechanism_is_refused():
    with pytest.raises(EconError, match="arrow drawn on it"):
        _edge(mechanism="")


# --- synthetic known-DAG recovery ------------------------------------------
def test_a_known_chain_is_recovered_end_to_end():
    """x -> y -> z, with x and z NOT directly connected.

    The engine must reach z from x through y, must report it as second-order,
    and must not invent a direct edge.
    """
    g = C.StructuralCausalGraph([
        _edge("x", "y", lag_days=3),
        _edge("y", "z", lag_days=7),
    ])
    result = SH.propagate(g, quantity="x", direction=C.UP, as_of="2026-01-01")
    reached = {e.quantity: e for e in result.effects}
    assert set(reached) == {"y", "z"}
    assert reached["y"].order == 1 and reached["z"].order == 2
    assert reached["y"].path == ("x", "y")
    assert reached["z"].path == ("x", "y", "z")
    assert g.get("x", "z") is None, "a direct edge was invented"


def test_lag_is_recovered_cumulatively_along_the_chain():
    g = C.StructuralCausalGraph([
        _edge("x", "y", lag_days=3), _edge("y", "z", lag_days=7)])
    result = SH.propagate(g, quantity="x", as_of="2026-01-01")
    reached = {e.quantity: e for e in result.effects}
    assert reached["y"].lag_days == 3
    assert reached["z"].lag_days == 10, (
        "a second-order effect must arrive after BOTH lags; reporting it at "
        "the second edge's lag alone makes the chain unfalsifiable at any "
        "particular moment")


def test_signs_compose_so_two_falls_make_a_rise():
    g = C.StructuralCausalGraph([
        _edge("x", "y", sign=C.DOWN), _edge("y", "z", sign=C.DOWN)])
    reached = {e.quantity: e for e in
               SH.propagate(g, quantity="x", as_of="2026-01-01").effects}
    assert reached["y"].direction == C.DOWN
    assert reached["z"].direction == C.UP


def test_confidence_compounds_downward_and_never_rises():
    g = C.StructuralCausalGraph([
        _edge("x", "y", confidence=0.7), _edge("y", "z", confidence=0.7)])
    reached = {e.quantity: e for e in
               SH.propagate(g, quantity="x", as_of="2026-01-01").effects}
    assert reached["y"].confidence == pytest.approx(0.7)
    assert reached["z"].confidence == pytest.approx(0.49)
    assert reached["z"].confidence < reached["y"].confidence


def test_the_weakest_link_decides_whether_a_chain_may_claim_causation():
    """A level-1 edge downstream of a level-5 edge is still level 1."""
    g = C.StructuralCausalGraph([
        _edge("x", "y", level=C.L5_SYNTHETIC, evidence="synthetic control"),
        _edge("y", "z", level=C.L1_LAGGED)])
    reached = {e.quantity: e for e in
               SH.propagate(g, quantity="x", as_of="2026-01-01").effects}
    assert reached["y"].may_state_causation
    assert not reached["z"].may_state_causation, (
        "a chain laundered a lagged correlation through an identified edge")
    assert "has tended to" in reached["z"].sentence()


# --- spurious correlation control ------------------------------------------
def test_a_spurious_pair_cannot_reach_causal_language_by_accumulation():
    """The control: co-movement, repeated, is still co-movement.

    Ten years of data raises `sample_n`. It does not raise the level, and
    there is no function that lets it.
    """
    e = _edge(level=C.L0_CORRELATION, sample_n=2500,
              evidence="correlated at 0.91 over ten years")
    assert not e.may_state_causation
    g = C.StructuralCausalGraph([e])
    assert g.summary()["may_state_causation"] == 0
    assert g.summary()["association_only"] == 1


def test_a_min_level_filter_removes_weak_edges_from_propagation():
    g = C.StructuralCausalGraph([
        _edge("x", "y", level=C.L0_CORRELATION, evidence="co-moves"),
        _edge("x", "w", level=C.L3_STRUCTURAL, evidence="a restriction")])
    strict = SH.propagate(g, quantity="x", as_of="2026-01-01",
                          min_evidence_level=C.L3_STRUCTURAL)
    assert {e.quantity for e in strict.effects} == {"w"}
    assert "y" in strict.unreached


# --- cycles and bounds ------------------------------------------------------
def test_a_cycle_terminates():
    g = C.StructuralCausalGraph([_edge("x", "y"), _edge("y", "x")])
    result = SH.propagate(g, quantity="x", as_of="2026-01-01")
    assert {e.quantity for e in result.effects} == {"y"}


def test_the_stronger_path_wins_and_paths_are_not_summed():
    """Two routes to one quantity are one reading, not two."""
    g = C.StructuralCausalGraph([
        _edge("x", "y", confidence=0.9), _edge("y", "z", confidence=0.9),
        _edge("x", "w", confidence=0.2), _edge("w", "z", confidence=0.2)])
    reached = {e.quantity: e for e in
               SH.propagate(g, quantity="x", as_of="2026-01-01").effects}
    assert reached["z"].confidence == pytest.approx(0.81)
    assert reached["z"].path == ("x", "y", "z")


def test_unreached_quantities_are_reported_rather_than_omitted():
    g = C.StructuralCausalGraph([_edge("x", "y"), _edge("p", "q")])
    result = SH.propagate(g, quantity="x", as_of="2026-01-01")
    assert set(result.unreached) == {"p", "q"}


# --- the shipped seed -------------------------------------------------------
def test_the_seed_graph_is_honest_about_what_it_knows():
    g = SEED.seed_graph()
    summary = g.summary()
    assert summary["edges"] >= 15
    # The map of what this system actually knows: mostly associations.
    assert summary["association_only"] > summary["may_state_causation"], (
        "most of the seed graph claims causation, which would mean the "
        "engine has identified more mechanisms than it has evidence for")
    for e in g.edges():
        assert e.falsifier.strip()
        if e.may_state_causation:
            assert e.competing_explanation.strip()


def test_every_named_shock_propagates_or_says_it_cannot():
    g = SEED.seed_graph()
    for name in SH.NAMED_SHOCKS:
        result = SH.evaluate_structural_shock(g, name, as_of="2026-08-24")
        assert result.as_dict()["shock"]
        for e in result.effects:
            assert e.confidence <= 1.0
            assert e.sentence()


def test_an_unknown_shock_raises_rather_than_returning_nothing():
    with pytest.raises(KeyError, match="not a named shock"):
        SH.evaluate_structural_shock(SEED.seed_graph(), "made_up",
                                     as_of="2026-08-24")


def test_confidence_bands_are_words_not_decimals():
    assert SH.confidence_band(0.81) == "likely"
    assert SH.confidence_band(0.45) == "plausible"
    assert SH.confidence_band(0.25) == "weak"
    assert SH.confidence_band(0.05) == "speculative"

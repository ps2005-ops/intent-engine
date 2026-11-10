"""Two demand figures that disagree, and are never averaged into one.

The central test is `test_backlog_up_with_cancellations_up_is_a_tension`. Both
figures moved UP, so the chain's direction rule reads them as agreeing; they
are the clearest disagreement in the vocabulary, because a rise in
cancellations is committed demand leaving. The chain cannot say so and is
right not to — CANCELLATIONS is a leak out of the pool, not a step along it —
which leaves cancellations compared to nothing at all.

The second theme is that nothing here produces a verdict. There is no field
reading "demand strong", and `test_no_overall_demand_verdict_is_produced`
exists to keep it that way: the flattening is the failure, not the absence.
"""
from __future__ import annotations

import pytest

from intent_engine.market import demand_chain as DC
from intent_engine.market import demand_tension as DT


def reading(state, direction, company="ACME", ids=("ev1",)):
    return DC.DemandReading(company_id=company, state=state,
                            direction=direction, basis=f"{state} {direction}",
                            evidence_ids=tuple(ids))


class Chain:
    """The shape `demand_chain.build` returns, with only what this layer reads."""

    def __init__(self, company_id="ACME", **states):
        self.company_id = company_id
        self.readings = {s: DC.unknown(company_id, s) for s in DC.STATES}
        for state, direction in states.items():
            self.readings[state] = reading(state, direction, company_id)


# --- polarity ---------------------------------------------------------------

def test_a_rise_in_cancellations_points_down_for_demand():
    """The one state in the vocabulary whose rise is bad news."""
    assert DT.demand_sign(DC.CANCELLATIONS, "UP") == "DOWN"
    assert DT.demand_sign(DC.CANCELLATIONS, "DOWN") == "UP"


def test_every_other_state_points_the_way_it_moved():
    for state in DC.STATES:
        if state == DC.CANCELLATIONS:
            continue
        assert DT.demand_sign(state, "UP") == "UP", state


def test_a_flat_figure_points_nowhere():
    """A figure that did not move says nothing about direction, and refusing
    to guess is why this is a function rather than an `== UP` at each site."""
    assert DT.demand_sign(DC.BACKLOG, "FLAT") is None
    assert DT.demand_sign(DC.BACKLOG, "SIDEWAYS") is None


def test_exactly_one_state_is_demand_negative():
    negative = [s for s, p in DT.POLARITY.items()
                if p == DT.DEMAND_NEGATIVE]
    assert negative == [DC.CANCELLATIONS]


# --- the three named cases --------------------------------------------------

def test_backlog_up_with_cancellations_up_is_a_tension():
    """Both moved UP. The chain's direction rule reads that as agreement."""
    got = DT.find(Chain(**{DC.BACKLOG: "UP", DC.CANCELLATIONS: "UP"}))
    assert len(got) == 1
    assert got[0].left == DC.BACKLOG and got[0].right == DC.CANCELLATIONS
    assert got[0].left_direction == "UP" and got[0].right_direction == "UP"
    assert "leaking" in got[0].meaning


def test_revenue_up_with_bookings_down_is_a_tension():
    """Four links apart, and every link between them is unmeasured in this
    corpus, so the chain sees nothing."""
    got = DT.find(Chain(**{DC.BOOKINGS: "DOWN", DC.REVENUE: "UP"}))
    assert len(got) == 1
    assert "the past arriving" in got[0].meaning


def test_orders_up_with_shipments_down_is_a_tension():
    got = DT.find(Chain(**{DC.ORDERS: "UP", DC.SHIPMENTS: "DOWN"}))
    assert len(got) == 1
    assert "constraint" in got[0].meaning


def test_all_three_named_cases_are_representable():
    """The acceptance criterion, in one assertion."""
    cases = [
        {DC.BACKLOG: "UP", DC.CANCELLATIONS: "UP"},
        {DC.BOOKINGS: "DOWN", DC.REVENUE: "UP"},
        {DC.ORDERS: "UP", DC.SHIPMENTS: "DOWN"},
    ]
    for states in cases:
        assert DT.find(Chain(**states)), states


# --- what is NOT a tension --------------------------------------------------

def test_two_figures_that_agree_are_not_a_tension():
    assert DT.find(Chain(**{DC.ORDERS: "UP", DC.SHIPMENTS: "UP"})) == ()
    assert DT.find(Chain(**{DC.BOOKINGS: "UP", DC.REVENUE: "UP"})) == ()


def test_cancellations_falling_while_backlog_rises_is_not_a_tension():
    """Both point the same way for demand, which is the point of polarity."""
    assert DT.find(Chain(**{DC.BACKLOG: "UP",
                            DC.CANCELLATIONS: "DOWN"})) == ()


def test_one_measured_figure_cannot_disagree_with_an_absent_one():
    """Inventing a tension from one figure and one gap is the same error as
    inferring demand from backlog, which this package already refuses."""
    assert DT.find(Chain(**{DC.BACKLOG: "UP"})) == ()
    assert DT.find(Chain()) == ()


def test_a_flat_figure_produces_no_tension():
    assert DT.find(Chain(**{DC.BACKLOG: "FLAT",
                            DC.CANCELLATIONS: "UP"})) == ()


# --- every tension carries its innocent reading -----------------------------

def test_every_tension_carries_an_alternative_and_a_falsifier():
    """For every pair there IS a benign reading, and a layer reporting only
    the alarming one is the mirror image of flattening."""
    for rule in DT.RULES:
        assert rule.alternative.strip(), rule.left
        assert rule.falsifier.strip(), rule.left
        assert rule.meaning.strip(), rule.left


def test_the_tension_cites_both_sides_evidence():
    got = DT.find(Chain(**{DC.BACKLOG: "UP", DC.CANCELLATIONS: "UP"}))
    assert got[0].evidence_ids == ("ev1", "ev1")


def test_no_rule_pairs_a_state_with_itself():
    for rule in DT.RULES:
        assert rule.left != rule.right


def test_every_rule_names_states_the_vocabulary_has():
    for rule in DT.RULES:
        assert rule.left in DC.STATES and rule.right in DC.STATES


# --- never flattened --------------------------------------------------------

def test_no_overall_demand_verdict_is_produced():
    """There is no field here that could stand in for one, and that is the
    node's second acceptance criterion."""
    got = DT.summarise([Chain(**{DC.BACKLOG: "UP", DC.CANCELLATIONS: "UP"})])
    flat = " ".join(str(k) for k in got).lower()
    for banned in ("demand_strong", "demand_score", "verdict", "overall"):
        assert banned not in flat
    assert "no overall demand verdict" in got["note"]


def test_the_summary_counts_by_pair_rather_than_in_total_only():
    chains = [Chain("A", **{DC.BACKLOG: "UP", DC.CANCELLATIONS: "UP"}),
              Chain("B", **{DC.BOOKINGS: "DOWN", DC.REVENUE: "UP"})]
    got = DT.summarise(chains)
    assert got["tensions"] == 2
    assert got["companies_with_a_tension"] == 2
    assert set(got["by_pair"]) == {f"{DC.BACKLOG}/{DC.CANCELLATIONS}",
                                   f"{DC.BOOKINGS}/{DC.REVENUE}"}


def test_a_corpus_with_no_tension_reports_zero_rather_than_nothing():
    got = DT.summarise([Chain(**{DC.ORDERS: "UP", DC.SHIPMENTS: "UP"})])
    assert got["tensions"] == 0
    assert got["rules_available"] == len(DT.RULES)


# --- against a real chain ---------------------------------------------------

def test_it_reads_a_chain_built_by_demand_chain():
    """The producer's own object, not this file's stand-in."""
    rows = [
        {"record": "evidence", "subject_company": "ACME",
         "evidence_type": "DEMAND_SIGNAL", "fact": "backlog rose 12%",
         "evidence_id": "ev1", "observed_at": "2026-07-01"},
    ]
    chain = DC.build(rows, company_id="ACME", as_of="2026-08-10")
    # Whatever the corpus yields, the layer must consume the real shape
    # without raising and must never invent a tension from unmeasured states.
    got = DT.find(chain)
    assert isinstance(got, tuple)
    for one in got:
        assert chain.readings[one.left].known
        assert chain.readings[one.right].known

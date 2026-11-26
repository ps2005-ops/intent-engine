"""Dependence-aware Bayesian updating: a monthly series is not N independent facts."""
import math
from types import SimpleNamespace as NS

from intent_engine.econ import estimator as EST, collective as CO, vocabulary as V

POP = CO.population("US_households", V.HOUSEHOLD)


def _node(month, value, publisher="US Bureau of Labor Statistics", kind="quits", year=2026):
    return NS(node_class=V.BEHAVIORAL, value=value, kind=kind,
              node_id=f"{publisher[:3]}-{year}-{month}", occurred_at=f"{year}-{month:02d}-01",
              available_at=f"{year}-{month:02d}-28", provenance=NS(publisher=publisher))


def _run(nodes, prior=None):
    e, ups, diag = EST.estimate(population=POP, as_of="2026-11-25", nodes=nodes, prior=prior)
    return e, e.dimension("perceived_control"), diag


def test_a_long_steady_series_is_worth_far_fewer_than_its_length():
    _, one, _ = _run([_node(10, 2.0)])
    _, many, diag = _run([_node(m, 2.0 + 0.02 * (m % 3)) for m in range(1, 12)])
    s = diag["dependence"]["series"][0]
    assert s["readings"] == 11 and s["effective_n"] <= 1.0
    # repetition of ONE instrument cannot beat its shared construct error
    assert many.uncertainty >= one.uncertainty * 0.99
    assert many.uncertainty > one.uncertainty / math.sqrt(11)


def test_the_original_overconfidence_cannot_recur():
    """24 readings combined independently gave uncertainty 0.020; the filter
    may not get anywhere near that from one series."""
    _, d, _ = _run([_node(m, 2.0, year=2025) for m in range(1, 13)]
                   + [_node(m, 2.0) for m in range(1, 13)])
    _, one, _ = _run([_node(10, 2.0)])
    assert d.uncertainty >= one.uncertainty * 0.99 and d.uncertainty > 0.04


def test_two_independent_instruments_add_information():
    _, a, _ = _run([_node(10, 2.0)])
    _, ab, diag = _run([_node(10, 2.0), _node(10, 2.0, publisher="Other Survey Bureau")])
    assert len(diag["dependence"]["series"]) == 2
    assert ab.uncertainty < a.uncertainty


def test_a_contradictory_reading_moves_the_state_not_a_constant():
    _, low, _ = _run([_node(m, 1.5) for m in range(1, 11)])
    _, jump, _ = _run([_node(m, 1.5) for m in range(1, 10)] + [_node(10, 3.5)])
    assert jump.posterior_mean > low.posterior_mean


def test_no_reading_is_no_information():
    _, d, diag = _run([])
    assert d is None or d.posterior_mean is None
    assert diag["dependence"]["readings"] == 0


def test_the_same_history_is_not_counted_again_next_cycle():
    nodes = [_node(m, 2.0) for m in range(1, 11)]
    est1, d1, _ = _run(nodes)
    est2, d2, diag2 = _run(nodes, prior=est1)
    assert diag2["dependence"]["series"] == []        # nothing new to filter
    assert d2.uncertainty == d1.uncertainty

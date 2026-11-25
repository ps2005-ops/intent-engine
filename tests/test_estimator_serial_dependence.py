"""A monthly series is one piece of evidence about today, not twenty-four."""
from types import SimpleNamespace as NS

from intent_engine.econ import estimator as EST, collective as CO, vocabulary as V


def _node(month, value):
    return NS(node_class=V.BEHAVIORAL, value=value, kind="quits",
              node_id=f"n{month}", occurred_at=f"2026-{month:02d}-01",
              available_at=f"2026-{month:02d}-28",
              provenance=NS(publisher="US Bureau of Labor Statistics"))


def _est(nodes):
    e, ups, diag = EST.estimate(population=CO.population("US_households", V.HOUSEHOLD),
                                as_of="2026-11-25", nodes=nodes)
    return e.dimension("perceived_control"), diag


def test_history_of_one_series_does_not_shrink_uncertainty():
    one, _ = _est([_node(10, 2.0)])
    many, diag = _est([_node(m, 2.0) for m in range(1, 11)])
    assert many.uncertainty == one.uncertainty
    assert diag["serially_dependent_readings_not_counted"] == 9


def test_the_latest_period_is_the_one_kept():
    d, _ = _est([_node(3, 1.0), _node(10, 3.0), _node(7, 2.0)])
    solo, _ = _est([_node(10, 3.0)])
    assert d.posterior_mean == solo.posterior_mean

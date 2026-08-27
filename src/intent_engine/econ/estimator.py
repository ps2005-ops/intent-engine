"""The producer: behavioural evidence in, collective state out.

WHERE THIS SITS
---------------
`proxies` maps observations onto constructs. `bayes` moves posteriors.
`construct` decides which constructs are allowed to matter. This module is
the one the CYCLE calls, and it is the seam where all three meet.

WHY THE REGISTER IS AN INPUT
----------------------------
A cycle that estimated every declared dimension and let the dashboard sort
out which ones were real would be publishing sixteen posteriors of which
fourteen have never been tested. So the register comes in, and each
estimate carries the construct's promotion state with it -- a reader always
sees whether the number in front of them has earned anything.

RETIRED CONSTRUCTS ARE NOT ESTIMATED
------------------------------------
Not merely hidden from the dashboard: not computed. Section 42 says the
engine must be able to remove a construct, and a construct that is still
being computed every cycle and merely filtered at the surface has not been
removed. `estimate()` skips it, and `skipped_retired` says so out loud.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import bayes, proxies
from .collective import (
    CollectiveStateEstimate, DimensionEstimate, LagModel, Population,
    UNKNOWN_LAG, build, unmeasured,
)
from .construct import Construct
from .vocabulary import CANDIDATE, RETIRED, require

CONTRACT = "econ_estimator.v1"

#: Extra uncertainty applied when every proxy behind a construct is one of
#: the ambiguous ones. Not a fudge factor: it encodes that the evidence does
#: not discriminate between competing readings, which is a real property of
#: the measurement rather than of our confidence in it.
CONTESTED_WIDENING = 1.5

#: Lag bands per construct, in days. Section 5 requires a lag model on every
#: estimate and Section 18 is why: a comparison run at the wrong lag finds
#: nothing and retires a construct that was real.
LAGS: Dict[str, LagModel] = {
    "financial_anxiety": LagModel(30, 7, 90,
        "survey and credit instruments lag the conditions they respond to by "
        "roughly a month; delinquency lags by a quarter"),
    "perceived_control": LagModel(60, 21, 120,
        "labour-market revealed preference moves slowly; a worker's read of "
        "their own options updates over months, not weeks"),
    "institutional_trust": LagModel(90, 30, 365,
        "trust is the slowest of these; it is rebuilt over years and lost "
        "over weeks, so the band is deliberately asymmetric in spirit"),
    "risk_appetite": LagModel(14, 1, 60,
        "household allocation responds fast, and retail speculation faster"),
    "time_horizon": LagModel(45, 14, 120,
        "durable-goods intent turns over a quarter"),
    "future_orientation": LagModel(30, 7, 90,
        "trade-down is the first observable act and appears within weeks"),
    "stress": LagModel(7, 0, 30,
        "search behaviour is near-contemporaneous with the news that drives "
        "it, which is also why it is a weak instrument"),
    "anger": LagModel(7, 0, 30, "public language moves with the news cycle"),
}


def estimate(*, population: Population, as_of: str, nodes: Iterable,
             register: Sequence[Construct] = (),
             prior: Optional[CollectiveStateEstimate] = None,
             ) -> Tuple[CollectiveStateEstimate, List[bayes.Update], dict]:
    """One population's collective state from one cycle's behavioural evidence.

    Returns (estimate, updates, diagnostics). The updates are returned rather
    than folded away because they are what `acceleration` counts: a cycle
    that produced sixteen posteriors from duplicate evidence learned nothing,
    and only the update objects can say so.
    """
    require(bool(as_of), "an estimate is dated")
    by_dim = {c.dimension: c for c in register}
    retired = {d for d, c in by_dim.items() if c.state == RETIRED}

    readings = proxies.read_nodes(nodes)
    grouped = proxies.group_by_dimension(readings)

    dimensions: List[DimensionEstimate] = []
    updates: List[bayes.Update] = []
    skipped_retired: List[str] = []

    for dim, rs in sorted(grouped.items()):
        if dim in retired:
            skipped_retired.append(dim)
            continue

        start = (prior.dimension(dim) if prior is not None
                 else unmeasured(dim, "no prior cycle estimated this"))
        # Carry forward the lag model and promotion state, which are
        # properties of the construct rather than of this cycle's evidence.
        start = replace(start, lag_model=LAGS.get(dim, UNKNOWN_LAG),
                        promotion_state=(by_dim[dim].state if dim in by_dim
                                         else CANDIDATE))

        upd = bayes.update(start, [r.observation() for r in rs], at=as_of)
        updates.append(upd)
        moved = bayes.apply(start, upd)

        if proxies.sole_contested(rs) and moved.posterior_mean is not None:
            moved = replace(moved,
                            uncertainty=min(1.0, round(
                                moved.uncertainty * CONTESTED_WIDENING, 4)))
            moved = replace(moved, confidence=round(
                max(0.0, 1.0 - moved.uncertainty * 2), 3))

        dimensions.append(moved)

    # Constructs that exist and were not touched this cycle stay visible as
    # absences rather than vanishing from the surface.
    touched = {d.dimension for d in dimensions}
    for dim in sorted(set(proxies.covered_dimensions()) - touched - retired):
        dimensions.append(unmeasured(
            dim, "a proxy exists for this construct but no behavioural node "
                 "measuring it arrived in this cycle"))

    est = build(population=population, as_of=as_of, dimensions=dimensions,
                source_nodes=[r.node_id for r in readings],
                provenance={"producer": "econ.estimator", "contract": CONTRACT,
                            "readings": len(readings),
                            "register_size": len(register)})

    diagnostics = {
        "readings": proxies.summarise(readings),
        "updates": bayes.summarise(updates),
        "skipped_retired": skipped_retired,
        "dimensions_estimated": len([d for d in dimensions
                                     if d.posterior_mean is not None]),
        "dimensions_no_proxy": proxies.uncovered_dimensions(),
    }
    return est, updates, diagnostics


def estimate_many(*, populations: Sequence[Population], as_of: str,
                  nodes_by_population: Dict[str, Iterable],
                  register: Sequence[Construct] = (),
                  priors: Optional[Dict[str, CollectiveStateEstimate]] = None,
                  ) -> Tuple[List[CollectiveStateEstimate],
                             List[bayes.Update], dict]:
    """Section 6: several populations, never one 'the market is fearful'.

    Each population is estimated from ITS OWN evidence. Handing every
    population the same node set would reproduce the exact failure Section 6
    forbids, with more objects.
    """
    priors = priors or {}
    states, all_updates = [], []
    diags: Dict[str, dict] = {}
    for pop in populations:
        nodes = nodes_by_population.get(pop.key, ())
        est, ups, d = estimate(population=pop, as_of=as_of, nodes=nodes,
                               register=register, prior=priors.get(pop.key))
        states.append(est)
        all_updates.extend(ups)
        diags[pop.key] = d
    return states, all_updates, {
        "populations": len(states),
        "per_population": diags,
        "total_updates": len(all_updates),
        "informative_updates": sum(1 for u in all_updates if u.informative),
    }

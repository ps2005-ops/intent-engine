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


def _filter_series(readings, prior=None):
    """One dependence-aware observation per series: a local-level Kalman filter.

    WHY (2026-11-25): the first live update precision-combined 24 monthly
    quits readings as 24 independent measurements of today's state
    (uncertainty 0.020, confidence 0.959). Consecutive months of one series
    share one slowly moving state; they are not independent evidence about
    the present. An interim fix kept only the latest reading, which discards
    real information. This is the standard model for the situation:

        state       x_t = x_{t-1} + w_t,   w ~ N(0, q)   (the state drifts)
        observation y_t = x_t + v_t,       v ~ N(0, r)   (instrument noise)

    TWO KINDS OF ERROR, BECAUSE ONLY ONE OF THEM AVERAGES OUT. The proxy's
    stated noise is mostly CONSTRUCT error -- how well "quits" measures
    "perceived control" -- and that error is shared by every reading of the
    series. Repetition cannot reduce it. It is therefore added to the filtered
    variance at the end, in full (`r_shared`). What repetition CAN reduce is
    month-to-month idiosyncratic noise, filtered with a local level:

        state       x_t = x_{t-1} + w_t,   w ~ N(0, q)
        observation y_t = x_t + v_t,       v ~ N(0, r_idio)

    Under a local level Var(y_t - y_{t-1}) = q + 2 r_idio. q and r_idio are
    not separately identified from that one moment, so they are split evenly
    (q = r_idio = Var(dy)/3) -- a stated assumption, with the 1/4-3/4 splits
    reported as sensitivity. The result: an instrument read 24 times is worth
    a little more than once, never 24 times; two DIFFERENT instruments with
    independent construct errors still combine.

    Only readings not already folded into `prior` are filtered, so the same
    history cannot be counted again on the next cycle; the prior is combined
    once, downstream, by `bayes.update`.
    """
    import math
    from statistics import pvariance
    seen = set(getattr(prior, "evidence", ()) or ()) if prior is not None else set()
    groups = {}
    for r in readings:
        groups.setdefault((r.kind, r.publisher, r.dimension), []).append(r)
    kept, diag = [], []
    for key, rs in sorted(groups.items()):
        rs = sorted(rs, key=lambda x: (x.as_of or "", x.node_id))
        new = [x for x in rs if x.node_id not in seen]
        if not new:
            continue
        r_shared = float(rs[-1].proxy.noise) ** 2
        ys = [float(x.placed) for x in rs]
        dys = [b - a for a, b in zip(ys, ys[1:])]
        vdy = pvariance(dys) if len(dys) >= 2 else 0.0
        eps = 1e-8

        def _filter(split):
            q = max(vdy * split, eps)
            ri = max(vdy * (1 - split) / 2, eps)
            m, P = float(new[0].placed), ri
            for x in new[1:]:
                P = P + q
                K = P / (P + ri)
                m = m + K * (float(x.placed) - m)
                P = (1 - K) * P
            return m, P
        m, P_idio = _filter(1 / 3)
        P = P_idio + r_shared
        sens = {f"split_{a}": round(math.sqrt(_filter(a)[1] + r_shared), 4)
                for a in (0.25, 0.75)}
        last = new[-1]
        kept.append((last, min(1.0, max(0.0, m)), math.sqrt(P),
                     tuple(x.node_id for x in new)))
        diag.append({"series": "|".join(str(k) for k in key), "readings": len(new),
                     "already_folded": len(rs) - len(new),
                     "r_shared": round(r_shared, 6), "var_dy": round(vdy, 6),
                     "filtered_idio_sd": round(math.sqrt(P_idio), 4),
                     "posterior_sd": round(math.sqrt(P), 4),
                     "effective_n": round(r_shared / P, 3),
                     "naive_independent_sd": round(math.sqrt(r_shared / len(new)), 4),
                     "sensitivity_posterior_sd": sens})
    return kept, diag


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

    all_readings = proxies.read_nodes(nodes)
    readings = all_readings
    grouped = proxies.group_by_dimension(readings)

    dimensions: List[DimensionEstimate] = []
    updates: List[bayes.Update] = []
    series_diag: List[dict] = []
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

        filtered, fdiag = _filter_series(rs, prior=(prior.dimension(dim)
                                                    if prior is not None else None))
        series_diag.extend(fdiag)
        obs = [replace(r.observation(), value=round(m, 4), noise=max(sd, 1e-4))
               for r, m, sd, _ids in filtered]
        folded = {i for *_x, ids in filtered for i in ids}
        upd = bayes.update(start, obs, at=as_of)
        updates.append(upd)
        moved = bayes.apply(start, upd)
        if folded:
            # Every reading the filter consumed is folded in, not only the
            # one that carried the result -- or the next cycle re-reads them.
            moved = replace(moved, evidence=tuple(sorted(
                set(moved.evidence) | folded)))

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
        "dependence": {"model": "local-level Kalman filter per series",
                       "readings": len(all_readings), "series": series_diag},
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

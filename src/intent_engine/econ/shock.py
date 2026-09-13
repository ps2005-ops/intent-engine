"""Structural shocks: what a move in one quantity implies, and how sure.

WHAT A SHOCK EVALUATION IS
--------------------------
A shock is a hypothetical: "+50bp real yield". Propagating it through the
structural causal graph gives first-, second- and third-order effects, the
companies and sectors exposed, and — the part that is usually missing — an
honest statement of how much less is known at each remove.

CONFIDENCE COMPOUNDS DOWNWARD, ALWAYS
-------------------------------------
A third-order effect reached through three edges of confidence 0.7 is not a
0.7 claim. It is 0.34, and presenting it beside the first-order effect at the
same visual weight is the false-precision failure this whole programme keeps
returning to. `propagate` multiplies, and the band widens with depth.

MAGNITUDE IS REFUSED UNLESS THE EDGES CARRY IT
----------------------------------------------
The temptation is to report "-8% on high-growth multiples". Almost no edge in
this graph has an estimated elasticity, and inventing one produces a number
that will be quoted back. So a shock reports DIRECTION, ORDER, LAG and
CONFIDENCE, and reports magnitude only where an edge carries a measured
elasticity — `magnitude` is None otherwise, and the renderer says so.

THE LEVEL FLOOR TRAVELS WITH THE EFFECT
---------------------------------------
An effect reached through a level-1 edge is an ASSOCIATION however many
level-5 edges preceded it. `min_evidence_level` on the result is the weakest
link, and `may_state_causation` reads it — so a shock chain cannot launder a
correlation by attaching it to an identified mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .causal import (
    CAUSAL_LANGUAGE_FLOOR, CausalEdge, LEVEL_NAMES, StructuralCausalGraph,
    DOWN, UP,
)
from .vocabulary import require

CONTRACT = "econ_shock.v1"


@dataclass(frozen=True)
class Effect:
    """One propagated consequence of a shock."""

    quantity: str
    direction: str
    order: int
    lag_days: int
    confidence: float
    min_evidence_level: int
    path: Tuple[str, ...]
    mechanism: str
    magnitude: Optional[float] = None
    magnitude_unit: str = ""

    @property
    def may_state_causation(self) -> bool:
        return self.min_evidence_level >= CAUSAL_LANGUAGE_FLOOR

    def sentence(self) -> str:
        # The verb form carries the evidence level, so it has to agree with
        # it grammatically as well as semantically: "should fall" for an
        # identified mechanism, "has tended to fall" for an association.
        move = "rise" if self.direction == UP else "fall"
        band = confidence_band(self.confidence)
        verb = "should" if self.may_state_causation else "has tended to"
        chain = " -> ".join(self.path)
        magnitude = ("" if self.magnitude is None
                     else f" by about {self.magnitude:g}"
                          f"{self.magnitude_unit}")
        return (f"{self.quantity} {verb} {move}{magnitude} after about "
                f"{self.lag_days} days ({band}, order {self.order}, via "
                f"{chain})")

    def as_dict(self) -> dict:
        return {"quantity": self.quantity, "direction": self.direction,
                "order": self.order, "lag_days": self.lag_days,
                "confidence": round(self.confidence, 3),
                "confidence_band": confidence_band(self.confidence),
                "min_evidence_level": self.min_evidence_level,
                "min_evidence_level_name":
                    LEVEL_NAMES[self.min_evidence_level],
                "may_state_causation": self.may_state_causation,
                "path": list(self.path), "mechanism": self.mechanism,
                "magnitude": self.magnitude,
                "magnitude_unit": self.magnitude_unit,
                "sentence": self.sentence()}


@dataclass(frozen=True)
class ShockResult:
    shock: str
    quantity: str
    direction: str
    as_of: str
    effects: Tuple[Effect, ...]
    #: Quantities the graph knows about but could not reach from here. Named,
    #: because "we have no path to credit spreads" is a research priority and
    #: an empty list is indistinguishable from "nothing is affected".
    unreached: Tuple[str, ...] = ()

    def by_order(self, order: int) -> List[Effect]:
        return [e for e in self.effects if e.order == order]

    def exposed(self, exposures: Dict[str, Sequence[str]]) -> Dict[str, List[str]]:
        """Which subjects are exposed, given a subject -> quantities map.

        The map comes from `company.CompanyEconomicState.macro_exposure`, and
        it is EVIDENCE-BOUND on that side: a company is exposed to a quantity
        because a retrieved document says so, never because of its sector.
        This function does not weaken that — it only joins.
        """
        hit = {e.quantity for e in self.effects}
        out: Dict[str, List[str]] = {}
        for subject, quantities in exposures.items():
            overlap = sorted(set(quantities) & hit)
            if overlap:
                out[subject] = overlap
        return out

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "shock": self.shock,
                "quantity": self.quantity, "direction": self.direction,
                "as_of": self.as_of,
                "effects": [e.as_dict() for e in self.effects],
                "orders": {str(o): len(self.by_order(o))
                           for o in sorted({e.order for e in self.effects})},
                "unreached": list(self.unreached)}


def confidence_band(p: float) -> str:
    """Words, not decimals, on any surface a human reads.

    0.34 and 0.29 are not different claims about the economy; printing them
    as different numbers says they are. The bands are wide on purpose.
    """
    if p >= 0.66:
        return "likely"
    if p >= 0.40:
        return "plausible"
    if p >= 0.20:
        return "weak"
    return "speculative"


def _combine(sign_a: str, sign_b: str) -> str:
    """Sign algebra along a path: two falls make a rise."""
    return UP if sign_a == sign_b else DOWN


def propagate(graph: StructuralCausalGraph, *, quantity: str,
              direction: str = UP, as_of: str, max_order: int = 3,
              min_evidence_level: int = 0,
              label: str = "") -> ShockResult:
    """Walk the graph outward from a shocked quantity.

    Breadth-first and cycle-safe. Where two paths reach the same quantity the
    STRONGER one is kept — not summed. Summing would let a densely-connected
    corner of the graph manufacture confidence purely by having more edges,
    which is the graph-shaped version of double counting.
    """
    require(direction in (UP, DOWN), f"unknown direction {direction!r}")
    require(bool(as_of), "a shock evaluation is dated")
    best: Dict[str, Effect] = {}
    frontier: List[Tuple[str, str, float, int, int, Tuple[str, ...], str]] = [
        (quantity, direction, 1.0, 0, 5, (quantity,), "")]
    while frontier:
        node, sign, conf, order, floor, path, mech = frontier.pop(0)
        if order >= max_order:
            continue
        for e in graph.edges(cause=node, min_level=min_evidence_level):
            if e.effect in path:      # cycle
                continue
            new_sign = _combine(sign, e.sign)
            new_conf = conf * e.confidence
            new_floor = min(floor, e.evidence_level)
            new_path = path + (e.effect,)
            effect = Effect(
                quantity=e.effect, direction=new_sign, order=order + 1,
                lag_days=_lag_of(path, graph) + e.lag_days,
                confidence=new_conf, min_evidence_level=new_floor,
                path=new_path,
                mechanism=(f"{mech} | {e.mechanism}" if mech else e.mechanism))
            prior = best.get(e.effect)
            if prior is None or effect.confidence > prior.confidence:
                best[e.effect] = effect
            frontier.append((e.effect, new_sign, new_conf, order + 1,
                             new_floor, new_path, effect.mechanism))
    effects = tuple(sorted(best.values(),
                           key=lambda x: (x.order, -x.confidence, x.quantity)))
    reached = {e.quantity for e in effects} | {quantity}
    unreached = tuple(q for q in graph.quantities() if q not in reached)
    return ShockResult(
        shock=label or f"{direction} shock to {quantity}",
        quantity=quantity, direction=direction, as_of=as_of,
        effects=effects, unreached=unreached)


def _lag_of(path: Tuple[str, ...], graph: StructuralCausalGraph) -> int:
    """Cumulative lag along a path already walked."""
    total = 0
    for a, b in zip(path, path[1:]):
        e = graph.get(a, b)
        if e is not None:
            total += e.lag_days
    return total


#: The named shocks Section 6 asks for. A catalogue, not a limit: `propagate`
#: takes any quantity in the graph.
NAMED_SHOCKS = {
    "real_yield_up_50bp": ("real_yield", UP,
                           "+50bp real yield"),
    "credit_spread_up_100bp": ("credit_spread_hy", UP,
                               "+100bp high-yield credit spread"),
    "dollar_up_10pct": ("fx_dxy", UP, "+10% trade-weighted dollar"),
    "oil_down_20pct": ("commodity_oil", DOWN, "-20% crude oil"),
    "vol_spike": ("vix", UP, "volatility spike"),
    "funding_stress": ("funding_stress", UP, "funding stress event"),
}


def evaluate_structural_shock(graph: StructuralCausalGraph, name: str, *,
                              as_of: str, max_order: int = 3) -> ShockResult:
    """Run one of the named shocks. Unknown names raise rather than default."""
    if name not in NAMED_SHOCKS:
        raise KeyError(
            f"{name!r} is not a named shock; known: "
            f"{sorted(NAMED_SHOCKS)}. Use `propagate` for an arbitrary one.")
    quantity, direction, label = NAMED_SHOCKS[name]
    return propagate(graph, quantity=quantity, direction=direction,
                     as_of=as_of, max_order=max_order, label=label)

"""`EconomicState` — the one object both decision surfaces read.

WHAT THIS IS AND IS NOT
-----------------------
It is the engine's dated reading of the economy: what each condition is
doing, which beliefs are live, what shocks are being evaluated, how sure any
of it is, and where every part came from. It is NOT a summary of the market
engine's operations. Nothing about positions, P&L, win rates, signal states,
schedulers, funnels or strategies may appear in it, and that is enforced
structurally rather than promised.

WHY THE ALLOWLIST IS HERE AND NOT AT THE BOUNDARY
-------------------------------------------------
The founder-facing `market_contract` learned this the expensive way: a
blacklist answers "is this one of the fields we thought of?", and the field
that leaks is by definition the one nobody thought of. An audit found six
leaking fields, none of them on the blacklist.

So `validate` inverts the test — `ALLOWED` names every field that may appear,
at every depth, and anything else raises. Putting it in the STATE rather than
at each boundary means a new consumer cannot forget to call it: there is one
serialisation path, and it validates itself.

A NAME COLLISION WORTH KNOWING ABOUT
------------------------------------
`market.macro_state.EconomicState` is a different, older object: the state of
ONE condition ("US policy rate, OBSERVED, moved UP"). This one is the whole
economy at a moment. The bridge maps the former into `ConditionReading`
below. They were not merged because the market-side object carries series
selection and revision rules that only its own ingestion needs, and lifting
those would have made the shared contract heavier than either side wants.

MISSING IS NEVER ZERO
---------------------
Every reading carries a `standing`. UNKNOWN with `value=None` is the honest
encoding of "nothing in evidence measures this", and it renders as an absence
with a reason. It must never be shown as FLAT: "we did not measure this" and
"this did not move" support completely different decisions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .belief import EconomicBelief
from .evidence import EconomicNode, assert_public
from .vocabulary import (
    CONTRACT as CORE_CONTRACT, DOWN, EconError, FLAT, NO_PRIOR, PUBLIC,
    STANDINGS, TENANT_PRIVATE, UNKNOWN, UP, require,
)

CONTRACT = "economic_state.v1"


class StateViolation(EconError):
    """A field that is not allowlisted tried to enter the shared state."""


#: The pillars Section 20 names. A pillar is a NAMED GROUP of condition
#: readings, not a single number, because "rates" is a curve and collapsing it
#: to one figure is what made the engine's reading of Canadian market rates
#: flip between the 2-year and the 10-year.
PILLARS = ("growth", "inflation", "liquidity", "rates", "credit", "fx",
           "commodities", "volatility", "labour")


@dataclass(frozen=True)
class ConditionReading:
    """One economic condition, as of one date, with its standing."""

    kind: str
    standing: str
    #: Which way the quantity MOVED, computed against the previous
    #: observation of the same quantity -- never from the sign of the level.
    #: NO_PRIOR when there is no earlier observation to compare against.
    direction: str = NO_PRIOR
    value: Optional[float] = None
    unit: str = ""
    as_of: str = ""
    #: The evidence node this reading IS. Empty only for UNKNOWN.
    node_id: str = ""
    publisher: str = ""
    reason: str = ""
    #: What it was, and when, so a reader can check the direction.
    prior_value: Optional[float] = None
    prior_as_of: str = ""

    def __post_init__(self) -> None:
        require(self.standing in STANDINGS,
                f"unknown standing {self.standing!r}")
        require(self.direction in (UP, DOWN, FLAT, NO_PRIOR),
                f"unknown direction {self.direction!r}")
        if self.direction in (UP, DOWN, FLAT):
            require(self.prior_value is not None,
                    f"{self.kind} claims direction {self.direction} with no "
                    "prior value; a direction that is not computed against an "
                    "earlier observation is the sign of a level wearing the "
                    "word 'rising'")
        if self.standing == UNKNOWN:
            require(self.value is None,
                    "an UNKNOWN condition carries no value; a number with no "
                    "standing is the false-precision failure in miniature")
            require(bool(self.reason),
                    "an absence states what is missing, or it reads as calm")
        else:
            require(bool(self.node_id),
                    f"a {self.standing} reading names the evidence node it "
                    "is; a reading with no node cannot be checked or replayed")

    @property
    def known(self) -> bool:
        return self.standing != UNKNOWN

    @property
    def moved(self) -> bool:
        """Did it change? False for FLAT and for NO_PRIOR, for opposite
        reasons -- `direction` is what distinguishes them."""
        return self.direction in (UP, DOWN)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "standing": self.standing,
                "direction": self.direction, "value": self.value,
                "unit": self.unit, "as_of": self.as_of,
                "node_id": self.node_id, "publisher": self.publisher,
                "reason": self.reason, "known": self.known,
                "moved": self.moved, "prior_value": self.prior_value,
                "prior_as_of": self.prior_as_of}


def unknown_reading(kind: str, reason: str = "") -> ConditionReading:
    return ConditionReading(
        kind=kind, standing=UNKNOWN, direction=NO_PRIOR,
        reason=reason or "no series in evidence measures this condition")


def _direction_between(prior, latest) -> str:
    """Which way it moved. NO_PRIOR when that cannot be established.

    THE DEFECT THIS REPLACED, measured on the first live state published:
    direction was `UP if (value or 0) > 0 else FLAT` -- the sign of the
    LEVEL. A consumer price index of 333.918 is greater than zero every month
    that has ever existed, so all five measured conditions reported UP, and a
    founder-facing block read "inflation is rising at 333.918 index" whatever
    inflation had done. Uniformity across every condition is the tell: a real
    economy does not move one way in five out of five.

    The change was computable the whole time -- 23 to 46 dated observations
    per condition were already in the graph.
    """
    if prior is None or prior.value is None or latest.value is None:
        return NO_PRIOR
    if latest.value > prior.value:
        return UP
    if latest.value < prior.value:
        return DOWN
    return FLAT


@dataclass(frozen=True)
class SectorState:
    """One sector's reading, and what it rests on."""

    sector: str
    direction: str
    standing: str
    basis: str
    node_ids: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"sector": self.sector, "direction": self.direction,
                "standing": self.standing, "basis": self.basis,
                "node_ids": list(self.node_ids)}


@dataclass(frozen=True)
class PositioningReading:
    """What a participant class appears to be doing. A PROXY, labelled.

    Positioning is not observed. It is inferred from prices, open interest and
    flows, and every inference here carries the assumption that produced it.
    `standing` is never OBSERVED for a positioning reading, and `basis` is
    what a reader checks.
    """

    participant: str
    stance: str
    basis: str
    confidence: float = 0.3
    standing: str = "INFERRED"

    def as_dict(self) -> dict:
        return {"participant": self.participant, "stance": self.stance,
                "basis": self.basis, "confidence": round(self.confidence, 3),
                "standing": self.standing}


@dataclass(frozen=True)
class EconomicState:
    """The canonical economic state. One per (as_of, area)."""

    as_of: str
    area: str = "US"
    conditions: Dict[str, ConditionReading] = field(default_factory=dict)
    sectors: Tuple[SectorState, ...] = ()
    beliefs: Tuple[EconomicBelief, ...] = ()
    shocks: Tuple[dict, ...] = ()
    positioning: Tuple[PositioningReading, ...] = ()
    #: Where this state came from: which producer, over which nodes, at which
    #: contract version. Not decoration — a founder surface prints it.
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require(bool(self.as_of), "an economic state is dated")
        private = [b.belief_id for b in self.beliefs
                   if b.visibility != PUBLIC]
        if private:
            raise StateViolation(
                f"{len(private)} tenant-private belief(s) in a shared "
                f"economic state ({private[:3]}). The shared state is public "
                "by construction; a tenant's private belief belongs in that "
                "tenant's CompanyEconomicState and nowhere else.")

    # --- reading ------------------------------------------------------------
    def reading(self, kind: str) -> ConditionReading:
        """Never a KeyError. An unmeasured condition is a reading too."""
        return self.conditions.get(kind) or unknown_reading(kind)

    def pillar(self, name: str) -> List[ConditionReading]:
        require(name in PILLARS, f"{name!r} is not a pillar; known: {PILLARS}")
        return [r for kind, r in sorted(self.conditions.items())
                if _PILLAR_OF.get(kind) == name]

    @property
    def known_conditions(self) -> int:
        return sum(1 for r in self.conditions.values() if r.known)

    @property
    def uncertainty(self) -> dict:
        """How much of the economy this state actually measures.

        Reported as a fraction of the vocabulary, not of what happened to be
        fetched. A state that measured three conditions out of forty and
        called itself complete is the failure mode; the denominator is the
        vocabulary so coverage cannot be inflated by asking for less.
        """
        from .vocabulary import NODE_KINDS, MACRO
        total = len(NODE_KINDS[MACRO])
        known = self.known_conditions
        return {"measured": known, "vocabulary": total,
                "coverage": round(known / total, 3) if total else 0.0,
                "unmeasured": sorted(
                    k for k in NODE_KINDS[MACRO]
                    if k not in self.conditions
                    or not self.conditions[k].known)}

    def most_fragile_belief(self) -> Optional[EconomicBelief]:
        live = [b for b in self.beliefs if b.status != "RETIRED"]
        return max(live, key=lambda b: b.fragility) if live else None

    def as_dict(self) -> dict:
        payload = {
            "contract": CONTRACT, "as_of": self.as_of, "area": self.area,
            "conditions": {k: r.as_dict()
                           for k, r in sorted(self.conditions.items())},
            "sectors": [s.as_dict() for s in self.sectors],
            "beliefs": [_belief_view(b) for b in self.beliefs],
            "shocks": [dict(s) for s in self.shocks],
            "positioning": [p.as_dict() for p in self.positioning],
            "uncertainty": self.uncertainty,
            "provenance": dict(self.provenance),
        }
        validate(payload)
        return payload


#: Which pillar each macro kind belongs to. Kinds absent from this map are
#: still readable; they simply do not roll up, and `pillar()` says so by
#: returning fewer readings rather than by inventing a group.
_PILLAR_OF = {
    "growth": "growth", "industrial_production": "growth",
    "business_investment": "growth", "consumer_demand": "growth",
    "housing": "growth", "trade": "growth", "fiscal": "growth",
    "inflation": "inflation", "inflation_expectation": "inflation",
    "policy_rate": "rates", "sofr": "rates", "ois": "rates",
    "treasury_2y": "rates", "treasury_5y": "rates", "treasury_10y": "rates",
    "treasury_30y": "rates", "curve_slope": "rates",
    "curve_butterfly": "rates", "real_yield": "rates",
    "credit_spread_ig": "credit", "credit_spread_hy": "credit",
    "bank_stress": "credit",
    "liquidity": "liquidity", "financial_conditions": "liquidity",
    "fx_dxy": "fx", "fx_cross": "fx", "currency_basis": "fx",
    "commodity_oil": "commodities", "commodity_gas": "commodities",
    "commodity_copper": "commodities", "commodity_gold": "commodities",
    "commodity_ags": "commodities", "commodity_curve": "commodities",
    "labour": "labour", "wages": "labour",
}


def _belief_view(b: EconomicBelief) -> dict:
    """The belief fields that may cross into a shared state.

    Deliberately narrower than `EconomicBelief.as_dict`: the full revision
    chain is internal learning history, and a founder surface reading it would
    be reading the engine's diary rather than its conclusions.
    """
    return {"belief_id": b.belief_id, "proposition": b.proposition,
            "subject": b.subject, "probability": round(b.probability, 3),
            "mechanism": b.mechanism, "falsifier": b.falsifier,
            "status": b.status, "fragility": b.fragility,
            "last_updated": b.last_updated,
            "revision_count": len(b.revisions)}


# --- the allowlist ----------------------------------------------------------
#: Every key that may appear at every depth. Nested dicts are keyed by their
#: own name; lists are validated element-wise.
ALLOWED: Dict[str, Any] = {
    "contract": None, "as_of": None, "area": None,
    "conditions": {"*": {"kind": None, "standing": None, "direction": None,
                         "value": None, "unit": None, "as_of": None,
                         "node_id": None, "publisher": None, "reason": None,
                         "known": None, "moved": None, "prior_value": None,
                         "prior_as_of": None}},
    "sectors": {"sector": None, "direction": None, "standing": None,
                "basis": None, "node_ids": None},
    "beliefs": {"belief_id": None, "proposition": None, "subject": None,
                "probability": None, "mechanism": None, "falsifier": None,
                "status": None, "fragility": None, "last_updated": None,
                "revision_count": None},
    "shocks": {"contract": None, "shock": None, "quantity": None,
               "direction": None, "as_of": None, "orders": None,
               "unreached": None,
               "effects": {"quantity": None, "direction": None, "order": None,
                           "lag_days": None, "confidence": None,
                           "confidence_band": None,
                           "min_evidence_level": None,
                           "min_evidence_level_name": None,
                           "may_state_causation": None, "path": None,
                           "mechanism": None, "magnitude": None,
                           "magnitude_unit": None, "sentence": None}},
    "positioning": {"participant": None, "stance": None, "basis": None,
                    "confidence": None, "standing": None},
    "uncertainty": {"measured": None, "vocabulary": None, "coverage": None,
                    "unmeasured": None},
    "provenance": {"producer": None, "nodes": None, "contract": None,
                   "graph": None, "cycle": None, "as_of": None,
                   "evidence_nodes": None, "source_count": None},
}

#: Words that may not appear inside any free-text field. The structural test
#: cannot catch a win rate written into `basis`, and `basis` accepts prose by
#: design.
_BANNED_SUBSTRINGS = (
    "win rate", "win_rate", "sharpe", "pnl", "p&l", "profit and loss",
    "alpha", "position", "portfolio value", "paper trade", "paper_book",
    "order", "fill", "slippage", "drawdown", "scheduler", "funnel",
    "strategy_id", "signal_fired", "leaderboard",
)

#: Free-text fields the substring scan applies to. Listed rather than "every
#: string", because `mechanism` legitimately contains "positioning" when the
#: mechanism IS about participant positioning, and a scan that cannot tell
#: those apart fails closed on real economics.
_PROSE_FIELDS = ("reason", "basis", "proposition", "sentence",
                 "resolution_rule", "note")


def validate(payload: Any, *, allowed: Any = None, path: str = "") -> None:
    """Refuse anything not allowlisted, at any depth, including inside lists."""
    spec = ALLOWED if allowed is None else allowed
    if isinstance(payload, dict):
        if not isinstance(spec, dict):
            raise StateViolation(
                f"{path or 'root'}: an object where the contract expects a "
                "scalar")
        wildcard = spec.get("*")
        for key, value in payload.items():
            child = spec.get(key, wildcard)
            if key not in spec and wildcard is None:
                raise StateViolation(
                    f"{path}{'.' if path else ''}{key} is not in the shared "
                    "economic-state contract. The allowlist fails closed on "
                    "purpose: a new upstream field does not render, and does "
                    "not silently pass.")
            if key in _PROSE_FIELDS and isinstance(value, str):
                _scan_prose(value, f"{path}.{key}")
            if child is not None:
                validate(value, allowed=child, path=f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            validate(item, allowed=spec, path=f"{path}[{i}]")
    # scalars are terminal and need no further check


def _scan_prose(text: str, where: str) -> None:
    low = text.lower()
    for banned in _BANNED_SUBSTRINGS:
        if banned in low:
            raise StateViolation(
                f"{where}: the phrase {banned!r} is a trading internal and "
                "may not appear in shared economic state, including inside "
                "free text. A win rate that arrives inside a sentence leaks "
                "exactly like one that arrives inside a key.")


def build(*, as_of: str, area: str = "US",
          nodes: Sequence[EconomicNode] = (),
          beliefs: Sequence[EconomicBelief] = (),
          sectors: Sequence[SectorState] = (),
          shocks: Sequence[dict] = (),
          positioning: Sequence[PositioningReading] = (),
          producer: str = "", graph_summary: Optional[dict] = None,
          ) -> EconomicState:
    """Assemble a state from evidence nodes. The supported constructor.

    Every input node is checked for visibility FIRST. The shared state is a
    public surface, and the check is a refusal rather than a filter so a
    caller cannot build a state from private material and have it silently
    come out smaller.
    """
    assert_public(nodes, where="EconomicState.build")
    assert_public([], where="")  # no-op; keeps the import honest under linting
    # Grouped by quantity so a DIRECTION can be computed against the previous
    # observation of the SAME quantity. Ordered by the period the figure
    # describes, then by when it became available, so two prints of one period
    # order deterministically rather than by dictionary insertion.
    by_kind: Dict[str, List[EconomicNode]] = {}
    for n in nodes:
        if n.node_class != "MACRO" or n.subject != area:
            continue
        by_kind.setdefault(n.kind, []).append(n)

    conditions: Dict[str, ConditionReading] = {}
    for kind, items in by_kind.items():
        items.sort(key=lambda x: (x.occurred_at, x.available_at))
        latest = items[-1]
        # The most recent observation of an EARLIER period. Two prints of the
        # same period are a revision, not a movement, and comparing against
        # one would report a statistical revision as an economic change.
        prior = next((p for p in reversed(items[:-1])
                      if p.occurred_at < latest.occurred_at
                      and p.value is not None), None)
        conditions[kind] = ConditionReading(
            kind=kind, standing=latest.standing,
            direction=_direction_between(prior, latest),
            value=latest.value, unit=latest.unit,
            as_of=latest.occurred_at, node_id=latest.node_id,
            publisher=latest.provenance.publisher,
            prior_value=(prior.value if prior is not None else None),
            prior_as_of=(prior.occurred_at if prior is not None else ""))
    provenance = {"producer": producer or "unknown",
                  "contract": CONTRACT, "as_of": as_of,
                  "nodes": len(nodes),
                  "source_count": len({n.provenance.publisher
                                       for n in nodes}),
                  "graph": graph_summary or {}}
    return EconomicState(
        as_of=as_of, area=area, conditions=conditions,
        sectors=tuple(sectors),
        beliefs=tuple(b for b in beliefs if b.visibility == PUBLIC),
        shocks=tuple(shocks), positioning=tuple(positioning),
        provenance=provenance)

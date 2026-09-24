"""Company evidence -> candidate economic indicators (Section 18).

WHAT THIS DELIBERATELY DOES NOT USE
-----------------------------------
Demo search queries. Which companies anonymous visitors type, and how often,
is not a signal about the economy: it is a signal about who linked to the
product this week. Using it would create a privacy exposure, a sampling bias
nobody could correct, and — the decisive one — a manipulation surface, since
anyone who can type into a public box can move a "signal".

The useful bridge is the PUBLIC CORPORATE EVIDENCE the engine reads while
analysing companies. Hiring, pricing, capacity, inventories, demand language,
financing, guidance, supply constraints. Those are statements companies made
in public, they are attributable, and they are what a macro analyst would use
if they had the patience to read four hundred filings.

AN INDEX IS A HYPOTHESIS, NOT A SIGNAL
--------------------------------------
Everything built here enters the learning system as a CANDIDATE. It is not
tradable, it does not enter a belief at more than candidate weight, and
`Aggregate.tradable` is False with no code path that sets it True. Promotion
requires forward validation, and that lives in `promotion`.

PRIVACY IS ENFORCED AT THE INPUT, NOT THE OUTPUT
------------------------------------------------
`build` calls `assert_public` on every contributing node and raises. It does
not filter. An aggregate quietly built from nine public and forty private
observations, reporting nine, is a privacy breach that also lies about its
own sample.

WHY THE MINIMUM PANEL IS FIVE AND NOT THREE
-------------------------------------------
Below five contributors an "index" is a small number of companies with a
label on it, and the label is what gets quoted. Five is not a statistical
threshold — nothing here is powered — it is the point at which no single
company can be more than a fifth of the reading. `MIN_CONTRIBUTORS` is stated
so it can be argued with, and `insufficient()` is a real return value rather
than an empty result.

DOMINANCE IS REFUSED SEPARATELY FROM COUNT
------------------------------------------
Five contributors where one supplied eleven of fifteen observations is a
company with a panel drawn around it. `MAX_CONTRIBUTOR_SHARE` caps any one
company's weight, and the cap is applied by REWEIGHTING rather than by
dropping, so the reading stays defined and the concentration is reported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .evidence import EconomicNode, assert_public, node as make_node
from .vocabulary import (
    COMPANY, DOWN, FLAT, HYPOTHESIZED, INFERRED, MACRO, PUBLIC, UP, require,
)

CONTRACT = "econ_aggregate.v1"

#: Below this an index is a handful of companies with a label on it.
MIN_CONTRIBUTORS = 5
#: No single company may be more than this share of a reading.
MAX_CONTRIBUTOR_SHARE = 0.25

#: index name -> (the company node kind it reads, what a rise MEANS)
INDEX_SPECS = {
    "hiring_pressure_index": ("hiring",
                              "companies are adding staff faster than they "
                              "were"),
    "pricing_pressure_index": ("pricing",
                               "companies report raising prices or defending "
                               "price"),
    "inventory_cycle_index": ("inventory",
                              "inventories are building relative to sales"),
    "capex_intention_index": ("capex",
                              "companies are committing to more capacity"),
    "demand_revision_index": ("demand_language",
                              "management language about demand is improving"),
    "supply_constraint_index": ("supply_constraint",
                                "companies report more binding supply "
                                "constraints"),
    "wage_pressure_index": ("wage_pressure",
                            "companies report wage costs rising faster"),
    "financing_conditions_index": ("financing",
                                   "companies describe financing as easier "
                                   "to obtain"),
}


@dataclass(frozen=True)
class Contribution:
    """One company's contribution to one index, with its weight."""

    company_id: str
    node_ids: Tuple[str, ...]
    raw_count: int
    weight: float
    direction: str

    def as_dict(self) -> dict:
        return {"company_id": self.company_id,
                "node_ids": list(self.node_ids),
                "raw_count": self.raw_count,
                "weight": round(self.weight, 4),
                "direction": self.direction}


@dataclass(frozen=True)
class Aggregate:
    """A candidate economic indicator built from public company evidence."""

    name: str
    as_of: str
    direction: str
    #: -1.0 .. +1.0. A DIFFUSION reading, not a level: the share of the panel
    #: moving one way minus the share moving the other. It has no units and
    #: is not comparable to a published statistic, which is why it never
    #: enters a state as OBSERVED.
    score: Optional[float]
    contributors: Tuple[Contribution, ...]
    meaning: str
    #: The evidence node this aggregate becomes, once written. Lineage lives
    #: there, and it is what the double-counting wall reads.
    node_id: str = ""
    sufficient: bool = True
    reason: str = ""

    #: Permanently False. Section 18: these are candidate macro indicators
    #: and are not tradable until forward validated. There is no setter.
    tradable: bool = field(default=False, init=False)

    @property
    def concentration(self) -> float:
        """The largest single company's share. Reported, always."""
        if not self.contributors:
            return 0.0
        return round(max(c.weight for c in self.contributors), 4)

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "name": self.name, "as_of": self.as_of,
                "direction": self.direction,
                "score": None if self.score is None else round(self.score, 4),
                "meaning": self.meaning, "sufficient": self.sufficient,
                "reason": self.reason, "tradable": self.tradable,
                "contributors": [c.as_dict() for c in self.contributors],
                "panel": len(self.contributors),
                "concentration": self.concentration,
                "node_id": self.node_id}


def insufficient(name: str, as_of: str, *, panel: int) -> Aggregate:
    """An honest refusal, not an empty index."""
    spec = INDEX_SPECS.get(name, ("", ""))
    return Aggregate(
        name=name, as_of=as_of, direction=FLAT, score=None, contributors=(),
        meaning=spec[1], sufficient=False,
        reason=(f"{panel} contributing compan{'y' if panel == 1 else 'ies'}; "
                f"{MIN_CONTRIBUTORS} are required before this is an index "
                "rather than a few companies with a label on them"))


def _direction_of(n: EconomicNode) -> str:
    """A node's contribution direction.

    Numeric nodes use the sign of the value. Qualitative ones must state a
    direction in `statement` via the conventional prefixes the founder-side
    signal detectors already emit; anything else contributes NOTHING rather
    than a default. A default direction is how "we could not tell" becomes
    "flat", and flat is a reading.
    """
    if n.value is not None:
        return UP if n.value > 0 else DOWN if n.value < 0 else FLAT
    head = n.statement.strip().lower()[:12]
    if head.startswith(("rising", "increas", "expand", "tighten")):
        return UP
    if head.startswith(("falling", "decreas", "contract", "easing", "slow")):
        return DOWN
    return ""


def build(name: str, *, nodes: Sequence[EconomicNode], as_of: str,
          producer: str = "econ.aggregates") -> Aggregate:
    """Build one candidate index from public company evidence.

    Every contributing node is checked for visibility first, and the check
    RAISES. See the module docstring for why it is not a filter.
    """
    require(name in INDEX_SPECS,
            f"{name!r} is not a declared index; known: {sorted(INDEX_SPECS)}")
    kind, meaning = INDEX_SPECS[name]
    relevant = [n for n in nodes
                if n.node_class == COMPANY and n.kind == kind]
    assert_public(relevant, where=f"aggregates.build({name})")

    by_company: Dict[str, List[EconomicNode]] = {}
    for n in relevant:
        if _direction_of(n):
            by_company.setdefault(n.subject, []).append(n)
    panel = len(by_company)
    if panel < MIN_CONTRIBUTORS:
        return insufficient(name, as_of, panel=panel)

    # Equal weight per COMPANY, not per observation. Weighting by observation
    # would let one company that publishes constantly become the index.
    raw = 1.0 / panel
    capped = min(raw, MAX_CONTRIBUTOR_SHARE)
    contributions: List[Contribution] = []
    for company, items in sorted(by_company.items()):
        ups = sum(1 for n in items if _direction_of(n) == UP)
        downs = sum(1 for n in items if _direction_of(n) == DOWN)
        direction = UP if ups > downs else DOWN if downs > ups else FLAT
        contributions.append(Contribution(
            company_id=company, node_ids=tuple(n.node_id for n in items),
            raw_count=len(items), weight=capped, direction=direction))
    total_weight = sum(c.weight for c in contributions) or 1.0
    score = sum((1.0 if c.direction == UP else -1.0 if c.direction == DOWN
                 else 0.0) * c.weight for c in contributions) / total_weight
    direction = UP if score > 0.1 else DOWN if score < -0.1 else FLAT
    return Aggregate(
        name=name, as_of=as_of, direction=direction, score=score,
        contributors=tuple(contributions), meaning=meaning)


def as_node(agg: Aggregate, *, as_of: str,
            producer: str = "econ.aggregates") -> EconomicNode:
    """Turn a sufficient aggregate into an evidence node WITH ITS LINEAGE.

    `depends_on` is every contributing node id. That is what makes Section 35
    enforceable: when a company analysis later asks whether this index is
    independent corroboration of its own filing, the wall reads this list.

    Standing is INFERRED, never OBSERVED. Nobody published this number; it was
    derived from statements by a stated rule, and the distinction is the
    difference between a statistic and an opinion with arithmetic in it.
    """
    require(agg.sufficient,
            f"{agg.name} is insufficient and may not become an evidence "
            "node; an index nobody can defend is worse than a stated absence")
    parents = tuple(nid for c in agg.contributors for nid in c.node_ids)
    return make_node(
        node_class=MACRO, kind="financial_conditions" if "financing" in
        agg.name else _MACRO_KIND_FOR.get(agg.name, "growth"),
        subject="US", standing=INFERRED, occurred_at=as_of,
        available_at=as_of, publisher="intent-engine",
        value=agg.score, unit="diffusion",
        statement=(f"{agg.name}: {agg.meaning} "
                   f"({agg.direction.lower()}, panel of "
                   f"{len(agg.contributors)})"),
        confidence=min(0.6, 0.2 + 0.05 * len(agg.contributors)),
        visibility=PUBLIC, producer=producer, depends_on=parents,
        venue="derived")


#: Which macro condition each index is a candidate READING OF. Not the same
#: as being that condition: a hiring diffusion index is a candidate reading of
#: labour, and the shared state records it as INFERRED so it can never
#: displace a published labour statistic.
_MACRO_KIND_FOR = {
    "hiring_pressure_index": "labour",
    "wage_pressure_index": "wages",
    "pricing_pressure_index": "inflation",
    "inventory_cycle_index": "industrial_production",
    "capex_intention_index": "business_investment",
    "demand_revision_index": "consumer_demand",
    "supply_constraint_index": "industrial_production",
    "financing_conditions_index": "financial_conditions",
}


def build_all(*, nodes: Sequence[EconomicNode], as_of: str
              ) -> Dict[str, Aggregate]:
    """Every declared index, including the insufficient ones.

    Insufficient indices are RETURNED rather than omitted. "We cannot yet say
    anything about capex intentions, on a panel of two" is a research
    priority; an absent key is indistinguishable from an index nobody thought
    to build.
    """
    return {name: build(name, nodes=nodes, as_of=as_of)
            for name in sorted(INDEX_SPECS)}


def summarise(aggregates: Dict[str, Aggregate]) -> dict:
    ready = [a for a in aggregates.values() if a.sufficient]
    return {"contract": CONTRACT, "indices": len(aggregates),
            "sufficient": len(ready),
            "insufficient": len(aggregates) - len(ready),
            "tradable": 0,
            "note": ("candidate macro indicators derived from public company "
                     "evidence; not tradable until forward validated"),
            "readings": {a.name: {"direction": a.direction,
                                  "score": (None if a.score is None
                                            else round(a.score, 3)),
                                  "panel": len(a.contributors),
                                  "concentration": a.concentration}
                         for a in sorted(ready, key=lambda x: x.name)}}

"""Two-way transmission: economy <-> psychology <-> behaviour <-> companies.

WHY BOTH DIRECTIONS ARE ONE MODULE
----------------------------------
Sections 13 and 14 are the same object read in two directions, and splitting
them into two modules would have let the two halves drift until the loop
stopped closing. Section 15's reflexivity is precisely the case where an
edge in one direction feeds an edge in the other; if psychology->economy and
economy->psychology live in different registries with different vocabularies,
the loop is undetectable by construction.

WHY A CHAIN AND NOT A PAIR
--------------------------
Section 13's example is six links long: anxiety -> deferral -> traffic ->
inventory -> promotion -> margin. Recording only the endpoints ("anxiety
hurts margins") loses every place the chain could break, which is the only
useful thing the chain contains. A `Chain` is therefore an ordered sequence
of edges, and its weakest link is a first-class property.

WHY COMPANY EXPOSURE IS PER-COMPANY
-----------------------------------
Section 13's last line: do not dump the same psychological conclusion into
all companies. Walmart's exposure to household anxiety runs through basket
mix; Visa's runs through ticket size; Caterpillar's does not run through
households at all. `Exposure` names the specific channel, and a company with
no declared channel gets NO reading rather than the population average.

THE PROMOTION GATE
------------------
`registry()` refuses to hand back an edge whose psychological end is not a
PROMOTED construct. That is the join to Section 42: an untested construct
cannot inform a decision, no matter how good the story is.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .causal import CAUSAL_LANGUAGE_FLOOR, DOWN, UP, CausalEdge, edge
from .construct import Construct
from .vocabulary import (
    ALL_KINDS, BEHAVIORAL, COLLECTIVE_DIMENSIONS, NODE_KINDS, PROMOTED,
    EconError, require,
)

CONTRACT = "econ_transmission.v1"

# --- which side of the loop an edge crosses ---------------------------------
PSYCH_TO_ECON = "PSYCH_TO_ECON"
ECON_TO_PSYCH = "ECON_TO_PSYCH"
PSYCH_TO_COMPANY = "PSYCH_TO_COMPANY"
WITHIN_PSYCH = "WITHIN_PSYCH"
DIRECTIONS = (PSYCH_TO_ECON, ECON_TO_PSYCH, PSYCH_TO_COMPANY, WITHIN_PSYCH)


class TransmissionRefused(EconError):
    """An edge was requested whose psychological end has not earned its place."""


def _side(name: str) -> str:
    if name in COLLECTIVE_DIMENSIONS:
        return "PSYCH"
    if name in NODE_KINDS[BEHAVIORAL]:
        return "BEHAVIOUR"
    if name in ALL_KINDS:
        return "ECON"
    return "UNKNOWN"


def crossing(cause: str, effect: str) -> str:
    a, b = _side(cause), _side(effect)
    if a == "PSYCH" and b == "PSYCH":
        return WITHIN_PSYCH
    if a == "PSYCH":
        return PSYCH_TO_ECON
    if b == "PSYCH":
        return ECON_TO_PSYCH
    return PSYCH_TO_COMPANY


@dataclass(frozen=True)
class Link:
    """One edge in a transmission chain, with the construct it depends on."""

    edge: CausalEdge
    crossing: str
    #: The collective construct at either end, if there is one. This is what
    #: `usable()` checks against the register.
    construct: str = ""

    @property
    def gated(self) -> bool:
        """Does this link depend on a psychological construct at all?"""
        return bool(self.construct)

    def as_dict(self) -> dict:
        d = self.edge.as_dict()
        d.update({"crossing": self.crossing, "construct": self.construct,
                  "gated": self.gated})
        return d


def link(*, cause: str, effect: str, sign: str, mechanism: str,
         evidence_level: int, evidence: str, falsifier: str, lag_days: int,
         sample_start: str = "", sample_end: str = "", sample_n: int = 0,
         confidence: float = 0.5, competing_explanation: str = "",
         evidence_nodes: Sequence[str] = ()) -> Link:
    e = edge(cause=cause, effect=effect, sign=sign, mechanism=mechanism,
             evidence_level=evidence_level, evidence=evidence,
             falsifier=falsifier, lag_days=lag_days,
             sample_start=sample_start, sample_end=sample_end,
             sample_n=sample_n, confidence=confidence,
             competing_explanation=competing_explanation,
             evidence_nodes=tuple(evidence_nodes))
    construct = next((n for n in (cause, effect)
                      if n in COLLECTIVE_DIMENSIONS), "")
    return Link(edge=e, crossing=crossing(cause, effect), construct=construct)


@dataclass(frozen=True)
class Chain:
    """An ordered transmission chain (Section 13's six-link example)."""

    name: str
    links: Tuple[Link, ...]
    population: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        require(len(self.links) >= 1, "a chain has at least one link")
        for a, b in zip(self.links, self.links[1:]):
            if a.edge.effect != b.edge.cause:
                raise EconError(
                    f"chain {self.name!r} is broken: {a.edge.effect!r} does "
                    f"not feed {b.edge.cause!r}. A chain whose links do not "
                    "meet is a list of edges with a title.")

    @property
    def path(self) -> List[str]:
        return [self.links[0].edge.cause] + [l.edge.effect for l in self.links]

    @property
    def total_lag_days(self) -> int:
        return sum(l.edge.lag_days for l in self.links)

    @property
    def weakest(self) -> Link:
        """The link most likely to be where this chain actually breaks."""
        return min(self.links, key=lambda l: (l.edge.evidence_level,
                                              l.edge.confidence))

    @property
    def net_sign(self) -> str:
        downs = sum(1 for l in self.links if l.edge.sign == DOWN)
        return UP if downs % 2 == 0 else DOWN

    @property
    def constructs(self) -> List[str]:
        return sorted({l.construct for l in self.links if l.construct})

    @property
    def may_state_causation(self) -> bool:
        """A chain is only as causal as its weakest link."""
        return self.weakest.edge.evidence_level >= CAUSAL_LANGUAGE_FLOOR

    def statement(self) -> str:
        arrow = " -> ".join(self.path)
        verb = ("transmits to" if self.may_state_causation
                else "is ASSOCIATED WITH")
        return (f"{arrow} ({self.net_sign} net, ~{self.total_lag_days}d): "
                f"the chain {verb} its endpoint; weakest link is "
                f"{self.weakest.edge.cause} -> {self.weakest.edge.effect} at "
                f"level {self.weakest.edge.evidence_level}")

    def as_dict(self) -> dict:
        return {"name": self.name, "path": self.path,
                "population": self.population,
                "total_lag_days": self.total_lag_days,
                "net_sign": self.net_sign, "constructs": self.constructs,
                "may_state_causation": self.may_state_causation,
                "weakest_link": self.weakest.as_dict(),
                "links": [l.as_dict() for l in self.links],
                "statement": self.statement(), "note": self.note}


# =============================================================================
# COMPANY EXPOSURE (Section 13's "do NOT dump the same conclusion")
# =============================================================================

@dataclass(frozen=True)
class Exposure:
    """How one collective construct reaches one company, through what."""

    company_id: str
    construct: str
    #: The SPECIFIC channel. "consumer basket mix", not "consumer sentiment".
    channel: str
    sign: str
    #: Which of the company's own measurable quantities this shows up in.
    observable: str
    confidence: float = 0.5
    evidence_nodes: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(self.construct in COLLECTIVE_DIMENSIONS,
                f"{self.construct!r} is not a declared construct")
        require(bool(self.channel),
                f"{self.company_id}/{self.construct}: an exposure names the "
                "channel it runs through. Without one this is the generic "
                "psychology dump Section 13 forbids.")
        require(self.observable in NODE_KINDS["COMPANY"],
                f"{self.observable!r} is not a company quantity; an exposure "
                "that shows up in nothing measurable cannot be falsified")
        require(self.sign in (UP, DOWN), f"unknown sign {self.sign!r}")

    def statement(self) -> str:
        return (f"{self.construct.replace('_',' ')} reaches {self.company_id} "
                f"through {self.channel}, and would show up as "
                f"{self.observable} moving {self.sign}")

    def as_dict(self) -> dict:
        return {"company_id": self.company_id, "construct": self.construct,
                "channel": self.channel, "sign": self.sign,
                "observable": self.observable, "confidence": self.confidence,
                "evidence_nodes": list(self.evidence_nodes),
                "statement": self.statement()}


# =============================================================================
# THE REGISTRY
# =============================================================================

class TransmissionRegistry:
    """Every declared transmission edge, chain and company exposure."""

    def __init__(self) -> None:
        self._chains: Dict[str, Chain] = {}
        self._exposures: Dict[str, List[Exposure]] = {}

    def add_chain(self, c: Chain) -> "TransmissionRegistry":
        self._chains[c.name] = c
        return self

    def add_exposure(self, e: Exposure) -> "TransmissionRegistry":
        self._exposures.setdefault(e.company_id, []).append(e)
        return self

    # --- reading, gated by the register -------------------------------------
    def chains(self, *, register: Sequence[Construct] = (),
               enforce: bool = True) -> List[Chain]:
        """Chains whose psychological constructs have all been promoted.

        `enforce=False` is for the research surface, which must be able to
        SEE untested chains in order to test them. Every decision surface
        calls this with enforce=True, and the difference is the whole gate.
        """
        if not enforce:
            return [self._chains[n] for n in sorted(self._chains)]
        ok = {c.dimension for c in register if c.state == PROMOTED}
        return [self._chains[n] for n in sorted(self._chains)
                if all(d in ok for d in self._chains[n].constructs)]

    def refused_chains(self, *, register: Sequence[Construct] = ()
                       ) -> List[dict]:
        """What the gate is holding back, and why. A work list, not a wall."""
        by_dim = {c.dimension: c for c in register}
        out = []
        for name in sorted(self._chains):
            ch = self._chains[name]
            blocking = [d for d in ch.constructs
                        if by_dim.get(d) is None
                        or by_dim[d].state != PROMOTED]
            if blocking:
                out.append({"chain": name, "path": ch.path,
                            "blocked_by": blocking,
                            "states": {d: (by_dim[d].state if d in by_dim
                                           else "NOT_IN_REGISTER")
                                       for d in blocking}})
        return out

    def exposures(self, company_id: str, *,
                  register: Sequence[Construct] = (),
                  enforce: bool = True) -> List[Exposure]:
        rows = self._exposures.get(company_id, [])
        if not enforce:
            return list(rows)
        ok = {c.dimension for c in register if c.state == PROMOTED}
        return [e for e in rows if e.construct in ok]

    def companies(self) -> List[str]:
        return sorted(self._exposures)

    def summarise(self, *, register: Sequence[Construct] = ()) -> dict:
        allowed = self.chains(register=register, enforce=True)
        refused = self.refused_chains(register=register)
        by_crossing: Dict[str, int] = {d: 0 for d in DIRECTIONS}
        for ch in self._chains.values():
            for l in ch.links:
                by_crossing[l.crossing] = by_crossing.get(l.crossing, 0) + 1
        return {"contract": CONTRACT,
                "chains_declared": len(self._chains),
                "chains_usable": len(allowed),
                "chains_refused": len(refused),
                "refused_detail": refused,
                "links_by_crossing": by_crossing,
                "companies_with_exposure": self.companies(),
                "exposures_declared": sum(len(v)
                                          for v in self._exposures.values()),
                "bidirectional": (by_crossing.get(PSYCH_TO_ECON, 0) > 0
                                  and by_crossing.get(ECON_TO_PSYCH, 0) > 0)}

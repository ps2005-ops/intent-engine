"""`CompanyEconomicState` — one company, in the economy the core knows about.

WHAT THIS FIXES
---------------
Today a founder analysis computes its own macro picture from whatever
documents the company happened to publish, and the market engine holds a much
better one that the analysis cannot see. The result is the product problem
this whole transformation exists for: excellent company evidence beside weak
market context, on the same page, from the same repository.

This object is the join. It carries the company's own measured state AND the
shared economic state it sits in, with the exposure between them stated as a
mechanism rather than assumed from a sector.

EXPOSURE IS EVIDENCE-BOUND, AND THAT RULE IS INHERITED NOT INVENTED
--------------------------------------------------------------------
`external_intel.macro_contract` already refuses a macro factor that is not
bound to a retrieved observation, for a good reason: sector classification
says a payroll company and a chip designer are both "technology", with
opposite exposures to unemployment. `MacroExposure` below keeps that rule --
`evidence_node` is required, and there is no constructor that fills it in
from an industry code.

WHAT IS NOT DUPLICATED HERE
---------------------------
No macro REASONING. The company state names which economic quantities it is
exposed to and by what mechanism; what those quantities are doing comes from
`EconomicState`, and what a shock to them implies comes from
`shock.propagate`. A company report that recomputed the macro picture would
be the drift this object exists to end.

TENANT PRIVACY IS A ONE-WAY VALVE
---------------------------------
A CompanyEconomicState MAY read private evidence -- that is the whole point
of the later Personal AI stage. What it may never do is contribute private
evidence upward. `public_evidence()` is the only accessor the aggregate
builder is allowed to call, and `contribution()` refuses outright if asked
for a private node.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .evidence import EconomicNode, assert_public, public_only
from .state import EconomicState
from .vocabulary import (
    COMPANY, PUBLIC, PrivacyViolation, TENANT_PRIVATE, require,
)

CONTRACT = "company_economic_state.v1"


@dataclass(frozen=True)
class MacroExposure:
    """This company's exposure to one economic quantity, and why we think so."""

    quantity: str
    #: The transmission sentence. Not "rates affect us" -- the path.
    mechanism: str
    direction: str
    #: The evidence node that ESTABLISHES the exposure. Required.
    evidence_node: str
    confidence: float = 0.5
    #: What would show this exposure had stopped holding.
    falsifier: str = ""

    def __post_init__(self) -> None:
        require(bool(self.evidence_node),
                f"exposure to {self.quantity!r} names no evidence; an "
                "exposure inferred from a sector is right often enough to "
                "feel reliable and wrong exactly where it matters")
        require(bool(self.mechanism.strip()),
                "an exposure states the path, not the correlation")

    def as_dict(self) -> dict:
        return {"quantity": self.quantity, "mechanism": self.mechanism,
                "direction": self.direction,
                "evidence_node": self.evidence_node,
                "confidence": round(self.confidence, 3),
                "falsifier": self.falsifier}


@dataclass(frozen=True)
class Engine:
    """One of the company's economic engines, as measured.

    `revenue`, `margin` and `capital` are the three Section 21 names them.
    Each is a reading with the nodes behind it, so a founder surface can show
    what it rests on and a replay can ask what was knowable.
    """

    name: str
    reading: str
    standing: str
    node_ids: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"name": self.name, "reading": self.reading,
                "standing": self.standing, "node_ids": list(self.node_ids)}


@dataclass(frozen=True)
class CompanyEconomicState:
    """One company's economic state, joined to the shared one."""

    company_id: str
    company_name: str
    as_of: str
    #: The shared state this company is being read against. Not a copy --
    #: the same object both surfaces consume.
    economy: Optional[EconomicState] = None
    engines: Tuple[Engine, ...] = ()
    exposures: Tuple[MacroExposure, ...] = ()
    #: Every node this state was built from, private ones included.
    evidence: Tuple[EconomicNode, ...] = ()
    #: Beliefs, expectations and falsifiers scoped to THIS company.
    expectations: Tuple[dict, ...] = ()
    falsifiers: Tuple[str, ...] = ()
    #: Competitor / substitute / adversary readings, and the hypotheses that
    #: attack them. Carried as dicts because their producers live on the
    #: founder side and this package may not import them.
    competitors: Tuple[dict, ...] = ()
    substitutes: Tuple[dict, ...] = ()
    impossible_hypotheses: Tuple[dict, ...] = ()
    #: Which collective constructs reach THIS company, and through what
    #: channel (Section 12's `collective_behavior_exposures`). Deliberately
    #: NOT a copy of the population's state: Section 13's closing line is
    #: that the same psychological conclusion must not be dumped into every
    #: company, and an exposure is what makes the reading company-specific.
    #: Empty is the correct value for a company with no declared channel --
    #: better than the population average, which is a guess wearing a number.
    collective_exposures: Tuple[dict, ...] = ()
    #: Which tenant this state belongs to. Empty means public-only.
    tenant: str = ""

    def __post_init__(self) -> None:
        require(bool(self.company_id), "a company state names its company")
        require(bool(self.as_of), "a company state is dated")
        private = [n for n in self.evidence if n.visibility != PUBLIC]
        if private and not self.tenant:
            raise PrivacyViolation(
                f"{len(private)} private node(s) in a company state with no "
                "tenant. Private evidence is only meaningful inside a tenant "
                "boundary; a tenant-less state holding it has nowhere to "
                "enforce that boundary.")

    # --- the one-way valve --------------------------------------------------
    def public_evidence(self) -> List[EconomicNode]:
        """The only accessor an aggregate builder may call."""
        return public_only(self.evidence)

    def contribution(self, node_ids: Sequence[str]) -> List[EconomicNode]:
        """Named nodes, for the company -> market direction. Refuses private.

        A refusal rather than a filter, deliberately: a caller that asked for
        eleven nodes and silently received four would build an aggregate
        conditioned on material it may not use and report a denominator that
        does not match.
        """
        wanted = {n.node_id: n for n in self.evidence if n.node_id in
                  set(node_ids)}
        assert_public(wanted.values(),
                      where=f"CompanyEconomicState.contribution({self.company_id})")
        return [wanted[i] for i in node_ids if i in wanted]

    # --- reading ------------------------------------------------------------
    @property
    def has_economy(self) -> bool:
        return self.economy is not None

    def exposure_map(self) -> Dict[str, List[str]]:
        return {self.company_id: [e.quantity for e in self.exposures]}

    def live_exposures(self) -> List[Tuple[MacroExposure, object]]:
        """Exposures paired with what the economy is actually doing.

        Returns the exposure and its ConditionReading. An exposure whose
        quantity the shared state does not measure comes back with an UNKNOWN
        reading rather than being dropped: "we are exposed to real yields and
        nobody here is measuring them" is a research priority, and dropping it
        makes the company look less exposed than it is.
        """
        if self.economy is None:
            return [(e, None) for e in self.exposures]
        return [(e, self.economy.reading(e.quantity)) for e in self.exposures]

    def uncertainty(self) -> dict:
        measured = sum(1 for _, r in self.live_exposures()
                       if r is not None and getattr(r, "known", False))
        return {"exposures": len(self.exposures),
                "measured_by_the_economy": measured,
                "unmeasured": [e.quantity for e, r in self.live_exposures()
                               if r is None or not getattr(r, "known", False)],
                "evidence_nodes": len(self.evidence),
                "public_nodes": len(self.public_evidence()),
                "has_shared_economy": self.has_economy}

    def as_dict(self, *, include_private: bool = False) -> dict:
        """Serialise. Private evidence is EXCLUDED unless explicitly asked for.

        The default is the safe one because the caller who forgets is the
        caller who is writing to a file, a response body or a log.
        """
        nodes = (self.evidence if include_private
                 else tuple(self.public_evidence()))
        return {
            "contract": CONTRACT, "company_id": self.company_id,
            "company_name": self.company_name, "as_of": self.as_of,
            "tenant": self.tenant,
            "economy": self.economy.as_dict() if self.economy else None,
            "engines": [e.as_dict() for e in self.engines],
            "exposures": [e.as_dict() for e in self.exposures],
            "evidence": [n.as_dict() for n in nodes],
            "expectations": [dict(e) for e in self.expectations],
            "falsifiers": list(self.falsifiers),
            "competitors": [dict(c) for c in self.competitors],
            "collective_exposures": [dict(x)
                                     for x in self.collective_exposures],
            "substitutes": [dict(s) for s in self.substitutes],
            "impossible_hypotheses": [dict(h)
                                      for h in self.impossible_hypotheses],
            "uncertainty": self.uncertainty(),
            "private_evidence_withheld": (
                0 if include_private
                else len(self.evidence) - len(nodes)),
        }


def build(*, company_id: str, company_name: str, as_of: str,
          evidence: Sequence[EconomicNode] = (),
          economy: Optional[EconomicState] = None,
          exposures: Sequence[MacroExposure] = (),
          engines: Sequence[Engine] = (), tenant: str = "",
          competitors: Sequence[dict] = (),
          substitutes: Sequence[dict] = (),
          impossible_hypotheses: Sequence[dict] = (),
          expectations: Sequence[dict] = (),
          collective_exposures: Sequence[dict] = (),
          falsifiers: Sequence[str] = ()) -> CompanyEconomicState:
    """The supported constructor. Exposure evidence must be IN the evidence.

    An exposure naming a node the state does not hold is unverifiable, and an
    unverifiable exposure is exactly the sector-inferred one this contract
    refuses -- with an id attached to make it look checked.
    """
    known = {n.node_id for n in evidence}
    missing = [e.quantity for e in exposures if e.evidence_node not in known]
    require(not missing,
            f"exposure(s) {missing} name evidence nodes this state does not "
            "hold; an exposure whose evidence cannot be read is a sector "
            "guess with an id attached")
    return CompanyEconomicState(
        company_id=company_id, company_name=company_name, as_of=as_of,
        economy=economy, engines=tuple(engines), exposures=tuple(exposures),
        evidence=tuple(evidence), tenant=tenant,
        competitors=tuple(competitors), substitutes=tuple(substitutes),
        impossible_hypotheses=tuple(impossible_hypotheses),
        expectations=tuple(expectations),
        collective_exposures=tuple(collective_exposures),
        falsifiers=tuple(falsifiers))

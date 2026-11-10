"""Which sections this company's report gets, in what order, at what depth.

WHY A COMPOSER AND NOT A DASHBOARD PER VERTICAL
-----------------------------------------------
A dashboard per vertical is ten products to maintain and ten places for the
same defect to hide, and the eleventh company still gets nothing. One
composer with a declared module set is one product, and a new company is a new
composition rather than new code.

WHAT MAKES THE ADAPTATION REAL
------------------------------
Hiding and showing cards at random is indistinguishable from adaptation on any
single screen. The difference is that every decision here is ACCOUNTABLE: each
module carries `included`, `reason`, `depth` and `emphasis`, and the reason
names the input that decided it -- the lens, the business model, the evidence,
the decision priority, the confidence, or the reader's role.

That is also what makes it testable. A composition whose reasons are all
"default" has not adapted, and `test_composition_is_explained` fails on it.

MODULES DECLARE THEIR OWN PRECONDITIONS
---------------------------------------
`requires` is what a module needs before it can honestly be shown. A module
whose precondition fails is not silently dropped: it becomes `included=False`
with the reason, so the report can say what it does NOT have. A section that
vanishes without explanation is how a reader concludes the analysis was thin
when in fact one input was missing.
"""
from __future__ import annotations

import dataclasses
from typing import Callable, Dict, Optional, Tuple

CONTRACT = "adaptive_report_composition.v1"

FULL, STANDARD, BRIEF = "full", "standard", "brief"
LEAD, PRIMARY, SUPPORTING = "lead", "primary", "supporting"


@dataclasses.dataclass(frozen=True)
class Module:
    module_id: str
    title: str
    #: what must be true before this can honestly be shown
    requires: Tuple[str, ...] = ()
    #: base position when nothing argues otherwise (lower is earlier)
    base_rank: int = 50
    #: True for modules that must appear on every report that has anything
    always: bool = False

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


MODULES: Tuple[Module, ...] = (
    Module("executive_change", "What changed", ("causal_chain",), 10),
    Module("strategic_thesis", "The strategic read", ("analysis",), 12,
           always=True),
    Module("why_this_is_different", "Why this analysis is different",
           ("differentiation",), 14, always=True),
    Module("strategic_lens", "The lens this analysis is using",
           ("lens",), 16, always=True),
    Module("decision_opportunity_map", "Where intelligence could change a "
           "decision", ("opportunities",), 20, always=True),
    Module("causal_chain", "From the change to the decision",
           ("causal_chain",), 24),
    Module("decision_delta", "What we would do differently",
           ("opportunities",), 28),
    Module("economic_exposure", "What reaches this company",
           ("macro_exposures",), 32),
    Module("market_belief", "What the market believes", ("market",), 34),
    Module("customer_signals", "What customers are doing", ("analysis",), 36),
    Module("competitive_response", "What a competitor does about it",
           ("competitive",), 38),
    Module("supply_chain_exposure", "Supply chain exposure",
           ("physical_inputs",), 40),
    Module("financial_sensitivity", "Financial sensitivity",
           ("financials",), 42),
    Module("data_ai_exposure", "Data and AI exposure",
           ("technology_exposure",), 44),
    Module("regulatory_exposure", "Regulatory exposure",
           ("regulatory_exposure",), 46),
    Module("client_portfolio", "Client portfolio exposure",
           ("services_business",), 48),
    Module("operational_intelligence", "Operational picture",
           ("analysis",), 50),
    Module("contradictions", "What argues against this", ("analysis",), 56),
    Module("alternative_interpretation", "A different reading of the same "
           "evidence", ("analysis",), 58),
    Module("scenario_comparison", "How this could go", ("scenarios",), 60),
    Module("what_would_change_our_mind", "What would change our mind",
           ("analysis",), 64, always=True),
    Module("information_priority", "What to find out next", (), 68,
           always=True),
    Module("learning_state", "What this system expects next", (), 72),
    Module("evidence", "The evidence", ("observations",), 80, always=True),
    Module("provenance", "Where this came from", (), 84, always=True),
    Module("ask_intent_engine", "Ask Intent Engine", (), 90, always=True),
)

_BY_ID = {m.module_id: m for m in MODULES}


@dataclasses.dataclass(frozen=True)
class ComposedModule:
    module_id: str
    title: str
    included: bool
    reason: str
    depth: str = STANDARD
    emphasis: str = SUPPORTING
    rank: int = 50

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ComposedReport:
    modules: Tuple[ComposedModule, ...] = ()
    #: the reader this composition was built for
    role_id: str = "ceo"
    lens_id: str = ""
    #: how many INCLUDED modules were positioned by an input rather than by
    #: their default. Exclusions are counted separately: a report that
    #: excluded twelve modules and adapted none would otherwise report a
    #: high `explained` and look adaptive. A break proof that disabled the
    #: adaptation ran GREEN on exactly that arithmetic.
    explained: int = 0
    #: how many exclusions named the precondition that failed
    excluded_explained: int = 0
    contract: str = CONTRACT

    @property
    def included_ids(self) -> Tuple[str, ...]:
        return tuple(m.module_id for m in self.modules if m.included)

    @property
    def excluded(self) -> Tuple[ComposedModule, ...]:
        return tuple(m for m in self.modules if not m.included)

    def module(self, module_id: str) -> Optional[ComposedModule]:
        for m in self.modules:
            if m.module_id == module_id:
                return m
        return None

    def as_dict(self) -> dict:
        return {"modules": [m.as_dict() for m in self.modules],
                "included": list(self.included_ids),
                "role_id": self.role_id, "lens_id": self.lens_id,
                "explained": self.explained,
                "excluded_explained": self.excluded_explained,
                "contract": self.contract}


def _preconditions(*, profile, analysis, lens_selection, opportunities,
                   causal_chain, differentiation, observations,
                   market=None) -> Dict[str, Tuple[bool, str]]:
    """Every precondition, with the sentence to print when it fails."""
    model = getattr(profile, "business_model_class", "UNKNOWN")
    physical = model in ("DESIGN_AND_MANUFACTURE", "COMMODITY_PRODUCER",
                         "BRANDED_CONSUMER", "SCALE_RETAIL",
                         "MANUFACTURE_AND_AFTERMARKET",
                         "CONTRACTED_OR_RATE_BASE_ASSETS")
    services = model == "PEOPLE_OR_ROUTE_BASED_SERVICES"
    competitive = getattr(analysis, "competitive", None) or {}
    scenarios = getattr(analysis, "scenarios", None) or {}
    return {
        "analysis": (
            analysis is not None,
            "no strategic reading was produced for this run, so nothing "
            "here would rest on one"),
        "lens": (
            bool(getattr(lens_selection, "primary", "")),
            "no lens was selected, because this company's own material does "
            "not say clearly enough what decision it serves"),
        "differentiation": (
            bool(differentiation),
            "nothing company-specific was established, so there is no "
            "difference to state"),
        "opportunities": (
            bool(opportunities),
            "no decision opportunity cleared the evidence bar"),
        "causal_chain": (
            bool(causal_chain),
            "no mechanism connecting an external change to this company was "
            "established"),
        "macro_exposures": (
            bool(getattr(profile, "macro_exposures", ())),
            "no macroeconomic channel has an established mechanism into a "
            "business of this kind"),
        "technology_exposure": (
            bool(getattr(profile, "technology_exposure", None)),
            "this company's own material does not describe its product in "
            "technology terms, so no direct exposure is asserted"),
        "regulatory_exposure": (
            bool(getattr(profile, "regulatory_exposure", None)),
            "no regulatory regime was established for this company"),
        "physical_inputs": (
            physical,
            "this business has no physical inputs, so it has no supply-chain "
            "exposure to report"),
        "services_business": (
            services,
            "this is not a client-delivery business, so there is no client "
            "portfolio to report"),
        "competitive": (
            bool(competitive.get("who_must_respond")
                 or competitive.get("who_is_forcing_the_change")),
            "the evidence did not establish who is applying the pressure or "
            "who has to answer it"),
        "scenarios": (
            bool(scenarios.get("upside_case") or scenarios.get("downside_case")),
            "no scenario pair was established"),
        "financials": (
            any("financial" in str(g).lower() or "margin" in str(g).lower()
                for g in getattr(profile, "revenue_drivers", ()) or ())
            or bool(getattr(profile, "capital_intensity", None)),
            "no financial disclosure was retrieved for this company"),
        "observations": (
            bool(observations),
            "no observation was retrieved"),
        "market": (
            market is not None,
            "no market snapshot is available for this company"),
    }


def compose_report(*, profile=None, analysis=None, lens_selection=None,
                   opportunity_map=None, causal_chain=None,
                   differentiation=None, observations=(), market=None,
                   role_id: str = "ceo") -> ComposedReport:
    """Decide which sections this report gets, in what order, at what depth."""
    lens = getattr(lens_selection, "lens", None)
    opportunities = tuple(getattr(opportunity_map, "opportunities", ()) or ())
    preferred = tuple(getattr(lens, "preferred_report_modules", ()) or ())
    top_priority = (opportunities[0].decision_priority if opportunities
                    else 0.0)
    specificity = float(getattr(profile, "specificity", 0.0) or 0.0)
    confidence = str(getattr(profile, "confidence", "none"))

    pre = _preconditions(
        profile=profile, analysis=analysis, lens_selection=lens_selection,
        opportunities=opportunities, causal_chain=causal_chain,
        differentiation=differentiation, observations=observations,
        market=market)

    composed, explained, excluded_explained = [], 0, 0
    for module in MODULES:
        failed = [pre[r][1] for r in module.requires
                  if r in pre and not pre[r][0]]
        if failed and not module.always:
            composed.append(ComposedModule(
                module.module_id, module.title, False,
                reason=f"Not shown: {failed[0]}.", rank=module.base_rank))
            excluded_explained += 1
            continue
        if failed and module.always:
            # An ALWAYS module whose precondition failed is still shown, and
            # says what it does not have. A report that silently drops its
            # own epistemic sections is a report that looks more confident
            # than it is.
            composed.append(ComposedModule(
                module.module_id, module.title, True,
                reason=(f"Shown with what is available: {failed[0]}."),
                depth=BRIEF, emphasis=SUPPORTING, rank=module.base_rank))
            excluded_explained += 1
            continue

        rank, depth, emphasis, reasons = module.base_rank, STANDARD, \
            SUPPORTING, []

        if module.module_id in preferred:
            rank -= 20
            emphasis = PRIMARY
            depth = FULL
            reasons.append(
                f"the {lens.name} lens this company's evidence selected "
                f"reads it as central")
        if module.module_id in ("why_this_is_different", "strategic_lens"):
            emphasis = LEAD
            reasons.append("it is what makes this report about this company "
                           "rather than about its industry")
        if module.module_id == "decision_opportunity_map" and opportunities:
            emphasis = LEAD if top_priority >= 0.25 else PRIMARY
            reasons.append(
                f"the top-ranked decision scored {top_priority:.2f}, so it "
                + ("leads" if top_priority >= 0.25 else "is shown but does "
                   "not lead"))
        if module.module_id == "causal_chain" and causal_chain is not None:
            if causal_chain.generic_links and causal_chain.links:
                depth = BRIEF
                reasons.append(
                    f"{causal_chain.generic_links} of "
                    f"{len(causal_chain.links)} links name nothing specific "
                    f"to this company, so it is shown short and marked")
            else:
                reasons.append(
                    f"every link is tied to this company's own evidence "
                    f"({causal_chain.evidence_coverage:.0%} carry a cited "
                    f"observation)")
        if module.module_id == "why_this_is_different" and \
                differentiation is not None and differentiation.flagged:
            depth = BRIEF
            reasons.append("the difference is real but thin, so it is stated "
                           "short rather than expanded")
        if module.module_id in ("contradictions", "what_would_change_our_mind",
                                "information_priority"):
            if confidence in ("none", "low") or specificity < 0.34:
                rank -= 24
                emphasis = PRIMARY
                depth = FULL
                reasons.append(
                    f"confidence here is {confidence} and only "
                    f"{specificity:.0%} of what is established came from "
                    f"this company's own evidence, so what is NOT known is "
                    f"raised rather than buried")
        if module.module_id == "evidence" and observations:
            reasons.append(f"{len(observations)} observation(s) were "
                           f"retrieved and every claim resolves to one")

        composed.append(ComposedModule(
            module.module_id, module.title, True,
            reason=("Shown because " + "; ".join(reasons) + "."
                    if reasons else
                    "Shown in its default position: nothing about this "
                    "company argued for moving it."),
            depth=depth, emphasis=emphasis, rank=rank))
        if reasons:
            explained += 1

    composed.sort(key=lambda m: (m.rank, m.module_id))
    return ComposedReport(
        modules=tuple(composed), role_id=str(role_id or "ceo"),
        lens_id=str(getattr(lens_selection, "primary", "") or ""),
        explained=explained, excluded_explained=excluded_explained)


def module_by_id(module_id: str) -> Optional[Module]:
    return _BY_ID.get(str(module_id or ""))

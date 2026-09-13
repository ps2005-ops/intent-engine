"""One call that produces the whole adaptive reading, and its telemetry.

WHY A SINGLE ENTRY POINT
------------------------
Because the alternative is what the product already learned not to do: each
page composing its own read, and two screens of one run disagreeing about what
kind of company they are describing. The producers below run in a fixed order
because each one is an input to the next --

    classify -> profile -> lens -> opportunities -> causal chain
             -> differentiation -> composition -> role view

-- and a caller that ran them in any other order would be building a lens from
a profile that did not exist yet.

`build` NEVER RAISES. A surface that cannot render its adaptive block should
show the ordinary analysis, not a 500. Every producer is individually guarded
and a failure is recorded in `errors` and reported in telemetry, so a silent
degradation is impossible: a missing block always has a named cause.

TELEMETRY IS NOT OPTIONAL
-------------------------
Every field in `telemetry()` exists because a matrix run that fails on it has
to be able to say WHY from its own output. A blank cell in a qualification
matrix costs a whole re-run to explain, and the recorded lesson is that an
instrument naming producer fields wrongly invents uniform defects.
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Optional, Tuple

from intent_engine.adaptive import causal, composer, differentiation, lens
from intent_engine.adaptive import opportunity as opp
from intent_engine.adaptive import profile as prof
from intent_engine.adaptive import roles

log = logging.getLogger(__name__)


def _engine_roles(profile, lens_selection) -> tuple:
    """Where this product could do work for THIS company.

    Composed from the lens the company's own evidence selected, so a
    consultancy is offered client-portfolio work and a data-security vendor
    is offered regulatory monitoring. Empty when no lens was selected, which
    is honest: with no reading of what the company is for, a list of things
    we could do for it would be a list of things we do for anybody.
    """
    entry = getattr(lens_selection, "lens", None)
    if entry is None:
        return ()
    roles = [f"watch {domain}" for domain in entry.decision_domains[:3]]
    if getattr(profile, "critical_dependencies", ()):
        roles.append(
            f"monitor {profile.critical_dependencies[0].value}, which this "
            f"company names as something it depends on")
    if getattr(profile, "falsifiers", ()):
        roles.append("test the assumption this reading rests on, and say "
                     "when it stops holding")
    return tuple(roles[:5])

CONTRACT = "adaptive_intelligence.v1"


@dataclasses.dataclass(frozen=True)
class AdaptiveIntelligence:
    company: str = ""
    profile: Optional[prof.CompanyStrategicProfile] = None
    lens_selection: Optional[lens.LensSelection] = None
    opportunity_map: Optional[opp.DecisionOpportunityMap] = None
    causal_chain: Optional[causal.CausalChain] = None
    differentiation: Optional[differentiation.Differentiation] = None
    composition: Optional[composer.ComposedReport] = None
    role: Optional[roles.RoleView] = None
    errors: Tuple[str, ...] = ()
    contract: str = CONTRACT

    @property
    def headline_lens(self) -> str:
        """The line that replaces the generic page title.

        Empty when no lens was selected, which the caller renders as the
        company name alone -- never as a lens name we did not earn.
        """
        return str(getattr(self.lens_selection, "primary_name", "") or "")

    @property
    def top_opportunity(self):
        return getattr(self.opportunity_map, "top", None)

    def telemetry(self) -> dict:
        p, l = self.profile, self.lens_selection
        m, c = self.opportunity_map, self.causal_chain
        d, comp = self.differentiation, self.composition
        top = self.top_opportunity
        cls = getattr(p, "classification", None)
        return {
            "contract": CONTRACT,
            "company": self.company,
            "company_profile_status": getattr(p, "profile_state", "ABSENT"),
            "company_profile_source": getattr(p, "profile_source", "NONE"),
            "business_model_source": prof.model_source_of(
                getattr(p, "profile_source", "NONE")),
            "business_model_source_words": prof.MODEL_SOURCE_WORDS.get(
                prof.model_source_of(getattr(p, "profile_source", "NONE")),
                ""),
            "business_model_alternatives": (
                [getattr(cls, "runner_up", "")]
                if getattr(cls, "runner_up", "") else []),
            # THE THREE STATES A RUN CAN HONESTLY BE IN, reported separately
            # because they are separate questions and a reader (or a matrix)
            # that collapses them cannot tell "we understand this company and
            # will not guess" from "we could not read this company".
            "profile_available": bool(getattr(p, "known", False)),
            "lens_available": bool(getattr(l, "primary", "")),
            "decision_reading_available": bool(
                getattr(m, "has_reading", False)),
            "decision_map_state": getattr(m, "state", ""),
            "causal_chain_kind": getattr(c, "kind", ""),
            "potential_domains": [d.domain for d in
                                  (getattr(m, "domains", ()) or ())],
            "evidence_limitation": getattr(m, "evidence_limitation", ""),
            "what_would_unlock_a_decision": getattr(
                m, "what_would_unlock_a_decision", ""),
            "business_model": getattr(p, "business_model_class", "UNKNOWN"),
            "business_model_confidence": getattr(cls, "confidence", ""),
            "business_model_evidence": (getattr(cls, "evidence_span", "")
                                        or "")[:200],
            "business_model_reason": (getattr(cls, "reason", "") or "")[:240],
            "customer_job": getattr(getattr(p, "customer_job", None),
                                    "value", "")[:200],
            "customer_job_provenance": getattr(
                getattr(p, "customer_job", None), "provenance", ""),
            "strategic_assets": [f.value for f in
                                 (getattr(p, "strategic_assets", ()) or ())],
            "critical_dependencies": [
                f.value for f in
                (getattr(p, "critical_dependencies", ()) or ())],
            "company_specificity_score": getattr(p, "specificity", 0.0),
            "company_specific_fields": list(
                getattr(p, "company_specific_fields", ()) or ()),
            "decision_opportunity_count": len(
                getattr(m, "opportunities", ()) or ()),
            "decision_opportunities_considered": getattr(m, "considered", 0),
            "decision_opportunities_withheld": list(
                getattr(m, "withheld", ()) or ()),
            "top_decision_domain": getattr(top, "decision_domain", ""),
            "top_decision_owner": getattr(top, "decision_owner_role", ""),
            "top_decision_priority": getattr(top, "decision_priority", 0.0),
            "top_decision_components": ({
                "materiality": top.materiality,
                "change_velocity": top.change_velocity,
                "company_exposure": top.company_exposure,
                "actionability": top.actionability,
                "evidence_strength": top.evidence_strength,
                "uncertainty": top.uncertainty,
                "evidence_gap": top.evidence_gap,
                "genericity": top.genericity} if top is not None else {}),
            "primary_lens": getattr(l, "primary", ""),
            "primary_lens_name": getattr(l, "primary_name", ""),
            "lens_confidence": getattr(l, "confidence", "none"),
            "secondary_lenses": list(getattr(l, "secondary", ()) or ()),
            "lens_selection_reasons": (getattr(l, "why_selected", "") or "")[:400],
            "lens_refusals": list(
                getattr(l, "why_others_were_not_selected", ()) or ())[:6],
            "causal_chain_nodes": len(getattr(c, "links", ()) or ()),
            "causal_chain_evidence_coverage": getattr(
                c, "evidence_coverage", 0.0),
            "causal_chain_stopped_because": (
                getattr(c, "stopped_because", "") or "")[:240],
            "genericity_flags": (
                (getattr(c, "generic_links", 0) or 0)
                + (1 if getattr(d, "flagged", False) else 0)),
            "differentiation_carried_by": list(
                getattr(d, "carried_by", ()) or ()),
            "differentiation_flagged": bool(getattr(d, "flagged", False)),
            "differentiation_flag_reason": (
                getattr(d, "flag_reason", "") or "")[:300],
            "counterevidence_present": bool(
                getattr(top, "contradicting_evidence", "")),
            "information_priority": getattr(
                top, "recommended_information_next", ""),
            "abstention_reason": (getattr(m, "reason", "") or "")[:300],
            "role_lens": getattr(self.role, "role_id", ""),
            "role_module_order": list(getattr(self.role, "order", ()) or []),
            "role_promoted": list(getattr(self.role, "promoted", ()) or []),
            "composition_modules": list(
                getattr(comp, "included_ids", ()) or []),
            "composition_excluded": [
                m.module_id for m in (getattr(comp, "excluded", ()) or ())],
            "composition_explained": getattr(comp, "explained", 0),
            "reasoning_provenance": getattr(p, "provenance", ""),
            "errors": list(self.errors),
        }


def build(*, company: str, domain: str = "", evidence_text: str = "",
          intelligence_profile=None, analysis=None, observations=(),
          documents=(), identity_line: str = "", market=None,
          role_id: str = "ceo") -> AdaptiveIntelligence:
    """Run every producer in dependency order. Never raises."""
    errors = []

    def _guard(name, fn, fallback):
        try:
            return fn()
        except Exception as exc:                             # noqa: BLE001
            log.exception("adaptive_%s_failed company=%s", name, company)
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:160]}")
            return fallback

    p = _guard("profile", lambda: prof.build_profile(
        company=company, domain=domain, evidence_text=evidence_text,
        intelligence_profile=intelligence_profile, analysis=analysis,
        observations=observations, documents=documents,
        identity_line=identity_line), prof.CompanyStrategicProfile(
            canonical_name=company, domain=domain))

    l = _guard("lens", lambda: lens.select_lens(
        evidence_text=evidence_text,
        business_model=p.business_model_class if p.known else "",
        exposures=tuple(p.macro_exposures) + tuple(p.operational_exposures),
        decision_domains=tuple(p.decision_cycles)), lens.LensSelection())

    # WHAT INTENT ENGINE COULD DO FOR THIS COMPANY, which cannot be known
    # until the lens is. The profile is frozen, so this is a replacement
    # rather than a mutation -- the object every consumer sees is the one
    # with the field populated, and there is never a moment where two
    # versions of one company's profile are in flight.
    #
    # It was declared and never written. A field that is always empty reads
    # as "there is no role for us here", which is the opposite of the claim
    # the product is making.
    p = _guard("engine_roles", lambda: dataclasses.replace(
        p, potential_intent_engine_roles=_engine_roles(p, l)), p)

    m = _guard("opportunities", lambda: opp.build_opportunity_map(
        company=company, profile=p, analysis=analysis, lens_selection=l,
        observations=observations), opp.DecisionOpportunityMap())

    c = _guard("causal_chain", lambda: causal.build_causal_chain(
        company=company, profile=p, analysis=analysis,
        opportunity=m.top, lens_selection=l,
        observations=observations), causal.CausalChain())

    d = _guard("differentiation", lambda: differentiation.build_differentiation(
        company=company, profile=p, lens_selection=l, analysis=analysis,
        opportunity=m.top, causal_chain=c), differentiation.Differentiation())

    comp = _guard("composition", lambda: composer.compose_report(
        profile=p, analysis=analysis, lens_selection=l, opportunity_map=m,
        causal_chain=c, differentiation=d, observations=observations,
        market=market, role_id=role_id), composer.ComposedReport())

    rv = _guard("role", lambda: roles.role_view(
        role_id=role_id, module_ids=comp.included_ids, lens_selection=l),
        roles.RoleView(role_id=role_id, title="", status=roles.FUTURE))

    return AdaptiveIntelligence(
        company=company, profile=p, lens_selection=l, opportunity_map=m,
        causal_chain=c, differentiation=d, composition=comp, role=rv,
        errors=tuple(errors))

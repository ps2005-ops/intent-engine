"""The neutral join. It validates, it states, it never concludes.

WHAT THIS MODULE IS ALLOWED TO DERIVE
--------------------------------------
Metadata about the JOIN, and nothing else: whether each side arrived, whether
their evidence windows may honestly be compared, whether their populations may
be mixed, whether anything disqualifies the result, and how ready it is to
show somebody.

WHAT IT IS FORBIDDEN TO DERIVE
-------------------------------
A thesis, a recommendation, a causal standing, a confidence, an internal
impact, a competitor's intent. Every one of those already has exactly one
canonical producer, and a second derivation is a second copy of a rule that
will drift from the first. `test_the_dossier_seam_stays_neutral` tokenizes
this module and fails on any import that would make such a derivation
possible; the guards below make it unnecessary as well as impossible.

A NOTE ON DETERMINISM
----------------------
`assemble()` takes `now` rather than reading a clock. Two assemblies of the
same inputs must produce the same `content_key`, or §14's idempotence is a
coin flip and the 100-company second pass reports change everywhere.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Optional, Tuple

from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.contracts import (
    REF_NOT_A_ZERO, FounderDemoSnapshot, MarketDemoSnapshot)
from intent_engine.demo_dossier.dossier import CompanyDemoDossier

#: Market blocks that appear in the dossier, and the name each is stated
#: under. A block absent from the snapshot is UNAVAILABLE with a reason —
#: never an empty list, and never a zero (§21).
_MARKET_VIEW = (
    ("evidence", "evidence_reference_ids"),
    ("economic_state", "economic_state_refs"),
    ("demand", "demand_state_refs"),
    ("beliefs", "belief_refs"),
    ("theses", "thesis_refs"),
    ("thesis_history", "thesis_revision_refs"),
    ("expectations", "expectation_refs"),
    ("reconciliations", "reconciliation_refs"),
    ("contradictions", "contradiction_refs"),
    ("causal_questions", "causal_question_refs"),
    ("causal_results", "causal_result_refs"),
    ("replay", "replay_refs"),
    ("adversary", "adversary_refs"),
)

_FOUNDER_VIEW = (
    ("living_decisions", "living_decision_refs"),
    ("minimum_data_requests", "mdr_refs"),
    ("minimum_viable_experiments", "mve_refs"),
    ("evidence", "evidence_reference_ids"),
)

#: Both sides present and readable. The ONLY value that means the bridge
#: actually opened; every other value is reported rather than hidden (§34).
CROSSING_BOTH = "MARKET_AND_FOUNDER"
CROSSING_FOUNDER_ONLY = "FOUNDER_AVAILABLE_MARKET_UNAVAILABLE"
CROSSING_MARKET_ONLY = "MARKET_AVAILABLE_FOUNDER_UNAVAILABLE"
CROSSING_NEITHER = "NEITHER_AVAILABLE"
CROSSING_STATES = (CROSSING_BOTH, CROSSING_FOUNDER_ONLY,
                   CROSSING_MARKET_ONLY, CROSSING_NEITHER)


def _days_between(a: str, b: str) -> Optional[int]:
    try:
        return abs((date.fromisoformat(str(a)[:10])
                    - date.fromisoformat(str(b)[:10])).days)
    except (ValueError, TypeError):
        return None


def temporal_compatibility(market: MarketDemoSnapshot,
                           founder: FounderDemoSnapshot) -> str:
    """Whether the two sides may be read as describing one moment.

    WINDOW_UNKNOWN is returned whenever either side declined to state its
    cutoff. That is NOT the same as agreeing, and it is deliberately outside
    `IMPACT_COMPARABLE_WINDOWS`: a before/after claim across a window nobody
    stated is a claim about evidence nobody has.
    """
    if not (market.has_content and founder.has_content):
        return V.WINDOW_UNKNOWN
    a, b = market.evidence_cutoff, founder.evidence_cutoff
    if not a or not b:
        return V.WINDOW_UNKNOWN
    gap = _days_between(a, b)
    if gap is None:
        return V.WINDOW_UNKNOWN
    if gap == 0:
        return V.SAME_WINDOW
    if gap <= V.BOUNDED_WINDOW_DAYS:
        return V.COMPATIBLE_BOUNDED_WINDOW
    return V.DIFFERENT_WINDOW


def population_compatibility(market: MarketDemoSnapshot,
                             founder: FounderDemoSnapshot) -> str:
    """Look the pair up in the table. A pair not in the table is UNKNOWN.

    Reading a table rather than branching is the point: what is permitted can
    be read in one place, and a combination nobody has decided about is
    refused by absence rather than allowed by fallthrough.
    """
    if not market.has_content:
        return (V.POPULATION_UNKNOWN if not founder.has_content
                else {V.REAL_ENTERPRISE: V.POPULATION_COHERENT_REAL,
                      V.SYNTHETIC_ENTERPRISE: V.POPULATION_COHERENT_SYNTHETIC
                      }.get(founder.data_population, V.POPULATION_UNKNOWN))
    if not founder.has_content:
        return {V.REAL_MARKET: V.POPULATION_COHERENT_REAL,
                V.SYNTHETIC_MARKET: V.POPULATION_COHERENT_SYNTHETIC
                }.get(market.market_population, V.POPULATION_UNKNOWN)
    return V.POPULATION_JOIN.get(
        (market.market_population, founder.data_population),
        V.POPULATION_UNKNOWN)


def _tenant_leak(market: MarketDemoSnapshot,
                 founder: FounderDemoSnapshot) -> bool:
    """Whether the market snapshot echoes the founder's tenant identity.

    Market intelligence is derived from public evidence and cannot know a
    tenant id. If one appears in its references or summaries, the payload was
    assembled somewhere it should not have been, and the join is refused
    rather than reasoned about. The contract already refuses a market field
    NAMED for a tenant; this catches the same identity smuggled as a value.
    """
    tenant = (founder.tenant_id or "").strip()
    if not tenant or len(tenant) < 4:
        return False
    haystack = [tenant in i for blk in market.blocks.values() for i in blk.ids]
    for summary in (market.source_health_summary, market.evidence_summary,
                    market.learning_summary, market.provenance_summary):
        if summary:
            haystack.append(tenant in str(summary))
    haystack.append(tenant in market.reason)
    return any(haystack)


def _quarantine(market: MarketDemoSnapshot, founder: FounderDemoSnapshot,
                temporal: str, population: str) -> Tuple[str, ...]:
    """Every condition that disqualifies this dossier from being shown."""
    reasons = []
    if (market.has_content and founder.has_content and market.company_id
            and founder.company_id
            and market.company_id != founder.company_id):
        reasons.append(V.WRONG_COMPANY_EVIDENCE)
    if _tenant_leak(market, founder):
        reasons.append(V.TENANT_LEAK)
    if temporal == V.DIFFERENT_WINDOW:
        reasons.append(V.TEMPORAL_LEAK)
    if population == V.POPULATION_REFUSED:
        reasons.append(V.REAL_SYNTHETIC_POPULATION_MIX)
    if V.CONTRACT_INCOMPATIBLE in (market.contract_state,
                                   founder.contract_state):
        # Only a side that CLAIMED to be here counts. A market snapshot that
        # was simply never produced is UNAVAILABLE, not incompatible, and
        # must not quarantine an otherwise sound founder-only dossier.
        if (market.availability == V.INCOMPATIBLE
                or founder.availability == V.INCOMPATIBLE):
            reasons.append(V.CONTRACT_INCOMPATIBILITY)
    if founder.has_content and founder.internal_graph_availability == \
            V.AVAILABLE and not founder.tenant_id:
        # Private rows readable with nobody accountable for the read.
        reasons.append(V.TENANT_LEAK)
    if market.has_content and not market.provenance_summary and \
            market.contract_state == V.SUPPORTED:
        reasons.append(V.CORRUPTED_PROVENANCE)
    # Order is stable so the content key is stable.
    return tuple(sorted(set(reasons)))


def _readiness(market: MarketDemoSnapshot, founder: FounderDemoSnapshot,
               quarantined: bool, surfaces: dict) -> str:
    """How ready this dossier is to be put in front of somebody.

    DEMO_VERIFIED is unreachable from here by construction, not by policy:
    this function never returns it, and `ASSEMBLER_REACHABLE` excludes it. A
    backend that certified its own appearance would be asserting something it
    has no instrument for (§19, §27).
    """
    if quarantined:
        return V.QUARANTINED
    if not (market.has_content or founder.has_content):
        return V.NOT_STARTED
    if V.HYDRATING in (market.coverage_state, founder.coverage_state):
        return V.HYDRATING
    if not (market.has_content and founder.has_content):
        return V.INTELLIGENCE_PARTIAL
    # A stale side is readable but not current. It is reported rather than
    # suppressed, and it is capped here rather than at the contract, so the
    # window it describes stays comparable (see `HAS_CONTENT_STATES`).
    if not (market.availability in V.CURRENT_STATES
            and founder.availability in V.CURRENT_STATES):
        return V.INTELLIGENCE_PARTIAL
    if all(surfaces.get(name) == "PRESENT" for name in V.PRODUCT_SURFACES):
        return V.DEMO_CANDIDATE
    return V.INTELLIGENCE_READY


def _impact_state(founder: FounderDemoSnapshot, temporal: str,
                  previous: Optional[CompanyDemoDossier]) -> str:
    """Read the founder's impact state, then gate it on comparability.

    Never upgraded, only ever held back. A first observation has no `before`
    and is structurally unmeasurable — which is not NONE, not zero, and not a
    retrieval gap that better sources would close (§18, Batch 7 FINDING 2).
    """
    if previous is None:
        return V.IMPACT_UNMEASURABLE_FIRST_OBSERVATION
    if not founder.has_content:
        return V.IMPACT_UNAVAILABLE
    declared = founder.decision_impact_state
    if declared not in V.IMPACT_STATES:
        return V.IMPACT_UNAVAILABLE
    if declared == V.IMPACT_MEASURED and \
            temporal not in V.IMPACT_COMPARABLE_WINDOWS:
        return V.IMPACT_UNMEASURABLE_WINDOW
    return declared


def _block_view(snapshot, view) -> dict:
    """State each block, with its own availability. Never a bare list."""
    out = {}
    for name, source in view:
        blk = snapshot.block(source)
        out[name] = {"state": blk.state, "ids": list(blk.ids),
                     "count": blk.count, "note": blk.note,
                     "is_measured_zero": blk.is_zero}
    return out


def _effective_cutoff(market: MarketDemoSnapshot,
                      founder: FounderDemoSnapshot) -> str:
    """The OLDER of the two cutoffs. A joint reading sees only as far as its
    blinder side, and taking the newer one would claim sight the pair does
    not jointly have."""
    seen = [c for c in (market.evidence_cutoff if market.has_content else "",
                        founder.evidence_cutoff if founder.has_content else "")
            if c]
    return min(seen) if seen else ""


def assemble(market: MarketDemoSnapshot, founder: FounderDemoSnapshot, *,
             now: str = "", cohort: str = "",
             previous: Optional[CompanyDemoDossier] = None
             ) -> CompanyDemoDossier:
    """Join two snapshots into one materialized view. Deterministic.

    Either side may be unavailable. Neither absence is an error, and neither
    is a finding about the company: a missing market snapshot means the
    market engine did not publish, not that the market is quiet.
    """
    temporal = temporal_compatibility(market, founder)
    population = population_compatibility(market, founder)
    reasons = _quarantine(market, founder, temporal, population)
    quarantined = bool(reasons)

    surfaces = {name: founder.product_surfaces.get(name, V.UNMEASURED)
                for name in V.PRODUCT_SURFACES}
    readiness = _readiness(market, founder, quarantined, surfaces)
    impact = _impact_state(founder, temporal, previous)

    if market.has_content and founder.has_content:
        crossing = CROSSING_BOTH
    elif founder.has_content:
        crossing = CROSSING_FOUNDER_ONLY
    elif market.has_content:
        crossing = CROSSING_MARKET_ONLY
    else:
        crossing = CROSSING_NEITHER

    company_id = founder.company_id or market.company_id
    name = founder.canonical_name or market.canonical_name

    market_block = {
        "availability": market.availability,
        "reason": market.reason,
        "contract_state": market.contract_state,
        "coverage_state": market.coverage_state,
        "population": market.market_population,
        "source_health": market.source_health_summary,
        "evidence_summary": market.evidence_summary,
        # NEVER a source count standing in for an independence measurement.
        # Three sites carrying one press release are one account (§26).
        "evidence_independence_state": market.evidence_independence_state,
        "learning": market.learning_summary,
        "provenance": market.provenance_summary,
        "blocks": _block_view(market, _MARKET_VIEW),
    }
    founder_block = {
        "availability": founder.availability,
        "reason": founder.reason,
        "contract_state": founder.contract_state,
        "coverage_state": founder.coverage_state,
        "population": founder.data_population,
        "tenant_state": founder.tenant_state,
        "ceo_answer_coverage": founder.ceo_answer_coverage,
        "recommendation_ref": founder.recommendation_ref,
        "recommendation_standing": founder.recommendation_standing,
        "what_changed_ref": founder.what_changed_ref,
        "what_changed_your_mind_ref": founder.what_changed_your_mind_ref,
        "internal_impact_state": founder.internal_impact_state,
        "internal_graph_availability": founder.internal_graph_availability,
        "evidence_independence_state": founder.evidence_independence_state,
        "learning": founder.learning_summary,
        "provenance": founder.provenance_summary,
        "blocks": _block_view(founder, _FOUNDER_VIEW),
    }
    product_block = {
        "surfaces": surfaces,
        "hydration_state": readiness,
        # A backend has no instrument for either of these, so both are
        # permanently UNMEASURED here. `VISUAL_PASS` is not a value this
        # package defines at all (§27).
        "visual_verification_state": V.UNMEASURED,
        "accessibility_verification_state": V.UNMEASURED,
        "provenance_readiness": (
            V.AVAILABLE if (market.provenance_summary
                            or founder.provenance_summary) else V.UNAVAILABLE),
    }
    # A list, not a tuple: this survives a JSON round trip unchanged, and a
    # reloaded dossier that differs from the live one only by container type
    # fails an equality check for a reason that has nothing to do with the
    # company.
    absent = sorted(
        name for name, blk in
        list(market_block["blocks"].items()) + list(
            founder_block["blocks"].items())
        if blk["state"] in REF_NOT_A_ZERO)
    quality_block = {
        # MISSINGNESS IS NAMED, not counted. A count would let a reader infer
        # "mostly complete" from a small number without knowing which blocks
        # are gone, and the missing block is usually the interesting one.
        "absent_blocks": absent,
        "unknown_fields": sorted(set(market.unknown_fields)
                                 | set(founder.unknown_fields)),
        "missing_contract_fields": sorted(set(market.missing_fields)
                                          | set(founder.missing_fields)),
        "quarantined": quarantined,
        "quarantine_reasons": list(reasons),
        "known_defects": [],
    }

    dossier = CompanyDemoDossier(
        company_id=company_id, canonical_name=name,
        domain=founder.domain, ticker=founder.ticker,
        cohort=cohort or V.FIELD_UNAVAILABLE,
        coverage_class=(founder.coverage_state if founder.has_content
                        else market.coverage_state),
        generated_at=now,
        market_snapshot_id=market.snapshot_id,
        founder_snapshot_id=founder.snapshot_id,
        market_runtime_sha=market.runtime_sha,
        founder_runtime_sha=founder.runtime_sha,
        market_known_at=market.known_at, founder_known_at=founder.known_at,
        effective_evidence_cutoff=_effective_cutoff(market, founder),
        market_block=market_block, founder_block=founder_block,
        product_block=product_block, quality_block=quality_block,
        temporal_compatibility=temporal, population_compatibility=population,
        synthetic_label=("This joins synthetic data and is a product proof, "
                         "not real intelligence about this company."
                         if population in V.MUST_LABEL_SYNTHETIC else ""),
        decision_impact_state=impact, readiness=readiness,
        quarantined=quarantined, quarantine_reasons=reasons,
        crossing_state=crossing)
    # The id is content-addressed, so it can only be stamped once every other
    # field is final — hence the second construction rather than a field in
    # the first.
    return replace(dossier,
                   dossier_id=f"{company_id}:{dossier.content_key()[:16]}")

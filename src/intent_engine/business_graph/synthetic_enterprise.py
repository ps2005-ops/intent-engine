"""D-SYN-001 -- a synthetic enterprise that is a BUSINESS, not fixture soup.

WHY A COHERENT WORLD AND NOT RANDOM ROWS
----------------------------------------
The purpose of this world is to make the internal-intelligence path RUNNABLE:
D-IBG-001, F-TS-001 and the Minimum Data Request seam all have live proofs that
say, in effect, "a populated tenant is queried through the real request stack".
Random disconnected rows would satisfy the letter of that and prove nothing,
because every interesting failure in this subsystem is a failure of RELATION --
a metric attributed to the wrong initiative, a segment whose revenue does not
add up, an impact traced through an edge that should not exist.

So the segments' ARR sums to the company's ARR, contracts correspond to the
segments that hold them, and pipeline is bounded by something. `reconcile()`
returns the discrepancies and the suite asserts it is empty, which means the
world cannot drift into incoherence without a test going red.

WHAT MAKES IT VALID: THE NEGATIVES
-----------------------------------
A synthetic world containing only success cases is invalid, and this one is
built around four deliberately different subjects:

    SUBJECT_MOVES_METRICS   declared links AND wired metrics -> an impact with
                            a traceable chain
    SUBJECT_NO_IMPACT       nothing in the business declares it -> a MEASURED
                            negative, the control that proves the positive
                            above is not the only answer the reader can give
    SUBJECT_LINK_NO_METRIC  an assumption depends on it and nothing measures
                            it -> an instrumentation gap, and the natural
                            input to a Minimum Data Request
    SUBJECT_STALE           wired, but the metric was last observed long ago
                            -> present, and not to be read as current

Plus a second tenant holding a near-identical business, because every isolation
test needs the collision to be meaningful: same local ids, same company_id, same
declared subjects, different owner.

DETERMINISM IS THE CONTRACT
---------------------------
Same `seed` and same `version` produce byte-identical rows, so a decision
recorded against world v1/seed 7 can be re-derived a month later. Nothing here
calls `random` without the seed, and no timestamp is taken from the clock:
`generated_at` is derived from the world identity. A fixture whose content
depends on when it ran cannot support a decision record.

LABELLING IS NOT ADVISORY
-------------------------
Every node carries `data_population = SYNTHETIC_ENTERPRISE` and
`synthetic_world_id`. `assert_all_synthetic` refuses a world in which any row
lost the tag, and it is exported so the suite can prove it fires. Section 26 of
the constitution is explicit that these rows may prove capability, persistence,
security and plumbing, and may never prove a real economic result -- so the tag
has to survive persistence, reload and rendering, and there is a break proof for
the day somebody helpfully defaults it.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from intent_engine.business_graph import internal as P
from intent_engine.business_graph.model import BusinessGraph, GraphError
from intent_engine.core.tenant import TenantScope, requires_tenant_scope
from intent_engine.external_intel.internal_impact import (
    EXTERNAL_SUBJECT_KEY,
    POPULATION_KEY,
    SYNTHETIC_ENTERPRISE,
)

CONTRACT = "synthetic_enterprise.v1"
SCHEMA_VERSION = "1"

#: Bumped when the SHAPE of the world changes. Seed varies the numbers; version
#: varies the structure. Two different questions, two different knobs.
WORLD_VERSION = "1"

SCENARIO_ENTERPRISE_SAAS = "enterprise_saas"

#: The four subjects the world is built around. See the module docstring: these
#: are the reader's four answers, and a world that could only produce one of
#: them would make the consumer's tests unfalsifiable.
SUBJECT_MOVES_METRICS = "company:northwind-data"
SUBJECT_NO_IMPACT = "company:helio-robotics"
SUBJECT_LINK_NO_METRIC = "company:vantage-billing"
SUBJECT_STALE = "company:cedar-analytics"

SUBJECTS = (SUBJECT_MOVES_METRICS, SUBJECT_NO_IMPACT,
            SUBJECT_LINK_NO_METRIC, SUBJECT_STALE)

#: Tenant A's canary. Never appears in tenant B's world, so any occurrence of
#: this string in a B-scoped response is a leak by definition rather than by
#: interpretation. F-TS-001's live proof greps for exactly this.
CANARY_FIELD = "unreleased_discount_floor_pct"
CANARY_VALUE = "17.3"

_OBSERVED = "2026-07-01T00:00:00+00:00"
_KNOWN = "2026-07-02T00:00:00+00:00"
#: Deliberately old. "Stale" must be a property of the DATA, not of a flag
#: somebody sets, or the reader is trusting an annotation instead of measuring.
_STALE_OBSERVED = "2025-09-15T00:00:00+00:00"


@dataclass(frozen=True)
class WorldIdentity:
    """Which world this is, so a decision can name the world it was made in."""

    synthetic_world_id: str = ""
    version: str = WORLD_VERSION
    seed: int = 0
    schema_version: str = SCHEMA_VERSION
    scenario_id: str = SCENARIO_ENTERPRISE_SAAS
    generated_at: str = ""

    def as_dict(self) -> dict:
        return {"contract": CONTRACT,
                "synthetic_world_id": self.synthetic_world_id,
                "version": self.version, "seed": self.seed,
                "schema_version": self.schema_version,
                "scenario_id": self.scenario_id,
                "generated_at": self.generated_at,
                "data_population": SYNTHETIC_ENTERPRISE}


def world_identity(*, seed: int, version: str = WORLD_VERSION,
                   scenario_id: str = SCENARIO_ENTERPRISE_SAAS
                   ) -> WorldIdentity:
    """Deterministic identity. `generated_at` is DERIVED, never taken from the
    clock -- a fixture whose content depends on when it ran cannot support a
    decision record that has to be re-derivable later."""
    raw = f"{CONTRACT}|{version}|{SCHEMA_VERSION}|{scenario_id}|{seed}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    # A stable pseudo-instant inside the world's own observation window.
    generated_at = _KNOWN
    return WorldIdentity(synthetic_world_id=f"syn_{digest[:16]}", version=version,
                         seed=seed, scenario_id=scenario_id,
                         generated_at=generated_at)


@dataclass
class SyntheticEnterprise:
    """One tenant's whole internal world, plus the numbers it must reconcile."""

    identity: WorldIdentity = field(default_factory=WorldIdentity)
    nodes: Tuple = ()
    edges: Tuple = ()
    company_arr: int = 0
    segment_arr: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {**self.identity.as_dict(), "nodes": len(self.nodes),
                "edges": len(self.edges), "company_arr": self.company_arr,
                "segment_arr": dict(self.segment_arr)}


def _attrs(identity: WorldIdentity, *, subject: str = "",
           extra: Optional[dict] = None) -> dict:
    """Every node carries its population and its world. Both, always.

    The population tag is what section 26 rests on. The world id is what lets a
    decision record say WHICH synthetic world it was made in, so a re-generated
    world with a different seed cannot be mistaken for the one that was decided
    against.
    """
    out = {POPULATION_KEY: SYNTHETIC_ENTERPRISE,
           "synthetic_world_id": identity.synthetic_world_id,
           "world_version": identity.version}
    if subject:
        out[EXTERNAL_SUBJECT_KEY] = subject
    out.update(extra or {})
    return out


@requires_tenant_scope
def build(*, scope: TenantScope, seed: int = 7,
          company_id: str = "acme-analytics",
          include_canary: bool = False,
          version: str = WORLD_VERSION) -> SyntheticEnterprise:
    """One deterministic enterprise for one tenant.

    `include_canary` puts tenant A's unreleased discount floor into the world.
    It is a parameter rather than always-on so the isolation proof has a tenant
    that demonstrably does NOT contain the string it is hunting for -- otherwise
    "B cannot see the canary" is satisfied by B not having been built yet.
    """
    identity = world_identity(seed=seed, version=version)
    rng = random.Random(f"{identity.synthetic_world_id}|{company_id}")

    nodes: List = []
    edges: List = []

    def node(local_id, kind, label, *, subject="", extra=None,
             sensitivity=P.SENSITIVITY_INTERNAL, observed=_OBSERVED):
        made = P.private_node(
            scope=scope, kind=kind, local_id=local_id, label=label,
            company_id=company_id, source="synthetic_enterprise",
            observed_at=observed, known_at=_KNOWN, sensitivity=sensitivity,
            attrs=_attrs(identity, subject=subject, extra=extra))
        nodes.append(made)
        return made

    def edge(kind, src, dst, *, derived, source="synthetic_enterprise"):
        made = P.private_edge(scope=scope, kind=kind, src_local_id=src,
                              dst_local_id=dst, derived=derived, source=source)
        edges.append(made)
        return made

    # -- the revenue spine, which must add up ------------------------------
    # Segment ARR is chosen first and the company total is DERIVED from it.
    # Deriving the total is what makes `reconcile` a real check: if the total
    # were also chosen, the two would only agree because somebody kept them in
    # step, which is the arrangement that always drifts.
    segments = [
        ("seg-enterprise", "Enterprise", 4_200_000),
        ("seg-midmarket", "Mid-market", 1_650_000),
        ("seg-smb", "SMB", 480_000),
    ]
    company_arr = sum(arr for _, _, arr in segments)
    segment_arr = {sid: arr for sid, _, arr in segments}

    node("co", P.CUSTOMER_SEGMENT, "All customers",
         extra={"arr": company_arr, "is_company_total": True})
    for sid, label, arr in segments:
        node(sid, P.CUSTOMER_SEGMENT, label,
             extra={"arr": arr,
                    "share_of_arr": round(arr / company_arr, 4)})

    # -- products, and who buys them ---------------------------------------
    node("prod-core", P.PRIVATE_PRODUCT, "Core platform",
         extra={"list_price": 48_000})
    node("prod-insights", P.PRIVATE_PRODUCT, "Insights add-on",
         extra={"list_price": 12_000})
    edge(P.SEGMENT_BUYS_PRODUCT, "seg-enterprise", "prod-core", derived=True)
    edge(P.SEGMENT_BUYS_PRODUCT, "seg-enterprise", "prod-insights",
         derived=True)
    edge(P.SEGMENT_BUYS_PRODUCT, "seg-midmarket", "prod-core", derived=True)
    edge(P.SEGMENT_BUYS_PRODUCT, "seg-smb", "prod-core", derived=True)

    # -- contracts, bounded by the segment that holds them -----------------
    # Enterprise ARR / a plausible ACV, so contract count cannot imply a
    # customer base the revenue could not support.
    ent_acv = 210_000
    ent_contracts = max(1, segment_arr["seg-enterprise"] // ent_acv)
    for i in range(ent_contracts):
        discount = 8 + rng.randrange(0, 9)
        node(f"contract-ent-{i}", P.CONTRACT, f"Enterprise contract {i}",
             sensitivity=P.SENSITIVITY_CONFIDENTIAL,
             extra={"acv": ent_acv, "discount_pct": discount,
                    "segment": "seg-enterprise"})
        edge(P.CONTRACT_WITH_SEGMENT, f"contract-ent-{i}", "seg-enterprise",
             derived=True)

    # -- pipeline, explicitly bounded --------------------------------------
    # Coverage is a stated multiple of the segment's ARR rather than an
    # arbitrary number, so "pipeline exceeds impossible bounds" is a thing the
    # world can be CHECKED for instead of a thing a reader has to notice.
    pipeline_value = int(segment_arr["seg-enterprise"] * 0.35)
    node("pipe-ent-q4", P.PIPELINE_OPPORTUNITY, "Q4 enterprise pipeline",
         sensitivity=P.SENSITIVITY_CONFIDENTIAL,
         extra={"value": pipeline_value, "stage": "PROPOSAL",
                "coverage_of_segment_arr": 0.35})
    edge(P.PIPELINE_FOR_PRODUCT, "pipe-ent-q4", "prod-core", derived=False)

    node("channel-direct", P.CHANNEL, "Direct sales",
         extra={"share_of_bookings": 0.82})
    node("cohort-2025h2", P.COHORT, "2025 H2 cohort",
         extra={"logo_retention": 0.91})

    # -- metrics -----------------------------------------------------------
    node("m-ent-arr", P.INTERNAL_METRIC, "Enterprise ARR",
         extra={"value": segment_arr["seg-enterprise"], "unit": "USD",
                "grain": "quarterly"})
    node("m-gross-margin", P.INTERNAL_METRIC, "Gross margin",
         extra={"value": 0.78, "unit": "ratio", "grain": "quarterly"})
    node("m-net-retention", P.INTERNAL_METRIC, "Net revenue retention",
         extra={"value": 1.06, "unit": "ratio", "grain": "quarterly"})
    # STALE BY ITS DATE, not by a flag. A reader that wants to know whether
    # this is current has to look at observed_at, which is the honest test.
    node("m-support-cost", P.INTERNAL_METRIC, "Support cost per account",
         observed=_STALE_OBSERVED,
         extra={"value": 3_400, "unit": "USD", "grain": "quarterly"})

    # -- SUBJECT_MOVES_METRICS: declared link, wired metric -----------------
    node("init-repricing", P.INITIATIVE, "Enterprise repricing",
         subject=SUBJECT_MOVES_METRICS,
         extra={"status": "ACTIVE", "owner": "cro"})
    edge(P.INITIATIVE_AFFECTS_METRIC, "init-repricing", "m-ent-arr",
         derived=False, source="rev-ops")
    edge(P.INITIATIVE_AFFECTS_METRIC, "init-repricing", "m-gross-margin",
         derived=False, source="rev-ops")

    # A decision -> action -> metric chain on the same subject, so the reader's
    # two-hop route is exercised by the world and not only by a unit test.
    node("dec-price-floor", P.PRIVATE_DECISION,
         "Whether to hold the enterprise discount floor",
         subject=SUBJECT_MOVES_METRICS,
         sensitivity=P.SENSITIVITY_RESTRICTED,
         extra=({CANARY_FIELD: CANARY_VALUE} if include_canary else {}))
    node("act-floor-memo", P.PRIVATE_ACTION, "Issue revised floor to sales")
    edge(P.DECISION_AUTHORIZES_ACTION, "dec-price-floor", "act-floor-memo",
         derived=False, source="cro")
    edge(P.ACTION_AFFECTS_METRIC, "act-floor-memo", "m-net-retention",
         derived=False, source="rev-ops")

    # -- SUBJECT_LINK_NO_METRIC: the instrumentation gap --------------------
    node("asm-price-insensitive", P.INTERNAL_ASSUMPTION,
         "Enterprise buyers are price-insensitive below 20% discount",
         subject=SUBJECT_LINK_NO_METRIC,
         extra={"confidence": "MEDIUM", "tested": False})
    node("exp-discount-ab", P.EXPERIMENT, "Discount sensitivity A/B")
    edge(P.EXPERIMENT_TESTS_ASSUMPTION, "exp-discount-ab",
         "asm-price-insensitive", derived=False, source="growth")

    # -- SUBJECT_STALE: wired, but last observed long ago -------------------
    node("init-support-automation", P.INITIATIVE, "Support automation",
         subject=SUBJECT_STALE, observed=_STALE_OBSERVED,
         extra={"status": "PAUSED"})
    edge(P.INITIATIVE_AFFECTS_METRIC, "init-support-automation",
         "m-support-cost", derived=False, source="support")

    # -- an action that produced NO measurable effect -----------------------
    # Required by section 6. Without it the world implies every action moves
    # something, which is the belief this whole system exists to interrogate.
    node("act-webinar", P.PRIVATE_ACTION, "Run partner webinar series")
    node("out-webinar-flat", P.PRIVATE_OUTCOME,
         "No detectable change in enterprise pipeline",
         extra={"effect": "NONE_DETECTED", "measured": True})
    node("dec-webinar", P.PRIVATE_DECISION, "Whether to fund partner marketing")
    edge(P.DECISION_AUTHORIZES_ACTION, "dec-webinar", "act-webinar",
         derived=False, source="cmo")
    edge(P.OUTCOME_RESOLVES_DECISION, "out-webinar-flat", "dec-webinar",
         derived=False, source="cmo")

    # SUBJECT_NO_IMPACT is deliberately absent from every `subject=` above.
    # Its absence IS the fixture: the reader must reach a MEASURED negative by
    # examining rows, not by failing to find any.

    return SyntheticEnterprise(
        identity=identity, nodes=tuple(nodes), edges=tuple(edges),
        company_arr=company_arr, segment_arr=segment_arr)


# =============================================================================
# Coherence, and the guard that proves the labelling held
# =============================================================================
def reconcile(world: SyntheticEnterprise) -> Tuple[str, ...]:
    """Arithmetic discrepancies. Empty tuple is the pass.

    Exposed as a function returning findings rather than asserted at build
    time, so the suite can prove it REPORTS a discrepancy when one exists. A
    guard that has never returned a non-empty result is an untested guard.
    """
    problems = []
    by_id = {n.local_id: n for n in world.nodes}

    total = by_id.get("co")
    if total is None:
        return ("the company total segment is missing",)
    declared = (total.attrs or {}).get("arr")
    summed = sum(world.segment_arr.values())
    if declared != summed:
        problems.append(
            f"company arr {declared} != sum of segment arr {summed}")

    for sid, arr in world.segment_arr.items():
        seg = by_id.get(sid)
        if seg is None:
            problems.append(f"segment {sid} is missing")
        elif (seg.attrs or {}).get("arr") != arr:
            problems.append(f"segment {sid} arr disagrees with the world total")

    # Contracts must not imply more revenue than their segment holds.
    booked = sum((n.attrs or {}).get("acv", 0) for n in world.nodes
                 if n.kind == P.CONTRACT)
    if booked > world.segment_arr.get("seg-enterprise", 0):
        problems.append(
            f"contracts book {booked} against an enterprise segment holding "
            f"{world.segment_arr.get('seg-enterprise')}")

    # Pipeline must be bounded and must say what it is a multiple of.
    for n in world.nodes:
        if n.kind != P.PIPELINE_OPPORTUNITY:
            continue
        attrs = n.attrs or {}
        coverage = attrs.get("coverage_of_segment_arr")
        if coverage is None:
            problems.append(f"pipeline {n.local_id} states no coverage basis")
        elif attrs.get("value", 0) > world.company_arr:
            problems.append(
                f"pipeline {n.local_id} exceeds total company ARR without "
                f"explanation")
    return tuple(problems)


def assert_all_synthetic(world: SyntheticEnterprise) -> Tuple[str, ...]:
    """Any node that lost its SYNTHETIC_ENTERPRISE tag. Empty tuple is the pass.

    Section 26 forbids a synthetic row from ever being read as REAL, and the
    way that rule actually breaks is not a malicious relabelling -- it is a
    helpful default somewhere downstream. So this is checkable, tested for its
    ability to report a violation, and has a break proof.
    """
    return tuple(sorted(
        n.local_id for n in world.nodes
        if (n.attrs or {}).get(POPULATION_KEY) != SYNTHETIC_ENTERPRISE))


@requires_tenant_scope
def install(graph: BusinessGraph, world: SyntheticEnterprise, *,
            scope: TenantScope) -> BusinessGraph:
    """Put the world into a graph through the ordinary private doors."""
    for node in world.nodes:
        graph.add_private_node(node, scope=scope)
    for edge in world.edges:
        graph.add_private_edge(edge, scope=scope)
    return graph

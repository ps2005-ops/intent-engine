"""The states a cross-system read model may take, and nothing else.

WHY THIS PACKAGE IMPORTS NOTHING
---------------------------------
`intent_engine.demo_dossier` is the neutral side of the Market/Founder seam.
It is joined to by two packages that must never see each other, so it may not
import either of them — not `intent_engine.market`, and not the founder
intelligence packages. A structural guard tokenizes this package's source and
fails on any such import; see `tests/test_the_dossier_seam_stays_neutral.py`.

That has a consequence this module has to own honestly: the population and
coverage vocabularies below are RESTATED here, not imported. This is the same
discipline `strategic_contract.ALLOWED` already runs on — the two sides share
a schema, never a module. Restating is only safe when drift is detectable, so
a test compares this module's sets against the founder-side canonical sets and
fails the moment one gains a term the other has not. Restating without that
test would be copying.

WHY ABSENCE HAS SO MANY NAMES HERE
-----------------------------------
Every `*_UNAVAILABLE` state in this module exists because collapsing it into
zero has already cost this program a release. A snapshot that never arrived,
a producer too old to send a field, a block nobody attempted, and a genuinely
empty result are four different readings, and a surface that renders them
identically is lying three times out of four.
"""
from __future__ import annotations

CONTRACT = "demo_dossier_vocabulary.v1"

# --- availability, §6 ------------------------------------------------------
# The reading for one snapshot, or for one block inside a dossier.
AVAILABLE = "AVAILABLE"
#: The producer never sent this. NOT "the producer sent nothing interesting".
UNAVAILABLE = "UNAVAILABLE"
#: It arrived, it validated, and it describes a world old enough that acting
#: on it is acting on a company that has since moved.
STALE = "STALE"
#: It arrived and is partially readable — some blocks refused, the rest kept.
DEGRADED = "DEGRADED"
#: It arrived and this side refused it. Distinct from UNAVAILABLE precisely
#: because Batch 7 FINDING 1 records 22 dossiers where the two looked alike.
REFUSED = "REFUSED"
#: Its contract version is one this side cannot read at all.
INCOMPATIBLE = "INCOMPATIBLE"

AVAILABILITY_STATES = (AVAILABLE, UNAVAILABLE, STALE, DEGRADED, REFUSED,
                       INCOMPATIBLE)

#: States that mean "this side has no content to show". A surface asserts
#: against this set rather than testing `!= AVAILABLE`, so DEGRADED and STALE
#: (both of which do carry content) are never rendered as absences.
NO_CONTENT_STATES = frozenset({UNAVAILABLE, REFUSED, INCOMPATIBLE})

#: The complement, stated rather than derived: these carry something to read.
#:
#: STALE IS HERE ON PURPOSE, and it is the one entry worth arguing about.
#: `strategic_contract` refuses to RENDER a stale dossier, and it is right to:
#: on a page, an old reading is indistinguishable from a current one. A read
#: model is not a page. It states staleness in a field, so suppressing the
#: content buys nothing and costs something specific — with STALE treated as
#: absent, a market snapshot more than three weeks old had no window to
#: compare, and `DIFFERENT_WINDOW` became almost unreachable. An axis that
#: cannot be reached is not a guard, it is decoration that reports green.
#: Readiness is where staleness is paid for: a stale side caps the dossier at
#: INTELLIGENCE_PARTIAL and can never reach a demo state.
HAS_CONTENT_STATES = frozenset({AVAILABLE, DEGRADED, STALE})

#: Sides whose content is trustworthy enough to build a demo on. Separate
#: from HAS_CONTENT_STATES because "readable" and "current" are different
#: questions and this program has already paid for conflating them once.
CURRENT_STATES = frozenset({AVAILABLE, DEGRADED})

#: An absence is never a measured zero. Mirrors `internal_impact.NOT_A_NEGATIVE`
#: in intent and is asserted against by the missing-vs-zero tests (§21).
NOT_A_MEASURED_ZERO = frozenset({UNAVAILABLE, REFUSED, INCOMPATIBLE, STALE})


# --- contract compatibility, §11 -------------------------------------------
SUPPORTED = "SUPPORTED"
#: An older contract this side still reads. Its missing fields are
#: FIELD_UNAVAILABLE, never zero — that distinction is the whole point.
OLDER_SUPPORTED = "OLDER_SUPPORTED"
CONTRACT_INCOMPATIBLE = "INCOMPATIBLE"

CONTRACT_STATES = (SUPPORTED, OLDER_SUPPORTED, CONTRACT_INCOMPATIBLE)

#: What a field reads when the producer's contract predates it. Never 0,
#: never "", never an empty list.
FIELD_UNAVAILABLE = "FIELD_UNAVAILABLE"


# --- temporal compatibility, §8 --------------------------------------------
#: Both sides describe the same evidence window.
SAME_WINDOW = "SAME_WINDOW"
#: Different windows, but close enough that a bounded joint reading is honest.
COMPATIBLE_BOUNDED_WINDOW = "COMPATIBLE_BOUNDED_WINDOW"
#: Far enough apart that a before/after claim across them would be invented.
DIFFERENT_WINDOW = "DIFFERENT_WINDOW"
#: At least one side did not state its window. Not the same as agreeing.
WINDOW_UNKNOWN = "WINDOW_UNKNOWN"

TEMPORAL_STATES = (SAME_WINDOW, COMPATIBLE_BOUNDED_WINDOW, DIFFERENT_WINDOW,
                   WINDOW_UNKNOWN)

#: Windows a cross-system impact / before-after / "changed because of market"
#: claim may be made across. Stated as an allowlist, so a state added later is
#: excluded until somebody decides it belongs.
IMPACT_COMPARABLE_WINDOWS = frozenset({SAME_WINDOW, COMPATIBLE_BOUNDED_WINDOW})

#: Days between the two sides' evidence cutoffs that still counts as bounded.
#: Matches `strategic_contract.MAX_AGE_DAYS`: past three weeks the market
#: dossier describes a company that has since acted, and the same threshold
#: that makes a dossier too old to render makes two of them too far apart to
#: join into a claim.
BOUNDED_WINDOW_DAYS = 21


# --- population compatibility, §9 ------------------------------------------
# RESTATED from `external_intel.internal_impact`, not imported (see module
# docstring). `test_the_dossier_seam_stays_neutral` pins these against the
# canonical sets.
SYNTHETIC_ENTERPRISE = "SYNTHETIC_ENTERPRISE"
REAL_ENTERPRISE = "REAL_ENTERPRISE"
POPULATIONS = frozenset({SYNTHETIC_ENTERPRISE, REAL_ENTERPRISE})

#: Market's own population axis. A market snapshot is derived from public
#: evidence about a real company, or from a fixture. It is NOT the same axis
#: as the founder's internal-data population, which is why joining them needs
#: an explicit table rather than an equality check.
REAL_MARKET = "REAL_MARKET"
SYNTHETIC_MARKET = "SYNTHETIC_MARKET"
MARKET_POPULATIONS = frozenset({REAL_MARKET, SYNTHETIC_MARKET})

#: The join's verdict.
POPULATION_COHERENT_REAL = "POPULATION_COHERENT_REAL"
POPULATION_COHERENT_SYNTHETIC = "POPULATION_COHERENT_SYNTHETIC"
#: Real public market evidence joined to synthetic internal data. Permitted,
#: but ONLY under a label that forbids presenting it as real internal-company
#: intelligence. This is the combination a demo actually wants, and it is
#: also the one most likely to be shown to an investor as if it were real.
POPULATION_SYNTHETIC_PRODUCT_PROOF = "SYNTHETIC_PRODUCT_PROOF"
#: Synthetic market evidence joined to real internal data. Never permitted:
#: it invites a real business decision from invented external facts.
POPULATION_REFUSED = "POPULATION_REFUSED"
POPULATION_UNKNOWN = "POPULATION_UNKNOWN"

POPULATION_JOIN_STATES = (
    POPULATION_COHERENT_REAL, POPULATION_COHERENT_SYNTHETIC,
    POPULATION_SYNTHETIC_PRODUCT_PROOF, POPULATION_REFUSED,
    POPULATION_UNKNOWN)

#: THE ALLOWED COMBINATIONS, stated as a table rather than as branches, so
#: the set of what is permitted can be read in one place and asserted against.
#: A pair absent from this table is POPULATION_UNKNOWN and quarantines.
POPULATION_JOIN = {
    (REAL_MARKET, REAL_ENTERPRISE): POPULATION_COHERENT_REAL,
    (SYNTHETIC_MARKET, SYNTHETIC_ENTERPRISE): POPULATION_COHERENT_SYNTHETIC,
    (REAL_MARKET, SYNTHETIC_ENTERPRISE): POPULATION_SYNTHETIC_PRODUCT_PROOF,
    (SYNTHETIC_MARKET, REAL_ENTERPRISE): POPULATION_REFUSED,
}

#: Joins that must carry a visible synthetic label wherever they are shown.
MUST_LABEL_SYNTHETIC = frozenset({POPULATION_COHERENT_SYNTHETIC,
                                  POPULATION_SYNTHETIC_PRODUCT_PROOF})


# --- readiness, §19 --------------------------------------------------------
# Maps onto `coverage_state.COVERAGE_STATES` rather than competing with it:
# coverage describes what is known about the COMPANY, readiness describes
# whether the DOSSIER can be put in front of somebody.
NOT_STARTED = "NOT_STARTED"
HYDRATING = "HYDRATING"
INTELLIGENCE_PARTIAL = "INTELLIGENCE_PARTIAL"
INTELLIGENCE_READY = "INTELLIGENCE_READY"
UI_PARTIAL = "UI_PARTIAL"
DEMO_CANDIDATE = "DEMO_CANDIDATE"
#: Reachable ONLY from an exercised UI proof. No backend test may set it, and
#: `assemble()` structurally cannot: a dossier cannot certify its own
#: appearance, and a backend that says it looks right has not looked.
DEMO_VERIFIED = "DEMO_VERIFIED"
DEMO_REGRESSED = "DEMO_REGRESSED"
QUARANTINED = "QUARANTINED"

READINESS_STATES = (NOT_STARTED, HYDRATING, INTELLIGENCE_PARTIAL,
                    INTELLIGENCE_READY, UI_PARTIAL, DEMO_CANDIDATE,
                    DEMO_VERIFIED, DEMO_REGRESSED, QUARANTINED)

#: States the neutral assembler is permitted to reach. DEMO_VERIFIED and
#: DEMO_REGRESSED are absent on purpose — both are claims about a rendered
#: surface, and this package never renders one.
ASSEMBLER_REACHABLE = frozenset({NOT_STARTED, HYDRATING, INTELLIGENCE_PARTIAL,
                                 INTELLIGENCE_READY, DEMO_CANDIDATE,
                                 QUARANTINED})

#: Readiness states that permit showing the dossier to somebody outside the
#: team. Quarantine blocks both, by construction rather than by convention.
DEMO_STATES = frozenset({DEMO_CANDIDATE, DEMO_VERIFIED})


# --- quarantine, §20 -------------------------------------------------------
WRONG_COMPANY_EVIDENCE = "WRONG_COMPANY_EVIDENCE"
TENANT_LEAK = "TENANT_LEAK"
TEMPORAL_LEAK = "TEMPORAL_LEAK"
FABRICATED_NUMERIC_CLAIM = "FABRICATED_NUMERIC_CLAIM"
UNSUPPORTED_CERTAINTY = "UNSUPPORTED_CERTAINTY"
CORRUPTED_PROVENANCE = "CORRUPTED_PROVENANCE"
STANDING_CONFLICT = "STANDING_CONFLICT"
REAL_SYNTHETIC_POPULATION_MIX = "REAL_SYNTHETIC_POPULATION_MIX"
CONTRACT_INCOMPATIBILITY = "CONTRACT_INCOMPATIBILITY"

QUARANTINE_REASONS = (WRONG_COMPANY_EVIDENCE, TENANT_LEAK, TEMPORAL_LEAK,
                      FABRICATED_NUMERIC_CLAIM, UNSUPPORTED_CERTAINTY,
                      CORRUPTED_PROVENANCE, STANDING_CONFLICT,
                      REAL_SYNTHETIC_POPULATION_MIX, CONTRACT_INCOMPATIBILITY)


# --- evidence independence, §26 --------------------------------------------
#: Independence is NOT built in this vertical. The dossier carries the state
#: and refuses the one substitution that would make it look built: a raw
#: source count standing in for an independent-source count. Three sites
#: carrying one press release are one account, and this program has already
#: shipped the version that called them three.
INDEPENDENCE_AVAILABLE = "AVAILABLE"
INDEPENDENCE_UNAVAILABLE = "UNAVAILABLE"
INDEPENDENCE_STATES = (INDEPENDENCE_AVAILABLE, INDEPENDENCE_UNAVAILABLE)


# --- decision impact, §18 --------------------------------------------------
#: A first dossier has no `before`, so impact is structurally unmeasurable.
#: This is not NONE, and not a retrieval gap: the second run is the fix.
IMPACT_UNMEASURABLE_FIRST_OBSERVATION = "IMPACT_UNMEASURABLE_FIRST_OBSERVATION"
#: A pair exists but its windows are not comparable.
IMPACT_UNMEASURABLE_WINDOW = "IMPACT_UNMEASURABLE_INCOMPARABLE_WINDOW"
#: The founder side did not send an impact reading at all.
IMPACT_UNAVAILABLE = "IMPACT_UNAVAILABLE"
IMPACT_MEASURED = "IMPACT_MEASURED"

IMPACT_STATES = (IMPACT_UNMEASURABLE_FIRST_OBSERVATION,
                 IMPACT_UNMEASURABLE_WINDOW, IMPACT_UNAVAILABLE,
                 IMPACT_MEASURED)

#: None of these mean "the analysis changed nothing".
IMPACT_NOT_A_NEGATIVE = frozenset({IMPACT_UNMEASURABLE_FIRST_OBSERVATION,
                                   IMPACT_UNMEASURABLE_WINDOW,
                                   IMPACT_UNAVAILABLE})


# --- diff, §17 -------------------------------------------------------------
FIRST_OBSERVATION = "FIRST_OBSERVATION"
NO_CHANGE = "NO_CHANGE"
CHANGED = "CHANGED"
DIFF_STATES = (FIRST_OBSERVATION, NO_CHANGE, CHANGED)


# --- UI readiness, §27 -----------------------------------------------------
#: Nothing has looked at the rendered surface. The ONLY value a backend may
#: write. `VISUAL_PASS` is not defined in this module at all, so a backend
#: test cannot set it by name even by accident.
UNMEASURED = "UNMEASURED"
SURFACE_STATES = (UNMEASURED, "PRESENT", "ABSENT")

PRODUCT_SURFACES = ("analysis_surface", "provenance_surface", "thesis_surface",
                    "causal_surface", "replay_surface", "adversary_surface",
                    "decision_surface", "mdr_mve_surface")


# --- causal resolution states -------------------------------------------------
#
# DECLARED TWICE ON PURPOSE, and this is the second copy. The market engine
# owns `causal_question.STATES`; this seam may not import the market package
# (see the ADR and the structural guard), so the two ends necessarily restate
# it. Only the ESTIMATE states are listed, because that is the short list and
# the safe direction: a state this side does not recognise is NOT read as an
# estimate, so a new refusal added upstream degrades to "no effect was
# estimated" rather than to a fabricated effect.

#: The only states in which an effect was actually estimated.
CAUSAL_ESTIMATE_STATES = frozenset({"ESTIMATE_BOUNDED", "ESTIMATE_SUPPORTED"})


def is_causal_estimate(state: str) -> bool:
    return str(state) in CAUSAL_ESTIMATE_STATES


def is_causal_refusal(state: str) -> bool:
    """Anything that is not an estimate. The engine ran and declined.

    Never read as "no effect": `NOT_AN_ESTIMATE` upstream exists to prevent
    exactly that reading, and this is its counterpart on the consuming side.
    """
    return not is_causal_estimate(state)

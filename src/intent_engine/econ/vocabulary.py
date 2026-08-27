"""The words the two products must agree on, and nothing else.

WHY A VOCABULARY MODULE
-----------------------
Every other module in this package restates one of these constants, and the
one thing that must not happen is two spellings of the same idea. The market
engine and the founder engine already each have a private vocabulary for
"how sure are we" and "where did this come from"; a shared substrate that
introduced a third would have made the drift worse, not better.

Nothing here imports anything. That is enforceable and enforced: see
`tests/test_econ_core_is_neutral.py`.
"""
from __future__ import annotations

CONTRACT = "economic_core.v1"

# --- visibility -------------------------------------------------------------
# The privacy boundary (Section 31). It is a property of the EVIDENCE, not of
# the reader, because the reader is whoever happens to call. A tenant's board
# memo is private wherever it is standing.
PUBLIC = "PUBLIC"
TENANT_PRIVATE = "TENANT_PRIVATE"
VISIBILITIES = (PUBLIC, TENANT_PRIVATE)

# --- standing: how a number came to be known --------------------------------
# Deliberately the same four words `market.macro_state` already uses, so the
# bridge is a rename of nothing.
OBSERVED = "OBSERVED"          # a named publisher published this figure
INFERRED = "INFERRED"          # derived from observed figures by a stated rule
HYPOTHESIZED = "HYPOTHESIZED"  # asserted by a source, not measured by one
UNKNOWN = "UNKNOWN"            # nothing in evidence measures this
STANDINGS = (OBSERVED, INFERRED, HYPOTHESIZED, UNKNOWN)

#: Only these two may anchor a claim. HYPOTHESIZED and UNKNOWN may appear in a
#: state and may never be the thing a decision rests on.
ANCHORING = frozenset({OBSERVED, INFERRED})

# --- direction --------------------------------------------------------------
UP, DOWN, FLAT = "UP", "DOWN", "FLAT"
#: No earlier observation of this quantity, so no change is computable.
#:
#: NOT the same as FLAT, and the distinction is the one this codebase keeps
#: having to relearn: "this did not move" and "we cannot tell whether it
#: moved" support completely different decisions, and collapsing them makes
#: an unmeasured economy read as a calm one.
NO_PRIOR = "NO_PRIOR"
DIRECTIONS = (UP, DOWN, FLAT, NO_PRIOR)

# --- node classes (Section 2) ----------------------------------------------
MACRO = "MACRO"
MARKET_STRUCTURE = "MARKET_STRUCTURE"
COMPANY = "COMPANY"
STRATEGIC = "STRATEGIC"
#: What a population was OBSERVED DOING or SAYING (Section 4). Deliberately a
#: fifth class rather than a subset of MACRO: a behavioural observation is a
#: measurement of people, and the moment it is filed as macro the engine loses
#: the ability to ask whether people told it something the aggregates had not.
BEHAVIORAL = "BEHAVIORAL"
NODE_CLASSES = (MACRO, MARKET_STRUCTURE, COMPANY, STRATEGIC, BEHAVIORAL)

#: The measurable kinds inside each class. This is a VOCABULARY, not a
#: schema: a node whose kind is not here is refused, because an unrecognised
#: kind is how "revenue" and "revenues" become two economic quantities that
#: never corroborate each other.
NODE_KINDS = {
    MACRO: (
        "policy_rate", "sofr", "ois", "treasury_2y", "treasury_5y",
        "treasury_10y", "treasury_30y", "curve_slope", "curve_butterfly",
        "real_yield", "inflation", "inflation_expectation", "labour",
        "wages", "credit_spread_ig", "credit_spread_hy", "liquidity",
        "financial_conditions", "bank_stress", "fx_dxy", "fx_cross",
        "currency_basis", "commodity_oil", "commodity_gas",
        "commodity_copper", "commodity_gold", "commodity_ags",
        "commodity_curve", "growth", "industrial_production", "housing",
        "fiscal", "trade", "consumer_demand", "business_investment",
    ),
    MARKET_STRUCTURE: (
        "vix", "vol_term_structure", "skew", "realised_vol",
        "dealer_gamma_proxy", "breadth", "positioning", "market_liquidity",
        "funding_stress", "sector_return", "factor_return",
        "small_large_ratio", "toxicity_proxy",
    ),
    COMPANY: (
        "price", "volume", "revenue", "margin", "backlog", "bookings",
        "rpo", "customer_count", "arpu", "inventory", "utilisation",
        "capex", "hiring", "financing", "pricing", "guidance",
        "segment_mix", "demand_language", "supply_constraint",
        "customer_concentration", "regional_weakness", "wage_pressure",
    ),
    STRATEGIC: (
        "competitor_move", "product_launch", "substitution",
        "capacity_expansion", "acquisition", "vertical_integration",
        "regulatory_change",
    ),
    #: Section 4's collective-human family. Every one of these is a PUBLIC
    #: aggregate of what a population did or reported -- never an inference
    #: about a named person, and never a private record.
    BEHAVIORAL: (
        "survey_confidence", "survey_expectation", "survey_trust",
        "search_interest", "spending_level", "spending_mix",
        "discretionary_intent", "big_ticket_intent", "trade_down",
        "saving_rate", "borrowing_rate", "delinquency", "credit_application",
        "revolving_balance", "job_switching", "quits", "labour_participation",
        "business_formation", "household_expectation", "trust_index",
        # Added once real instruments for them were found and called. Each is
        # a measurement of what households are EXPERIENCING or DOING, not an
        # inference about how they feel about it -- the latter is a construct
        # and lives in COLLECTIVE_DIMENSIONS.
        "debt_service_burden", "underemployment", "employment_ratio",
        "retail_speculation", "risk_taking_proxy", "defensive_spending",
        "public_language", "public_attention", "information_diffusion",
    ),
}

#: Flat set, for the membership test.
ALL_KINDS = frozenset(k for kinds in NODE_KINDS.values() for k in kinds)

# --- freshness --------------------------------------------------------------
CURRENT = "CURRENT"
AGEING = "AGEING"
STALE = "STALE"
FRESHNESS = (CURRENT, AGEING, STALE)


class EconError(ValueError):
    """Any refusal by the canonical core. Callers catch this, not ValueError."""


class PrivacyViolation(EconError):
    """Tenant-private evidence reached a public surface (Section 31)."""


class LineageViolation(EconError):
    """A derived signal was offered as independent support for its own input."""


def require(condition: bool, message: str) -> None:
    """A refusal that reads as a sentence rather than an assertion trace."""
    if not condition:
        raise EconError(message)


# =============================================================================
# COLLECTIVE HUMAN STATE (Sections 5-8, 29, 42)
# =============================================================================
# Everything below names a LATENT ESTIMATE ABOUT PEOPLE. It is kept in this
# module for the same reason the rest is: two spellings of one construct is
# how "risk appetite" and "risk_appetite" become two variables that never
# corroborate each other, and a research programme whose whole output is a
# comparison of two models cannot afford that.

CONTRACT_COLLECTIVE = "collective_state.v1"

# --- the scales (Section 6) -------------------------------------------------
# "The market is fearful" is not a state, because it names no population.
# Every estimate must sit at exactly one of these scales, and the scale is
# what makes "fear among first-time homebuyers" a different object from
# "fear among bank risk officers" rather than a rewording of it.
INDIVIDUAL = "INDIVIDUAL"          # Personal AI only; refused in public state
HOUSEHOLD = "HOUSEHOLD"
DEMOGRAPHIC_COHORT = "DEMOGRAPHIC_COHORT"
CONSUMER_COHORT = "CONSUMER_COHORT"
WORKER_COHORT = "WORKER_COHORT"
INVESTOR_COHORT = "INVESTOR_COHORT"
EXECUTIVE_COHORT = "EXECUTIVE_COHORT"
INDUSTRY = "INDUSTRY"
POPULATION = "POPULATION"
SCALES = (INDIVIDUAL, HOUSEHOLD, DEMOGRAPHIC_COHORT, CONSUMER_COHORT,
          WORKER_COHORT, INVESTOR_COHORT, EXECUTIVE_COHORT, INDUSTRY,
          POPULATION)

#: The scale a public world model may never hold. Section 52: an individual
#: state is a Personal-AI object, and the firewall is that this package
#: refuses to build one rather than trusting a caller not to ask.
PRIVATE_SCALES = frozenset({INDIVIDUAL})

# --- the dimensions (Section 5) ---------------------------------------------
# These are CANDIDATE constructs, not truths. Section 7: a framework may
# propose a dimension; only Section 18's incremental-value test may keep one.
COLLECTIVE_DIMENSIONS = (
    "financial_anxiety", "perceived_control", "institutional_trust",
    "interpersonal_trust", "hope", "anger", "stress", "agency", "belonging",
    "risk_appetite", "time_horizon", "certainty", "perceived_security",
    "perceived_fairness", "willingness_to_experiment", "future_orientation",
)

#: Section 3's wall, as data. A collective dimension may never be spelled with
#: an economic quantity's name, nor an economic quantity with a dimension's:
#: "credit stress" is not "fear", and "market volatility" is not "anxiety".
#: `tests/test_econ_collective_state.py` asserts the two sets are disjoint.
def collective_dimension_collisions() -> frozenset:
    """Names claimed by both the economic and the collective vocabulary."""
    return frozenset(COLLECTIVE_DIMENSIONS) & ALL_KINDS


# --- market participants are NOT people (Section 29) ------------------------
# A dealer's gamma is not a mood. Kept as a separate tuple so that a caller
# asking for a collective state cannot be handed a positioning reading.
#: EXACTLY the classes `levelk.PARTICIPANTS` models. A second, prettier list
#: here would be two spellings of one participant, which is how a reflexive
#: loop goes undetected: the flow engine reacts for `corporate_buybacks` and
#: a report keyed on `corporate_buyback` finds nothing and says so calmly.
#: `test_a_market_participant_is_not_a_population` asserts they agree.
PARTICIPANT_CLASSES = (
    "corporate_buybacks", "cta_trend_following", "discretionary_macro",
    "long_only", "market_makers", "options_dealers", "passive_index",
    "retail", "risk_parity", "volatility_control",
)

# --- promotion states (Section 42) ------------------------------------------
CANDIDATE = "CANDIDATE"
OBSERVED_C = "OBSERVED"      # a proxy exists and has been measured
TESTED = "TESTED"            # it has faced Section 18's comparison once
REPLICATED = "REPLICATED"    # and again, out of sample
PROMOTED = "PROMOTED"
WEAKENED = "WEAKENED"
RETIRED = "RETIRED"
COLLECTIVE_STATES = (CANDIDATE, OBSERVED_C, TESTED, REPLICATED, PROMOTED,
                     WEAKENED, RETIRED)

# --- what a new observation did to a posterior (Section 10) -----------------
# "Arrival != learning" is the whole point of this tuple. A duplicate is
# named, not silently counted, because counting it is how a cycle reports
# 554 units of learning for a cycle that learned three things.
CONFIRMATION = "CONFIRMATION"
STRENGTHENING = "STRENGTHENING"
WEAKENING = "WEAKENING"
CONTRADICTION = "CONTRADICTION"
NO_INFORMATION = "NO_INFORMATION"
DUPLICATE_EVIDENCE = "DUPLICATE_EVIDENCE"
EVIDENCE_EFFECTS = (CONFIRMATION, STRENGTHENING, WEAKENING, CONTRADICTION,
                    NO_INFORMATION, DUPLICATE_EVIDENCE)

#: Effects that moved the posterior. The others arrived.
INFORMATIVE_EFFECTS = frozenset({CONFIRMATION, STRENGTHENING, WEAKENING,
                                 CONTRADICTION})


class CollectiveStateViolation(EconError):
    """A collective-state estimate broke one of Section 5's requirements."""


class UnsupportedInference(EconError):
    """A psychological claim was made that the evidence does not license."""

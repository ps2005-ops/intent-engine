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
NODE_CLASSES = (MACRO, MARKET_STRUCTURE, COMPANY, STRATEGIC)

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

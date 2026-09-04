"""The seed structural causal graph: the transmission chains, written out.

WHY A SEED AT ALL
-----------------
An empty causal graph learns nothing, because there is no candidate for
evidence to bear on. These are the transmission chains an economist would
write on a whiteboard, entered at the level the evidence actually supports —
which for almost all of them is LEVEL 1, a lagged relationship, and for none
of them is LEVEL 5.

EVERY EDGE ENTERS AT THE LEVEL ITS EVIDENCE SUPPORTS, NOT AT THE LEVEL ITS
STORY SUPPORTS
--------------------------------------------------------------------------
This is the whole discipline. "Real yields compress high-growth multiples"
is a textbook mechanism with a clean derivation, and that derivation is a
STRUCTURAL RESTRICTION — a discount-rate identity — which is genuinely
LEVEL 3. "The dollar affects multinational margins" is an accounting identity
on the translation line and is also LEVEL 3. But "funding conditions transmit
to small-cap valuation" is, in this engine's evidence, a lagged co-movement:
LEVEL 1, and it says so, and `statement()` therefore refuses to use the word
"causes" about it.

Reading the list below, the LEVEL column is the honest map of what this
system actually knows.

LAGS ARE PART OF THE CLAIM
--------------------------
Every edge carries one. A chain with no lags cannot be wrong at any
particular moment, and `shock.propagate` sums them so a third-order effect
arrives when the chain says it should rather than immediately.
"""
from __future__ import annotations

from typing import List

from .causal import (
    DOWN, L1_LAGGED, L2_INFORMATION, L3_STRUCTURAL, StructuralCausalGraph,
    UP, edge,
)

CONTRACT = "econ_seed.v1"

#: A shared window for edges established on this engine's own price history.
_WINDOW = ("2024-01-01", "2026-08-01")


def _e(cause, effect, sign, mechanism, level, evidence, falsifier, lag,
       n=0, confidence=0.5, competing=""):
    return edge(cause=cause, effect=effect, sign=sign, mechanism=mechanism,
                evidence_level=level, evidence=evidence, falsifier=falsifier,
                lag_days=lag, sample_start=_WINDOW[0], sample_end=_WINDOW[1],
                sample_n=n, confidence=confidence,
                competing_explanation=competing)


def seed_edges() -> List:
    """The four chains Section 3 names, plus what links them."""
    return [
        # --- funding chain --------------------------------------------------
        _e("sofr", "funding_stress", UP,
           "an overnight secured rate rising relative to the policy rate is "
           "money-market funding becoming more expensive at the margin",
           L1_LAGGED,
           "co-moves with a 0-2 day lag over the sample; the relationship is "
           "close to definitional but has not been identified structurally "
           "here",
           "SOFR rises for a week with no widening of the money-market "
           "spread over the policy rate",
           lag=1, n=400, confidence=0.7),
        _e("funding_stress", "financial_conditions", UP,
           "funding costs feed the financial-conditions index directly as "
           "one of its components, and indirectly through credit pricing",
           L1_LAGGED,
           "lagged co-movement at 5 days over the sample",
           "conditions loosen through a month of rising funding stress",
           lag=5, n=100, confidence=0.6),
        _e("financial_conditions", "credit_spread_hy", UP,
           "tighter conditions raise the price of the marginal borrower's "
           "credit before they raise the price of the safest borrower's",
           L1_LAGGED,
           "lagged co-movement at 10 days; direction is consistent across "
           "the sample and has not been identified against a common driver",
           "high-yield spreads compress through a sustained tightening",
           lag=10, n=100, confidence=0.55),
        _e("credit_spread_hy", "small_large_ratio", DOWN,
           "smaller firms refinance more often, at floating rates, from "
           "fewer lenders; a widening in the marginal cost of credit reaches "
           "their equity value before it reaches a large firm's",
           L1_LAGGED,
           "lagged co-movement at 15 days over the sample",
           "small caps outperform through a sustained high-yield widening "
           "with no offsetting growth surprise",
           lag=15, n=90, confidence=0.5,
           competing="both respond to the same growth expectation, and "
                     "neither transmits to the other"),

        # --- discount-rate chain --------------------------------------------
        _e("real_yield", "curve_slope", UP,
           "a real-yield move that is concentrated at the long end steepens "
           "the curve mechanically",
           L1_LAGGED,
           "co-moves at 0-1 day when the move is long-end led",
           "long real yields rise with no change in the 2s10s slope",
           lag=1, n=400, confidence=0.5),
        _e("real_yield", "small_large_ratio", DOWN,
           "the value of a cash flow further in the future falls faster when "
           "the real discount rate rises; a company whose value is mostly "
           "terminal is repriced more than one whose value is mostly current "
           "earnings. This is the present-value identity, not a correlation",
           L3_STRUCTURAL,
           "structural restriction: the discount-rate identity fixes the "
           "SIGN and the ORDERING of the response by duration, and the "
           "ordering is what distinguishes it from a common growth shock",
           "long-duration equity outperforms short-duration equity through a "
           "sustained real-yield rise, with duration ranking preserved",
           lag=3, n=200, confidence=0.65,
           competing="a growth shock moves real yields and equity together "
                     "with no discounting channel; discriminated by the "
                     "DURATION ORDERING, which a growth shock does not "
                     "predict"),

        # --- energy / capital-goods chain -----------------------------------
        _e("commodity_oil", "business_investment", UP,
           "a higher crude price raises producer cash flow, and producer "
           "capital budgets are set from cash flow with a lag of one to two "
           "planning cycles",
           L1_LAGGED,
           "lagged co-movement at roughly two quarters in the sample; the "
           "sample contains one full cycle, which is not enough to identify",
           "producer capex falls through a sustained doubling of the crude "
           "price",
           lag=120, n=10, confidence=0.45,
           competing="both respond to global demand"),
        _e("business_investment", "industrial_production", UP,
           "capital budgets become equipment orders, and equipment orders "
           "become production at the supplier",
           L1_LAGGED,
           "lagged co-movement at roughly one quarter",
           "production falls through a sustained rise in investment "
           "intentions",
           lag=90, n=12, confidence=0.45),

        # --- dollar / translation chain -------------------------------------
        _e("fx_dxy", "growth", DOWN,
           "a stronger trade-weighted dollar reduces the domestic-currency "
           "value of foreign revenue on translation, and reduces the price "
           "competitiveness of exports. The translation leg is an accounting "
           "identity for any firm reporting in dollars with foreign revenue",
           L3_STRUCTURAL,
           "structural restriction: the translation effect is an identity "
           "whose SIZE is fixed by the foreign-revenue share, so the "
           "cross-section predicts which firms are affected and by how much "
           "-- a prediction a common-shock story does not make",
           "firms with high foreign-revenue shares show no larger revenue "
           "effect than domestic-only firms through a sustained dollar move",
           lag=60, n=20, confidence=0.6,
           competing="a global risk-off shock strengthens the dollar and "
                     "weakens growth independently; discriminated by the "
                     "foreign-revenue cross-section"),

        # --- volatility / flow chain ----------------------------------------
        _e("realised_vol", "vix", UP,
           "implied volatility is priced off realised volatility plus a "
           "premium; the premium moves more slowly than the realised term",
           L2_INFORMATION,
           "directional dependence from realised to implied at 1-2 days, "
           "stronger than the reverse direction over the sample; this is an "
           "INFORMATION-FLOW result and does not establish direction",
           "implied volatility leads realised volatility over a sustained "
           "period",
           lag=1, n=300, confidence=0.5),
        _e("vix", "small_large_ratio", DOWN,
           "risk-targeting mandates cut the most volatile exposure first, "
           "and small capitalisation is the more volatile exposure",
           L1_LAGGED,
           "lagged co-movement at 2 days",
           "small caps outperform through a sustained volatility rise",
           lag=2, n=300, confidence=0.5,
           competing="both respond to the same growth news"),
        _e("funding_stress", "market_liquidity", DOWN,
           "a dealer funding its inventory more expensively quotes wider and "
           "smaller",
           L1_LAGGED,
           "lagged co-movement at 1 day in the sample",
           "quoted depth improves through a sustained funding widening",
           lag=1, n=90, confidence=0.5),

        # --- policy transmission --------------------------------------------
        _e("policy_rate", "sofr", UP,
           "the secured overnight rate trades within the policy corridor by "
           "construction",
           L3_STRUCTURAL,
           "structural restriction: the corridor is an administered bound, "
           "so the relationship is imposed by policy rather than estimated",
           "the secured overnight rate trades outside the corridor for more "
           "than a settlement period",
           lag=1, n=400, confidence=0.85,
           competing="none that survives the corridor being administered; "
                     "the bound is the identification"),
        _e("policy_rate", "treasury_2y", UP,
           "the two-year yield is close to an average of expected policy "
           "over two years",
           L1_LAGGED,
           "lagged co-movement at 0-1 day; the expectations identity is "
           "approximate because it also contains a term premium this engine "
           "does not measure",
           "the two-year yield falls through a sustained tightening with no "
           "change in the expected path",
           lag=1, n=400, confidence=0.7),
        _e("inflation", "policy_rate", UP,
           "a mandate-driven reaction function raises the policy rate when "
           "inflation is above target",
           L1_LAGGED,
           "lagged co-movement at roughly one to two meetings; the reaction "
           "function has not been estimated here",
           "the policy rate is cut through a sustained overshoot with no "
           "offsetting labour-market deterioration",
           lag=45, n=30, confidence=0.55,
           competing="both respond to the growth cycle"),
        _e("labour", "consumer_demand", DOWN,
           "unemployment rising reduces aggregate household income and, "
           "separately, precautionary saving rises",
           L1_LAGGED,
           "lagged co-movement at roughly one quarter",
           "consumption accelerates through a sustained rise in "
           "unemployment",
           lag=90, n=12, confidence=0.5),
    ]


def seed_graph() -> StructuralCausalGraph:
    """The graph a fresh deployment starts with."""
    return StructuralCausalGraph(seed_edges())

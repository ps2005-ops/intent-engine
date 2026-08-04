"""External intelligence: market, macro and competitive context.

The boundary between the market-learning engine and the founder product. Every
module here reads PUBLIC sources and versioned contracts only — there is no
import path from this package to the engine's paper book, strategy registry,
funnel or experiment stores, and `tests/test_market_intel_contract.py` asserts
the absence of that edge rather than trusting it.
"""

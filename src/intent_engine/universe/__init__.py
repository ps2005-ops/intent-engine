"""Company prediction/trading universe + company-specific learning.

The purpose of the whole hosted loop is to IMPROVE the Intent Engine by
learning from the companies it researches and predicts. This package owns:

  * the versioned CompanyPredictionUniverse (who we track, and how each company
    may or may not be traded) — see `companies.py`;
  * the durable store for universe versions — see `store.py`;
  * per-company + cross-company learning state — see `learning.py`.

The load-bearing safety property lives here: a PRIVATE company can NEVER be
converted into a stock order (`CompanyProfile.may_generate_order` is False for
it, and the execution service refuses it). Proxies are always labelled and
never imply the private company's own performance.
"""
from __future__ import annotations

from intent_engine.universe.companies import (
    CompanyClass,
    CompanyProfile,
    CompanyPredictionUniverse,
    default_universe,
)
from intent_engine.universe.store import UniverseStore

__all__ = [
    "CompanyClass",
    "CompanyProfile",
    "CompanyPredictionUniverse",
    "default_universe",
    "UniverseStore",
]

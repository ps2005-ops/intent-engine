"""The founder decision experience — the 60-second answer, and what backs it.

The customer's message, in one line: *good intelligence is wasted if the
presentation is difficult.* The backend was not the problem. The default was.

This package owns the first screen a founder sees and the contract that makes
it possible to build: an insight that cannot be displayed unless it says why it
matters and what decision it touches.
"""
from intent_engine.founder_brief.contract import (
    CONTRACT_VERSION,
    FounderInsight,
    InsightRejected,
    validate,
)

__all__ = ["CONTRACT_VERSION", "FounderInsight", "InsightRejected", "validate"]

"""Market opportunity reasoning — the layer between a strategic reading of a
company and a position in it.

`opportunity.classify` is the only entry point. It reuses the Founder
Intelligence strategic report rather than reasoning again, and turns it into a
recorded, classified opportunity with the gates that stopped it stated.
"""
from intent_engine.market.opportunity import (
    CLASSIFICATIONS,
    Opportunity,
    classify,
)

__all__ = ["CLASSIFICATIONS", "Opportunity", "classify"]

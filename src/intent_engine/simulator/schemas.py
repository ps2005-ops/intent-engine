"""Business-domain-specific output shapes (Week 2). Kept out of core/schemas.py because
"founder priority" and "upside/base/downside scenarios" are Pre-Mortem Machine concepts,
not generic Intent Engine concepts a future voice-assistant domain would share.
"""

from typing import List, Optional
from pydantic import BaseModel, Field

from ..core.schemas import StructuredIntent

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

FounderPriority = Literal["growth", "profitability", "survival", "optionality"]


class Scenario(BaseModel):
    name: Literal["upside", "base", "downside"]
    tag: str = Field(..., description="Short situational label for this branch, e.g. 'strong fundraising', not a sentence.")
    key_deltas: str = Field(..., description="Short, concrete outcome deltas as one line, e.g. '+$2M runway, +2 hires possible'.")


class ScenarioSet(BaseModel):
    primary_priority: FounderPriority
    scenarios: List[Scenario]


class BusinessStructuredIntent(StructuredIntent):
    """Adds Scale/Leverage/Luck framework signals to the domain-agnostic
    StructuredIntent. Kept out of core/schemas.py for the same reason
    FounderPriority/ScenarioSet are: these are Pre-Mortem Machine concepts, not
    generic Intent Engine concepts voice/ would ever need. Subclassing (rather
    than adding fields to core.schemas.StructuredIntent directly) means every
    other consumer of the base class -- core/classifier.py,
    simulator/outcome_simulation.py's two-call reference path, and any future
    voice/ use -- is completely unaffected; only analysis.py's combined-call
    path constructs this subclass.
    """

    scale_efficiency: Optional[Literal["proportional", "cost_outpacing_output", "unclear"]] = None
    # Does cost/output scale proportionally, or is cost growing faster than
    # output? "unclear" if the decision text doesn't contain enough signal --
    # do not force a guess.

    leverage_type: List[Literal["financial", "people", "technology", "media", "none_apparent"]] = Field(
        default_factory=list
    )
    # Which forms of leverage (if any) this decision relies on. Multiple can
    # apply. "none_apparent" if the decision is pure linear effort with no
    # identified leverage mechanism -- never left empty by the classifier
    # (see analysis.py's tool schema: minItems=1), since an omitted/empty list
    # would be indistinguishable from "not asked," not the same honest signal
    # as an explicit "none_apparent."
    #
    # OPEN CALIBRATION QUESTION, found during the extraction-reliability check
    # (8 runs each, 3 decisions, real API calls -- not estimated), same shape
    # as the voice-salience finding in voice/classifier.py. scale_efficiency
    # and market_timing_signal were highly stable (8/8 in their own targeted
    # example each; market_timing_signal was also 8/8 "uncertain" on the two
    # examples whose text says nothing about market conditions). leverage_type
    # was NOT stable on the market-timing example, where the decision text
    # never states what leverage mechanism the entrant would use:
    #   {('people','technology'): 4, ('people',): 3, ('financial','people'): 1}
    # across 8 runs of the identical input. The model appears to guess a
    # plausible leverage type rather than reliably answering "none_apparent"
    # when the signal is genuinely absent from the text -- unresolved, not
    # settled by this data alone, but real and worth tracking before treating
    # leverage_type as trustworthy on ambiguous decisions specifically.

    market_timing_signal: Optional[Literal["rising_tide", "saturated", "uncertain"]] = None
    # Is the market growing/under-saturated (rising_tide), already crowded
    # (saturated), or is there insufficient signal in the decision text to
    # judge? "uncertain" is a valid, honest answer -- do not force a guess.

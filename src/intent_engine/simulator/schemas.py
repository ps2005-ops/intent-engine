"""Business-domain-specific output shapes (Week 2). Kept out of core/schemas.py because
"founder priority" and "upside/base/downside scenarios" are Pre-Mortem Machine concepts,
not generic Intent Engine concepts a future voice-assistant domain would share.
"""

from typing import List
from pydantic import BaseModel, Field

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

FounderPriority = Literal["growth", "profitability", "survival", "optionality"]


class Scenario(BaseModel):
    name: Literal["upside", "base", "downside"]
    narrative: str
    key_deltas: str = Field(..., description="Short, concrete outcome deltas as one line, e.g. '+$2M runway, +2 hires possible'.")


class ScenarioSet(BaseModel):
    primary_priority: FounderPriority
    scenarios: List[Scenario]

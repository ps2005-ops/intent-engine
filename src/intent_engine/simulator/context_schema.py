"""Business context schema for the Pre-Mortem Machine.

Scoped to pre-seed/seed SaaS per the Week 1 spec's risk mitigation (narrow domain
reduces out-of-distribution failures in intent classification).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class BusinessContext(BaseModel):
    revenue: Optional[str] = None
    growth_rate: Optional[str] = None
    team_size: Optional[int] = None
    runway_months: Optional[int] = None
    market: Optional[str] = None
    competitive_position: Optional[str] = None
    founder_goals: Optional[str] = None
    stated_priorities: List[str] = Field(default_factory=list)

    def to_prompt_text(self) -> str:
        lines = []
        if self.revenue:
            lines.append(f"Revenue: {self.revenue}")
        if self.growth_rate:
            lines.append(f"Growth rate: {self.growth_rate}")
        if self.team_size is not None:
            lines.append(f"Team size: {self.team_size}")
        if self.runway_months is not None:
            lines.append(f"Runway: {self.runway_months} months")
        if self.market:
            lines.append(f"Market: {self.market}")
        if self.competitive_position:
            lines.append(f"Competitive position: {self.competitive_position}")
        if self.founder_goals:
            lines.append(f"Founder-stated goals: {self.founder_goals}")
        if self.stated_priorities:
            lines.append(f"Stated priorities: {', '.join(self.stated_priorities)}")
        return "\n".join(lines) if lines else "No additional business context provided."

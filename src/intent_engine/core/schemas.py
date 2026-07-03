"""Domain-agnostic data shapes shared by every Intent Engine consumer (simulator, voice, ...)."""

from typing import List, Optional
from pydantic import BaseModel, Field

try:
    from typing import Literal
except ImportError:  # pragma: no cover - py<3.8 fallback, not expected here
    from typing_extensions import Literal


class RawInput(BaseModel):
    """What every domain hands to the intent classifier: raw text plus serialized context.

    Domain modules (simulator, voice) own their own structured context schema and are
    responsible for flattening it to `context_text` before calling the classifier, so the
    core engine never has to know about business- or voice-specific fields.
    """

    decision_text: str
    context_text: str


class StructuredIntent(BaseModel):
    """Structured output of the intent-classification stage."""

    decision_summary: str = Field(..., description="One-sentence restatement of the decision being evaluated.")
    goals: List[str] = Field(..., description="What the person/founder is explicitly or implicitly trying to achieve.")
    constraints: List[str] = Field(..., description="Hard limits: budget, timeline, team, runway, etc.")
    risk_tolerance: Literal["low", "medium", "high"] = Field(..., description="Inferred appetite for risk.")
    stated_priorities: List[str] = Field(default_factory=list, description="Priorities stated directly in the input.")
    inferred_priorities: List[str] = Field(default_factory=list, description="Priorities inferred but not stated.")


class FailureMode(BaseModel):
    description: str
    likelihood: Literal["unlikely", "possible", "likely", "tail_risk"]
    rationale: str


class RiskAudit(BaseModel):
    """Structured output of the outcome-simulation stage."""

    narrative_summary: str = Field(
        ...,
        description=(
            "One vivid, second-person, present-tense sentence framing the top risk as a felt "
            "regret, not a probability. Sits above the quantified audit as the conversion layer; "
            "does not replace it. E.g. 'You're explaining to your board in month 8 why the "
            "expansion drained the runway that was funding the business that actually worked.'"
        ),
    )
    failure_modes: List[FailureMode]
    recommended_stress_tests: List[str]
    key_sensitivity: str = Field(..., description="The single factor this decision is most sensitive to.")

"""Stage 1: raw context input -> structured intent (goals, constraints, risk tolerance)."""

from typing import Optional

from .llm_client import LLMClient
from .pipeline import Stage
from .schemas import RawInput, StructuredIntent

SYSTEM_PROMPT = """You are an intent-extraction engine used by a decision-support tool. \
Given a decision someone is about to make and context about their situation, extract their \
underlying intent: what they're really trying to achieve, what constraints bound them, and how \
much risk they seem willing to accept. Infer priorities they didn't state directly when the \
context supports it, but keep inferred and stated priorities clearly separate."""

INTENT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "decision_summary": {"type": "string"},
        "goals": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "risk_tolerance": {"type": "string", "enum": ["low", "medium", "high"]},
        "stated_priorities": {"type": "array", "items": {"type": "string"}},
        "inferred_priorities": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision_summary", "goals", "constraints", "risk_tolerance"],
}


class IntentClassifier(Stage):
    name = "intent_classifier"

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()

    def run(self, raw_input: RawInput) -> StructuredIntent:
        user_message = (
            f"Decision: {raw_input.decision_text}\n\n"
            f"Context:\n{raw_input.context_text}"
        )
        result = self.client.call_tool(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            tool_name="extract_intent",
            tool_description="Record the extracted structured intent for this decision.",
            input_schema=INTENT_TOOL_SCHEMA,
        )
        return StructuredIntent(**result)

"""Stage 2: structured intent + business context -> risk audit.

This is the business-domain-specific reasoning stage. It consumes the domain-agnostic
StructuredIntent produced by core.classifier and produces a domain-agnostic RiskAudit,
so later domains (voice) can plug in their own outcome-simulation stage against the
same core schemas.
"""

from typing import Optional

from ..core.llm_client import LLMClient
from ..core.pipeline import Stage
from ..core.schemas import RiskAudit, StructuredIntent
from .context_schema import BusinessContext

SYSTEM_PROMPT = """You are a pre-mortem risk auditor for pre-seed/seed-stage SaaS founders. \
Given a founder's decision, their inferred intent, and their business context, identify the \
top 3-5 ways this decision could fail, given their specific situation and stated goals. \
Do not claim false precision: use likelihood bands (unlikely, possible, likely, tail_risk), \
not fake percentages. Ground every failure mode in the specific context provided, not generic \
startup advice. Also name the single factor this decision is most sensitive to, and recommend \
concrete stress-tests the founder could run before committing.

Be concise: 1-2 sentences for each failure mode's description, 1 sentence for its rationale, \
1 sentence per stress-test. This is a quick pre-commit check, not a full report.

Within each failure mode's description, write in confident, direct language, not hedged \
qualifiers ("Your team will not survive doubling headcount without an ops hire" beats "the \
team may struggle with a larger headcount"). The likelihood field already carries the honest \
uncertainty -- the description doesn't need to hedge on top of it.

Also write narrative_summary: ONE short sentence, 30 words or fewer, second person, present \
tense, describing the single worst failure mode as something the founder is already living \
through, not a probability they're evaluating. It must do three things in that one short \
sentence: (a) name ONE specific vivid moment (a board meeting, a runway number, a slipping \
deadline) -- not a cascading multi-clause scenario with several sub-events strung together on \
commas, (b) explicitly state the pattern-match, using language like "this is exactly how \
[stage/type] founders lose [thing]" or "founders in your exact position almost always..." -- \
say it outright, don't just imply it, (c) frame the cost of NOT stress-testing this decision, \
not just the cost of the decision itself going wrong. Do not soften it with "might" or "could." \
If your draft has more than one comma-separated clause, cut it down to one. This sentence is \
the hook that gets someone to read the quantified audit below it, not a summary of that audit."""

RISK_AUDIT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "narrative_summary": {"type": "string", "maxLength": 220},
        "failure_modes": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "likelihood": {
                        "type": "string",
                        "enum": ["unlikely", "possible", "likely", "tail_risk"],
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["description", "likelihood", "rationale"],
            },
        },
        "recommended_stress_tests": {"type": "array", "items": {"type": "string"}},
        "key_sensitivity": {"type": "string"},
    },
    "required": ["narrative_summary", "failure_modes", "recommended_stress_tests", "key_sensitivity"],
}


class RiskAuditGenerator(Stage):
    name = "risk_audit_generator"

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()

    def run(
        self,
        decision_text: str,
        context: BusinessContext,
        intent: StructuredIntent,
    ) -> RiskAudit:
        user_message = (
            f"Decision: {decision_text}\n\n"
            f"Business context:\n{context.to_prompt_text()}\n\n"
            f"Inferred intent:\n"
            f"- Summary: {intent.decision_summary}\n"
            f"- Goals: {', '.join(intent.goals) or 'none extracted'}\n"
            f"- Constraints: {', '.join(intent.constraints) or 'none extracted'}\n"
            f"- Risk tolerance: {intent.risk_tolerance}\n"
            f"- Stated priorities: {', '.join(intent.stated_priorities) or 'none'}\n"
            f"- Inferred priorities: {', '.join(intent.inferred_priorities) or 'none'}"
        )
        result = self.client.call_tool(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            tool_name="record_risk_audit",
            tool_description="Record the structured risk audit for this decision.",
            input_schema=RISK_AUDIT_TOOL_SCHEMA,
            max_tokens=3072,
        )
        return RiskAudit(**result)

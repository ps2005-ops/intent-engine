"""Combined intent-classification + risk-audit stage, used by the simulator's actual pipeline.

Why this exists alongside core.classifier.IntentClassifier and
simulator.outcome_simulation.RiskAuditGenerator (rather than replacing them): those two
stages are correct and independently testable, but as two sequential Claude calls they
take ~20s+ end-to-end, blowing the Week 1 spec's <10s budget. A single combined call on
Haiku 4.5 with a flattened schema (parallel arrays instead of nested objects, which
Haiku handled unreliably) gets this to ~7-8s. IntentClassifier/RiskAuditGenerator are
kept as-is for reuse where the two-call latency doesn't matter (e.g. testing, or a
future domain with a looser budget).
"""

from typing import NamedTuple, Optional

from ..core.llm_client import LLMClient
from ..core.pipeline import Stage
from ..core.schemas import FailureMode, RiskAudit, StructuredIntent
from .context_schema import BusinessContext

FAST_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a pre-mortem risk auditor for pre-seed/seed-stage SaaS founders. \
In one pass: (1) extract the founder's intent (goals, constraints, risk tolerance) from \
their decision and context, then (2) identify the top 3 ways this decision could fail given \
that specific context. failure_descriptions, failure_likelihoods, and failure_rationales are \
PARALLEL arrays: index i in each describes the same failure mode. Use likelihood bands \
(unlikely, possible, likely, tail_risk), not fake percentages. Ground every failure mode in \
the specific context given, not generic startup advice. Be terse: max one short sentence per \
field. This is a fast pre-commit check, not a report."""

ANALYSIS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "decision_summary": {"type": "string"},
        "goals": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "constraints": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "risk_tolerance": {"type": "string", "enum": ["low", "medium", "high"]},
        "failure_descriptions": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
        "failure_likelihoods": {
            "type": "array",
            "items": {"type": "string", "enum": ["unlikely", "possible", "likely", "tail_risk"]},
            "minItems": 3,
            "maxItems": 3,
        },
        "failure_rationales": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
        "recommended_stress_tests": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "key_sensitivity": {"type": "string"},
    },
    "required": [
        "decision_summary",
        "goals",
        "constraints",
        "risk_tolerance",
        "failure_descriptions",
        "failure_likelihoods",
        "failure_rationales",
        "recommended_stress_tests",
        "key_sensitivity",
    ],
}


class AnalysisResult(NamedTuple):
    intent: StructuredIntent
    risk_audit: RiskAudit


class PremortemAnalyzer(Stage):
    name = "premortem_analyzer"

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient(model=FAST_MODEL)

    def run(self, decision_text: str, context: BusinessContext) -> AnalysisResult:
        user_message = f"Decision: {decision_text}\n\nContext:\n{context.to_prompt_text()}"
        result = self.client.call_tool(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            tool_name="record_analysis",
            tool_description="Record the combined intent extraction and risk audit.",
            input_schema=ANALYSIS_TOOL_SCHEMA,
            max_tokens=1024,
        )

        intent = StructuredIntent(
            decision_summary=result["decision_summary"],
            goals=result["goals"],
            constraints=result["constraints"],
            risk_tolerance=result["risk_tolerance"],
        )
        failure_modes = [
            FailureMode(description=desc, likelihood=likelihood, rationale=rationale)
            for desc, likelihood, rationale in zip(
                result["failure_descriptions"],
                result["failure_likelihoods"],
                result["failure_rationales"],
            )
        ]
        risk_audit = RiskAudit(
            failure_modes=failure_modes,
            recommended_stress_tests=result["recommended_stress_tests"],
            key_sensitivity=result["key_sensitivity"],
        )
        return AnalysisResult(intent=intent, risk_audit=risk_audit)

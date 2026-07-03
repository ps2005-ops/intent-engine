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
their decision and context, then (2) identify EXACTLY 3 ways this decision could fail given \
that specific context -- not 2, not 4: always exactly 3, even under the word budgets below. \
failure_descriptions, failure_likelihoods, and failure_rationales are PARALLEL arrays of \
length 3: index i in each describes the same failure mode. Use likelihood bands \
(unlikely, possible, likely, tail_risk), not fake percentages -- these bands are the honest \
signal and must stay calibrated to your actual confidence. Ground every failure mode in the \
specific context given, not generic startup advice. Be terse and keep every field within its \
word budget: failure_descriptions <=22 words, failure_rationales <=15 words, \
recommended_stress_tests <=18 words each, key_sensitivity <=25 words. These budgets are for \
cutting FILLER WORDS ONLY -- never cut the specific dollar amounts, percentages, or timeframes \
that make this grounded instead of generic, and never drop a failure mode to make the others fit \
the budget; if something has to give, go a few words over rather than cutting a number or an \
item. This is a fast pre-commit check, not a report.

Within failure_descriptions specifically, write in confident, direct language, not hedged \
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

ANALYSIS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "decision_summary": {"type": "string"},
        "goals": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "constraints": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "risk_tolerance": {"type": "string", "enum": ["low", "medium", "high"]},
        "narrative_summary": {"type": "string", "maxLength": 220},
        "failure_descriptions": {"type": "array", "items": {"type": "string", "maxLength": 170}, "minItems": 3, "maxItems": 3},
        "failure_likelihoods": {
            "type": "array",
            "items": {"type": "string", "enum": ["unlikely", "possible", "likely", "tail_risk"]},
            "minItems": 3,
            "maxItems": 3,
        },
        "failure_rationales": {"type": "array", "items": {"type": "string", "maxLength": 130}, "minItems": 3, "maxItems": 3},
        "recommended_stress_tests": {"type": "array", "items": {"type": "string", "maxLength": 150}, "maxItems": 3},
        "key_sensitivity": {"type": "string", "maxLength": 200},
    },
    "required": [
        "decision_summary",
        "goals",
        "constraints",
        "risk_tolerance",
        "narrative_summary",
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

        # Occasionally the model omits a required field or returns mismatched-length
        # parallel arrays despite the schema. One retry is cheap insurance against a
        # hard crash from a single bad generation; a second consecutive failure is a
        # real problem worth surfacing rather than silently retrying forever.
        last_error = None
        for attempt in range(2):
            result = self.client.call_tool(
                system=SYSTEM_PROMPT,
                user_message=user_message,
                tool_name="record_analysis",
                tool_description="Record the combined intent extraction and risk audit.",
                input_schema=ANALYSIS_TOOL_SCHEMA,
                max_tokens=1024,
            )
            try:
                return self._parse(result)
            except (KeyError, ValueError) as exc:
                last_error = exc
        raise RuntimeError(f"record_analysis response malformed twice in a row: {last_error}")

    def _parse(self, result: dict) -> AnalysisResult:
        lengths = {len(result[k]) for k in ("failure_descriptions", "failure_likelihoods", "failure_rationales")}
        if lengths != {3}:
            raise ValueError(f"expected 3 parallel failure-mode entries, got lengths {lengths}")

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
            narrative_summary=result["narrative_summary"],
            failure_modes=failure_modes,
            recommended_stress_tests=result["recommended_stress_tests"],
            key_sensitivity=result["key_sensitivity"],
        )
        return AnalysisResult(intent=intent, risk_audit=risk_audit)

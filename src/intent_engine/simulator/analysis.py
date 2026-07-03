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

import re
from typing import NamedTuple, Optional

from ..core.llm_client import LLMClient
from ..core.pipeline import Stage
from ..core.schemas import FailureMode, RiskAudit, StructuredIntent
from .context_schema import BusinessContext

FAST_MODEL = "claude-haiku-4-5-20251001"

# Occasionally the model leaks tag-like fragments (e.g. "</sensitivity>", "</invoke>")
# into an otherwise-fine string field -- a rare generation glitch, not a schema issue.
# Matches closing tags and simple self-contained opening tags, but not legitimate
# business text like "<5%" or "CAC < $50" (no letter immediately follows the "<").
_MARKUP_LEAK_PATTERN = re.compile(r"</[a-zA-Z]|<[a-zA-Z_]+>")

SYSTEM_PROMPT = """You are a pre-mortem risk auditor for pre-seed/seed-stage SaaS founders. \
In one pass: (1) extract the founder's intent as EXACTLY 2 goals and EXACTLY 2 constraints \
(pick the 2 that matter most, not the 4 that are merely true) plus risk tolerance, then (2) \
identify EXACTLY 3 ways this decision could fail given that specific context -- not 2, not 4: \
always exactly 3, even under the word budgets below -- plus EXACTLY 2 recommended stress-tests. \
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
through, not a probability they're evaluating. It must carry four qualities: (a) ONE specific \
vivid moment (a board meeting, a runway number, a slipping deadline), not a cascading scenario \
with several sub-events strung together on commas, (b) a stated pattern-match -- signal that \
founders in this situation predictably fail this way, not just that this founder might, (c) \
direct, unhedged language -- no "might" or "could," (d) an implicit sense that not stress-testing \
this is itself the risky move, not just that the decision might go wrong.

Vary the sentence's shape every time -- do not default to one fixed skeleton. Below are three \
DIFFERENT structures showing the range available; do not reuse their wording, only the shape \
of how they're built:
- Scene first, pattern-match as a trailing tag: "You're staring at a term sheet worse than \
today's, having spent the runway that would've gotten you a better one on your own -- this is \
the exact sequence that sinks pre-seed bridge rounds."
- Pattern-match first, scene second: "Founders who hire before PMF almost always end up here: \
four new salaries, zero repeatable pipeline, and a board asking what happened to the runway."
- Direct address with the pattern folded into the consequence, no "this is exactly how" phrasing \
at all: "Skip the stress test and you're the founder explaining in Q3 why doubling headcount \
moved no growth metric -- this specific hiring mistake repeats almost every time it's tried."
Pick whichever shape fits the specific failure mode best, or write a fourth shape entirely -- \
the four qualities above are the requirement, not the sentence skeleton. This sentence is the \
hook that gets someone to read the quantified audit below it, not a summary of that audit."""

ANALYSIS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "decision_summary": {"type": "string"},
        "goals": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        "constraints": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
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
        "recommended_stress_tests": {"type": "array", "items": {"type": "string", "maxLength": 150}, "minItems": 2, "maxItems": 2},
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

        for key, value in result.items():
            values = value if isinstance(value, list) else [value]
            for v in values:
                if isinstance(v, str) and _MARKUP_LEAK_PATTERN.search(v):
                    raise ValueError(f"field '{key}' contains leaked markup: {v!r}")

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

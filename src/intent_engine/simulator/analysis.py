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

import logging
import re
from typing import List, NamedTuple, Optional, Set

from spellchecker import SpellChecker

from ..core.llm_client import LLMClient
from ..core.pipeline import Stage
from ..core.schemas import FailureMode, RiskAudit
from .causal_model import CausalRelationship, relevant_relationships
from .context_schema import BusinessContext
from .retrieval import format_retrieval_digest, retrieve_similar
from .schemas import BusinessStructuredIntent, Scenario, ScenarioSet

logger = logging.getLogger(__name__)

FAST_MODEL = "claude-haiku-4-5-20251001"

# Occasionally the model leaks tag-like fragments (e.g. "</sensitivity>", "</invoke>")
# into an otherwise-fine string field -- a rare generation glitch, not a schema issue.
# Matches closing tags and simple self-contained opening tags, but not legitimate
# business text like "<5%" or "CAC < $50" (no letter immediately follows the "<").
_MARKUP_LEAK_PATTERN = re.compile(r"</[a-zA-Z]|<[a-zA-Z_]+>")

# narrative_summary's real length ceiling. The prompt targets ~40 words, but this is
# the actually-ENFORCED backstop (see _NarrativeSummaryTooLong below) -- the old
# maxLength:170 tool-schema hint was never enforced (Claude's tool-use API doesn't
# validate JSON-schema constraints server-side, and RiskAudit itself had no pydantic
# length constraint either), so real outputs silently ran up to 339 chars/58 words
# once the regret-avoidance + anti-templating instructions were added. ~300 chars
# gives room for the ~40-word target's natural variance (structural variation was
# the point of loosening the word count from 24) while still catching real outliers.
_NARRATIVE_SUMMARY_MAX_CHARS = 300


class _NarrativeSummaryTooLong(ValueError):
    """Distinct from other malformation ValueErrors below: a length overage is
    recoverable by truncation, unlike a markup leak or a mismatched-length array,
    so the retry loop in run() treats this one differently on a second consecutive
    miss (truncate instead of raising RuntimeError)."""


# Occasionally the model produces a coherent-looking sentence with a corrupted word
# inside it (e.g. "pricing pressure emerads" instead of "emerges") -- a compression
# artifact under tight word budgets, not a schema issue, so pydantic validation lets
# it through clean. Safety net: flag lowercase alphabetic words the dictionary doesn't
# know, skipping all-caps tokens (likely acronyms) and a manual allowlist of common
# startup/SaaS jargon a general English dictionary doesn't recognize -- extend the
# allowlist if a real word starts getting flagged.
_spellchecker = SpellChecker()
_DOMAIN_JARGON_ALLOWLIST = {
    "saas", "mrr", "arr", "cac", "ltv", "pmf", "apac", "gtm", "icp", "sdr", "kpi", "roi",
    "b2b", "b2c", "onboarding", "freemium", "fundraise", "fundraising", "preseed",
    "tranched", "tranching",
}
# Must capture contractions ("hasn't", "didn't") as one token, not split on the
# apostrophe -- splitting was a real bug: it turned "hasn't" into "hasn" + "t" and
# flagged "hasn" as a garbled word, causing false-positive retries (and, once, an
# outright crash) on completely ordinary English.
_WORD_PATTERN = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?")


def _find_garbled_words(text: str) -> Set[str]:
    candidates = set()
    for word in _WORD_PATTERN.findall(text):
        if len(word) < 4 or word.isupper():
            continue
        lower = word.lower()
        if lower in _DOMAIN_JARGON_ALLOWLIST:
            continue
        candidates.add(lower)
    return _spellchecker.unknown(candidates) if candidates else set()

SYSTEM_PROMPT = """You are a pre-mortem risk auditor for pre-seed/seed-stage SaaS founders. \
In one pass: (1) extract the founder's intent. goals and constraints must each be a JSON \
array of EXACTLY 2 short strings -- a real array, never a single string and never a \
stringified list like '["a", "b"]' -- pick the 2 that matter most, not the 4 that are merely \
true, plus risk_tolerance, then (2) \
identify EXACTLY 3 ways this decision could fail given that specific context -- not 2, not 4: \
always exactly 3, even under the word budgets below -- plus EXACTLY 1 recommended stress-test. \
failure_descriptions, failure_likelihoods, and failure_rationales are PARALLEL arrays of \
length 3: index i in each describes the same failure mode. Use likelihood bands \
(unlikely, possible, likely, tail_risk), not fake percentages -- these bands are the honest \
signal and must stay calibrated to your actual confidence. Ground every failure mode in the \
specific context given, not generic startup advice. Be terse and keep every field within its \
word budget: failure_descriptions <=13 words, failure_rationales <=8 words, \
recommended_stress_tests <=11 words. These budgets are for cutting FILLER WORDS ONLY -- never \
cut the specific dollar amounts, percentages, or timeframes that make this grounded instead of \
generic, and never drop a failure mode to make the others fit the budget; if something has to \
give, go a few words over rather than cutting a number or an item. Never compress a word into \
something that isn't a real word to hit a budget (e.g. "emerads" instead of "emerges") -- a \
correct sentence a few words over budget always beats a shorter one with a broken word in it. \
This is a fast pre-commit check, not a report.

Within failure_descriptions specifically, write in confident, direct language, not hedged \
qualifiers ("Your team will not survive doubling headcount without an ops hire" beats "the \
team may struggle with a larger headcount"). The likelihood field already carries the honest \
uncertainty -- the description doesn't need to hedge on top of it.

Also write key_sensitivity: ONE plain-data sentence, 13 words or fewer, naming the single \
factor this decision's success or failure is most sensitive to -- a number, threshold, or \
condition (e.g. "Churn above 8% erases the margin gain within two quarters."), not a summary \
of the audit above it and not a restatement of narrative_summary. This is a plain data field: \
end with a period or a number and nothing else. Never include XML/HTML-like tags, angle \
brackets, or any formatting/meta-commentary about the response itself.

Also write narrative_summary: ONE short sentence, 40 words or fewer, second person, present \
tense, describing the single worst failure mode as something the founder is already living \
through, not a probability they're evaluating.

This sentence must use Sutherland's regret-avoidance mechanism specifically -- not just a vivid \
bad outcome. Regret-avoidance requires: (1) place the founder in a specific future moment \
looking back at THIS decision, not a generic bad future, (2) make explicit that the outcome \
resulted from a choice they actively made -- something they authored, not something that just \
happened to them, (3) where the reference data supports it, let the sentence imply what \
inaction or the nearest alternative would have looked like instead, so there's a felt "and you \
could have avoided this" underneath it, even without spelling the alternative out in full. A \
sentence that is vivid and scary but never puts the founder in the position of having chosen \
this outcome over another path is not using the mechanism, however well-written.

It must also carry: (a) ONE specific vivid moment (a board meeting, a runway number, a slipping \
deadline), not a cascading scenario with several sub-events strung together on commas, (b) a \
stated pattern-match -- signal that founders in this situation predictably fail this way, not \
just that this founder might, (c) direct, unhedged language -- no "might" or "could." Stay in \
the same vivid, plain, concrete register all the way to the final word -- do not let the last \
clause drift into dry analytical or technical vocabulary (e.g. "...without local market friction \
modeling" breaks register; "...before you've validated a single local deal" holds it). The \
punchline should land in the same voice the sentence started in.

If you use a dash to connect clauses, it must be an em-dash (—), never a double-hyphen (--).

Do not converge on one rhythm every time. Vary, across responses: whether you use an em-dash at \
all (a single clause with no dash is a valid shape), sentence length (some should land well \
under the 40-word ceiling, not all stretched to it), and WHERE the pattern-match claim lands -- \
opening the sentence, closing it as a trailing tag, or embedded mid-sentence with no clause set \
apart at all. Below are three DIFFERENT structures illustrating that range -- these are \
illustrations of range, not a menu of 3 templates to rotate between; do not let any single one \
of these (or any other single shape) become your default:
- Scene first, pattern-match as a trailing tag, em-dash: "You're staring at a term sheet worse \
than the one patience would've gotten you, having spent the runway you chose to burn instead of \
validating first — this is the exact sequence that sinks pre-seed bridge rounds."
- Pattern-match opening, scene second, no dash: "Founders who hire before PMF always face this \
exact board question: what happened to the four salaries and zero pipeline you added instead of \
waiting the six months you had runway for."
- Chosen-path-vs-alternative embedded mid-sentence, short, no dash: "You chose to double \
headcount over validating demand, and now you're giving the board the same growth-stalled \
explanation every team in this spot gives."
Pick whichever shape fits the specific failure mode best, or write a genuinely different shape \
entirely -- the regret-avoidance mechanism and the four qualities above are the requirement, not \
any specific sentence skeleton. This sentence is the hook that gets someone to read the \
quantified audit below it, not a summary of that audit.

Finally: classify primary_priority as exactly ONE of growth, profitability, survival, \
optionality -- the single dominant thing this founder is actually optimizing for, not a blend \
of several. Then write EXACTLY 3 scenarios in this fixed order: upside, base, downside, each \
parameterized by that priority (a "growth" priority means scenarios stress growth levers; a \
"profitability" priority means they stress margin/cost levers; "survival" means runway/cash; \
"optionality" means flexibility/reversibility). Ground scenarios in the causal relationships \
listed in the user message where they apply -- e.g. if a relevant relationship says headcount \
growth increases burn, an upside scenario shouldn't assume hiring is free. Also weight the \
similar past decisions listed in the user message: if a 'strong match' precedent failed a \
specific way, that failure mode should show up in failure_descriptions or the downside \
scenario unless this decision differs meaningfully (say so implicitly through the delta \
numbers, don't just copy the precedent's outcome as if it's certain to repeat). \
scenario_tags and scenario_deltas are PARALLEL arrays of length 3, in that fixed \
upside/base/downside order. scenario_tags <=4 words each: a short situational label for what's \
driving this branch, e.g. "strong fundraising", "as planned", "competitor undercuts" -- NOT a \
sentence, just the label, matching the style "Scenario A (strong fundraising): +$2M runway, \
+2 hires possible". scenario_deltas <=8 words each: concrete deltas only, e.g. '+$2M runway, \
+2 hires' -- no full sentences, just the numbers/outcomes that changed.

Also classify three additional structured signals (a Scale/Leverage/Luck framework \
classification, separate from the risk audit above -- these are honest extraction \
signals, not risk claims, and must NOT be referenced in narrative_summary, \
key_sensitivity, or any failure_description this pass):

scale_efficiency: does this decision's cost and output scale proportionally (adding \
customers/revenue without proportional cost growth), or is cost growing faster than \
output (cost_outpacing_output)? Answer "unclear" if the decision text doesn't contain \
enough signal to judge -- do not force a guess.

leverage_type: a JSON array of every leverage mechanism this decision clearly relies \
on -- financial (raising or deploying capital), people (hiring, delegation), technology \
(automation, product-led/self-serve scaling), media (audience or distribution reach). \
Multiple can apply. If the decision is pure linear effort with no identified leverage \
mechanism, the array must be exactly ["none_apparent"] -- never leave it empty.

market_timing_signal: is this decision made in a market that's growing or \
under-saturated (rising_tide), already crowded (saturated), or is there insufficient \
signal in the decision text to judge (uncertain)? "uncertain" is a valid, honest answer \
-- do not force a guess when the text doesn't mention market conditions."""

ANALYSIS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "decision_summary": {"type": "string"},
        "goals": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        "constraints": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        "risk_tolerance": {"type": "string", "enum": ["low", "medium", "high"]},
        "narrative_summary": {"type": "string", "maxLength": _NARRATIVE_SUMMARY_MAX_CHARS},
        "failure_descriptions": {"type": "array", "items": {"type": "string", "maxLength": 100}, "minItems": 3, "maxItems": 3},
        "failure_likelihoods": {
            "type": "array",
            "items": {"type": "string", "enum": ["unlikely", "possible", "likely", "tail_risk"]},
            "minItems": 3,
            "maxItems": 3,
        },
        "failure_rationales": {"type": "array", "items": {"type": "string", "maxLength": 65}, "minItems": 3, "maxItems": 3},
        "recommended_stress_tests": {"type": "array", "items": {"type": "string", "maxLength": 85}, "minItems": 1, "maxItems": 1},
        "key_sensitivity": {"type": "string", "maxLength": 100},
        "primary_priority": {"type": "string", "enum": ["growth", "profitability", "survival", "optionality"]},
        "scenario_tags": {"type": "array", "items": {"type": "string", "maxLength": 30}, "minItems": 3, "maxItems": 3},
        "scenario_deltas": {"type": "array", "items": {"type": "string", "maxLength": 50}, "minItems": 3, "maxItems": 3},
        "scale_efficiency": {"type": "string", "enum": ["proportional", "cost_outpacing_output", "unclear"]},
        "leverage_type": {
            "type": "array",
            "items": {"type": "string", "enum": ["financial", "people", "technology", "media", "none_apparent"]},
            "minItems": 1,
        },
        "market_timing_signal": {"type": "string", "enum": ["rising_tide", "saturated", "uncertain"]},
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
        "primary_priority",
        "scenario_tags",
        "scenario_deltas",
        "recommended_stress_tests",
        "key_sensitivity",
        "scale_efficiency",
        "leverage_type",
        "market_timing_signal",
    ],
}


class AnalysisResult(NamedTuple):
    intent: BusinessStructuredIntent
    risk_audit: RiskAudit
    scenario_set: ScenarioSet


def _format_causal_context(relationships: List[CausalRelationship]) -> str:
    lines = [f"- {rel.trigger} -> {rel.effect}" for rel in relationships]
    return "\n".join(lines)


class PremortemAnalyzer(Stage):
    name = "premortem_analyzer"

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient(model=FAST_MODEL)

    def run(self, decision_text: str, context: BusinessContext) -> AnalysisResult:
        context_text = context.to_prompt_text()
        relationships = relevant_relationships(decision_text, context_text, limit=3)
        retrieved = retrieve_similar(decision_text, top_k=3)
        retrieval_digest = format_retrieval_digest(
            retrieved, current_team_size=context.team_size, current_runway_months=context.runway_months
        )
        user_message = (
            f"Decision: {decision_text}\n\n"
            f"Context:\n{context_text}\n\n"
            f"Potentially relevant causal relationships for this domain (use where applicable, "
            f"ignore where not):\n{_format_causal_context(relationships)}\n\n"
            f"Similar past decisions with known outcomes (weight 'strong match' entries more "
            f"than 'loose match' ones; use these to ground scenarios and failure modes in real "
            f"precedent, not as facts about THIS business):\n{retrieval_digest}"
        )

        # Occasionally the model omits a required field or returns mismatched-length
        # parallel arrays despite the schema. One retry is cheap insurance against a
        # hard crash from a single bad generation; a second consecutive failure is a
        # real problem worth surfacing rather than silently retrying forever. Logged
        # every time it fires so we can see real incidence in production, not just
        # guess from a handful of test fixtures.
        last_error = None
        for attempt in range(2):
            result = self.client.call_tool(
                system=SYSTEM_PROMPT,
                user_message=user_message,
                tool_name="record_analysis",
                tool_description="Record the combined intent extraction and risk audit.",
                input_schema=ANALYSIS_TOOL_SCHEMA,
                max_tokens=1536,
            )
            try:
                return self._parse(result)
            except _NarrativeSummaryTooLong as exc:
                last_error = exc
                if attempt == 1:
                    logger.warning("record_analysis narrative_summary exceeded %d chars twice in a "
                                    "row, truncating instead of retrying again: %s", _NARRATIVE_SUMMARY_MAX_CHARS, exc)
                    try:
                        return self._parse(result, force_truncate=True)
                    except (KeyError, ValueError) as exc2:
                        last_error = exc2
                else:
                    logger.warning("record_analysis narrative_summary exceeded %d chars, retrying: %s",
                                    _NARRATIVE_SUMMARY_MAX_CHARS, exc)
            except (KeyError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "record_analysis attempt %d/2 failed validation, %s: %s",
                    attempt + 1,
                    "retrying" if attempt == 0 else "giving up",
                    exc,
                )
        raise RuntimeError(f"record_analysis response malformed twice in a row: {last_error}")

    def _parse(self, result: dict, force_truncate: bool = False) -> AnalysisResult:
        lengths = {len(result[k]) for k in ("failure_descriptions", "failure_likelihoods", "failure_rationales")}
        if lengths != {3}:
            raise ValueError(f"expected 3 parallel failure-mode entries, got lengths {lengths}")

        scenario_lengths = {len(result[k]) for k in ("scenario_tags", "scenario_deltas")}
        if scenario_lengths != {3}:
            raise ValueError(f"expected 3 parallel scenario entries, got lengths {scenario_lengths}")

        for key, value in result.items():
            values = value if isinstance(value, list) else [value]
            for v in values:
                if not isinstance(v, str):
                    continue
                if _MARKUP_LEAK_PATTERN.search(v):
                    raise ValueError(f"field '{key}' contains leaked markup: {v!r}")
                # Log-only, not retry-blocking: the dictionary check has unknown
                # precision against a bug ("emerads" for "emerges") that's occurred
                # once all session, and already produced two false-positive crashes
                # on ordinary words ("analytics", "underdeliver", "onboard") the
                # dictionary just doesn't know. Blocking on a signal this noisy is a
                # worse trade than the rare bug it's meant to catch. This gives real
                # incidence data over time -- if it turns out to matter, that's the
                # evidence to justify a better check (domain-augmented dictionary, a
                # narrower heuristic), not a guess made now.
                garbled = _find_garbled_words(v)
                if garbled:
                    logger.warning("field '%s' contains a possibly-garbled token %r: %r", key, garbled, v)

        narrative_summary = result["narrative_summary"]
        if len(narrative_summary) > _NARRATIVE_SUMMARY_MAX_CHARS:
            if force_truncate:
                narrative_summary = narrative_summary[:_NARRATIVE_SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + "…"
            else:
                raise _NarrativeSummaryTooLong(
                    f"narrative_summary is {len(narrative_summary)} chars, exceeds {_NARRATIVE_SUMMARY_MAX_CHARS}"
                )

        intent = BusinessStructuredIntent(
            decision_summary=result["decision_summary"],
            goals=result["goals"],
            constraints=result["constraints"],
            risk_tolerance=result["risk_tolerance"],
            scale_efficiency=result["scale_efficiency"],
            leverage_type=result["leverage_type"],
            market_timing_signal=result["market_timing_signal"],
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
            narrative_summary=narrative_summary,
            failure_modes=failure_modes,
            recommended_stress_tests=result["recommended_stress_tests"],
            key_sensitivity=result["key_sensitivity"],
        )
        scenarios = [
            Scenario(name=name, tag=tag, key_deltas=deltas)
            for name, tag, deltas in zip(
                ("upside", "base", "downside"),
                result["scenario_tags"],
                result["scenario_deltas"],
            )
        ]
        scenario_set = ScenarioSet(primary_priority=result["primary_priority"], scenarios=scenarios)
        return AnalysisResult(intent=intent, risk_audit=risk_audit, scenario_set=scenario_set)

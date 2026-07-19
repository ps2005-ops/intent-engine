"""T005 (overnight Task 4, spec: docs/TASK4_SPEC_PROPOSAL.md, approved
2026-07-18): the structural-mechanisms section of the premortem rendering.

Additive only. One ISOLATED extraction call (the exact prompt/schema design
Task 3's reliability gate verified and the 2026-07-18 v2 gate re-verified —
duplicated here as production code per the same convention M7 used for
M4's design; the gate script itself stays TEST-ONLY per its scope wall) →
the deterministic matcher (core.mechanism_library.match_mechanisms) →
a rendered list where every line carries its matched-condition provenance
and a cited historical instance.

Hard walls honored here:
- PremortemAnalyzer's combined-call prompt is untouched (A3) — this is the
  LuckTest isolation pattern: separate call, separate module.
- Information hiding: the extraction prompt shows ONLY the closed
  trigger-condition taxonomy — no mechanism names, no library content.
- Language wall: "possibly in play" phrasing only; assert_section_language_walls
  is a code-level backstop greping the RENDERED section for forbidden
  probability/trade/prediction phrasing (word-boundary matching, so
  legitimate words like "buyers" in future data can't false-positive).
- The extraction prompt below is GATE-VERIFIED SURFACE: editing it re-opens
  the Task 3 gate (full 5x3 protocol) — PARK, never patch (spec park
  condition 1).
"""

import re
from typing import List, Optional

from ..core.llm_client import LLMClient
from ..core.mechanism_library import RankedMechanism, TriggerCondition, match_mechanisms

FAST_MODEL = "claude-haiku-4-5-20251001"

TRIGGER_CONDITIONS = list(TriggerCondition.__args__)

# Verbatim the design the Task 3 gate verified (v1 2026-07-15, v2 rerun
# PASS 2026-07-18) -- decision-text flavor.
EXTRACTION_SYSTEM_PROMPT = f"""You are identifying which of a fixed set of structural conditions are \
present in a business decision's description. You have no information about any historical \
pattern, precedent, or named phenomenon this might resemble -- judge ONLY what the text itself \
states or clearly implies.

The closed set of conditions you may select from (select ONLY ones the text actually supports --\
 do not select a condition on a vague or generic resemblance):
{chr(10).join(f"- {c}" for c in TRIGGER_CONDITIONS)}

If the text is genuinely ambiguous or doesn't clearly support any condition, select FEW or NONE \
-- do not force a selection to seem thorough. Confidence should track how clearly the text \
actually states each condition, not how many conditions you can find a stretch for."""

EXTRACTION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "trigger_conditions": {
            "type": "array",
            "items": {"type": "string", "enum": TRIGGER_CONDITIONS},
            "description": "The subset of conditions the text actually, clearly supports.",
        },
    },
    "required": ["trigger_conditions"],
}

SECTION_HEADER = "Structural mechanisms possibly in play:"

# Word-boundary walls for the rendered section (bar (d) of the spec).
# "will happen"/trade verbs/position sizing per A-M4, plus probability
# phrasing -- this section carries structural reads, never predictions.
_FORBIDDEN_SECTION_PATTERNS = (
    r"\bwill happen\b", r"\bwill\b", r"\bbuy\b", r"\bsell\b",
    r"\bposition size\b", r"\bprobability\b", r"p=", r"% chance",
)


def assert_section_language_walls(rendered: str) -> None:
    lowered = rendered.lower()
    violations = [p for p in _FORBIDDEN_SECTION_PATTERNS if re.search(p, lowered)]
    if violations:
        raise ValueError(f"Mechanism-section language wall violation(s): {violations}")


def extract_decision_trigger_conditions(
    decision_text: str, client: Optional[LLMClient] = None,
) -> List[str]:
    """One real, isolated call -- the gate already verified this design; a
    production run needs one call, not five."""
    client = client or LLMClient(model=FAST_MODEL)
    result = client.call_tool(
        system=EXTRACTION_SYSTEM_PROMPT,
        user_message=f"Decision text:\n{decision_text}\n\nWhich conditions are present?",
        tool_name="record_trigger_conditions",
        tool_description="Record the identified trigger conditions.",
        input_schema=EXTRACTION_TOOL_SCHEMA,
        max_tokens=200,
    )
    return sorted(result["trigger_conditions"])


def compute_ranked_mechanisms(
    decision_text: str, client: Optional[LLMClient] = None,
) -> List[RankedMechanism]:
    """Extraction (1 live call) -> deterministic matcher. Returns [] on a
    no-condition or no-match read -- correct silence, never a forced match."""
    conditions = extract_decision_trigger_conditions(decision_text, client=client)
    if not conditions:
        return []
    return match_mechanisms(conditions)


def render_mechanism_section(ranked: List[RankedMechanism]) -> str:
    """Empty string when nothing matched -- the CALLER renders no section at
    all (bar (b): silence is the correct output, not a 'none matched' line;
    the premortem is a user-facing product surface, unlike the weekly
    report where the explicit 'none matched' line is itself the product)."""
    if not ranked:
        return ""
    lines = [SECTION_HEADER]
    for r in ranked:
        instance = r.mechanism.historical_instances[0]
        lines.append(
            f"  - {r.mechanism.name} ({r.mechanism.confidence_tier}) -- matched on: "
            f"{', '.join(r.matched_conditions)}. Historical instance: {instance.case} ({instance.year})."
        )
    rendered = "\n".join(lines)
    assert_section_language_walls(rendered)
    return rendered


# --- T007: mechanism explanation depth -------------------------------------
# Approved 2026-07-18 (docs/MECHANISM_EXPLANATION_DEPTH_SPEC.md); built
# 2026-07-22 under the OPTION-1 wall reconciliation the founder ratified
# after the build-time (c)-vs-(d) conflict (docs/T007_PARK_FINDING.md).
#
# A DETERMINISTIC render of data that already exists on each matched
# Mechanism -- matched_conditions (what fired), causal_chain (documented
# pattern, verbatim), historical_instances (cited precedent). ZERO LLM
# calls: a model call in this feature is a park condition, not an option.
#
# Wall scoping (option 1): the language wall applies to the SYSTEM-AUTHORED
# framing this renderer generates (the header/label lines) -- NOT to the
# verbatim causal_chain steps or the cited source, which bar (c) guarantees
# are unedited quotes of documented history, not the system's predictive
# voice. "No predictions in the system's voice" is what the wall protects;
# a third-person historical description that says a firm "was forced to
# sell" an asset is not the system advising a sale. This preserves bar
# (d)'s intent while resolving the (c)/(d) conflict.

EXPLANATION_HEADER_PREFIX = "Why this may be in play — "

# The forbidden terms, applied ONLY to system-authored lines. Superset of
# the section wall plus the T007 spec's added prediction terms.
_EXPLANATION_SYSTEM_FORBIDDEN = (
    r"\bwill happen\b", r"\bwill\b", r"\bbuy\b", r"\bsell\b",
    r"\bposition size\b", r"\bprobability\b", r"p=", r"% chance",
    r"\bforecast\b", r"\bexpected to\b", r"\baccuracy\b", r"\bpredict\b",
)


def assert_explanation_system_walls(system_lines: List[str]) -> None:
    """Bar (d), option-1 scope: 0 forbidden terms in the SYSTEM-AUTHORED
    lines only. Verbatim causal-chain steps and the cited source are passed
    separately and are exempt (bar (c) guarantees they're quotes)."""
    blob = "\n".join(system_lines).lower()
    violations = [p for p in _EXPLANATION_SYSTEM_FORBIDDEN if re.search(p, blob)]
    if violations:
        raise ValueError(f"Mechanism-explanation system-line wall violation(s): {violations}")


def render_mechanism_explanation(ranked: List[RankedMechanism]) -> str:
    """Fuller, traceable explanation of a deterministic match. Empty string
    on no match (bar (e), correct silence). Every block: system-authored
    framing (wall-checked) + verbatim causal_chain (bar (c)) + matched
    conditions (bar (a)) + cited instance with year and source (bar (b))."""
    if not ranked:
        return ""
    blocks = []
    for r in ranked:
        m = r.mechanism
        instance = m.historical_instances[0]
        # System-authored lines -- these the renderer generates, so these
        # are wall-checked.
        system_lines = [
            f"{EXPLANATION_HEADER_PREFIX}{m.name} ({m.confidence_tier})",
            "  Conditions present in your situation:",
            "  How it unfolds (documented pattern):",
            "  Historical precedent:",
            "  Source:",
        ]
        assert_explanation_system_walls(system_lines)

        lines = [f"{EXPLANATION_HEADER_PREFIX}{m.name} ({m.confidence_tier})",
                 "  Conditions present in your situation:"]
        lines += [f"    - {c}" for c in r.matched_conditions]           # bar (a)
        lines.append("  How it unfolds (documented pattern):")
        lines += [f"    {i}. {step}" for i, step in enumerate(m.causal_chain, 1)]  # bar (c) verbatim
        lines.append(f"  Historical precedent: {instance.case} ({instance.year})")  # bar (b)
        lines.append(f"  Source: {instance.source}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)

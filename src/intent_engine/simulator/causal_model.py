"""Hand-coded causal relationships for early-stage SaaS (Week 2 spec: "no Bayesian
networks yet... define sensitivity relationships").

This is deliberately not a numeric calculator: BusinessContext keeps revenue/growth_rate
as free text (a Week 1 choice to avoid guessing units this early), so these relationships
encode DIRECTION and REASONING, not formulas. `relevant_relationships()` does simple
keyword/tag matching against the decision text + context so only relationships that
plausibly apply to a given decision get fed to the LLM as grounding context for scenario
generation -- this keeps the model's causal reasoning anchored to explicit, inspectable
logic instead of free-floating speculation, without pretending to precision the inputs
don't support.
"""

import re
from typing import List, NamedTuple, Optional


class CausalRelationship(NamedTuple):
    trigger: str
    effect: str
    tags: List[str]


CAUSAL_RELATIONSHIPS: List[CausalRelationship] = [
    CausalRelationship(
        trigger="CAC increases",
        effect="LTV must increase proportionally, or burn rate absorbs the gap",
        tags=["cac", "acquisition cost", "customer acquisition"],
    ),
    CausalRelationship(
        trigger="Headcount increases",
        effect="execution velocity increases short-term, but burn rate increases immediately while productivity ramps over months",
        tags=["hiring", "headcount", "team size", "hire"],
    ),
    CausalRelationship(
        trigger="Prices increase",
        effect="churn increases, with magnitude driven by switching costs and competitive alternatives",
        tags=["pricing", "price increase", "price"],
    ),
    CausalRelationship(
        trigger="Growth rate accelerates",
        effect="support, infra, and onboarding load increase faster than revenue, straining a small team",
        tags=["growth", "scale", "scaling"],
    ),
    CausalRelationship(
        trigger="Runway shortens relative to a commitment's timeline",
        effect="fundraising urgency rises and risk tolerance for the commitment should fall, not stay fixed",
        tags=["runway", "fundraise", "fundraising", "cash", "raise"],
    ),
    CausalRelationship(
        trigger="Entering a new market or geography",
        effect="CAC rises short-term due to unfamiliarity with local buyers, channels, and competitors",
        tags=["expansion", "new market", "geography", "international", "asia", "apac"],
    ),
    CausalRelationship(
        trigger="Headcount grows faster than revenue",
        effect="burn multiple worsens, shortening effective runway beyond the raw cash math",
        tags=["hiring", "headcount", "burn multiple", "team size"],
    ),
    CausalRelationship(
        trigger="Competitive pressure increases",
        effect="pricing power decreases and sales cycles lengthen as buyers gain leverage to shop around",
        tags=["competition", "competitive", "incumbent", "competitor"],
    ),
]


def relevant_relationships(decision_text: str, context_text: str, limit: int = 4) -> List[CausalRelationship]:
    """Keyword-match relationships against the decision + context text.

    Simple substring matching, not ML -- matches the spec's "hand-coded, no Bayesian
    networks yet" bar. Returns at most `limit` relationships, most-tag-matches first,
    falling back to the first `limit` relationships if nothing matches (so scenario
    generation always has some causal grounding to work with).
    """
    haystack = re.sub(r"[^a-z0-9\s]", " ", f"{decision_text} {context_text}".lower())

    scored = []
    for rel in CAUSAL_RELATIONSHIPS:
        score = sum(1 for tag in rel.tags if tag in haystack)
        if score > 0:
            scored.append((score, rel))

    if not scored:
        return CAUSAL_RELATIONSHIPS[:limit]

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [rel for _, rel in scored[:limit]]


# --- Scale/Leverage/Luck extraction flags -----------------------------------
#
# Deliberately NOT added to CAUSAL_RELATIONSHIPS/relevant_relationships() above.
# Those 8 rules are matched by keyword/tag search against decision_text +
# context_text BEFORE the LLM call runs, so the matched relationships can be
# fed INTO that same call as grounding context. The 3 rules below are gated on
# scale_efficiency/leverage_type/market_timing_signal (BusinessStructuredIntent,
# simulator/schemas.py) and primary_priority (ScenarioSet) -- fields that don't
# exist until AFTER that same combined call returns them. There is no text to
# keyword-match against for these; forcing them into relevant_relationships()'s
# pre-call pattern would mean matching on fields that aren't populated yet.
# These are evaluated post-classification instead, against the LLM's own
# structured output, not against raw text.
#
# Kept in this file (not analysis.py) because the trigger/effect descriptive
# shape mirrors CAUSAL_RELATIONSHIPS' tone and this is still "hand-coded causal
# relationships for early-stage SaaS" -- just evaluated at a different point in
# the pipeline. NOT wired into PremortemAnalyzer or RiskAudit yet -- this is an
# extraction + causal-rule pass only, per explicit scope.
class ExtractionFlag(NamedTuple):
    trigger: str
    effect: str


def evaluate_extraction_flags(
    *,
    leverage_type: List[str],
    scale_efficiency: Optional[str],
    market_timing_signal: Optional[str],
    primary_priority: str,
) -> List[ExtractionFlag]:
    """Evaluate the 3 Scale/Leverage/Luck flags against one decision's
    already-classified signals. `primary_priority` stands in for "aggressive
    growth/entry" in the 2nd and 3rd rules below -- there is no dedicated
    aggressiveness signal, so this reuses the closest existing structured
    field rather than inventing a new one for this pass. Flagged here, not
    hidden: this is an approximation, not a precise match to "aggressive."
    """
    flags: List[ExtractionFlag] = []

    if primary_priority == "growth" and leverage_type == ["none_apparent"]:
        flags.append(
            ExtractionFlag(
                trigger="Growth-oriented decision with no identified leverage mechanism",
                effect="scaling via linear effort alone (no financial, people, technology, "
                "or media leverage) tends to hit a ceiling, since effort can't compound",
            )
        )

    if scale_efficiency == "cost_outpacing_output" and primary_priority == "growth":
        flags.append(
            ExtractionFlag(
                trigger="Cost growing faster than output in a growth-oriented decision",
                effect="burn accelerates ahead of revenue, a cost-structure risk that shows "
                "up before revenue has a chance to catch up",
            )
        )

    if market_timing_signal == "saturated" and primary_priority == "growth":
        flags.append(
            ExtractionFlag(
                trigger="Growth-oriented decision entering an already-saturated market",
                effect="timing risk: a crowded market gives incumbents room to respond "
                "competitively before this decision can establish traction",
            )
        )

    # New for this pass -- combines existing fields only, no new extraction, no
    # primary_priority gate (unlike the two rules above): cost outpacing output is
    # a risk regardless of what the founder is optimizing for, if there's no
    # leverage mechanism in place to eventually break the linear cost-to-output
    # relationship (automation, capital, a distribution channel, a team that
    # scales sublinearly with output).
    if scale_efficiency == "cost_outpacing_output" and leverage_type == ["none_apparent"]:
        flags.append(
            ExtractionFlag(
                trigger="Cost outpacing output with no identified leverage mechanism",
                effect="nothing in place to eventually decouple cost from output -- without "
                "automation, capital, or a distribution advantage, the gap compounds rather "
                "than closing on its own",
            )
        )

    # New for this pass: a favorable market can mask exactly the same absence of
    # leverage the rule above flags -- growth driven by a rising tide, not a
    # repeatable mechanism, looks fine until the tide turns. Deliberately NOT
    # gated on primary_priority: this is a risk about durability, not about what
    # the founder is currently optimizing for.
    if market_timing_signal == "rising_tide" and leverage_type == ["none_apparent"]:
        flags.append(
            ExtractionFlag(
                trigger="Favorable market timing with no identified leverage mechanism",
                effect="growth may currently look healthy on tailwinds alone -- fragile once "
                "market conditions normalize, since nothing here would keep working without them",
            )
        )

    return flags

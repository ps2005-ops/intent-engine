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
from typing import List, NamedTuple


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

"""Growth Research taxonomy (§1). Pure constants + helpers, no I/O."""
from __future__ import annotations

import re

RESEARCH_STREAM = "growth_research"

# The domains to research continuously (§1).
RESEARCH_DOMAINS = {
    "ai", "founders", "startups", "saas", "business_intelligence", "planning",
    "forecasting", "decision_making", "finance", "autonomous_ai", "agents",
    "enterprise_software", "productivity", "developer_tools", "executive_workflows",
}

# What kind of signal an observation is (§1 — "do not simply collect keywords").
RESEARCH_KINDS = {
    "topic", "pain_point", "question", "objection", "language", "community",
    "recurring_discussion",
}

# Understood intent behind the signal (not the keyword). Ordered roughly by
# funnel depth so a rising shift toward the deeper classes is itself a signal.
INTENT_CLASSES = (
    "informational",     # learning about the space
    "problem_aware",     # feels a pain, naming it
    "solution_aware",    # comparing approaches
    "evaluative",        # comparing specific tools
    "buying_trigger",    # an event that starts a purchase
)

# event types on the research stream
RESEARCH_OBSERVED = "growth_research.observed"
RESEARCH_CANDIDATE_PROPOSED = "growth_research.candidate_proposed"


def normalize_topic(text: str) -> str:
    """Stable key for 'the same topic' across wordings: lowercased, punctuation
    stripped, whitespace collapsed. Deliberately simple + deterministic."""
    t = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", t).strip()

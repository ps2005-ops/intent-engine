"""Growth Research (§1) — continuous research that produces UNDERSTOOD INTENT,
not keywords.

Ingests signals from permitted sources into typed, evidenced observations
(topics, pain points, questions, objections, terminology, communities,
recurring discussions) across the growth domains, each with an intent
classification and confidence-with-basis. Evolution is first-class: a topic
re-observed appends a new record and the trajectory (rising / steady / fading)
is a deterministic fold. Recurring, rising, well-evidenced intent EMITS a
LearningCandidate for a human to accept — the head of the autonomous loop.
"""
from intent_engine.growth_os.research.records import (  # noqa: F401
    RESEARCH_DOMAINS,
    RESEARCH_KINDS,
    INTENT_CLASSES,
    RESEARCH_STREAM,
)
from intent_engine.growth_os.research.service import (  # noqa: F401
    GrowthResearchService,
    TopicEvolution,
)

__all__ = [
    "RESEARCH_DOMAINS", "RESEARCH_KINDS", "INTENT_CLASSES", "RESEARCH_STREAM",
    "GrowthResearchService", "TopicEvolution",
]

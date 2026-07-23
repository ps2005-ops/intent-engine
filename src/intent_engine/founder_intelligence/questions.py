"""Leadership questions (T023.5) — supportive, precise, traceable.

Questions the product would ask the leadership team, each derived from a
supported claim or a named evidence gap, each traceable to its evidence.
They are supportive and precise, never generic MBA filler and never
commands.
"""
from __future__ import annotations

from intent_engine.founder_intelligence.records import (
    AVAIL_SUPPORTED, InsightCard, IntelligenceSection, SECTION_QUESTIONS,
    assert_product_language,
)

QUESTIONS_VERSION = "fi_questions.v1"


def leadership_question(*, question: str, why_surfaced: str, claim,
                        decision_it_informs: str) -> InsightCard:
    assert_product_language(question, where="leadership question")
    card = InsightCard(
        insight_id=f"{SECTION_QUESTIONS}.{claim.claim_id}",
        kind=SECTION_QUESTIONS, headline=question,
        availability=AVAIL_SUPPORTED, claims=(claim,),
        why_it_matters=why_surfaced,
        question_to_investigate=decision_it_informs)
    card.validate()
    return card


def assemble_leadership_questions(supported_claims) -> IntelligenceSection:
    """One traceable question per strong supported claim, bounded to a few.
    No generic filler."""
    templates = [
        ("Why do customers describe the outcome differently from the "
         "homepage?", "the visible customer language emphasizes a different "
         "outcome", "how the homepage frames the core value"),
        ("Where do prospective customers learn the category before they "
         "reach you?", "public signals suggest category education happens "
         "elsewhere", "where to invest in education vs. acquisition"),
        ("Which visible customer persona is intentionally deprioritized?",
         "public signals suggest more personas than the homepage addresses",
         "which audience the product focuses on next"),
    ]
    strong = [c for c in supported_claims if c.availability == AVAIL_SUPPORTED]
    cards = []
    for (q, why, decision), claim in zip(templates, strong):
        cards.append(leadership_question(question=q, why_surfaced=why,
                                         claim=claim,
                                         decision_it_informs=decision))
    section = IntelligenceSection(
        kind=SECTION_QUESTIONS, title="Questions we would ask your team",
        cards=tuple(cards),
        availability=AVAIL_SUPPORTED if cards else "UNAVAILABLE",
        note="each question is traceable to evidence; none is generic filler")
    if cards:
        section.validate()
    return section

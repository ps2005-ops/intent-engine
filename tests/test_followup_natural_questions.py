"""Follow-up questions must behave like a product, not a classifier.

An external tester asked "What does this company actually do?" and was told
"Intent: UNSUPPORTED". Asking "Explain this in simple terms" produced
"Intent: SUPPORTED" followed by an answer about pricing.
"""
import pytest

from intent_engine.founder_intelligence.conversation import (
    detect_topics,
    run_claim_set,
)


class _Claim:
    def __init__(self, claim_id, text, availability="AVAILABLE"):
        self.claim_id, self.text, self.availability = claim_id, text, availability


RUN = [
    _Claim("u.identity", "Palantir builds Gotham and Foundry data platforms."),
    _Claim("u.pricing", "Pricing model: not determinable from approved sources."),
    _Claim("u.customers", "Customer evidence: government and commercial users."),
    _Claim("mv.risk", "Disclosed risk: dependence on government contracts."),
]


# --- the two reproduced failures -----------------------------------------

def test_what_does_this_company_do_is_understood():
    """The tester's first question. Previously UNSUPPORTED."""
    assert detect_topics("What does this company actually do?")
    cs = run_claim_set("What does this company actually do?", RUN)
    assert cs.intent == "SUPPORTED"


def test_explain_simply_does_not_answer_about_pricing():
    """The tester's second failure: matched on 'explain', then returned every
    claim, leading with pricing."""
    cs = run_claim_set("Explain this in simple terms.", RUN)
    assert cs.intent == "SUPPORTED"
    assert "summary" in detect_topics("Explain this in simple terms.")[:1]


# --- natural phrasings ----------------------------------------------------

@pytest.mark.parametrize("q", [
    "What does this company actually do?",
    "Who are its customers?",
    "What are the biggest risks?",
    "What products does it sell?",
    "What changed recently?",
    "Summarize the report.",
    "Make this easier to understand.",
    "Why is this important?",
    "What evidence supports this?",
    "What should leadership investigate?",
    "Why was this report limited?",
    "How confident are you?",
    "Who are the competitors?",
])
def test_normal_questions_are_recognised(q):
    assert detect_topics(q), f"not recognised: {q!r}"
    assert run_claim_set(q, RUN).intent != "UNRECOGNISED"


# --- relevance ------------------------------------------------------------

def test_a_topical_question_does_not_return_unrelated_claims():
    cs = run_claim_set("What are the biggest risks?", RUN)
    ids = [c.claim_id for c in cs.claims]
    assert "u.pricing" not in ids, "risk question must not answer with pricing"


def test_topic_with_no_evidence_says_so_rather_than_substituting():
    sparse = [_Claim("u.identity", "Acme makes widgets.")]
    cs = run_claim_set("Who are its customers?", sparse)
    assert cs.intent == "INSUFFICIENT"
    assert "customers" in cs.claims[0].text


# --- never expose internals ----------------------------------------------

def test_unrecognised_question_gets_help_not_jargon():
    cs = run_claim_set("purple monkey dishwasher", RUN)
    assert cs.intent == "UNRECOGNISED"
    text = cs.claims[0].text
    assert "UNSUPPORTED" not in text
    assert "intent" not in text.lower()
    assert "What does this company do?" in text     # suggests real questions


def test_no_claim_text_leaks_classifier_vocabulary():
    for q in ("What does this company do?", "asdfgh", "What are the risks?"):
        for c in run_claim_set(q, RUN).claims:
            for banned in ("UNSUPPORTED", "classifier", "enum", "intent="):
                assert banned not in (c.text or "")

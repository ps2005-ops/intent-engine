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


# --- the full natural range (P8) -------------------------------------------
import pytest as _pytest

from intent_engine.founder_intelligence.conversation import (
    _SUBJECT_LABEL, _TOPICS, detect_topics, is_referential, referenced_ordinal,
)


@_pytest.mark.parametrize("question,expected", [
    ("What does this company do?", "identity"),
    ("Explain this simply", "summary"),
    ("What is the main finding?", "thesis"),
    ("Why does this matter?", "implication"),
    ("What changed recently?", "recent_change"),
    ("What products do they sell?", "products"),
    ("Who are the customers?", "customers"),
    ("What does the market look like?", "market"),
    ("What are the risks?", "risks"),
    ("What opportunities are there?", "opportunity"),
    ("How confident are you?", "confidence"),
    ("What is the strongest evidence?", "strongest_evidence"),
    ("What evidence weakens this?", "weakest_evidence"),
    ("What are you least confident about?", "weakest_evidence"),
    ("What would change the conclusion?", "falsification"),
    ("What are the limitations?", "limitation"),
    ("What should I ask leadership?", "leadership"),
    ("What should I monitor?", "monitoring"),
    ("What does outside-in mean?", "definition"),
    ("Compare these two findings", "comparison"),
    ("Which conclusion is most likely wrong?", "weakest_evidence"),
])
def test_every_promised_question_kind_is_recognised(question, expected):
    assert expected in detect_topics(question), \
        f"{question!r} -> {detect_topics(question)}"


@_pytest.mark.parametrize("question", [
    "Why?", "Explain that.", "What weakens it?", "Say that without jargon.",
    "Why should I care?", "Which one is most important?", "Tell me more",
])
def test_conversational_references_are_recognised_as_such(question):
    assert is_referential(question), question


def test_a_bare_why_inherits_the_previous_subject():
    assert "risks" in detect_topics("Why?", previous_topics=("risks",))


def test_a_bare_why_with_no_previous_turn_has_no_subject_to_borrow():
    """Inventing one would be worse than saying so."""
    assert detect_topics("Why?") == ()


def test_a_question_with_its_own_subject_does_not_borrow_one():
    topics = detect_topics("What are the risks?", previous_topics=("products",))
    assert "risks" in topics
    assert "products" not in topics


def test_standalone_referential_phrases_work_without_context():
    assert detect_topics("Why should I care?") == ("implication",)
    assert "summary" in detect_topics("Say that without jargon.")


def test_ordinal_references_are_understood():
    assert referenced_ordinal("What about the second point?") == 2
    assert referenced_ordinal("Explain the first one") == 1
    assert referenced_ordinal("What are the risks?") is None


def test_every_topic_has_a_reader_facing_label():
    """The classifier's vocabulary stays inside the classifier."""
    for topic in _TOPICS:
        assert topic in _SUBJECT_LABEL, f"{topic} has no reader-facing label"
        assert "_" not in _SUBJECT_LABEL[topic]


def test_no_internal_name_can_reach_a_reader_through_the_no_evidence_path():
    sparse = [_Claim("u.identity", "Acme makes widgets.")]
    for question in ("What should I monitor?",
                     "What evidence weakens this?",
                     "What changed recently?"):
        cs = run_claim_set(question, sparse)
        text = " ".join(c.text for c in cs.claims)
        # Only names that are NOT ordinary English. "evidence" is both a topic
        # id and a word a sentence may legitimately use; "recent_change" and
        # "weakest_evidence" can only have come from the classifier.
        for internal in (t for t in _TOPICS if "_" in t):
            assert internal not in text, f"leaked {internal} for {question!r}"
        assert "topic" not in text.lower()

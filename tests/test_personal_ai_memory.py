"""A recommendation is not a decision, a decision is not an act.

THE SENTENCE THIS EXISTS TO PREVENT. The engine recommends expanding, the
founder chooses to hold, nothing is executed, and demand later rises anyway.
A system that stores one "decision" field summarises that as:

    "We expanded and it worked."

Every clause is false. These tests pin the five stages apart -- recommendation,
human decision, action, outcome, learning -- and pin that an ABSENT stage is
reported absent rather than inferred from the stage before it.
"""
import pytest

from intent_engine.executive import personal_ai as PA
from intent_engine.executive.living_decision import (LivingDecisionRecord,
                                                     Retrospective)


def _record(**kw):
    base = dict(decision_id="d1", company_id="cloudflare",
                decision_question="What should we charge?",
                recommendation="expand into the mid-market")
    base.update(kw)
    return LivingDecisionRecord(**base)


# --- the five stages stay apart --------------------------------------------

def test_a_recommendation_is_not_a_decision():
    record = _record()                       # status defaults to OPEN
    out = PA.answer("What did we decide?", record=record)
    assert out.supported is False
    assert out.information_gap == PA.NO_DECISION_RECORDED
    assert "recommendation, not a decision" in out.answer


def test_a_decision_is_not_an_action():
    """The founder chose. Nobody did anything. Those are different facts."""
    record = _record(status="HUMAN_DECIDED", decided_by="founder@example.com")
    decided = PA.answer("What did we decide?", record=record)
    assert decided.supported is True
    assert "founder@example.com" in decided.answer

    acted = PA.answer("What did we actually do?", record=record)
    assert acted.supported is False
    assert acted.information_gap == PA.NO_ACTION_RECORDED
    assert "no action" in acted.answer.lower()
    # and it must say the decision exists, so the reader is not told the
    # whole thing is empty
    assert "decision was recorded" in acted.answer


def test_approving_an_action_is_not_doing_it():
    """ACTION_APPROVED is the last thing before acting. Reporting it as
    "what we did" is the same collapse one stage further on."""
    record = _record(status="ACTION_APPROVED", decided_by="f@example.com")
    out = PA.answer("What did we actually do?", record=record)
    assert out.supported is False
    assert out.information_gap == PA.NO_ACTION_RECORDED


def test_an_action_is_not_an_outcome():
    record = _record(status="EXECUTING", decided_by="founder@example.com",
                     action_status="EXECUTED")
    acted = PA.answer("What did we actually do?", record=record)
    assert acted.supported is True

    worked = PA.answer("Did it work?", record=record)
    assert worked.supported is False
    assert worked.information_gap == PA.NO_OUTCOME_RECORDED


def test_an_outcome_is_not_a_lesson():
    """An outcome that cannot be attributed to the decision teaches nothing.
    `Retrospective.learnable` is the record's own discipline; this asserts
    the reader honours it instead of announcing a lesson."""
    record = _record(status="AWAITING_OUTCOME", decided_by="f@example.com",
                     action_status="EXECUTED", outcome_refs=("obs-1",))
    learned = PA.answer("What did we learn?", record=record)
    assert learned.supported is False
    assert learned.information_gap == PA.NO_LEARNING_RECORDED


def test_the_false_summary_is_not_producible():
    """The whole scenario: recommended expand, chose hold, did nothing,
    demand rose. No answer may say we expanded, and none may say it worked.
    """
    record = _record(status="HUMAN_DECIDED", decided_by="founder@example.com",
                     recommendation="hold at current capacity")
    answers = {PA.classify(q): PA.answer(q, record=record)
               for q in PA.MEMORY_QUESTIONS}

    # ASSERTED STRUCTURALLY, not by string matching. A first version checked
    # that the phrase "it worked" was absent -- and the honest answer
    # "whether IT WORKED is not something this record can answer" contains
    # it while denying it. A substring cannot tell an assertion from its
    # denial, so the invariant is the support flag: no stage after the human
    # decision may be reported as established.
    assert answers[PA.WHAT_WE_DECIDED].supported is True
    for stage in (PA.WHAT_WE_DID, PA.WHAT_HAPPENED, PA.WHAT_WE_LEARNED):
        assert answers[stage].supported is False, stage
    assert answers[PA.WHAT_WE_DID].information_gap == PA.NO_ACTION_RECORDED
    # and the decision that IS on the record is reported as itself, not as
    # the recommendation the engine originally made
    assert "hold at current capacity" in answers[PA.WHAT_WE_DECIDED].answer


# --- absence is a state, never an inference --------------------------------

def test_no_record_is_distinguished_from_an_empty_record():
    out = PA.answer("What did we decide?", record=None)
    assert out.supported is False
    assert out.information_gap == PA.NO_DECISION_RECORDED
    assert "no decision has been recorded" in out.answer.lower()


def test_did_it_work_notes_there_was_nothing_to_judge():
    """With no action, "did it work" is not merely unanswered -- the reader
    should know there is nothing whose result could be judged."""
    record = _record(status="HUMAN_DECIDED", decided_by="f@example.com")
    out = PA.answer("Did it work?", record=record)
    assert "no action was recorded" in out.answer.lower()


# --- routing ---------------------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("What did we decide?", PA.WHAT_WE_DECIDED),
    ("what was the decision", PA.WHAT_WE_DECIDED),
    ("What did we actually do?", PA.WHAT_WE_DID),
    ("did we do anything", PA.WHAT_WE_DID),
    ("Did it work?", PA.WHAT_HAPPENED),
    ("what happened afterwards", PA.WHAT_HAPPENED),
    ("What did we learn?", PA.WHAT_WE_LEARNED),
    ("What are we waiting to learn?", PA.AWAITING),
])
def test_memory_questions_are_classified(question, expected):
    assert PA.classify(question) == expected


@pytest.mark.parametrize("question", [
    "What do you recommend?", "What is the biggest risk?",
    "Show me the source.", "What could a competitor do?",
])
def test_present_tense_questions_are_delegated(question):
    """Not this module's job. One answerer per kind of question."""
    assert PA.classify(question) == PA.DELEGATED


def test_a_delegated_question_still_gets_an_answer():
    """A caller may send every question here; routing is internal."""
    out = PA.answer("What do you recommend?", record=_record(), decision=None)
    assert out.answer                       # ceo_questions answered it


def test_what_did_we_actually_do_beats_what_did_we_decide():
    """Pattern order matters: the more specific question contains the more
    general one, and matching the wrong one answers about the wrong stage."""
    assert PA.classify("What did we actually do?") == PA.WHAT_WE_DID


# --- awaiting --------------------------------------------------------------

def test_awaiting_reports_open_expectations_and_gaps():
    record = _record(preregistered_expectations=("renewal rate holds",),
                     information_gaps=("no competitor pricing on file",))
    out = PA.answer("What are we waiting to learn?", record=record)
    assert out.supported is True
    assert "expectation" in out.answer and "gap" in out.answer


def test_awaiting_says_so_when_nothing_is_open():
    out = PA.answer("What are we waiting to learn?", record=_record())
    assert out.supported is False
    assert "nothing is on the record as awaited" in out.answer.lower()

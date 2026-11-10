"""Sixteen seconds is not an evidence problem.

MEASURED ACROSS A TEN-COMPANY MATRIX. Three to five of every six executive
questions came back "There is not enough public evidence to answer that
confidently" -- on runs with thirteen documents, all three evidence roles
filled, and a fifty-thousand-character report already published. The identical
questions, asked sixteen seconds later, were answered.

The cause is not the gate. `brief.key_insight` is None between the moment CORE
opens the result and the moment the deeper reading merges into it, and Q&A
read that None as a verdict about the COMPANY. A reader is told their company
lacks public evidence because they clicked early.

The honest refusal is kept for the case it was written for -- a review that
finished and still found nothing. What changes is that a page which has not
finished says so.
"""
import inspect

from intent_engine.founder_brief import qa as Q

STRATEGIC = "What should we do about this?"
STILL_RUNNING = "still running"
THE_OLD_VERDICT = "the public evidence does not support one"


class _Brief:
    """Permissive except where this test is precise: `key_insight` is None,
    which is the whole condition under examination."""
    key_insight = None
    limitations = ()
    confidence = "moderate"

    def __getattr__(self, name):
        return ""


def test_a_review_still_running_is_not_a_verdict_about_the_company():
    out = Q.answer(STRATEGIC, _Brief(), deep_pending=True)
    said = out.direct_answer.lower()
    assert STILL_RUNNING in said, out.direct_answer
    assert THE_OLD_VERDICT not in said, (
        "a reader who clicked early was told their company lacks evidence")
    assert out.so_what, "the reader is not told what IS answerable now"


def test_a_finished_review_that_found_nothing_still_says_so():
    """THE NEGATIVE CONTROL. This repair must not delete the refusal; an
    evidence-limited company is a real outcome and abstention is a PASS."""
    out = Q.answer(STRATEGIC, _Brief(), deep_pending=False)
    said = out.direct_answer.lower()
    assert THE_OLD_VERDICT in said, out.direct_answer
    assert STILL_RUNNING not in said


def test_a_question_matching_no_intent_gets_the_same_truthful_reason():
    """The catch-all fallback carried the same sentence, one branch over --
    which is exactly how the first repair of this family shipped incomplete."""
    obscure = "How many distribution centres are in Ohio?"
    pending = Q.answer(obscure, _Brief(), deep_pending=True).direct_answer
    finished = Q.answer(obscure, _Brief(), deep_pending=False).direct_answer
    assert STILL_RUNNING in pending.lower(), pending
    assert "not enough public evidence" in finished.lower(), finished


def test_the_webapp_tells_it_which_state_the_run_is_in():
    """A parameter defaulting to False is inert until a caller sets it, and
    an inert repair is this project's most repeated failure."""
    from intent_engine.webapp.app import WebApp
    src = inspect.getsource(WebApp._converse)
    assert "deep_pending=" in src, (
        "the only caller never tells Q&A whether the reading has landed")
    marker = src.index("deep_pending=")
    assert "deep_status" in src[marker:marker + 200], (
        "deep_pending is set from something other than the run's deep status")

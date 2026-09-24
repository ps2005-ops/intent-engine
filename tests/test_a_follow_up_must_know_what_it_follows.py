"""'Why does that matter?' answered a different question, twice.

MEASURED LIVE on 4908ad99, through the deployed product, after five prior
questions in the same session on the same run:

    Synopsys  Q6 -> question ONE's refusal, verbatim
    Emerson   Q6 -> question TWO's answer, verbatim

Neither referred to anything. The cause was not the intent router: a question
whose only subject is "that" carries no topic, so it fell to whichever intent
happened to share a word with it and returned that intent's answer again.

THE MECHANISM EXISTED AND COULD NOT RUN. `_conversation_context` has been
declared on the webapp since the second Q&A engine was removed as
unreachable, and NOTHING HAS EVER WRITTEN TO IT -- the only writer was inside
the dead block. `founder_intelligence.service.converse` still documents
`previous_topics` as "the last turn's subject, so 'Why?' and 'Explain that'
resolve", on the engine that was deleted. The surviving engine had no such
parameter at all.
"""
from __future__ import annotations

import inspect

from intent_engine.founder_brief import qa as Q

PRIOR = {
    "question": "What is the most important strategic implication?",
    "direct_answer": "Emerson is committing capital to capacity ahead of "
                     "uncertain demand.",
    "so_what": "It concentrates the outcome in a small number of buyers' "
               "product cycles, which the company does not control.",
    "decision_affected": "How much capacity to commit, and when.",
    "what_could_change": "A published order book would settle it.",
    "confidence": "low",
}


class _Brief:
    key_insight = None
    limitations = ()
    confidence = "moderate"

    def __getattr__(self, name):
        return ""


# --- what counts as a follow-up ------------------------------------------

def test_a_bare_back_reference_is_a_follow_up():
    for q in ("Why does that matter most for this company specifically?",
              "Why does this matter?", "Can you expand on that?",
              "What do you mean by it?"):
        assert Q.is_follow_up(q, (PRIOR,)), q


def test_a_question_that_names_its_own_topic_is_not():
    """NEGATIVE CONTROL, and the one that keeps this from swallowing the
    router: a question with a real intent must keep going to it, however many
    pronouns it happens to contain."""
    for q in ("What evidence supports that?",
              "What should management monitor next?",
              "What would make this recommendation wrong?"):
        assert not Q.is_follow_up(q, (PRIOR,)), q


def test_the_first_question_of_a_session_is_never_a_follow_up():
    assert not Q.is_follow_up("Why does that matter?", ())


# --- what a follow-up answers with ---------------------------------------

def test_the_answer_is_built_out_of_the_turn_it_refers_to():
    out = Q.answer("Why does that matter most for this company specifically?",
                   _Brief(), previous=(PRIOR,))
    assert out.follows == PRIOR["question"]
    assert PRIOR["so_what"] in out.direct_answer, out.direct_answer
    assert "capacity ahead of uncertain demand" in out.direct_answer, (
        "the answer does not say what it resolved 'that' to")
    assert out.decision_affected == PRIOR["decision_affected"]


def test_the_follow_up_does_not_repeat_the_previous_answer():
    """THE DEFECT, STATED AS A PROPERTY. Returning the prior answer verbatim
    is what was measured live, and it is what must not happen."""
    out = Q.answer("Why does that matter?", _Brief(), previous=(PRIOR,))
    assert out.direct_answer.strip() != PRIOR["direct_answer"].strip()


def test_a_previous_turn_that_established_nothing_says_so():
    """A follow-up to a refusal may not invent a reason. It reports that the
    previous turn had nothing to build on."""
    empty = {"question": "What is the implication?", "direct_answer": "",
             "so_what": "", "decision_affected": ""}
    out = Q.answer("Why does that matter?", _Brief(), previous=(empty,))
    assert "established nothing" in out.direct_answer.lower()


def test_resolution_happens_before_routing():
    """The router matched a shared word and returned that intent's answer
    again; the follow-up branch has to run first or the defect returns."""
    src = inspect.getsource(Q.answer)
    assert src.index("is_follow_up(") < src.index("_route_answer("), (
        "a back-reference is being routed before it is resolved")


# --- and the live call site actually carries the turns -------------------

def test_the_webapp_reads_passes_and_writes_the_history():
    """A parameter with no caller is inert, and this codebase has shipped
    that exact shape before -- including for this very field."""
    from intent_engine.webapp.app import WebApp
    src = inspect.getsource(WebApp._converse)
    assert "_conversation_context" in src, (
        "the history store still has no reader on the live path")
    assert "previous=_history" in src, (
        "the turns are read and then not passed to the answerer")
    assert "self._conversation_context[_hist_key] =" in src, (
        "the history is never written, which is the original defect")
    read = src.index("_conversation_context.get")
    write = src.index("self._conversation_context[_hist_key] =")
    assert read < write, "the turn is stored before it is used as history"


def test_history_is_keyed_by_reader_as_well_as_run():
    """A key that ignores the reader is one redeploy away from showing
    somebody else's questions."""
    from intent_engine.webapp.app import WebApp
    src = inspect.getsource(WebApp._converse)
    assert 'session.get("user_id")' in src[src.index("_hist_key"):
                                           src.index("_hist_key") + 200]

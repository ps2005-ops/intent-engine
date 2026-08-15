"""The executive's memory of one company's decision, and what came of it.

WHY THIS IS SEPARATE FROM `ceo_questions`
-----------------------------------------
`ceo_questions` projects ONE `FounderDecision`: what the engine concludes
now, from the published record. Every question it answers is present tense.

The questions an executive actually returns with a week later are not:

    What did we decide?
    What did we actually do?
    Did it work?
    What did we learn?

None of those are answerable from a FounderDecision, because none of them is
about the engine's conclusion. They are about what a HUMAN chose, whether the
company then did anything, and what happened. That history lives in
`LivingDecisionRecord`, which already models it -- so this module is a
projection of canonical state, not a second memory.

THE FIVE THINGS THAT MUST NOT COLLAPSE
--------------------------------------
    RECOMMENDATION   what the engine concluded
    HUMAN DECISION   what a person chose, and who
    ACTION           what the company then did
    OUTCOME          what happened afterwards
    LEARNING         what that taught us

The failure this module exists to prevent is the fluent summary:

    "We expanded and it worked."

when the record says the engine recommended expanding, the founder chose to
hold, nothing was executed, and demand later rose anyway. Every clause of
that sentence is false, and it is exactly what a system that stores one
"decision" field produces.

`LivingDecisionRecord` already refuses to conflate them -- a DECIDED record
without `decided_by` raises, because a recommendation is not a decision. This
module inherits that discipline and adds the one rule a reader can violate:
an ABSENT stage is reported as absent. There is no inference from
recommendation to action, or from action to outcome.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

from intent_engine.executive.ceo_questions import Answer

CONTRACT = "personal_ai.v1"

# --- the memory question classes -------------------------------------------

WHAT_WE_DECIDED = "WHAT_WE_DECIDED"
WHAT_WE_DID = "WHAT_WE_DID"
WHAT_HAPPENED = "WHAT_HAPPENED"
WHAT_WE_LEARNED = "WHAT_WE_LEARNED"
AWAITING = "AWAITING"
DELEGATED = "DELEGATED"

#: Ordered: the first pattern that matches wins, so the more specific
#: question is listed above the more general one it contains. "what did we
#: actually do" contains "what did we", which is why it is first.
_PATTERNS = (
    (WHAT_WE_DID, r"\b(what did we (actually )?do|did we (do )?anything|"
                  r"what action|was (it|anything) (done|executed)|"
                  r"did we act)\b"),
    (WHAT_HAPPENED, r"\b(did it work|what happened( afterwards?| next| "
                    r"since)?|how did it turn out|was it right)\b"),
    (WHAT_WE_LEARNED, r"\b(what did (we|you) learn|what have (we|you) "
                      r"learned|what did that teach)\b"),
    (AWAITING, r"\b(what are we waiting (to learn|for)|what are you waiting|"
               r"what (still )?needs to (happen|be observed))\b"),
    (WHAT_WE_DECIDED, r"\b(what did we decide|what was (the )?decision|"
                      r"what (did|have) (we|you) (chosen|choose|decided)|"
                      r"who decided)\b"),
)

#: What the record says when nothing was recorded. These are STATES, not
#: apologies: "no action was recorded" is a fact about the record and the
#: only honest answer. Inventing an action here is the defect.
NO_DECISION_RECORDED = "NO_DECISION_RECORDED"
NO_ACTION_RECORDED = "NO_ACTION_RECORDED"
NO_OUTCOME_RECORDED = "NO_OUTCOME_RECORDED"
NO_LEARNING_RECORDED = "NO_LEARNING_RECORDED"

#: WITH NO RECORD AT ALL, EACH QUESTION STILL HAS ITS OWN ANSWER.
#:
#: The state is the same for all five -- nothing is recorded -- but the
#: questions are not, and answering them with one shared paragraph spends a
#: whole screen repeating a single sentence. That is the duplicated-caveat
#: failure: it reads as a broken page rather than an empty history, and it
#: buries the one thing the reader does need to know, which is that the
#: reading on the page is the engine's and nobody has acted on it.
#:
#: These say strictly what an absent record supports and nothing more. The
#: chain is the point: with no decision there can have been no action, with
#: no action there is no result to judge, and with no result there is no
#: lesson. Each answer states its own stage and names the missing stage
#: BEFORE it -- which is a fact about the record, not an inference about
#: the company.
_NO_RECORD = {
    WHAT_WE_DECIDED: (
        "No decision has been recorded for this company. The reading on "
        "this page is the engine's recommendation; no person has chosen "
        "it, and a recommendation nobody has accepted is not a decision.",
        NO_DECISION_RECORDED),
    WHAT_WE_DID: (
        "No action has been recorded. Nothing has been decided either, so "
        "there is nothing on file that could have been carried out.",
        NO_ACTION_RECORDED),
    WHAT_HAPPENED: (
        "No outcome has been recorded, so whether it worked is not "
        "something this record can answer. Nothing was decided or done "
        "here, so there is nothing yet whose result could be judged.",
        NO_OUTCOME_RECORDED),
    WHAT_WE_LEARNED: (
        "Nothing has been learned from this company's decision history, "
        "because there is no history yet. A lesson needs an outcome to "
        "compare against what was expected, and neither is on the record.",
        NO_LEARNING_RECORDED),
    AWAITING: (
        "Nothing is on the record as awaited. Expectations are registered "
        "when a decision is taken, and no decision has been recorded here, "
        "so there is nothing outstanding to reconcile.",
        NO_DECISION_RECORDED),
}


def classify(question: str) -> str:
    """Which memory question this is, or DELEGATED.

    DELEGATED means "not a memory question" -- it belongs to
    `ceo_questions`, which projects the current decision. Routing rather
    than answering keeps one answerer per kind of question.
    """
    text = str(question or "").strip().lower()
    if not text:
        return DELEGATED
    for name, pattern in _PATTERNS:
        if re.search(pattern, text):
            return name
    return DELEGATED


def _states(record) -> dict:
    """The five stages of one decision, each present or explicitly absent.

    Read from the record's own fields rather than derived from each other.
    A stage is absent when the record does not carry it, and no later stage
    may be inferred from an earlier one.
    """
    if record is None:
        return {"recommendation": "", "decided": False, "decided_by": "",
                "acted": False, "action_status": "", "outcome": False,
                "learned": False, "learning": ""}
    recommendation = str(getattr(record, "recommendation", "") or "")
    # DECIDED is the record's own status discipline: a record that is
    # recommendation-only has no human decision, whatever else it carries.
    decided = not bool(getattr(record, "is_recommendation_only", True))
    decided_by = str(getattr(record, "decided_by", "") or "")
    # WHAT THE PERSON CHOSE, WHICH THE ENGINE'S RECOMMENDATION IS NOT.
    # Read as its own field so that a founder who overruled the engine is
    # reported as having overruled it, rather than as having been advised
    # to do what they in fact chose against.
    human_choice = str(getattr(record, "human_choice", "") or "")
    followed = getattr(record, "followed_recommendation", None)
    action_status = str(getattr(record, "action_status", "") or "")
    execution = tuple(getattr(record, "execution_refs", ()) or ())
    status = str(getattr(record, "status", "") or "").upper()
    # ACTION IS NOT INFERRED FROM THE DECISION. A founder who chose to
    # expand has not expanded; the company may never have executed. Only an
    # execution reference or a status that means work started is evidence.
    #
    # ACTION_APPROVED IS DELIBERATELY NOT IN THIS SET. Approving an action
    # is the last thing that happens before doing it, and reporting an
    # approval as "what we did" is the same collapse one stage further on.
    acted = bool(execution) or status in ("EXECUTING", "AWAITING_OUTCOME",
                                          "RESOLVED") or \
        action_status.upper() in ("EXECUTED", "IN_PROGRESS",
                                  "PARTIALLY_EXECUTED", "COMPLETE")
    outcome_refs = tuple(getattr(record, "outcome_refs", ()) or ())
    retro = getattr(record, "retrospective", None)
    outcome = bool(outcome_refs) or retro is not None
    learned = bool(retro is not None and getattr(retro, "learnable", False))
    learning = ""
    if retro is not None:
        learning = str(getattr(retro, "lesson", "") or
                       getattr(retro, "summary", "") or "")
    return {"recommendation": recommendation, "decided": decided,
            "decided_by": decided_by, "human_choice": human_choice,
            "followed": followed, "acted": acted,
            "action_status": action_status, "outcome": outcome,
            "learned": learned, "learning": learning}


def _provenance(record) -> Tuple[str, ...]:
    if record is None:
        return ()
    out = []
    if getattr(record, "decision_id", ""):
        out.append(f"living decision {record.decision_id}")
    if getattr(record, "revision", 0):
        out.append(f"revision {record.revision}")
    if getattr(record, "updated_at", ""):
        out.append(f"last updated {record.updated_at}")
    return tuple(out)


def answer(question: str, *, record=None, decision: Any = None,
           prior: Optional[Any] = None) -> Answer:
    """Answer one question about this company's decision history.

    A question that is not about history is DELEGATED to `ceo_questions`,
    so a caller can send every question here and get one answerer's
    discipline over both.
    """
    cls = classify(question)
    if cls == DELEGATED:
        from intent_engine.executive import ceo_questions as _Q
        return _Q.answer(question, decision, prior)

    state = _states(record)
    prov = _provenance(record)

    if record is None:
        # No record at all is a different state from a record with nothing
        # in it, and the reader is told which -- per question, because five
        # questions answered with one paragraph is a page that looks broken.
        text, gap = _NO_RECORD[cls]
        return Answer(question, cls, text,
                      supported=False, information_gap=gap)

    if cls == WHAT_WE_DECIDED:
        if not state["decided"]:
            return Answer(
                question, cls,
                (f"Nobody has decided yet. The engine's recommendation is: "
                 f"{state['recommendation']}. That is a recommendation, not "
                 f"a decision -- no person has chosen it."
                 if state["recommendation"] else
                 "Nobody has decided yet, and no recommendation is on the "
                 "record either."),
                supported=False, standing=getattr(record, "standing", ""),
                provenance=prov, information_gap=NO_DECISION_RECORDED)
        who = state["decided_by"] or "an unnamed owner"
        # The choice, if one was recorded as distinct from the engine's
        # advice; otherwise the recommendation the person accepted.
        what = state["human_choice"] or state["recommendation"] or (
            "the decision is recorded without a stated recommendation")
        # WHETHER THE ENGINE WAS FOLLOWED IS PART OF THE ANSWER. A record
        # that says only "they decided X" hides the more useful fact that X
        # was not what the engine advised -- and that is precisely the case
        # a reader coming back later needs to see.
        note = ""
        if state["followed"] is False and state["recommendation"]:
            note = (f" That went against the engine's recommendation, which "
                    f"was: {state['recommendation']}.")
        elif state["followed"] is True and not state["human_choice"]:
            note = " That was the engine's recommendation, accepted as it stood."
        return Answer(question, cls, f"{who} decided: {what}.{note}",
                      standing=getattr(record, "standing", ""),
                      provenance=prov)

    if cls == WHAT_WE_DID:
        if not state["acted"]:
            # THE SENTENCE THIS MODULE EXISTS FOR. A decision is not an act.
            decided_note = (
                " A decision was recorded, but nothing on file shows it was "
                "carried out." if state["decided"] else
                " Nothing has been decided either.")
            return Answer(
                question, cls,
                f"No action has been recorded.{decided_note}",
                supported=False, provenance=prov,
                information_gap=NO_ACTION_RECORDED)
        return Answer(
            question, cls,
            f"Recorded action: {state['action_status'] or 'executed'}.",
            provenance=prov)

    if cls == WHAT_HAPPENED:
        if not state["outcome"]:
            return Answer(
                question, cls,
                ("No outcome has been recorded, so whether it worked is not "
                 "something this record can answer." +
                 ("" if state["acted"] else
                  " Note that no action was recorded either, so there is "
                  "nothing yet whose result could be judged.")),
                supported=False, provenance=prov,
                information_gap=NO_OUTCOME_RECORDED)
        retro = getattr(record, "retrospective", None)
        return Answer(
            question, cls,
            (f"An outcome is on the record. {state['learning']}"
             if state["learning"] else
             "An outcome is on the record, without a stated reading of it."),
            supported=True, provenance=prov + (
                ("retrospective recorded",) if retro is not None else ()))

    if cls == WHAT_WE_LEARNED:
        if not state["learned"]:
            return Answer(
                question, cls,
                ("Nothing has been learned from this decision yet. A lesson "
                 "requires an outcome to compare against what was expected, "
                 "and " +
                 ("no outcome has been recorded." if not state["outcome"]
                  else "the outcome on file does not support a lesson: it "
                       "cannot be attributed to the decision.")),
                supported=False, provenance=prov,
                information_gap=NO_LEARNING_RECORDED)
        return Answer(question, cls, state["learning"], provenance=prov)

    if cls == AWAITING:
        gaps = tuple(getattr(record, "information_gaps", ()) or ())
        expectations = tuple(
            getattr(record, "preregistered_expectations", ()) or ())
        if not gaps and not expectations:
            return Answer(
                question, cls,
                "Nothing is on the record as awaited: no information gap and "
                "no preregistered expectation is open for this decision.",
                supported=False, provenance=prov)
        parts = []
        if expectations:
            parts.append(f"{len(expectations)} preregistered expectation(s) "
                         f"are waiting to be reconciled")
        if gaps:
            parts.append(f"{len(gaps)} information gap(s) remain open")
        return Answer(question, cls, "; ".join(parts) + ".",
                      provenance=prov)

    return Answer(question, DELEGATED, "", supported=False)


#: The questions a returning executive asks that the present-tense answerer
#: cannot answer. Kept here so a surface renders the set rather than
#: inventing its own list.
MEMORY_QUESTIONS = (
    "What did we decide?",
    "What did we actually do?",
    "Did it work?",
    "What did we learn?",
    "What are we waiting to learn?",
)

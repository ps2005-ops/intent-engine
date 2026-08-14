"""The CEO's questions, answered from the FounderDecision and nothing else.

WHY THIS DOES NOT RE-READ THE EVIDENCE
--------------------------------------
`external_intel.ceo_answers` already answers questions deterministically from
a dossier, and it is kept. What it cannot do is guarantee that the answer to
"what do you recommend" is the SAME recommendation the X-Ray screen shows,
because the two derive it separately. Two derivations of one strategy is how
a product ends up telling a founder one thing on a page and another in a
chat.

So every answer here is a PROJECTION of `FounderDecision`. This module reads
fields; it does not weigh evidence, and it has no access to anything that
would let it. If a field is empty the answer says so.

THE UNSUPPORTED ANSWER IS A FEATURE
-----------------------------------
An unrecognised question returns `UNSUPPORTED_QUESTION` and names what can be
asked. It never nearest-matches: answering "what is our runway" with the
closest available topic is how a decision-support tool becomes a liability.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

from intent_engine.executive import decision_synthesis as DS

CONTRACT = "ceo_questions.v1"

RECOMMEND = "RECOMMEND"
WHY = "WHY"
STRONGEST_EVIDENCE = "STRONGEST_EVIDENCE"
CONTRADICTS = "CONTRADICTS"
WHAT_CHANGED = "WHAT_CHANGED"
CHANGED_YOUR_MIND = "CHANGED_YOUR_MIND"
WOULD_CHANGE_YOUR_MIND = "WOULD_CHANGE_YOUR_MIND"
ALTERNATIVES = "ALTERNATIVES"
BIGGEST_RISK = "BIGGEST_RISK"
COMPETITOR = "COMPETITOR"
CANNOT_MEASURE = "CANNOT_MEASURE"
WHAT_TO_TEST = "WHAT_TO_TEST"
WHAT_TO_MONITOR = "WHAT_TO_MONITOR"
DECIDED_BEFORE = "DECIDED_BEFORE"
SHOW_SOURCE = "SHOW_SOURCE"
UNSUPPORTED = "UNSUPPORTED_QUESTION"

CLASSES = (RECOMMEND, WHY, STRONGEST_EVIDENCE, CONTRADICTS, WHAT_CHANGED,
           CHANGED_YOUR_MIND, WOULD_CHANGE_YOUR_MIND, ALTERNATIVES,
           BIGGEST_RISK, COMPETITOR, CANNOT_MEASURE, WHAT_TO_TEST,
           WHAT_TO_MONITOR, DECIDED_BEFORE, SHOW_SOURCE)

# ORDER MATTERS. "what changed your mind" must not be caught by the plainer
# "what changed", and "what would change your mind" must not be caught by
# either -- they are three different questions with three different sources,
# and only the middle one may be answered from a recorded transition.
_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (WOULD_CHANGE_YOUR_MIND,
     r"\bwhat\s+would\s+change\s+(your|our|the)\s+mind|"
     r"\bwhat\s+would\s+(change|falsify|disprove|overturn)\b"),
    (CHANGED_YOUR_MIND,
     r"\bwhat\s+changed\s+(your|our|the)\s+mind|"
     r"\bwhy\s+did\s+(you|we)\s+change\b"),
    (WHAT_CHANGED, r"\bwhat(?:'s| is| has)?\s+changed\b|\bwhat\s+is\s+new\b"),
    (RECOMMEND, r"\brecommend|\bwhat\s+should\s+we\s+do\b|\byour\s+advice\b"),
    (STRONGEST_EVIDENCE,
     r"\bstrongest\s+evidence|\bbest\s+evidence|\bwhat\s+supports\b|"
     r"\bwhat\s+is\s+the\s+evidence\b"),
    (CONTRADICTS, r"\bcontradict|\bagainst\s+(this|it)\b|\bdisagree"),
    (ALTERNATIVES, r"\balternativ|\bother\s+option|\bwhat\s+else\s+could\b"),
    (BIGGEST_RISK, r"\brisk\b|\bwhat\s+could\s+go\s+wrong\b|\bdownside\b"),
    (COMPETITOR, r"\bcompetitor|\brival|\bwhat\s+would\s+they\s+do\b"),
    # "can you not measure" and "cannot measure" and "can't measure" are the
    # same question asked three ways; the first form is the one a CEO uses
    # out loud and was the one this pattern missed.
    (CANNOT_MEASURE,
     r"\bcan(?:'t|not)?\s+(?:you\s+)?(?:not\s+)?measure\b|"
     r"\bwhat\s+do\s+(?:you|we)\s+not\s+know\b|"
     r"\bunmeasur|\blimit(?:s|ation)\b"),
    (WHAT_TO_TEST, r"\btest\b|\bexperiment\b|\bwhat\s+should\s+we\s+run\b"),
    (WHAT_TO_MONITOR, r"\bmonitor|\bwatch\b|\btrack\b"),
    (DECIDED_BEFORE,
     r"\bdecide[d]?\s+(before|last\s+time|previously)|"
     r"\bwhat\s+did\s+we\s+decide\b|\bprior\s+decision\b"),
    (SHOW_SOURCE,
     r"\bshow\s+me\s+the\s+(source|evidence)|\bprovenance\b|"
     r"\bwhere\s+(did|does)\s+(this|that)\s+come\s+from\b"),
    (WHY, r"^\s*why\b|\bwhy\s+(is|do|does|would)\b"),
)


class Answer:
    """One answer, with the standing and provenance that bound it."""

    __slots__ = ("question", "question_class", "answer", "supported",
                 "standing", "evidence_ids", "provenance", "information_gap")

    def __init__(self, question, question_class, answer, *, supported=True,
                 standing="", evidence_ids=(), provenance=(),
                 information_gap=""):
        self.question = question
        self.question_class = question_class
        self.answer = answer
        self.supported = supported
        self.standing = standing
        self.evidence_ids = tuple(evidence_ids)
        self.provenance = tuple(provenance)
        self.information_gap = information_gap

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "question": self.question,
                "question_class": self.question_class, "answer": self.answer,
                "supported": self.supported, "standing": self.standing,
                "evidence_ids": list(self.evidence_ids),
                "provenance": list(self.provenance),
                "information_gap": self.information_gap}


def classify(question: str) -> str:
    text = str(question or "").strip().lower()
    if not text:
        return UNSUPPORTED
    for name, pattern in _PATTERNS:
        if re.search(pattern, text):
            return name
    return UNSUPPORTED


def _joined(items, empty: str) -> str:
    items = [str(i) for i in (items or ()) if i]
    return " ".join(items) if items else empty


def answer(question: str, decision: Any,
           prior: Optional[Any] = None) -> Answer:
    """Answer one question by projecting one FounderDecision."""
    cls = classify(question)
    if decision is None:
        return Answer(question, UNSUPPORTED,
                      "No decision has been composed for this company, so "
                      "there is nothing to answer from.", supported=False)

    standing = getattr(decision, "standing", "") or ""
    verb = DS.verb_for(standing)
    ev = tuple(getattr(decision, "supporting_evidence_ids", ()) or ())
    prov = tuple(getattr(decision, "provenance", ()) or ())
    gaps = tuple(getattr(decision, "information_gaps", ()) or ())
    gap = gaps[0] if gaps else ""

    def _a(text, **kw):
        kw.setdefault("standing", standing)
        kw.setdefault("evidence_ids", ev)
        kw.setdefault("provenance", prov)
        kw.setdefault("information_gap", gap)
        return Answer(question, cls, text, **kw)

    if cls == UNSUPPORTED:
        return Answer(
            question, UNSUPPORTED,
            "I cannot answer that from this company's recorded intelligence. "
            "I can tell you what the current read is and why, what changed, "
            "what would change it, what the risks and alternatives are, what "
            "cannot be measured, and what to test or monitor.",
            supported=False, standing=standing, provenance=prov)

    if cls == RECOMMEND:
        if standing == DS.SUPPORTED:
            return _a(f"{decision.current_read} On that standing the evidence "
                      f"{verb} acting on the reading above.")
        return _a(
            f"No action is recommended on this evidence. {decision.current_read}"
            f" The reading {verb} the position above and no more, so the next "
            f"move is to resolve what is missing rather than to commit.")

    if cls == WHY:
        return _a(f"{decision.current_read} {decision.causal_note}".strip())

    if cls == STRONGEST_EVIDENCE:
        if not ev:
            return _a("No evidence row published for this company is cited by "
                      "any block in the current reading.", supported=False)
        return _a(f"{len(ev)} evidence row(s) are cited by this company's own "
                  f"blocks. They are listed under provenance and each one "
                  f"resolves to a source document.")

    if cls == CONTRADICTS:
        against = tuple(getattr(decision, "contradicting_evidence_ids", ())
                        or ())
        if not against:
            return _a("No contradicting evidence has been recorded for this "
                      "company. That is an absence of recorded contradiction, "
                      "not a demonstration that none exists.", supported=False)
        return _a(f"{len(against)} recorded row(s) contradict the reading.",
                  evidence_ids=against)

    if cls == WHAT_CHANGED:
        return _a(_joined(getattr(decision, "what_changed", ()),
                          "Nothing in the published record has changed."))

    if cls == CHANGED_YOUR_MIND:
        moved = tuple(getattr(decision, "what_changed_mind", ()) or ())
        if not moved:
            # NEVER inferred from how the view reads today. A claim about a
            # transition requires a recorded transition.
            return _a("Nothing has changed the reading. No recorded revision "
                      "has moved it, which is not the same as the reading "
                      "never having been tested.", supported=False)
        return _a(_joined(moved, ""))

    if cls == WOULD_CHANGE_YOUR_MIND:
        return _a(_joined(
            gaps + tuple(getattr(decision, "minimum_data_requests", ()) or ()),
            "Nothing has been recorded that would change this reading, which "
            "means the falsifier has not been stated rather than that none "
            "exists."))

    if cls == ALTERNATIVES:
        alts = tuple(getattr(decision, "alternatives", ()) or ())
        if not alts:
            return _a("No alternative course has been composed for this "
                      "company: the reading is not yet strong enough to be "
                      "weighed against one.", supported=False)
        return _a(_joined(alts, ""))

    if cls == BIGGEST_RISK:
        # THE GUARDRAIL LEADS, not the gap. "What is the biggest risk" and
        # "what would change your mind" both draw on the same unresolved
        # question, and answering them with the same sentence makes the
        # product look like it has one thought. The risk answer is about
        # ACTING under the gap; the falsifier answer is about resolving it.
        rails = tuple(getattr(decision, "guardrails", ()) or ())
        if rails:
            return _a(_joined(rails, ""))
        if gaps:
            return _a(f"The reading rests on a question that is not settled: "
                      f"{gaps[0]}")
        return _a("No risk has been recorded for this company beyond the "
                  "limits already stated on the reading.", supported=False)

    if cls == COMPETITOR:
        adv = tuple(getattr(decision, "adversary", ()) or ())
        if not adv:
            return _a("No competitor response has been modelled for this "
                      "company: THESIS_NOT_FORMED, so there is no strategic "
                      "position for a rival to respond to.", supported=False)
        return _a(_joined(adv, ""))

    if cls == CANNOT_MEASURE:
        return _a(_joined(
            (decision.causal_note,) + gaps,
            "Everything the reading rests on has been measured."))

    if cls == WHAT_TO_TEST:
        mdrs = tuple(getattr(decision, "minimum_data_requests", ()) or ())
        mves = tuple(getattr(decision, "minimum_viable_experiments", ()) or ())
        if not (mdrs or mves):
            return _a("No test has been proposed: no unresolved question has "
                      "been recorded that one would settle.", supported=False)
        return _a(_joined(mdrs + mves, ""))

    if cls == WHAT_TO_MONITOR:
        return _a(_joined(getattr(decision, "monitoring", ()),
                          "Nothing has been put under monitoring for this "
                          "company."))

    if cls == DECIDED_BEFORE:
        if prior is None:
            # NO_DECISION_RECORDED, not an invented history.
            return Answer(question, cls,
                          "NO_DECISION_RECORDED. No earlier decision has been "
                          "recorded for this company in this deployment.",
                          supported=False, standing=standing, provenance=prov)
        return _a(f"The previous recorded decision was: "
                  f"{getattr(prior, 'recommendation', '') or 'no recommendation'}"
                  f" (standing {getattr(prior, 'standing', '') or 'unstated'}).")

    if cls == SHOW_SOURCE:
        return _a(f"{len(ev)} evidence row(s) are cited by this company's "
                  f"blocks, published under {_joined(prov, 'no provenance')}.")

    return Answer(question, UNSUPPORTED, "", supported=False)


#: The questions §5 requires, for a surface that wants to offer them.
REQUIRED_QUESTIONS = (
    "What do you recommend?",
    "Why?",
    "What is the strongest evidence?",
    "What contradicts this?",
    "What changed?",
    "What changed your mind?",
    "What would change your mind?",
    "What are the alternatives?",
    "What is the biggest risk?",
    "What could a competitor do?",
    "What can you not measure?",
    "What should we test?",
    "What should we monitor?",
    "What did we decide before?",
    "Show me the source.",
)

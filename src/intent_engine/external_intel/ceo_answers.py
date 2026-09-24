"""What a founder asks, answered from the record or refused.

WHY A PLANNER AND NOT A PROMPT
------------------------------
The tempting build is a prompt: hand a model the dossier and the question and
let it write. That model will answer every question, including the ones the
evidence cannot support, and it will answer them in the same confident voice
as the ones it can. There is no seam at which to check it.

So the reasoning happens HERE, deterministically, and produces a plan: the
direct answer, the objects it came from, what is missing, and what the reader
must not conclude. A renderer may phrase the plan. It may not add to it.

THE DISTINCTION THIS MODULE EXISTS TO HOLD
------------------------------------------
"What changed?" and "What changed your mind?" are different questions and the
difference is the whole product. New evidence can arrive — a filing, a print,
a competitor move — and change NOTHING about the view. A system that answers
the second with the first is describing its own activity and calling it
learning.

    WHAT_CHANGED            new evidence and new economic state
    WHAT_CHANGED_YOUR_MIND  a recorded thesis transition, and its cause

EVERY EMPTY CASE IS DECIDED BEFORE IT SHIPS
-------------------------------------------
This project has now found the same defect in five layers: a degraded source
read as no activity, missing thesis history read as a thesis that never
moved, an absent baseline read as impact, an empty section read as no
intelligence, an empty before-state read as universal impact.

So every reader here declares what it does when its input is absent, and
absence never renders as a negative finding. `MISSING`, `NONE`,
`UNAVAILABLE` and `NOT_OBSERVED` are different answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.external_intel import decision_impact as di
from intent_engine.external_intel import coverage_state as CV
from intent_engine.external_intel import standing_ceiling as SC

CONTRACT = "ceo_answers.v1"

# --- question classes -------------------------------------------------------
CURRENT_STATE = "CURRENT_STATE"
WHY = "WHY"
WHY_IT_MATTERS = "WHY_IT_MATTERS"
WHAT_CHANGED = "WHAT_CHANGED"
WHAT_CHANGED_YOUR_MIND = "WHAT_CHANGED_YOUR_MIND"
STRONGEST_ALTERNATIVE = "STRONGEST_ALTERNATIVE"
WEAKEST_LINK = "WEAKEST_LINK"
FALSIFIER = "FALSIFIER"
MONITOR = "MONITOR"
NEXT_INFORMATION = "NEXT_INFORMATION"
WHAT_NOT_TO_CONCLUDE = "WHAT_NOT_TO_CONCLUDE"
CONFIDENCE = "CONFIDENCE"
CHALLENGE = "CHALLENGE"
UNKNOWN_QUESTION = "UNKNOWN_QUESTION"

QUESTION_CLASSES = (
    CURRENT_STATE, WHY, WHY_IT_MATTERS, WHAT_CHANGED,
    WHAT_CHANGED_YOUR_MIND, STRONGEST_ALTERNATIVE, WEAKEST_LINK, FALSIFIER,
    MONITOR, NEXT_INFORMATION, WHAT_NOT_TO_CONCLUDE, CONFIDENCE, CHALLENGE,
    UNKNOWN_QUESTION)

# --- hop standing -----------------------------------------------------------
OBSERVED = "OBSERVED"
SUPPORTED = "SUPPORTED"
HYPOTHESIZED = "HYPOTHESIZED"
CONTRADICTED = "CONTRADICTED"
MISSING = "MISSING"

#: The causal chain "why?" is allowed to walk, in order. A MISSING hop STOPS
#: the causal statement — the renderer is never handed a gap to bridge, which
#: is the one thing a language model will always do well and always do wrong.
WHY_CHAIN = ("EVIDENCE", "ECONOMIC_STATE", "COMPANY_EXPOSURE",
             "MECHANISM", "THESIS", "DECISION_CONSEQUENCE")

# --- premises a question can smuggle in -------------------------------------
#
# ORDERED MOST SPECIFIC FIRST. "Prove demand is collapsing" is a demand claim
# AND an instruction to prove; the demand reading is the useful one.
_LEADING = (
    (r"\bprove\b|\bshow me (?:the )?(?:evidence|proof) that\b",
     "asks for proof of a stated conclusion rather than for what the "
     "evidence shows"),
    (r"\bdefinitely\b|\bcertainly\b|\bguarantee\w*\b|\bwill (?:definitely|"
     r"certainly)\b",
     "asks for certainty the standing of this evidence cannot carry"),
    (r"\bignore\b[^.?]{0,30}\b(downside|risk|negative|bear case)\b",
     "asks for one side of the case"),
    (r"\bassume\b[^.?]{0,40}\b(won'?t|will not|cannot|no)\b[^.?]{0,30}"
     r"\b(respond|react|retaliate|compete)\b",
     "assumes a competitor response that no evidence rules out"),
    (r"\bstrongest possible case for\b|\bmake the case for\b",
     "asks for advocacy rather than adjudication"),
    (r"\bwe should\b|\bwe need to\b|\bgive me evidence (?:for|that)\b",
     "states a conclusion and asks for supporting evidence"),
)

_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (WHAT_CHANGED_YOUR_MIND,
     r"changed your mind|changed our mind|why did you change|"
     r"what made you change|revised your view"),
    (WHAT_CHANGED, r"\bwhat(?:'s| has| have)? changed\b|\bwhat is new\b|"
                   r"\bwhat'?s new\b|\banything new\b"),
    (WHAT_CHANGED_YOUR_MIND, r"what strengthened|what weakened"),
    (STRONGEST_ALTERNATIVE,
     r"strongest alternative|other explanation|what else could|"
     r"alternative explanation|could it be"),
    (WEAKEST_LINK, r"weakest link|weakest part|where.{0,20}weakest|"
                   r"what.{0,20}least confident"),
    (FALSIFIER, r"falsif\w+|prove(?:s|d)? (?:this|it) wrong|"
                r"what would change (?:your|the) (?:view|mind)|"
                r"what would disprove"),
    (MONITOR, r"what should i (?:monitor|watch)|what to watch|keep an eye"),
    (NEXT_INFORMATION,
     r"what (?:information|data|evidence) (?:should|do) we (?:get|need)|"
     r"what should we (?:research|find out)"),
    (WHAT_NOT_TO_CONCLUDE,
     r"should i not conclude|what does(?:n't| not) this (?:prove|mean)|"
     r"what can'?t (?:i|we) conclude"),
    (CONFIDENCE, r"how confident|how sure|confidence level|how certain"),
    (WHY_IT_MATTERS, r"why (?:should i|do i|does this) (?:care|matter)|"
                     r"why does it matter|so what"),
    (WHY, r"^why\b|\bwhy is\b|\bwhy are\b|\bwhat'?s driving\b|\bwhat is "
          r"driving\b|\bwhat'?s causing\b"),
    (CURRENT_STATE,
     r"what(?:'s| is) happening|current (?:state|situation|picture)|"
     r"where do (?:we|things) stand|how are things"),
)
_COMPILED = tuple((cls, re.compile(p, re.I)) for cls, p in _PATTERNS)


@dataclass(frozen=True)
class Hop:
    """One step of the causal chain, and how well it is known."""
    name: str
    standing: str
    detail: str = ""
    ids: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"name": self.name, "standing": self.standing,
                "detail": self.detail, "ids": list(self.ids)}


@dataclass(frozen=True)
class CEOAnswerPlan:
    """A bounded answer, and everything it rests on.

    The renderer may phrase `direct_answer` and `decision_implication`. It may
    not add a claim that is not here, and it may not drop `limitations` or
    `must_not_conclude` — those are the parts a fluent renderer removes first
    because they read as hedging.
    """
    question: str
    question_class: str
    direct_answer: str
    supported: bool
    decision_implication: str = ""
    standing: str = ""
    thesis_ids: Tuple[str, ...] = ()
    revision_ids: Tuple[str, ...] = ()
    effect_ids: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    hops: Tuple[Hop, ...] = ()
    alternatives: Tuple[str, ...] = ()
    falsifiers: Tuple[str, ...] = ()
    monitoring: Tuple[str, ...] = ()
    missing_information: Tuple[str, ...] = ()
    source_constraints: Tuple[str, ...] = ()
    must_not_conclude: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()
    premise_challenged: str = ""
    #: What this answer is permitted to assert, adjudicated by the producer
    #: and narrowed on this side. Empty means it was never decided, which the
    #: certainty wall reads as "assert nothing" rather than as "no limit".
    ceiling: str = ""
    #: The producer's own forbidden vocabulary, carried so a phrase this side
    #: never thought of is still caught when the producer named it.
    forbidden_words: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "question": self.question,
            "question_class": self.question_class,
            "direct_answer": self.direct_answer, "supported": self.supported,
            "decision_implication": self.decision_implication,
            "standing": self.standing,
            "thesis_ids": list(self.thesis_ids),
            "revision_ids": list(self.revision_ids),
            "effect_ids": list(self.effect_ids),
            "evidence_ids": list(self.evidence_ids),
            "hops": [h.as_dict() for h in self.hops],
            "alternatives": list(self.alternatives),
            "falsifiers": list(self.falsifiers),
            "monitoring": list(self.monitoring),
            "missing_information": list(self.missing_information),
            "source_constraints": list(self.source_constraints),
            "must_not_conclude": list(self.must_not_conclude),
            "limitations": list(self.limitations),
            "premise_challenged": self.premise_challenged,
            "ceiling": self.ceiling,
            "forbidden_words": list(self.forbidden_words),
        }


def classify(question: str) -> str:
    """Which question this is. UNKNOWN rather than a guess.

    A default class is a claim about what was asked, and answering the wrong
    question confidently is worse than declining: the founder cannot tell
    from the answer that it missed.
    """
    text = " ".join((question or "").split())
    if not text:
        return UNKNOWN_QUESTION
    if leading_premise(text):
        return CHALLENGE
    for cls, pattern in _COMPILED:
        if pattern.search(text):
            return cls
    return UNKNOWN_QUESTION


def leading_premise(question: str) -> str:
    """The unsupported premise this question smuggles in, or ""."""
    text = " ".join((question or "").split())
    for pattern, why in _LEADING:
        if re.search(pattern, text, re.I):
            return why
    return ""


def _theses(intel) -> List[dict]:
    return list(getattr(intel, "economic_theses", ()) or ())


def _degraded(intel) -> List[str]:
    """Source families whose silence must not be read as quiet."""
    health = getattr(intel, "source_health", None)
    if not isinstance(health, dict):
        return []
    return [str(f) for f in (health.get("impaired_families") or ())]


def _source_constraints(intel) -> Tuple[str, ...]:
    impaired = _degraded(intel)
    if not impaired:
        return ()
    return (f"visibility is reduced: {', '.join(sorted(impaired))} "
            f"{'is' if len(impaired) == 1 else 'are'} not currently "
            f"delivering, so the absence of new evidence from that source is "
            f"not evidence that nothing happened",)


def _unsupported(question: str, cls: str, why: str,
                 **kwargs) -> CEOAnswerPlan:
    # THE CEILING IS DECIDED HERE, not left empty. An unsupported plan used to
    # carry ceiling="" — an undecided value, which the certainty wall then had
    # to interpret. "Nothing may be asserted" is a decision and "" is the
    # absence of one, and this layer is the one that knows which.
    kwargs.setdefault("ceiling", SC.ASSERT_NONE)
    return CEOAnswerPlan(question=question, question_class=cls,
                         direct_answer=why, supported=False, **kwargs)


def _no_view_answer(intel) -> Tuple[str, Tuple[str, ...], str]:
    """WHICH KIND OF NOTHING this is, rather than one sentence for six.

    Every branch below used to return "No economic view is recorded for this
    company yet." That is honest and it is the same sentence for a company
    nobody has looked at and a company whose sources went dark — and those
    call for opposite actions: the first is a research task, the second is a
    risk. It is the ABSENT / SOURCE_DEGRADED distinction the engine already
    enforces per source, applied where it never had been: to the company.

    THE CEILING COMES BACK WITH THE SENTENCE. An earlier version returned only
    the words and let the caller hard-code ASSERT_NONE. That happened to be
    right for every state and was right by coincidence rather than by wiring —
    a break proof that widened OBSERVED to cover sparse dossiers went
    uncaught, because the coverage state said "observed" while the plan went
    on saying "assert nothing" from a constant. Two answers to one question is
    how they drift.
    """
    state = CV.classify(
        intel,
        hydrating=bool(getattr(intel, "hydrating", False)),
        degraded_sources=tuple(getattr(intel, "degraded_sources", ()) or ()))
    return (CV.STATE_WORDS[state], (CV.MUST_NOT_CONCLUDE[state],),
            CV.ceiling_for(state))


def plan(question: str, intel) -> CEOAnswerPlan:
    """The answer plan for one question against one dossier."""
    cls = classify(question)
    constraints = _source_constraints(intel)

    if cls == CHALLENGE:
        return _challenge(question, intel, constraints)
    if cls == WHAT_CHANGED_YOUR_MIND:
        return _changed_your_mind(question, intel, constraints)
    if cls == WHAT_CHANGED:
        return _what_changed(question, intel, constraints)
    if cls == STRONGEST_ALTERNATIVE:
        return _alternative(question, intel, constraints)
    if cls == FALSIFIER:
        return _falsifier(question, intel, constraints)
    if cls == WHAT_NOT_TO_CONCLUDE:
        return _not_conclude(question, intel, constraints)
    if cls == UNKNOWN_QUESTION:
        return _unsupported(
            question, cls,
            "I do not have a way to answer that from this company's recorded "
            "evidence. I can tell you what the current view is, what changed "
            "it, what would falsify it, or what the strongest alternative is.",
            source_constraints=constraints)
    return _current_state(question, cls, intel, constraints)


def _changed_your_mind(question, intel, constraints) -> CEOAnswerPlan:
    """The one question that may never be composed from the current view.

    A claim about what CHANGED a view can only come from a recorded
    transition. Inferring one from how the view reads today is the
    fabrication the whole provenance chain exists to prevent.
    """
    got = di.what_changed_your_mind(intel)
    limitations: List[str] = []
    if got["state"] == di.HISTORY_UNAVAILABLE:
        limitations.append(
            "revision history did not reach this analysis; this is not the "
            "same as the view never having changed")
    if got["state"] == di.HISTORY_AVAILABLE_NO_THESIS:
        limitations.append(
            "no economic view has been opened for this company; the silence "
            "here is an absence of analysis, not a stable conclusion")
    # THE STATE IS A FACT ABOUT THE RECORD, NOT ABOUT THE WORLD, so it caps
    # this answer at ASSERT_NONE. "We cannot see whether it moved" and "it did
    # not move" are the same sentence to a renderer that treats the state as a
    # standing, and this is the one place that difference is decided.
    return CEOAnswerPlan(
        question=question, question_class=WHAT_CHANGED_YOUR_MIND,
        direct_answer=got["answer"], supported=bool(got["supported"]),
        standing=got["state"], ceiling=SC.from_standing(got["state"]),
        revision_ids=tuple(str(r) for r in got["revisions"] if r),
        effect_ids=tuple(got["effects"]), evidence_ids=tuple(got["evidence"]),
        source_constraints=constraints, limitations=tuple(limitations),
        must_not_conclude=_history_must_not_conclude(got["state"]))


def _history_must_not_conclude(state: str) -> Tuple[str, ...]:
    """What each history state specifically forbids concluding.

    One sentence per state rather than one shared sentence, because the whole
    reason there are four states is that they license four different silences.
    """
    if state == di.HISTORY_AVAILABLE_NO_MOVEMENT:
        return ("an absence of recorded change is not evidence the view is "
                "settled; it may only mean nothing has tested it yet",)
    if state == di.HISTORY_AVAILABLE_NO_THESIS:
        return ("an absence of analysis is not a finding about this company; "
                "nothing here says the situation is quiet",)
    if state == di.HISTORY_UNAVAILABLE:
        return ("not seeing the history is not the same as the history being "
                "empty; no claim about movement can be made either way",)
    return ()


def _what_changed(question, intel, constraints) -> CEOAnswerPlan:
    """New information, which is NOT the same as a new conclusion."""
    theses = _theses(intel)
    revisions = list(getattr(intel, "thesis_revisions", ()) or ())
    moved = [r for r in revisions
             if str(r.get("transition") or "") != "CREATED"]
    beliefs = list(getattr(intel, "beliefs", ()) or ())
    if not beliefs and not theses:
        return _unsupported(
            question, WHAT_CHANGED,
            "No new market evidence reached this analysis, so I cannot tell "
            "you what changed.", source_constraints=constraints)
    if moved:
        answer = (f"{len(beliefs)} reading(s) are on file and "
                  f"{len(moved)} recorded revision(s) actually moved a view.")
    else:
        # THE SENTENCE THIS MODULE EXISTS FOR.
        answer = (f"{len(beliefs)} reading(s) are on file for this company, "
                  f"and none of them has moved a view yet. New evidence "
                  f"arrived; the conclusions did not change.")
    return CEOAnswerPlan(
        question=question, question_class=WHAT_CHANGED, direct_answer=answer,
        supported=True,
        thesis_ids=tuple(str(t.get("thesis_id") or "") for t in theses),
        revision_ids=tuple(str(r.get("revision_id") or "") for r in moved),
        source_constraints=constraints,
        must_not_conclude=(
            "new evidence arriving is not the same as a conclusion "
            "changing; count the second, not the first",))


def _alternative(question, intel, constraints) -> CEOAnswerPlan:
    theses = _theses(intel)
    # Blank entries are dropped BEFORE the emptiness check. A Mechanism with
    # no description arrives as "", which is not an alternative and rendered
    # as "The strongest recorded alternative is: " on a live dossier.
    alts = [str(a) for t in theses for a in (t.get("alternatives") or ())
            if str(a or "").strip()]
    if not alts:
        return _unsupported(
            question, STRONGEST_ALTERNATIVE,
            "No competing explanation is recorded for this view. That is a "
            "gap in the analysis rather than evidence the view is "
            "uncontested.", source_constraints=constraints,
            missing_information=("recorded alternatives",))
    return CEOAnswerPlan(
        question=question, question_class=STRONGEST_ALTERNATIVE,
        direct_answer=(f"The strongest recorded alternative is: "
                       f"{str(alts[0])}"),
        supported=True, alternatives=tuple(str(a) for a in alts[:5]),
        thesis_ids=tuple(str(t.get("thesis_id") or "") for t in theses),
        source_constraints=constraints)


def _falsifier(question, intel, constraints) -> CEOAnswerPlan:
    theses = _theses(intel)
    falsifiers = [str(t.get("falsifier") or "") for t in theses
                  if str(t.get("falsifier") or "").strip()]
    if not falsifiers:
        return _unsupported(
            question, FALSIFIER,
            "No falsifier is recorded for this view, which means it is not "
            "currently stated in a way that evidence could overturn.",
            source_constraints=constraints,
            missing_information=("a recorded falsifier",))
    return CEOAnswerPlan(
        question=question, question_class=FALSIFIER,
        direct_answer=f"This view would be wrong if: {falsifiers[0]}",
        supported=True, falsifiers=tuple(falsifiers[:5]),
        thesis_ids=tuple(str(t.get("thesis_id") or "") for t in theses),
        source_constraints=constraints)


def _not_conclude(question, intel, constraints) -> CEOAnswerPlan:
    limits = list(getattr(intel, "limitations", ()) or ())
    standing = [f"this view is recorded as {t.get('standing')}, not proven"
                for t in _theses(intel) if t.get("standing")]
    items = tuple(limits + standing) or (
        "nothing here is a measured causal effect; these are readings held "
        "from public evidence",)
    return CEOAnswerPlan(
        question=question, question_class=WHAT_NOT_TO_CONCLUDE,
        direct_answer="Here is what this evidence does not establish.",
        supported=True, must_not_conclude=items,
        source_constraints=constraints)


def _current_state(question, cls, intel, constraints) -> CEOAnswerPlan:
    theses = _theses(intel)
    if not theses:
        answer, forbids, ceiling_ = _no_view_answer(intel)
        return _unsupported(
            question, cls, answer, source_constraints=constraints,
            must_not_conclude=forbids, ceiling=ceiling_)
    leading = theses[0]
    hops = _why_hops(leading, intel)
    stopped = next((h for h in hops if h.standing == MISSING), None)
    answer = str(leading.get("claim") or "")
    if cls in (WHY, WHY_IT_MATTERS) and stopped is not None:
        # `hops[index - 1]` wrapped to the LAST hop when the FIRST one was
        # missing, and produced "I can trace that as far as decision
        # consequence and no further: evidence is not recorded". Caught on a
        # live dossier, not by a fixture.
        index = hops.index(stopped)
        gap = stopped.name.lower().replace("_", " ")
        if index == 0:
            answer = (f"{answer} I cannot trace that back at all: {gap} is "
                      f"not recorded for this company.")
        else:
            reached = hops[index - 1].name.lower().replace("_", " ")
            answer = (f"{answer} I can trace that as far as {reached} and no "
                      f"further: {gap} is not recorded for this company.")
    # `supported` WAS HARD-CODED TRUE. A thesis the producer had abandoned —
    # REFUTED, or SUPERSEDED by a later reading — arrived here and came back
    # out as a supported answer about the current state, because the presence
    # of a thesis row was being read as support for its claim. Whether an
    # answer is supported is a question about the standing, and the ceiling is
    # where that question is already answered.
    ceiling_ = SC.ceiling_for(leading)
    if not SC.may_assert(ceiling_):
        answer = _abandoned_reading(leading, answer, ceiling_)
    return CEOAnswerPlan(
        question=question, question_class=cls, direct_answer=answer,
        supported=SC.may_assert(ceiling_),
        standing=str(leading.get("standing") or ""),
        ceiling=ceiling_,
        forbidden_words=tuple(str(w) for w in
                              (leading.get("forbidden_words") or ())),
        decision_implication=str(leading.get("decision_implication") or ""),
        thesis_ids=(str(leading.get("thesis_id") or ""),),
        evidence_ids=tuple(str(e) for e in
                           (leading.get("evidence_ids") or ())),
        hops=tuple(hops),
        alternatives=tuple(str(a) for a in
                           (leading.get("alternatives") or ())
                           if str(a or "").strip()),
        falsifiers=((str(leading.get("falsifier")),)
                    if leading.get("falsifier") else ()),
        missing_information=tuple(
            h.name for h in hops if h.standing == MISSING),
        source_constraints=constraints,
        limitations=tuple(getattr(intel, "limitations", ()) or ()))


#: Thesis standing -> how well THIS HOP is known. A translation, so the two
#: vocabularies never share a slot. CONTRADICTED is the reading for a thesis
#: the producer abandoned: the hop is known, and what is known is that it
#: failed — which is not the same as MISSING, where nothing is known at all.
_THESIS_HOP = {
    "PROPOSED": HYPOTHESIZED,
    "SUPPORTED": SUPPORTED,
    "TESTED": OBSERVED,
    "WEAKENED": HYPOTHESIZED,
    "REFUTED": CONTRADICTED,
    "SUPERSEDED": CONTRADICTED,
}


def _hop_standing(thesis: dict) -> str:
    """The causal-hop standing for the thesis hop, translated not copied."""
    if not str(thesis.get("claim") or "").strip():
        return MISSING
    return _THESIS_HOP.get(str(thesis.get("standing") or "").upper(),
                           HYPOTHESIZED)


def _abandoned_reading(thesis: dict, claim: str, ceiling_: str) -> str:
    """Say that a reading no longer holds, rather than reporting it as news.

    The claim still travels — an executive who was told this last month is
    owed the correction, not silence — but it travels in the past tense with
    the standing that ended it attached.
    """
    standing = str(thesis.get("standing") or "").upper()
    if standing == "SUPERSEDED":
        return (f"That reading has been replaced. What we previously said was: "
                f"{claim} A later reading now stands in its place.")
    if standing == "REFUTED":
        return (f"That reading no longer holds. What we previously said was: "
                f"{claim} The test that would break it fired.")
    return (f"I cannot state a current view here. The recorded reading is "
            f"{standing or 'unnamed'}, which does not support asserting it.")


def _why_hops(thesis: dict, intel) -> List[Hop]:
    """The causal chain, with every gap named rather than bridged."""
    evidence = list(thesis.get("evidence_ids") or ())
    conditions = list(thesis.get("macro_conditions") or ())
    exposures = list(thesis.get("exposures") or ())
    mechanism = str(thesis.get("mechanism") or "")
    consequence = str(thesis.get("decision_implication") or "")
    return [
        Hop("EVIDENCE", OBSERVED if evidence else MISSING,
            f"{len(evidence)} evidence id(s)", tuple(str(e) for e in evidence)),
        Hop("ECONOMIC_STATE", SUPPORTED if conditions else MISSING,
            ", ".join(str(c) for c in conditions[:3])),
        Hop("COMPANY_EXPOSURE", SUPPORTED if exposures else MISSING,
            ", ".join(str(e) for e in exposures[:3])),
        Hop("MECHANISM", HYPOTHESIZED if mechanism else MISSING, mechanism),
        # THE HOP VOCABULARY, NOT THE THESIS ONE. This slot used to receive
        # the transported thesis standing directly, so one field held values
        # from two vocabularies that overlap only at SUPPORTED — and every
        # reader of `Hop.standing` had to know which kind it had been handed.
        # The thesis standing is not lost: it is on the plan, where it means
        # what it says.
        Hop("THESIS", _hop_standing(thesis),
            str(thesis.get("claim") or "")),
        Hop("DECISION_CONSEQUENCE",
            SUPPORTED if consequence else MISSING, consequence),
    ]


def _challenge(question, intel, constraints) -> CEOAnswerPlan:
    """A leading question is answered by adjudicating it, not obeying it.

    The premise is named, the evidence is reported as it stands, and the
    alternative and falsifier travel with it — because the reason to refuse a
    leading question is not politeness, it is that the answer would otherwise
    be built from the question rather than from the record.
    """
    why = leading_premise(question) or "assumes a conclusion"
    theses = _theses(intel)
    alts = [str(a) for t in theses for a in (t.get("alternatives") or ())
            if str(a or "").strip()]
    falsifiers = [str(t.get("falsifier") or "") for t in theses
                  if str(t.get("falsifier") or "").strip()]
    leading = theses[0] if theses else {}
    answer = (
        "I can't answer that as asked — it " + why + ". "
        + (f"What the evidence currently supports is: "
           f"{leading.get('claim')}" if leading
           else _no_view_answer(intel)[0]))
    return CEOAnswerPlan(
        question=question, question_class=CHALLENGE, direct_answer=answer,
        supported=bool(theses), premise_challenged=why,
        standing=str(leading.get("standing") or ""),
        thesis_ids=((str(leading.get("thesis_id") or ""),) if leading else ()),
        alternatives=tuple(str(a) for a in alts[:3]),
        falsifiers=tuple(falsifiers[:3]),
        source_constraints=constraints,
        must_not_conclude=(
            "a question asserting a conclusion is not evidence for it",))


#: Words a renderer may not introduce AT ANY STANDING. The graded list lives
#: in `standing_ceiling` and narrows as the record weakens; these are the ones
#: nothing this engine can produce would ever license.
FORBIDDEN_UPGRADES = ("definitely", "certainly", "guaranteed", "proven",
                      "proves", "must be", "always", "never fails")


def violates_certainty_wall(text: str, plan_: CEOAnswerPlan) -> Tuple[str, ...]:
    """Words in a rendered answer that its plan does not support.

    THE CEILING MOVES WITH THE PLAN, which it did not before. This function
    used to exempt plans whose standing was OBSERVED or MEASURED — values from
    the causal-hop vocabulary, which `plan_.standing` never holds, because it
    is read off a transported thesis whose standings are PROPOSED, SUPPORTED,
    TESTED, WEAKENED, REFUTED and SUPERSEDED. The branch was unreachable for
    every value the field can carry, so one fixed word list applied to a
    tested reading and an abandoned one alike. A ceiling that does not move
    with the record is a constant wearing the name of a ceiling.
    """
    ceiling_ = SC.stricter_of(plan_.ceiling or "",
                             SC.from_standing(plan_.standing))
    return SC.words_beyond(text, ceiling_,
                           extra=tuple(FORBIDDEN_UPGRADES)
                           + tuple(plan_.forbidden_words))

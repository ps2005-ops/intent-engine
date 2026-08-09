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
    return CEOAnswerPlan(question=question, question_class=cls,
                         direct_answer=why, supported=False, **kwargs)


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
    return CEOAnswerPlan(
        question=question, question_class=WHAT_CHANGED_YOUR_MIND,
        direct_answer=got["answer"], supported=bool(got["supported"]),
        standing=got["state"],
        revision_ids=tuple(str(r) for r in got["revisions"] if r),
        effect_ids=tuple(got["effects"]), evidence_ids=tuple(got["evidence"]),
        source_constraints=constraints, limitations=tuple(limitations),
        must_not_conclude=(
            ("an absence of recorded change is not evidence the view is "
             "settled; it may only mean nothing has tested it yet",)
            if got["state"] == di.HISTORY_AVAILABLE_NO_MOVEMENT else ()))


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
    alts = [a for t in theses for a in (t.get("alternatives") or ())]
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
        return _unsupported(
            question, cls,
            "No economic view is recorded for this company yet.",
            source_constraints=constraints)
    leading = theses[0]
    hops = _why_hops(leading, intel)
    stopped = next((h for h in hops if h.standing == MISSING), None)
    answer = str(leading.get("claim") or "")
    if cls in (WHY, WHY_IT_MATTERS) and stopped is not None:
        answer = (f"{answer} I can trace that as far as "
                  f"{hops[hops.index(stopped) - 1].name.lower().replace('_', ' ')} "
                  f"and no further: {stopped.name.lower().replace('_', ' ')} "
                  f"is not recorded for this company.")
    return CEOAnswerPlan(
        question=question, question_class=cls, direct_answer=answer,
        supported=True, standing=str(leading.get("standing") or ""),
        decision_implication=str(leading.get("decision_implication") or ""),
        thesis_ids=(str(leading.get("thesis_id") or ""),),
        evidence_ids=tuple(str(e) for e in
                           (leading.get("evidence_ids") or ())),
        hops=tuple(hops),
        alternatives=tuple(str(a) for a in
                           (leading.get("alternatives") or ())),
        falsifiers=((str(leading.get("falsifier")),)
                    if leading.get("falsifier") else ()),
        missing_information=tuple(
            h.name for h in hops if h.standing == MISSING),
        source_constraints=constraints,
        limitations=tuple(getattr(intel, "limitations", ()) or ()))


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
        Hop("THESIS", str(thesis.get("standing") or HYPOTHESIZED),
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
    alts = [a for t in theses for a in (t.get("alternatives") or ())]
    falsifiers = [str(t.get("falsifier") or "") for t in theses
                  if str(t.get("falsifier") or "").strip()]
    leading = theses[0] if theses else {}
    answer = (
        "I can't answer that as asked — it " + why + ". "
        + (f"What the evidence currently supports is: "
           f"{leading.get('claim')}" if leading
           else "No economic view is recorded for this company yet."))
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


#: Words a renderer may not introduce. The plan's standing is the ceiling,
#: and an executive asking for confidence does not raise it.
FORBIDDEN_UPGRADES = ("definitely", "certainly", "guaranteed", "proven",
                      "proves", "must be", "always", "never fails")


def violates_certainty_wall(text: str, plan_: CEOAnswerPlan) -> Tuple[str, ...]:
    """Words in a rendered answer that its plan does not support."""
    if str(plan_.standing).upper() in ("OBSERVED", "MEASURED"):
        return ()
    lowered = " " + " ".join((text or "").lower().split()) + " "
    return tuple(word for word in FORBIDDEN_UPGRADES
                 if f" {word} " in lowered)

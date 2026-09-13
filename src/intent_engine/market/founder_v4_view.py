"""What a chief executive gets, derived from the thesis rather than rewritten.

WHY THIS IS A PROJECTION AND NOT A WRITER
-----------------------------------------
Every field here is read off an `EconomicThesis`. Nothing is composed, nothing
is softened, and there is no path by which the briefing can contain a claim the
thesis does not. That constraint is the product: a reader who asks "why do you
believe that" three times reaches provenance rather than a better sentence.

CEO LANGUAGE IS NOT A LOWER STANDARD
------------------------------------
Translating "MARKET_RATE → CAPITAL_INTENSITY, LOWERS, 270 days" into "your cost
of capital is rising and the projects you have not yet committed are the ones
that move" changes the vocabulary and not the claim. What must survive the
translation is the uncertainty: the alternative explanations, the fact that
nothing has been tested, and what would change the answer.

THE ENGINE IS ALLOWED TO REFUSE
-------------------------------
`answer` will decline a leading question. Asked to prove something the evidence
does not establish, the useful response is the state of the argument, not
compliance — and an engine that produces the requested conclusion on request is
worth nothing to the person asking, because it would have produced the opposite
one just as readily.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import economic_thesis as ET

CONTRACT = "founder_v4_view.v1"

# --- how a decision is affected ------------------------------------------------
NONE = "NONE"
PRESENTATIONAL = "PRESENTATIONAL"
MEANINGFUL = "MEANINGFUL"
DECISION_CHANGING = "DECISION_CHANGING"
IMPACT_LEVELS = (NONE, PRESENTATIONAL, MEANINGFUL, DECISION_CHANGING)

#: Plain words for a standing. Chosen so none of them reads as settled.
_STANDING_WORDS = {
    ET.PROPOSED: "we think this is the most likely explanation and have not "
                 "tested it",
    ET.SUPPORTED: "the evidence so far fits, and the test that would break it "
                  "has not been run",
    ET.TESTED: "we tried to break this and could not",
    ET.WEAKENED: "something has come in that argues against this",
    ET.REFUTED: "this turned out to be wrong",
    ET.SUPERSEDED: "we have replaced this with a later reading",
}


class RefusedToOverstate(ValueError):
    """Raised when a question would require asserting more than is known."""


@dataclass(frozen=True)
class FounderV4View:
    """One thesis, in the words of the person who has to act on it."""

    subject: str
    direct_answer: str
    what_changed: str
    economic_context: str
    how_it_reaches_this_company: str
    why_it_matters: str
    second_order: Tuple[str, ...]
    what_could_make_this_wrong: Tuple[str, ...]
    what_we_expect_next: str
    what_to_watch: Tuple[str, ...]
    decision_implication: str
    confidence_in_words: str
    evidence_ids: Tuple[str, ...]
    thesis_id: str = ""
    standing: str = ET.PROPOSED

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT)
        return d


def project(thesis: ET.EconomicThesis, *,
            consequences: Sequence[ET.ConsequenceHypothesis] = (),
            state_reason: str = "") -> FounderV4View:
    """Render a thesis for a reader who has to decide something.

    Passes through `consistent_with` before returning, so a projection that
    somehow claimed more than its source raises here rather than reaching a
    slide.
    """
    mech = thesis.leading_mechanism
    alternatives = tuple(m.description for m in thesis.alternatives)
    view = FounderV4View(
        subject=thesis.subject,
        direct_answer=thesis.claim,
        what_changed=state_reason or ", ".join(thesis.macro_conditions)
        or "no measured condition moved",
        economic_context=", ".join(thesis.macro_conditions)
        or "no economic condition is measured for this",
        how_it_reaches_this_company=(
            f"{mech.description} — this reaches {thesis.subject} through its "
            f"{', '.join(thesis.exposures) or 'unrated'} exposure, which the "
            "company established in its own material"),
        why_it_matters=(
            f"if the mechanism holds, the effect lands within about "
            f"{thesis.horizon_days} days, which is inside the window in which "
            "a decision could still change it"),
        second_order=tuple(f"order {c.order}: {c.actor} — {c.mechanism}"
                           for c in consequences if c.order > 1),
        # THE ALTERNATIVES ARE NOT OPTIONAL AND NOT A FOOTNOTE. They are the
        # answer to the only question a chief executive reliably asks, and a
        # briefing that omits them has converted a leading explanation into
        # the only one.
        what_could_make_this_wrong=alternatives + (mech.falsifier,),
        what_we_expect_next=mech.falsifier and
        f"the test is simple: {mech.falsifier} would end this reading",
        what_to_watch=tuple(thesis.falsifiers),
        decision_implication=_implication(thesis),
        confidence_in_words=_STANDING_WORDS.get(thesis.standing,
                                                thesis.standing),
        evidence_ids=thesis.supporting_evidence,
        thesis_id=thesis.thesis_id,
        standing=thesis.standing)
    ET.consistent_with(thesis, rendered_standing=view.standing,
                       drops_alternatives=not view.what_could_make_this_wrong,
                       surface="founder view")
    return view


def _implication(thesis: ET.EconomicThesis) -> str:
    """What to do about it — including, most often, nothing yet.

    "Watch this" is a real recommendation and the honest one for an untested
    thesis. A layer that always produces an action produces actions on
    nothing.
    """
    if thesis.standing in (ET.REFUTED, ET.SUPERSEDED):
        return "no action; this reading no longer holds"
    if thesis.standing == ET.PROPOSED:
        return ("do not act on this yet; it is the leading explanation and "
                f"nothing has tested it. Watch for: "
                f"{thesis.leading_mechanism.falsifier}")
    if thesis.standing == ET.WEAKENED:
        return ("hold; something has come in against this and the alternative "
                "explanations are back in play")
    return (f"this is firm enough to plan around within "
            f"{thesis.horizon_days} days, while the alternatives stay listed")


# --- the CEO conversation ---------------------------------------------------------

#: Question -> which field answers it. A fixed map, so an answer cannot be
#: composed on the spot: every reply is a field of a record somebody can open.
_QUESTION_FIELDS = {
    "why": "how_it_reaches_this_company",
    "what would change your mind": "what_could_make_this_wrong",
    "how soon": "why_it_matters",
    "what are you assuming": "what_could_make_this_wrong",
    "what should i watch": "what_to_watch",
    "what should i not do": "decision_implication",
    "how confident": "confidence_in_words",
    "what changed": "what_changed",
    "so what": "why_it_matters",
}

#: Phrasings that ask for a conclusion rather than for the state of one.
_LEADING = ("prove that", "prove ", "confirm that", "show me that",
            "tell me that", "make the case that", "just say")


def answer(view: FounderV4View, question: str,
           thesis: Optional[ET.EconomicThesis] = None) -> dict:
    """Answer from the record, or decline and say what is actually known.

    A leading question is refused whenever the thesis is not assertable. The
    refusal is not a dodge: it returns the leading explanation, the live
    alternatives and the observation that would settle it, which is more use
    than the requested sentence would have been.
    """
    lowered = question.strip().lower()
    leading = any(phrase in lowered for phrase in _LEADING)
    if leading and thesis is not None and not thesis.assertable:
        return {
            "contract": CONTRACT,
            "refused": True,
            "reason": ("the evidence does not establish that; here is where "
                       "the argument actually stands"),
            "leading_explanation": thesis.claim,
            "standing": thesis.standing,
            "alternatives": [m.description for m in thesis.alternatives],
            "what_would_settle_it": list(thesis.falsifiers),
            "note": ("an engine that produces the requested conclusion would "
                     "have produced the opposite one just as readily"),
        }
    for phrase, field_name in _QUESTION_FIELDS.items():
        if phrase in lowered:
            value = getattr(view, field_name)
            return {"contract": CONTRACT, "refused": False,
                    "answered_from": field_name,
                    "answer": list(value) if isinstance(value, tuple)
                    else value,
                    "thesis_id": view.thesis_id, "standing": view.standing}
    return {"contract": CONTRACT, "refused": True,
            "reason": ("no field of this thesis answers that; composing one "
                       "would be writing rather than reporting"),
            "answerable": sorted(_QUESTION_FIELDS)}


# --- what V4 actually changed ---------------------------------------------------------

#: The components of a decision a briefing can affect. Fixed, so "impact" is
#: a count of named things rather than an impression of richness.
COMPONENTS = ("assumption", "risk", "opportunity", "timing", "scenario",
              "monitoring", "falsifier", "research_priority", "option",
              "recommendation")


def decision_impact(without: Dict[str, object],
                    with_v4: Dict[str, object]) -> dict:
    """Deterministic before-and-after over named decision components.

    NOT A PROSE COMPARISON. More sophisticated writing is not more decision
    value, and the only way to keep the two apart is to count components that
    were empty before and are populated now — and to say plainly when the
    answer is that nothing changed.
    """
    added, changed = [], []
    for component in COMPONENTS:
        before, after = without.get(component), with_v4.get(component)
        if not before and after:
            added.append(component)
        elif before and after and before != after:
            changed.append(component)
    decisive = {"falsifier", "timing", "recommendation", "option",
                "monitoring"}
    touched = set(added) | set(changed)
    if not touched:
        level = NONE
    elif touched & decisive:
        level = (DECISION_CHANGING if len(touched & decisive) >= 2
                 else MEANINGFUL)
    elif len(touched) >= 2:
        level = MEANINGFUL
    else:
        level = PRESENTATIONAL
    return {
        "contract": CONTRACT,
        "added": sorted(added),
        "changed": sorted(changed),
        "untouched": sorted(set(COMPONENTS) - touched),
        "level": level,
        "note": ("counted over named components; a longer briefing that "
                 "populates nothing new scores NONE"),
    }


def summarise(views: Sequence[FounderV4View]) -> dict:
    return {
        "contract": CONTRACT,
        "views": len(views),
        "subjects": sorted({v.subject for v in views}),
        "all_carry_alternatives": all(v.what_could_make_this_wrong
                                      for v in views),
        "all_carry_a_watch_item": all(v.what_to_watch for v in views),
        "by_standing": {s: sum(1 for v in views if v.standing == s)
                        for s in sorted({v.standing for v in views})},
        "note": ("every field is read off a thesis; nothing here is composed "
                 "and nothing may say more than its source"),
    }

"""Slides, as a view over the thesis. Never a second place reasoning happens.

WHY A DECK IS THE MOST DANGEROUS SURFACE
----------------------------------------
It is the one people remember. A bounded thesis becomes a confident headline,
the headline becomes the decision, and the qualification survives only in a
record nobody opens. Every other surface in this engine can be checked against
its source by a reader who cares; a slide is read once, by people who will not.

So a deck here is generated, not written. Each slide names the thesis field it
came from, every slide passes `economic_thesis.consistent_with` on the way out,
and a slide that cannot name its source is not rendered — an empty section is
the honest output when the thesis has nothing to put in it.

THE HEADLINE IS BOUND TO THE STANDING
-------------------------------------
A PROPOSED thesis may not produce "this is happening". The map from standing to
permitted headline verb is data below rather than a convention, so a reviewer
can disagree with it in one place instead of auditing prose.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No chart generation, no template engine, no styling. The deck is a list of
typed sections; whatever renders it inherits the standing because the standing
is in the data.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import economic_thesis as ET

CONTRACT = "presentation.v1"

# --- the sections, in the order a chief executive reads them --------------------
ANSWER = "DIRECT_ANSWER"
WHAT_CHANGED = "WHAT_CHANGED"
WHY_IT_MATTERS = "WHY_IT_MATTERS"
TRANSMISSION = "ECONOMIC_TRANSMISSION"
EXPOSURE = "COMPANY_EXPOSURE"
SECOND_ORDER = "SECOND_ORDER_EFFECTS"
SCENARIOS = "SCENARIOS"
OPTIONS = "OPTIONS_AND_DECISION"
ALTERNATIVES = "ALTERNATIVE_EXPLANATIONS"
CHANGE_OUR_MIND = "WHAT_WOULD_CHANGE_OUR_MIND"
WATCH = "WHAT_TO_WATCH"
APPENDIX = "EVIDENCE_APPENDIX"

SECTIONS = (ANSWER, WHAT_CHANGED, WHY_IT_MATTERS, TRANSMISSION, EXPOSURE,
            SECOND_ORDER, SCENARIOS, OPTIONS, ALTERNATIVES, CHANGE_OUR_MIND,
            WATCH, APPENDIX)

#: Sections that may never be dropped, whatever the deck is for. The
#: alternatives and the falsifier are the two a presenter is most tempted to
#: cut for time, and cutting them converts a leading explanation into the only
#: one — which is the failure this module exists to prevent.
REQUIRED = frozenset({ANSWER, ALTERNATIVES, CHANGE_OUR_MIND})

#: What the headline is allowed to assert at each standing. A deck cannot be
#: more certain than the record it renders, and the ceiling is data so a
#: reviewer can argue with it in one place.
_HEADLINE_VERB = {
    ET.PROPOSED: "may be",
    ET.SUPPORTED: "appears to be",
    ET.TESTED: "is, on the evidence we have tried to break",
    ET.WEAKENED: "is in doubt:",
    ET.REFUTED: "is not:",
    ET.SUPERSEDED: "has been replaced:",
}

#: Words a slide may not contain, whatever the standing. Certainty language
#: survives editing in a way a standing field does not.
_BANNED = ("will certainly", "guaranteed", "risk-free", "cannot fail",
           "proven fact", "no doubt", "definitely will")


class DeckRejected(ValueError):
    """A slide that would say more than the record behind it."""


@dataclass(frozen=True)
class Slide:
    """One section, its content, and the field it was read from."""

    section: str
    heading: str
    bullets: Tuple[str, ...] = ()
    #: The thesis attribute or record this slide projects. A slide that cannot
    #: name one is prose, and prose does not go in a deck built from records.
    sourced_from: str = ""
    standing: str = ET.PROPOSED

    def __post_init__(self) -> None:
        if self.section not in SECTIONS:
            raise DeckRejected(f"unknown section {self.section!r}")
        if not self.sourced_from.strip():
            raise DeckRejected(
                f"{self.section} names no source field; a slide that cannot "
                "say where it came from is being written rather than "
                "rendered")
        text = " ".join((self.heading,) + self.bullets).lower()
        for phrase in _BANNED:
            if phrase in text:
                raise DeckRejected(
                    f"{self.section} contains {phrase!r}: certainty language "
                    "outlives the standing field that was supposed to "
                    "qualify it")

    @property
    def empty(self) -> bool:
        return not self.bullets

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, bullets=list(self.bullets),
                 empty=self.empty)
        return d


@dataclass(frozen=True)
class Deck:
    """A presentation, and the thesis it is a view of."""

    subject: str
    thesis_id: str
    standing: str
    slides: Tuple[Slide, ...]
    as_of: str = ""
    #: THE CLAIM THIS DECK WAS RENDERED FROM. `thesis_id` binds a deck to a
    #: thesis, and identity deliberately survives a reworded claim — the same
    #: thesis is allowed to restate itself. That leaves a gap `thesis_id`
    #: alone cannot close: a deck whose headline still asserts last month's
    #: wording belongs to this thesis and no longer says what it says. Stale
    #: is a different failure from foreign, and both reach the room.
    claim: str = ""

    @property
    def missing_required(self) -> Tuple[str, ...]:
        present = {s.section for s in self.slides if not s.empty}
        return tuple(sorted(REQUIRED - present))

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "subject": self.subject,
                "thesis_id": self.thesis_id, "standing": self.standing,
                "as_of": self.as_of,
                "slides": [s.as_dict() for s in self.slides],
                "sections": [s.section for s in self.slides],
                "empty_sections": [s.section for s in self.slides if s.empty],
                "missing_required": list(self.missing_required),
                "note": ("every slide names the field it renders; a deck is a "
                         "view of a thesis and may say less than it, never "
                         "more")}


def build(thesis: ET.EconomicThesis, *, view=None,
          consequences: Sequence[ET.ConsequenceHypothesis] = (),
          scenarios: Sequence[ET.Scenario] = (),
          proof: Optional[ET.ProofPackage] = None,
          as_of: str = "") -> Deck:
    """Render a thesis as slides, refusing to overstate it anywhere.

    `view` is an optional `founder_v4_view.FounderV4View`; when present its
    plain-language fields are used, because they were already checked against
    the same thesis. When absent the deck is built from the thesis directly
    and says the same thing in the thesis's own words.
    """
    verb = _HEADLINE_VERB.get(thesis.standing, "may be")
    mech = thesis.leading_mechanism

    def slide(section, heading, bullets, source):
        return Slide(section=section, heading=heading,
                     bullets=tuple(b for b in bullets if b),
                     sourced_from=source, standing=thesis.standing)

    slides: List[Slide] = [
        slide(ANSWER, f"{thesis.subject}: {thesis.claim}",
              (f"On what we can show today, this {verb} the case.",
               getattr(view, "confidence_in_words", "")
               or f"standing: {thesis.standing}"),
              "thesis.claim + thesis.standing"),
        slide(WHAT_CHANGED,
              "What moved",
              (getattr(view, "what_changed", "")
               or ", ".join(thesis.macro_conditions)
               or "no measured economic condition moved",),
              "thesis.macro_conditions"),
        slide(WHY_IT_MATTERS, "Why it matters to us",
              (getattr(view, "why_it_matters", "")
               or f"the effect would land within about "
                  f"{thesis.horizon_days} days",),
              "thesis.horizon_days"),
        slide(TRANSMISSION, "How it reaches us",
              (mech.description,
               f"expected lag: about {mech.lag_days or thesis.horizon_days} "
               "days" if (mech.lag_days or thesis.horizon_days) else ""),
              "thesis.leading_mechanism"),
        slide(EXPOSURE, "Where we are exposed",
              tuple(thesis.exposures) or
              ("no exposure of ours is established for this condition",),
              "thesis.exposures"),
        slide(SECOND_ORDER, "What follows from that",
              tuple(f"{c.actor}: {c.mechanism} ({c.direction}, about "
                    f"{c.horizon_days} days)" for c in consequences
                    if c.order > 1),
              "consequences"),
        slide(SCENARIOS, "If it goes the other way",
              tuple(f"{s.kind}: {s.direction}, {s.magnitude.lower()}"
                    + (f" — {s.decision_implication}"
                       if s.decision_implication else "")
                    for s in scenarios),
              "scenarios"),
        slide(OPTIONS, "What this changes",
              (getattr(view, "decision_implication", "")
               or _default_implication(thesis),),
              "founder_v4_view.decision_implication"),
        # NOT OPTIONAL AND NOT A FOOTNOTE. These two are the sections a
        # presenter cuts for time, and cutting them is the whole failure.
        slide(ALTERNATIVES, "What else could explain this",
              tuple(m.description for m in thesis.alternatives)
              or ("none has been identified, which is itself a weakness in "
                  "this reading",),
              "thesis.alternatives"),
        slide(CHANGE_OUR_MIND, "What would change our mind",
              (mech.falsifier,) + tuple(m.falsifier
                                        for m in thesis.alternatives),
              "thesis.falsifiers"),
        slide(WATCH, "What to watch",
              tuple(getattr(view, "what_to_watch", ())) or thesis.falsifiers,
              "thesis.falsifiers"),
        slide(APPENDIX, "Evidence",
              tuple(thesis.supporting_evidence)
              + ((f"proof status: {proof.status}",) if proof else ())
              + tuple(f"limitation: {u}" for u in thesis.unknowns),
              "thesis.supporting_evidence + proof.status"),
    ]

    # THE WALL, RUN ONCE PER SLIDE. Each slide claims the thesis's standing,
    # so a slide is refused the moment it would assert more — and a deck that
    # dropped the alternatives is refused as a whole rather than shipped with
    # a gap nobody notices.
    dropped = not any(s.section == ALTERNATIVES and not s.empty
                      for s in slides)
    for one in slides:
        ET.consistent_with(thesis, rendered_standing=one.standing,
                           drops_alternatives=dropped,
                           surface=f"slide {one.section}")
    return Deck(subject=thesis.subject, thesis_id=thesis.thesis_id,
                standing=thesis.standing, slides=tuple(slides),
                as_of=as_of or thesis.as_of, claim=thesis.claim)


def _default_implication(thesis: ET.EconomicThesis) -> str:
    if thesis.standing in ET.ASSERTABLE:
        return ("firm enough to plan around, with the alternatives still "
                "listed")
    return "nothing yet; this is the leading reading and it is untested"


def check(deck: Deck, thesis: ET.EconomicThesis) -> dict:
    """Re-verify a deck against its thesis after any editing.

    `build` cannot protect a deck somebody changed afterwards, and a deck is
    exactly the artefact people change afterwards. This is the check to run
    before it leaves the building.
    """
    problems: List[str] = []
    if deck.thesis_id != thesis.thesis_id:
        problems.append("deck does not belong to this thesis")
    elif deck.claim and deck.claim != thesis.claim:
        problems.append(
            "deck renders a claim this thesis no longer makes: "
            f"{deck.claim!r} against {thesis.claim!r}")
    for one in deck.slides:
        try:
            ET.consistent_with(thesis, rendered_standing=one.standing,
                               surface=f"slide {one.section}")
        except ET.Overclaim as exc:
            problems.append(str(exc))
    if deck.missing_required:
        problems.append(
            "required sections are empty: "
            + ", ".join(deck.missing_required))
    return {"contract": CONTRACT, "consistent": not problems,
            "problems": problems,
            "note": ("a deck may say less than its thesis and never more; "
                     "the alternatives and the falsifier are never optional")}


def summarise(decks: Sequence[Deck]) -> dict:
    return {
        "contract": CONTRACT,
        "decks": len(decks),
        "subjects": sorted({d.subject for d in decks}),
        "by_standing": {s: sum(1 for d in decks if d.standing == s)
                        for s in sorted({d.standing for d in decks})},
        "all_carry_alternatives": all(not d.missing_required for d in decks),
        "empty_sections": sum(len(d.as_dict()["empty_sections"])
                              for d in decks),
        "note": ("an empty section is the honest output when the thesis has "
                 "nothing to put in it; it is never filled with prose"),
    }

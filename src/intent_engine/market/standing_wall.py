"""One ceiling for every surface, so certainty cannot be gained by travelling.

THE FAILURE THIS EXISTS FOR
---------------------------
A view of the world passes through four surfaces before anybody acts on it:
the thesis states it, the proof package says what was tested, the deck shows
it to a room, and the CEO answer is asked about it out loud. Each surface was
built with its own honest local rule. None of them compared notes.

So the same reading could be PROPOSED in the thesis, VERIFIED in the proof,
asserted in a slide and answered without hedging — with no single step being
wrong. Certainty was gained by travelling, which is the failure mode nobody
catches by reviewing one file.

This module is that comparison, in one place. It does not replace
`economic_thesis.consistent_with`, which already governs the thesis→render
axis correctly and is depended on by V3 surfaces. It adds the three axes that
had no owner:

  * PROOF vs THESIS. `ProofPackage.status` was derived purely from evidence
    counts and never looked at the standing of the thesis it was proving. A
    REFUTED thesis with two independent sources and a tested falsifier
    produced status VERIFIED, and the deck printed "proof status: VERIFIED" in
    the appendix of a reading the engine had already abandoned.

  * RECORD STATES vs WORLD STATES. "We have no history for this" and "the
    history shows nothing moved" are different sentences, and only the second
    is a finding. They are not two values of one scale; asking which is
    stronger is a category error, and this module raises rather than answers.

  * WORDING vs STANDING. A renderer's certainty vocabulary must narrow as the
    standing weakens. The founder branch had a "certainty wall" whose
    standing-based exemption tested for values the field could never hold, so
    it applied one fixed word list to TESTED and REFUTED alike. A ceiling that
    does not move is not a ceiling.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No new standing vocabulary for the thesis. `economic_thesis.STANDINGS` remains
the only definition of how strongly a thesis is held; this module maps those
values onto what a surface may SAY, which is a different question and the one
that was unowned. Two copies of one fact is how the planner drifted before.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Tuple

from . import economic_thesis as ET

CONTRACT = "standing_wall.v1"


class StandingViolation(ValueError):
    """A surface that would say more than the record behind it."""


class CategoryError(ValueError):
    """A comparison between a claim about the world and a fact about the record."""


# --- what a surface is permitted to assert ----------------------------------
#
# ORDERED, and about ASSERTION rather than about belief. `ASSERT_NEGATIVE` is
# deliberately off this ladder: "this reading does not hold" is a strong claim
# that is nonetheless not a licence to assert the reading, so it is compared
# by identity and never by rank.
ASSERT_NONE = "ASSERT_NONE"          # only that a question is open
ASSERT_LEADING = "ASSERT_LEADING"    # "the leading reading is X, untested"
ASSERT_BOUNDED = "ASSERT_BOUNDED"    # "the evidence fits, within stated limits"
ASSERT_TESTED = "ASSERT_TESTED"      # "we tried to break this and could not"
ASSERT_NEGATIVE = "ASSERT_NEGATIVE"  # "this reading no longer holds"

CEILINGS = (ASSERT_NONE, ASSERT_LEADING, ASSERT_BOUNDED, ASSERT_TESTED,
            ASSERT_NEGATIVE)

_RANK = {ASSERT_NONE: 0, ASSERT_LEADING: 1, ASSERT_BOUNDED: 2,
         ASSERT_TESTED: 3}

#: How strongly a thesis standing lets a surface speak. WEAKENED is capped at
#: LEADING rather than at its `economic_thesis` rank: counterevidence has
#: arrived, so the reading may still be stated as the leading one and may no
#: longer be reported as fitting the evidence.
_THESIS_CEILING = {
    ET.PROPOSED: ASSERT_LEADING,
    ET.SUPPORTED: ASSERT_BOUNDED,
    ET.TESTED: ASSERT_TESTED,
    ET.WEAKENED: ASSERT_LEADING,
    ET.REFUTED: ASSERT_NEGATIVE,
    ET.SUPERSEDED: ASSERT_NEGATIVE,
}

#: What a proof status claims. The mirror of the map above, so the two can be
#: compared at all.
_PROOF_CEILING = {
    ET.OPEN: ASSERT_LEADING,
    ET.BOUNDED: ASSERT_BOUNDED,
    ET.VERIFIED: ASSERT_TESTED,
    ET.FAILED: ASSERT_NEGATIVE,
}

# --- facts about the record, which are not claims about the world -----------
#
# Every one of these has been produced by mistake by some earlier layer of
# this engine as a stand-in for a measured zero. They are enumerated so that a
# reader forced to handle one cannot reach for the nearest world-state.
UNRESOLVED = "UNRESOLVED"                    # asked, nothing decided it
UNMEASURABLE = "UNMEASURABLE"                # cannot be measured as posed
ABSENT = "ABSENT"                            # the record has no entry
NOT_OBSERVED = "NOT_OBSERVED"                # looked, saw nothing
NOT_APPLICABLE = "NOT_APPLICABLE"            # the question does not apply
REFUSED = "REFUSED"                          # declined to answer
SOURCE_DEGRADED = "SOURCE_DEGRADED"          # the channel, not the world
FIRST_OBSERVATION = "FIRST_OBSERVATION"      # nothing to compare against yet
HISTORY_UNAVAILABLE = "HISTORY_UNAVAILABLE"  # no prior version is readable
HISTORY_AVAILABLE_NO_MOVEMENT = "HISTORY_AVAILABLE_NO_MOVEMENT"  # a finding
HISTORY_AVAILABLE_MOVED = "HISTORY_AVAILABLE_MOVED"              # a finding
HISTORY_AVAILABLE_NO_THESIS = "HISTORY_AVAILABLE_NO_THESIS"  # nothing to move

RECORD_STATES = (UNRESOLVED, UNMEASURABLE, ABSENT, NOT_OBSERVED,
                 NOT_APPLICABLE, REFUSED, SOURCE_DEGRADED, FIRST_OBSERVATION,
                 HISTORY_UNAVAILABLE, HISTORY_AVAILABLE_NO_MOVEMENT,
                 HISTORY_AVAILABLE_MOVED, HISTORY_AVAILABLE_NO_THESIS)

#: Plain readings, so a surface handed a record state has a sentence to use
#: that does not quietly become a measurement.
RECORD_STATE_WORDS = {
    UNRESOLVED: "this is open; nothing in the record decides it",
    UNMEASURABLE: "this cannot be measured as asked",
    ABSENT: "there is no entry for this",
    NOT_OBSERVED: "we looked and saw nothing, which is not the same as none",
    NOT_APPLICABLE: "this question does not apply here",
    REFUSED: "this was declined, and the reason is recorded",
    SOURCE_DEGRADED: "the source feeding this is degraded, so visibility "
                     "fell rather than activity",
    FIRST_OBSERVATION: "this is the first recorded version; there is nothing "
                       "to compare it against",
    HISTORY_UNAVAILABLE: "no earlier version of this is readable",
    HISTORY_AVAILABLE_NO_MOVEMENT: "earlier versions are readable and none of "
                                   "them differ",
    HISTORY_AVAILABLE_MOVED: "earlier versions are readable and the view "
                             "moved between them",
    HISTORY_AVAILABLE_NO_THESIS: "the history is readable and holds nothing "
                                 "for this subject; no view has been opened",
}

#: The vocabulary the founder causal chain uses for one hop. Named here only
#: so a value from it can be REJECTED when it turns up in a thesis-standing
#: slot; the two vocabularies share the word SUPPORTED and nothing else, and
#: a field that accepts both silently is how a hop standing became a thesis
#: standing on the way across the bridge.
HOP_STANDINGS = frozenset({"OBSERVED", "SUPPORTED", "HYPOTHESIZED",
                           "CONTRADICTED", "MISSING"})

# --- wording that outlives the field meant to qualify it --------------------
#
# CUMULATIVE AND CEILING-BOUND. The strongest thing this engine can say is
# that it tried to break a reading and could not, so the top row is not empty:
# no standing licenses "guaranteed". Each weaker ceiling forbids everything
# the stronger one forbids, plus more.
_BANNED_AT = {
    # Truth, certainty and guarantee. Forbidden at EVERY standing, because the
    # strongest thing this engine can say is that it tried to break a reading
    # and could not — a smaller claim than truth, and one no amount of
    # evidence upgrades.
    ASSERT_TESTED: ("guaranteed", "risk-free", "cannot fail", "no doubt",
                    "will certainly", "certain to", "beyond doubt",
                    "proves", "proven", "proof that", "definitely",
                    "certainly", "always", "never fails", "must be"),
    # The falsifier was not tested, so nothing may say that it was.
    ASSERT_BOUNDED: ("withstood", "held up under", "survived every",
                     "stress-tested", "we tried to break", "ruled out",
                     "verified", "confirms", "confirmed"),
    # Nothing has confirmed the reading, so nothing may say the evidence does.
    ASSERT_LEADING: ("established", "we know", "demonstrates",
                     "shows conclusively", "the evidence supports",
                     "corroborated", "consistent with the evidence"),
    # Nothing may be asserted about the world at all.
    ASSERT_NONE: ("indicates", "suggests the", "shows that", "means that",
                  "evidence for"),
    ASSERT_NEGATIVE: ("indicates", "suggests the", "shows that", "means that",
                      "evidence for"),
}

_NARROWING = (ASSERT_TESTED, ASSERT_BOUNDED, ASSERT_LEADING, ASSERT_NONE)


def banned_words(ceiling_: str) -> Tuple[str, ...]:
    """Every phrase forbidden at this ceiling, strongest rules included.

    A weaker ceiling inherits the stronger one's prohibitions, so the list
    grows as the record weakens. That growth is the whole point: a word list
    that does not change with the standing is a constant wearing the name of
    a ceiling.
    """
    if ceiling_ not in CEILINGS:
        raise StandingViolation(f"unknown ceiling {ceiling_!r}")
    if ceiling_ == ASSERT_NEGATIVE:
        return tuple(dict.fromkeys(
            sum((_BANNED_AT[c] for c in _NARROWING), ())
            + _BANNED_AT[ASSERT_NEGATIVE]))
    out: list = []
    for step in _NARROWING:
        out.extend(_BANNED_AT[step])
        if step == ceiling_:
            break
    return tuple(dict.fromkeys(out))


# --- the ceiling ------------------------------------------------------------

def is_record_state(state: str) -> bool:
    return state in RECORD_STATES


def ceiling(state: str) -> str:
    """The strongest thing a surface may say, given this state.

    Accepts a thesis standing, a proof status or a record state, because the
    caller's whole problem is that it holds one of the three and must not
    guess which ladder it is on.
    """
    if state in _THESIS_CEILING:
        return _THESIS_CEILING[state]
    if state in _PROOF_CEILING:
        return _PROOF_CEILING[state]
    if state in RECORD_STATES:
        # A fact about the record licenses no assertion about the world. This
        # is the rule that keeps "we have no history" from being rendered in
        # the voice of "nothing changed".
        return ASSERT_NONE
    if state in HOP_STANDINGS:
        raise StandingViolation(
            f"{state!r} is a causal-hop standing, not a standing for a "
            "thesis or a proof; the two vocabularies overlap only at "
            "SUPPORTED and a slot that takes both silently loses the "
            "difference")
    raise StandingViolation(f"unknown state {state!r}")


def rank(ceiling_: str) -> int:
    """How much assertion a ceiling permits. ASSERT_NEGATIVE has no rank."""
    if ceiling_ == ASSERT_NEGATIVE:
        raise CategoryError(
            "ASSERT_NEGATIVE is not a point on the assertion ladder: "
            "'this reading does not hold' is not a weaker version of "
            "'this reading holds'")
    if ceiling_ not in _RANK:
        raise StandingViolation(f"unknown ceiling {ceiling_!r}")
    return _RANK[ceiling_]


def permits(source_state: str, rendered_state: str) -> bool:
    """May a surface in `rendered_state` speak for a record in `source_state`?"""
    src, ren = ceiling(source_state), ceiling(rendered_state)
    if src == ASSERT_NEGATIVE:
        # An abandoned reading may only be reported as abandoned, or not at
        # all. It may never be reported as holding, however weakly.
        return ren in (ASSERT_NEGATIVE, ASSERT_NONE)
    if ren == ASSERT_NEGATIVE:
        # Reporting a live reading as dead understates rather than overstates,
        # which this wall does not police — but it is never silently equal.
        return True
    return rank(ren) <= rank(src)


def interchangeable(a: str, b: str) -> bool:
    """Whether one state may be rendered in place of another.

    Two distinct record states are NEVER interchangeable. This is the
    guard against the substitution this engine keeps making: reporting
    HISTORY_UNAVAILABLE as HISTORY_AVAILABLE_NO_MOVEMENT turns "we cannot
    see" into "we looked and it held still", which is a finding nobody made.
    """
    if a == b:
        return True
    if is_record_state(a) or is_record_state(b):
        return False
    return ceiling(a) == ceiling(b)


# --- the cross-surface adjudication -----------------------------------------

@dataclass(frozen=True)
class SurfaceClaim:
    """What one surface intends to say, and what it kept from the record."""

    surface: str
    #: A thesis standing, a proof status or a record state.
    state: str
    text: str = ""
    keeps_alternatives: bool = True
    keeps_falsifiers: bool = True

    def as_dict(self) -> dict:
        return {"surface": self.surface, "state": self.state,
                "ceiling": ceiling(self.state),
                "keeps_alternatives": self.keeps_alternatives,
                "keeps_falsifiers": self.keeps_falsifiers}


@dataclass(frozen=True)
class WallReport:
    """Whether a set of surfaces agree about how much is known."""

    thesis_state: str
    thesis_ceiling: str
    surfaces: Tuple[dict, ...]
    violations: Tuple[str, ...]

    @property
    def consistent(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "thesis_state": self.thesis_state,
                "thesis_ceiling": self.thesis_ceiling,
                "surfaces": list(self.surfaces),
                "violations": list(self.violations),
                "consistent": self.consistent,
                "note": ("a surface may say less than the record behind it "
                         "and never more; the alternatives and the falsifier "
                         "are not optional at any standing")}


def check(thesis_state: str, surfaces: Sequence[SurfaceClaim], *,
          has_alternatives: bool = True,
          has_falsifiers: bool = True) -> WallReport:
    """Adjudicate every surface against the one record they all render.

    Returns rather than raises, because the useful artefact is the full list
    of disagreements — a wall that stops at the first one gets fixed one
    surface at a time, and the next cycle finds the next.
    """
    top = ceiling(thesis_state)
    problems: list = []
    for claim in surfaces:
        try:
            if not permits(thesis_state, claim.state):
                problems.append(
                    f"{claim.surface} presents {claim.state} "
                    f"({ceiling(claim.state)}) for a record that is "
                    f"{thesis_state} ({top})")
        except StandingViolation as exc:
            problems.append(f"{claim.surface}: {exc}")
            continue
        if has_alternatives and not claim.keeps_alternatives:
            problems.append(
                f"{claim.surface} drops the alternative explanations; "
                "removing them converts a leading explanation into the "
                "only one")
        if has_falsifiers and not claim.keeps_falsifiers:
            problems.append(
                f"{claim.surface} drops the falsifier; a claim nothing "
                "could disprove is not the same claim")
        for word in words_beyond(claim.text, claim.state):
            problems.append(
                f"{claim.surface} says {word!r}, which its {claim.state} "
                "standing does not carry")
    return WallReport(thesis_state=thesis_state, thesis_ceiling=top,
                      surfaces=tuple(c.as_dict() for c in surfaces),
                      violations=tuple(problems))


def words_beyond(text: str, state: str) -> Tuple[str, ...]:
    """Phrases in rendered text that the state behind it does not support."""
    if not text:
        return ()
    lowered = " " + " ".join(text.lower().split()) + " "
    return tuple(w for w in banned_words(ceiling(state)) if f" {w} " in lowered
                 or f" {w}," in lowered or f" {w}." in lowered)


# --- what travels to a consumer that cannot import this module --------------

def export(thesis_state: str, *, proof_status: str = "") -> dict:
    """The ceiling, as data, for a surface in another repository.

    The founder branch cannot import this package, so the decision travels
    instead of the code. What crosses is the ADJUDICATED ceiling and the words
    it forbids — not the standing alone, because a consumer handed a bare
    standing has to re-derive the map, and the second copy is where the two
    sides drift.
    """
    top = ceiling(thesis_state)
    if proof_status:
        proof_top = ceiling(proof_status)
        if not permits(thesis_state, proof_status):
            raise StandingViolation(
                f"proof status {proof_status} ({proof_top}) exceeds thesis "
                f"standing {thesis_state} ({top}); exporting this would carry "
                "the overclaim across the bridge")
    return {
        "contract": CONTRACT,
        "thesis_standing": thesis_state,
        "proof_status": proof_status,
        "ceiling": top,
        "forbidden_words": list(banned_words(top)),
        "is_record_state": is_record_state(thesis_state),
        "reading": RECORD_STATE_WORDS.get(thesis_state,
                                          _CEILING_WORDS.get(top, "")),
    }


#: What each ceiling licenses, in the voice a consumer may use. Keyed on the
#: ceiling rather than on the standing, because the consumer is being told
#: what it may SAY and a standing is a fact about what we believe.
_CEILING_WORDS = {
    ASSERT_NONE: "nothing may be asserted from this",
    ASSERT_LEADING: "this may be stated as the leading reading, untested",
    ASSERT_BOUNDED: "the evidence so far fits, within the stated limits",
    ASSERT_TESTED: "the test that would break this was run and it survived",
    ASSERT_NEGATIVE: "this reading no longer holds and may not be presented "
                     "as holding",
}

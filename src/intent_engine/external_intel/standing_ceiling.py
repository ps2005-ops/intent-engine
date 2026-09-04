"""What this side may assert, mirroring the producer and never exceeding it.

WHY THIS IS A SECOND COPY
-------------------------
The market package holds the canonical wall (`market/standing_wall.py`). This
package cannot import it — the two live on branches that do not share a
dependency — so the ceiling travels as DATA on every thesis row, and this
module is the reader for it.

The mirror below exists for the case the data does not arrive: an older
producer, a refused field, a thesis this side downgraded after it crossed. In
every one of those cases the answer has to come from somewhere, and a
consumer that shrugs and asserts is the failure the bridge was built to
prevent.

THE RULE WHEN THE TWO DISAGREE
------------------------------
The stricter reading wins, always. This side may say less than the producer
meant and never more, so `stricter_of` takes a minimum rather than trusting
either party. That asymmetry is what makes a second copy safe: drift can only
close the surface down, never open it up.

WHAT THIS IS NOT
----------------
Not a re-derivation of how strongly a thesis is held. The producer decides
that. This decides what a sentence on this side is allowed to sound like.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

CONTRACT = "standing_ceiling.v1"

ASSERT_NONE = "ASSERT_NONE"
ASSERT_LEADING = "ASSERT_LEADING"
ASSERT_BOUNDED = "ASSERT_BOUNDED"
ASSERT_TESTED = "ASSERT_TESTED"
ASSERT_NEGATIVE = "ASSERT_NEGATIVE"

CEILINGS = (ASSERT_NONE, ASSERT_LEADING, ASSERT_BOUNDED, ASSERT_TESTED,
            ASSERT_NEGATIVE)

_RANK = {ASSERT_NONE: 0, ASSERT_LEADING: 1, ASSERT_BOUNDED: 2,
         ASSERT_TESTED: 3}

#: MIRROR of the producer's map. Pinned by `test_founder_standing_ceiling`
#: against the exported values on real dossiers, because a mirror nobody
#: compares is just a guess with a comment.
_FROM_STANDING = {
    "PROPOSED": ASSERT_LEADING,
    "SUPPORTED": ASSERT_BOUNDED,
    "TESTED": ASSERT_TESTED,
    "WEAKENED": ASSERT_LEADING,
    "REFUTED": ASSERT_NEGATIVE,
    "SUPERSEDED": ASSERT_NEGATIVE,
}

#: Facts about the record. None of them licenses an assertion about the world,
#: and none of them may be rendered as another: "we have no history" and "the
#: history shows nothing moved" are different sentences and only one is a
#: finding.
RECORD_STATES = ("UNRESOLVED", "UNMEASURABLE", "ABSENT", "NOT_OBSERVED",
                 "NOT_APPLICABLE", "REFUSED", "SOURCE_DEGRADED",
                 "FIRST_OBSERVATION", "HISTORY_UNAVAILABLE",
                 "HISTORY_AVAILABLE_NO_MOVEMENT", "HISTORY_AVAILABLE_MOVED",
                 "HISTORY_AVAILABLE_NO_THESIS")

#: EACH STEP FORBIDS THE CLAIM THE STEP ABOVE IT EARNED. That is what makes
#: this a ladder rather than four lists: at ASSERT_BOUNDED the falsifier was
#: not tested, so language asserting that it WAS is what becomes unavailable;
#: at ASSERT_LEADING nothing has confirmed the reading, so language asserting
#: that evidence confirms it goes; at ASSERT_NONE nothing may be said about
#: the world at all.
#:
#: An earlier arrangement put the truth-claim words at ASSERT_BOUNDED while a
#: separate flat "forbidden at any standing" list also contained them. The
#: BOUNDED rung was therefore dead — TESTED and SUPPORTED forbade exactly the
#: same words — and a break proof collapsing the whole table went uncaught.
_BANNED_AT = {
    # Truth, certainty and guarantee. Forbidden at EVERY standing: the
    # strongest thing this engine can say is that it tried to break a reading
    # and could not, which is a smaller claim than truth.
    ASSERT_TESTED: ("guaranteed", "risk-free", "cannot fail", "no doubt",
                    "will certainly", "certain to", "beyond doubt",
                    "proves", "proven", "proof that", "definitely",
                    "certainly", "always", "never fails", "must be"),
    # The falsifier was not tested, so nothing may say it was.
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
    """Every phrase forbidden at this ceiling, cumulative as it weakens."""
    if ceiling_ not in CEILINGS:
        return _all_banned()
    if ceiling_ == ASSERT_NEGATIVE:
        return _all_banned()
    out: list = []
    for step in _NARROWING:
        out.extend(_BANNED_AT[step])
        if step == ceiling_:
            break
    return tuple(dict.fromkeys(out))


def _all_banned() -> Tuple[str, ...]:
    return tuple(dict.fromkeys(
        sum((_BANNED_AT[c] for c in _NARROWING), ())
        + _BANNED_AT[ASSERT_NEGATIVE]))


def from_standing(standing: str) -> str:
    """The ceiling a bare standing implies, when no ceiling was transported.

    An unknown standing yields ASSERT_NONE. That is not a judgement about the
    claim — it is the only honest response to a word this side cannot place,
    and it fails toward silence rather than toward confidence.
    """
    state = str(standing or "").upper()
    if state in _FROM_STANDING:
        return _FROM_STANDING[state]
    if state in RECORD_STATES:
        return ASSERT_NONE
    return ASSERT_NONE


def stricter_of(*ceilings: str) -> str:
    """The narrowest ceiling among those given.

    ASSERT_NEGATIVE is not a rank on the ladder — "this reading no longer
    holds" is not a weaker version of "it holds" — so its presence anywhere
    decides the result outright: a reading the producer abandoned may not be
    reported as holding, however faintly.
    """
    seen = [c for c in ceilings if c]
    if not seen:
        return ASSERT_NONE
    if ASSERT_NEGATIVE in seen:
        return ASSERT_NEGATIVE
    ranked = [c for c in seen if c in _RANK]
    if not ranked:
        return ASSERT_NONE
    return min(ranked, key=lambda c: _RANK[c])


def ceiling_for(row: dict) -> str:
    """The ceiling for one transported thesis row.

    Reads the producer's decision when it arrived, re-derives from the
    standing on this side, and returns the stricter. The re-derivation is not
    redundant: this side downgrades a thesis that arrived without its rivals,
    and a ceiling computed before that downgrade would outrank the standing it
    is supposed to cap.
    """
    if not isinstance(row, dict):
        return ASSERT_NONE
    transported = str(row.get("ceiling") or "")
    if transported and transported not in CEILINGS:
        # An unrecognised ceiling is not mapped onto the nearest one.
        transported = ASSERT_NONE
    local = from_standing(row.get("standing"))
    return stricter_of(transported, local)


def words_beyond(text: str, ceiling_: str,
                 extra: Sequence[str] = ()) -> Tuple[str, ...]:
    """Phrases in rendered text the ceiling behind it does not support.

    `extra` carries the producer's own forbidden list, so a phrase this side
    has not thought of is still caught when the producer names it.
    """
    if not text:
        return ()
    words = tuple(dict.fromkeys(tuple(banned_words(ceiling_))
                                + tuple(str(e).lower() for e in extra or ())))
    lowered = " " + " ".join(text.lower().split()) + " "
    return tuple(w for w in words
                 if f" {w} " in lowered or f" {w}," in lowered
                 or f" {w}." in lowered)


def may_assert(ceiling_: str) -> bool:
    """Whether a surface at this ceiling may state the reading at all."""
    return ceiling_ in (ASSERT_LEADING, ASSERT_BOUNDED, ASSERT_TESTED)

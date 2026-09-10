"""Quoting the sentence a match sat in, without quoting page furniture.

WHY THIS IS ITS OWN MODULE
--------------------------
Three producers here quote evidence back to a reader -- the classifier, the
lens router and the profile's asset extractor -- and all three had their own
character-offset window. Measured on the deployed service, Highspot:

    "The evidence this rests on omers are transforming GTM performance."

The span began mid-word, because a window of "match minus 220 characters" has
no idea where a word starts. Two of the three quotes on that page were also
drawn from a press-releases index -- "Highspot in the news. ... Get in touch
for any press inquiries: press@highspot.com" -- which is page furniture and
is not evidence for anything.

Both faults are one fault: a span cut by arithmetic rather than by grammar. So
there is one function, it snaps to SENTENCES, and it refuses furniture using
`strategic_intelligence.evidence_text` -- the module that already owns that
rule for every other consumer in the product. A second furniture detector is
how two subsystems come to disagree about what a page says.
"""
from __future__ import annotations

from typing import Optional

#: how much text either side of the match is considered for a sentence
WINDOW = 600
#: the longest quote worth putting on a page
MAX_CHARS = 300


def quote_around(text: str, start: int, end: int,
                 *, max_chars: int = MAX_CHARS) -> str:
    """The best real sentence containing or adjoining [start, end).

    Returns "" when everything nearby is furniture, and the CALLER RENDERS
    NOTHING rather than a fragment: a quotation that begins mid-word tells a
    reader the machine is not reading, which costs more than the quote was
    worth.
    """
    body = str(text or "")
    if not body:
        return ""
    left = max(0, start - WINDOW)
    right = min(len(body), end + WINDOW)
    window = body[left:right]
    try:
        from intent_engine.strategic_intelligence.evidence_text import (
            furniture_reason, split_sentences,
        )
    except Exception:                                        # noqa: BLE001
        return _word_snapped(body, start, end, max_chars)

    target = start - left
    best: Optional[str] = None
    best_distance = None
    for offset, sentence in split_sentences(window):
        clean = " ".join(str(sentence).split())
        if len(clean) < 30 or furniture_reason(clean):
            continue
        # the sentence the match is INSIDE wins outright
        if offset <= target < offset + len(sentence):
            return clean[:max_chars]
        distance = abs(offset - target)
        if best_distance is None or distance < best_distance:
            best, best_distance = clean, distance
    if best is None:
        return ""
    return best[:max_chars]


def _word_snapped(body: str, start: int, end: int, max_chars: int) -> str:
    """Fallback that at least never begins mid-word."""
    left = max(0, start - 200)
    right = min(len(body), end + 200)
    while left > 0 and body[left - 1].isalnum():
        left -= 1
    while right < len(body) and body[right].isalnum():
        right += 1
    return " ".join(body[left:right].split())[:max_chars]

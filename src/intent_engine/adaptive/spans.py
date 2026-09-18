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


#: Glyphs a list uses to mark an item. A passage that OPENS with one is the
#: tail of a list, not a sentence.
_BULLETS = "\u2022\u25cf\u25aa\u00b7\u2023\u2043-\u2013\u2014*"


def is_quotable(passage: str) -> bool:
    """Can this stand on a page as a quotation, on its own?

    MEASURED LIVE (ZoomInfo, 807a4143). The page carried:

        "\u2022We experience competition from other companies and technologies
         that allow businesses to gather and aggregate sales, marketing,
         recruiting, and other data, and we may in the future face competition
         from prominent large-language-model (LLM) providers and generative AI
         companies,"

    A bullet glyph at the front and a comma at the back: the middle of one
    item of a risk-factor list, quoted as though it were a sentence. Both ends
    are the same fault -- a passage lifted out of a structure that carried its
    meaning.

    A caller that gets False renders a PARAPHRASE with its citation instead,
    which is the existing behaviour for a span that found only furniture.
    """
    text = " ".join(str(passage or "").split())
    if len(text) < 30:
        return False
    if text[0] in _BULLETS:
        return False
    # A PASSAGE THAT BEGINS MID-SENTENCE. The live defect this module was
    # built for read "omers are transforming GTM performance" -- the tail of
    # "customers". `quote_around` snaps to sentences, but the fallback path
    # and a corpus with no sentence punctuation can still hand back a
    # fragment, and the two ends are the same fault.
    #
    # A lowercase FIRST LETTER is only a fragment when the whole first word is
    # lowercase: "iPhone", "eBay" and "openAI" are how those companies write
    # their own names, and refusing them would delete real first-party
    # evidence to catch a formatting artifact.
    first = text.split(" ", 1)[0]
    if first[:1].islower() and first.islower():
        return False
    # a quotation may be elided, but it may not simply stop mid-clause
    if text[-1] not in ".!?\u2026" and not text.endswith('."'):
        return False
    return True


def dedupe_passages(passages):
    """Distinct passages, keeping the most complete form of each.

    MEASURED LIVE (ZoomInfo, 807a4143): the same sentence appeared twice
    under "The evidence this rests on". The existing guard was
    `dict.fromkeys`, which is EXACT-string dedup -- and the two copies were
    not exactly equal, because three producers quote with three different
    `max_chars` (240, 280, 300). The same passage cut at two lengths is two
    strings and one quotation.

    So sameness is decided by prefix after normalisation, in both directions,
    and the longer form wins. Elision markers are stripped before comparing,
    or "... selling \u2026" and "... selling, training" never match.
    """
    kept = []
    for raw in passages:
        text = " ".join(str(raw or "").split())
        if not text:
            continue
        key = text.rstrip(" \u2026.").casefold()
        replaced = False
        for index, (existing_key, existing_text) in enumerate(kept):
            if key.startswith(existing_key) or existing_key.startswith(key):
                if len(text) > len(existing_text):
                    kept[index] = (key, text)
                replaced = True
                break
        if not replaced:
            kept.append((key, text))
    return tuple(text for _key, text in kept)


def trim_to_word(text: str, max_chars: int) -> str:
    """Shorten to `max_chars` without ending mid-word.

    The whole point of this module is that a span is cut by grammar and not
    by arithmetic, and the last line of it was `clean[:max_chars]`. A reader
    meeting "...with unified content manag" learns the same thing they learn
    from a quote that begins mid-word: that nothing here is reading.

    A clause boundary the reader already pauses at is preferred; failing
    that, the last whole word, marked as an elision so the quote does not
    claim the sentence ended there.
    """
    body = str(text or "")
    if len(body) <= max_chars:
        return body
    head = body[:max_chars]
    # a sentence that genuinely ends inside the budget needs no marker
    for mark in (". ", "! ", "? "):
        cut = head.rfind(mark)
        if cut >= max_chars // 2:
            return head[:cut + 1].rstrip()
    for mark in ("; ", ", ", " -- "):
        cut = head.rfind(mark)
        if cut >= max_chars // 2:
            return head[:cut].rstrip(" ,;-") + " \u2026"
    cut = head.rfind(" ")
    if cut <= 0:
        # one unbroken token longer than the budget: there is no honest
        # way to shorten it, so quote nothing.
        return ""
    return _drop_dangling(head[:cut].rstrip(" ,;:-")) + " \u2026"


#: Words that join a clause to the next one. A quote that ENDS on one was
#: cut in the middle of an idea, and the reader is left holding a
#: conjunction. MEASURED LIVE on Netskope (bbb75261):
#:
#:     "My job combines the usual CISO responsibilities alongside daily
#:      self and"
#:
#: The cut was already at a word boundary, which is what `trim_to_word`
#: promised; a word boundary is not a grammatical one. Same rule the
#: decision-object extractor applies to a captured phrase, for the same
#: reason.
_DANGLING = frozenset("""
and or but nor so yet for the a an of to with from by at in on as that which
is are was were be been being has have had will would can could should may
than then when while if unless because about into onto over under
""".split())


def _drop_dangling(text: str) -> str:
    """Trim trailing joining words, so a quote ends on an idea."""
    words = text.split()
    while words and words[-1].lower().strip(",;:") in _DANGLING:
        words.pop()
    return " ".join(words)


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
        # A LIST ITEM IS A SENTENCE WITH A GLYPH IN FRONT OF IT. Dropping the
        # marker keeps the item; keeping the marker makes every list item
        # unquotable and throws away real evidence.
        clean = clean.lstrip(_BULLETS + " ").strip()
        if len(clean) < 30 or furniture_reason(clean):
            continue
        # the sentence the match is INSIDE wins outright
        if offset <= target < offset + len(sentence):
            chosen = trim_to_word(clean, max_chars)
            return chosen if is_quotable(chosen) else ""
        distance = abs(offset - target)
        if best_distance is None or distance < best_distance:
            best, best_distance = clean, distance
    if best is None:
        return ""
    chosen = trim_to_word(best, max_chars)
    return chosen if is_quotable(chosen) else ""


def _word_snapped(body: str, start: int, end: int, max_chars: int) -> str:
    """Fallback that at least never begins mid-word."""
    left = max(0, start - 200)
    right = min(len(body), end + 200)
    while left > 0 and body[left - 1].isalnum():
        left -= 1
    while right < len(body) and body[right].isalnum():
        right += 1
    return trim_to_word(" ".join(body[left:right].split()), max_chars)

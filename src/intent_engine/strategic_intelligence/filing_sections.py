"""Read a filing from its sections, not from its first 280 characters.

`derive_observations` builds every observation's excerpt as

    doc["meta_description"] or doc["text_content"][:280]

For a marketing page that is reasonable. For a 10-K it is the COVER PAGE --
form title, filing-status checkboxes, state of incorporation, IRS number --
which is why a run that retrieved Datadog's annual report produced no
filing-derived observation at all, and why "What was verified" fell back to
blog marketing once the cover page was filtered out.

Filtering furniture was necessary and was not sufficient: removing the wrong
280 characters does not find the right ones.

WHAT THIS DOES. Locate the commercially meaningful Items in a filing and
return the first substantive prose from the highest-priority one present.
Item 1 (Business), Item 1A (Risk Factors) and Item 7 (MD&A) carry what a
reader actually needs; the rest of the document is tables, notes and exhibits.

WHAT THIS DOES NOT DO. It does not summarise, rewrite or interpret. It selects
an existing span and records which section it came from, so provenance stays
exact and the interpretation layer stays responsible for meaning.

NAVIGATION IS NOT BODY. Every 10-K prints its Item headings twice: once in the
table of contents, once at the section itself. The table of contents entries
sit within the first few thousand characters and are followed immediately by
another heading or a page number rather than prose. A heading only counts as a
body heading when substantive text follows it.
"""
from __future__ import annotations

import re

from intent_engine.strategic_intelligence import filing_hygiene as FH

#: Ordered by how much a reader gets from them.
SECTION_PRIORITY = (
    "item_7",    # Management's Discussion and Analysis
    "item_1",    # Business
    "item_1a",   # Risk Factors
    "item_3",    # Legal Proceedings
    "item_7a",   # Market Risk
)

SECTION_NAMES = {
    "item_1": "Item 1 (Business)",
    "item_1a": "Item 1A (Risk Factors)",
    "item_3": "Item 3 (Legal Proceedings)",
    "item_7": "Item 7 (Management's Discussion and Analysis)",
    "item_7a": "Item 7A (Quantitative and Qualitative Disclosures About "
               "Market Risk)",
}

# Tolerant of case, of "ITEM 1." / "Item 1 -" / "Item 1:" and of the &#160;
# spacing these documents are full of.
_HEADINGS = (
    ("item_1a", re.compile(r"item\s*1a\b[\s.:\-—]*(?:risk\s+factors)?", re.I)),
    ("item_7a", re.compile(r"item\s*7a\b[\s.:\-—]*", re.I)),
    ("item_7", re.compile(r"item\s*7\b[\s.:\-—]*"
                          r"(?:management'?s\s+discussion)?", re.I)),
    ("item_3", re.compile(r"item\s*3\b[\s.:\-—]*(?:legal\s+proceedings)?",
                          re.I)),
    ("item_1", re.compile(r"item\s*1\b[\s.:\-—]*(?:business)?", re.I)),
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_MIN_PROSE = 80        # a heading followed by less than this is navigation
_MAX_SPAN = 600


def looks_like_filing(text: str, url: str = "") -> bool:
    """True when this document is a regulatory filing rather than a web page.

    Deliberately conservative: it must show filing structure, not merely
    mention a form name somewhere in a blog post.
    """
    blob = (text or "")[:20000]
    if "sec.gov" in (url or "").lower():
        return True
    hits = sum(bool(re.search(p, blob, re.I)) for p in (
        r"pursuant to section 13 or 15\(d\)",
        r"securities exchange act of 19\d\d",
        r"item\s*1a\b.{0,40}risk factors",
        r"item\s*7\b.{0,60}management'?s discussion",
        r"commission file (?:number|no)",
    ))
    return hits >= 2


def _normalise(text: str) -> str:
    return re.sub(r"[   ]", " ", text or "")


def find_sections(text: str) -> dict:
    """Map section key -> body text, for body headings only.

    A heading whose following text is shorter than `_MIN_PROSE` before the next
    heading is a table-of-contents entry and is skipped.
    """
    blob = _normalise(text)
    marks = []
    for key, pattern in _HEADINGS:
        for m in pattern.finditer(blob):
            marks.append((m.start(), m.end(), key))
    marks.sort()

    out: dict = {}
    for i, (start, end, key) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(blob)
        body = blob[end:stop].strip()
        if len(body) < _MIN_PROSE:
            continue          # navigation entry, not the section itself
        # The LAST qualifying occurrence wins: the body always follows the
        # contents page, so a later match is the real section.
        out[key] = body
    return out


def _first_substantive_sentences(body: str, *, limit: int = _MAX_SPAN) -> str:
    """The first prose that is not furniture, up to `limit` characters."""
    parts = []
    for sentence in _SENTENCE.split(body):
        s = " ".join(sentence.split())
        if len(s) < 40 or FH.is_filing_furniture(s):
            continue
        parts.append(s)
        if sum(len(p) for p in parts) >= limit:
            break
    joined = " ".join(parts).strip()
    return joined[:limit].rstrip()


def best_excerpt(text: str) -> tuple:
    """Return `(excerpt, section_label)` for a filing, or `("", "")`.

    Fails closed: a malformed or section-free document returns empty strings
    rather than a guess, so the caller keeps its existing behaviour.
    """
    sections = find_sections(text)
    if not sections:
        return "", ""
    for key in SECTION_PRIORITY:
        body = sections.get(key)
        if not body:
            continue
        excerpt = _first_substantive_sentences(body)
        if len(excerpt) >= _MIN_PROSE:
            return excerpt, SECTION_NAMES[key]
    return "", ""

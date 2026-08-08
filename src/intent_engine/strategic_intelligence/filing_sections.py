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
#:
#: `item_2` is LAST and is there for quarterly reports, where MD&A is Item 2
#: rather than Item 7. In an annual report Item 2 is Properties, which is why
#: it must never be reached before Item 7, Item 1 and Item 1A have been tried
#: -- and in a 10-K at least one of those is always present.
SECTION_PRIORITY = (
    "item_7",    # Management's Discussion and Analysis (annual)
    "item_1",    # Business
    "item_1a",   # Risk Factors
    "item_3",    # Legal Proceedings
    "item_7a",   # Market Risk
    "item_2",    # MD&A in a 10-Q; Properties in a 10-K
)

SECTION_NAMES = {
    "item_1": "Item 1 (Business)",
    "item_1a": "Item 1A (Risk Factors)",
    "item_2": "Item 2",
    "item_3": "Item 3 (Legal Proceedings)",
    "item_7": "Item 7 (Management's Discussion and Analysis)",
    "item_7a": "Item 7A (Quantitative and Qualitative Disclosures About "
               "Market Risk)",
    "item_8": "Item 8 (Financial Statements and Supplementary Data)",
}

# Tolerant of case, of "ITEM 1." / "Item 1 -" / "Item 1:" and of the &#160;
# spacing these documents are full of.
# The heading MATCH stops at the item number. Stripping the human title is
# `_TITLE_TAIL`'s single job -- when both tried, the heading consumed
# "Management's Discussion" and the title stripper (anchored at the start) then
# saw "and Analysis of Financial Condition..." and left it in the excerpt.
_HEADINGS = (
    ("item_1a", re.compile(r"item\s*1a\b[\s.:\-\u2014]*", re.I)),
    ("item_7a", re.compile(r"item\s*7a\b[\s.:\-\u2014]*", re.I)),
    ("item_7", re.compile(r"item\s*7\b[\s.:\-\u2014]*", re.I)),
    ("item_8", re.compile(r"item\s*8\b[\s.:\-\u2014]*", re.I)),
    ("item_3", re.compile(r"item\s*3\b[\s.:\-\u2014]*", re.I)),
    ("item_2", re.compile(r"item\s*2\b[\s.:\-\u2014]*", re.I)),
    ("item_1", re.compile(r"item\s*1\b[\s.:\-\u2014]*", re.I)),
)

# EVERY "Item N" is a BOUNDARY, even the ones nothing is extracted from.
# Measured live: only five items were recognised, so Item 5's heading --
# "Market for Registrant's Common Equity, Related Stockholder Matters and
# Issuer Purchases of Equity Securities" -- sat inside the previous section's
# body, was long enough to pass the prose check, and became the excerpt. A
# section must end where the next section starts, not where the next
# INTERESTING section starts.
_ANY_ITEM = re.compile(r"item\s*\d{1,2}[a-z]?\b[\s.:\-\u2014]*", re.I)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_MIN_PROSE = 80        # a heading followed by less than this is navigation
_MAX_SPAN = 600

# A CROSS-REFERENCE IS NOT A HEADING. Filings refer to each other constantly:
# MD&A says "see Part I, Item 1A. Risk Factors", Item 1 says "included in
# Item 8". Measured on a full Datadog 10-K, those references ended MD&A after
# 4,263 characters and then labelled 23,410 characters of MD&A prose as Item
# 1A -- so an excerpt cited to Risk Factors was actually management's
# discussion.
#
# A real heading is the whole start of its line; a reference sits inside a
# sentence. The rule only applies when the document HAS line-start headings,
# so a fixture stored as one unbroken blob keeps its previous behaviour rather
# than losing every section.
_LINE_START = re.compile(r"(?:\A|\n)[ \t]{0,4}$")


def _at_line_start(blob: str, position: int) -> bool:
    return bool(_LINE_START.search(blob[max(0, position - 8):position]))


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


#: The heading's own title, which follows "Item 7" and is not body prose.
#: Measured live: the Item 7 heading matched, but the filing writes
#: "Management’s" with a CURLY apostrophe, so an optional `management'?s`
#: group never consumed it -- and "management's Discussion and Analysis of
#: Financial Condition and Results of Operations." became the excerpt. The
#: title is stripped after the match rather than guessed inside it.
_TITLE_TAIL = re.compile(
    r"^(?:"
    r"management'?s\s+discussion\s+and\s+analysis"
    r"(?:\s+of\s+financial\s+condition)?"
    r"(?:\s+and\s+results\s+of\s+operations)?"
    r"|quantitative\s+and\s+qualitative\s+disclosures"
    r"(?:\s+about\s+market\s+risk)?"
    r"|risk\s+factors|legal\s+proceedings|business|properties"
    r"|financial\s+statements(?:\s+and\s+supplementary\s+data)?"
    r")[\s.:;,\-\u2014]*", re.I)


def _normalise(text: str) -> str:
    # Curly quotes normalised FIRST: filings use them and every pattern here
    # is written with the straight forms.
    text = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"[\xa0\u2007\u202f]", " ", text)


def section_spans(text: str) -> list:
    """Ordered body sections with their offsets INTO `text`.

    Each entry is `{key, name, heading_start, body_start, body_end, body}`.
    A heading whose following text is shorter than `_MIN_PROSE` before the next
    heading is a table-of-contents entry and is skipped.

    Offsets are usable against the caller's own string: `_normalise` only
    substitutes single characters for single characters, so it never shifts a
    position. That is what lets retention record where a kept excerpt came
    from instead of storing a second copy of the filing.
    """
    blob = _normalise(text)
    marks = []
    for key, pattern in _HEADINGS:
        for m in pattern.finditer(blob):
            marks.append((m.start(), m.end(), key))
    # Boundary-only marks: they terminate the previous section but nothing is
    # extracted from them. `None` keys are skipped when building the result.
    known = {m[0] for m in marks}
    for m in _ANY_ITEM.finditer(blob):
        if m.start() not in known:
            marks.append((m.start(), m.end(), None))
    anchored = [m for m in marks if _at_line_start(blob, m[0])]
    if anchored:
        marks = anchored
    marks.sort()

    by_key: dict = {}
    for i, (start, end, key) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(blob)
        if key is None:
            continue                  # boundary only
        raw = blob[end:stop]
        lead = len(raw) - len(raw.lstrip())
        title = _TITLE_TAIL.match(raw[lead:])
        body_start = end + lead + (title.end() if title else 0)
        body = blob[body_start:stop].strip()
        if len(body) < _MIN_PROSE:
            continue          # navigation entry, not the section itself
        offset = blob.index(body[:64], body_start) if body else body_start
        # The LAST qualifying occurrence wins: the body always follows the
        # contents page, so a later match is the real section.
        #
        # EXCEPT when the later one is a different section with the same
        # number. A 10-Q prints "Item 2" twice -- Part I is Management's
        # Discussion and Analysis, Part II is Unregistered Sales of Equity
        # Securities -- and last-wins took the second. A heading whose title
        # this module recognises is one of the sections it models; an
        # unrecognised title reusing the same number is not, and must not
        # displace it.
        titled = title is not None
        if key in by_key and by_key[key]["titled"] and not titled:
            continue
        by_key[key] = {
            "key": key, "name": SECTION_NAMES.get(key, key), "kind": "item",
            "heading_start": start, "body_start": offset,
            "body_end": offset + len(body), "body": body, "titled": titled,
        }
    return sorted(by_key.values(), key=lambda s: s["heading_start"])


def find_sections(text: str) -> dict:
    """Map section key -> body text, for body headings only."""
    return {span["key"]: span["body"] for span in section_spans(text)}


#: Where a section stops explaining itself and starts saying something.
#:
#: Filtering the preamble sentence by sentence does not work: removing one
#: promotes the next. Measured across five filers, the opening of Item 7 was
#: five different sentences that all describe the document -- how to read the
#: MD&A, which statements are forward-looking, what is incorporated by
#: reference -- before any of them described the company. What they share is
#: not wording, it is position: the substance begins at the first real
#: subheading. Datadog, NVIDIA and Amazon call it "Overview"; others use
#: "Executive Summary" or go straight to "Results of Operations".
_SUBSTANCE_HEADING = re.compile(
    r"^\s*(?:overview|executive\s+summary|business\s+overview|our\s+business"
    r"|company\s+overview|introduction|general|results\s+of\s+operations)"
    r"\s*[.:]?\s*$", re.I | re.M)
_PREAMBLE_WINDOW = 15_000


def _skip_preamble(body: str) -> str:
    """`body` from its first substantive subheading, if it has one nearby."""
    match = _SUBSTANCE_HEADING.search(body[:_PREAMBLE_WINDOW])
    return body[match.end():] if match else body


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


#: A quarterly report numbers its Items differently, and reading it with the
#: annual order picks the wrong one. In a 10-Q, Item 1 is Financial Statements
#: and MD&A is Item 2 -- so the annual priority reached the notes to the
#: accounts first. Measured live on Datadog's 10-Q, that produced "Defending
#: such proceedings is costly... The results of any current or future
#: litigation cannot be predicted with certainty" as the quarter's excerpt:
#: litigation boilerplate, true of every public company, shown to a reader
#: under the label "Regulatory or investor filing".
QUARTERLY_SECTION_PRIORITY = (
    "item_2",    # Management's Discussion and Analysis (quarterly)
    "item_1a",   # Risk Factors
    "item_3",    # Legal Proceedings
    "item_1",    # Financial Statements -- notes, tables, boilerplate
)

#: The citation a reader sees. "Item 2" alone says nothing; which Item 2 it is
#: depends on the form, so the label does too.
QUARTERLY_SECTION_NAMES = dict(
    SECTION_NAMES,
    item_2="Item 2 (Management's Discussion and Analysis)",
    item_1="Item 1 (Financial Statements)",
)


def best_excerpt(text: str, *, form: str = "") -> tuple:
    """Return `(excerpt, section_label)` for a filing, or `("", "")`.

    Fails closed: a malformed or section-free document returns empty strings
    rather than a guess, so the caller keeps its existing behaviour.
    """
    sections = find_sections(text)
    if not sections:
        return "", ""
    quarterly = (form or "").upper().strip().startswith("10-Q")
    priority = QUARTERLY_SECTION_PRIORITY if quarterly else SECTION_PRIORITY
    names = QUARTERLY_SECTION_NAMES if quarterly else SECTION_NAMES
    for key in priority:
        body = sections.get(key)
        if not body:
            continue
        # Past the preamble first; the whole section only if that finds
        # nothing, because a section with no subheading still has content.
        for candidate in (_skip_preamble(body), body):
            excerpt = _first_substantive_sentences(candidate)
            if len(excerpt) >= _MIN_PROSE:
                return excerpt, names[key]
    return "", ""


# ===========================================================================
# A FILING WRITTEN BY SOMEONE ELSE
# ===========================================================================
#
# `third_party_filings` retrieves filings by OTHER registrants that name the
# subject, and that is a genuinely independent vantage point -- the only one
# most runs get. But the excerpt was chosen the same way as for the subject's
# own filing: highest-priority Item, first substantive prose. In a filing
# written by someone else, that is the FILER describing ITSELF.
#
# Measured live on the deployed preview, analysing Stripe:
#
#   "Headquartered in Pittsford, New York, Infinite Group is a developer of
#    cybersecurity software and related cybersecurity consulting..."
#
# Accurate, accountable, correctly cited, and about the wrong company. The
# reader is told this supports a proposition about Stripe.
#
# WHAT IS SELECTED INSTEAD. The sentences that actually name the subject. If
# none do, this returns "" and the caller drops the document -- a third-party
# filing whose usable content cannot be tied to the subject is not evidence
# about the subject, and showing it anyway is what created the problem.

#: Corporate-form suffixes, stripped so "Datadog, Inc." matches "Datadog".
_SUFFIXES = re.compile(
    r"[,\s]+(?:inc|inc\.|incorporated|corp|corp\.|corporation|co|co\.|"
    r"company|ltd|ltd\.|limited|llc|l\.l\.c\.|plc|n\.v\.|nv|s\.a\.|sa|ag|"
    r"gmbh|holdings?|group|technologies|technology|labs?)\.?$", re.I)

#: How much context around a naming sentence is worth keeping.
_SUBJECT_SPAN_LIMIT = 700
_MIN_SUBJECT_SENTENCE = 50


def subject_aliases(subject: str) -> tuple:
    """Names that mean THIS company, and no shorter ones.

    Deliberately does NOT include a leading token of a multi-word name. A
    previous cycle matched "Linear Minerals Corp." on the alias "Linear" and
    attributed a mining company's disclosures to a software company; two of
    the three fixes attempted then were worse than the bug. A suffix is
    removable because it is not distinguishing. A first word is not.
    """
    name = " ".join((subject or "").split())
    if not name:
        return ()
    out = [name]
    stripped = _SUFFIXES.sub("", name).strip(" ,.")
    if stripped and stripped.lower() != name.lower() and len(stripped) >= 3:
        out.append(stripped)
    return tuple(out)


def subject_span(text: str, subject: str, *,
                 limit: int = _SUBJECT_SPAN_LIMIT) -> str:
    """The sentences in someone else's filing that name `subject`.

    Returns "" when the subject is never named in substantive prose — the
    caller must then drop the document rather than fall back to the filer's
    own description of itself.
    """
    aliases = subject_aliases(subject)
    if not aliases:
        return ""
    patterns = [re.compile(rf"\b{re.escape(a)}\b", re.I) for a in aliases]
    blob = _normalise(text)
    kept: list = []
    for sentence in _SENTENCE.split(blob):
        line = " ".join(sentence.split())
        if len(line) < _MIN_SUBJECT_SENTENCE or FH.is_filing_furniture(line):
            continue
        if not any(p.search(line) for p in patterns):
            continue
        kept.append(line)
        if sum(len(k) for k in kept) >= limit:
            break
    return " ".join(kept)[:limit].rstrip()

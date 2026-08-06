"""Read a regulatory filing as the document a browser renders.

WHY THIS EXISTS -- MEASURED, NOT INFERRED.

`parse_html` buffers character data only while a `_BLOCK` tag is open, and its
block set is the vocabulary of a hand-written web page: `p`, `h1`-`h6`, `li`,
`td`, `blockquote`, `dt`, `dd`. Datadog's 2025 annual report contains

    <p>   0        <h1>-<h6>   0        <li>  0
    <td>  7,147    <div>   1,878       <span>  4,857

Every narrative paragraph in that filing lives in `<div><span>...</span></div>`,
so every narrative paragraph was discarded. What survived was the 7,147 table
cells: the cover page, the table of contents, the financial-statement grids and
the signature page -- 25,787 characters out of a 2,086,014-byte document, ending
on the last signature.

The traversal was never truncated and never stopped early; the parser walked the
whole document and threw away 93% of it. That distinction matters, because it
means no byte cap, fetch budget or document-selection change could have fixed
it. Item 7 was absent from the text, `filing_detectors.detect` therefore matched
nothing, no filing-derived observation was ever proposed, and the live Datadog
decision fell back to marketing copy from the company blog.

Measured on the same document through this module: 381,098 characters, Items
1, 1A, 3, 7 and 7A all located, and nine filing propositions where there were
none.

WHAT THIS MODULE IS. A filing-shaped reader: block/inline text extraction that
does not care which tags a filing agent chose, exclusion of the inline-XBRL
metadata a browser never shows, an explicit quality verdict, and section-aware
retention so the stored excerpt cannot be all cover page and no MD&A.

WHAT IT IS NOT. It is not company-specific -- nothing here names an issuer, a
filing agent or a document. It is not a second source of truth for what a
section IS: section boundaries come from `filing_sections`, which owns that
vocabulary. And it does not interpret: it selects spans of the filer's own
words and records where each came from.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from html.parser import HTMLParser

from intent_engine.company_ingestion.parsing import _terminated

FILING_PARSER_VERSION = "filing-text/1"

# Never rendered: executable or presentational payloads.
_DROP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe",
              "head"}

# Inline-XBRL machine metadata. `<ix:hidden>` exists precisely to carry facts
# the browser must NOT display, and `<ix:header>` wraps the contexts, units and
# references -- CIK numbers, ISO currency codes, FASB namespace URIs. Admitting
# them turns a filing into a bag of identifiers that no detector can read and
# that a reader would recognise instantly as machine exhaust.
#
# `<ix:continuation>` is deliberately NOT here: a continuation carries the rest
# of a fact that IS displayed, in document order, and dropping it removes real
# sentences from the middle of a paragraph.
_HIDDEN_TAGS = {"ix:hidden", "ix:header", "ix:references", "ix:resources",
                "ix:relationship", "xbrli:xbrl", "xbrl"}

# A boundary between two pieces of text a reader sees on separate lines.
# `div` is here and is the whole point: filing agents lay out prose in nested
# divs, and a parser that does not treat a div as a line break either loses the
# text or welds the entire filing into one line.
_BLOCK_TAGS = {"p", "div", "section", "article", "main", "aside", "header",
               "footer", "nav", "table", "tr", "td", "th", "caption",
               "ul", "ol", "li", "dl", "dt", "dd", "blockquote", "figure",
               "figcaption", "pre", "center", "form", "fieldset", "address",
               "h1", "h2", "h3", "h4", "h5", "h6"}

_VOID_FLUSH = {"br", "hr"}

#: Bounds. A filing is untrusted input; every loop below is finite.
MAX_FILING_TEXT_CHARS = 4_000_000
MAX_FILING_LINES = 400_000

#: A short line repeated at least this often is running page furniture
#: ("Table of Contents", the issuer name in the page header, a page number).
#: Only repeats are dropped, and the first occurrence always survives, so a
#: heading that happens to be short is never removed from the document.
_FURNITURE_MAX_CHARS = 80
_FURNITURE_MIN_REPEATS = 3


def _hidden_style(attrs: dict) -> bool:
    """True for an element a browser will not paint."""
    style = (attrs.get("style") or "").lower().replace(" ", "")
    if "display:none" in style or "visibility:hidden" in style:
        return True
    return (attrs.get("hidden") is not None
            or (attrs.get("aria-hidden") or "").lower() == "true")


class _FilingExtractor(HTMLParser):
    """Block/inline text extraction that tolerates browser-recoverable HTML.

    Two rules, and nothing else decides what becomes a line:

      * text accumulates into an inline buffer regardless of which element it
        sits in, so `<span>`, `<ix:nonFraction>` and bare text all contribute;
      * a block element boundary flushes that buffer as one line.

    Table rows are assembled from their cells rather than emitted cell by cell:
    a filing states "Revenue $ 3,467 $ 2,684 29 %" across four `<td>`s, and
    four separate lines lose the association a reader reads at a glance.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list = []
        self.title = ""
        self.meta_description = ""
        self.canonical_url = None
        self.modified_date = ""
        self.links: list = []
        self.node_count = 0
        self.hidden_regions = 0
        self.overflowed = False
        self._buffer: list = []
        # Open table rows, innermost last, each holding its own cells. A stack
        # because filings nest tables inside cells for layout.
        self._rows: list = []
        # Every open element, so an end tag can be resolved without attributes.
        self._stack: list = []
        self._drop_depth = 0
        self._in_title = False

    # --- emission ---------------------------------------------------------
    def _emit(self, text: str) -> None:
        if len(self.lines) >= MAX_FILING_LINES:
            self.overflowed = True
            return
        if self._rows:
            self._rows[-1].append(text)
        else:
            self.lines.append(text)

    def _flush(self) -> None:
        text = " ".join("".join(self._buffer).split())
        self._buffer = []
        if text:
            self._emit(text)

    # --- tags -------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self.node_count += 1
        tag = tag.lower()
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            if (attrs.get("name") or "").lower() == "description":
                self.meta_description = (attrs.get("content") or "").strip()
            prop = (attrs.get("property") or "").lower()
            if prop == "og:description" and not self.meta_description:
                self.meta_description = (attrs.get("content") or "").strip()
            return
        if tag == "link" and (attrs.get("rel") or "").lower() == "canonical":
            self.canonical_url = attrs.get("href")
            return
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in _VOID_FLUSH:
            self._flush()
            return
        drop = (tag in _DROP_TAGS or tag in _HIDDEN_TAGS
                or _hidden_style(attrs))
        if drop or tag in _BLOCK_TAGS:
            # Whatever was accumulating belongs to the text BEFORE this
            # boundary, dropped region or not.
            self._flush()
        self._stack.append((tag, drop, tag in _BLOCK_TAGS, tag == "tr"))
        if drop:
            self._drop_depth += 1
            self.hidden_regions += 1
            return
        if tag == "tr":
            self._rows.append([])

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in _VOID_FLUSH:
            self._flush()
            return
        if tag in ("meta", "link", "a"):
            self.handle_starttag(tag, attrs)
            self._stack and self._close(self._stack.pop())

    def _close(self, entry) -> None:
        _tag, drop, block, row = entry
        if drop:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if row and self._rows:
            self._flush()                     # trailing cell text
            cells = self._rows.pop()
            joined = " ".join(cell for cell in cells if cell)
            if joined:
                self._emit(joined)
            return
        if block:
            self._flush()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            return
        if tag in _VOID_FLUSH:
            return
        # Close the innermost element this tag opened and everything left open
        # inside it. Filings leave tags unclosed; an element that never closed
        # must not swallow the rest of the document.
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                for entry in reversed(self._stack[index:]):
                    self._close(entry)
                del self._stack[index:]
                return

    def handle_data(self, data):
        if self._in_title:
            if len(self.title) < 400:
                self.title += data
            return
        if self._drop_depth:
            return
        self._buffer.append(data)

    def finish(self) -> None:
        """Close what the document left open, so the tail is not lost."""
        self._flush()
        while self._stack:
            self._close(self._stack.pop())
        self._flush()


def _strip_repeated_furniture(lines: list) -> list:
    """Drop repeats of running page furniture, keeping the first occurrence.

    A paginated filing prints "Table of Contents" and the issuer's name at
    every page break -- 150 times in a 10-K. Removing repeats keeps the
    document readable without a global de-duplication that would delete the
    SECOND occurrence of an Item heading, which is the one that marks the body.
    """
    counts = Counter(line.lower() for line in lines)
    out, seen = [], set()
    for line in lines:
        key = line.lower()
        if len(line) <= _FURNITURE_MAX_CHARS and \
                counts[key] >= _FURNITURE_MIN_REPEATS:
            if key in seen:
                continue
            seen.add(key)
        out.append(line)
    return out


def extract_filing_text(html: str) -> dict:
    """Full rendered text of a filing document. Deterministic and bounded."""
    extractor = _FilingExtractor()
    parse_error = ""
    try:
        extractor.feed(html or "")
    except Exception as exc:                                  # noqa: BLE001
        # Keep whatever was extracted; the quality verdict decides whether a
        # partial read is usable. Recording the reason keeps "the parser gave
        # up" distinguishable from "the filing was short".
        parse_error = type(exc).__name__
    try:
        extractor.finish()
    except Exception as exc:                                  # noqa: BLE001
        parse_error = parse_error or type(exc).__name__
    lines = _strip_repeated_furniture(extractor.lines)
    text = "\n".join(_terminated(line) for line in lines)
    if len(text) > MAX_FILING_TEXT_CHARS:
        text = text[:MAX_FILING_TEXT_CHARS]
        extractor.overflowed = True
    return {
        "text": text,
        "lines": lines,
        "title": extractor.title.strip(),
        "meta_description": extractor.meta_description,
        "canonical_url": extractor.canonical_url,
        "modified_date": extractor.modified_date,
        "links": extractor.links,
        "content_hash": hashlib.sha256((html or "").encode()).hexdigest(),
        "parser_version": FILING_PARSER_VERSION,
        "node_count": extractor.node_count,
        "hidden_regions": extractor.hidden_regions,
        "blocks_found": len(lines),
        "overflowed": extractor.overflowed,
        "parse_error": parse_error,
    }


# --- extraction quality --------------------------------------------------------
#
# "We retrieved the 10-K" and "we can read the 10-K" were the same fact to every
# gate downstream, which is how a cover page was carried for weeks as an annual
# report. These states make the difference sayable.

FULL_BODY_CONFIRMED = "FULL_BODY_CONFIRMED"
SUBSTANTIVE_PARTIAL_BODY = "SUBSTANTIVE_PARTIAL_BODY"
FRONT_ONLY = "FRONT_ONLY"
INDEX_ONLY = "INDEX_ONLY"
COVER_ONLY = "COVER_ONLY"
XBRL_METADATA_ONLY = "XBRL_METADATA_ONLY"
SEC_BLOCKED = "SEC_BLOCKED"
MALFORMED = "MALFORMED"
UNSUPPORTED = "UNSUPPORTED"

QUALITY_STATES = (FULL_BODY_CONFIRMED, SUBSTANTIVE_PARTIAL_BODY, FRONT_ONLY,
                  INDEX_ONLY, COVER_ONLY, XBRL_METADATA_ONLY, SEC_BLOCKED,
                  MALFORMED, UNSUPPORTED)

#: Quality states a consumer may treat as readable filing evidence.
USABLE_QUALITY = frozenset({FULL_BODY_CONFIRMED, SUBSTANTIVE_PARTIAL_BODY})

#: Forms that carry narrative Items. An 8-K or an exhibit legitimately has
#: none, and demanding Item 7 of them would report every current report as
#: broken.
_PERIODIC_FORM_PREFIXES = ("10-K", "10-Q", "20-F", "40-F", "S-1", "S-4",
                           "424B", "10-KT", "10-QT", "11-K")

#: Sections that only exist past the front of a periodic filing. Their absence
#: when the front is present is the exact signature of a front-only read.
_LATE_SECTIONS = ("item_2", "item_3", "item_7", "item_7a", "item_8")
_FRONT_SECTIONS = ("item_1", "item_1a")

_BLOCK_MARKERS = (
    "your request originated from an undeclared automated tool",
    "request rate threshold exceeded",
    "you have exceeded the sec's traffic limit",
)
_INDEX_MARKERS = (
    "document format files",
    "data files",
    "seq description document type size",
    "filing date period of report",
)
_SENTENCE_END = re.compile(r"[.!?][\"')\]]?(?:\s|$)")

#: Below this much prose a periodic filing has not delivered a body, whatever
#: else it contains.
MIN_FULL_BODY_CHARS = 25_000
MIN_SUBSTANTIVE_CHARS = 4_000
#: A large response that yields almost no text is being mis-parsed, even if
#: what it did yield happens to contain a heading.
SUSPICIOUS_TEXT_RATIO = 0.02
LARGE_RAW_CHARS = 200_000


def _is_periodic(form: str) -> bool:
    upper = (form or "").upper().strip()
    return any(upper.startswith(p) for p in _PERIODIC_FORM_PREFIXES)


def _prose_chars(text: str) -> int:
    """Characters sitting in lines that read as sentences, not grid cells."""
    total = 0
    for line in (text or "").split("\n"):
        stripped = line.strip()
        if len(stripped) >= 120 and " " in stripped:
            total += len(stripped)
    return total


#: An accession carries the filing AND its XBRL machinery. A schema or a
#: linkbase is a real document that yields real strings — element labels,
#: documentation annotations — and without this it reads as a short filing
#: with unusual prose rather than as machinery.
_XBRL_ROOTS = ("<xsd:schema", "<schema xmlns", "<xbrli:xbrl", "<xbrl ",
               "<link:linkbase", "<linkbase")
#: Vocabulary that only appears when XBRL machinery has leaked into the text.
_XBRL_TOKENS = ("us-gaap", "dei:", "xbrli", "iso4217", "fasb.org",
                "xbrl.org", "linkbase")


def classify_extraction(*, text, raw_chars, form="", sections=None,
                        truncated=False, status_code=200, mime_type="text/html",
                        parse_error="", raw_head="") -> dict:
    """An explicit verdict on what was actually read, plus its diagnostics.

    Fails toward the honest end: a state is only FULL_BODY_CONFIRMED when the
    evidence for it is positive, never because nothing contradicted it.
    """
    text = text or ""
    sections = dict(sections or {})
    body = text.strip()
    lowered = body[:200_000].lower()
    ratio = (len(body) / raw_chars) if raw_chars else 0.0
    prose = _prose_chars(body)
    front = [k for k in _FRONT_SECTIONS if sections.get(k)]
    late = [k for k in _LATE_SECTIONS if sections.get(k)]
    diagnostics = {
        "raw_chars": int(raw_chars or 0),
        "text_chars": len(body),
        "prose_chars": prose,
        "text_ratio": round(ratio, 5),
        "sections_found": sorted(sections),
        "front_sections": front,
        "late_sections": late,
        "sentence_count": len(_SENTENCE_END.findall(body[:200_000])),
        "truncated": bool(truncated),
        "form": (form or "").upper().strip(),
        "periodic": _is_periodic(form),
    }

    def verdict(state, reason):
        return {"quality": state, "reason": reason,
                "diagnostics": diagnostics,
                "usable": state in USABLE_QUALITY}

    if int(status_code or 200) in (403, 429) or \
            any(marker in lowered[:4000] for marker in _BLOCK_MARKERS):
        return verdict(SEC_BLOCKED,
                       "SEC returned a rate-limit or automated-tool block "
                       "instead of the document")
    if not any(prefix in (mime_type or "text/html")
               for prefix in ("html", "text/plain", "xhtml", "xml")):
        return verdict(UNSUPPORTED,
                       f"content type {mime_type!r} is not a readable filing "
                       "document")
    head = (raw_head or "").lower()
    if "<html" not in head and any(root in head for root in _XBRL_ROOTS):
        return verdict(XBRL_METADATA_ONLY,
                       "this is XBRL machinery (a schema or linkbase), not "
                       "the filing document")
    if not body:
        return verdict(MALFORMED,
                       f"no readable text extracted from {int(raw_chars or 0)} "
                       f"raw characters"
                       + (f" ({parse_error})" if parse_error else ""))
    if any(marker in lowered[:8000] for marker in _INDEX_MARKERS) and \
            len(body) < 20_000:
        return verdict(INDEX_ONLY,
                       "this is an EDGAR filing index, not the filing")
    # An XBRL instance carries facts and contexts, not sentences -- but so
    # does a cover page, which is why "no sentences" alone cannot decide this.
    # The verdict needs positive evidence of the machinery.
    if diagnostics["sentence_count"] < 5 and prose == 0 and \
            any(marker in lowered[:20000] for marker in _XBRL_TOKENS):
        return verdict(XBRL_METADATA_ONLY,
                       "the document yielded XBRL identifiers and figures but "
                       "no sentences")
    if raw_chars >= LARGE_RAW_CHARS and ratio < SUSPICIOUS_TEXT_RATIO:
        return verdict(FRONT_ONLY,
                       f"{len(body)} characters extracted from "
                       f"{int(raw_chars)} raw ({ratio:.2%}) — the body of the "
                       "document did not survive parsing")
    if not diagnostics["periodic"]:
        # A current report or exhibit has no Items to miss. It is complete when
        # it reads as a document rather than as a cover sheet.
        if prose >= 200 or len(body) >= 1_500:
            return verdict(FULL_BODY_CONFIRMED,
                           "non-periodic filing read in full")
        return verdict(COVER_ONLY,
                       "only cover-sheet furniture was extracted")
    if not sections:
        # COVER_ONLY IS A CLAIM ABOUT VOLUME, NOT ABOUT ITEM NUMBERING.
        # Measured on Shopify's 10-K/A: an amendment carries only the items it
        # amends (Part III — governance and compensation), so it has no Item 1
        # and no Item 7 by design. 145,228 characters of real prose from a
        # 741,610-byte document is a complete read of that document, and
        # calling it a cover page would have reported a healthy retrieval as
        # broken. What a cover page actually looks like is almost no prose.
        if prose >= MIN_SUBSTANTIVE_CHARS:
            return verdict(SUBSTANTIVE_PARTIAL_BODY,
                           "no standard Item section was located, but the "
                           f"document carries {prose} characters of prose — "
                           "an amendment or a non-standard structure")
        return verdict(COVER_ONLY,
                       "no Item section was located — the extract is cover "
                       "page and filing furniture")
    if front and not late:
        return verdict(FRONT_ONLY,
                       f"located {', '.join(front)} but no later section; a "
                       f"{diagnostics['form'] or 'periodic'} filing continues "
                       "past Item 1A")
    if late and prose >= MIN_FULL_BODY_CHARS and not truncated:
        return verdict(FULL_BODY_CONFIRMED,
                       f"located {len(sections)} sections including "
                       f"{', '.join(late)}")
    if late or prose >= MIN_SUBSTANTIVE_CHARS:
        return verdict(SUBSTANTIVE_PARTIAL_BODY,
                       "substantive body read"
                       + (", response truncated" if truncated else "")
                       + (f"; {prose} characters of prose"
                          if prose < MIN_FULL_BODY_CHARS else ""))
    return verdict(COVER_ONLY,
                   "sections were named but carry no substantive prose")


# --- section-aware retention ---------------------------------------------------
#
# The stored excerpt used to be `parsed["text"][:120_000]`. On a filing that is
# the worst possible 120,000 characters: Item 1. Business runs to 98,000 in a
# Datadog 10-K, so the front-truncated store held the cover page, the contents,
# and most of Business -- and stopped before MD&A. Measured on the repaired
# extract: front truncation at 120,000 carries 4 of the 9 filing propositions
# the whole document supports, losing revenue trajectory, margin trajectory,
# recurring revenue and capital intensity, which are exactly the ones a reader
# came for.
#
# The contract here is that no single section can spend the budget. Every
# section present gets an equal reserve first; only what is left over is
# redistributed by priority.

RETENTION_BUDGET = 120_000
#: The filing's own identity -- form, registrant, period, exchange -- always
#: survives, so a stored excerpt can always be tied back to what it is.
IDENTITY_CHARS = 3_000
#: No section may exceed this even when the budget is idle, so a long Item 1
#: cannot crowd out a topical span that a shorter section would have funded.
MAX_SECTION_CHARS = 24_000
MIN_SECTION_CHARS = 800

#: Retention priority. Ordered by what a reader needs from a filing, not by
#: where it appears in one.
RETENTION_PRIORITY = (
    "item_1", "item_1a", "item_7", "item_7a", "item_8",
    "results_of_operations", "competition", "customer_concentration",
    "segments", "liquidity", "capital_expenditures", "acquisitions",
    "supplier_dependency", "legal_regulatory", "item_2", "item_3",
)

TOPIC_NAMES = {
    "competition": "Competition",
    "customer_concentration": "Customer concentration",
    "segments": "Segment reporting",
    "liquidity": "Liquidity and capital resources",
    "capital_expenditures": "Capital expenditures",
    "acquisitions": "Acquisitions",
    "supplier_dependency": "Supplier dependencies",
    "legal_regulatory": "Legal and regulatory exposure",
    "results_of_operations": "Results of operations",
}

#: Topical spans, located wherever the filer put them. These are a safety net
#: for the disclosures a reader needs that do not have an Item of their own,
#: and for forms whose Item numbering differs.
_TOPIC_PATTERNS = (
    ("competition", re.compile(
        r"\bcompetiti(?:on|ve\s+landscape)\b", re.I)),
    ("customer_concentration", re.compile(
        r"customer\s+concentration"
        r"|\b(?:no\s+)?(?:single|individual|one)\s+customer\b"
        r"|\bour\s+largest\s+customers?\b"
        r"|\d{1,2}(?:\.\d)?%\s+of\s+(?:our\s+)?(?:total\s+)?revenue", re.I)),
    ("segments", re.compile(
        r"\breportable\s+segments?\b"
        r"|\boperating\s+segments?\b"
        r"|\bsegment\s+(?:reporting|information)\b", re.I)),
    ("results_of_operations", re.compile(
        r"\bgross\s+(?:profit|margin)\b"
        r"|\bcost\s+of\s+revenue\s+consists\b"
        r"|\boperating\s+(?:income|loss)\s+margin\b", re.I)),
    ("liquidity", re.compile(
        r"liquidity\s+and\s+capital\s+resources", re.I)),
    ("capital_expenditures", re.compile(
        r"\bcapital\s+expenditures?\b"
        r"|purchases?\s+of\s+property\s+and\s+equipment", re.I)),
    ("acquisitions", re.compile(
        r"\bbusiness\s+combinations?\b"
        r"|\bwe\s+(?:completed\s+the\s+)?acquir\w+\b"
        r"|\bpurchase\s+price\s+allocation\b", re.I)),
    ("supplier_dependency", re.compile(
        r"\b(?:sole|single|limited)[- ]sourc\w+\b"
        r"|\b(?:depend|rely|reliance)\w*\s+(?:heavily\s+)?(?:up)?on\b"
        r"[^.\n]{0,80}?(?:provider|supplier|vendor|manufacturer"
        r"|data\s+cent|cloud|hosting)"
        r"|\bthird[- ]party\s+(?:cloud|hosting|data\s+cent)\w*", re.I)),
    ("legal_regulatory", re.compile(
        r"legal\s+proceedings"
        r"|regulatory\s+(?:requirements|compliance|scrutiny|approval)"
        r"|data\s+protection\s+laws?", re.I)),
)
TOPIC_WINDOW = 6_000


def _section_spans(text: str) -> list:
    """Item spans with offsets, from the module that owns that vocabulary."""
    from intent_engine.strategic_intelligence.filing_sections import (
        section_spans,
    )
    return section_spans(text)


def _topic_spans(text: str, *, exclude: list) -> list:
    """Topical spans, taken from text no Item excerpt already carries.

    THIS IS WHERE THE DEEP DISCLOSURES COME FROM. Item 1A runs to 149,000
    characters in a Datadog 10-K and its reserve buys the first 24,000 — so
    customer concentration, supplier dependency and competitive intensity,
    which sit tens of thousands of characters in, are never reached by the
    section reserve alone. Excluding topics that merely fall INSIDE an Item
    was measured to cost six of nine filing propositions; what has to be
    excluded is the text already retained, not the section it belongs to.
    """
    out = []
    for key, pattern in _TOPIC_PATTERNS:
        for match in pattern.finditer(text):
            start = text.rfind("\n", 0, match.start()) + 1
            end = min(len(text), start + TOPIC_WINDOW)
            if any(start < b and a < end for a, b in exclude):
                continue
            out.append({
                "key": key, "name": TOPIC_NAMES[key], "kind": "topic",
                "heading_start": start, "body_start": start, "body_end": end,
            })
            break
    return out


def _clean_cut(span: str, limit: int) -> str:
    """`span` shortened to `limit`, ending on a sentence or a line."""
    if len(span) <= limit:
        return span
    window = span[:limit]
    for boundary in (window.rfind(". "), window.rfind(".\n"),
                     window.rfind("\n")):
        if boundary >= limit // 3:
            return window[:boundary + 1]
    cut = window.rfind(" ")
    return window[:cut] if cut >= limit // 3 else window


def retain_filing_text(text: str, *, budget: int = RETENTION_BUDGET) -> dict:
    """Bounded, section-aware retention of a filing's text.

    Returns the text to store plus the record of what was kept and where it
    came from. The full document remains canonical: every retained span
    carries its offsets into the extract it was cut from.
    """
    text = text or ""
    if len(text) <= budget:
        return {"text": text, "status": "COMPLETE", "retained": [],
                "full_text_chars": len(text), "budget": budget,
                "retained_chars": len(text)}

    rank = {key: i for i, key in enumerate(RETENTION_PRIORITY)}

    def _allocate(units, capacity):
        """Equal reserve first, then leftover by priority. Returns (map, spent).

        THE GUARANTEE LIVES HERE. Every unit is offered the same reserve before
        any unit is offered a second character, so no early section can spend
        the budget: Item 1 at 39,000 characters and Item 1A at 149,000 cannot
        between them exclude MD&A, however long they are.
        """
        units = sorted(units, key=lambda u: (rank.get(u["key"], len(rank)),
                                             u["body_start"]))
        if not units or capacity <= 0:
            return {}, 0
        share = max(MIN_SECTION_CHARS,
                    min(MAX_SECTION_CHARS, capacity // len(units)))
        allocated, spent = {}, 0
        for unit in units:
            available = max(0, unit["body_end"] - unit["body_start"])
            take = min(share, available, capacity - spent)
            if take > 0:
                allocated[id(unit)] = take
                spent += take
        for unit in units:                 # leftover, by priority
            if spent >= capacity:
                break
            available = max(0, unit["body_end"] - unit["body_start"])
            current = allocated.get(id(unit), 0)
            extra = min(MAX_SECTION_CHARS - current, available - current,
                        capacity - spent)
            if extra > 0:
                allocated[id(unit)] = current + extra
                spent += extra
        return allocated, spent

    identity = _clean_cut(text, IDENTITY_CHARS)
    remaining = max(0, budget - len(identity))
    item_spans = _section_spans(text)
    # Items and topics are funded from separate reserves. Sharing one pool let
    # the Items — which are always present and always long — take everything,
    # and the topical spans are the only route to disclosures that sit deep
    # inside a section the reserve can only reach the front of.
    item_capacity = (remaining * 2) // 3 if item_spans else 0
    item_alloc, item_spent = _allocate(item_spans, item_capacity)

    retained_ranges = [(u["body_start"], u["body_start"] + item_alloc[id(u)])
                       for u in item_spans if item_alloc.get(id(u))]
    topic_spans = _topic_spans(text, exclude=retained_ranges)
    topic_alloc, _ = _allocate(topic_spans, remaining - item_spent)

    units = list(item_spans) + list(topic_spans)
    allocated = dict(item_alloc)
    allocated.update(topic_alloc)
    if not units:
        # Bounded general fallback. Nothing was recognisable, so the honest
        # store is the front of the document, explicitly labelled as such.
        return {"text": _clean_cut(text, budget), "status": "FALLBACK_FRONT",
                "retained": [], "full_text_chars": len(text),
                "budget": budget, "retained_chars": min(len(text), budget)}

    kept = [u for u in units if allocated.get(id(u), 0) > 0]
    kept.sort(key=lambda u: u["heading_start"])

    chunks, retained = [identity], []
    for unit in kept:
        limit = allocated[id(unit)]
        heading = text[unit["heading_start"]:unit["body_start"]].strip()
        body = _clean_cut(text[unit["body_start"]:unit["body_end"]], limit)
        if not body.strip():
            continue
        piece = f"{heading}\n{body}" if heading else body
        chunks.append(piece)
        retained.append({
            "key": unit["key"],
            "name": unit.get("name", unit["key"]),
            "kind": unit.get("kind", "item"),
            "source_start": unit["body_start"],
            "source_end": unit["body_start"] + len(body),
            "retained_chars": len(body),
            "complete": len(body) >= (unit["body_end"] - unit["body_start"]),
            "excerpt_hash": hashlib.sha256(body.encode()).hexdigest()[:16],
        })
    joined = "\n".join(chunks)
    return {"text": joined, "status": "SECTION_RETAINED", "retained": retained,
            "full_text_chars": len(text), "budget": budget,
            "retained_chars": len(joined)}


# --- composed entry point ------------------------------------------------------

def is_filing_document(*, url: str = "", form: str = "", html: str = "") -> bool:
    """True when this response should be read as a regulatory filing.

    Deliberately narrow: an EDGAR-served document, or one the discovery adapter
    already identified as a filing. Ordinary web pages keep the ordinary
    parser, whose behaviour is unchanged by this module.
    """
    if (form or "").strip():
        return True
    host = (url or "").lower()
    return "sec.gov" in host or "sedarplus.ca" in host


def parse_filing_html(html: str, *, url: str = "", form: str = "",
                      truncated: bool = False, status_code: int = 200,
                      mime_type: str = "text/html") -> dict:
    """Parse, judge and retain a filing in one pass.

    The returned mapping is shape-compatible with `parse_html` so the fetch
    path is unchanged, and carries a `filing` record so no consumer has to
    re-derive from a blob what was already known here.
    """
    extracted = extract_filing_text(html)
    full_text = extracted["text"]
    try:
        from intent_engine.strategic_intelligence.filing_sections import (
            find_sections,
        )
        sections = find_sections(full_text)
    except Exception:                                         # noqa: BLE001
        sections = {}
    quality = classify_extraction(
        text=full_text, raw_chars=len(html or ""), form=form,
        sections=sections, truncated=truncated, status_code=status_code,
        mime_type=mime_type, parse_error=extracted["parse_error"],
        raw_head=(html or "")[:4000])
    retention = retain_filing_text(full_text)
    return {
        "title": extracted["title"],
        "meta_description": extracted["meta_description"],
        "canonical_url": extracted["canonical_url"],
        "modified_date": extracted["modified_date"],
        "headings": [],
        "text": retention["text"],
        "links": extracted["links"],
        "content_hash": extracted["content_hash"],
        "parser_version": FILING_PARSER_VERSION,
        "extraction_mode": "filing",
        "blocks_found": extracted["blocks_found"],
        "filing": {
            "form": (form or "").upper().strip(),
            "primary_document_url": url,
            "parser_version": FILING_PARSER_VERSION,
            "extraction_quality": quality["quality"],
            "quality_reason": quality["reason"],
            "diagnostics": quality["diagnostics"],
            "full_text_chars": retention["full_text_chars"],
            "retained_chars": retention["retained_chars"],
            "retention_status": retention["status"],
            "sections_detected": sorted(sections),
            "sections_retained": retention["retained"],
            "node_count": extracted["node_count"],
            "hidden_regions_dropped": extracted["hidden_regions"],
            "truncated": bool(truncated),
        },
    }

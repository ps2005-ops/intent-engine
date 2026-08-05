"""Canonical evidence text: one body selector, one segmentation, one gate.

WHY THIS EXISTS
---------------
Measured on the deployed preview, 17 real observations across two companies:
roughly fifteen carried no commercial event in any phrasing. They were page
furniture — "Explore the Microsoft Store for apps and games on Windows.",
"A featured collection of the latest Palantir blog posts.", and both
companies' 10-K cover pages. The cause was one line:

    excerpt = (doc.get("meta_description")
               or doc.get("text_content", "")[:280]).strip()

A marketing page's `meta_description` IS its blurb, and the first 280
characters of a filing ARE its cover page. Microsoft's Q4 earnings exhibit —
the one document in the corpus carrying a real event — was cut at
"...as compared to the corresp", one clause before a single number.

`derive_analyst_evidence` already read 1,200 characters of body, but only as a
fallback: `derive_observations` wins whenever it returns anything, so the weak
path was production. This module is the unification, not a third engine. Both
derivations now call `evidence_excerpt`, and the market translator segments
the same body with `candidates`.

WHAT IT DOES NOT DO
-------------------
It does not decide what an event is. Selecting event-bearing text and
recognising an event are different jobs, and merging them is how a furniture
sentence gets relabelled as evidence: push a classifier hard enough to find
events in "Palantir partners with world leading organizations" and it will
find one. So this module answers only "is this a real sentence from the body
of a document, rather than a heading, a slogan or a cover page" — and the
classifier downstream stays free to say no.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

EXTRACTION_VERSION = "evidence_text.v1"

#: how much body text one observation carries as its human-readable excerpt
EXCERPT_CHARS = 1200
#: how deep into a document candidate sentences are drawn from. Bounded so a
#: 300-page filing cannot turn one company into a whole cycle's work, but far
#: past the 1,200-character excerpt: an earnings release states its numbers
#: after the boilerplate, and a 10-K states its business after the cover page.
SCAN_CHARS = 40000
#: a candidate longer than this is an unsegmented block, not a sentence
MAX_SENTENCE_CHARS = 600
#: below this a candidate is a fragment, not a statement
MIN_SENTENCE_WORDS = 6
#: below this a filtered excerpt is thinner than the page it came from, and
#: the raw body is used instead. Matches the analyst layer's own floor.
MIN_USEFUL_EXCERPT_CHARS = 120


@dataclass(frozen=True)
class Candidate:
    """One bounded sentence with the lineage to find it again.

    `offset` is a character offset into the document body — deterministic,
    reproducible, and enough to point a reader at the exact sentence that
    carried a claim rather than at the page that contained it.
    """
    text: str
    offset: int
    index: int
    source_id: str = ""
    origin: str = ""

    def as_dict(self) -> dict:
        return {"text": self.text, "offset": self.offset,
                "index": self.index, "source_id": self.source_id,
                "origin": self.origin}


# --- segmentation ---------------------------------------------------------
#
# Splitting on `[.!?]` alone breaks "$90.0 billion", "Microsoft Corp.",
# "Section 13 or 15(d)" and "No. 001-37845" — and a broken number is worse
# than an unsplit paragraph, because it becomes a fact with a wrong figure in
# it. Boundaries are therefore decided, not assumed.
_ABBREVIATIONS = frozenset("""
inc corp co ltd llc lp plc sa nv ag gmbh
mr mrs ms dr prof rev hon st jr sr
u.s u.k u.n e.u
no nos fig figs sec secs art arts ch chs vol vols pp
vs etc al approx est
e.g i.e cf viz
jan feb mar apr jun jul aug sept sep oct nov dec
a.m p.m
gov sen rep gen adm col lt capt maj sgt
""".split())

# a period that closes one of these is never a boundary, whatever follows
_INITIAL = re.compile(r"(?:^|\s)[A-Z]$")
_TERMINATOR = re.compile(r"[.!?…]+[\"'’”)\]]*")


def split_sentences(text: str) -> List[Tuple[int, str]]:
    """Segment into (offset, sentence). Deterministic, no model, no guessing.

    A boundary is a terminator followed by whitespace and then something that
    can start a sentence. Everything that looks like a terminator but is not —
    an abbreviation, an initial, a decimal, a filing reference — is stepped
    over rather than special-cased downstream.
    """
    body = text or ""
    out: List[Tuple[int, str]] = []
    start = 0
    for match in _TERMINATOR.finditer(body):
        end = match.end()
        if end >= len(body):
            break
        after = body[end:end + 2]
        if not after[:1].isspace():
            continue                      # "3.5%", "u.s.-based": not a break
        nxt = _next_visible(body, end)
        if nxt and not (nxt.isupper() or nxt.isdigit()
                        or nxt in "\"'“‘($€£¥•"):
            continue                      # "Inc. and its subsidiaries"
        head = body[start:match.start()]
        last = head.split()[-1].lower().rstrip(".,;:") if head.split() else ""
        if last in _ABBREVIATIONS:
            continue
        if _INITIAL.search(head[-2:]):
            continue                      # "J. P. Morgan"
        sentence = body[start:end].strip()
        if sentence:
            out.append((start + (len(body[start:end])
                                 - len(body[start:end].lstrip())), sentence))
        start = end
    tail = body[start:].strip()
    if tail:
        out.append((start + (len(body[start:]) - len(body[start:].lstrip())),
                    tail))
    return out


def _next_visible(body: str, index: int) -> str:
    for ch in body[index:index + 4]:
        if not ch.isspace():
            return ch
    return ""


# --- furniture ------------------------------------------------------------
#
# Every phrase below was taken from a real harvested page. The gate rejects
# what a document uses to move a reader around, sell to them, or satisfy a
# regulator's formatting rule — not what it says happened.
_MARKETING_OPENERS = (
    "explore", "shop", "discover", "browse", "learn", "sign", "get",
    "start", "try", "buy", "download", "subscribe", "contact", "read",
    "watch", "join", "see", "find", "meet", "imagine", "invent", "build",
    "create", "unlock", "experience", "transform", "empower", "welcome",
    "introducing", "let", "make", "bring", "take",
)
_MISSION_MARKERS = (
    "we believe", "we're on a mission", "we are on a mission", "our mission",
    "our vision", "we exist to", "we are committed", "we're committed",
    "we help", "we make it", "we work with", "we partner with",
    "our purpose", "our values", "our story", "we are building",
    "we're building", "our customers trust",
)
_COVER_PAGE_MARKERS = (
    "pursuant to section", "pursuant to rule", "annual report pursuant",
    "quarterly report pursuant", "transition report pursuant",
    "under the exchange act", "under the securities act",
    "securities exchange act of",
    "securities act of 1933", "commission file number", "title of each class",
    "name of each exchange", "trading symbol", "irs employer identification",
    "indicate by check mark", "check mark whether", "incorporated by "
    "reference", "state or other jurisdiction", "registrant's telephone",
    "emerging growth company", "well-known seasoned issuer",
    "aggregate market value of", "shares of common stock outstanding as of",
    "☐", "☒", "☑", "[x]", "[ ]",
)
_LEGAL_BOILERPLATE = (
    "all rights reserved", "copyright ©", "©", "terms of service",
    "terms of use", "privacy policy", "cookie policy", "cookie preferences",
    "forward-looking statements", "safe harbor", "trademarks of",
    "registered trademark", "are trademarks", "modern slavery",
    "accessibility statement",
)
_NAVIGATION = (
    "skip to main content", "skip to content", "main menu",
    "toggle navigation", "back to top", "site map", "follow us",
    "share this", "related articles", "you may also like", "sign in",
    "log in", "select your country", "change region", "view all",
    "see all", "load more", "next page", "previous page", "search results",
    "no results found", "click here", "read more", "learn more",
)
_INDEX_MARKERS = (
    "a featured collection", "featured collection of", "collection of the "
    "latest", "the latest blog", "latest posts", "blog posts", "press "
    "releases and", "browse our", "explore our", "all articles",
    "recent stories", "in this section", "on this page", "table of contents",
)

# Finite verbs and auxiliaries. A body sentence that contains none of these is
# a heading or a noun phrase — "A featured collection of the latest Palantir
# blog posts." has no verb at all, which is exactly what makes it furniture
# rather than a weakly-worded event.
_FINITE_VERBS = frozenset("""
is are was were be been being am
has have had having
do does did done
will would shall should can could may might must
said says say stated states reported reports announced announces
launched launches unveiled unveils introduced introduces released releases
awarded awards won wins secured secures selected selects signed signs
raised raises lowered lowers cut cuts increased increases reduced reduces
expanded expands added adds hired hires laid cutting adding
grew grows rose rise rises fell fall falls declined declines
exceeded exceeds beat beats missed misses delivered delivers
expects expect expected anticipates anticipate anticipated
plans plan planned intends intend intended agreed agrees
acquired acquires acquiring purchased purchases merged merges
filed files reported reporting completed completes began begins
posted posts recorded records generated generates returned returns
opened opens closed closes invested invests committed commits
appointed appoints named names promoted promotes resigned resigns
launched partnered partners collaborates collaborated
priced prices repriced charging charges paid pays
sued sues fined fines investigating investigated approved approves
warned warns noted notes disclosed discloses confirmed confirms
""".split())

# Third-person -s forms. The morphological rule below covers -ed and -ing but
# deliberately not -s, because "posts", "stockholders" and "activities" are
# nouns and admitting every plural would empty the furniture gate. So the
# common verb forms are named instead. Measured cost of leaving them out:
# "Palantir Joins Forces with U.S. Army for Project Convergence Capstone." —
# a real partnership event — was thrown away as a heading.
_FINITE_VERBS = _FINITE_VERBS | frozenset("""
joins halves enables unlocks accelerates discusses turns seeks gains holds
brings takes makes sets puts leads drives helps offers provides serves
supports creates builds ships targets moves opens picks names calls sees
becomes remains includes continues begins ends starts stops runs works
""".split())


def has_finite_verb(sentence: str) -> bool:
    """True when the sentence contains something that behaves like a verb.

    The lexicon alone was measured wrong on the real corpus, and wrong in the
    expensive direction. Caterpillar's dividend release says "The Board of
    Directors of Caterpillar Inc. (NYSE: CAT) voted today to raise the
    quarterly dividend by 12 cents" — the single most eventful sentence in the
    document — and "voted" was not on the list, so the sentence was thrown
    away as a heading.

    A missing word must not be able to do that again, so morphology backs the
    lexicon up: an -ed or -ing form is treated as verbal. It over-admits
    ("a featured collection") and that is the right way round to be wrong —
    admitting a furniture sentence costs nothing, because the classifier
    downstream still requires an actual event marker before it becomes
    evidence, while dropping a real one is unrecoverable.
    """
    for word in _words(sentence):
        if word in _FINITE_VERBS:
            return True
        if len(word) >= 5 and word.endswith("ed"):
            return True
        if len(word) >= 6 and word.endswith("ing"):
            return True
    return False


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z][a-z'’-]*", (text or "").lower())


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]?\d{4}\b")

# Financial-statement captions. A row of a cash-flow statement reads like a
# sentence once the table markup is gone — "Cash flow from investing
# activities: Capital expenditures – excluding equipment leased to others." —
# and it classified as a CAPEX event on the real corpus, as did "Investments
# and acquisitions (net of cash acquired)." on the M&A family. These are
# captions for numbers in an adjacent column, not statements that something
# happened, and no amount of classifier care fixes that: the fix is not to
# offer them as candidates.
_STATEMENT_LINE = re.compile(
    r"^(?:total|less|add|net cash|cash flow|cash and cash|operating "
    r"activities|investing activities|financing activities|adjustments? to "
    r"reconcile|weighted[- ]average|accumulated|accounts (?:payable|"
    r"receivable)|deferred|income before|cost of (?:goods|sales|revenue)|"
    r"gross (?:profit|margin)|current (?:assets|liabilities)|noncurrent|"
    r"property and equipment|stock[- ]based compensation|"
    r"proceeds from|purchases of|investments and|effect of foreign|"
    r"acquisition of companies|payments? for|repayments? of|"
    r"changes in operating|operating (?:costs|expenses)|"
    r"earnings per share attributable|profit \(loss\)|"
    r"equity in (?:profit|loss))\b")
_STATEMENT_TAIL = re.compile(
    r"\(net of [^)]*\)|\bnet of cash acquired\b|,\s*net\.?$|"
    r"\(unaudited\)|\(loss\)|"
    r"\bexcluding (?:equipment|discrete items)\b|"
    r"\bin thousands, except\b|\bin millions, except\b")


def furniture_reason(sentence: str) -> str:
    """Why this is page furniture rather than evidence — "" when it is not.

    The reason is returned, not a boolean, because the translation report has
    to be able to tell an operator WHAT it threw away. "17 rejected" and "17
    rejected as cover-page boilerplate" are very different diagnoses.
    """
    text = " ".join((sentence or "").split())
    if not text:
        return "empty"
    low = text.lower()
    words = text.split()

    if len(words) < MIN_SENTENCE_WORDS:
        return "fragment"
    if len(text) > MAX_SENTENCE_CHARS:
        return "unsegmented_block"

    for marker in _COVER_PAGE_MARKERS:
        if marker in low:
            return "cover_page_boilerplate"
    for marker in _NAVIGATION:
        if marker in low:
            return "navigation"
    for marker in _LEGAL_BOILERPLATE:
        if marker in low:
            return "legal_boilerplate"
    for marker in _INDEX_MARKERS:
        if marker in low:
            return "page_index"
    for marker in _MISSION_MARKERS:
        if marker in low:
            return "mission_statement"
    if _EMAIL.search(text) or _PHONE.search(text):
        return "contact_details"
    if _STATEMENT_LINE.match(low) or _STATEMENT_TAIL.search(low):
        return "financial_statement_line"

    # An unterminated line is a heading, a menu item or a truncated read —
    # never a complete statement of fact.
    if text[-1] not in ".!?":
        return "incomplete_sentence"

    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        return "heading"

    # An imperative opener with no reporting verb is a call to action:
    # "Explore the Microsoft Store for apps and games on Windows." Checked
    # BEFORE the verb test, which would also reject it but under the much
    # less useful reason "no_verb" — an operator reading the rejection
    # breakdown should be told this was marketing, not that it was a heading.
    first = words[0].lower().strip(".,:;")
    if first in _MARKETING_OPENERS and not _reports_an_action(low):
        return "marketing_imperative"

    # Title Case With No Verb is a section heading wearing a full stop.
    if not has_finite_verb(text):
        return "no_verb"

    return ""


# Verbs that describe something that HAPPENED, as opposed to something the
# reader is invited to do. An imperative sentence containing one of these is
# usually a real statement with an unlucky first word.
_REPORTING = ("announced", "reported", "said", "stated", "disclosed",
              "launched", "released", "awarded", "won", "signed", "filed",
              "completed", "acquired", "raised", "lowered", "increased",
              "reduced", "expects", "expanded", "posted", "recorded",
              "delivered", "exceeded", "beat", "missed")


def _reports_an_action(low: str) -> bool:
    return any(v in low for v in _REPORTING)


def is_furniture(sentence: str) -> bool:
    return bool(furniture_reason(sentence))


# --- the canonical extraction ---------------------------------------------
def body_text(doc) -> str:
    """The document's body, preferring real content over its own description.

    `meta_description` is what a page tells a search engine it is about. It is
    a legitimate last resort and a terrible first choice, and it was the first
    choice for every observation production made.
    """
    if isinstance(doc, dict):
        body = (doc.get("text_content") or "").strip()
        return body or (doc.get("meta_description") or "").strip()
    body = (getattr(doc, "text_content", "") or "").strip()
    return body or (getattr(doc, "meta_description", "") or "").strip()


def _doc_field(doc, name: str) -> str:
    if isinstance(doc, dict):
        return str(doc.get(name) or "")
    return str(getattr(doc, name, "") or "")


def candidates(doc, *, scan_chars: int = SCAN_CHARS,
               limit: Optional[int] = None) -> List[Candidate]:
    """THE canonical candidate-extraction function.

    Every consumer — market learning, strategic reasoning, founder evidence,
    competitor extraction — segments a document here, so two subsystems cannot
    derive materially different facts from the same page. Bounded by
    `scan_chars` and deduplicated on normalised text: a site that repeats its
    banner on every page must not produce the same "fact" eight times.
    """
    body = body_text(doc)[:scan_chars]
    source_id = _doc_field(doc, "source_id")
    origin = _doc_field(doc, "final_url") or _doc_field(doc, "origin")
    out: List[Candidate] = []
    seen = set()
    for offset, sentence in split_sentences(body):
        text = " ".join(sentence.split())
        if furniture_reason(text):
            continue
        key = _dedupe_key(text)
        if key in seen:
            continue
        seen.add(key)
        out.append(Candidate(text=text, offset=offset, index=len(out),
                             source_id=source_id, origin=origin))
        if limit is not None and len(out) >= limit:
            break
    return out


def _dedupe_key(text: str) -> str:
    """Normalised form, so punctuation and case cannot mint a second fact."""
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


_NUMBER = re.compile(r"(?:\$|€|£|¥)\s?[\d.,]+|\b\d[\d.,]*\s*"
                     r"(?:%|percent|billion|bn|million|thousand)\b")
_DATE = re.compile(r"\b(?:19|20)\d{2}\b|\b(?:jan|feb|mar|apr|may|jun|jul|"
                   r"aug|sep|oct|nov|dec)\w*\.?\s+\d{1,2}\b", re.I)


def density(sentence: str) -> int:
    """How much a sentence commits to — the basis for choosing a window.

    Deliberately not an event classifier: it counts the marks of a specific
    claim (a reported action, a figure, a date) without asserting what kind of
    event it is. `concrete.action_kind` is reused rather than reimplemented,
    so "what counts as a company action" has one definition in this codebase.
    """
    from intent_engine.strategic_intelligence import concrete
    score = 0
    if concrete.action_kind(sentence):
        score += 2
    if _NUMBER.search(sentence):
        score += 1
    if _DATE.search(sentence):
        score += 1
    return score


def evidence_excerpt(doc, *, max_chars: int = EXCERPT_CHARS) -> str:
    """The excerpt an observation carries: real sentences, in document order.

    Built from surviving candidates rather than from a character slice, so a
    filing's excerpt starts at its first substantive sentence instead of at
    its cover page, and a marketing page contributes its prose rather than its
    search-engine blurb.

    THE WINDOW IS CHOSEN, NOT ASSUMED. Taking the first 1,200 characters of
    surviving prose is still a positional guess, and it was measured wrong:
    Palantir's blog page states "Palantir Joins Forces with U.S. Army for
    Project Convergence Capstone" well past the first twenty sentences, so a
    leading window returned navigation prose and the real event was never
    seen. The excerpt is therefore the highest-density CONTIGUOUS run of
    candidates that fits — contiguous and in order, so it still reads as
    prose, and earliest-wins on a tie so the choice is deterministic.

    Falls back to raw body and then to `meta_description`. A document whose
    every sentence is furniture is allowed to say so with its own words — the
    fallback is visible to the reader and is the honest answer, where an empty
    string would look like a retrieval failure.
    """
    body = " ".join(body_text(doc).split())
    items = candidates(doc)
    if not items:
        return body[:max_chars]

    scores = [density(c.text) for c in items]
    best_start, best_score, best_end = 0, -1, 0
    for start in range(len(items)):
        used, total, end = 0, 0, start
        while end < len(items):
            need = len(items[end].text) + (1 if end > start else 0)
            if used + need > max_chars and end > start:
                break
            used += need
            total += scores[end]
            end += 1
        if total > best_score:
            best_start, best_score, best_end = start, total, end
        if end >= len(items) and start > 0:
            break                       # every later window is a suffix
    selected = " ".join(c.text for c in items[best_start:best_end])

    # THE FLOOR. A thin page can survive the furniture gate with one clean
    # sentence, and a one-sentence excerpt is below what the analyst layer
    # will read at all (`MIN_ANALYST_EXCERPT_CHARS`), so filtering would have
    # silently deleted the whole page as evidence rather than tidied it. When
    # the filtered window is thinner than the raw body, the raw body wins:
    # some furniture in the excerpt is a much smaller cost than a page that
    # vanishes.
    if len(selected) < MIN_USEFUL_EXCERPT_CHARS and len(body) > len(selected):
        return body[:max_chars]
    return selected[:max_chars]

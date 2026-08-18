"""What one company IS to another, before anything calls it a competitor.

THE DEFECT THIS CLOSES, MEASURED.

EDGAR full-text search finds filings by other registrants that name the
subject, and every one of them was stamped `source_class: "competitor"` on
arrival — the class was a constant in `third_party_filings._emit`, not a
finding. Measured live for Meta Platforms:

    Oklo Inc.        "prepayment agreement with Meta Platforms, Inc."
                     -> Meta BUYS POWER FROM THEM. A customer relationship,
                        filed as competition.

    Network-1        "our case against Meta Platforms, Inc."
                     -> a patent suit. A litigant, filed as competition.

    ENBRIDGE INC     an excerpt that never names Meta at all
                     -> incidental, filed as competition.

    RingCentral      "(Google G-Suite and Meet), Meta Platforms, Inc.,
                      Microsoft Teams, Slack Technologies, Inc."
                     -> genuinely a rival naming its market. The only one.

Three of four were wrong, and the relevance grade beside them said
DIRECTLY_RELEVANT for all four because it counted PASSAGES rather than
reading them. A pipeline that promotes a mention to a competitor has no way
to be right: being named in a filing is evidence that two companies have
something to do with each other, and nothing more.

THE RULE. `mention -> competitor` is never valid. A mention becomes
`RelationshipEvidence`, the evidence must contain the span that establishes
the relationship, and only COMPETITOR or SUBSTITUTE may enter the
competitive ladder.

WHY THE VERB AND NOT THE COMPANY. The classification is decided by what the
sentence DOES — "agreement with", "case against", "compete with" — because
that generalises. A stoplist of company names does not: three live rounds in
an earlier cycle proved that stoplists cannot separate a heading from a firm,
and a rule keyed on "AT&T" would have left Oklo, Network-1 and Enbridge
exactly where they were.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Tuple

CONTRACT = "relationship_evidence.v1"

# --- the relationship vocabulary -------------------------------------------
COMPETITOR = "COMPETITOR"
SUBSTITUTE = "SUBSTITUTE"
SUPPLIER = "SUPPLIER"
CUSTOMER = "CUSTOMER"
PARTNER = "PARTNER"
VENDOR = "VENDOR"
DISTRIBUTION = "DISTRIBUTION"
INFRASTRUCTURE = "INFRASTRUCTURE"
LITIGATION = "LITIGATION"
INVESTOR = "INVESTOR"
INCIDENTAL_MENTION = "INCIDENTAL_MENTION"
UNKNOWN = "UNKNOWN"

RELATIONSHIP_TYPES = (COMPETITOR, SUBSTITUTE, SUPPLIER, CUSTOMER, PARTNER,
                      VENDOR, DISTRIBUTION, INFRASTRUCTURE, LITIGATION,
                      INVESTOR, INCIDENTAL_MENTION, UNKNOWN)

#: The ONLY two that may reach the competitive ladder. Everything else is a
#: real, often useful fact about the company — and not a rival.
COMPETITIVE = (COMPETITOR, SUBSTITUTE)

#: Human labels. The enum never reaches a reader (§73).
RELATIONSHIP_LABEL = {
    COMPETITOR: "competes with",
    SUBSTITUTE: "is an alternative to",
    SUPPLIER: "supplies",
    CUSTOMER: "buys from",
    PARTNER: "partners with",
    VENDOR: "is a vendor to",
    DISTRIBUTION: "distributes for",
    INFRASTRUCTURE: "is infrastructure for",
    LITIGATION: "is in litigation with",
    INVESTOR: "has invested in",
    INCIDENTAL_MENTION: "is mentioned alongside",
    UNKNOWN: "has an unestablished relationship with",
}

# --- the cues, strongest claim first ---------------------------------------
#
# ORDER MATTERS AND IS NOT ARBITRARY. A sentence can carry more than one cue
# ("we compete with X, who is also a supplier"), and the first match wins, so
# the more specific and less reversible relationships are tested first.
# Litigation before competition, because "against" reads as adversarial to a
# competition rule and a lawsuit is not a market.
_CUES: Tuple[Tuple[str, "re.Pattern"], ...] = (
    (LITIGATION, re.compile(
        r"\b(case|suit|lawsuit|complaint|action|litigation|claim)s?\b[^.;]{0,60}"
        r"\b(against|versus|v\.)\b"
        r"|\b(infring\w+|patent dispute|settlement agreement)\b", re.I)),
    (CUSTOMER, re.compile(
        r"\b(prepayment|purchase|offtake|supply|services|master)\s+agreement\b"
        r"[^.;]{0,40}\bwith\b"
        r"|\b(our|its)\s+(largest\s+)?customers?\b[^.;]{0,60}\binclude\b"
        r"|\bsells?\s+to\b|\brevenue\s+from\b", re.I)),
    (SUPPLIER, re.compile(
        r"\b(we|our company)\s+(purchase|buy|source|licen[sc]e)s?\b"
        r"[^.;]{0,50}\bfrom\b"
        r"|\b(supplier|vendor)s?\b[^.;]{0,40}\binclude\b", re.I)),
    (PARTNER, re.compile(
        r"\b(partnership|collaboration|joint venture|alliance|"
        r"strategic relationship)\b[^.;]{0,40}\bwith\b"
        r"|\bpartners?\s+with\b|\bteamed up with\b", re.I)),
    (INVESTOR, re.compile(
        r"\b(investment|stake|equity interest|shares)\b[^.;]{0,40}\bin\b"
        r"|\binvested\s+in\b", re.I)),
    (DISTRIBUTION, re.compile(
        r"\b(distribut\w+|resell\w+|channel partner|app store|marketplace)\b"
        r"[^.;]{0,40}\b(through|via|by|with)\b", re.I)),
    (INFRASTRUCTURE, re.compile(
        r"\b(operating system|browser|platform|network|cloud)\s+provider"
        r"|\b(hosted|runs?|built)\s+on\b", re.I)),
    (SUBSTITUTE, re.compile(
        r"\b(alternative|substitute|instead of|in place of|"
        r"migrat\w+\s+(from|to))\b", re.I)),
    (COMPETITOR, re.compile(
        r"\bcompet\w+\b|\brival\w*\b"
        r"|\b(other|principal|primary)\s+(participants|providers|vendors)\b",
        re.I)),
)


@dataclasses.dataclass(frozen=True)
class RelationshipEvidence:
    """What the subject IS to the counterparty, and the span that says so."""
    subject: str
    counterparty: str
    relationship_type: str
    evidence: str
    confidence: str                    # HIGH | MEDIUM | LOW
    date: str = ""
    source: str = ""

    def __post_init__(self):
        if self.relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError(
                f"unknown relationship_type {self.relationship_type!r}")
        # A CLASSIFICATION WITHOUT ITS SPAN IS AN OPINION. Every type except
        # the two that mean "we established nothing" must quote the text it
        # was read from, or the reader cannot reject it.
        if self.relationship_type not in (INCIDENTAL_MENTION, UNKNOWN) \
                and not (self.evidence or "").strip():
            raise ValueError(
                f"{self.relationship_type} requires the evidence span that "
                f"establishes it")

    @property
    def is_competitive(self) -> bool:
        return self.relationship_type in COMPETITIVE

    def describe(self) -> str:
        return (f"{self.counterparty} "
                f"{RELATIONSHIP_LABEL[self.relationship_type]} "
                f"{self.subject}")


def _names_subject(text: str, subject: str) -> bool:
    """Does this span actually mention the subject?

    THE ENBRIDGE CASE. A search hit guarantees the DOCUMENT names the
    subject; the excerpt selected from it need not. Enbridge's excerpt was
    capital-allocation boilerplate with no mention of Meta anywhere in it,
    and it was still graded DIRECTLY_RELEVANT. A span that does not name the
    subject cannot establish a relationship to the subject.
    """
    if not text or not subject:
        return False
    lowered = text.lower()
    # The distinguishing words of the name, legal form dropped: "Meta
    # Platforms, Inc." -> "meta platforms". Requiring the full legal string
    # would miss every filing that writes "Meta" or "Meta Platforms".
    words = [w for w in re.findall(r"[A-Za-z0-9&]+", subject.lower())
             if w not in _LEGAL_FORMS]
    if not words:
        return False
    lead = words[0]
    # A leading generic word ("bank", "target") matches half the corpus on
    # its own, so those need a second word present too.
    if lead in _GENERIC_LEADS and len(words) > 1:
        return bool(re.search(rf"\b{re.escape(lead)}\b", lowered)) and \
            bool(re.search(rf"\b{re.escape(words[1])}\b", lowered))
    return bool(re.search(rf"\b{re.escape(lead)}\b", lowered))


_LEGAL_FORMS = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "llc", "lp", "llp", "plc", "sa", "nv", "ag", "se", "gmbh",
    "holdings", "holding", "group", "the", "and",
})

#: Leading words that are ordinary English before they are a company.
_GENERIC_LEADS = frozenset({
    "bank", "target", "block", "apple", "meta", "visa", "shell", "gap",
    "square", "oracle", "amazon", "delta", "general", "american", "national",
    "first", "united", "standard",
})


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence the match sits in, bounded so it stays quotable.

    Filing prose runs long and is full of abbreviations, so this cuts on
    terminal punctuation followed by whitespace, and falls back to a
    character window when the "sentence" is longer than anything worth
    showing a reader.
    """
    left = max((m.end() for m in re.finditer(r"[.;]\s+", text[:start])),
               default=0)
    right_match = re.search(r"[.;]\s+", text[end:])
    right = end + (right_match.start() + 1 if right_match else 0) \
        if right_match else len(text)
    if right - left > 420:                 # not a sentence, a paragraph
        left, right = max(0, start - 120), min(len(text), end + 120)
    return text[left:right].strip()


def classify_relationship(*, subject: str, counterparty: str, text: str,
                          date: str = "", source: str = "",
                          ) -> RelationshipEvidence:
    """Read the span and say what the two companies are to each other.

    Never raises, and never guesses COMPETITOR. When the span does not name
    the subject the answer is INCIDENTAL_MENTION; when it names it but
    carries no relationship verb the answer is UNKNOWN. Both keep the
    counterparty out of the competitive ladder, which is the point: the
    default has to be "we did not establish this".
    """
    span = (text or "").strip()
    if not _names_subject(span, subject):
        return RelationshipEvidence(
            subject=subject, counterparty=counterparty,
            relationship_type=INCIDENTAL_MENTION, evidence="",
            confidence="LOW", date=date, source=source)
    for kind, pattern in _CUES:
        match = pattern.search(span)
        if not match:
            continue
        # THE QUOTED SPAN IS THE SENTENCE THAT MATCHED, not the whole
        # excerpt. One document carries many signals, and an excerpt shown
        # beside a classification it did not produce justifies nothing —
        # a fixed character window around the match reached into the
        # neighbouring sentences and quoted a revenue line under a
        # litigation verdict.
        return RelationshipEvidence(
            subject=subject, counterparty=counterparty,
            relationship_type=kind,
            evidence=_sentence_around(span, match.start(), match.end()),
            confidence="HIGH" if kind in (LITIGATION, COMPETITOR) else "MEDIUM",
            date=date, source=source)
    return RelationshipEvidence(
        subject=subject, counterparty=counterparty,
        relationship_type=UNKNOWN, evidence="", confidence="LOW",
        date=date, source=source)


def source_class_for(relationship_type: str) -> str:
    """The ingestion source class this relationship justifies.

    `competitor` is the class that lets a document's market claims speak
    about the SUBJECT's market, so only a competitive relationship earns it.
    Everything else is still an independent third party writing about the
    company — genuinely useful evidence, and not a rival.
    """
    return ("competitor" if relationship_type in COMPETITIVE
            else "independent_reporting")

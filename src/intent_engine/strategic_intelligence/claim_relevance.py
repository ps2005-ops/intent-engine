"""Does this independent source actually bear on a claim, or just say the name?

MEASURED, on the eighteen third-party filings the product accepts today:

    CLAIM_RELEVANT      1   ( 5%)
    WEAK / IRRELEVANT  17   (94%)

Seventeen of eighteen "independent vantage points" were not statements about
the subject at all. They were:

  * executive-compensation peer groups  ("Removed Cloudflare and Zscaler ...")
  * XBRL taxonomy fragments             ("ichr:AppliedMaterialsMember")
  * director biographies                ("has served on the board of ...")
  * forward-looking-statement boilerplate
  * long risk-factor competitor lists

Adding that evidence raised the independence COUNT and taught the analyst
nothing, which is exactly the failure mode "more documents is not better"
describes. A company named beside twenty others is not corroboration.

So relevance is decided here, deterministically, before the analyst sees
anything -- and the honest outcome of this module is usually rejection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- claim relationships -----------------------------------------------------
SUPPORTS = "SUPPORTS"
WEAKENS = "WEAKENS"
CONTRADICTS = "CONTRADICTS"
CONTEXTUALIZES = "CONTEXTUALIZES"
UNRELATED = "UNRELATED"

#: A window this wide either side of the mention. Wide enough to carry the
#: sentence, narrow enough that an unrelated paragraph cannot rescue it.
WINDOW = 320

# SPECIFIC statements: something happened between these two companies.
_MATERIAL = re.compile(
    r"(displac\w+|switch\w+\s+(?:from|to)|migrat\w+\s+(?:from|to|away)|"
    r"lost\s+(?:a\s+|the\s+)?(?:customer|contract|account)|market\s+share|"
    r"pricing\s+pressure|replaced?\s+\w+\s+with|competitive\s+response|"
    r"churn|won\s+(?:business\s+)?(?:against|from)|head[- ]to[- ]head)", re.I)

# GENERIC competition language. "We compete with X" is a true sentence that
# every risk-factor section contains; beside a list of eight names it
# establishes participation in a market, not a change in position. It is
# therefore material ONLY when it is not sitting inside an enumeration.
_GENERIC_COMPETITION = re.compile(
    r"we\s+compete\s+(?:directly\s+)?with", re.I)

# Direction, when a material statement is present.
_NEGATIVE = re.compile(
    r"(lost|declin\w+|weaken\w+|pressure|eroded?|churn|switch\w+\s+away|"
    r"migrat\w+\s+away|slower|shortfall)", re.I)

# --- the seventeen. Each pattern is one measured false positive. -------------
_XBRL = re.compile(r"(us-gaap:|ifrs-full:|dei:|srt:|[a-z]{2,6}:[A-Z][A-Za-z]+Member"
                   r"|\d{4}-\d{2}-\d{2}\s+\d{4}-\d{2}-\d{2})")
_COMP_PEER = re.compile(
    r"(compensia|peer\s+group|compensation\s+committee|pay\s+ratio|"
    r"removed\s+\w+\s+and\s+\w+\s+due\s+to|added\s+to\s+the\s+peer)", re.I)
_DIRECTOR_BIO = re.compile(
    r"(served\s+on\s+the\s+board|board\s+of\s+directors\s+of|"
    r"received\s+(?:a\s+|his\s+|her\s+)?(?:b\.?a\.?|b\.?s\.?|m\.?b\.?a\.?)|"
    r"university\s+of|bachelor\s+of|master\s+of|executive\s+vice\s+president"
    r"\s+(?:of|at)\s+\w+)", re.I)
_FORWARD_LOOKING = re.compile(
    r"(forward[- ]looking\s+statements?|difficult\s+to\s+predict|"
    r"safe\s+harbor|private\s+securities\s+litigation)", re.I)
#: four or more capitalised names in a row is an enumeration, not a sentence
_LIST_LIKE = re.compile(
    r"(,\s*[A-Z][A-Za-z.&'-]+(?:\s+[A-Z][A-Za-z.&'-]+)*){4,}")

_REJECTIONS = (
    ("xbrl_fragment", _XBRL),
    ("compensation_peer_group", _COMP_PEER),
    ("director_biography", _DIRECTOR_BIO),
    ("forward_looking_boilerplate", _FORWARD_LOOKING),
)


@dataclass(frozen=True)
class RelevanceVerdict:
    relationship: str
    confidence: str            # "high" | "medium" | "low"
    reason: str
    excerpt: str
    rejected_as: str = ""

    @property
    def usable_as_support(self) -> bool:
        """CONTEXT_ONLY may be shown; it may never carry a conclusion."""
        return self.relationship in (SUPPORTS, WEAKENS, CONTRADICTS)


def mention_window(text: str, company_name: str, *, width: int = WINDOW) -> str:
    """The text around the first real mention of the company."""
    key = (company_name or "").split()[0] if company_name else ""
    if not key or not text:
        return ""
    match = re.search(re.escape(key), text, re.I)
    if not match:
        return ""
    start = max(0, match.start() - width)
    return " ".join(text[start:match.start() + width].split())


def assess(*, text: str, company_name: str, claim_terms=()) -> RelevanceVerdict:
    """Classify one independent source against a candidate claim.

    `claim_terms` are the product, market or event words the claim is about.
    When supplied, a source that never mentions any of them is CONTEXTUALIZES
    at best -- naming the company is not the same as bearing on the claim.
    """
    window = mention_window(text, company_name)
    if not window:
        return RelevanceVerdict(UNRELATED, "high",
                                "the company is not named in this document",
                                "", rejected_as="wrong_entity")

    for label, pattern in _REJECTIONS:
        if pattern.search(window):
            return RelevanceVerdict(
                UNRELATED, "high",
                "the mention sits in boilerplate rather than a statement "
                "about the company", window, rejected_as=label)

    listed = _LIST_LIKE.search(window)
    material = _MATERIAL.search(window)
    if not material and _GENERIC_COMPETITION.search(window) and not listed:
        material = True          # "we compete with X" on its own is a claim
    if material and listed and not _MATERIAL.search(window):
        material = None          # ... but inside a list of names it is not

    if not material:
        if listed:
            return RelevanceVerdict(
                CONTEXTUALIZES, "medium",
                "the company appears in a list of market participants, which "
                "shows it competes here and nothing more", window,
                rejected_as="competitor_list")
        return RelevanceVerdict(
            UNRELATED, "medium",
            "the company is named but nothing is said about it", window,
            rejected_as="weak_mention")

    # A material statement exists. Does it bear on THIS claim?
    if claim_terms:
        low = window.lower()
        if not any(term.lower() in low for term in claim_terms if term):
            return RelevanceVerdict(
                CONTEXTUALIZES, "medium",
                "a substantive competitive statement, but not about the "
                "product or market this claim concerns", window,
                rejected_as="different_subject")

    relationship = WEAKENS if _NEGATIVE.search(window) else SUPPORTS
    return RelevanceVerdict(
        relationship, "medium",
        "an independent registrant states something material about this "
        "company", window)

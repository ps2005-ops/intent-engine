"""Filing furniture is not a finding.

Measured live on the deployed preview (commit 16dc4b8, Datadog, 2026-08-05).
Slide 1 of 7 -- the first presentation screen a CEO sees -- read:

    What was verified: ☒. ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE
    SECURITIES EXCHANGE ACT OF 1934. ☐. TRANSITION REPORT PURSUANT TO SECTION
    13 OR 15(d) OF THE SECURITIES EXCHANGE ACT OF 1934. Delaware. 27-2825503.
    (State or other jurisdiction ofincorporation or organization). (I.R.S.
    Emplo.

That is a 10-K cover page: two form titles, their filing-status checkboxes, a
state of incorporation and an IRS employer number, cut off mid-word. It tells a
reader nothing except that a document exists, and it occupied the one line on
the slide that was supposed to say what the analysis had established.

SCOPE. This suppresses filing furniture from EXECUTIVE candidates only. The
document stays in storage, stays cited, and stays readable in the evidence
appendix -- provenance is not the problem. What must not happen is furniture
being promoted to "what was verified", "what changed", a slide title, a slide
body, or the evidence under a recommendation.

WHY PATTERNS AND NOT A PARSER. These filings arrive as flattened HTML with the
cover page first. A section-aware parser is the better long-term answer and is
not what closes this defect: every pattern below is a real string from a real
filing, and each one is furniture in every filing layout, not just this one.
"""
from __future__ import annotations

import re

# Ballot-box and check glyphs used for filing-status boxes. These are never
# meaningful prose, so they are stripped before any other judgement.
CHECKBOX_GLYPHS = "☐☑☒✓✔✗✘■□"

_FURNITURE = tuple(re.compile(p, re.I) for p in (
    # form titles and the Exchange Act boilerplate that follows them
    r"\bannual report pursuant to section\b",
    r"\btransition report pursuant to section\b",
    r"\bquarterly report pursuant to section\b",
    r"\bcurrent report pursuant to section\b",
    r"\bpursuant to section 13 or 15\(d\)\b",
    r"\bof the securities exchange act of 19\d\d\b",
    r"\bregistration statement pursuant to\b",
    r"\bfor the (?:fiscal year|quarterly period|transition period) ended\b",
    r"\bcommission file (?:number|no)\b",
    # cover-page identity metadata
    r"\bstate or other jurisdiction of\s*incorporation\b",
    r"\bi\.?r\.?s\.? employer\b",
    r"\bidentification (?:number|no)\b",
    r"\baddress of principal executive offices\b",
    r"\bregistrant'?s telephone number\b",
    r"\btitle of each class\b",
    r"\bname of each exchange on which registered\b",
    r"\btrading symbol\(?s?\)?\b",
    r"\bsecurities registered pursuant to\b",
    # filing-status checkbox questions
    r"\bindicate by check mark\b",
    r"\bcheck the appropriate box\b",
    r"\bemerging growth company\b",
    r"\bwell-known seasoned issuer\b",
    r"\bnon-accelerated filer\b", r"\blarge accelerated filer\b",
    r"\bsmaller reporting company\b",
    r"\bshell company\b",
    # navigation and document furniture
    r"\btable of contents\b", r"\bindex to (?:financial|exhibits)\b",
    r"^\s*part [ivx]+\s*[.\-—]?\s*$",
    r"^\s*item \d+[a-z]?\s*[.\-—]?\s*$",
    r"\bexhibit (?:index|\d+\.\d+)\b",
    r"\bsee accompanying notes\b",
    r"\bthe accompanying notes are an integral part\b",
    r"\bsignatures?\s*$", r"\bpursuant to the requirements of the securities\b",
    r"\bhas duly caused this report to be signed\b",
    # safe-harbour boilerplate
    r"\bprivate securities litigation reform act\b",
    r"\bactual results (?:could|may) differ materially\b",
    # SECTION-OPENING FRAMING. Every Item begins by telling the reader how to
    # read it, and once the body of a filing actually reached the excerpt
    # selector these became the FIRST substantive-looking sentence in their
    # section. Measured live: the Datadog 10-K led with "The following
    # discussion and analysis of our financial condition and results of
    # operations should be read in conjunction with our audited consolidated
    # financial statements", and the 10-Q led with "From time to time we may
    # become involved in legal proceedings". Both are long, both parse as
    # prose, and neither says anything about the company.
    # THE GENERAL RULE THIS IS AN INSTANCE OF: prose about the DOCUMENT is not
    # prose about the company. Filtering the opening sentence one phrase at a
    # time just promoted the next one -- Datadog led with "This discussion,
    # particularly information with respect to our future results", Microsoft
    # and Caterpillar with "is intended to help the reader understand", NVIDIA
    # with "our Consolidated Financial Statements and related Notes thereto",
    # Amazon with "All statements other than statements of historical fact".
    # Five filers, five different sentences, all saying how to read the filing.
    r"\bthe following discussion and analysis\b",
    r"\b(?:this|the following)\s+(?:discussion|md&a|section)\b",
    r"\bis intended to (?:help|assist|provide)\b.{0,40}\breader\b",
    r"\bstatements? (?:other than|of historical facts?)\b",
    # SAFE HARBOUR IS ALWAYS ABOUT THE DOCUMENT. Three narrower rules were
    # tried and each was defeated by the next filing's phrasing: "within
    # the meaning", then "subject to risks and uncertainties", then
    # "Examples of forward-looking statements include, but are not limited
    # to (i) projections of sales, income or loss". A sentence that names
    # forward-looking statements at all is telling the reader how to weigh
    # the filing, never what the company does.
    r"\bforward.looking statements?\b",
    r"\bcautionary statements?\b",
    r"\bnotes thereto\b",
    r"\b(?:described|discussed|included) elsewhere in this\b",
    r"\bshould be read (?:in conjunction|together) with\b",
    # A cross-reference to the filing itself, and the fragment left when one
    # is split at a sentence boundary. Measured on a 2007 Caterpillar 10-K,
    # which offered "(Risk Factors and Cautionary Factors That May Affect
    # Future Results) of this Form 10-K." as its Item 7 excerpt.
    r"\bof this (?:form 10-[kq]|annual report|quarterly report)\b",
    r"^\s*\(",
    r"\bfrom time to time,? we may become (?:involved|subject)\b",
    r"\bwe are not (?:presently|currently) a party to any\b",
    r"\bis incorporated (?:herein )?by reference\b",
    r"\bunless the context otherwise requires\b",
    r"\bthe information (?:set forth|contained) (?:in|under)\b"
    r".{0,60}\bis incorporated\b",
    r"\bthis (?:annual|quarterly|current) report on form\b"
    r".{0,40}\bcontains forward-looking\b",
    # XBRL / tagging labels
    r"\bxbrl\b", r"\binline xbrl\b", r"\bus-gaap:\b",
))

# A fragment that is mostly a corporate identifier and no verb is metadata,
# however it is worded: "Delaware. 27-2825503." matches nothing above.
_EIN = re.compile(r"\b\d{2}-\d{7}\b")
_CIK = re.compile(r"\bcik\s*[#:]?\s*\d{6,10}\b", re.I)


def strip_checkboxes(text: str) -> str:
    """Remove filing-status glyphs and the empty punctuation they leave."""
    out = (text or "").translate({ord(c): None for c in CHECKBOX_GLYPHS})
    out = re.sub(r"(?:\s*\.){2,}", ".", out)      # "☒. ☐." -> "."
    out = re.sub(r"^[\s.;,]+", "", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def is_filing_furniture(text: str) -> bool:
    """True when this fragment is filing structure rather than content."""
    raw = " ".join((text or "").split())
    if not raw:
        return True
    if any(g in raw for g in CHECKBOX_GLYPHS):
        return True
    stripped = strip_checkboxes(raw)
    if not stripped:
        return True
    if any(p.search(stripped) for p in _FURNITURE):
        return True
    if _EIN.search(stripped) or _CIK.search(stripped):
        return True
    # A cover page is a list of noun phrases. Real prose has a verb; requiring
    # one would over-refuse, so this only fires on very short fragments that
    # are mostly capitalised labels.
    words = stripped.split()
    if len(words) <= 12:
        caps = sum(1 for w in words if w[:1].isupper())
        if caps >= max(3, len(words) - 2):
            return True
    return False


def executive_safe(candidates) -> list:
    """The candidates that may reach an executive surface, in order.

    Furniture is dropped rather than rewritten: a cover page has no
    interpretation hiding inside it. Everything else is returned with its
    filing glyphs stripped, because a real sentence can still carry one.
    """
    out = []
    for c in candidates or ():
        text = c if isinstance(c, str) else str(c or "")
        if is_filing_furniture(text):
            continue
        cleaned = strip_checkboxes(text)
        if cleaned:
            out.append(cleaned)
    return out

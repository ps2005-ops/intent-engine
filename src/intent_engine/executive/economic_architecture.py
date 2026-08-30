"""What THIS company sells, who pays, and what decides its margin.

WHY THIS EXISTS
---------------
The business-model sentence was written per MODEL CLASS. Measured across the
50-company gauntlet, 79 of 990 pairs were BYTE-IDENTICAL:

    Adobe == Cloudflare == Microsoft == Salesforce == Shopify
    Alphabet == Meta
    Amazon == The Home Depot

    "software platform business that runs on recurring software
     subscription: revenue is contracted and renews..."          x5
    "semiconductor business that runs on design and manufacture of a
     physical product sold into a capacity-constrained supply chain"  x6

A chief executive who reads the sentence describing their company and sees it
describing four others has been shown a template with a name inserted.

THE CLASS IS A PRIOR, NOT A DESCRIPTION. It stays: it is how the engine knows
which questions a business of this kind is judged on. What it may no longer do
is BE the answer. The particulars below come from the subject's own filings --
its named segments, the sentence in which it says what it sells, the sentence
in which it says where revenue comes from -- and they separate Adobe from
Cloudflare without one line of company-specific code:

    Adobe   three reportable segments: Digital Media, Digital Experience
            and Publishing and Advertising; revenue derived from cloud-
            enabled software subscriptions, term-based, royalty, and
            perpetual software licenses
    Cloudflare  revenue generated from pay-as-you-go and contracted
            customers: subscription fees to access its network, support
            services, and usage-based fees

NO COMPANY-SPECIFIC BRANCHES. There is no table keyed on a company name here
and there must never be one. Every field is a regular expression over the
subject's own prose, and a company whose filing does not say a thing simply
does not get that field.

OWNERSHIP IS CHECKED. A sentence in a competitor's filing describes the
competitor. Only documents this run established as the SUBJECT's own are read.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Tuple

CONTRACT = "economic_architecture.v2"

#: A field is only worth rendering if it says something. Below this a match is
#: a fragment, not a description.
_MIN_CLAUSE = 24
#: Above this the reader is being handed a paragraph, not an answer.
_MAX_CLAUSE = 260


@dataclasses.dataclass(frozen=True)
class EconomicArchitecture:
    """The measured economics of ONE company. Every field is optional."""
    contract: str = CONTRACT
    company: str = ""
    #: Named reportable segments, in the filing's own words.
    segments: Tuple[str, ...] = ()
    what_is_sold: str = ""
    revenue_basis: str = ""
    pricing_mechanism: str = ""
    margin_basis: str = ""
    capital_basis: str = ""
    customer: str = ""
    # --- v2: the rest of the canonical object (§7) -------------------------
    #
    # ONE ONTOLOGY, NOT ONE PER SURFACE. The decision question, the
    # competitor set, the impossible hypothesis, the adversary, Step 6 and
    # Q&A were each deriving their own idea of what the company runs on. The
    # fields below exist so they read the same object instead.
    buyer: str = ""             #: who signs, when it differs from the user
    unit_of_sale: str = ""      #: what one purchase is
    volume_driver: str = ""     #: what makes the unit count go up
    growth_constraint: str = ""  #: what stops it going up
    #: WHICH SEGMENT IS WHICH ENGINE. A multi-engine filer is not one
    #: business, and the segment that earns the revenue is frequently not
    #: the one that earns the profit or holds the strategic position.
    #: Never invented: each is a segment the filing itself named, or "".
    revenue_engine: str = ""
    profit_engine: str = ""
    strategic_engine: str = ""
    secondary_engines: Tuple[str, ...] = ()
    #: Which of the above were found, for the scorer and the audit.
    measured: Tuple[str, ...] = ()
    #: Documents actually read, so a claim can be traced to a filer.
    source_ids: Tuple[str, ...] = ()

    @property
    def is_specific(self) -> bool:
        """Enough measured particulars to describe THIS company."""
        return bool(self.segments) or len(self.measured) >= 2

    @property
    def multi_engine(self) -> bool:
        """More than one reportable segment is more than one engine.

        §5: Alphabet, Amazon, Microsoft and Meta are not one business, and
        flattening them into a class is how a reader is told less than the
        filing already says.
        """
        return len(self.segments) > 1

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip(" ,;:")
    return text


#: What a company offers its STAFF is not what it sells.
#:
#: MEASURED LIVE on the deployed preview, f8c183f. Meta's economic engine
#: rendered as "Meta Platforms, Inc. is a software platform business that
#: runs on competitive compensation and a wide range of benefits, including
#: many learning and development resources" -- the Human Capital section of
#: its own 10-K, read as what Meta sells, in the first sentence a chief
#: executive reads. `We offer ...` matched, and Item 1 states the employment
#: offer before it states the product one.
#:
#: The verb was already guarded here ("operate IS NOT SELLING"); the OBJECT
#: was not, so the same defect simply arrived through a different verb.
#:
#: "benefits" is deliberately NOT on its own list: an insurer sells benefits
#: to members, and a stoplist that refused the word would refuse a real
#: company's real product. It counts only alongside an employment marker,
#: which is what makes the sentence about staff.
_EMPLOYMENT_OBJECT = (
    "compensation", "employee", "personnel", "workforce",
    "learning and development", "paid time off", "parental leave",
    "401(k)", "retirement", "equity award", "stock-based award",
    "family care", "time away", "wellness", "resource groups",
)


#: A thing a company MIGHT do is not a thing it sells. Meta's filing has no
#: product sentence in this grammar at all, so vetoing the Human Capital ones
#: and continuing walked straight into Item 1A -- "we ... from time to time
#: have had, and in the future may have, quality issues resulting from the
#: design or manufacture of the products". A veto that only moves the wrong
#: answer along is not a repair.
_HYPOTHETICAL = (" may ", " could ", " would ", " might ", "from time to time",
                 "adversely", "if we ", "no assurance")

#: HOW REVENUE IS *ACCOUNTED FOR* IS NOT HOW THE COMPANY EARNS.
#:
#: MEASURED LIVE on 517180e6, Microsoft. Its economic engine rendered as
#: "... and we provide solution support and consulting services; revenue upon
#: transfer of control of promised products or services to customers in an
#: amount that reflects the consideration we expect to receive in exchange for
#: those products or services" -- the ASC 606 revenue-recognition policy,
#: presented to a chief executive as what Microsoft sells.
#:
#: This is the third arrival of one defect: the grammar of a filing sentence
#: does not tell you what the sentence is ABOUT. Staff offers came first,
#: hypotheticals second, and an accounting policy is simply the next section
#: written in the same shape.
#:
#: THESE PHRASES ARE UNAMBIGUOUS, which is why a lexical veto is safe here
#: where a bare word list would not be. "revenue" and "customers" appear in
#: every real product sentence and are deliberately absent; a company can
#: sell "services" but no company sells "a performance obligation". Each
#: entry is standard-setter vocabulary that has no use outside an accounting
#: policy -- so this cannot refuse a real description the way a stoplist on
#: "benefits" would have refused an insurer's actual product.
_ACCOUNTING_POLICY = (
    "transfer of control",
    "performance obligation",
    "in an amount that reflects the consideration",
    "expect to be entitled",
    "expect to receive in exchange",
    "revenue is recognized",
    "revenue is recognised",
    "asc 606",
    "topic 606",
    "standalone selling price",
    "contract asset",
    "contract liability",
    "deferred revenue is",
    "estimated useful li",
    "in accordance with gaap",
    "generally accepted accounting principles",
)


#: WHERE THE BUSINESS IS DESCRIBED, AND WHERE IT IS NOT.
#:
#: This is the real discriminator, and it is POSITIONAL rather than lexical.
#: MEASURED on Meta's 2025 10-K: "Human Capital" occurs exactly once, at
#: character 55,533, and ALL FIVE employment matches fall between 55,962 and
#: 59,041 -- immediately after it. Every risk-factor match is past 159,000,
#: well inside Item 1A. The Business section itself contains no sentence of
#: this shape, which means EMPTY is the honest answer for Meta and the class
#: prior plus its revenue basis is what the reader should get.
#:
#: A word list would have to grow once per filing; the heading does not.
_HUMAN_CAPITAL = re.compile(r"(?i)\bhuman capital\b")

#: Far enough in that a table-of-contents line cannot truncate the section.
_MIN_BUSINESS_TEXT = 2000


def _business_text(text: str) -> str:
    """Item 1 up to the Human Capital subsection, where there is one."""
    match = _HUMAN_CAPITAL.search(text or "")
    if match and match.start() > _MIN_BUSINESS_TEXT:
        return text[:match.start()]
    return text


def _is_employment_offer(clause: str) -> bool:
    """Is this clause the offer made to STAFF rather than to customers?"""
    low = (clause or "").lower()
    return any(marker in low for marker in _EMPLOYMENT_OBJECT)


def _is_accounting_policy(clause: str) -> bool:
    """Is this clause about how revenue is RECOGNISED rather than earned?

    A revenue-recognition policy is written in the same grammar as a product
    description and is about bookkeeping. See `_ACCOUNTING_POLICY`.
    """
    low = (clause or "").lower()
    return any(marker in low for marker in _ACCOUNTING_POLICY)


def _is_not_a_product(clause: str) -> bool:
    """Vetoes for `what_is_sold`: staff offers, hypotheticals, and policy."""
    low = f" {(clause or '').lower()} "
    return (_is_employment_offer(clause)
            or _is_accounting_policy(clause)
            or any(marker in low for marker in _HYPOTHETICAL))


def _clause(text: str, pattern: str, reject=None) -> str:
    """The first clause this pattern finds that `reject` does not veto.

    ITERATES rather than taking `re.search`'s first hit. A filing states many
    things with the same grammar, and the first one is not always the one
    meant -- when the earliest "We offer ..." is the employment offer, the
    product sentence is usually still there, further down. Vetoing without
    continuing would trade a wrong answer for an empty one.
    """
    for match in re.finditer(pattern, text):
        found = _clean(match.group(match.lastindex or 0))
        if not (_MIN_CLAUSE <= len(found)):
            continue
        if len(found) > _MAX_CLAUSE:
            cut = found[:_MAX_CLAUSE].rsplit(",", 1)[0]
            found = cut if len(cut) >= _MIN_CLAUSE else found[:_MAX_CLAUSE]
        if reject is not None and reject(found):
            continue
        return found
    return ""


_SEGMENTS = re.compile(
    r"(?P<count>one|two|three|four|five|six|seven|eight)\s+reportable"
    r"\s+segments?\s*[:,]?\s*(?P<names>[^.]{6,220})")
_COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8}


def _segment_names(count_word: str, listing: str) -> tuple:
    """Split "A, B and C" using the count the filing itself states.

    THE COUNT IS THE DISAMBIGUATOR. Adobe's three segments are "Digital
    Media", "Digital Experience" and "Publishing and Advertising" -- and
    splitting on " and " turns the third into two, inventing a fourth
    segment out of the company's own name for one. Splitting on commas
    alone leaves Cloudflare-shaped two-item lists joined. The filing says
    how many there are, so the split that produces that many is the right
    one and no heuristic is needed.
    """
    want = _COUNT_WORDS.get(str(count_word or "").lower(), 0)
    by_comma = [_clean(x) for x in re.split(r",\s*(?:and\s+)?", listing)]
    by_comma = [x for x in by_comma if x]
    if not by_comma:
        return ()
    if want and len(by_comma) == want:
        return tuple(by_comma)
    if not want or len(by_comma) > want:
        return ()
    # The final element carries the remaining segments, joined by "and".
    # Split it EXACTLY as many times as the stated count still needs, from
    # the left: Adobe's "Digital Experience and Publishing and Advertising"
    # is two segments, not three, and one split produces the right pair.
    need = want - len(by_comma)
    head, last = by_comma[:-1], by_comma[-1]
    tail = [_clean(x) for x in re.split(r"\s+and\s+", last, maxsplit=need)]
    parts = [x for x in head + tail if x]
    return tuple(parts) if len(parts) == want else ()

#: Per-field vetoes. Only `what_is_sold` needs one today, and it is a map
#: rather than a special case in the loop so the next field that needs one
#: does not become a second `if`.
_REJECT = {"what_is_sold": _is_not_a_product}

#: Fields that may only be read from the Business section. The others must
#: not be scoped: `margin_basis` and `capital_basis` are stated in MD&A,
#: which is past every boundary above, and cutting there would empty two
#: fields that were being read correctly.
_BUSINESS_ONLY = ("what_is_sold",)

_FIELDS = (
    # "operate" IS NOT SELLING. It matched "We operate in a very
    # competitive and rapidly changing environment" -- a risk factor -- and
    # rendered it as what Cloudflare sells. A verb only counts here when its
    # object is a thing a customer buys.
    ("what_is_sold",
     r"[Ww]e (?:sell|offer|provide|deliver|design|manufacture|produce)\s"
     r"(?!in\s|under\s|as\s|through\s|primarily in\s)"
     r"(?P<c>[^.]{20,240})"),
    ("revenue_basis",
     r"[Rr]evenue[s]?\s+(?:is|are)\s+(?:primarily\s+)?"
     r"(?:generated|derived|recognized|earned)\s+(?P<c>[^.]{20,240})"),
    ("pricing_mechanism",
     r"(?P<c>(?:pay-as-you-go|usage-based|consumption-based|per-seat|"
     r"per-user|subscription fees|list price|negotiated (?:contract )?price|"
     r"take rate|interchange|net price after rebates|spread)[^.]{0,200})"),
    ("margin_basis",
     r"(?:[Gg]ross margin|[Cc]ost of revenue|[Cc]ost of sales)\s+"
     r"(?:is|are|consists? of|primarily)\s+(?P<c>[^.]{20,240})"),
    ("capital_basis",
     r"(?:[Cc]apital expenditures?|[Pp]roperty and equipment)\s+"
     r"(?:is|are|consists? of|primarily|relate[sd]? to)\s+(?P<c>[^.]{20,240})"),
    ("customer",
     r"[Oo]ur customers (?:are|include|consist of|range from)\s+"
     r"(?P<c>[^.]{20,240})"),
    # --- v2 ---------------------------------------------------------------
    ("buyer",
     r"(?:[Ww]e (?:sell|market) (?:our|these) [a-z ]{2,40} (?:to|through)|"
     r"[Oo]ur (?:products|services|solutions) are (?:sold|purchased) by)\s+"
     r"(?P<c>[^.]{20,240})"),
    ("unit_of_sale",
     r"(?P<c>(?:[Ss]ubscriptions?|[Ll]icen[cs]es?|[Cc]ontracts?|[Pp]olicies|"
     r"[Ss]eats?|[Uu]nits?|[Oo]rders?|[Tt]ransactions?)\s+"
     r"(?:are|is)\s+(?:typically\s+|generally\s+)?"
     r"(?:sold|priced|billed|entered into|renewed)[^.]{10,200})"),
    ("volume_driver",
     r"(?:[Gg]rowth (?:in|of) (?:our )?revenue|[Rr]evenue growth)\s+"
     r"(?:is|was|has been)\s+(?:primarily\s+)?(?:driven|attributable)\s+"
     r"(?:by|to)\s+(?P<c>[^.]{20,240})"),
    ("growth_constraint",
     r"(?:[Oo]ur (?:ability|growth) (?:to grow |)?depends|"
     r"[Ww]e may (?:not )?be (?:unable|able) to (?:grow|scale))"
     r"[^.]{0,20}?\s+(?:on|upon)\s+(?P<c>[^.]{20,240})"),
)


#: The largest/smallest qualifiers a filing uses when it ranks its own
#: segments. Read only in a sentence that also names one of THIS filer's
#: segments, so a generic superlative cannot promote a segment on its own.
_LARGEST = re.compile(
    r"\b(?:largest|biggest|principal|primary|most significant)\b", re.I)
_MOST_PROFITABLE = re.compile(
    r"\b(?:highest[- ]margin|most profitable|greatest operating income|"
    r"largest (?:share of )?operating income)\b", re.I)
_STRATEGIC = re.compile(
    r"\b(?:strategic(?:ally)? (?:important|significant|critical)|"
    r"long[- ]term growth|future growth|growth engine|key to our "
    r"(?:strategy|future))\b", re.I)


def _engines(text: str, segments: Tuple[str, ...]) -> dict:
    """Which named segment is the revenue / profit / strategic engine.

    §7: a multi-engine filer is not one business, and forcing one is how a
    reader is told less than the filing already says. The three roles are
    frequently three different segments -- the one that books the revenue,
    the one that earns the margin, and the one the company is betting on.

    NOTHING IS INVENTED AND NOTHING IS INFERRED FROM A CLASS. A role is
    filled only when a sentence in this filer's own text carries both the
    qualifier and one of the segment names it just declared; otherwise the
    role stays empty, which is an honest state. A single-segment filer has
    one engine and all three roles are the same segment -- which is the
    correct reading, not a degenerate one.
    """
    if not segments:
        return {}
    if len(segments) == 1:
        only = segments[0]
        return {"revenue_engine": only, "profit_engine": only,
                "strategic_engine": only, "secondary_engines": ()}
    roles = {"revenue_engine": "", "profit_engine": "", "strategic_engine": ""}
    tests = (("revenue_engine", _LARGEST),
             ("profit_engine", _MOST_PROFITABLE),
             ("strategic_engine", _STRATEGIC))
    for sentence in re.split(r"(?<=[.])\s+", text):
        if len(sentence) > 400:
            continue
        present = [s for s in segments if s.lower() in sentence.lower()]
        if len(present) != 1:
            # A sentence naming two segments does not rank either of them,
            # and one naming none is about something else.
            continue
        for role, qualifier in tests:
            if not roles[role] and qualifier.search(sentence):
                roles[role] = present[0]
    named = {v for v in roles.values() if v}
    roles["secondary_engines"] = tuple(
        s for s in segments if s not in named) if named else tuple(
            segments[1:])
    return roles


def _subject_documents(documents, *, subject_cik: str = "") -> list:
    """The SUBJECT's own filings. A rival's filing describes the rival.

    Without a CIK nothing can be attributed, so nothing is read: inventing an
    owner is how one company's business model came to describe another.
    """
    digits = "".join(c for c in str(subject_cik or "") if c.isdigit())
    digits = digits.lstrip("0")
    if not digits:
        return []
    out = []
    for document in documents or ():
        url = str(document.get("final_url") or
                  document.get("original_url") or "")
        filer = re.search(r"/edgar/data/(\d+)", url)
        if filer and filer.group(1).lstrip("0") == digits:
            out.append(document)
    return out


def architecture_of(documents, *, company: str = "",
                    subject_cik: str = "") -> EconomicArchitecture:
    """Read this company's economics out of its own filings. Never raises."""
    try:
        own = _subject_documents(documents, subject_cik=subject_cik)
        if not own:
            return EconomicArchitecture(company=company)
        text = " ".join(
            re.sub(r"\s+", " ", str(d.get("text_content") or ""))
            for d in own)
        segments: Tuple[str, ...] = ()
        match = _SEGMENTS.search(text)
        if match:
            names = _segment_names(match.group("count"),
                                   match.group("names"))
            segments = tuple(n for n in names if 2 < len(n) <= 60)[:8]
        found = {}
        business = _business_text(text)
        for name, pattern in _FIELDS:
            clause = _clause(business if name in _BUSINESS_ONLY else text,
                             pattern, reject=_REJECT.get(name))
            if clause:
                found[name] = clause
        found.update({k: v for k, v in _engines(text, segments).items() if v})
        return EconomicArchitecture(
            company=company, segments=segments,
            measured=tuple(sorted(found)) + (("segments",) if segments else ()),
            source_ids=tuple(str(d.get("source_id") or "") for d in own)[:12],
            **found)
    except Exception:                                       # noqa: BLE001
        # A description that cannot be measured falls back to the class
        # prior. It must never be able to fail the analysis.
        return EconomicArchitecture(company=company)


def describe(architecture: EconomicArchitecture, *, name: str,
             sector: str = "", class_prior: str = "") -> str:
    """The business-model sentence, built from what was measured.

    The class prior is the FALLBACK and no longer the answer. When the
    filing said what the company sells, that is what the reader is told.
    """
    parts = []
    if architecture.what_is_sold:
        parts.append(architecture.what_is_sold)
    if architecture.revenue_basis:
        parts.append(f"revenue {architecture.revenue_basis}"
                     if not architecture.revenue_basis.startswith("revenue")
                     else architecture.revenue_basis)
    if not parts and class_prior:
        parts.append(class_prior)
    if not parts:
        return ""
    body = "; ".join(parts[:2])
    lead = (f"{name} is {_article(sector)} {sector} business that runs on "
            if sector else f"{name} runs on ")
    out = _clean(lead + body[0].lower() + body[1:])
    return out if out.endswith(".") else out + "."


def _article(word: str) -> str:
    return "an" if str(word or "")[:1].lower() in "aeiou" else "a"

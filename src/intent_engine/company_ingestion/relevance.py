"""Is this document ABOUT the company, or does it merely contain its name?

WHY THIS IS A SEPARATE AXIS FROM INDEPENDENCE
---------------------------------------------
Independence answers "did somebody other than the subject write this?".
Relevance answers "does what they wrote bear on the claim?". They are
orthogonal, and the product shipped live proving it:

    Cloudflare's sole independent origin was EVENTIKO INC.'s 10-K, which
    mentions Cloudflare exactly once:

        "All hosting and hosting related services of these websites are
         engaged via reputable companies such as Namecheap, Godaddy and
         Cloudflare."

That is a genuinely independent registrant. It is also EVENTIKO describing
ITS OWN vendor arrangements, and it carries no information about Cloudflare's
strategy, market or competitive position. Counting it made the dossier read
PARTIALLY_INDEPENDENT when the honest reading is that nothing independent and
relevant supports the claim at all.

Collapsing the two axes is what produced that: a filter that asks only "whose
voice is this?" will happily accept a stranger saying nothing.

THE MENTION IS THE UNIT, NOT THE DOCUMENT
-----------------------------------------
A 10-K is 78,000 characters and the subject appears in one of them. Scoring
the document as a whole cannot see that; scoring each MENTION can. The
question asked of every mention is whose behaviour the sentence describes --
the subject's, or the author's -- because "we buy hosting from Cloudflare"
is a fact about the author.

OVER-REFUSAL IS THE HAZARD ON THIS SIDE
---------------------------------------
Deleting a real independent observation is worse than keeping a weak one:
the count is the product's most load-bearing number and it is already scarce.
So only a POSITIVE finding of irrelevance demotes. No text, no subject terms,
or anything this module cannot read is UNMEASURABLE, and UNMEASURABLE never
demotes.
"""
from __future__ import annotations

import re
from typing import Dict, Sequence

CONTRACT = "evidence_relevance.v1"

# --- the closed vocabulary ---------------------------------------------------
DIRECTLY_RELEVANT = "DIRECTLY_RELEVANT"
CONTEXTUALLY_RELEVANT = "CONTEXTUALLY_RELEVANT"
WEAKLY_RELEVANT = "WEAKLY_RELEVANT"
IRRELEVANT = "IRRELEVANT"
UNMEASURABLE = "UNMEASURABLE"
REFUSED = "REFUSED"

RELEVANCE_STATES = (DIRECTLY_RELEVANT, CONTEXTUALLY_RELEVANT, WEAKLY_RELEVANT,
                    IRRELEVANT, UNMEASURABLE, REFUSED)

#: May a source in this state add an INDEPENDENT observation? UNMEASURABLE is
#: here deliberately: "we could not read it" must not silently delete evidence,
#: and the count already reports unknown lineage separately.
SUPPORTS_CORROBORATION = frozenset({DIRECTLY_RELEVANT, CONTEXTUALLY_RELEVANT,
                                    WEAKLY_RELEVANT, UNMEASURABLE})

#: Structure, not prose. A name in a table of contents is a page number.
_BOILERPLATE = re.compile(
    r"(exhibit\s+index|list of subsidiaries|table of contents|signature page|"
    r"trademarks? of (their|its) respective|forward-looking statements)", re.I)

#: "such as A, B and C" / "including X, Y, Z" -- the subject is an EXAMPLE in
#: somebody else's sentence about themselves. This is the EVENTIKO shape.
_ENUMERATION = re.compile(
    r"\b(such as|including|includes|e\.g\.|for example|among (?:them|others)|"
    r"like)\b", re.I)

#: Verbs that make a sentence a claim ABOUT the subject's business rather than
#: a mention of its name. Deliberately commercial: this is a strategy product.
_SUBSTANTIVE = re.compile(
    r"\b(compet(?:e|es|ing|itor|ition)|market share|customers? (?:of|from)|"
    r"migrat(?:e|ed|ing|ion)|switch(?:ed|ing)? (?:to|from)|replac(?:e|ed|ing)|"
    r"partner(?:s|ed|ship)?|acquir(?:e|ed|ing)|revenue|pricing|price|"
    r"contract|agreement|reseller|integrat(?:e|ed|ion)|alternativ)\b", re.I)

#: First-person subjects. "WE use Cloudflare" is a fact about the author.
_AUTHOR_VOICE = re.compile(
    r"\b(we|our|us|the company'?s?|registrant)\b", re.I)

#: A PERSON'S CAREER, not a company's business.
#:
#: Measured live: of four "independent relevant origins" retrieved for
#: Cloudflare, two were executive biographies -- "Garfield served as the Vice
#: President of Finance of Cloudflare, Inc." in Adobe's proxy, and a director
#: listing in Coursera's. Both name the company in a sentence whose subject is
#: an individual. Read as corroboration they say a company we have never
#: checked employs someone, which bears on nothing a reader is deciding.
#: Measured again on Toyota: Tesla's proxy says "Denholm also SERVED AT Toyota
#: Motor Corporation Australia for seven years", which the as/on form missed.
#: The preposition is not the signal -- a career verb pointed at the company is.
_BIOGRAPHICAL = re.compile(
    r"\b(serve[sd]?\s+(?:as|at|on|with)|"
    r"work(?:s|ed)?\s+(?:as|at|for)|"
    r"(?:prior|previous(?:ly)?)\s+to\s+joining|before\s+joining|"
    r"joined\s+(?:the\s+)?(?:company|firm|board)|"
    r"was\s+appointed|has\s+held\s+(?:various|senior)|"
    r"from\s+\d{4}\s+(?:to|until)\s+(?:\d{4}|present)|"
    r"age\s+\d{2}\b|"
    r"he\s+(?:is|was|has)|she\s+(?:is|was|has)|they\s+(?:are|were|have)|"
    r"holds?\s+a\s+(?:B\.?[AS]|M\.?[BAS]|Ph\.?D)|"
    r"(?:board|director|officer|chair)\s+of)\b", re.I)

#: THE AUTHOR'S OWN ARRANGEMENTS, in the supply direction.
#:
#: The enumeration rule below already catches "vendors such as X". It does not
#: catch the same disclosure written as a plain sentence -- "The Company
#: purchases cloud operations services from Cloudflare Inc." -- and both of
#: those forms are the author describing ITSELF. Measured live, that shape was
#: the other half of Cloudflare's four origins.
#:
#: This is not a claim that the fact is worthless: a customer disclosure is
#: real evidence that the subject has customers. It is a claim about WHOSE
#: account it is, and an account of the author's own supply chain cannot
#: corroborate a strategic reading of the supplier.
_SUPPLY_DISCLOSURE = re.compile(
    r"\b(purchas(?:e|es|ed|ing)|procur(?:e|es|ed)|licen[cs](?:e|es|ed)|"
    r"subscrib(?:e|es|ed)|us(?:e|es|ed)|utiliz(?:e|es|ed)|rel(?:y|ies|ied)\s+on|"
    r"depend(?:s|ed)?\s+on|host(?:ed|s)?\s+(?:by|on|with)|"
    r"operated\s+by|provided\s+by|served\s+by|behind)\b", re.I)

#: A LEGAL CAPTION IS A CITATION, NOT A CLAIM. "Bank of America Corporation,
#: et al." names the company as a party to a case; it asserts nothing about
#: the business that a reader could act on.
_CAPTION = re.compile(r"\b(et\s+al\.?|v\.\s+[A-Z]|,\s+No\.\s+\d)", re.I)

#: A list bullet, not a sentence.
_BULLET_LEAD = re.compile(r"^\s*[•·▪●‣\-\*]\s*")

#: Tokens that are quantities rather than words.
_NUMERIC_TOKEN = re.compile(r"^[\$\(\)\[\]<>=~\-–—%,.:/\d]+$")

#: Above this share of quantity-tokens, a span is a TABLE ROW.
#:
#: MEASURED LIVE ON THREE SECTORS AT ONCE. Bank of America's strongest
#: "evidence" was a fund's holdings row -- "$ 1,500,000 3/11/27 Bank of
#: America Corporation 1.66 % $ 1,497,566 2.16 %" -- and Toyota's was a
#: customer-concentration row, "Toyota Motor Corporation 12.2% 12.5% 11.5%".
#: Both are genuinely independent, genuinely about the company, and assert
#: nothing. Sentence splitting cannot tell a row from a claim, so the shape
#: of the span has to.
_TABLE_ROW_RATIO = 0.25

#: Below this many word-tokens there is not enough sentence to carry a claim.
_MIN_PROSE_WORDS = 5

#: Below this much text we are holding an EXCERPT, not a filing, and the shape
#: of a span says nothing about the document it came from.
_FULL_TEXT_CHARS = 400


def _is_prose(span: str) -> bool:
    """Whether this span is a sentence at all, as opposed to a row or a label.

    A POSITIVE FINDING OF NON-PROSE, like every other demotion here. The
    default stays permissive because deleting a real observation is worse
    than carrying a weak one -- this only refuses spans whose SHAPE shows
    they were never prose.
    """
    if _BULLET_LEAD.match(span or ""):
        return False
    if _CAPTION.search(span or ""):
        return False
    tokens = [t for t in re.split(r"\s+", (span or "").strip()) if t]
    if not tokens:
        return False
    words = [t for t in tokens if re.search(r"[A-Za-z]{2}", t)]
    if len(words) < _MIN_PROSE_WORDS:
        return False
    numeric = sum(1 for t in tokens if _NUMERIC_TOKEN.match(t))
    return (numeric / len(tokens)) < _TABLE_ROW_RATIO


_SENTENCE = re.compile(r"(?<=[.;!?])\s+")


def _sentences(text: str):
    return [s for s in _SENTENCE.split(text or "") if s.strip()]


#: LEADING WORDS THAT ARE NOT AN IDENTITY.
#:
#: MEASURED LIVE, AND THE WORST FALSE-EVIDENCE DEFECT FOUND SO FAR. The bare
#: leading word is added because filings say "Cloudflare", not "Cloudflare,
#: Inc." -- but "Bank of America Corporation" leads with "Bank", so every
#: sentence containing the word `bank` counted as a mention of the company.
#: Bank of America's four "independent relevant origins" were a futures fund
#: describing "segregated bank accounts" and a director biography at Virginia
#: National Bank. The company was never named in any of them.
#:
#: A word here is refused as a STANDALONE term only. The full name still
#: matches, so recall for the real company is untouched -- this deletes
#: collisions, not observations. Common to bank, insurance and utility names,
#: which is exactly where the collision is dense.
_GENERIC_LEAD = frozenset({
    "bank", "banks", "banking", "first", "national", "general", "american",
    "america", "united", "standard", "global", "international", "federal",
    "capital", "central", "pacific", "atlantic", "western", "eastern",
    "northern", "southern", "security", "trust", "republic", "community",
    "commerce", "commercial", "industrial", "universal", "allied", "premier",
    "superior", "continental", "empire", "liberty", "pioneer", "summit",
    "heritage", "alliance", "peoples", "citizens", "farmers", "merchants",
    "home", "public", "union", "state", "city", "county", "north", "south",
    "east", "west", "new", "great", "royal", "crown", "prime", "core",
    "united's", "advance", "advanced", "applied", "integrated", "unified",
})


def _terms(subject_name: str, subject_domain: str,
           extra: Sequence[str] = ()) -> list:
    """Names this company is likely to be called, without inviting collisions.

    The bare leading word is included because filings say "Cloudflare", not
    "Cloudflare, Inc." -- but it is matched on WORD BOUNDARIES downstream, so
    "alpha" cannot match inside "Alphabet". That regression is why this
    returns terms rather than doing substring work itself.
    """
    out = []
    name = (subject_name or "").strip()
    if name:
        out.append(name)
        lead = re.split(r"[,\s]+", name)[0].strip()
        # Two characters is not an identity; it is a collision waiting.
        if (len(lead) > 3 and lead.lower() not in ("the", "inc")
                and lead.lower() not in _GENERIC_LEAD):
            out.append(lead)
    host = (subject_domain or "").strip().lower()
    if host:
        stem = host.split(".")[0]
        if len(stem) > 3:
            out.append(stem)
    out.extend(t for t in extra if str(t or "").strip())
    seen, uniq = set(), []
    for t in out:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    return uniq


def _mentions(text: str, terms: Sequence[str]) -> list:
    if not terms:
        return []
    pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)
    return [s for s in _sentences(text) if pattern.search(s)]


def _author_pattern(author_name: str):
    """The author naming ITSELF. None when we do not know who wrote this.

    AUTHOR VOICE IS NOT ONLY PRONOUNS. Measured live: ChargePoint's 10-K says
    "ChargePoint's primary environments are behind the Content Delivery
    Network operated by Cloudflare, Inc." -- a first-person rule sees no "we"
    there and reads a supplier disclosure as an independent account of the
    supplier. The nearest governing subject decides ownership, and here it is
    the filer's own name.

    Only the leading distinguishing word, matched on word boundaries: the same
    discipline the subject terms use, for the same reason -- "alpha" must not
    match inside "Alphabet". A sentence where the author names BOTH itself and
    the subject is left alone by this, because it is demoted only in
    combination with a supply verb.
    """
    cleaned = re.sub(r"\((?:CIK|[A-Z.]{1,6})[^)]*\)", " ", author_name or "")
    words = [w for w in re.findall(r"[A-Za-z0-9]+", cleaned)
             if w.lower() not in _AUTHOR_LEGAL_FORMS]
    if not words or len(words[0]) <= 3:
        return None
    return re.compile(r"\b" + re.escape(words[0]) + r"(?:'s|’s)?\b", re.I)


_AUTHOR_LEGAL_FORMS = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "llc", "lp", "llp", "plc", "sa", "nv", "ag", "se", "gmbh",
    "holdings", "holding", "group", "the",
})


def adjudicate(document: dict, *, subject_name: str = "",
               subject_domain: str = "", aliases: Sequence[str] = (),
               author_name: str = "",
               self_authored: bool = False) -> Dict[str, object]:
    """How much this document bears on a claim about the subject.

    `self_authored` short-circuits to DIRECTLY_RELEVANT: a company's own
    pricing page is unambiguously about the company even when it never spells
    its own name, and running the mention test on it would mark it irrelevant
    for a reason that has nothing to do with its content. Those rows are not
    independence-bearing anyway, so this cannot inflate a count.
    """
    text = str(document.get("text_content") or "")
    terms = _terms(subject_name, subject_domain, aliases)

    if self_authored:
        return _verdict(DIRECTLY_RELEVANT,
                        "the company's own account of itself", 0, 0)
    if not terms:
        return _verdict(UNMEASURABLE,
                        "the subject was not identified, so relevance to it "
                        "could not be judged", 0, 0)
    if not text.strip():
        return _verdict(UNMEASURABLE,
                        "no readable text was retained for this document", 0, 0)

    author = _author_pattern(author_name)
    mentions = _mentions(text, terms)
    if not mentions:
        return _verdict(
            IRRELEVANT,
            "the document never names the company, so it cannot support a "
            "claim about it", 0, 0)

    substantive = 0
    incidental = 0
    biographical = 0
    tabular = 0
    #: THE SPANS THAT ACTUALLY DROVE THE VERDICT. A surface that shows the
    #: first mention instead will print a holdings row beside the word
    #: DIRECTLY_RELEVANT -- measured live on Bank of America and Cloudflare,
    #: where the excerpt and the reason came from different sentences.
    counted = []
    #: A whole filing, or an excerpt of one? Sentence SHAPE is only evidence
    #: when the sentence boundaries are the document's own.
    reading_full_text = len(text.strip()) >= _FULL_TEXT_CHARS
    for sentence in mentions:
        if _BOILERPLATE.search(sentence):
            continue
        # IS THIS A SENTENCE? A holdings row, a bullet or a case caption names
        # the company and claims nothing. Counted separately so a zero can say
        # which kind of nothing it found.
        #
        # ONLY WHEN WE HOLD THE WHOLE DOCUMENT. A span from a short input is
        # short because of OUR excerpting, and refusing it would demote a real
        # filing for a fact about our snippet -- the exact over-refusal this
        # module's docstring forbids.
        if reading_full_text and not _is_prose(sentence):
            tabular += 1
            continue
        # WHOSE BEHAVIOUR IS THIS? A first-person sentence listing the
        # subject among suppliers is the AUTHOR describing itself.
        listed = bool(_ENUMERATION.search(sentence))
        author_voice = bool(_AUTHOR_VOICE.search(sentence)) or bool(
            author and author.search(sentence))
        if listed and author_voice:
            incidental += 1
            continue
        # WHOSE LIFE IS THIS? A sentence whose subject is a person, that
        # happens to name a company, is about the person.
        if _BIOGRAPHICAL.search(sentence):
            biographical += 1
            continue
        # THE SAME AUTHOR-VOICE RULE, WRITTEN AS A PLAIN SENTENCE. Demoted on
        # a POSITIVE finding -- author voice AND a supply verb -- never by
        # flipping the default, because a wall that demotes on absence
        # shreds true evidence for a reason about our patterns.
        if author_voice and _SUPPLY_DISCLOSURE.search(sentence):
            incidental += 1
            continue
        if _SUBSTANTIVE.search(sentence):
            substantive += 1
            counted.append(sentence)
        elif listed:
            incidental += 1
        else:
            substantive += 1
            counted.append(sentence)

    if substantive >= 2:
        return _verdict(DIRECTLY_RELEVANT,
                        f"{substantive} passage(s) discuss the company",
                        substantive, incidental, counted)
    if substantive == 1:
        return _verdict(CONTEXTUALLY_RELEVANT,
                        "one passage discusses the company", 1, incidental,
                        counted)
    # THREE DISTINCT REASONS, because they are three distinct facts about the
    # document and a reader acts differently on each. A single merged sentence
    # would be shorter and would stop saying which one happened.
    if tabular and not (incidental or biographical):
        return _verdict(
            IRRELEVANT,
            f"the company appears {tabular} time(s), only in tables, lists or "
            f"case captions rather than in a statement about it",
            0, tabular)
    if biographical and not incidental:
        return _verdict(
            IRRELEVANT,
            f"the company is named {biographical} time(s), only in the career "
            f"history of an individual",
            0, biographical)
    if incidental and not biographical:
        return _verdict(
            IRRELEVANT,
            f"the company is named {incidental} time(s), only as an example "
            f"in the author's account of its own arrangements",
            0, incidental)
    if incidental or biographical or tabular:
        total = incidental + biographical + tabular
        return _verdict(
            IRRELEVANT,
            f"the company is named {total} time(s), only in the author's "
            f"account of its own arrangements, its people, or its tables",
            0, total)
    return _verdict(IRRELEVANT,
                    "the company is named only in boilerplate", 0, 0)


def _verdict(state: str, reason: str, substantive: int,
             incidental: int, counted: Sequence[str] = ()) -> Dict[str, object]:
    return {"contract": CONTRACT, "state": state, "reason": reason,
            "substantive_mentions": substantive,
            "incidental_mentions": incidental,
            # The sentences the verdict was actually built from, in order.
            "counted_spans": [str(c) for c in counted],
            "supports_corroboration": state in SUPPORTS_CORROBORATION}


def plain_statement(verdict: Dict[str, object]) -> str:
    """§9 -- what a reader is told when a source is set aside."""
    state = str((verdict or {}).get("state") or "")
    if state == IRRELEVANT:
        return ("Independent of the company, but it does not say enough "
                "about it to support this claim")
    if state == UNMEASURABLE:
        return "Relevance to this claim could not be assessed"
    if state == DIRECTLY_RELEVANT:
        return "Discusses the company directly"
    if state == CONTEXTUALLY_RELEVANT:
        return "Mentions the company in a relevant context"
    if state == WEAKLY_RELEVANT:
        return "Mentions the company only in passing"
    return "Set aside"


# =============================================================================
# DISCOVERY COVERAGE -- "we found none" is not "we did not look"
# =============================================================================
#
# The relevance wall took Cloudflare's independent origins to zero, which is
# honest about the evidence in the dossier and says NOTHING about the world.
# A dossier reporting zero can mean two opposite things:
#
#     FOUND_NONE       we searched adequately and no independent relevant
#                      source exists to be found
#     FAILED_TO_FIND   we did not search the places where it would be
#
# The product could state the first only if it could measure the second, and
# it cannot yet. Reporting a bare zero lets a reader infer the stronger,
# flattering claim -- that the company genuinely has no outside coverage --
# from what is actually a fact about our retrieval.
#
# This is the same class as the lineage vocabulary: an absence needs a state,
# and the state has to say whose absence it is.

DISCOVERY_NOT_RUN = "DISCOVERY_NOT_RUN"
DISCOVERY_PARTIAL = "DISCOVERY_PARTIAL"
DISCOVERY_ADEQUATE = "DISCOVERY_ADEQUATE"
DISCOVERY_EXHAUSTED = "DISCOVERY_EXHAUSTED"
DISCOVERY_BLOCKED = "DISCOVERY_BLOCKED"

DISCOVERY_STATES = (DISCOVERY_NOT_RUN, DISCOVERY_PARTIAL, DISCOVERY_ADEQUATE,
                    DISCOVERY_EXHAUSTED, DISCOVERY_BLOCKED)

#: Only from these may "none exists" be said. Everything else means the zero
#: is a fact about the search, not about the company.
SUPPORTS_FOUND_NONE = frozenset({DISCOVERY_ADEQUATE, DISCOVERY_EXHAUSTED})

FOUND_NONE = "FOUND_NONE"
FAILED_TO_FIND = "FAILED_TO_FIND"
HAVE_INDEPENDENT = "HAVE_INDEPENDENT"


def zero_reading(*, independent_relevant: int, coverage: str,
                 channels_attempted: int = 0,
                 channels_successful: int = 0) -> dict:
    """What a zero independent-origin count actually licenses us to say.

    Returns the reading AND the sentence, because the whole failure this
    prevents is a surface rendering its own gloss on a number.
    """
    coverage = coverage if coverage in DISCOVERY_STATES else DISCOVERY_NOT_RUN
    if independent_relevant > 0:
        return {"reading": HAVE_INDEPENDENT, "coverage": coverage,
                "channels_attempted": channels_attempted,
                "channels_successful": channels_successful,
                "statement": ""}
    if coverage in SUPPORTS_FOUND_NONE:
        return {"reading": FOUND_NONE, "coverage": coverage,
                "channels_attempted": channels_attempted,
                "channels_successful": channels_successful,
                "statement": (
                    "We searched for independent coverage of this company and "
                    "found none that bears on this question. That is a "
                    "finding about the company.")}
    return {"reading": FAILED_TO_FIND, "coverage": coverage,
            "channels_attempted": channels_attempted,
            "channels_successful": channels_successful,
            "statement": (
                "No independent source in this dossier supports the reading. "
                "That is a limit of what we retrieved, not evidence that no "
                "independent coverage exists.")}

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

_SENTENCE = re.compile(r"(?<=[.;!?])\s+")


def _sentences(text: str):
    return [s for s in _SENTENCE.split(text or "") if s.strip()]


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
        if len(lead) > 3 and lead.lower() not in ("the", "inc"):
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


def adjudicate(document: dict, *, subject_name: str = "",
               subject_domain: str = "", aliases: Sequence[str] = (),
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

    mentions = _mentions(text, terms)
    if not mentions:
        return _verdict(
            IRRELEVANT,
            "the document never names the company, so it cannot support a "
            "claim about it", 0, 0)

    substantive = 0
    incidental = 0
    for sentence in mentions:
        if _BOILERPLATE.search(sentence):
            continue
        # WHOSE BEHAVIOUR IS THIS? A first-person sentence listing the
        # subject among suppliers is the AUTHOR describing itself.
        listed = bool(_ENUMERATION.search(sentence))
        author_voice = bool(_AUTHOR_VOICE.search(sentence))
        if listed and author_voice:
            incidental += 1
            continue
        if _SUBSTANTIVE.search(sentence):
            substantive += 1
        elif listed:
            incidental += 1
        else:
            substantive += 1

    if substantive >= 2:
        return _verdict(DIRECTLY_RELEVANT,
                        f"{substantive} passage(s) discuss the company",
                        substantive, incidental)
    if substantive == 1:
        return _verdict(CONTEXTUALLY_RELEVANT,
                        "one passage discusses the company", 1, incidental)
    if incidental:
        return _verdict(
            IRRELEVANT,
            f"the company is named {incidental} time(s), only as an example "
            f"in the author's account of its own arrangements",
            0, incidental)
    return _verdict(IRRELEVANT,
                    "the company is named only in boilerplate", 0, 0)


def _verdict(state: str, reason: str, substantive: int,
             incidental: int) -> Dict[str, object]:
    return {"contract": CONTRACT, "state": state, "reason": reason,
            "substantive_mentions": substantive,
            "incidental_mentions": incidental,
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

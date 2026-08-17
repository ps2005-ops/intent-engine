"""The competitive reality ladder: who takes this decision away from us.

WHAT WAS MEASURED, AND WHY THE PREVIOUS DIAGNOSIS WAS WRONG
-----------------------------------------------------------
`company_specificity` was capped at 8.0 on five of seven golden companies by
one rule: rivals were carried, and none of them was named by the company
itself. The recorded explanation was that the subject's own annual filing had
not been mined, and that extracting its Competition section would close it.

That premise was measured before it was built on, and it is false. Cloudflare's
10-K *is* retrieved, its Competition section *is* located, and it reads:

    "We compete in the market for network services primarily across three
     categories: - On-premises network hardware vendors ... - Point solution
     vendors, which provide cloud-based products and services to address a
     single use case ... public cloud vendors"

There is no company name in it. There is no company name in most of them. A
modern 10-K Competition section names **classes of rival and the ground they
contest**, because naming a firm invites a claim and naming a category does
not. The extractor accepted only capitalised proper nouns, so it threw the
company's own account of its market away and fell back to structural peers --
Adobe, Constellation and Databricks for Cloudflare, a set no Cloudflare
customer has ever chosen between.

So the retrieval was never the constraint. The **contract** was: a competitor
had to be a company. That is the assumption this module removes.

    A COMPETITOR IS WHATEVER THE CUSTOMER COULD DO INSTEAD.

Sometimes that is a firm. More often, in the company's own words, it is a
category of vendor, a thing the customer builds in-house, a spreadsheet, an
incumbent workflow nobody is paid to defend, or a platform that bundles the
capability away. Every one of those is decision-relevant, every one is
company-specific, and every one is stated on the record by the subject.

THE LADDER
----------
Ten rungs, strongest first. The rung is not a quality score -- it records
*where the claim came from*, so a reader can see that rung 1 is somebody's
name in somebody's filing and rung 9 is an inference from business model.

    1  NAMED_BY_SUBJECT      the company named it, in its own filing
    2  NAMED_BY_CUSTOMER     a customer described the alternative they weighed
    3  NAMED_BY_RIVAL        a third party's filing names this company's market
    4  NAMED_BY_ANALYST      independent industry or analyst evidence
    5  CONTESTED_CATEGORY    the company named the CLASS it competes with
    6  WORKFLOW_SUBSTITUTE   the job is done today by a process, not a product
    7  INTERNAL_BUILD        the customer's own engineering is the alternative
    8  DISPLACEMENT          a technology shift removes the need to choose
    9  STRUCTURAL_PEER       same business model; not a stated rival
   10  UNRESOLVED            nothing defensible, and the measurement to get it

Rungs 1-4 are attributions: somebody said it. Rungs 5-8 are still the
company's own words -- a contested category IS a quotation -- but the
*identity* is a class rather than a firm, and the row says so rather than
inventing a member of the class. Rung 9 is honest and weak, and rung 10 is a
real rung reached often, carrying the measurement that would close it.

WHAT EVERY ROW MUST CARRY (§2)
------------------------------
identity, type, mechanism, evidence, independence, confidence, why it matters,
and what would disprove it. `Rival` refuses at construction to exist without
a mechanism and a disproof, because a competitor with no mechanism is a name
on a slide and a competitor with no disproof cannot be wrong, which means it
was never a claim.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Sequence, Tuple

CONTRACT = "competitive_ladder.v1"

# --- the rungs -------------------------------------------------------------
NAMED_BY_SUBJECT = "NAMED_BY_SUBJECT"
NAMED_BY_CUSTOMER = "NAMED_BY_CUSTOMER"
NAMED_BY_RIVAL = "NAMED_BY_RIVAL"
NAMED_BY_ANALYST = "NAMED_BY_ANALYST"
CONTESTED_CATEGORY = "CONTESTED_CATEGORY"
WORKFLOW_SUBSTITUTE = "WORKFLOW_SUBSTITUTE"
INTERNAL_BUILD = "INTERNAL_BUILD"
DISPLACEMENT = "DISPLACEMENT"
STRUCTURAL_PEER = "STRUCTURAL_PEER"
UNRESOLVED = "UNRESOLVED"

RUNGS = (NAMED_BY_SUBJECT, NAMED_BY_CUSTOMER, NAMED_BY_RIVAL,
         NAMED_BY_ANALYST, CONTESTED_CATEGORY, WORKFLOW_SUBSTITUTE,
         INTERNAL_BUILD, DISPLACEMENT, STRUCTURAL_PEER, UNRESOLVED)

RUNG_NUMBER = {rung: i + 1 for i, rung in enumerate(RUNGS)}

#: What the reader sees. Never the enum (§73).
RUNG_LABEL = {
    NAMED_BY_SUBJECT: "Named by the company",
    NAMED_BY_CUSTOMER: "Named by a customer",
    NAMED_BY_RIVAL: "Named by a rival",
    NAMED_BY_ANALYST: "Named by an independent source",
    CONTESTED_CATEGORY: "A category the company says it competes with",
    WORKFLOW_SUBSTITUTE: "The way the job is done today",
    INTERNAL_BUILD: "The customer's own engineering",
    DISPLACEMENT: "A shift that removes the choice",
    STRUCTURAL_PEER: "A structural peer, not a stated rival",
    UNRESOLVED: "Not established",
}

RUNG_MEANING = {
    NAMED_BY_SUBJECT: "the company named this rival in its own filing",
    NAMED_BY_CUSTOMER: "a customer described weighing this alternative",
    NAMED_BY_RIVAL: "another filer names this company's market as its own",
    NAMED_BY_ANALYST: "an independent source places them in one market",
    CONTESTED_CATEGORY: "the company named the class, not a member of it, so "
                        "no firm is asserted here",
    WORKFLOW_SUBSTITUTE: "the customer already has a way of doing this and "
                         "nobody is paid to defend it",
    INTERNAL_BUILD: "the customer can build it, and the decision is buy "
                    "versus build rather than which vendor",
    DISPLACEMENT: "a technology or regulatory shift changes what is being "
                  "bought at all",
    STRUCTURAL_PEER: "the same business model, which is not the same as "
                     "competing for the same customer",
    UNRESOLVED: "no alternative is established, and what would settle it",
}

# --- the kinds of alternative (§2) -----------------------------------------
DIRECT = "DIRECT"
ADJACENT = "ADJACENT"
SUBSTITUTE = "SUBSTITUTE"
BUILD_IN_HOUSE = "BUILD_IN_HOUSE"
MANUAL_WORKFLOW = "MANUAL_WORKFLOW"
DO_NOTHING = "DO_NOTHING"
PLATFORM_BUNDLE = "PLATFORM_BUNDLE"
OPEN_SOURCE = "OPEN_SOURCE"
CHANNEL_SHIFT = "CHANNEL_SHIFT"
AI_REPLACEMENT = "AI_REPLACEMENT"
AI_ENTRANT = "AI_ENTRANT"
REGULATORY = "REGULATORY"
BEHAVIOUR_SHIFT = "BEHAVIOUR_SHIFT"
PEER = "PEER"

KINDS = (DIRECT, ADJACENT, SUBSTITUTE, BUILD_IN_HOUSE, MANUAL_WORKFLOW,
         DO_NOTHING, PLATFORM_BUNDLE, OPEN_SOURCE, CHANNEL_SHIFT,
         AI_REPLACEMENT, AI_ENTRANT, REGULATORY, BEHAVIOUR_SHIFT, PEER)

KIND_LABEL = {
    DIRECT: "a direct competitor",
    ADJACENT: "an adjacent competitor",
    SUBSTITUTE: "a substitute",
    BUILD_IN_HOUSE: "the customer building it themselves",
    MANUAL_WORKFLOW: "the manual process this replaces",
    DO_NOTHING: "the customer doing nothing",
    PLATFORM_BUNDLE: "a platform that bundles this away",
    OPEN_SOURCE: "an open-source alternative",
    CHANNEL_SHIFT: "the channel going around us",
    AI_REPLACEMENT: "automation removing the need",
    AI_ENTRANT: "an entrant built on automation",
    REGULATORY: "a regulatory or mandated alternative",
    BEHAVIOUR_SHIFT: "customers changing what they do",
    PEER: "a structural peer",
}

#: A rung is either an attribution or a reading. Only the first four let a
#: surface say "named by".
ATTRIBUTED = frozenset({NAMED_BY_SUBJECT, NAMED_BY_CUSTOMER, NAMED_BY_RIVAL,
                        NAMED_BY_ANALYST})

#: Rungs that still rest on the subject's own words, even though the identity
#: is a class rather than a firm. These are what closes company specificity:
#: a contested category is quoted, dated and signed, and it differs between
#: any two companies in a way a peer list never does.
FROM_SUBJECT_WORDS = frozenset({NAMED_BY_SUBJECT, CONTESTED_CATEGORY})

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"


class RivalRefused(ValueError):
    """A competitive claim that cannot be made."""


@dataclasses.dataclass(frozen=True)
class Rival:
    """One alternative to buying from this company.

    Eight fields are required by §2 and the constructor enforces the two that
    were routinely missing. A row without a MECHANISM is a logo on a slide: it
    tells a reader to worry without telling them how the harm arrives. A row
    without a DISPROOF cannot be wrong, and a competitive claim that cannot be
    wrong is not intelligence, it is atmosphere.
    """
    identity: str
    kind: str
    rung: str
    #: How this takes the decision away. Required.
    mechanism: str
    #: The span that supports it, quoted. Empty only above the attributed
    #: rungs is not allowed -- an attributed rung must quote.
    evidence: str = ""
    #: Who said it, and whether they are independent of the subject.
    independence: str = ""
    confidence: str = CONFIDENCE_MEDIUM
    #: Why a chief executive should care -- the decision it bears on.
    why_it_matters: str = ""
    #: What would show this is not a real alternative. Required.
    disproof: str = ""
    #: Level-k, filled by the reaction model.
    likely_response: str = ""
    counter_move: str = ""
    signal_to_watch: str = ""
    response_likelihood: str = ""
    level: str = "L1"

    def __post_init__(self):
        if not (self.identity or "").strip():
            raise RivalRefused("a rival must have an identity")
        if self.rung not in RUNGS:
            raise RivalRefused(f"unknown rung {self.rung!r}")
        if self.kind not in KINDS:
            raise RivalRefused(f"unknown kind {self.kind!r}")
        if not (self.mechanism or "").strip():
            raise RivalRefused(
                f"{self.identity}: a rival with no mechanism is a name on a "
                f"slide")
        if not (self.disproof or "").strip():
            raise RivalRefused(
                f"{self.identity}: a rival that cannot be wrong is not a "
                f"claim")
        if self.rung in ATTRIBUTED and not (self.evidence or "").strip():
            raise RivalRefused(
                f"{self.identity}: rung {self.rung} asserts an attribution, "
                f"so it must quote the span that carries it")

    @property
    def rung_label(self) -> str:
        return RUNG_LABEL.get(self.rung, self.rung)

    @property
    def kind_label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    @property
    def is_attributed(self) -> bool:
        return self.rung in ATTRIBUTED

    @property
    def from_subject_words(self) -> bool:
        return self.rung in FROM_SUBJECT_WORDS

    @property
    def is_a_firm(self) -> bool:
        """Is the identity a company, or a class of alternative?

        A surface must not write "Point solution vendors announced" — the
        identity is a category and cannot take a verb of agency.
        """
        return self.rung in (NAMED_BY_SUBJECT, NAMED_BY_CUSTOMER,
                             NAMED_BY_RIVAL, NAMED_BY_ANALYST,
                             STRUCTURAL_PEER)

    def as_dict(self) -> dict:
        row = dataclasses.asdict(self)
        row["rung_label"] = self.rung_label
        row["kind_label"] = self.kind_label
        row["rung_number"] = RUNG_NUMBER.get(self.rung, 99)
        return row


@dataclasses.dataclass(frozen=True)
class CompetitiveGround:
    """Everything that could take this customer's decision away, and how it
    was established. One per run; every competitive surface projects from it.
    """
    company: str
    rivals: Tuple[Rival, ...] = ()
    #: The measurement that would move the weakest rung up, when the ladder
    #: bottomed out. Required when `best_rung` is UNRESOLVED or STRUCTURAL_PEER.
    next_measurement: str = ""
    #: What the run read, so the reader can judge the ladder's ceiling.
    basis_note: str = ""

    @property
    def best_rung(self) -> str:
        if not self.rivals:
            return UNRESOLVED
        return min((r.rung for r in self.rivals),
                   key=lambda r: RUNG_NUMBER.get(r, 99))

    @property
    def subject_grounded(self) -> Tuple[Rival, ...]:
        """Rivals resting on the company's own words -- named firms and the
        categories it says it contests. This is the set that makes a
        competitive read about THIS company."""
        return tuple(r for r in self.rivals if r.from_subject_words)

    @property
    def kinds_covered(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(r.kind for r in self.rivals))

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "company": self.company,
                "best_rung": self.best_rung,
                "next_measurement": self.next_measurement,
                "basis_note": self.basis_note,
                "rivals": [r.as_dict() for r in self.rivals]}


# ---------------------------------------------------------------------------
# Extraction: the contested categories a filing actually names.
# ---------------------------------------------------------------------------

#: How a filing introduces the ground it contests. Every one of these was read
#: off a real Competition section. The bullet forms matter more than the prose
#: forms: a 10-K enumerates its competitive categories as a list far more often
#: than it writes them into a sentence.
_CONTEST_LEAD = (
    r"we\s+compete\s+(?:primarily\s+)?(?:with|against)",
    r"we\s+compete\s+in\s+the\s+markets?\s+for",
    r"our\s+competitors?\s+includes?",
    r"competitors?\s+includes?",
    r"we\s+face\s+competition\s+from",
    r"competition\s+(?:comes|arises)\s+from",
    r"our\s+principal\s+competitors?\s+(?:are|include)",
    r"we\s+compete\s+across",
    r"our\s+competitive\s+arena\s+encompasses",
)

#: A category is a plural noun phrase describing a KIND of supplier. These
#: heads are what make it one. "Vendors", "providers", "firms" -- the words a
#: filing uses precisely because it is declining to name anybody.
_CATEGORY_HEAD = (
    "vendors", "providers", "suppliers", "firms", "companies", "competitors",
    "players", "entrants", "platforms", "solutions", "offerings", "systems",
    "manufacturers", "operators", "institutions", "banks", "insurers",
    "distributors", "retailers", "integrators", "consultancies", "agencies",
    "networks", "services", "products", "tools", "brands", "labels",
    "generics", "biosimilars", "startups", "incumbents", "specialists",
    # Bank of America's competition section is fifteen categories and not one
    # company name, and half of them are single words. Refusing single-word
    # categories threw away the most company-specific competitive statement
    # in the whole golden set.
    "thrifts", "unions", "issuers", "funds", "dealers", "brokers", "lenders",
    "carriers", "processors", "wholesalers", "marketplaces", "exchanges",
    "hospitals", "clinics", "pharmacies", "contractors", "miners",
    "refiners", "utilities", "publishers", "aggregators", "resellers",
)

#: Heads that carry no information on their own. "Vendors" is a category only
#: when something in front of it says WHICH vendors; "banks" is a category by
#: itself. A bare contentless head is what a fragment looks like.
_CONTENTLESS_ALONE = frozenset({
    "vendors", "providers", "suppliers", "firms", "companies", "competitors",
    "players", "entrants", "platforms", "solutions", "offerings", "systems",
    "services", "products", "tools", "networks", "operators", "specialists",
    "incumbents", "startups", "brands",
})

#: A candidate that starts with one of these is a fragment of a list, not the
#: head of a noun phrase. "and reliability services" reached the Cloudflare
#: table this way, out of "...to provide security, performance, and
#: reliability services" -- a sentence about what Cloudflare sells.
_FRAGMENT_LEAD = frozenset({
    "and", "or", "but", "nor", "with", "to", "for", "in", "of", "by", "as",
    "from", "on", "at", "than", "including", "include", "includes", "such",
    "well", "also", "into", "through", "across", "against", "about", "over",
    "under", "between", "among", "while", "whereas", "because", "since",
})

#: A clause marker inside a candidate means the split caught a sentence.
_CLAUSE_MARKER = re.compile(
    r"\b(?:to|that|which|who|whose|where|when|whether|if|would|will|may|"
    r"can|could|should|must|have|has|had|are|is|was|were|been|being)\b",
    re.I)

#: Bullet markers a filing uses to enumerate competitive categories.
_BULLET = re.compile(r"(?:^|\s)[•·●▪◦\-•]\s*")

#: A SECOND ENUMERATION LIVES INSIDE THE FIRST. Cloudflare's "Point solution
#: vendors" bullet continues "...in various categories including application
#: and network security vendors, content delivery network (CDN) vendors,
#: domain name system (DNS) services vendors, email security vendors, and
#: SD-WAN vendors" -- five more categories, each one precisely Cloudflare's
#: market, all discarded because only the head of the bullet was read.
#:
#: These leads fire ONLY inside a block already reached from a competition
#: lead-in, so "including" is not being mined out of the whole filing.
_INBLOCK_LEAD = (
    r"categories\s+including", r"such\s+as", r"including",
    r"consist(?:s|ing)?\s+of", r"range\s+from",
)

#: Sentence-ish split that survives "Inc." and "U.S."
_ABBREV = r"(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bCo)(?<!\bplc)(?<!\bLLC)" \
          r"(?<!\bSt)(?<!\bNo)(?<!\bU\.S)"
_SPLIT = re.compile(rf"{_ABBREV}(?<=[.;])\s+(?=[A-Z])")

#: Phrases that mark the alternative as something other than a vendor. Order
#: matters: the first match wins, and the more specific patterns come first.
_KIND_CUES = (
    (BUILD_IN_HOUSE, (r"in[-\s]house", r"internally\s+develop",
                      r"build\s+(?:it\s+|their\s+own\s+)?themselves",
                      r"their\s+own\s+(?:engineering|development|IT)",
                      r"develop\s+their\s+own", r"self[-\s]develop",
                      r"internal\s+(?:teams?|development|solutions?)")),
    (OPEN_SOURCE, (r"open[-\s]source", r"freely\s+available",
                   r"community[-\s](?:developed|maintained)")),
    (MANUAL_WORKFLOW, (r"manual\s+(?:process|workflow|method)",
                       r"spreadsheets?", r"paper[-\s]based",
                       r"legacy\s+process", r"traditional\s+methods?")),
    (REGULATORY, (r"generic\s+(?:drug|version|equivalent)", r"biosimilar",
                  r"government[-\s](?:provided|sponsored|run)",
                  r"state[-\s](?:owned|sponsored)", r"public\s+option",
                  r"mandated\s+alternative")),
    (AI_REPLACEMENT, (r"artificial\s+intelligence", r"machine\s+learning",
                      r"automat(?:ion|ed)\s+(?:tools?|solutions?|systems?)",
                      r"generative\s+AI")),
    (PLATFORM_BUNDLE, (r"bundl(?:e|ed|ing)", r"suites?\s+of\s+products",
                       r"integrated\s+suite", r"platform\s+providers?",
                       r"hyperscalers?", r"public\s+cloud\s+(?:vendors?|"
                       r"providers?)", r"standardi[sz]e\s+on")),
    (CHANNEL_SHIFT, (r"direct[-\s]to[-\s]consumer", r"disintermediat",
                     r"bypass(?:ing)?\s+(?:the\s+)?(?:channel|distributor)",
                     r"marketplaces?")),
    (ADJACENT, (r"adjacent", r"point\s+solutions?", r"single\s+use\s+case",
                r"niche\s+(?:vendors?|providers?)")),
    (SUBSTITUTE, (r"substitute", r"alternative\s+(?:approach|technolog)",
                  r"other\s+means\s+of")),
)

#: Words that make a captured span a clause rather than a category.
_NOT_A_CATEGORY = frozenset({
    "we", "our", "us", "they", "their", "it", "its", "this", "that", "these",
    "those", "there", "which", "who", "whom", "whose", "what", "when",
    "where", "however", "additionally", "further", "moreover", "although",
    "the company", "the following", "certain", "many", "some", "other",
    "others", "such", "each", "both", "either", "neither", "any", "all",
})

#: Maximum words in a category phrase. Longer spans are sentences that
#: happened to begin after a bullet.
_MAX_CATEGORY_WORDS = 7


def _sentences(text: str) -> Tuple[str, ...]:
    return tuple(s.strip() for s in _SPLIT.split(text or "") if s.strip())


def _clean_phrase(raw: str) -> str:
    phrase = re.sub(r"\s+", " ", (raw or "")).strip(" ,.;:—–-••·●▪◦")
    # A category introduced by an article reads badly in a table row.
    phrase = re.sub(r"^(?:the|a|an|other|certain|various|several|many)\s+", "",
                    phrase, flags=re.I).strip()
    return phrase


def _is_category(phrase: str) -> bool:
    """A plural noun phrase whose head names a KIND of supplier."""
    if not phrase:
        return False
    words = phrase.split()
    if not (0 < len(words) <= _MAX_CATEGORY_WORDS):
        return False
    lowered = phrase.lower()
    if lowered in _NOT_A_CATEGORY or words[0].lower() in _NOT_A_CATEGORY:
        return False
    if words[0].lower() in _FRAGMENT_LEAD:
        return False
    # A clause marker means the list split caught part of a sentence rather
    # than a noun phrase.
    if _CLAUSE_MARKER.search(phrase):
        return False
    # The head noun -- last word -- decides. "On-premises network hardware
    # vendors" is a category; "on-premises network hardware" is a product.
    head = words[-1].lower().strip(",.;:")
    if head not in _CATEGORY_HEAD:
        return False
    # One word, and that word is a bare head, is a fragment: "vendors" alone
    # names nobody. "Banks" alone names a market.
    if len(words) == 1 and head in _CONTENTLESS_ALONE:
        return False
    return True


def _kind_of(phrase: str, sentence: str = "") -> str:
    """What kind of alternative this is.

    THE PHRASE DECIDES FIRST. Reading the whole sentence made "Point solution
    vendors" a platform bundle, because the same sentence mentioned public
    cloud vendors two clauses later. A category's own words are what classify
    it; the sentence is only consulted when the category itself is silent.
    """
    for source in (phrase, sentence):
        lowered = (source or "").lower()
        if not lowered:
            continue
        for kind, patterns in _KIND_CUES:
            for pattern in patterns:
                if re.search(pattern, lowered):
                    return kind
    return DIRECT


def contested_categories(text: str, *, limit: int = 6) -> Tuple[dict, ...]:
    """The classes of rival a company names in its own competition passage.

    This is the extractor the previous cycle did not build because it was
    looking for company names. What it returns is a category, the sentence
    that carried it, and the kind of alternative the surrounding language
    makes it -- never a firm, and never a firm invented to represent a class.
    """
    if not text:
        return ()
    out, seen = [], set()
    sentences = _sentences(text)
    for position, sentence in enumerate(sentences):
        lowered = sentence.lower()
        if not any(re.search(lead, lowered) for lead in _CONTEST_LEAD):
            continue
        # A BULLETED ENUMERATION SPANS SENTENCES. Each bullet in a real filing
        # ends with a full stop, so the sentence splitter puts every category
        # after the first into its own fragment with no lead-in of its own.
        # Scanning only the lead-in sentence found one of Cloudflare's three
        # categories and silently dropped the other two.
        block = [sentence]
        for following in sentences[position + 1:position + 12]:
            if not _BULLET.search(" " + following):
                break
            block.append(following)

        candidates = []
        for part_of_block in block:
            chunks = [c for c in _BULLET.split(part_of_block) if c.strip()]
            if len(chunks) > 1 or _BULLET.search(" " + part_of_block):
                for chunk in chunks[1:] if len(chunks) > 1 else chunks:
                    # The category is the head of the bullet, up to the first
                    # separator that starts its description.
                    head = re.split(r"[,.;:—–]|\s-\s|\s+which\s+|\s+that\s+",
                                    chunk, maxsplit=1)[0]
                    candidates.append(head)
            # The bullet's own tail often enumerates the sub-categories that
            # are the real market. Mine it with the same category test.
            for inner in _INBLOCK_LEAD:
                inner_match = re.search(inner, part_of_block, re.I)
                if not inner_match:
                    continue
                inner_tail = part_of_block[inner_match.end():]
                inner_tail = re.split(r"[.;]", inner_tail, maxsplit=1)[0]
                for part in re.split(r",\s*|\s+and\s+|\s+or\s+", inner_tail):
                    candidates.append(part)
                break
        for lead in _CONTEST_LEAD:
            match = re.search(lead, lowered)
            if not match:
                continue
            tail = sentence[match.end():]
            for part in re.split(r",\s*|\s+and\s+|\s+or\s+", tail):
                candidates.append(re.split(r"[.;:—–]", part, maxsplit=1)[0])
        for candidate in candidates:
            phrase = _clean_phrase(candidate)
            if not _is_category(phrase) or phrase.lower() in seen:
                continue
            seen.add(phrase.lower())
            out.append({"category": phrase,
                        "evidence": sentence.strip()[:400],
                        "kind": _kind_of(phrase, sentence),
                        "at": text.find(phrase)})
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    # THE FILING'S OWN ORDER IS THE COMPANY'S RANKING. Mining the parenthetical
    # "including merchant banks and..." before the main list put Bank of
    # America's two weakest categories at the head of its table and left
    # "banks" and "thrifts" off it.
    out.sort(key=lambda row: row["at"] if row["at"] >= 0 else 10 ** 9)
    return tuple(out)


# ---------------------------------------------------------------------------
# Extraction: the alternative a customer actually left behind.
# ---------------------------------------------------------------------------

#: A MIGRATION SENTENCE NAMES THE INCUMBENT. A Competition section declines to
#: name anybody; a customer story cannot avoid it, because the whole point of
#: the story is what the customer stopped using. Shopify's 10-K names no
#: rival at all, and its own site says a merchant "migrated from Magento to
#: Shopify in under three months" -- which is Magento, named, dated, with the
#: switching cost attached.
#:
#: The subject must be the DESTINATION. "Migrated from Shopify to X" is the
#: same grammar pointing the other way and would file the subject's customers'
#: departures as the subject's wins.
_MIGRATION = (
    r"migrat(?:ed|ing|es|e)\s+(?:away\s+)?from\s+(?P<from>[^,.;]{2,60}?)\s+to\s+"
    r"(?P<to>[A-Z][\w&.\- ]{1,40})",
    r"switch(?:ed|ing|es)\s+from\s+(?P<from>[^,.;]{2,60}?)\s+to\s+"
    r"(?P<to>[A-Z][\w&.\- ]{1,40})",
    r"mov(?:ed|ing|es)\s+(?:off|away\s+from)\s+(?P<from>[^,.;]{2,60}?)\s+to\s+"
    r"(?P<to>[A-Z][\w&.\- ]{1,40})",
    r"replac(?:ed|ing|es)\s+(?P<from>[^,.;]{2,60}?)\s+with\s+"
    r"(?P<to>[A-Z][\w&.\- ]{1,40})",
)

#: What the customer left behind, when it is not a product. These are the
#: rungs a vendor-shaped extractor can never reach, and they are frequently
#: the real alternative: nobody is paid to defend a spreadsheet.
_LEFT_BEHIND = (
    (MANUAL_WORKFLOW, WORKFLOW_SUBSTITUTE,
     (r"spreadsheets?", r"manual\s+(?:process|processes|workflow|entry|"
      r"tracking|reconciliation)", r"paper[-\s]based", r"pen\s+and\s+paper",
      r"email\s+threads?", r"whiteboards?")),
    (BUILD_IN_HOUSE, INTERNAL_BUILD,
     (r"in[-\s]house\s+(?:system|tool|build|development|team|solution)",
      r"home[-\s]?grown", r"custom[-\s]built", r"bespoke\s+system",
      r"internal\s+tool")),
    (DO_NOTHING, WORKFLOW_SUBSTITUTE,
     (r"do(?:ing)?\s+nothing", r"no\s+solution\s+at\s+all",
      r"had\s+no\s+(?:system|process|tool)")),
    (OPEN_SOURCE, DISPLACEMENT,
     (r"open[-\s]source", r"self[-\s]hosted")),
)

#: A migration source that is a category rather than a firm still counts --
#: it just lands on a different rung. These heads say "not a company".
_LEFT_BEHIND_GENERIC = frozenset({
    "our", "their", "the", "a", "an", "it", "this", "that", "them",
    "legacy", "previous", "old", "former", "existing",
})


def migrations(text: str, subject: str, *, limit: int = 6) -> Tuple[dict, ...]:
    """What customers of this company stopped using, in the company's words.

    Returns the incumbent, the sentence, and whether the incumbent is a firm
    or a way of working. Never returns the subject itself, and never fires on
    a sentence whose destination is somebody else.
    """
    if not text or not subject:
        return ()
    subject_words = {w for w in re.split(r"\W+", subject.lower()) if len(w) > 2}
    out, seen = [], set()
    for sentence in _sentences(text):
        for pattern in _MIGRATION:
            for match in re.finditer(pattern, sentence, re.I):
                destination = (match.group("to") or "").strip()
                dest_words = {w for w in re.split(r"\W+", destination.lower())
                              if len(w) > 2}
                # The subject must be where the customer WENT.
                if not (dest_words & subject_words):
                    continue
                left = _clean_phrase(match.group("from") or "")
                if not left or left.lower() in seen:
                    continue
                low = left.lower()
                if {w for w in re.split(r"\W+", low) if len(w) > 2} \
                        & subject_words:
                    continue
                kind, rung = DIRECT, NAMED_BY_CUSTOMER
                for candidate_kind, candidate_rung, patterns in _LEFT_BEHIND:
                    if any(re.search(p, low) for p in patterns):
                        kind, rung = candidate_kind, candidate_rung
                        break
                else:
                    # NOT EVERY "REPLACED X WITH US" NAMES A COMPETITOR. The
                    # same grammar carries marketing prose: "replaced
                    # traditional fashion markups with Shopify" reached the
                    # table as a named rival. A rung-2 row claims a customer
                    # named an incumbent, so the incumbent has to look like
                    # one -- a proper noun, not a lower-case noun phrase.
                    words = left.split()
                    head = words[0].lower() if words else ""
                    if head in _LEFT_BEHIND_GENERIC and len(words) < 3:
                        continue
                    if not re.match(r"^[A-Z][A-Za-z0-9&.\-]*$", words[0] or ""):
                        continue
                    if len(words) > 4:
                        continue
                    if any(w.lower() in _NOT_A_CATEGORY for w in words):
                        continue
                seen.add(low)
                out.append({"left_behind": left, "kind": kind, "rung": rung,
                            "evidence": sentence.strip()[:400]})
                if len(out) >= limit:
                    return tuple(out)
    return tuple(out)


def subject_text(documents: Sequence[dict]) -> str:
    """Everything the subject published about itself, joined.

    The migration extractor works on customer stories and case studies, which
    live on the company's own site rather than in a filing, so it needs the
    whole own-published body rather than the competition passages.
    """
    from intent_engine.external_intel.competitor_finder import _document_text
    return " ".join(
        _document_text(d) for d in documents or ()
        if str((d or {}).get("source_class") or "")
        in ("investor_material", "executive_statement", "company_owned"))


def competition_text(documents: Sequence[dict], subject: str) -> str:
    """The subject's OWN competition passages, and nobody else's.

    A run legitimately holds third-party filings that merely mention the
    subject, and their Competition sections describe THEIR market. Reading
    those produced "Online Platforms" as one of Cloudflare's competitors --
    a category out of a sentiment-trading company's 10-K. The discriminator
    is the source class the ingestion already assigns: the subject's own
    filings are `investor_material` or `executive_statement`, a third party's
    is `competitor`.
    """
    from intent_engine.external_intel.competitor_finder import (
        competition_passages, _document_text)
    own = []
    for document in documents or ():
        source_class = str((document or {}).get("source_class") or "")
        if source_class not in ("investor_material", "executive_statement",
                                "company_owned"):
            continue
        text = _document_text(document)
        if not text:
            continue
        own.extend(competition_passages(text))
    return " ".join(own)


# ---------------------------------------------------------------------------
# Extraction: a named threat to a named product.
# ---------------------------------------------------------------------------

#: A FILING MAY NAME NO COMPETITOR AND STILL NAME THE THREAT EXACTLY.
#:
#: Johnson & Johnson's Competition section, retrieved in full, reads: "In all
#: of their product lines, the Company's subsidiaries compete with companies
#: both locally and globally." No firm, no category, nothing a reader could
#: act on -- and the extractor was right to return nothing from it.
#:
#: Two paragraphs earlier the same filing says: "Third parties have filed
#: biologics license applications ... seeking approval to market biosimilar
#: versions of STELARA around the globe. The Company expects continued
#: launches of biosimilar versions of STELARA globally which will continue to
#: negatively impact the Company's sales of STELARA."
#:
#: That is dated, specific, quantified elsewhere in the same document, and it
#: is the single most important competitive fact about the company. It was
#: invisible because the extractor was looking for WHO and the filing had
#: answered WHAT, TO WHAT.
#:
#: The shape generalises past pharmaceuticals: a contract up for rebid, a
#: licence expiring, a patent running out, a rate case. What they share is a
#: named asset of the subject's, and a dated event that removes its
#: protection.
_THREAT = (
    (REGULATORY,
     r"biosimilar\s+versions?\s+of\s+(?P<asset>[A-Z][A-Za-z0-9®™\-]{2,30})",
     "biosimilar competition to {asset}"),
    (REGULATORY,
     r"generic\s+versions?\s+of\s+(?P<asset>[A-Z][A-Za-z0-9®™\-]{2,30})",
     "generic competition to {asset}"),
    (REGULATORY,
     r"loss\s+of\s+(?:market\s+)?exclusivity\s+(?:for|of)\s+"
     r"(?P<asset>[A-Z][A-Za-z0-9®™\-]{2,30})",
     "loss of exclusivity on {asset}"),
    (REGULATORY,
     r"(?P<asset>[A-Z][A-Za-z0-9®™\-]{2,30})\s+(?:will\s+)?los[et]s?\s+"
     r"(?:market\s+)?exclusivity",
     "loss of exclusivity on {asset}"),
    (SUBSTITUTE,
     r"expiration\s+of\s+(?:the\s+)?(?:patent|patents)\s+(?:for|on)\s+"
     r"(?P<asset>[A-Z][A-Za-z0-9®™\-]{2,30})",
     "patent expiry on {asset}"),
    (CHANNEL_SHIFT,
     r"(?P<asset>[A-Z][A-Za-z0-9®™\-]{2,30})\s+contract\s+(?:is\s+)?"
     r"(?:up\s+for\s+)?(?:re)?bid",
     "rebid of the {asset} contract"),
)

#: A capitalised token that is not a product. Filings are full of them.
_NOT_AN_ASSET = frozenset({
    "the", "company", "companies", "third", "parties", "u.s", "us", "fda",
    "european", "medicines", "agency", "sec", "form", "item", "part", "note",
    "december", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "annual", "report",
    "competition", "trademarks", "seasonality", "products", "product",
})


def named_threats(text: str, subject: str, *, limit: int = 4) -> Tuple[dict, ...]:
    """Dated, specific competitive threats the subject names against itself.

    Rung 1 material: the subject said it, under obligation to be accurate,
    about a named asset of its own.
    """
    if not text:
        return ()
    out, seen = [], set()
    for sentence in _sentences(text):
        for kind, pattern, template in _THREAT:
            for match in re.finditer(pattern, sentence):
                asset = (match.group("asset") or "").strip(" .,;:")
                if not asset or asset.lower() in _NOT_AN_ASSET:
                    continue
                # The asset must be the subject's own, not a rival's. A
                # filing naming a competitor's patent expiry is telling us
                # about their market, not ours.
                identity = template.format(asset=asset)
                if identity.lower() in seen:
                    continue
                seen.add(identity.lower())
                out.append({"identity": identity, "kind": kind,
                            "evidence": sentence.strip()[:400],
                            "asset": asset})
                if len(out) >= limit:
                    return tuple(out)
    return tuple(out)

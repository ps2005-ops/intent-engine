"""Find competitors in what the run already retrieved.

WHERE THE NAMES COME FROM
--------------------------
Lawful, already-fetched sources: the company's own periodic filing, competitor
pages the run retrieved, and independent reporting. A filing's Competition
section is the best of these by some distance -- it names rivals in the
company's own words, with overlap language attached, and it is signed. Since
the periodic report started arriving in every listed company's run, it is
present far more often than a competitor's marketing page ever was.

Nothing here scrapes a review site, works around a bot control, or reads a
source the run did not already have. This is extraction from retrieved
evidence, not acquisition.

HOW A NAME IS FOUND WITHOUT A COMPANY LIST
-------------------------------------------
Capitalised multi-word spans inside a passage that is already about
competition, minus a stoplist of the things that look like company names in
filings and are not: section headings, standard legal phrases, month names,
place names, and the subject's own name. This is deliberately narrow. It
misses lower-cased brands and one-word names that collide with ordinary
vocabulary, and a missed competitor is a quiet omission -- while a fabricated
one is a founder told to worry about a company that is not in their market.

Every candidate then goes through `competitor_contract.assess`, which is where
compensation peer groups and bare mentions are thrown out.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence

from .competitor_contract import (
    ADJACENT_SUBSTITUTE, BARE_MENTION, CLAIM_RELEVANT, COMPETITIVE_CONTEXT,
    CONSULTING_ALTERNATIVE, DIRECT_COMPETITOR, INTERNAL_BUILD,
    PARTNER_AND_COMPETITOR, PLATFORM_ALTERNATIVE, Competitor,
    CompetitorRejected, Mention, assess,
)

#: Where a competition discussion starts in a filing.
_COMPETITION_CUES = (
    "competition", "competitive landscape", "competitive environment",
    "we compete", "our competitors", "principal competitors",
    "highly competitive", "competitors include",
)

#: Looks like a company name, is not one. Every entry was seen producing a
#: false competitor while calibrating against real filings.
_STOPLIST = {
    "the company", "our company", "the united states", "united states",
    "annual report", "form 10-k", "form 10-q", "risk factors",
    "item 1a", "item 1", "item 7", "part i", "part ii",
    "securities and exchange commission", "sec", "gaap", "non-gaap",
    "european union", "north america", "latin america", "asia pacific",
    "middle east", "board of directors", "chief executive officer",
    "management discussion", "table of contents", "common stock",
    "class a", "class b", "new york", "san francisco", "silicon valley",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "we", "our", "us", "the", "however", "additionally", "further",
    "in addition", "for example", "as a result", "these companies",
    "such companies", "certain", "many", "some", "other", "others",
}

#: Ordinary words that appear capitalised at the start of a filing sentence.
#: A span containing one of these is a clause, not a name.
_CLAUSE_WORDS = {
    "certain", "government", "customers", "some", "many", "other", "others",
    "these", "those", "such", "our", "their", "we", "they", "this", "that",
    "additionally", "however", "further", "moreover", "although", "while",
    "because", "when", "where", "which", "who", "including", "include",
    "includes", "may", "must", "will", "would", "could", "should", "can",
    "revenue", "customers", "products", "services", "solutions", "market",
    "markets", "business", "companies", "vendors", "providers", "firms",
}

#: Suffixes that confirm a span is an organisation rather than a phrase.
_CORPORATE = ("inc", "inc.", "corp", "corp.", "corporation", "company",
              "co.", "ltd", "ltd.", "llc", "plc", "sa", "ag", "nv",
              "technologies", "systems", "software", "labs", "group",
              "holdings", "solutions", "networks", "platforms")

_NAME = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,3})\b")

#: Words that place the alternative outside the "another vendor" frame.
_RELATIONSHIP_CUES = (
    (INTERNAL_BUILD, (r"in[- ]house", r"internally\s+develop",
                      r"build\s+(?:it\s+)?themselves", r"own\s+engineering")),
    (CONSULTING_ALTERNATIVE, (r"consult(?:ing|ants?)", r"system\s+integrator",
                              r"professional\s+services\s+firms?",
                              r"systems\s+integrators?")),
    (PARTNER_AND_COMPETITOR, (r"both\s+a\s+partner", r"partner\s+and\s+"
                              r"compet", r"also\s+(?:our\s+)?partners?")),
    (PLATFORM_ALTERNATIVE, (r"platform", r"suite", r"standardi[sz]e")),
    (ADJACENT_SUBSTITUTE, (r"substitute", r"adjacent",
                           r"alternative\s+approach")),
)


#: Abbreviations whose full stop does NOT end a sentence. Splitting naively on
#: "." turned "We compete with Databricks Inc. and Snowflake Inc." into three
#: fragments, so the overlap quote shown to a reader was "and Snowflake Inc." --
#: a citation that proves nothing to the person checking it.
_ABBREV = r"(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bCo)(?<!\bplc)(?<!\bLLC)" \
          r"(?<!\bSt)(?<!\bNo)(?<!\bU\.S)"

_SPLIT = re.compile(rf"{_ABBREV}(?<=[.;])\s+(?=[A-Z])")


def _document_text(document: dict) -> str:
    """Every field a retrieved document or an observation may hold its body in.

    `text_content` is the ingestion store's field name; `text` is an
    observation's. Reading only the second made every filing body invisible --
    live on the preview, Palantir's 10-Q Competition section was retrieved and
    stored and never searched, so the competitive passage reported that no
    competitor account had been read while the company's own list of rivals
    sat in the run.
    """
    return " ".join(str(document.get(f) or "")
                    for f in ("text", "text_content", "quote", "summary"))


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SPLIT.split(text or "") if s.strip()]


def competition_passages(text: str, *, window: int = 3) -> List[str]:
    """Sentences that are actually about competition, with their neighbours.

    Restricting extraction to these is what stops the whole filing being mined
    for capitalised words.
    """
    sentences = _sentences(text)
    keep, out = set(), []
    for i, sentence in enumerate(sentences):
        lowered = sentence.lower()
        if any(cue in lowered for cue in _COMPETITION_CUES):
            for j in range(max(0, i), min(len(sentences), i + window)):
                keep.add(j)
    run: List[str] = []
    for i, sentence in enumerate(sentences):
        if i in keep:
            run.append(sentence)
        elif run:
            out.append(" ".join(run))
            run = []
    if run:
        out.append(" ".join(run))
    return out


def candidate_names(passage: str, *, subject: str = "") -> List[str]:
    """Capitalised spans that plausibly name an organisation."""
    subject_words = {w.lower() for w in re.split(r"\W+", subject or "") if w}
    found: List[str] = []
    for raw in _NAME.findall(passage or ""):
        name = raw.strip(" .,;:")
        lowered = name.lower()
        if len(name) < 3 or lowered in _STOPLIST:
            continue
        # The subject is not its own competitor.
        if subject and (lowered in (subject or "").lower()
                        or lowered in subject_words):
            continue
        words = lowered.split()
        if len(words) == 1:
            # A single capitalised word is usually a sentence opener. Keep it
            # only when it is unambiguously a brand: mixed case inside the
            # word, a digit, or an ampersand.
            if not re.search(r"[a-z][A-Z]|[0-9&]", name):
                continue
        elif not any(w.strip(".") in _CORPORATE for w in words):
            # A multi-word span with no corporate suffix has to look like a
            # name rather than a clause: every word capitalised and none of
            # them ordinary vocabulary. This is what lets "Booz Allen
            # Hamilton" through while keeping "Certain Government Customers"
            # out.
            if len(words) > 3:
                continue
            if any(w in _CLAUSE_WORDS for w in words):
                continue
        if any(w in _STOPLIST for w in words[:1]):
            continue
        found.append(name)
    return list(dict.fromkeys(found))


def _relationship(sentence: str) -> str:
    """Read from the SENTENCE naming this competitor, not the whole passage.

    Reading the passage made every competitor in a Competition section inherit
    the same relationship: one sentence mentioning in-house building turned
    Databricks, Snowflake and a consulting firm all into INTERNAL_BUILD. The
    relationship is a claim about one alternative, so it has to come from the
    text about that alternative.
    """
    for relationship, patterns in _RELATIONSHIP_CUES:
        for pattern in patterns:
            if re.search(pattern, sentence, re.I):
                return relationship
    return DIRECT_COMPETITOR


def _overlap_sentence(passage: str, name: str) -> str:
    """The sentence that actually makes the claim, so a reader can check it."""
    for sentence in _sentences(passage):
        if name.lower() in sentence.lower():
            return sentence.strip()
    return ""


def find_competitors(documents, *, subject: str = "", today: str = "",
                     limit: int = 5) -> List[Competitor]:
    """Competitors this run's own evidence supports, best first.

    `documents` are mappings with `text`, `observation_id`, `source_title`,
    `source_class` and `date` — the shape the ingestion store already emits.
    """
    ranked: Dict[str, Competitor] = {}
    for document in documents or ():
        if not isinstance(document, dict):
            continue
        text = _document_text(document)
        evidence_id = document.get("observation_id") or document.get(
            "source_id") or document.get("document_id") or ""
        if not text or not evidence_id:
            continue
        for passage in competition_passages(text):
            for name in candidate_names(passage, subject=subject):
                mention = Mention(
                    name=name, passage=passage,
                    source_title=str(document.get("source_title") or ""),
                    source_class=str(document.get("source_class") or ""),
                    evidence_id=str(evidence_id),
                    date=str(document.get("date") or ""))
                verdict = assess(mention, today=today)
                if verdict.relevance in (BARE_MENTION, "IRRELEVANT", "STALE"):
                    continue
                overlap = _overlap_sentence(passage, name)
                if not overlap:
                    continue
                relationship = _relationship(overlap)
                existing = ranked.get(name.lower())
                if existing and existing.relevance == CLAIM_RELEVANT \
                        and verdict.relevance != CLAIM_RELEVANT:
                    continue
                try:
                    ranked[name.lower()] = Competitor(
                        name=name, relationship=relationship,
                        overlap=overlap[:400],
                        evidence_ids=(str(evidence_id),),
                        source_titles=(str(document.get("source_title")
                                           or ""),),
                        relevance=verdict.relevance, reason=verdict.reason,
                        matched_on=verdict.matched_on,
                        date=str(document.get("date") or ""),
                        decision_implication=_implication(
                            relationship),
                        limitation=(
                            "Taken from this company's own account of its "
                            "market, so it reflects who it says it competes "
                            "with rather than an independent assessment."
                            if str(document.get("source_class") or "")
                            in ("company_owned", "regulatory_filing",
                                "filing")
                            else "Based on a single retrieved source."))
                except CompetitorRejected:
                    continue
    internal = _internal_build(documents, today=today)
    if internal is not None:
        ranked.setdefault("__internal_build__", internal)
    out = sorted(ranked.values(),
                 key=lambda c: (c.relevance != CLAIM_RELEVANT, c.name))
    return out[:limit]


def category_alternatives(documents, *, limit: int = 8) -> List[dict]:
    """Classes of substitute a filing names WITHOUT naming any company.

    A name-based finder is blind to these and reports the honest-looking but
    misleading "no competitor was named". Measured on Shopify's 2026 10-K:
    its Competition section names no company at all, and instead lists what a
    merchant might choose instead — "ecommerce software vendors; content
    management systems; payment processors; point of sale providers;
    marketplaces". That is a real competitive statement, and to a founder it
    is arguably more useful than a name, because it describes the SHAPE of
    the alternative rather than one instance of it.

    Returned separately from `find_competitors` rather than folded in: these
    are categories, not companies, and presenting them in the same list would
    let "payment processors" read as a named rival.
    """
    out: List[dict] = []
    seen = set()
    for document in documents or ():
        if not isinstance(document, dict):
            continue
        text = _document_text(document)
        evidence_id = document.get("observation_id") or document.get(
            "source_id") or document.get("document_id") or ""
        if not text or not evidence_id:
            continue
        for passage in competition_passages(text):
            trigger = re.search(
                r"(?:select|choose|use|turn to|opt for)\s+(?:one or more\s+)?"
                r"(?:integrated or standalone\s+)?(?:offerings?|solutions?|"
                r"products?|providers?)?\s*from\s+other\s+providers?"
                r"|alternatives?\s+(?:to\s+\w+\s+)?includ\w*"
                r"|competitors?\s+includ\w*", passage, re.I)
            if not trigger:
                continue
            # Bound the enumeration to the sentence that introduces it.
            # Running past it captured "platform capabilities and product
            # functionality" from Palantir's filing — a competitive FACTOR
            # from the next sentence, offered to a founder as though it were
            # something a buyer could purchase instead.
            tail = passage[trigger.end():]
            stop = re.search(r"\.\s", tail)
            if stop:
                tail = tail[:stop.start()]
            for raw in re.split(r"[;•,]|&#8226;", tail):
                item = raw.strip(" .,:&#0123456789").strip()
                item = re.sub(r"^(?:and|or|such as|including)\s+", "", item,
                              flags=re.I).strip()
                if not (3 < len(item) < 60):
                    continue
                # A category is a lowercase noun phrase. A capitalised span is
                # a company name and belongs to find_competitors, not here.
                if item[:1].isupper() or _NAME.search(item):
                    continue
                if not re.search(r"\b(vendors?|systems?|processors?|"
                                 r"providers?|services?|marketplaces?|"
                                 r"registrars?|lenders?|companies|"
                                 r"integrators?|contractors?|consultants?|"
                                 r"platforms?|software)\b", item, re.I):
                    continue
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "category": item,
                    "evidence_id": str(evidence_id),
                    "source_title": str(document.get("source_title") or ""),
                    "date": str(document.get("date") or ""),
                    "limitation": ("A class of alternative named in the "
                                   "company's own filing, not a specific "
                                   "competitor; no company is identified."),
                })
                if len(out) >= limit:
                    return out
    return out


#: The alternative with no company name. A buyer's own engineering team is the
#: most common thing an enterprise product loses to, and a name-based finder
#: cannot see it -- there is no capitalised span to match. It was missing from
#: the first run against a real filing whose Competition section said exactly
#: that customers "may instead build these capabilities in-house".
_INTERNAL_PATTERNS = (
    r"build\s+(?:these\s+|this\s+|such\s+|their\s+own\s+|it\s+)?"
    r"(?:capabilit(?:y|ies)|solutions?|software|tools?|systems?)?\s*"
    r"in[- ]house",
    r"in[- ]house\s+(?:development|solutions?|alternatives?|teams?|"
    r"capabilit(?:y|ies))",
    r"internally\s+develop(?:ed|ing)?",
    r"(?:their|its)\s+own\s+engineering\s+teams?",
    # Added from the live Palantir 10-K, whose Competition section opens
    # "We are fundamentally competing with the internal software development
    # efforts of our potential customers" and continues "Organizations
    # frequently attempt to build their own data platforms before turning to
    # buy ours". Neither phrasing uses "in-house" or "internally develop", so
    # the strongest statement of the in-house alternative any filing in the
    # validation set contains was invisible to all four patterns above.
    r"internal\s+(?:software\s+)?(?:development|engineering)\s+"
    r"(?:efforts?|resources?|teams?)",
    r"build\s+their\s+own\s+\w+(?:\s+\w+)?",
    r"software\s+developed\s+by\s+customers\s+internally",
)


def _internal_build(documents, *, today: str) -> Optional[Competitor]:
    for document in documents or ():
        if not isinstance(document, dict):
            continue
        text = _document_text(document)
        evidence_id = document.get("observation_id") or document.get(
            "source_id") or document.get("document_id") or ""
        if not text or not evidence_id:
            continue
        for passage in competition_passages(text):
            for pattern in _INTERNAL_PATTERNS:
                found = re.search(pattern, passage, re.I)
                if not found:
                    continue
                sentence = next(
                    (s for s in _sentences(passage)
                     if re.search(pattern, s, re.I)), passage)
                try:
                    return Competitor(
                        name="The buyer's own engineering team",
                        relationship=INTERNAL_BUILD,
                        overlap=sentence.strip()[:400],
                        evidence_ids=(str(evidence_id),),
                        source_titles=(str(document.get("source_title")
                                           or ""),),
                        relevance=CLAIM_RELEVANT,
                        reason=("the company's own filing names building "
                                "in-house as the alternative its customers "
                                "weigh"),
                        matched_on=found.group(0),
                        date=str(document.get("date") or ""),
                        decision_implication=_implication(INTERNAL_BUILD),
                        limitation=("Named as an alternative in the "
                                    "company's own account; how often buyers "
                                    "actually choose it is not disclosed."))
                except CompetitorRejected:  # pragma: no cover
                    return None
    return None


def _implication(relationship: str) -> str:
    return {
        DIRECT_COMPETITOR: (
            "Whether the differentiation this plan assumes is one a buyer "
            "comparing the two would actually notice."),
        PLATFORM_ALTERNATIVE: (
            "Whether to compete on depth in one job or on breadth across a "
            "suite, since a buyer standardising on a platform is not "
            "comparing features."),
        INTERNAL_BUILD: (
            "Whether the pitch is against another vendor or against the "
            "buyer's own engineering time, which is a different argument and "
            "a different price anchor."),
        CONSULTING_ALTERNATIVE: (
            "Whether to sell outcomes with delivery attached rather than a "
            "product the buyer must staff themselves."),
        PARTNER_AND_COMPETITOR: (
            "Whether the partnership is worth the channel it opens, given it "
            "also arms the other side in overlapping deals."),
        ADJACENT_SUBSTITUTE: (
            "Whether the problem being solved is one a buyer could remove "
            "another way, which caps pricing regardless of feature parity."),
    }.get(relationship, "")

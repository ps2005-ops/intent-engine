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

from intent_engine.executive.competitive_qualification import (
    ADJACENT_THREAT_STATE, DIRECT_COMPETITOR, SUBSTITUTE_STATE, qualify,
)

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
#: A LEGAL FORM IS PROOF. Nothing else in a filing wears one.
_LEGAL_FORM = ("inc", "inc.", "corp", "corp.", "corporation", "company",
               "co.", "ltd", "ltd.", "llc", "plc", "sa", "ag", "nv", "gmbh",
               "ab", "oyj", "pte", "bv", "spa", "a/s", "kk", "lp", "llp",
               "s.a.", "n.v.", "s.p.a.", "pty")

#: A TRADE WORD IS EVIDENCE, NOT PROOF. "Akamai Technologies" is a company;
#: "Online Platforms" is a category, and it reached a live introduction as
#: one of Cloudflare's three named competitors because "platforms" was in
#: this list and nothing asked what came before it.
_TRADE_WORD = ("technologies", "systems", "software", "labs", "group",
               "holdings", "solutions", "networks", "platforms", "partners",
               "industries", "enterprises", "communications", "services")

_CORPORATE = _LEGAL_FORM + _TRADE_WORD

#: Strongest competitive claim first. An adjacent threat is real and is not
#: what contests the company most directly, so it sorts behind both.
_STATE_RANK = {DIRECT_COMPETITOR: 0, SUBSTITUTE_STATE: 1,
               ADJACENT_THREAT_STATE: 2}

#: Ordinary English that starts a noun phrase. A trade word behind one of
#: these is a category, not a firm. Measured live: "Federal Risk",
#: "Intuitive User Experience" and "Online Platforms" were all presented as
#: companies contesting Cloudflare's market.
_COMMON_ENGLISH = frozenset({
    "online", "federal", "national", "international", "global", "digital",
    "intuitive", "modern", "leading", "major", "large", "small", "public",
    "private", "certain", "other", "various", "multiple", "several", "many",
    "new", "existing", "traditional", "legacy", "open", "closed", "free",
    "paid", "enterprise", "consumer", "commercial", "financial", "general",
    "regional", "local", "primary", "secondary", "third", "cloud", "data",
    "security", "network", "internet", "web", "mobile", "social", "smart",
    "advanced", "integrated", "managed", "professional", "technical", "user",
    # ...and the ordinary nouns and verbs that turn a capitalised span into a
    # phrase. Every entry here was measured producing a false competitor or
    # is the kind of word that would.
    "experience", "risk", "risks", "platform", "product", "products",
    "service", "solution", "customer", "customers", "market", "markets",
    "business", "businesses", "company", "companies", "industry", "vendor",
    "vendors", "provider", "providers", "competitor", "competitors",
    "alternative", "alternatives", "offering", "offerings", "capability",
    "capabilities", "technology", "tools", "tool", "software", "hardware",
    "management", "program", "programme", "quality", "value", "cost",
    "price", "pricing", "growth", "revenue", "demand", "supply", "support",
    "development", "research", "operations", "performance", "innovation",
    "experiences", "access", "content", "design", "delivery", "scale",
    "trust", "safety", "privacy", "compliance", "governance", "strategy",
    "team", "teams", "people", "region", "regions", "state", "states",
    "government", "agency", "agencies", "authorization", "certification",
})

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


#: Head nouns that make a capitalised span an institution, a standard or a
#: programme rather than a company you could buy from instead. Measured live
#: on Cloudflare, whose competitors came back as "FedRAMP" and "Authorization
#: Management Program" -- both fragments of "Federal Risk and Authorization
#: Management Program", a US government certification scheme, presented to a
#: chief executive as firms contesting their market.
_NOT_A_VENDOR = frozenset({
    "program", "programme", "act", "framework", "standard", "standards",
    "regulation", "regulations", "directive", "initiative", "alliance",
    "association", "foundation", "institute", "consortium", "committee",
    "authority", "commission", "agency", "department", "ministry",
    "administration", "bureau", "council", "board", "office", "treaty",
    "convention", "protocol", "certification", "accreditation", "scheme",
    "guidelines", "rule", "rules", "law", "code",
})

#: Standard and programme acronyms that are single tokens and therefore slip
#: past the head-noun test above.
_NOT_A_VENDOR_EXACT = frozenset({
    # standards, regulations and certification schemes
    "fedramp", "gdpr", "hipaa", "soc", "pci", "pci-dss", "iso", "nist",
    "ccpa", "sox", "dora", "mifid", "basel", "ifrs", "gaap", "esg",
    # CATEGORY ACRONYMS. Structurally identical to the schemes above: a
    # capitalised token, mixed case, in a sentence that genuinely says
    # "compete" -- "we compete with other SaaS providers" -- and not a
    # company anyone can buy from. "SaaS" survived the grammatical rule and
    # reached the deployed introduction as one of Cloudflare's three named
    # competitors.
    "saas", "paas", "iaas", "api", "apis", "cdn", "vpn", "sase", "ai", "ml",
    "llm", "crm", "erp", "sdk", "cms", "b2b", "b2c", "sme", "smb", "it",
    "iot", "saas/paas", "devops", "mlops", "byod", "sso", "mfa",
})


def _is_the_subject(name: str, subject: str) -> bool:
    """Is this candidate the subject, or something the subject owns?

    "Cloudflare Workers" is Cloudflare's own product and was returned as
    Cloudflare's competitor and rendered on the introduction, one line under
    the company's name. The old test asked whether the CANDIDATE was inside
    the SUBJECT, which is the wrong direction for a product name.

    Word boundaries throughout: a substring test refuses "Alphabet Inc." for
    containing "alpha", which is the opposite mistake and has been made here
    before.
    """
    subject_tokens = [w.lower() for w in re.split(r"\W+", subject or "") if w]
    generic = {"inc", "corp", "corporation", "company", "co", "ltd",
               "limited", "plc", "holdings", "group", "the", "and", "sa",
               "nv", "ag", "llc", "lp"}
    distinctive = [t for t in subject_tokens
                   if t not in generic and len(t) > 2]
    candidate = {w.lower() for w in re.split(r"\W+", name) if w}
    return any(token in candidate for token in distinctive)


def candidate_names(passage: str, *, subject: str = "") -> List[str]:
    """Capitalised spans that plausibly name an organisation."""
    subject_words = {w.lower() for w in re.split(r"\W+", subject or "") if w}
    found: List[str] = []
    for raw in _NAME.findall(passage or ""):
        # A NAME MAY NOT SPAN A SENTENCE. `_NAME` allows "." inside a token so
        # that "Inc." and "Co." survive, and the cost is that "…Alphabet Inc.
        # The Federal…" matched as ONE span and reached the page as a company
        # called "Alphabet Inc. The Federal". A token ending in a full stop is
        # where the span ends -- that is true both when the stop closes an
        # abbreviation and when it closes a sentence.
        pieces = raw.split()
        for index, piece in enumerate(pieces):
            if piece.endswith(".") and index < len(pieces) - 1:
                pieces = pieces[:index + 1]
                break
        raw = " ".join(pieces)
        name = raw.strip(" .,;:")
        lowered = name.lower()
        if len(name) < 3 or lowered in _STOPLIST:
            continue
        # The subject is not its own competitor, and neither is anything the
        # subject makes.
        if subject and (lowered in (subject or "").lower()
                        or lowered in subject_words
                        or _is_the_subject(name, subject)):
            continue
        # A programme, a standard or a regulator is not an alternative a
        # buyer weighs. It cannot be sold to, bought from, or competed with.
        tokens = [w.lower().strip(".") for w in name.split()]
        if lowered.replace(" ", "").strip(".") in _NOT_A_VENDOR_EXACT:
            continue
        if tokens and tokens[-1] in _NOT_A_VENDOR:
            continue
        if any(t in _NOT_A_VENDOR for t in tokens):
            continue
        words = lowered.split()
        if len(words) == 1:
            # A single capitalised word is usually a sentence opener. Keep it
            # only when it is unambiguously a brand: mixed case inside the
            # word, a digit, or an ampersand.
            if not re.search(r"[a-z][A-Z]|[0-9&]", name):
                continue
        # A MULTI-WORD SPAN NEEDS POSITIVE EVIDENCE THAT IT IS AN
        # ORGANISATION. Three consecutive live runs put a certification
        # scheme, a marketing noun phrase and a product category on the
        # introduction as named competitors. A missed rival is a quiet
        # omission and the read still shows classified peers; a fabricated
        # one tells a chief executive to worry about a company that does not
        # exist in their market.
        elif len(words) > 1:
            tokens_clean = [w.strip(".") for w in words]
            has_legal = any(t in _LEGAL_FORM for t in tokens_clean)
            has_trade = any(t in _TRADE_WORD for t in tokens_clean)
            if has_legal:
                pass                        # a legal form is proof
            elif has_trade:
                # "Akamai Technologies" is a company; "Online Platforms" is a
                # category. What separates them is the word in front.
                if tokens_clean[0] in _COMMON_ENGLISH:
                    continue
            else:
                # NO CORPORATE MARKER AT ALL. "Booz Allen Hamilton" is three
                # surnames and is a real firm; "Intuitive User Experience" is
                # three ordinary English words and is a marketing phrase.
                # Requiring that NONE of the tokens is ordinary vocabulary
                # keeps the first and refuses the second, which is exactly
                # the line the live fabrications fell on.
                if any(t in _COMMON_ENGLISH for t in tokens_clean):
                    continue
        if len(words) > 1 and not any(
                w.strip(".") in _CORPORATE for w in words):
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


#: A sentence that is doing something, rather than labelling a section. Every
#: filing heading is a capitalised noun phrase with no verb in it, which is
#: exactly why three rounds of word-level stoplists could not stop them:
#: "Competitive Landscape", "Human Capital Resources" and "Item 1A. Risk
#: Factors" are not made of unusual words, they are made of no verbs.
_HAS_A_VERB = re.compile(
    r"\b(?:is|are|was|were|be|been|has|have|had|do|does|did|include|"
    r"includes|included|compete|competes|competing|competed|offer|offers|"
    r"provide|provides|sell|sells|serve|serves|face|faces|may|can|could|"
    r"would|will|expect|expects|believe|believes|consider|considers|"
    r"remain|remains|continue|continues)\b", re.I)

#: An explicit statement that this is a market contest, in the candidate's own
#: sentence. A heading three lines above one of these is not covered by it.
_COMPETITION_IN_SENTENCE = re.compile(
    r"\bcompet(?:e|es|ing|ed|itor|itors|itive)\b"
    r"|\balternatives?\s+(?:to|include)\b"
    r"|\brivals?\b|\bin[- ]house\b|\bsubstitutes?\b", re.I)


def names_a_contest(sentence: str) -> bool:
    """Is this a SENTENCE ABOUT COMPETING, rather than a heading?

    THE THIRD LIVE FABRICATION IS WHAT FORCED THIS. Two rounds of word-level
    filtering were each defeated within one deploy:

        run 1: "Authorization Management Program, Cloudflare Workers, FedRAMP"
        run 2: "Federal Risk, Intuitive User Experience, Online Platforms"
        run 3: "Competitive Landscape, Human Capital Resources, SaaS"

    Every entry in round three is a heading out of a 10-K. No stoplist of
    words can separate a heading from a name, because headings are built from
    ordinary business vocabulary -- which is what a stoplist is made of too.
    What separates them is GRAMMAR: a heading has no verb, and it does not
    itself say that anyone is competing.

    So a candidate is kept only when its own sentence both says that a
    contest exists and is a sentence at all. This is narrower than the
    stoplists it replaces and it cannot be defeated by a heading nobody has
    seen yet.
    """
    flat = " ".join(str(sentence or "").split())
    return bool(_COMPETITION_IN_SENTENCE.search(flat)
                and _HAS_A_VERB.search(flat))


def _overlap_sentence(passage: str, name: str) -> str:
    """The sentence that actually makes the claim, so a reader can check it."""
    for sentence in _sentences(passage):
        if name.lower() in sentence.lower():
            return sentence.strip()
    return ""


def find_competitors(documents, *, subject: str = "", today: str = "",
                     limit: int = 5, refusals: Optional[List] = None,
                     business_model: str = "") -> List[Competitor]:
    """Competitors this run's own evidence supports, best first.

    `documents` are mappings with `text`, `observation_id`, `source_title`,
    `source_class` and `date` — the shape the ingestion store already emits.

    Pass a list as `refusals` to receive every candidate that was NOT a
    competitive alternative, each carrying the section it belongs under. §6:
    the system should become smarter, not quieter.
    """
    ranked: Dict[str, Competitor] = {}
    #: §6. WHAT WAS NOT A RIVAL, KEPT. An index, a payer programme and a
    #: captive lender's competitors are real facts about the company. The
    #: answer to publishing them in the wrong section is the right section,
    #: not silence — `qualified_candidates` is how a surface reaches them.
    refused: List = []
    #: The order the SUBJECT names them in, which is the subject's own
    #: ranking of its markets. Recorded at first sight because the ranking
    #: below needs it and a dict of results has already lost it.
    first_seen: Dict[str, int] = {}
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
                first_seen.setdefault(name.lower(), len(first_seen))
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
                # §3. THE CLAUSE THAT NAMES IT MUST BE THE CLAUSE THAT MAKES
                # THE CLAIM, AND THE NAME MUST BE AN ECONOMIC ALTERNATIVE.
                #
                # `names_a_contest` reads the whole retrieved span, and a
                # filing "sentence" is routinely a list: Meta's was 2,262
                # characters and fifteen bullets, with "S&P" in the bullet
                # about stock indices and "competitors" five bullets away.
                # Asking the span whether a contest exists answered yes and
                # said nothing about S&P. The qualification reads the clause
                # the name is actually in.
                qualification = qualify(
                    candidate=name, evidence=overlap, subject=subject,
                    business_model=business_model)
                clause = qualification.evidence_basis or overlap
                # BOTH TESTS, AND BOTH MUST PASS. The clause has to be a
                # sentence that says a contest exists (`names_a_contest`,
                # which is what keeps filing headings out), and the entity
                # has to be something a customer could choose (the
                # qualification, which is what keeps an index and a payer
                # programme out). Each catches what the other cannot.
                if not qualification.may_contest:
                    refused.append(qualification)
                    continue
                if not names_a_contest(clause):
                    continue
                relationship = _relationship(clause)
                existing = ranked.get(name.lower())
                if existing and existing.relevance == CLAIM_RELEVANT \
                        and verdict.relevance != CLAIM_RELEVANT:
                    continue
                try:
                    ranked[name.lower()] = Competitor(
                        name=name, relationship=relationship,
                        # THE EXCERPT IS THE CLAUSE, NOT THE BLOB. Quoting
                        # the first 400 characters of a fifteen-bullet list
                        # put a sentence about income tax under a competitor
                        # called S&P — an excerpt that establishes nothing
                        # for the reader who tries to check it.
                        overlap=clause[:400],
                        qualification_state=qualification.qualification_state,
                        entity_type=qualification.entity_type,
                        contest_owner=qualification.contest_owner,
                        focal_need=qualification.focal_need,
                        substitution_mechanism=(
                            qualification.substitution_mechanism),
                        routed_section=qualification.section,
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
    if refusals is not None:
        refusals.extend(refused)
    internal = _internal_build(documents, today=today)
    if internal is not None:
        ranked.setdefault("__internal_build__", internal)
    # §3 OF THE MEASURED CAUSES: SELECTION WAS ALPHABETICAL.
    #
    # Caterpillar's filing names forty-three firms — Komatsu, Deere, Cummins,
    # Liebherr, Sandvik, Volvo CE — and this returned Alstom, America
    # Leasing, BNP Paribas and Baker Hughes, because it sorted by name and
    # took four. A company's own order of mention is its own ranking of its
    # markets, and it was being thrown away.
    order = {name: i for i, name in enumerate(first_seen)}
    out = sorted(ranked.values(),
                 key=lambda c: (not c.may_contest,
                                _STATE_RANK.get(c.qualification_state, 1),
                                c.relevance != CLAIM_RELEVANT,
                                order.get(c.name.lower(), 10_000),
                                c.name.lower()))
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

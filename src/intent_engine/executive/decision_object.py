"""What a decision at THIS company is actually about, in its own words.

THE DEFECT THIS CLOSES
----------------------
Measured on the frozen 40-company qualification (`db6946fa`): 33 companies
reached a decision and between them produced FOUR distinct decision questions.
Twenty-two of them received, verbatim:

    "what to charge, and for what, without losing more customer count than
     the price gains?"

Not because twenty-two companies face the same decision, but because the
question is `f(archetype, business_model_class)` -- its variable slots are
filled from `_ECONOMICS[business_model_class]`, a table keyed on the class.
Every subscription software business in existence has
`primary_revenue_drivers[0] == "customer count"`.

The positive controls confirm the mechanism rather than contradicting it.
project44, Descartes and o9 became EVIDENCE_LED on nine phrase matches
between them, all from ONE archetype's vocabulary -- and they too received
one byte-identical question.

WHAT THIS MODULE DOES
---------------------
It reads the company's OWN published account and tries to establish three
things a decision question actually needs and that genuinely differ between
companies:

    BILLING UNIT   what one unit of this company's revenue is counted in
                   -- "developer seats", "data ingested", "managed endpoints"
    BUYER          who decides to pay -- "security teams", "general
                   contractors", "law firms"
    DEPENDENCY     what delivery rests on that the company does not own

WHY THESE THREE AND NOT MORE VOCABULARY
---------------------------------------
Because the repair for a class-keyed constant is a different SOURCE, not a
longer keyword list. Giving the other fifteen archetypes object-noun
vocabularies would fire a security vocabulary at twelve security companies
and hand all twelve one NEW constant -- differentiation theatre, and the
exact thing the 40 already rejected (GTM vocabulary, compliance words,
ASC 805 boilerplate, disclosed SaaS metrics).

These three slots are high-cardinality, first-party, and load-bearing: a
pricing decision measured in developer seats is a different decision from one
measured in ingested terabytes, and the difference is the company's, not a
synonym's.

THE SUBJECT RULE
----------------
A phrase counts only when THIS COMPANY is the grammatical subject of the
sentence that carries it. This is the lesson the positive controls taught at
cost: project44's record is saturated with `carrier`, `freight` and `customs`
because logistics is the domain it SELLS INTO, and the system read that as
"this company is deciding about its own supply chain". A company that
mentions a thing is not a company that depends on it.

WHAT IT MAY NOT DO
------------------
Guess. Every slot is `ESTABLISHED` with a quoted sentence or it is
`NOT_ESTABLISHED` with a reason, and a caller that gets `NOT_ESTABLISHED`
must fall back to the class prior AND SAY THAT IT DID. A slot filled by
assumption is worse than no slot, because it reads as though the company
told us.

Low recall is correct here. A slot that fires for eight companies in
twenty-five with real quotes is an improvement; a slot that fires for
twenty-five with plausible noise is a regression that cannot be seen.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Tuple

CONTRACT = "decision_object.v1"

ESTABLISHED = "ESTABLISHED"
NOT_ESTABLISHED = "NOT_ESTABLISHED"

#: The longest a slot phrase may be. A decision question reads it inline, and
#: a clause pasted into the middle of a question is not a noun phrase.
MAX_SLOT_CHARS = 52   # five words of real English; measured, not guessed
MIN_SLOT_CHARS = 3

#: Words that cannot BEGIN a noun phrase. Openers that indicate the regex
#: captured a clause, a pronoun or a fragment rather than a thing.
_BAD_HEADS = frozenset("""
a an the and or but if then than that this these those which who whom whose
is are was were be been being am do does did done doing have has had having
it its they them their we us our you your he she his her i me my
to of in on at by for with from as so such very more most much many any
all some each every other another not no nor only just also both either
neither because while when where how what why whether can could should would
may might must will shall about over under into onto out up down off
""".split())

#: Grammatical filler. Never names anything, in any slot.
_FILLER = frozenset("""
year years month months day days week weeks quarter quarters annum
time times use uses case cases example examples experience experiences
free trial demo more less best better good great new next
rest details information detail thing things way ways
""".split())

#: Adjectives that open marketing copy rather than naming anything. MEASURED:
#: "Built for the best experience" produced a BUYER of "best experience".
_EVALUATIVE = frozenset("""
best better great good ideal perfect right leading innovative modern
world-class powerful simple easy fast secure smart seamless complete
ultimate premier trusted proven advanced next-generation
world world's worlds industry industry's global leading-edge
""".split())

#: Words that name a BUYER only in the sense that everybody is one. A
#: company "built for businesses" has told us nothing, so the buyer slot
#: refuses them -- while the BILLING UNIT slot does NOT, because "priced per
#: user" is a real and load-bearing answer even though it is a common one.
#: Whether it is a COMMON answer is the genericity detector's question, not
#: the extractor's: refusing to read a true similarity hides it.
_GENERIC_BUYER = frozenset("""
company companies business businesses organisation organisations organization
organizations team teams customer customers client clients user users
person people employee employees member members everyone anyone
thousands millions hundreds dozens many all some others world
enterprise enterprises firm firms
""".split())

#: Quantifiers and size words. They modify a buyer without naming one, so
#: "businesses of all sizes" carries four words and names nobody -- which is
#: how it escaped a check that required EVERY word to be generic.
_QUANTIFIER = frozenset("""
of all any every each both some many few several most more less
size sizes type types kind kinds shape shapes scale scales range ranges
large small medium big little tiny huge growing modern today
everywhere worldwide global globally across throughout around
""".split())

#: Nouns that point back at something rather than naming it. "the rest of
#: the group" carries four words, passes every word-level gate, and names
#: nobody -- it is an anaphor, and whatever it refers to is in a different
#: sentence. Defence in depth behind the subject rule: even a sentence that
#: DOES name the company can contain one.
_PARTITIVE = frozenset("""
rest remainder some many most few several all both each one any none
others other half part portion majority minority handful number couple
""".split())

_STOP_SLOTS = _FILLER

#: Page furniture: if a captured sentence carries one of these it is
#: navigation, a cookie banner or a form, not the company speaking.
_FURNITURE = (
    "cookie", "privacy policy", "terms of service", "all rights reserved",
    "sign up", "log in", "sign in", "subscribe", "newsletter",
    "contact us", "get in touch", "request a demo", "book a demo",
    "javascript", "browser", "404", "page not found", "skip to",
)

#: The company as grammatical subject. Either first person or the company's
#: own name in subject position.
#:
#: THE WORD BOUNDARIES ARE THE WHOLE RULE. Without them "we" matches inside
#: "ho-we-ver" and "us" inside "vers-us", so EVERY sentence on the internet
#: names the company in the first person and the subject discipline is
#: decorative. MEASURED LIVE on Arctic Wolf (a9ca9f8c): a threat-research
#: post about the Karakurt and Conti ransomware gangs -- "However Karakurt
#: is being run ... used by the rest of the group" -- was read as Arctic
#: Wolf naming its own buyer, and the page said so to a reader.
_FIRST_PERSON = r"(?<![a-z])(?:we|our|ours|us)(?![a-z])"

#: Base verbs that take an object in "helps X <verb> Y". A greedy capture
#: runs straight through them -- "development teams find and fix
#: vulnerabilities" -- so the phrase is cut at the first one. This is a
#: closed GRAMMATICAL list (infinitive complements), deliberately not a list
#: of domain words: adding domain words here would be the keyword approach
#: this module exists to replace.
_COMPLEMENT_VERBS = frozenset("""
find fix build manage secure reduce improve deliver scale automate protect
monitor detect respond comply grow save move track plan connect discover
prevent accelerate simplify streamline transform optimise optimize
understand see get stay work run do make take keep turn bring put use
identify remediate enforce govern audit report analyse analyze measure
""".split())

#: Time words that may follow "per" and are never a billing unit.
_PER_TIME = frozenset("""
year month day week quarter hour minute second annum night
""".split())


@dataclasses.dataclass(frozen=True)
class Slot:
    """One extracted variable, or an explicit refusal to extract it."""
    kind: str                       #: BILLING_UNIT / BUYER / DEPENDENCY
    value: str = ""
    state: str = NOT_ESTABLISHED
    quote: str = ""                 #: the sentence the value came from
    pattern: str = ""               #: which rule matched, for audit
    reason: str = ""                #: why NOT_ESTABLISHED

    @property
    def known(self) -> bool:
        return self.state == ESTABLISHED and bool(self.value)

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class DecisionObject:
    """The company-specific variables a decision question can be built from."""
    company: str = ""
    billing_unit: Slot = dataclasses.field(
        default_factory=lambda: Slot(kind="BILLING_UNIT"))
    buyer: Slot = dataclasses.field(
        default_factory=lambda: Slot(kind="BUYER"))
    dependencies: Tuple[Slot, ...] = ()
    text_chars: int = 0
    contract: str = CONTRACT

    @property
    def established_count(self) -> int:
        return (int(self.billing_unit.known) + int(self.buyer.known)
                + sum(1 for d in self.dependencies if d.known))

    @property
    def any_established(self) -> bool:
        return self.established_count > 0

    def as_dict(self) -> dict:
        return {
            "contract": self.contract,
            "company": self.company,
            "billing_unit": self.billing_unit.as_dict(),
            "buyer": self.buyer.as_dict(),
            "dependencies": [d.as_dict() for d in self.dependencies],
            "established_count": self.established_count,
            "text_chars": self.text_chars,
        }


def _sentences(text: str):
    """Split on sentence ends, keeping it cheap and boundary-safe."""
    body = " ".join(str(text or "").split())
    for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", body):
        part = part.strip()
        if 12 <= len(part) <= 400:
            yield part


def _is_furniture(sentence: str) -> bool:
    low = sentence.lower()
    return any(marker in low for marker in _FURNITURE)


def _is_prose(sentence: str) -> bool:
    """Is this a sentence somebody wrote, or a navigation bar with the tags
    taken out?

    MEASURED ON REAL PAGES, which is the only place this shows. Stripping
    tags from a marketing homepage yields long unpunctuated runs of menu
    labels -- "Platform Solutions Pricing Partners Resources Outcomes
    Company" -- and a "built for X" pattern matching inside one of those
    produced a BUYER of "Outcomes" for Huntress and "center" for Vanta
    (from "Trust Center"). Both would have reached a customer page.

    Prose is distinguished from furniture by three properties no menu has:
    it is punctuated, it is mostly lower case, and it contains a function
    word. None of them is about the topic, so this cannot become a
    domain-vocabulary filter by accident.
    """
    words = sentence.split()
    if len(words) < 5:
        return False
    if not re.search(r"[.,;:]", sentence):
        return False
    capitalised = sum(1 for w in words if w[:1].isupper())
    if capitalised > len(words) * 0.5:
        return False
    # A menu label is Title Case; a sentence carries ordinary lower-case
    # words. Two of them, so a single stray token cannot vouch for a run of
    # navigation. Deliberately NOT a function-word list: "Arctic Wolf serves
    # mid-market credit unions." contains none and is plainly a sentence.
    return sum(1 for w in words if len(w) >= 3 and w.islower()) >= 2


def _clean_phrase(raw: str) -> str:
    """Trim a captured span to something that can stand in a question."""
    phrase = " ".join(str(raw or "").split()).replace("\u2019", "'")
    phrase = phrase.strip(" ,;:.!?\"'()[]{}-–—")
    # A capture that runs into a subordinate clause is cut at the joint.
    phrase = re.split(r"\b(?:that|which|who|when|where|because|so that|"
                      r"in order to|whose|while)\b", phrase, maxsplit=1)[0]
    # A counting preamble is not the unit. "the number of contributing
    # developers" is billed per DEVELOPER; "number" on its own names nothing.
    phrase = re.sub(r"^(?:the\s+)?(?:number|amount|volume|total|quantity)"
                    r"\s+of\s+", "", phrase, flags=re.I)
    phrase = re.sub(r"^(?:the|a|an|your|each|every|any)\s+", "",
                    phrase, flags=re.I)
    phrase = phrase.strip(" ,;:.!?\"'()[]{}-–—")
    # "helps development teams find and fix vulnerabilities" names a buyer
    # of three words and then says what they do with it.
    words = phrase.split()
    for i, word in enumerate(words):
        if i and word.lower().strip(",") in _COMPLEMENT_VERBS:
            phrase = " ".join(words[:i])
            break
    # "priced per camera per year" is priced per CAMERA.
    phrase = re.sub(r"\s+per\s+(?:" + "|".join(sorted(_PER_TIME)) + r")$", "",
                    phrase, flags=re.I)
    phrase = re.sub(r"(?:\s+(?:with|of|for|to|and|in|on|at|by|from|a|an|the|"
                    r"that|as|is|are|you|your|we|our|they|their|it|its))+$",
                    "", phrase, flags=re.I)
    # English noun phrases are head-final, so a trailing prepositional
    # phrase is a modifier and not the thing named. Cutting it turns
    # "mid-market enterprises across north america" into its head and
    # exposes "enterprise-wide access governance across all users" as the
    # activity it is.
    phrase = re.split(
        r"\s+(?:across|throughout|within|around|worldwide|globally|of)\s+",
        phrase, maxsplit=1, flags=re.I)[0].strip()
    # A trailing adverb modifies the verb, not the noun: "...operations teams
    # EVERYWHERE" names the same people as "...operations teams".
    phrase = re.sub(r"(?:\s+(?:everywhere|worldwide|globally|today|daily|"
                    r"now|currently|anywhere|always|everyday))+$", "",
                    phrase, flags=re.I).strip()
    return phrase.strip(" ,;:.!?\"'()[]{}-–—")


#: Singular nouns that name a population anyway. Deliberately tiny: every
#: addition is a claim that a word names people, and the plural test below
#: already covers the ordinary case.
_COLLECTIVE = frozenset("""
industry sector market workforce staff personnel leadership management
government military public academia healthcare
""".split())

#: Endings that mark a verb or a gerund. A noun phrase naming buyers carries
#: none of them at any position.
_VERB_ENDINGS = ("ing", "ize", "ise", "ify", "ate")

#: Nouns that end like verbs and are not. Short by design -- a long list
#: here would be the closed-list mistake in a new place.
_NOUN_EXCEPTIONS = frozenset("""
engineering manufacturing accounting consulting banking marketing training
underwriting shipping publishing advertising gaming staffing housing
building holding leasing insuring nursing teaching
""".split())


def is_plural_noun(word: str) -> bool:
    """Plural in FORM. One rule, because two callers need exactly this test.

    `_is_population` asks it about a buyer's head word; `analysis_selection`
    asks it about a billing unit before putting it after "more", which is
    how "without losing more device than the price gains" reached NinjaOne's
    X-Ray. Restating it there would be a second copy of a rule that is
    already subtle: "-ss", "-us", "-is" and "-ics" endings are singular
    words that merely end in s.
    """
    w = str(word or "").lower().strip(",;:.'\u2019\"")
    if not w.endswith("s"):
        return False
    return not w.endswith(("ss", "us", "is", "ics"))


def _is_population(word: str) -> bool:
    """Does this word name a group of people or organisations?

    A plural common noun is the ordinary form ("firms", "teams", "developers",
    "hospitals").
    """
    if word in _COLLECTIVE:
        return True
    return is_plural_noun(word)


#: Prepositions that open a POST-HEAD modifier. English noun phrases are
#: head-final up to the first of these, and everything after one modifies
#: the head rather than being it.
_POST_HEAD = ("in", "of", "for", "across", "with", "to", "at", "on", "from",
              "among", "within", "through", "by", "under", "over", "into",
              "between", "around", "about", "against")

#: Possessive determiners -- a genuinely CLOSED class in English, unlike the
#: verb list this module had to abandon at 1b5689f6. A named population is
#: named; a phrase carrying "their" or "our" is pointing back at a subject
#: somewhere else in the sentence, which is the tell of a capture that ran
#: past the people it was meant to name.
_POSSESSIVE = ("my", "our", "your", "their", "its", "his", "her", "whose")


def _head_noun(phrase: str) -> str:
    """The head: the last word BEFORE the first post-head preposition.

    THE COMMENT BELOW PROMISED THIS AND THE CODE DID NOT DO IT. The buyer
    branch said "the head is found by cutting the trailing prepositional
    phrase" and then tested `words[-1]`, so on Procore's live X-Ray at
    591041b0 "vital role in our customers' operations" was accepted as a
    population -- its LAST word, "operations", is plural, while its actual
    head, "role", is not. The central question went out reading "without
    losing more customer count among vital role in our customers'
    operations than the price gains".
    """
    words = [w.lower() for w in str(phrase or "").split()]
    for index, word in enumerate(words):
        if index and word in _POST_HEAD:
            return words[index - 1].strip(",;:.'\u2019\"")
    return words[-1].strip(",;:.'\u2019\"") if words else ""


def _is_inflected_verb(word: str) -> bool:
    """Does this word carry a verb or gerund inflection?"""
    if word in _NOUN_EXCEPTIONS or word in _COLLECTIVE:
        return False
    return word.endswith(_VERB_ENDINGS)


def _narrow(phrase: str) -> str:
    """First conjunct of an over-long phrase, for a second acceptance try."""
    head = re.split(r"\s+and\s+|\s*,\s*", phrase, maxsplit=1)[0]
    return head.strip(" ,;:.!?\"'()[]{}-–—")


def _acceptable(phrase: str, company: str, kind: str = "") -> str:
    """'' when the phrase may stand in a question, else why it may not."""
    if not phrase:
        return "nothing was captured"
    if len(phrase) < MIN_SLOT_CHARS:
        return "the captured phrase is too short to name anything"
    if len(phrase) > MAX_SLOT_CHARS:
        return "the captured phrase is a clause, not a thing"
    words = phrase.lower().split()
    if not words:
        return "nothing was captured"
    if len(words) > 6:
        return "the captured phrase is a clause, not a thing"
    if words[0] in _BAD_HEADS:
        return f"the phrase begins with {words[0]!r}, so it is a fragment"
    if words[0] in _EVALUATIVE:
        return (f"the phrase begins with {words[0]!r}, so it is a claim about "
                f"quality rather than a thing")
    if all(w in _FILLER for w in words):
        return "the phrase is grammatical filler rather than a thing"
    # A BUYER IS A ROLE, AND ROLES ARE WRITTEN IN LOWER CASE.
    #
    # MEASURED on real pages: "Built for Outcomes, Not Optics" is a slogan,
    # and it gave Huntress a buyer of "Outcomes". A heading run together with
    # the next heading gave Vanta "center", from "Help center". Both are
    # Title Case where a common noun would not be, because both are headings
    # rather than sentences -- and a marketing page is mostly headings.
    if kind == "BILLING_UNIT":
        # A UNIT IS A COMMON NOUN IN PROSE, NOT A DEFINED TERM.
        #
        # MEASURED LIVE on Coveo (bbb75261): "Entitlement", capitalised
        # mid-sentence, reached the central question as "without losing more
        # Entitlement than the price gains". A capitalised single word in a
        # filing is a defined term or a heading; a thing customers are
        # charged for is written in lower case, like "seat" or "endpoint".
        words = phrase.split()
        if words and all(w[:1].isupper() for w in words) and len(words) <= 2:
            return ("the phrase is a defined term or a heading rather than a "
                    "unit customers are charged for")
        # A UNIT IS A NOUN PHRASE, NOT A PREPOSITIONAL ONE.
        #
        # MEASURED LIVE on Netskope: an equity-compensation note reading
        # "...the price per share for the total shares withheld..." produced
        # a unit of "share for the total shares withheld", and the question
        # asked what to charge "without losing more share for the total
        # shares withheld than the price gains". A filing is a different
        # register from a pricing page, and "price per X" occurs in it for
        # reasons that have nothing to do with what customers buy.
        #
        # The leading "number/amount/volume of" form is stripped earlier, so
        # a surviving preposition means the capture ran into a clause.
        if re.search(r"(?<![a-z])(for|from|with|by|under|between|against)"
                     r"(?![a-z])", phrase, re.I):
            return ("the phrase runs into a clause, so it names a "
                    "relationship rather than a unit")
    if kind == "BUYER":
        # A BUYER IS A POPULATION, AND ENGLISH NOUN PHRASES ARE HEAD-FINAL.
        #
        # MEASURED LIVE across cohorts A and B (a762b2bf): "define" (Vanta),
        # "saying" (Island), "safety managers prioritize" (Motive),
        # "construction industry ecosystem" (Procore), "nuanced dynamics of
        # the trades" (ServiceTitan) all reached the central question as who
        # the company sells to.
        #
        # Every one escaped `_COMPLEMENT_VERBS`, which is a CLOSED LIST of
        # verbs -- and English is not closed. A third patch adding
        # "prioritize", "define" and "say" would fail on the fourth verb.
        # So the test is POSITIVE instead: the head of the phrase must look
        # like a population, and no word in it may carry a verb inflection.
        words = phrase.split()
        head = _head_noun(phrase)
        if not _is_population(head):
            return ("the phrase does not end in a population of people or "
                    "organisations, so it names something other than a buyer")
        # MEASURED LIVE on ServiceTitan (591041b0): "experience their own
        # rapid technological changes" ends in a plural noun and carries no
        # verb inflection, so both rules above let it through and the
        # central question read "without losing more customer count among
        # experience their own rapid technological changes". A population
        # this company sells to is NAMED, never referred back to.
        if any(w.lower() in _POSSESSIVE for w in words):
            return ("the phrase points back at a subject named elsewhere, "
                    "so the capture ran past the people it names")
        if any(_is_inflected_verb(w.lower()) for w in words):
            return ("the phrase carries a verb, so the capture ran past the "
                    "people it names")
    if kind == "BUYER":
        # A BUYER IS A WHO, NOT A WHAT.
        #
        # MEASURED: Veza's "built for enterprise-wide access governance
        # across all users" filled the buyer slot with a CAPABILITY that
        # happens to end in a person-word. English noun phrases are
        # head-final, so the head is found by cutting the trailing
        # prepositional phrase -- which leaves "enterprise-wide access
        # governance", whose head is an abstract noun and not a population.
        # The same cut improves a good phrase too: "mid-market enterprises
        # across north america" becomes "mid-market enterprises".
        head_words = phrase.split()
        if head_words and re.search(
                r"(?:ance|ence|ment|tion|sion|ity|ness|ing|ship|age)$",
                head_words[-1], re.I):
            return ("the phrase names an activity rather than the people or "
                    "organisations that buy")
        original = phrase.split()
        if original and all(w[:1].isupper() for w in original) \
                and len(original) <= 2:
            return ("the phrase is written like a heading or a slogan rather "
                    "than like somebody a company sells to")
        # "center" is what is left of "Help center Find the help you need"
        # once the complement verb is cut. A buyer named in one singular word
        # is nearly always the tail of a heading; a real one-word buyer is a
        # plural population ("fleets", "developers", "hospitals").
        if len(original) > 1 and original[0].lower() in _PARTITIVE \
                and original[1].lower() == "of":
            return ("the phrase points back at something named elsewhere "
                    "rather than naming who buys")
        if len(original) == 1 and not original[0].lower().endswith("s"):
            return ("a buyer named in one singular word is a fragment, not a "
                    "population this company sells to")
    if kind == "BUYER" and not any(
            w not in _GENERIC_BUYER and w not in _FILLER
            and w not in _QUANTIFIER for w in words):
        return ("the phrase names buyers in general rather than this "
                "company's buyer")
    if any(ch.isdigit() for ch in phrase):
        return "the phrase carries a figure, so it is a measurement not a unit"
    # The company's own name is an identity, not a decision variable.
    name = " ".join(str(company or "").lower().split())
    if name and (name in phrase.lower() or phrase.lower() in name):
        return "the phrase is the company's own name"
    if not re.fullmatch(r"[A-Za-z][A-Za-z’'\-\s/&\.]*", phrase):
        return "the phrase carries characters a noun phrase does not"
    return ""


def _subject_patterns(company: str):
    """Regexes anchored on THIS COMPANY as the grammatical subject."""
    # MATCHING RUNS ON LOWERCASED TEXT, so the name must be lowercased too.
    # Left capitalised, `Snyk helps development teams` never matched and the
    # company-as-subject rule -- the whole discipline of this module -- was
    # dead for every company, silently, with first person still working.
    name = re.escape(" ".join(str(company or "").lower().split()))
    # THE WHOLE NAME, not its first token. Keeping only the head meant
    # `arctic` had to be followed immediately by the verb, so every
    # multi-word company failed the subject rule while single-word ones
    # passed -- a silent split in behaviour along name length. Internal
    # whitespace is relaxed because published text hyphenates and wraps.
    if not name:
        return _FIRST_PERSON
    full = name.replace(r"\ ", " ")
    full = r"\s+".join(re.escape(part) for part in full.split())
    return rf"(?:{_FIRST_PERSON}|{full}(?:’s|'s)?)"


# --- billing unit -----------------------------------------------------------

def _billing_unit(text: str, company: str) -> Slot:
    """What one unit of this company's revenue is counted in.

    A pricing decision measured in ingested terabytes is a different decision
    from one measured in developer seats, and no class table can know which.
    """
    subj = _subject_patterns(company)
    rules = (
        ("per-unit-pricing",
         rf"\bpriced?\s+per\s+([a-z][a-z\-\s/&’']{{2,70}})", False),
        ("charged-per",
         rf"\b(?:charged|billed|charge|bill)\s+per\s+"
         rf"([a-z][a-z\-\s/&’']{{2,70}})", False),
        ("per-X-pricing",
         rf"\bper[\s\-]([a-z][a-z\-\s/&’']{{2,40}})\s+pricing\b", False),
        ("X-based-pricing",
         rf"\b([a-z][a-z\-\s/&’']{{2,40}})[\s\-]based\s+pricing\b", False),
        ("we-charge-for",
         rf"\b{subj}\s+(?:charge|bill|price)\s+(?:customers\s+)?"
         rf"(?:for|by|on)\s+([a-z][a-z\-\s/&’']{{2,70}})", False),
        ("pricing-is-based-on",
         rf"\bpricing\s+is\s+based\s+on\s+"
         rf"(?:the\s+)?([a-z][a-z\-\s/&’']{{2,70}})", False),
    )
    return _first_match("BILLING_UNIT", text, company, rules,
                        missing=("this company does not state publicly what a "
                                 "unit of its revenue is counted in"),
                        bad_values=_PER_TIME)


# --- buyer ------------------------------------------------------------------

def _buyer(text: str, company: str) -> Slot:
    """Who decides to pay. Not who benefits, and not who is mentioned."""
    subj = _subject_patterns(company)
    # A RULE THAT DOES NOT NAME THE COMPANY CAN READ ANY SENTENCE ON THE
    # PAGE. MEASURED LIVE on Arctic Wolf (a9ca9f8c): "used by the rest of the
    # group" matched inside a THREAT-RESEARCH POST about the Karakurt and
    # Conti ransomware gangs, and the product told a reader that "rest of the
    # group" is who Arctic Wolf sells to -- and marked the reading GROUNDED
    # on it. That is a fabricated ground, which is worse than NAME_ONLY,
    # because it claims a company-specificity it does not have.
    #
    # It is the same subject/object confusion the positive controls were
    # diagnosed with, reappearing through the three rules that did not carry
    # the subject anchor. `needs_subject` makes the anchor a property of each
    # rule rather than something a reader has to notice is missing.
    rules = (
        ("built-for",
         rf"\b(?:built|designed|made|purpose-built)\s+for\s+"
         rf"([a-z][a-z\-\s/&’']{{3,70}})", True),
        ("we-help",
         rf"\b{subj}\s+(?:help|helps|serve|serves|enable|enables)\s+"
         rf"([a-z][a-z\-\s/&’']{{3,70}})", False),
        ("our-customers-are",
         rf"\bour\s+(?:customers|clients|users)\s+(?:are|include)\s+"
         rf"([a-z][a-z\-\s/&’']{{3,70}})", False),
        ("used-by",
         rf"\b(?:used|trusted|chosen)\s+by\s+"
         rf"([a-z][a-z\-\s/&’']{{3,70}})", True),
        ("built-for-how",
         rf"\b(?:built|designed|made)\s+for\s+how\s+"
         rf"([a-z][a-z\-\s/&’']{{3,70}})", True),
        ("we-sell-to",
         rf"\b{subj}\s+(?:sell|sells|market|markets)\s+to\s+"
         rf"([a-z][a-z\-\s/&’']{{3,70}})", False),
    )
    return _first_match("BUYER", text, company, rules,
                        missing=("this company does not state publicly who "
                                 "decides to buy it"))


# --- dependency -------------------------------------------------------------

def _dependencies(text: str, company: str, limit: int = 3):
    """What delivery rests on that the company does not own.

    The subject rule matters most here: a page that says "supply chains are
    fragile" is not a company saying it depends on one.
    """
    subj = _subject_patterns(company)
    rules = (
        ("we-rely-on",
         rf"\b{subj}\s+(?:rely|relies|depend|depends)\s+(?:up)?on\s+"
         rf"(?:the\s+)?([a-z][a-z\-\s/&’']{{3,70}})"),
        ("we-are-dependent-on",
         rf"\b{subj}\s+(?:are|is)\s+dependent\s+(?:up)?on\s+"
         rf"(?:the\s+)?([a-z][a-z\-\s/&’']{{3,70}})"),
        ("platform-runs-on",
         rf"\b{subj}(?:’s|'s)?\s+[a-z]+\s+"
         rf"(?:runs|is\s+hosted|is\s+built)\s+on\s+"
         rf"([a-z][a-z\-\s/&’']{{3,70}})"),
    )
    found, seen = [], set()
    for sentence in _sentences(text):
        if _is_furniture(sentence) or not _is_prose(sentence):
            continue
        low = sentence.lower()
        for label, rule in rules:
            for match in re.finditer(rule, low):
                phrase = _clean_phrase(
                    sentence[match.start(1):match.end(1)])
                if _acceptable(phrase, company, "DEPENDENCY"):
                    phrase = _narrow(phrase)
                    if _acceptable(phrase, company, "DEPENDENCY"):
                        continue
                if phrase.lower() in seen:
                    continue
                seen.add(phrase.lower())
                found.append(Slot(kind="DEPENDENCY", value=phrase,
                                  state=ESTABLISHED, quote=sentence[:300],
                                  pattern=label))
                if len(found) >= limit:
                    return tuple(found)
    return tuple(found)


def _first_match(kind: str, text: str, company: str, rules,
                 *, missing: str, bad_values=frozenset()) -> Slot:
    """First phrase clearing every gate, or an explicit refusal.

    A rule marked `needs_subject` may only read a sentence in which THIS
    COMPANY names itself or speaks in the first person. Without that,
    "used by ..." reads any sentence on the site -- including a security
    vendor's threat research about somebody else's tooling.
    """
    rejected = ""
    subject = re.compile(_subject_patterns(company))
    for sentence in _sentences(text):
        if _is_furniture(sentence) or not _is_prose(sentence):
            continue
        low = sentence.lower()
        names_itself = bool(subject.search(low))
        for label, rule, needs_subject in rules:
            if needs_subject and not names_itself:
                rejected = rejected or (
                    "the sentence it was found in does not mention this "
                    "company, so it describes somebody else")
                continue
            for match in re.finditer(rule, low):
                phrase = _clean_phrase(
                    sentence[match.start(1):match.end(1)])
                if phrase.lower() in bad_values:
                    continue
                why_not = _acceptable(phrase, company, kind)
                if why_not:
                    # An over-long capture usually names the thing and then
                    # goes on; its first conjunct is still a quoted fact.
                    phrase = _narrow(phrase)
                    why_not = _acceptable(phrase, company, kind)
                if why_not:
                    rejected = rejected or why_not
                    continue
                return Slot(kind=kind, value=phrase, state=ESTABLISHED,
                            quote=sentence[:300], pattern=label)
    return Slot(kind=kind, state=NOT_ESTABLISHED,
                reason=(f"{missing}; the closest candidate was rejected "
                        f"because {rejected}" if rejected else missing))


def build(*, company: str, evidence_text: str = "",
          published_text: str = "") -> DecisionObject:
    """Everything this company said about its own decision variables.

    NEVER RAISES. A slot that cannot be established is `NOT_ESTABLISHED` with
    a reason, which is a usable answer; an exception would take the decision
    down with it.
    """
    try:
        body = " ".join(t for t in (published_text, evidence_text) if t)
        body = body[:400_000]
        name = str(company or "").strip()
        return DecisionObject(
            company=name,
            billing_unit=_billing_unit(body, name),
            buyer=_buyer(body, name),
            dependencies=_dependencies(body, name),
            text_chars=len(body))
    except Exception:                                        # noqa: BLE001
        return DecisionObject(company=str(company or ""))

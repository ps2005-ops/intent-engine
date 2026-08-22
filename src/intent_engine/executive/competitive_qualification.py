"""Is this named entity an economic alternative, or merely a name in the way?

THE DEFECT THIS CLOSES, MEASURED ON THREE LIVE BATCH-A COMPANIES.

`competitor_finder` gates the SENTENCE — `names_a_contest` asks whether a
contest is being described — and nothing asks what the NAME is. Three
introductions shipped with it:

    Meta        "contested most directly by S&P"
    Walmart     "contested most directly by ... Medicare Part D"
    Caterpillar "contested most directly by Alstom SA, America Leasing"

Re-run offline against the same filings, the mechanism is not a missing
stoplist. It is three separable grammatical failures.

1. THE "SENTENCE" IS A LIST. Meta's evidence blob is 2,262 characters and
   fifteen bullets. "S&P" sits at character 1,670, inside

       "the inclusion, exclusion, or deletion of our stock from any trading
        indices, such as the S&P 500 Index"

   and the word "competitors" that admitted the whole blob is at character
   1,400, in a DIFFERENT bullet. The excerpt quoted to the reader was
   characters 0-400 — a third bullet, about income tax. One blob, three
   unrelated clauses, and the page presented them as one claim. Walmart is
   the same shape: 2,677 characters, seventeen semicolons, "Medicare Part D"
   inside "changes in the scope of or the elimination of Medicare Part D or
   Medicaid drug programs", and the contest cue five clauses earlier.

2. THE CONTEST HAS AN OWNER, AND IT IS NOT ALWAYS THE COMPANY. Caterpillar's
   filing says

       "Cat Financial's competitors include Wells Fargo Equipment Finance
        Inc., Banc of America Leasing & Capital LLC, BNP Paribas Leasing
        Solutions Limited, ..."

   Those firms contest CAT FINANCIAL — a captive lender — for a customer's
   financing, not Caterpillar for a customer's excavator. The claim belongs
   to whoever the sentence says it belongs to, and reading the possessor is
   what separates six financiers from Komatsu and Deere. No name list can.

3. SELECTION WAS ALPHABETICAL. Caterpillar's filing names forty-three firms,
   almost all of them correct — Komatsu, Deere, Cummins, Liebherr, Sandvik,
   Volvo CE. `find_competitors` sorted by `(relevance, name)` and took four:
   Alstom, America Leasing, BNP Paribas, Baker Hughes. The company's most
   direct rivals were present in the evidence and lost to the alphabet.

WHY THIS IS NOT ANOTHER STOPLIST. The module's own history records three
consecutive live rounds in which word-level filters were defeated within a
deploy, because filing headings are built from the same vocabulary a stoplist
is made of. Every discriminator here is positional or grammatical: which
clause the name is in, what noun governs it, and who owns the verb. A rule
keyed on "S&P" would have left Medicare Part D and America Leasing exactly
where they were, and would have been defeated by the next filing.

WHAT IS *NOT* DONE HERE. Nothing is deleted. §6: an index, a payer programme
and a captive lender's rivals are real facts about the company, and the
answer to putting them in the wrong section is to put them in the right one.
Every candidate leaves here with a state, and the states that are not
competitive carry the heading they belong under.
"""
from __future__ import annotations

import dataclasses
import re
from typing import List, Optional, Sequence, Tuple

CONTRACT = "competitive_qualification.v1"

# --- WHAT IS THIS THING? (§4) ----------------------------------------------
#
# Deliberately separate from the relationship below. "S&P Global" is an
# ORGANISATION and its relationship to Meta is INDEX_BENCHMARK; a bank is an
# ORGANISATION and its relationship to Caterpillar is FINANCIER. Collapsing
# the two questions is what let "is a company" imply "is a competitor".
ENTITY_COMPANY = "COMPANY"
ENTITY_SEGMENT = "SEGMENT_OR_SUBSIDIARY"
ENTITY_FINANCIER = "FINANCIAL_INSTITUTION"
ENTITY_PROGRAM = "PROGRAM_OR_POLICY"
ENTITY_INDEX_PROVIDER = "INDEX_OR_BENCHMARK_PROVIDER"
ENTITY_REGULATOR = "REGULATOR_OR_AUTHORITY"
ENTITY_CATEGORY = "CATEGORY_OR_PRACTICE"
ENTITY_UNKNOWN = "UNKNOWN"

ENTITY_TYPES = (ENTITY_COMPANY, ENTITY_SEGMENT, ENTITY_FINANCIER,
                ENTITY_PROGRAM, ENTITY_INDEX_PROVIDER, ENTITY_REGULATOR,
                ENTITY_CATEGORY, ENTITY_UNKNOWN)

# --- HOW DOES IT RELATE TO THE FOCAL COMPANY? (§5) -------------------------
#
# The vocabulary of `executive.relationship` extended, not replaced: that
# module classifies a THIRD PARTY'S filing about the subject, this one
# classifies a name inside the SUBJECT'S OWN filing, and a reader who is told
# "supplier" by one and "SUPPLIER" by the other should see one word.
COMPETITOR = "COMPETITOR"
SUBSTITUTE = "SUBSTITUTE"
ADJACENT_THREAT = "ADJACENT_THREAT"
CUSTOMER = "CUSTOMER"
SUPPLIER = "SUPPLIER"
PARTNER = "PARTNER"
VENDOR = "VENDOR"
FINANCIER = "FINANCIER"
DISTRIBUTOR = "DISTRIBUTOR"
REGULATOR = "REGULATOR"
PAYER = "PAYER"
INDEX_BENCHMARK = "INDEX_BENCHMARK"
COMPLEMENT = "COMPLEMENT"
LITIGATION = "LITIGATION"
INVESTOR = "INVESTOR"
UNKNOWN = "UNKNOWN"

RELATIONSHIP_TYPES = (COMPETITOR, SUBSTITUTE, ADJACENT_THREAT, CUSTOMER,
                      SUPPLIER, PARTNER, VENDOR, FINANCIER, DISTRIBUTOR,
                      REGULATOR, PAYER, INDEX_BENCHMARK, COMPLEMENT,
                      LITIGATION, INVESTOR, UNKNOWN)

# --- THE QUALIFICATION STATE (§3) ------------------------------------------
DIRECT_COMPETITOR = "DIRECT_COMPETITOR"
SUBSTITUTE_STATE = "SUBSTITUTE"
ADJACENT_THREAT_STATE = "ADJACENT_THREAT"
COMPLEMENT_STATE = "COMPLEMENT"
CUSTOMER_STATE = "CUSTOMER"
SUPPLIER_STATE = "SUPPLIER"
PARTNER_STATE = "PARTNER"
FINANCIER_STATE = "FINANCIER"
REGULATOR_STATE = "REGULATOR"
INDEX_OR_BENCHMARK = "INDEX_OR_BENCHMARK"
PROGRAM_OR_POLICY = "PROGRAM_OR_POLICY"
CATEGORY_OR_PRACTICE_STATE = "CATEGORY_OR_PRACTICE"
INCIDENTALLY_NAMED = "INCIDENTALLY_NAMED"
UNKNOWN_STATE = "UNKNOWN"

QUALIFICATION_STATES = (
    DIRECT_COMPETITOR, SUBSTITUTE_STATE, ADJACENT_THREAT_STATE,
    COMPLEMENT_STATE, CUSTOMER_STATE, SUPPLIER_STATE, PARTNER_STATE,
    FINANCIER_STATE, REGULATOR_STATE, INDEX_OR_BENCHMARK, PROGRAM_OR_POLICY,
    CATEGORY_OR_PRACTICE_STATE, INCIDENTALLY_NAMED, UNKNOWN_STATE)

#: §3. THE ONLY THREE THAT MAY REACH A COMPETITIVE CLAIM. Everything else is
#: still published — under the heading it belongs to, never as a rival.
MAY_CONTEST = (DIRECT_COMPETITOR, SUBSTITUTE_STATE, ADJACENT_THREAT_STATE)

#: §3. And only these two may fill "contested most directly by": an adjacent
#: threat is real and is not direct, and the sentence has to say which.
MAY_CONTEST_DIRECTLY = (DIRECT_COMPETITOR, SUBSTITUTE_STATE)

#: §8. THE SENTENCE CONTRACT. Customer-facing language must match the state,
#: because "contested most directly by" is a strong claim and a state that
#: does not support it must not borrow its words.
WORDING = {
    DIRECT_COMPETITOR: "contested directly by",
    SUBSTITUTE_STATE: "customers can substitute",
    ADJACENT_THREAT_STATE: "an adjacent threat comes from",
    COMPLEMENT_STATE: "sold alongside, not instead of",
    CUSTOMER_STATE: "buys from this company",
    SUPPLIER_STATE: "supplies this company",
    PARTNER_STATE: "partners with this company",
    FINANCIER_STATE: "finances the customer's purchase",
    REGULATOR_STATE: "sets the terms this business operates under",
    INDEX_OR_BENCHMARK: "is how this company's shares are measured",
    PROGRAM_OR_POLICY: "is a programme whose terms move this business",
    CATEGORY_OR_PRACTICE_STATE: ("is an activity this business is held to, "
                                 "not a party it competes with"),
    INCIDENTALLY_NAMED: "appears in the filing without a stated relationship",
    UNKNOWN_STATE: "has an unestablished relationship",
}

#: §6. WHERE A NON-COMPETITOR BELONGS. Suppressing these would make the
#: product quieter; the point is to make it smarter, so each state names the
#: section of the analysis that should carry it.
ROUTING = {
    FINANCIER_STATE: "Customer financing and purchase enablement",
    REGULATOR_STATE: "Regulatory exposure",
    PROGRAM_OR_POLICY: "Regulation and payer economics",
    INDEX_OR_BENCHMARK: "Market, index and capital-market context",
    CATEGORY_OR_PRACTICE_STATE: "Regulation and operating practice",
    CUSTOMER_STATE: "Demand concentration",
    SUPPLIER_STATE: "Supply and input dependence",
    PARTNER_STATE: "Partnerships and channel",
    COMPLEMENT_STATE: "Complements and ecosystem",
}


class QualificationRefused(ValueError):
    """A qualification that cannot state its own basis is not a finding."""


@dataclasses.dataclass(frozen=True)
class CompetitiveQualification:
    """One candidate, and whether a customer could choose it instead."""
    candidate: str
    entity_type: str
    relationship_type: str
    focal_need: str
    substitution_mechanism: str
    customer_choice_possible: bool
    evidence_basis: str
    confidence: str                      # HIGH | MEDIUM | LOW
    qualification_state: str
    reason: str
    #: Who the filing says the contest belongs to. "" means the subject.
    contest_owner: str = ""

    def __post_init__(self):
        if self.entity_type not in ENTITY_TYPES:
            raise QualificationRefused(f"unknown entity_type "
                                       f"{self.entity_type!r}")
        if self.relationship_type not in RELATIONSHIP_TYPES:
            raise QualificationRefused(f"unknown relationship_type "
                                       f"{self.relationship_type!r}")
        if self.qualification_state not in QUALIFICATION_STATES:
            raise QualificationRefused(f"unknown qualification_state "
                                       f"{self.qualification_state!r}")
        # §7. A DIRECT COMPETITOR CLAIM REQUIRES A CHOICE MECHANISM. The
        # whole defect is a name reaching this state with nothing behind it,
        # so the state cannot be constructed without the mechanism.
        if self.qualification_state in MAY_CONTEST:
            if not self.customer_choice_possible:
                raise QualificationRefused(
                    f"{self.qualification_state} without a customer choice")
            if not (self.substitution_mechanism or "").strip():
                raise QualificationRefused(
                    f"{self.qualification_state} without a substitution "
                    f"mechanism")
        if not (self.reason or "").strip():
            raise QualificationRefused("a qualification must state its basis")

    @property
    def may_contest(self) -> bool:
        return self.qualification_state in MAY_CONTEST

    @property
    def may_contest_directly(self) -> bool:
        return self.qualification_state in MAY_CONTEST_DIRECTLY

    @property
    def section(self) -> str:
        """§6. The heading this belongs under when it is not a rival."""
        return ROUTING.get(self.qualification_state, "")

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# 1. CLAUSES. A filing "sentence" is frequently a list.
# ---------------------------------------------------------------------------

#: What ends a clause inside a filing list: a semicolon, a bullet, a newline,
#: or a full stop. NOT a comma — "Wabtec Corp, Greenbrier Companies, Inc.,
#: Voestalpine AG" is one enumeration and splitting it would strand every
#: name after the first away from the verb that governs them all.
_CLAUSE_BREAK = re.compile(r"\s*(?:[;•]|•|\n|(?<=[.!?])\s(?=[A-Z]))\s*")

#: A clause that introduces a list: the names come AFTER it, in clauses of
#: their own, and they are covered by it. Bounded to the immediately
#: preceding clause on purpose — Meta's contest cue was five bullets away
#: from "S&P" and an unbounded inheritance is the defect itself.
_INTRODUCES_A_LIST = re.compile(
    r"(?:\binclude|\bincluding|\bsuch as|\bare|\bcomprise\w*|:)\s*$", re.I)


#: A NEWLINE INSIDE A SENTENCE IS A WRAP, NOT A CLAUSE. Filing text arrives
#: one block per line, so a newline usually IS a boundary — but a paragraph
#: soft-wrapped mid-sentence would otherwise be cut in half, and "We compete
#: with Databricks Inc. and Snowflake Inc. for the / same customers" would
#: quote a citation that stops before it says anything. A newline sitting
#: between an unterminated word and a lower-case continuation is a wrap.
_SOFT_WRAP = re.compile(r"(?<=[^\s.;:!?•])[ \t]*\n[ \t]*(?=[a-z(])")


def clauses(text: str) -> List[str]:
    """The clauses of one filing 'sentence', in order."""
    joined = _SOFT_WRAP.sub(" ", text or "")
    return [c.strip() for c in _CLAUSE_BREAK.split(joined) if c.strip()]


def governing_clause(text: str, name: str) -> str:
    """The clause the name actually sits in, plus a list header if it has one.

    THE EXCERPT MUST BE THE SPAN THAT MAKES THE CLAIM. Quoting characters
    0-400 of a fifteen-bullet blob put a sentence about income tax under a
    competitor called S&P.
    """
    parts = clauses(text)
    lowered = (name or "").lower()
    if not lowered:
        return ""
    for i, clause in enumerate(parts):
        if lowered in clause.lower():
            if i and _INTRODUCES_A_LIST.search(parts[i - 1]):
                return f"{parts[i - 1]} {clause}".strip()
            return clause
    return ""


# ---------------------------------------------------------------------------
# 2. WHO OWNS THE CONTEST.
# ---------------------------------------------------------------------------

_COMPETITION_WORD = re.compile(
    r"\b(competitors?|competition|competes?|competing|competitive)\b", re.I)

#: "X's competitors", "the competitors of X". The possessor is what decides
#: whose market is being described.
_POSSESSIVE = re.compile(
    r"([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,3})"
    # "Cat Financial’s competitors" AND "Orion Robotics’ competitors": a name
    # already ending in s takes the bare apostrophe, and requiring the s
    # silently exempted every such owner.
    r"[’']s?\s+(?:principal\s+|primary\s+|global\s+|main\s+|key\s+)?"
    r"(?:competitors?|competition)", re.I)

_FIRST_PERSON = re.compile(
    r"\b(our|we|us|the\s+Company|the\s+Corporation|its)\b", re.I)


#: Legal form and filler, which carry no identity.
_NAME_NOISE = frozenset({"inc", "corp", "corporation", "company", "co", "ltd",
                         "limited", "plc", "holdings", "holding", "group",
                         "the", "and", "sa", "nv", "ag", "llc", "lp"})


def _subject_tokens(subject: str) -> set:
    generic = {"inc", "corp", "corporation", "company", "co", "ltd",
               "limited", "plc", "holdings", "holding", "group", "the",
               "and", "sa", "nv", "ag", "llc", "lp", "platforms"}
    return {t.lower() for t in re.split(r"\W+", subject or "")
            if t and t.lower() not in generic and len(t) > 2}


def contest_owner(clause: str, subject: str) -> str:
    """Whose competitors these are. "" means the subject's own.

    MEASURED: "Cat Financial's competitors include Wells Fargo Equipment
    Finance Inc., Banc of America Leasing & Capital LLC, ..." — six financial
    institutions that contest Caterpillar's CAPTIVE LENDER for a customer's
    financing. They are real competitors of a segment and they are not what
    contests Caterpillar most directly, and the only thing in the text that
    says so is the possessor of the verb.
    """
    match = _POSSESSIVE.search(clause or "")
    if not match:
        return ""
    owner = match.group(1).strip()
    if _FIRST_PERSON.fullmatch(owner.strip()):
        return ""
    # SUBSET, NOT INTERSECTION. "Caterpillar" inside "Caterpillar Inc." is
    # the company writing its own name; "Orion Robotics" beside "Orion
    # Industrial Corp" is a different entity that happens to share a word,
    # and an intersection test calls both the same company — which is the
    # shared-leading-word collision this codebase has made before.
    mine = _subject_tokens(subject)
    theirs = {t.lower() for t in re.split(r"\W+", owner) if t} - _NAME_NOISE
    if theirs and (theirs <= mine or mine <= theirs):
        return ""                       # the company, written out in full
    return owner


# ---------------------------------------------------------------------------
# 3. WHAT THE THING IS. Governing nouns, never a name list.
# ---------------------------------------------------------------------------

#: A measure, not a market. Read from the noun that governs the name within a
#: short window — "the S&P 500 Index", "the Dow Jones Industrial Average",
#: "our peer group". A company that PUBLISHES indices is still a company; it
#: is the apposition that makes this one a benchmark.
_INDEX_NOUN = re.compile(
    r"\b(index|indices|benchmark|benchmarks|composite|average|peer\s+group|"
    r"stock\s+market)\b", re.I)

#: A programme, a plan or a statute. Same shape: the governing noun decides.
_PROGRAM_NOUN = re.compile(
    r"\b(programs?|programmes?|plans?|act|acts|statutes?|regulations?|rules?|"
    r"schemes?|benefits?|coverage|reimbursement|formular(?:y|ies)|mandates?|"
    r"subsidies|subsidy|tariffs?|entitlements?|legislation)\b", re.I)

_REGULATOR_NOUN = re.compile(
    r"\b(commission|authority|agency|department|ministry|bureau|"
    r"administration|regulators?|tribunal|court)\b", re.I)

#: A financing head noun, in the candidate's own name or in the apposition
#: that introduces it. This does not by itself demote anything — a bank
#: competing with a bank is a competitor — it records what the entity IS so
#: the ROUTING can be right (§4), and the demotion below is decided by
#: whether the SUBJECT sells financing at all.
_FINANCE_HEAD = re.compile(
    r"\b(leasing|capital|credit|finance|finances|financing|financial|bancorp|"
    r"banking|lending|factoring|mortgage)\b", re.I)

#: §7. THE ONLY MODELS WHOSE OWN FOCAL NEED IS FINANCING. For every other
#: model a lender contests the customer's FINANCING decision, not the
#: purchase decision, and calling it a direct rival tells a chief executive
#: to price against a bank.
#:
#: MEASURED: Caterpillar's filing names six lenders — three under "Cat
#: Financial's competitors include", three as "financial subsidiaries" of
#: the manufacturers that compete with it — and four of them reached the
#: deployed introduction. Keyed on the business model, never on the company
#: (§43): a bank's rivals ARE banks, and this must not take them away.
_FINANCING_MODELS = frozenset({"BALANCE_SHEET_OR_NETWORK", "BANK",
                               "INSURANCE"})

_SEGMENT_HEAD = re.compile(
    r"\b(segment|division|subsidiar(?:y|ies)|business\s+unit)\b", re.I)

#: How far from the name a governing noun still governs it. An apposition
#: ("the S&P 500 Index") is adjacent; a noun six clauses away is not.
_GOVERNS_WITHIN = 48


def _near(clause: str, name: str, pattern: re.Pattern) -> str:
    """Does `pattern` govern `name` — that is, sit right beside it?"""
    lowered, low_name = clause.lower(), (name or "").lower()
    at = lowered.find(low_name)
    if at < 0:
        return ""
    left = max(0, at - _GOVERNS_WITHIN)
    right = min(len(clause), at + len(low_name) + _GOVERNS_WITHIN)
    match = pattern.search(clause[left:right])
    return match.group(0) if match else ""


# --- IS THIS A NAME AT ALL, OR A HEADING? (§10) -----------------------------
#
# MEASURED LIVE on cb9e6b7, Goldman Sachs, on the introduction a customer
# reads:
#
#     "contested directly by Banking Supervision and Compensation Practices"
#
# That is an Item heading out of the 10-K's regulatory section. It reached
# the page because every discriminator above reads the CLAUSE, and when the
# clause carries no regulatory cue the name's own words decide -- so
# "Banking Supervision and Compensation Practices" was typed
# FINANCIAL_INSTITUTION on the strength of the word "Banking", and "Risk
# Management and Internal Controls" was typed COMPANY on the strength of
# nothing at all.
#
# THIS IS MORPHOLOGY, NOT ANOTHER STOPLIST. The module's history records
# three live rounds in which entity stoplists were defeated inside a deploy,
# because headings are built from the same vocabulary as the list. A rule
# about word FORM is different in kind and does not need maintaining: English
# process and abstract nouns end in a small closed set of suffixes, and a
# phrase whose content words are ALL of that form names an activity, not an
# actor. "Compensation" and "Supervision" cannot be sued, sell anything or
# take a customer.
#
# A corporate designator settles it the other way immediately: "Wells Fargo
# Equipment Finance Inc." is a firm whatever its nouns look like.
_ABSTRACT_SUFFIX = re.compile(
    r"(?:tion|sion|ment|ance|ence|ity|ing|ship|ism|ology|ance)$", re.I)
#: Plural process heads that carry no suffix marker but are never firms.
_PROCESS_HEAD = frozenset({
    "practices", "controls", "standards", "requirements", "procedures",
    "policies", "guidelines", "matters", "activities", "rules",
    "obligations", "disclosures", "considerations", "measures", "safeguards",
})
_DESIGNATOR = re.compile(
    r"\b(?:inc|corp|corporation|co|company|ltd|limited|llc|lp|llp|plc|"
    r"ag|sa|nv|bv|se|oyj|ab|as|kk|gmbh|holdings|group|bank|partners)\b\.?",
    re.I)
_CONNECTOR = frozenset({"and", "or", "of", "the", "for", "in", "on", "to",
                        "a", "an", "&"})


def names_an_activity(name: str) -> bool:
    """True when this phrase names a practice rather than an actor.

    Conservative by construction: a corporate designator, or fewer than half
    the content words being process nouns, and it is left alone. Refusing a
    real rival is worse than the heading it was meant to remove.
    """
    text = str(name or "").strip()
    if not text or _DESIGNATOR.search(text):
        return False
    words = [w for w in re.findall(r"[A-Za-z&']+", text)
             if w.lower() not in _CONNECTOR]
    if len(words) < 2:
        return False
    return _abstract_share(words) * 2 >= len(words)


#: A SUFFIX IS ONLY A SUFFIX ON A LONG ENOUGH WORD.
#:
#: "Li Ning" is NIKE's rival and appears on its live introduction. "Ning"
#: ends in -ing, and with "Li" too short to count the phrase read as 2-of-2
#: abstract and the real competitor was refused. A gerund that names a
#: business activity -- Banking, Reporting, Underwriting, Manufacturing --
#: is long; a short syllable that happens to end the same way is a name.
_MIN_ABSTRACT = 6
_MIN_GERUND = 7


def _abstract_share(words) -> int:
    found = 0
    for word in words:
        low = word.lower()
        if low in _PROCESS_HEAD:
            found += 1
            continue
        match = _ABSTRACT_SUFFIX.search(word)
        if not match:
            continue
        floor = _MIN_GERUND if low.endswith("ing") else _MIN_ABSTRACT
        if len(word) >= floor:
            found += 1
    return found


def entity_type_of(name: str, clause: str) -> Tuple[str, str]:
    """WHAT IS THIS THING? Returns (entity_type, the words that decided it)."""
    # ASKED FIRST, because every test below reads either the clause or the
    # name's vocabulary, and a heading defeats both: it sits in the clause
    # like a name and is built from the same words.
    if names_an_activity(name):
        return ENTITY_CATEGORY, "names an activity, not an actor"
    governing_index = _near(clause, name, _INDEX_NOUN)
    if governing_index:
        return ENTITY_INDEX_PROVIDER, governing_index
    governing_program = _near(clause, name, _PROGRAM_NOUN)
    if governing_program:
        return ENTITY_PROGRAM, governing_program
    in_name_regulator = _REGULATOR_NOUN.search(name or "")
    if in_name_regulator or _near(clause, name, _REGULATOR_NOUN):
        return ENTITY_REGULATOR, (in_name_regulator.group(0)
                                  if in_name_regulator
                                  else _near(clause, name, _REGULATOR_NOUN))
    finance = _FINANCE_HEAD.search(name or "") or None
    if finance:
        return ENTITY_FINANCIER, finance.group(0)
    # "…also own FINANCIAL SUBSIDIARIES, such as John Deere Capital
    # Corporation, Komatsu Financial L.P., …": the apposition says what the
    # list is made of, and the list members need not each wear the word.
    governing_finance = _near(clause, name, _FINANCE_HEAD)
    if governing_finance:
        return ENTITY_FINANCIER, governing_finance
    if _near(clause, name, _SEGMENT_HEAD):
        return ENTITY_SEGMENT, _near(clause, name, _SEGMENT_HEAD)
    return ENTITY_COMPANY, ""


# ---------------------------------------------------------------------------
# 4. THE CHOICE MECHANISM (§7).
# ---------------------------------------------------------------------------

_SUBSTITUTION = re.compile(
    r"\b(substitutes?|substitution|alternatives?|instead\s+of|in\s+place\s+of|"
    r"in\s+lieu\s+of|switch\w*\s+to|migrat\w+\s+(?:from|to)|replace\w*)\b",
    re.I)

_CONTEST = re.compile(
    r"\b(competitors?|competition|competes?|competing|rivals?)\b", re.I)

#: The market the contest happens in, when the clause frames one. "In
#: rail-related businesses, our global competitors include ..." names the
#: focal need exactly, and a reader who is told which market a rival contests
#: can check the claim.
_FOCAL_FRAME = re.compile(
    r"\b(?:in|for|within|across)\s+(?:our\s+|the\s+|its\s+)?"
    r"([a-z][a-z\-]*(?:\s+[a-z][a-z\-]*){0,4}\s+"
    r"(?:business(?:es)?|operations?|markets?|segments?|products?|services?))",
    re.I)


def focal_need_of(clause: str, business_model: str = "") -> str:
    """The need a customer would satisfy with either side."""
    match = _FOCAL_FRAME.search(clause or "")
    if match:
        return " ".join(match.group(1).split())
    return (business_model or "").replace("_", " ").lower()


# ---------------------------------------------------------------------------
# 5. THE TEST.
# ---------------------------------------------------------------------------

def qualify(*, candidate: str, evidence: str, subject: str,
            business_model: str = "") -> CompetitiveQualification:
    """Can a customer satisfy a need with this INSTEAD of the subject?

    Never raises. The default is not "competitor" — it is "we did not
    establish this", because the entire measured defect is a name arriving at
    the strongest claim on the page with nothing behind it.
    """
    name = (candidate or "").strip()
    clause = governing_clause(evidence, name) or (evidence or "").strip()
    entity, governing = entity_type_of(name, clause)
    owner = contest_owner(clause, subject)
    focal = focal_need_of(clause, business_model)
    contests = bool(_CONTEST.search(clause))
    substitutes = bool(_SUBSTITUTION.search(clause))

    def refuse(state, relationship, reason, confidence="MEDIUM"):
        return CompetitiveQualification(
            candidate=name, entity_type=entity,
            relationship_type=relationship, focal_need=focal,
            substitution_mechanism="", customer_choice_possible=False,
            evidence_basis=clause[:400], confidence=confidence,
            qualification_state=state, reason=reason, contest_owner=owner)

    if not name:
        return refuse(UNKNOWN_STATE, UNKNOWN, "no candidate name")

    # A MEASURE IS NOT A MARKET. Nobody buys an index instead of advertising.
    # AN ACTIVITY CANNOT BE CHOSEN INSTEAD OF A COMPANY.
    #
    # `entity_type_of` types this correctly as CATEGORY_OR_PRACTICE and
    # NOTHING READ THE ANSWER: there was no arm for it here, so it fell
    # through to the ordinary company path and `may_contest` came back True.
    # MEASURED LIVE on cb9e6b7 AND STILL ON f858d9e after the classifier was
    # fixed -- Goldman's introduction read "contested directly by Banking
    # Supervision and Compensation Practices" on both. A classification that
    # nothing acts on is not a repair.
    #
    # §6: it is not deleted. "Banking Supervision" is a real fact about a
    # bank, and it leaves here with the heading it belongs under.
    if entity == ENTITY_CATEGORY:
        return refuse(CATEGORY_OR_PRACTICE_STATE, UNKNOWN,
                      f"{name!r} names an activity or practice, not an "
                      f"actor a customer could choose instead",
                      confidence="HIGH")
    if entity == ENTITY_INDEX_PROVIDER:
        return refuse(INDEX_OR_BENCHMARK, INDEX_BENCHMARK,
                      f"governed by {governing!r}: this names how the "
                      f"company's shares are measured, not something a "
                      f"customer buys instead", confidence="HIGH")
    # A PROGRAMME SETS TERMS; IT IS NOT ON A SHORTLIST. Its terms can move
    # the business more than any rival, which is why it is routed and not
    # dropped.
    if entity == ENTITY_PROGRAM:
        return refuse(PROGRAM_OR_POLICY, PAYER,
                      f"governed by {governing!r}: a programme or policy "
                      f"whose terms move this business, not an alternative "
                      f"a customer chooses", confidence="HIGH")
    if entity == ENTITY_REGULATOR:
        return refuse(REGULATOR_STATE, REGULATOR,
                      f"governed by {governing!r}: sets the terms this "
                      f"business operates under", confidence="HIGH")
    # §7. A LENDER CONTESTS THE FINANCING, NOT THE PURCHASE — unless
    # financing is what this company sells, in which case a lender is
    # exactly the rival and this must not touch it.
    if entity == ENTITY_FINANCIER and \
            (business_model or "").upper() not in _FINANCING_MODELS:
        return refuse(FINANCIER_STATE, FINANCIER,
                      f"a lender ({governing!r}): it contests how the "
                      f"customer PAYS for the purchase, not which product "
                      f"they buy, and this company does not sell financing",
                      confidence="HIGH")

    # THE CONTEST BELONGS TO SOMEONE ELSE. Still a real competitive fact —
    # about a segment or about another firm — so it is an adjacent threat at
    # most, and it is worded as adjacent.
    if owner:
        if not (contests or substitutes):
            return refuse(INCIDENTALLY_NAMED, UNKNOWN,
                          f"named in {owner}'s clause without a contest")
        mechanism = (f"a customer could choose {name} instead of {owner}, "
                     f"which is part of this company rather than the whole "
                     f"of it — the contest is one segment's, not the "
                     f"company's")
        try:
            return CompetitiveQualification(
                candidate=name, entity_type=entity,
                relationship_type=ADJACENT_THREAT,
                focal_need=focal, substitution_mechanism=mechanism,
                customer_choice_possible=True,
                evidence_basis=clause[:400], confidence="MEDIUM",
                qualification_state=ADJACENT_THREAT_STATE,
                reason=(f"the filing attributes this contest to {owner}, not "
                        f"to {subject}"),
                contest_owner=owner)
        except QualificationRefused:
            return refuse(ADJACENT_THREAT_STATE, ADJACENT_THREAT,
                          f"contest owned by {owner}")

    # THE CLAUSE MUST CARRY THE CONTEST ITSELF. This is the rule that removes
    # S&P and Medicare Part D: their own clauses say nothing about competing,
    # and the cue that admitted them was in a different clause of the same
    # bullet list.
    if not (contests or substitutes):
        return refuse(INCIDENTALLY_NAMED, UNKNOWN,
                      "the clause naming this entity does not say a contest "
                      "exists; the competition language was elsewhere in the "
                      "passage", confidence="HIGH")

    state = SUBSTITUTE_STATE if (substitutes and not contests) \
        else DIRECT_COMPETITOR
    relationship = SUBSTITUTE if state == SUBSTITUTE_STATE else COMPETITOR
    need = focal or "what this company sells"
    mechanism = (f"a customer can meet the same need — {need} — by choosing "
                 f"{name} instead of {subject}, which is what the filing's "
                 f"own competition statement asserts")
    try:
        return CompetitiveQualification(
            candidate=name, entity_type=entity, relationship_type=relationship,
            focal_need=focal, substitution_mechanism=mechanism,
            customer_choice_possible=True, evidence_basis=clause[:400],
            confidence="HIGH", qualification_state=state,
            reason=(f"{subject}'s own filing states the contest in the clause "
                    f"that names it"),
            contest_owner="")
    except QualificationRefused:
        return refuse(UNKNOWN_STATE, UNKNOWN, "could not establish a basis")


# ---------------------------------------------------------------------------
# 6. RANKING (§3 of the measured causes).
# ---------------------------------------------------------------------------

#: Strongest claim first. Alphabetical order put a gold miner's alphabet
#: neighbour ahead of Komatsu in a filing that named Komatsu.
_STATE_RANK = {DIRECT_COMPETITOR: 0, SUBSTITUTE_STATE: 1,
               ADJACENT_THREAT_STATE: 2}
_CONFIDENCE_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def rank(qualifications: Sequence[Tuple[CompetitiveQualification, int]],
         ) -> List[CompetitiveQualification]:
    """Competitive rows first, in the company's own order of mention.

    THE ORDER OF MENTION IS INFORMATION. Caterpillar's filing discusses
    Construction Industries before Financial Products, so first appearance is
    the company's own ranking of its markets. Falling back to the alphabet
    threw that away and was the largest single cause of a wrong direct
    competitor on filings that name their rivals well.
    """
    scored = [(q, i) for q, i in qualifications if q.may_contest]
    scored.sort(key=lambda pair: (
        _STATE_RANK.get(pair[0].qualification_state, 9),
        _CONFIDENCE_RANK.get(pair[0].confidence, 9),
        pair[1],                                   # first appearance
        pair[0].candidate.lower()))                # deterministic tie-break
    return [q for q, _ in scored]


def routed(qualifications: Sequence[CompetitiveQualification]) -> dict:
    """§6. The non-competitors, grouped under the heading they belong to."""
    out: dict = {}
    for q in qualifications:
        if q.may_contest or not q.section:
            continue
        out.setdefault(q.section, []).append(q)
    return out

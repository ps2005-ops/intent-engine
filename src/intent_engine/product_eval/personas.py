"""Who is reading, and under what conditions.

A persona is not a demographic sketch. It is a set of EXPECTATIONS that can be
checked against a report: how long this reader will stay, what they must be
able to answer when they leave, and what makes them stop trusting the thing.

Keeping them in that shape is what stops the evaluation from becoming vibes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Persona:
    key: str
    label: str
    # Seconds of attention before they decide whether to continue.
    patience_s: int
    # Words they will realistically read before deciding.
    word_budget: int
    # Questions they must be able to answer from the layer they land on.
    must_answer: tuple
    # Things that make this reader distrust or abandon the product.
    deal_breakers: tuple = ()
    # Layer this reader should land on: "brief" | "slides" | "full"
    entry_layer: str = "brief"


# The primary product standard says a first-time reader answers ten questions
# in two minutes. Different readers need different subsets FIRST.
Q_WHAT = "what does this company do"
Q_CHANGING = "what appears to be changing"
Q_THESIS = "the most important strategic hypothesis"
Q_WHY = "why it matters"
Q_FOR = "what evidence supports it"
Q_AGAINST = "what evidence weakens it"
Q_DECISION = "what decision it could affect"
Q_NEXT = "what to investigate next"
Q_CONFIDENCE = "how confident to be"
Q_UNKNOWN = "what could not be determined"

PERSONAS = (
    Persona("busy_founder", "busy startup founder", 90, 400,
            (Q_WHAT, Q_THESIS, Q_DECISION),
            ("report longer than the attention budget",
             "thesis not visible without scrolling")),
    Persona("enterprise_exec", "enterprise executive", 120, 500,
            (Q_THESIS, Q_WHY, Q_DECISION, Q_CONFIDENCE),
            ("hedged language with no decision attached",)),
    Persona("sales_leader", "sales leader", 120, 500,
            (Q_WHAT, Q_CHANGING, Q_NEXT),
            ("nothing usable in a customer conversation",)),
    Persona("product_manager", "product manager", 180, 700,
            (Q_WHAT, Q_CHANGING, Q_FOR)),
    Persona("investor", "investor", 180, 700,
            (Q_THESIS, Q_FOR, Q_AGAINST, Q_CONFIDENCE),
            ("confidence unsupported by independent evidence",)),
    Persona("consultant", "consultant", 240, 900,
            (Q_THESIS, Q_FOR, Q_AGAINST, Q_UNKNOWN)),
    Persona("market_analyst", "market analyst", 240, 900,
            (Q_CHANGING, Q_FOR, Q_AGAINST, Q_UNKNOWN)),
    Persona("smb_owner", "non-technical small-business owner", 90, 350,
            (Q_WHAT, Q_WHY),
            ("jargon without explanation", "assumes public filings exist")),
    Persona("technical_founder", "technical founder", 180, 700,
            (Q_WHAT, Q_FOR, Q_AGAINST)),
    Persona("sceptical_expert", "sceptical subject-matter expert", 240, 900,
            (Q_FOR, Q_AGAINST, Q_CONFIDENCE, Q_UNKNOWN),
            ("claim stronger than its source",
             "pattern analogy presented as company evidence")),
    Persona("first_time_visitor", "first-time visitor", 60, 250,
            (Q_WHAT,),
            ("product does not explain itself",)),
    Persona("mobile_user", "mobile user", 90, 350,
            (Q_WHAT, Q_THESIS),
            ("horizontal scrolling", "slide overloaded with text")),
    Persona("five_minutes", "user with five minutes", 300, 1200,
            (Q_WHAT, Q_THESIS, Q_FOR, Q_DECISION, Q_NEXT)),
    Persona("thirty_seconds", "user with thirty seconds", 30, 120,
            (Q_WHAT,),
            ("central thesis below the fold",)),
    Persona("knows_company", "user who knows the company well", 180, 700,
            (Q_CHANGING, Q_FOR),
            ("only restates what is on the homepage",)),
    Persona("knows_nothing", "user who knows nothing about the company", 180,
            700, (Q_WHAT, Q_WHY, Q_THESIS),
            ("assumes prior knowledge",)),
    Persona("competitor_context", "user seeking competitor context", 180, 700,
            (Q_CHANGING, Q_FOR)),
    Persona("risk_seeker", "user seeking risks", 180, 700,
            (Q_AGAINST, Q_UNKNOWN, Q_CONFIDENCE),
            ("generic risk boilerplate",)),
    Persona("meeting_prep", "user preparing for a meeting", 300, 1200,
            (Q_WHAT, Q_CHANGING, Q_NEXT, Q_DECISION),
            ("no specific question to ask the other side",)),
    Persona("simple_explanation", "user seeking a simple explanation", 90, 350,
            (Q_WHAT, Q_WHY),
            ("jargon without explanation",)),
    # Readers defined by WHAT they point the product at rather than by their
    # job. They exist separately because the failure they catch is different:
    # not "was this useful to me" but "did the product understand what kind of
    # company this is". A private startup judged against filings and a
    # multinational judged against a marketing site fail in opposite
    # directions, and neither is visible from a job-title persona.
    Persona("public_company_tester", "user testing a public company", 180, 700,
            (Q_WHAT, Q_CHANGING, Q_FOR, Q_CONFIDENCE),
            ("no use made of filings or investor material",)),
    Persona("private_company_tester", "user testing a private company", 180,
            700, (Q_WHAT, Q_THESIS, Q_UNKNOWN),
            ("assumes public filings exist",)),
    Persona("startup_tester", "user testing a small startup", 120, 500,
            (Q_WHAT, Q_THESIS, Q_UNKNOWN),
            ("assumes public filings exist",
             "treats a small company as a failed large one")),
    Persona("multinational_tester", "user testing a multinational", 240, 900,
            (Q_WHAT, Q_CHANGING, Q_FOR, Q_AGAINST),
            ("confuses a subsidiary with the parent",)),
)

PERSONAS_BY_KEY = {p.key: p for p in PERSONAS}


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    # What the evaluation should EXPECT rather than demand.
    expects_refusal: bool = False
    expects_limited: bool = False
    # Evidence environment: "public" | "private" | "local"
    company_type: str = "public"
    notes: str = ""
    tags: tuple = field(default_factory=tuple)


SCENARIOS = (
    Scenario("strong_evidence", "strong, diverse evidence"),
    Scenario("company_owned_only", "only company-owned evidence",
             notes="confidence must be capped without independent sources",
             tags=("confidence",)),
    Scenario("weak_evidence", "thin evidence", expects_limited=True),
    Scenario("contradictory", "sources contradict each other",
             tags=("counter_evidence",)),
    Scenario("stale", "evidence is old", tags=("freshness",)),
    Scenario("no_customer_evidence", "no customer or use-case evidence",
             tags=("coverage",)),
    Scenario("no_financials", "no financial disclosure",
             company_type="private"),
    Scenario("js_heavy", "JavaScript-rendered marketing site"),
    Scenario("startup_no_filings", "small company with no filings",
             company_type="private",
             notes="must not expect SEC-style evidence"),
    Scenario("local_business", "local service business",
             company_type="local", expects_limited=True),
    Scenario("identity_ambiguous", "multinational identity ambiguity",
             tags=("identity",)),
    Scenario("retrieval_failed", "every source failed", expects_refusal=True),
    Scenario("sparse", "almost no public evidence", expects_refusal=True),
    Scenario("mobile", "mobile viewport", tags=("layout",)),
    Scenario("followup_natural", "natural follow-up questions",
             tags=("conversation",)),
    Scenario("followup_vague", "vague follow-up question",
             tags=("conversation",)),
    Scenario("followup_hostile", "sceptical challenge to the thesis",
             tags=("conversation",)),
    Scenario("followup_simplify", "asked to remove jargon",
             tags=("conversation",)),
    Scenario("presentation", "asked for a presentation",
             tags=("presentation",)),
    # Adversarial retrieved content. Retrieved pages are DATA; a page that
    # writes instructions to the system, or asserts a flattering claim it has
    # no standing to make, must change nothing about how it is treated.
    Scenario("prompt_injection", "a retrieved page addresses the system",
             tags=("safety",),
             notes="instructions inside retrieved content are never followed"),
    Scenario("evidence_poisoning", "a retrieved page asserts unearned claims",
             tags=("safety",),
             notes="a company-owned page cannot promote itself to "
                   "independent corroboration"),
    # Operational conditions. These are not evidence environments — the same
    # company, met under a condition the product has to survive.
    Scenario("cached_low_quality", "a prior weak analysis is cached",
             tags=("cache",),
             notes="a bad terminal result must not block a better rerun"),
    Scenario("pipeline_upgrade", "re-analysed after a pipeline upgrade",
             tags=("cache",),
             notes="a result from an incompatible version is not reused"),
    Scenario("cold_start", "first request against a cold deployment",
             tags=("performance",)),
    # Evidence that was retrieved perfectly and cannot be read. Distinct from
    # sparse evidence: there is plenty of it, and declining is still correct.
    Scenario("unreadable_language", "company publishes in another language",
             expects_limited=True, tags=("coverage",),
             notes="retrieval succeeded; the analysis could not read it"),
    # A site that serves the same page for every path. Distinct from sparse
    # evidence too: every count looks healthy and there is one document.
    Scenario("duplicate_pages", "every page is the same page",
             expects_limited=True, tags=("coverage",)),
    Scenario("low_bandwidth", "slow connection, little patience",
             tags=("performance", "layout")),
)

SCENARIOS_BY_KEY = {s.key: s for s in SCENARIOS}

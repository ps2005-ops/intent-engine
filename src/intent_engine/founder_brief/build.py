"""Build the 60-second founder brief from whatever the run actually found.

THE DESIGN CONSTRAINT
---------------------
Every field on this brief is derived from evidence the pipeline already
produced. Nothing here generates prose about a company from nothing — if the
material for a section does not exist, the section is omitted and the omission
is stated. That is the difference between a brief that is short because it is
focused and one that is short because it is guessing.

COMPANY MODES
-------------
The output must be equally USEFUL, not equally detailed. A local bakery and a
public software company need different briefs, and pretending otherwise is how
a product ends up padding one and truncating the other.

    PUBLIC_INFORMATION_RICH   filings, financials, market context
    PRIVATE_COMPANY           product, pricing, customers, hiring
    SMALL_STARTUP             what it sells, who buys, what proof exists
    LOCAL_BUSINESS            offering, discoverability, reputation, trust
    MARKETING_ONLY            visibility and positioning diagnosis

THE SPARSE CASE IS THE ONE THAT MATTERS
---------------------------------------
The customer's sharpest complaint: a company with little public information
gets a dead end. The old path returned "insufficient evidence" and stopped.

That is accurate and useless. A founder who runs their own small company
already knows there is not much written about them; what they do not know is
what a customer can actually verify, what the site claims without proof, and
which three pieces of public evidence would close the gap.

So `MARKETING_ONLY` returns a real product built only from what is genuinely
observable — no invented adoption, no invented economics, no invented strategy.
It diagnoses VISIBILITY, not strategy, and says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from intent_engine.founder_brief.contract import (
    FounderInsight, InsightRejected, safe_insights, validate,
)

BRIEF_VERSION = "founder_brief.v1"

PUBLIC_INFORMATION_RICH = "PUBLIC_INFORMATION_RICH"
PRIVATE_COMPANY = "PRIVATE_COMPANY"
SMALL_STARTUP = "SMALL_STARTUP"
LOCAL_BUSINESS = "LOCAL_BUSINESS"
MARKETING_ONLY = "MARKETING_ONLY"

MODES = (PUBLIC_INFORMATION_RICH, PRIVATE_COMPANY, SMALL_STARTUP,
         LOCAL_BUSINESS, MARKETING_ONLY)

# What each mode is allowed to talk about. A mode that claimed things outside
# its list would be inventing, so the list is the guard rather than a hint.
MODE_SCOPE = {
    PUBLIC_INFORMATION_RICH: ("filings", "financial trends", "earnings",
                              "independent reporting", "market context"),
    PRIVATE_COMPANY: ("product", "positioning", "pricing", "customer evidence",
                      "hiring", "partnerships", "verified funding"),
    SMALL_STARTUP: ("what it sells", "likely buyer", "visible proof",
                    "pricing clarity", "distribution", "messaging clarity"),
    LOCAL_BUSINESS: ("offering", "local positioning", "discoverability",
                     "reputation", "pricing visibility"),
    MARKETING_ONLY: ("what is verifiable", "what is claimed",
                     "what a customer can see", "what is unclear"),
}

# Never inferable from a marketing site, however confident the copy sounds.
# Result states in which the report asserts no strategic conclusion. Any of
# these means the founder-facing layers must withhold one too.
_WITHHELD_STATES = frozenset({
    "EVIDENCE_LIMITED", "INSUFFICIENT_EVIDENCE", "WITHHELD", "NO_SIGNAL",
    "LIMITED", "REFUSED",
})

#: The provenance composition stamps on a report whose hypotheses came from
#: the pattern library rather than from a verified analyst reading. This, and
#: not the state name, is what separates a reading from a scaffold.
_SCAFFOLD_PROVENANCE = "pattern_library"

NEVER_INVENT = ("leadership discussions", "strategic pivots",
                "customer adoption", "unit economics", "defensibility",
                "market share", "revenue", "margins", "retention")


def classify_mode(*, is_public: bool = False, evidence_count: int = 0,
                  independent_sources: int = 0, has_thesis: bool = False,
                  has_financials: bool = False,
                  employee_hint: str = "") -> str:
    """Which experience this company should get.

    Ordered from most to least evidence, and deliberately conservative: a
    company is only PUBLIC_INFORMATION_RICH when there is genuinely rich public
    material, because that mode promises financial and market depth it must
    then be able to deliver.
    """
    if is_public and has_financials and evidence_count >= 5:
        return PUBLIC_INFORMATION_RICH
    if independent_sources == 0 and evidence_count <= 3 and not has_thesis:
        return MARKETING_ONLY
    if employee_hint == "local":
        return LOCAL_BUSINESS
    if is_public or (has_thesis and independent_sources >= 1):
        return PRIVATE_COMPANY if not is_public else PUBLIC_INFORMATION_RICH
    if evidence_count <= 6:
        return SMALL_STARTUP
    return PRIVATE_COMPANY


@dataclass
class FounderBrief:
    """The 60-second answer. Every field is optional except the ones a founder
    cannot act without."""
    company: str
    mode: str
    what_it_does: str = ""
    what_changed: tuple = ()
    key_insight: Optional[FounderInsight] = None
    next_actions: tuple = ()
    biggest_risk: str = ""
    biggest_unknown: str = ""
    confidence: str = ""
    confidence_reason: str = ""
    limitations: tuple = ()
    dropped: tuple = ()
    market_context: Optional[dict] = None
    withheld_reason: str = ""
    verified: tuple = ()
    claimed: tuple = ()
    customer_can_see: tuple = ()
    unclear: tuple = ()
    internal_questions: tuple = ()
    public_proofs: tuple = ()

    @property
    def is_useful(self) -> bool:
        """A brief is useful when it answers the seven comprehension questions.

        A sparse brief with no key insight is still useful IF it tells the
        reader what is verifiable, what is unclear and what to do about it --
        which is exactly the case the old dead-end page failed.
        """
        has_answer = bool(self.key_insight) or bool(
            self.verified or self.unclear)
        return bool(self.what_it_does) and has_answer and bool(
            self.next_actions)

    def as_dict(self) -> dict:
        return {
            "version": BRIEF_VERSION, "company": self.company,
            "mode": self.mode, "what_it_does": self.what_it_does,
            "what_changed": list(self.what_changed),
            "key_insight": (self.key_insight.as_dict()
                            if self.key_insight else None),
            "next_actions": list(self.next_actions),
            "biggest_risk": self.biggest_risk,
            "biggest_unknown": self.biggest_unknown,
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "limitations": list(self.limitations),
            "dropped": list(self.dropped),
            "market_context": self.market_context,
            "verified": list(self.verified), "claimed": list(self.claimed),
            "customer_can_see": list(self.customer_can_see),
            "unclear": list(self.unclear),
            "internal_questions": list(self.internal_questions),
            "public_proofs": list(self.public_proofs),
            "is_useful": self.is_useful,
        }


#: Marketing formulas that describe an ASPIRATION rather than a business.
#: These are the sentences a company puts at the top of its own site, and
#: they are the ones this product may not put at the top of its page (§22).
_ASPIRATION = re.compile(
    r"\bmission is to\b|\bour vision\b|\bwe believe that\b"
    r"|\bwe are on a mission\b|\bhelp build a better\b"
    r"|\bthe world'?s leading\b|\bpowering the next generation\b"
    r"|\bwelcome to\b", re.I)


def _sentence(text: str, limit: int = 220) -> str:
    """A COMPLETE sentence, or a shorter complete one, but never a fragment.

    THE ELLIPSIS WAS THE DEFECT. Cutting at a character budget and appending
    "…" put this on the first line of the product, under the company name:

        "Cloudflare's mission is to help build a better Internet. We have
         built a global network that delivers a broad range of services to
         businesses of all sizes and in all…"

    Prose that trails off because a buffer ran out is indistinguishable, to a
    reader, from a product that stopped working. So the cut is made at a
    SENTENCE boundary. If not even one sentence fits, the value is dropped
    rather than clipped -- an absent line degrades the page, a broken one
    discredits it.
    """
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    kept = ""
    for match in re.finditer(r"[^.!?]*[.!?]", text):
        candidate = text[:match.end()].strip()
        if len(candidate) > limit:
            break
        kept = candidate
    return kept


def build(*, company: str, mode: str, report: Optional[dict] = None,
          observations: Optional[Sequence[dict]] = None,
          market: Optional[dict] = None) -> FounderBrief:
    """Assemble the brief for one company in one mode."""
    report = report or {}
    observations = list(observations or ())

    brief = FounderBrief(company=company, mode=mode)
    brief.what_it_does = _what_it_does(report, observations, company)

    if mode == MARKETING_ONLY:
        return _sparse_brief(brief, observations)

    brief.what_changed = _what_changed(observations)
    candidates = _insight_candidates(report, observations)
    keep, dropped = safe_insights(candidates)
    brief.key_insight = keep[0] if keep else None
    brief.dropped = tuple(dropped)

    thesis = (report.get("thesis") or {})
    brief.biggest_risk = _sentence(
        _first(report.get("risks")) or _first(thesis.get("risks"))
        or _first(report.get("evidence_gaps")))
    brief.biggest_unknown = _sentence(
        _first(report.get("questions")) or _first(report.get("evidence_gaps")))
    brief.next_actions = _next_actions(report, brief.key_insight, mode)

    # ONE SCREEN, ONE SENTENCE, ONCE.
    #
    # Seen live on Palantir: `risks` and `questions` were both empty, so
    # `biggest_risk`, `biggest_unknown` AND a "Find out:" action all fell back
    # to the same first evidence gap. The founder's primary screen printed one
    # sentence three times under three different headings, which is what a
    # generic AI summary looks like. Later fields yield to earlier ones and
    # are dropped rather than repeated -- an empty section is honest, a
    # duplicated one is not.
    spoken = {_said(brief.key_insight.fact) if brief.key_insight else "",
              _said(brief.key_insight.so_what) if brief.key_insight else "",
              _said(brief.key_insight.decision) if brief.key_insight else ""}
    spoken |= {_said(c["what"]) for c in brief.what_changed}
    for field in ("biggest_risk", "biggest_unknown"):
        value = getattr(brief, field)
        if _said(value) in spoken:
            setattr(brief, field, "")
        elif value:
            spoken.add(_said(value))
    kept = []
    for action in brief.next_actions:
        if _said(action) in spoken:
            continue
        spoken.add(_said(action))
        kept.append(action)
    brief.next_actions = tuple(kept)
    brief.confidence, brief.confidence_reason = _confidence(
        observations, report, brief.key_insight)
    brief.market_context = market
    if not brief.key_insight:
        brief.withheld_reason = " ".join(str(
            report.get("result_state_detail") or "").split())
        brief.limitations = (
            "No single conclusion cleared the evidence bar, so none is "
            "presented as the headline. What was found is below.",)
    return brief


def _first(items) -> str:
    for item in (items or ()):
        text = item if isinstance(item, str) else (
            item.get("text") or item.get("summary") or "")
        if text:
            return text
    return ""


# A consequence needs a subject doing something. These are the shapes that
# reached the deployed preview under a "Why this matters" heading and said
# nothing: a bare topic ("how much to invest ahead of the transition"), a
# question-shaped stub ("whether to keep investing in depth"), and a naked
# noun phrase. They are all recognisable by having no finite verb.
# Interrogative openings, not a list of the ones seen so far. "How much to
# invest ahead of the transition" was blocked and "How exposed a plan is to one
# buyer's product cycle slipping" was not, because the list named two "how"
# phrasings out of the six the library uses. A sentence that opens on "how" or
# "whether" is asking; "what"/"when" stay narrow because both open legitimate
# cleft sentences ("What customers actually buy is the outcome").
_FRAGMENT_STARTS = ("how ", "whether ", "what to", "when to",
                    "which ", "why ")
# SENTENCES ABOUT THE ANALYSIS, NOT ABOUT THE BUSINESS.
#
# "The most recent evidence is About Palantir." has a finite verb and passed
# the check below, then rendered to a real founder as a conclusion. It is
# provenance in the grammar of an assertion: it describes what the system
# read, and says nothing about the company. Metadata that parses as a sentence
# is exactly the case a verb test cannot catch, so it is named directly.
_SELF_REFERENTIAL = ("the most recent evidence", "the latest evidence",
                     "recent public signal", "this analysis", "the evidence is",
                     "sources include", "based on the sources")
_VERB_HINTS = (" is ", " are ", " was ", " were ", " can ", " could ",
               " may ", " might ", " will ", " would ", " has ", " have ",
               " raises ", " lowers ", " erodes ", " makes ", " forces ",
               " means ", " leaves ", " keeps ", " becomes ", " grows ",
               " reduces ", " increases ", " risks ", " threatens ",
               " depends ", " requires ", " shifts ", " turns ")

# THE INVENTORY WAS THE BUG, NOT THE RULE.
#
# The rule -- a claim needs a finite verb -- is right. Thirty hand-listed verbs
# to implement it is not: "Northstar pricing publishes its prices" is a
# complete assertion about a company and was rejected because nobody had
# written " publishes " into the tuple above. Every such rejection silently
# blanks a real finding, which is the failure mode this gate exists to
# prevent, so the inventory is widened to ordinary finite English.
#
# Widening the VERB list weakens nothing. A noun phrase ("Palantir Partnership
# Vanguard"), a bare topic ("whether to keep investing in depth"), a pattern
# label and a metadata sentence are each rejected by a DIFFERENT rule -- the
# fragment-start list, the self-referential list, the taxonomy filter, the word
# floor. None of them depends on a verb being absent from a lexicon.
_FINITE_VERBS = frozenset("""
is are was were be been am has have had do does did
can could may might will would shall should must ought need needs
acquires acquired adds added allows allowed announces announced appears
appeared applies applied arrives arrived asks asked avoids avoided
becomes became begins began breaks broke brings brought builds built
buys bought carries carried causes caused charges charged chooses chose
commits committed competes competed concentrates concentrated confirms
confirmed costs covers covered creates created cuts decides decided
delays delayed delivers delivered describes described determines
determined develops developed drives drove drops dropped earns earned
ends ended enters entered establishes established exceeds exceeded
exposes exposed extends extended fails failed falls fell favours favors
favoured favored finds found follows followed gains gained gives gave
goes went grew handles handled happens happened helps helped holds held
improves improved includes included invests invested joins joined
knows knew lacks lacked lands landed lasts lasted launches launched
leads led learns learned lets limits limited lives lived loses lost
matches matched matters mattered migrates migrated misses missed moves
moved names named needs needed offers offered opens opened operates
operated owns owned pays paid picks picked places placed plans planned
points pointed prevents prevented prices priced produces produced
promises promised protects protected proves proved provides provided
publishes published pulls pulled puts raised reaches reached reads read
receives received reflects reflected remains remained removes removed
replaces replaced reports reported rests rested returns returned rises
rose runs ran says said sees saw sells sold sends sent serves served
sets settles settled shows showed signals signalled signaled sits sat
solves solved sounds sounded spends spent splits split stands stood
starts started stays stayed stops stopped strains strained suggests
suggested supports supported takes took teaches taught tells told tends
tended tests tested tightens tightened trades traded treats treated
tries tried uses used wants wanted watches watched weakens weakened
wins won works worked
""".split()) | frozenset("""
add allow appear apply arrive ask avoid become begin break bring build buy
carry cause charge choose commit compete concentrate confirm cost cover
create cut decide delay deliver depend describe determine develop drive drop
earn end enter erode establish exceed expose extend fail fall favour favor
find follow force gain give grow handle happen help hold improve include
increase invest join keep know lack land last lead learn leave let limit
live lose make match matter mean migrate miss move name need offer open
operate own pay pick place plan point prevent price produce promise protect
prove provide publish pull put raise reach read receive reduce reflect
remain remove replace report require rest return rise run say see sell send
serve set settle shift show sit solve sound spend split stand start stay
stop strain suggest support take teach tell tend test threaten tighten
trade treat try turn use want watch weaken win work
""".split())
# A PLURAL SUBJECT TAKES THE BASE FORM, which the inflected list above cannot
# see. "value and lock-in migrate from the visible product to the rails
# underneath it" carries no inflected verb at all, and half the pattern
# library's mechanism sentences are written that way -- so rejecting them left
# the strongest thing the analysis had to say about a company in a field that
# nothing rendered.


def _has_finite_verb(low: str) -> bool:
    """True when a lowercased sentence carries a finite verb.

    Two inventories, deliberately: the hint tuple matches on surrounding
    spaces and so catches multi-word shapes, while the lexicon matches whole
    WORDS and so catches a verb opening an imperative or closing a clause --
    "Sentry acquired Codecov." has no trailing space after the object.
    """
    if any(hint in f" {low} " for hint in _VERB_HINTS):
        return True
    # Hyphens are part of the WORD. Splitting on them made "a people-delivered
    # service" contain the verb "delivered", so the pattern library's own
    # titles -- noun phrases, every one -- started passing as claims.
    return any(word in _FINITE_VERBS
               for word in re.findall(r"[a-z'\-]+", low))


def _is_consequence(text: str) -> bool:
    """True when this reads as a statement about what follows, not a topic.

    Deliberately conservative: it accepts anything with a finite verb, so it
    lets through prose that is merely mediocre and only rejects the shapes
    that carry no assertion at all. Over-rejecting would silently blank a
    real interpretation, which is worse than an inelegant one.
    """
    stripped = " ".join((text or "").split())
    if len(stripped.split()) < 5:
        return False
    low = stripped.lower()
    if low.startswith(_FRAGMENT_STARTS):
        return False
    # A PARTICIPIAL PHRASE IS NOT A SENTENCE.
    #
    # Every title in the pattern library opens on a gerund -- "leaning on a
    # buyer type whose budget it does not control", "turning a people-
    # delivered service into a repeatable product". They name a shape and
    # assert nothing, but a relative clause inside one ("does not control")
    # carries a finite verb, so a verb test alone lets them through. What
    # decides it is the MAIN clause, and an opening gerund means there is not
    # one.
    if re.match(r"[a-z]+ing\b", low):
        return False
    if any(marker in low for marker in _SELF_REFERENTIAL):
        return False
    return _has_finite_verb(low)


def _consequence(*candidates) -> str:
    """The first candidate that actually states a consequence, else "".

    Returning "" is a real outcome: the renderer omits the block rather than
    printing a heading over a fragment.
    """
    for candidate in candidates:
        if isinstance(candidate, str) and _is_consequence(candidate):
            return candidate
    return ""


def _is_about(excerpt: str, company: str, origin: str = "",
              title: str = "", vocabulary=frozenset(),
              source_class: str = "", observation_type: str = "") -> bool:
    """Whether this passage is the SUBJECT describing itself.

    Now a thin adapter over `identity.classify`, which returns four states
    instead of two. CONFIRMED and PROBABLE are both usable here.

    WHY CALLERS THAT PASS NO VOCABULARY ARE UNCHANGED. PROBABLE is only
    reachable when the passage's subject is found in the company's own site
    vocabulary, so a caller that supplies none can only ever get CONFIRMED,
    NOT or UNKNOWN — exactly the strict behaviour that closed the Stripe/Figma
    leak. The provenance labels in `narrative.py` call it that way on purpose:
    relaxing an attribution label is a different decision from relaxing which
    sentence opens a page, and only the second one is being made here.

    THE WORST DEFECT THIS CYCLE FOUND, and the generic label had been hiding
    it. On the deployed preview Stripe's page opened:

        "Figma democratizes design through its collaborative design products."

    A document about another company was in Stripe's observation set,
    classified as own-account, so preferring excerpts surfaced it. The old
    behaviour masked it only because `observation_sentence` pastes the SUBJECT
    name onto every generated label — the wrong content was there all along
    with the right name in front of it.

    `company_ingestion` already guards this for filings by other registrants
    (`FS.subject_span`). This is the same rule applied where the sentence is
    chosen: a description of the business either names the business or is
    written in its own voice. A passage that does neither may be about anyone.
    """
    from intent_engine.founder_brief import identity as ID
    return ID.classify(
        excerpt, company=company, origin=origin, title=title,
        source_class=source_class, observation_type=observation_type,
        vocabulary=vocabulary).usable


def _is_about_legacy(excerpt: str, company: str) -> bool:
    """The original two-signal rule, kept as the CONFIRMED half's reference.

    Retained so the strict behaviour has a name and a test of its own rather
    than only existing inside a branch of the four-state classifier.
    """
    low = " ".join((excerpt or "").split()).lower()
    if re.search(r"\b(we|our|us)\b", low):
        return True
    from intent_engine.strategic_intelligence.subject import _company_tokens
    tokens = [t.lower() for t in _company_tokens(company or "")]
    if any(t in low for t in tokens):
        return True
    # PROVENANCE IS NECESSARY AND NOT SUFFICIENT, measured live.
    #
    # Accepting any page from the company's own domain still let Stripe's
    # result open with "Figma democratizes design through its collaborative
    # design products." Stripe HOSTS that page: it is a customer story, on
    # stripe.com, about somebody else. A company's own site is full of other
    # companies.
    #
    # "Figma democratizes design" and "Connectors read payout files from
    # payment processors" are the same shape to any rule that does not
    # already know Figma is a company, so the sentence cannot be made to
    # settle it. The strict rule wins: a passage that neither speaks in the
    # company's voice nor names it may be about anyone, and showing a founder
    # another company's description is worse than showing a duller sentence.
    #
    # The cost is real and was measured — Brightledger's "Connectors read
    # payout files..." is rejected with it, and falls back to a page that
    # does name the company. That is the trade, taken deliberately.
    return False


# --- excerpt substance ------------------------------------------------------
#
# Copy ABOUT A PAGE, which reads as a description until you ask what it says.
# Every phrase below is from a real opening that shipped: Shopify's "Learn
# about Shopify and how it works. Explore its pricing plans and essential
# features for building and managing your business" is a meta description, is
# genuinely Shopify writing about Shopify, and answers nothing.
_PAGE_COPY = re.compile(
    r"^(?:learn|discover|explore|find out|see how|read|get started|"
    r"everything you need to know|your guide to|welcome to)\b", re.I)
_SEO_SHAPE = re.compile(
    r"\b(?:and how it works|pricing plans|essential features|"
    r"everything you need|step[- ]by[- ]step|in this (?:guide|article)|"
    r"free trial|sign up today|no credit card)\b", re.I)
#: Second person is marketing address, not description. A business
#: description is about the company; "your business" is about the reader.
_SECOND_PERSON = re.compile(r"\b(?:your|you|you'?re|yours)\b", re.I)
#: Concrete verbs a description of a working product uses.
_MECHANISM = re.compile(
    r"\b(?:process\w*|reconcil\w+|match\w+|route\w*|settle\w*|"
    r"integrat\w+|analy[sz]\w+|manufactur\w+|distribut\w+|deliver\w+|"
    r"generat\w+|detect\w+|monitor\w+|automat\w+|connect\w+|"
    r"builds?|operates?|provides?|sells?|serves?|enables?)\b", re.I)


def _excerpt_substance(text: str) -> int:
    """How much this sentence says about the BUSINESS, ordinally.

    Not a quality score in any calibrated sense — a ranking key, used only to
    order candidates that have already passed the identity gate. Positive
    signals are concrete; negative ones are the shapes metadata takes.
    """
    body = " ".join((text or "").split())
    score = 0
    if _PAGE_COPY.match(body):
        score -= 4
    if _SEO_SHAPE.search(body):
        score -= 3
    if _SECOND_PERSON.search(body):
        score -= 2
    if _MECHANISM.search(body):
        score += 3
    # Numbers and proper nouns mid-sentence are what specific claims carry.
    if re.search(r"\b\d", body):
        score += 1
    if len(body.split()) >= 18:
        score += 1
    return score


def _what_it_does(report: dict, observations: Sequence[dict],
                  company: str = "") -> str:
    """One plain sentence. Drawn from the company's own description, because
    that is the one thing a marketing site is a reliable source for."""
    for key in ("what_it_does", "offering", "summary", "description"):
        value = report.get(key)
        if isinstance(value, str) and len(value.split()) >= 4:
            return _sentence(value, 180)

    # THE COMPANY'S WORDS, NOT OURS. This is the first sentence under the
    # company name — the first thing any founder reads — and it was taking
    # `obs["text"]`, which is not the company's description at all. That field
    # is the sentence THIS SYSTEM generates from a signal label:
    #
    #   "Palantir Technologies sells several distinct products rather than
    #    one, so attention and engineering are split across products that
    #    compete with each other for both."
    #
    # Measured on the deployed preview across twenty companies: Palantir and
    # Microsoft opened with that identical sentence, name-substituted, because
    # they carry the same signal. It is a label about our taxonomy where a
    # description of the business belongs — and the description was sitting in
    # `excerpt` the whole time:
    #
    #   "Palantir Technologies builds three platforms: Foundry for the
    #    commercial enterprise, Gotham for defence and intelligence..."
    #
    # Only the company's own account is used. A customer review and an
    # analyst note are real evidence and are the wrong voice for "what this
    # company does" — Shopify's highest-ranked excerpt is a merchant review
    # praising fast setup, which describes an experience rather than a
    # business. Weak observations are skipped for the same reason they are
    # weak: title-only and generic-marketing text says nothing.
    # ...and the RIGHT excerpt, which is not simply the first one. Ranking
    # order put Brightledger's API changelog and Sony's segment-reporting
    # cadence at the top: both are the company's own words and neither says
    # what the business is.
    #
    # `product_surface` FIRST, then `messaging`, and the order is measured
    # rather than guessed. Trying `messaging` first opened Notion, Linear
    # and Brightledger with their PRICE LISTS — pricing pages carry that
    # type — while their product pages say what the thing actually is:
    # "Connectors read payout files from payment processors, match them to
    # ledger entries, and raise an exception when a difference persists."
    own_account = ("company_owned", "executive_statement", "investor_material")

    # The company's own section and product names, read off its own site.
    # This is what lets a passage qualify without literally naming the
    # company: "Connectors read payout files..." is Brightledger describing
    # Brightledger because /connectors is a Brightledger page. Built once per
    # company, and built only from pages that are not customer stories — see
    # `identity.owned_vocabulary`.
    from intent_engine.founder_brief import identity as ID
    vocabulary = ID.owned_vocabulary(observations, company=company)

    def _pick(types):
        # RANKED, not first-match. Shopify opened with "Learn about Shopify
        # and how it works. Explore its pricing plans..." — the page's SEO
        # meta description. It is Shopify writing about Shopify, so the
        # identity gate passed it correctly; it is copy about a PAGE rather
        # than about a business, and taking the first qualifying observation
        # had no way to prefer the one that says what the company does.
        candidates = []
        for obs in observations:
            if obs.get("weak") or obs.get("source_class") not in own_account:
                continue
            if types and obs.get("observation_type") not in types:
                continue
            excerpt = (obs.get("excerpt") or "").strip()
            if len(excerpt.split()) >= 8 and _is_about(
                    excerpt, company, obs.get("origin", ""),
                    obs.get("source_title", ""), vocabulary=vocabulary,
                    source_class=obs.get("source_class", ""),
                    observation_type=obs.get("observation_type", "")):
                candidates.append(excerpt)
        if not candidates:
            return ""
        # A MISSION STATEMENT IS NOT A DESCRIPTION OF A BUSINESS (§22).
        #
        # "Cloudflare's mission is to help build a better Internet" is the
        # company's own words, is correctly attributed, and tells a reader
        # nothing they can act on -- and it was the first sentence of the
        # product. Aspiration copy is demoted below anything else the
        # company said about itself, and used only when there is nothing
        # else at all.
        ranked = sorted(candidates,
                        key=lambda e: (bool(_ASPIRATION.search(e)),
                                       -_excerpt_substance(e)))
        for candidate in ranked:
            trimmed = _sentence(candidate, 180)
            if trimmed:
                return trimmed
        return ""

    return (_pick(("product_surface",)) or _pick(("messaging",))
            or _pick(()) or _fallback_label(observations))


def _fallback_label(observations) -> str:
    """Last resort: the generated signal sentence.

    Kept because the comprehension gate treats a missing opening line as a
    failure, and a company-specific label beats an empty page. It is last
    because it is the one option that can read identically for two different
    companies.
    """
    # Last resort. A generated label is still better than an empty opening,
    # and the gate treats a missing `what_it_does` as a comprehension failure.
    for obs in observations:
        text = obs.get("text") or obs.get("summary") or ""
        if len(text.split()) >= 8:
            return _sentence(text, 180)
    return ""


def _said(text: str) -> str:
    """A sentence's identity, for "has this screen already said it?".

    The leading action verb is stripped first: "Find out: Revenue mix is not
    public" and "Revenue mix is not public" are the same sentence to a reader,
    and comparing them with the prefix attached let the identical evidence gap
    appear as both the biggest risk and an action.
    """
    body = re.sub(r"^\s*(find out|watch|ask|check|confirm|verify)\s*:\s*",
                  "", str(text or ""), flags=re.I)
    return " ".join(re.findall(r"[a-z0-9]+", body.lower()))[:120]


def _what_changed(observations: Sequence[dict]) -> tuple:
    """Up to three DATED developments, newest first.

    Dated only: an undated item is not a change, it is a fact with no
    before-and-after, and listing it under "what changed" is a small lie that
    compounds across a page.
    """
    dated = [o for o in observations if (o.get("date") or "")[:4].isdigit()]
    dated.sort(key=lambda o: o.get("date", ""), reverse=True)
    out, seen = [], set()
    for obs in dated:
        if len(out) >= 3:
            break
        text = _sentence(obs.get("text") or obs.get("summary") or "", 160)
        # Two observations retrieved from different pages routinely carry the
        # SAME derived sentence. Printed twice under "What changed", with the
        # same date, it reads as a broken product -- seen live on Palantir,
        # where one company-description sentence filled both rows.
        if not text or _said(text) in seen:
            continue
        seen.add(_said(text))
        out.append({"when": obs.get("date", "")[:10], "what": text,
                    "evidence_id": obs.get("observation_id", "")})
    return tuple(out)


def _decision_sentence(report: dict) -> str:
    """What the founder should DO, from the one composed decision.

    The recommended move leads because it is the actionable half; the headline
    follows it only when there is no move, which happens when nothing survived
    filtering to check. Both come from the same object every other surface
    renders, so the brief cannot disagree with the deck about what the
    decision is.
    """
    from intent_engine.strategic_intelligence.decision import decision_of
    decision = decision_of(report)
    if decision.readiness == "WITHHELD":
        return ""
    # The HEADLINE, not the next move. This field answers "what is being
    # decided"; the check that would settle it is what `watch` already
    # carries, and putting it here left the brief with a question in the one
    # slot the contract requires to name a choice.
    return decision.headline


def _insight_candidates(report: dict,
                        observations: Sequence[dict]) -> List[FounderInsight]:
    """Turn whatever the strategic layer concluded into candidate insights.

    Every candidate then goes through `validate`, so a conclusion that cannot
    state its consequence is dropped here rather than rendered as a headline
    with an empty "so what" underneath it.

    THE FIELD NAMES ARE THE WHOLE INTEGRATION
    -----------------------------------------
    The strategic pipeline already produces every field this contract needs --
    under its own vocabulary. `thesis.why_care` IS the decision. `thesis.
    tension` IS the implication. `hypothesis.falsification_questions` ARE the
    next checks. Nothing had to be generated; it had to be *mapped*.

    That is the customer's complaint in one function: the intelligence was
    there and the presentation could not reach it.
    """
    out: List[FounderInsight] = []
    thesis = report.get("thesis") or {}

    # THE READINESS GATE, inherited rather than re-derived.
    #
    # `thesis.view` can be populated with a templated sentence even when the
    # report asserts NO conclusion -- `result_state = EVIDENCE_LIMITED` with
    # "no strategic conclusion is asserted". Reading `view` alone revived a
    # claim the report had withheld, on the primary screen, which is the most
    # serious thing this product could do. The strategic brief already honours
    # this state; the founder brief now honours the same one.
    if str(report.get("result_state") or "").upper() in _WITHHELD_STATES:
        return []
    # AND THE SAME QUESTION ASKED STRUCTURALLY, because the line above is a
    # denylist and a denylist cannot exclude a class invented after it. The
    # CORE/DEEP split added DEEP_PENDING, the pre-model payload began carrying
    # it instead of EVIDENCE_LIMITED, and the scaffolds walked straight
    # through onto the primary screen: `key_insight` became `thesis.view` and
    # the next three became `hypotheses[:3]` -- generic by construction,
    # carrying real observation ids so `safe_insights` passes them, shown on
    # the page a chief executive opens first and now opens in seconds.
    #
    # DEEP_PENDING is deliberately NOT added to the set above as well. It
    # would be a second guard over the same case, and a redundant guard masks
    # the proof of the one doing the work -- removing either would leave the
    # test green and the wall would only look defended.
    if str(report.get("reasoning_provenance") or "") == _SCAFFOLD_PROVENANCE:
        return []

    view = thesis.get("view") or ""
    hypotheses = [h for h in (report.get("hypotheses") or ())
                  if isinstance(h, dict)]
    lead = hypotheses[0] if hypotheses else {}

    if view and not thesis.get("view_withheld"):
        out.append(FounderInsight(
            fact=_sentence(view, 260),
            # the MECHANISM, which is what turns an observation into a reading
            interpretation=_sentence(
                lead.get("reasoning") or thesis.get("transition") or "", 300),
            # WHY THIS MATTERS IS A CONSEQUENCE, NOT A TOPIC.
            #
            # The blind spot's `why_it_may_matter` states the consequence of
            # the tension and is preferred; the tension itself ("A is growing
            # while B still promises...") is the runner-up because it at
            # least states two things that cannot both stay true. Anything
            # that is not a complete thought is dropped rather than shown --
            # the preview rendered "Why this matters: how much to invest
            # ahead of the transition", which tells a reader nothing.
            so_what=_sentence(_consequence(
                thesis.get("why_it_may_matter"),
                thesis.get("tension"),
                _first(report.get("decision_implications"))), 280),
            # THE DECISION, NOT THE QUESTION IT IS ABOUT.
            #
            # This read `why_care`, which is `implications[0]` -- a decision
            # TOPIC. "Whether to keep investing in depth or in adjacency" is
            # the question a founder arrived with, and the brief handed it
            # back under the heading "The decision". It reaches Q&A too, as
            # `decision_affected`, so the same question was the answer in two
            # places. The composed decision states the options and the move.
            decision=_sentence(_decision_sentence(report), 240),
            watch=_sentence(
                _first(lead.get("falsification_questions"))
                or _first(report.get("underexamined_questions"))
                or _first(report.get("questions")), 220),
            evidence_ids=tuple(lead.get("supporting_observation_ids")
                               or lead.get("strongest_support_ids") or ()),
            confidence=str(lead.get("confidence") or "")))

    for hypothesis in hypotheses[:3]:
        out.append(FounderInsight(
            fact=_sentence(hypothesis.get("statement")
                           or hypothesis.get("title") or "", 260),
            interpretation=_sentence(hypothesis.get("reasoning") or "", 300),
            so_what=_sentence(_consequence(
                _first(hypothesis.get("decision_implications")),
                thesis.get("why_it_may_matter"),
                thesis.get("tension")), 280),
            decision=_sentence(_decision_sentence(report), 240),
            watch=_sentence(_first(hypothesis.get("falsification_questions"))
                            or _first(hypothesis.get("evidence_gaps")), 220),
            evidence_ids=tuple(hypothesis.get("supporting_observation_ids")
                               or hypothesis.get("strongest_support_ids")
                               or ()),
            confidence=str(hypothesis.get("confidence") or "")))
    return out


def _next_actions(report: dict, insight: Optional[FounderInsight],
                  mode: str) -> tuple:
    """At most three, bounded, and never an instruction to contact anyone.

    Three is a product decision, not a layout one: a list of eight
    recommendations is a list nobody acts on, and the cap forces the ranking to
    happen here rather than in the reader's head.
    """
    actions: List[str] = []
    if insight and insight.watch:
        actions.append(f"Watch: {insight.watch}")
    for question in (report.get("questions") or ())[:3]:
        text = question if isinstance(question, str) else question.get("text")
        if text:
            actions.append(_sentence(f"Answer internally: {text}", 180))
    # Filtered where the visible item is SELECTED, the same boundary the deck
    # and the brief use. The deployed Palantir brief told a founder to "Find
    # out: Whether customers actually moved their source of truth is not
    # observable from outside" -- an evidence gap phrased in the library's own
    # vocabulary, on the primary screen, as the single thing to go and do.
    from intent_engine.strategic_intelligence.concrete import (
        reads_as_taxonomy,
    )
    for gap in (report.get("evidence_gaps") or ()):
        text = gap if isinstance(gap, str) else gap.get("text")
        if text and not reads_as_taxonomy(text):
            actions.append(_sentence(f"Find out: {text}", 180))
        if len(actions) >= 5:
            break
    seen, unique = set(), []
    for action in actions:
        key = action.lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(action)
    return tuple(unique[:3])


def _confidence(observations: Sequence[dict], report: dict,
                insight: Optional[FounderInsight]) -> tuple:
    """Plain English, and always says what LIMITS it.

    A confidence label with no reason is decoration. The reason is the part a
    founder can actually act on -- it tells them what evidence would move it.
    """
    from intent_engine.strategic_intelligence.source_semantics import (
        independent_count,
    )
    n = len(observations)
    # A company filing is authoritative because of its venue and company-
    # authored all the same. Counting it as independent told a founder their
    # reading was externally corroborated when only the company had spoken.
    independent = independent_count(o.get("source_class") for o in observations)
    dated = sum(1 for o in observations if (o.get("date") or "")[:4].isdigit())

    # EVERY REASON MUST SAY WHAT WOULD MOVE IT.
    #
    # The label was doing the talking: the page opened "Low." and a founder
    # took that as the product's verdict on the company rather than a
    # statement about the evidence behind it. A grade is not information --
    # what is established, what is missing, and what would settle it is.
    if not insight:
        return ("Low", "No conclusion cleared the evidence bar, so none is "
                       "presented. What follows is what could be verified, "
                       "not what it means. One dated, independently reported "
                       "development would be enough to change that.")
    if independent == 0:
        # Written to survive the renderer's 40-word clip. The clause that
        # says what would MOVE the conclusion is the only actionable part,
        # and a longer, better sentence was being truncated exactly there.
        return ("Low", f"All {n} source(s) are the company's own. The facts "
                       f"are checkable; the reading of them has not been "
                       f"tested outside the company. A customer account or "
                       f"independent report would move this.")
    if independent >= 2 and dated >= 3:
        return ("Moderate", f"{independent} source(s) outside the company "
                            f"agree with {dated} dated item(s), so the "
                            f"direction is corroborated, not asserted. It "
                            f"still cannot see pricing, retention or unit "
                            f"economics — those would confirm it.")
    return ("Low to moderate", f"{independent} source(s) from outside the "
                               f"company and {dated} dated item(s) — enough "
                               f"to point a direction, not enough to rely on. "
                               f"One further independent account either way "
                               f"would settle it.")


# ---------------------------------------------------------------------------
# THE SPARSE CASE — a real product, not a refusal
# ---------------------------------------------------------------------------
def _sparse_brief(brief: FounderBrief,
                  observations: Sequence[dict]) -> FounderBrief:
    """What a company with only a marketing site can honestly be told.

    Everything here is observable by anyone who visits the site. Nothing is
    inferred about adoption, economics or strategy — those are the things a
    marketing page cannot evidence, and inventing them is what makes a sparse
    report worse than no report.

    The value is a VISIBILITY diagnosis: a founder learns what a prospective
    customer can actually confirm about them, which is a question they cannot
    answer from the inside.
    """
    texts = [(o.get("text") or o.get("summary") or "") for o in observations]
    joined = " ".join(texts).lower()

    verified, claimed = [], []
    for text in texts:
        if not text:
            continue
        if _looks_like_a_claim(text):
            claimed.append(_sentence(text, 160))
        else:
            verified.append(_sentence(text, 160))

    customer_can_see = []
    for label, markers in (("what it sells", ("product", "service", "offer",
                                              "platform", "solution")),
                           ("pricing", ("price", "pricing", "$", "plan",
                                        "per month", "free trial")),
                           ("who it is for", ("for teams", "for business",
                                              "for developers", "customers",
                                              "clients")),
                           ("proof it works", ("case study", "testimonial",
                                               "review", "customer story",
                                               "logo"))):
        present = any(m in joined for m in markers)
        customer_can_see.append({"item": label, "present": present})

    missing = [c["item"] for c in customer_can_see if not c["present"]]
    brief.verified = tuple(verified[:4])
    brief.claimed = tuple(claimed[:4])
    brief.customer_can_see = tuple(customer_can_see)
    brief.unclear = tuple(
        f"A visitor cannot confirm {item} from the public site."
        for item in missing) or (
        "No dated, independently-reported activity could be found.",)

    # Tight on purpose. These are the highest-value lines in a sparse brief
    # and they compete for the same 60 seconds as everything else.
    brief.internal_questions = (
        "Who is this built for, and can a stranger tell in ten seconds?",
        "Which single proof would most reduce a buyer's doubt — and why is it "
        "not public?",
        "Is hidden pricing a deliberate sales motion, or an unmade decision?",
    )
    brief.public_proofs = (
        "A named customer story with a concrete before-and-after.",
        "Visible pricing, or an explicit reason it is quote-only.",
        "A dated changelog or release note showing the product is actively "
        "maintained.",
    )
    brief.next_actions = (
        "Publish the cheapest proof from the list below.",
        "Answer the three questions in writing — a buyer is asking them "
        "silently.",
        "Re-run this after the site changes to see what a stranger can verify.",
    )
    brief.biggest_risk = (
        "Nothing on the site is independently confirmable, so the whole burden "
        "of proof falls on a sales conversation.")
    brief.biggest_unknown = (
        "Whether the business is working. Nothing public shows adoption, "
        "retention or economics, and this does not guess.")
    brief.confidence = "Low, by construction"
    brief.confidence_reason = (
        "Only the company's own material was found. This diagnoses what is "
        "VISIBLE, not whether the strategy is sound.")
    brief.limitations = (
        "No independent reporting, filings or customer evidence was found.",
        "Nothing here describes adoption, revenue, margins or defensibility. "
        "A marketing site cannot evidence them, so they are not discussed.",
    )
    return brief


_CLAIM_MARKERS = ("leading", "best-in-class", "world-class", "revolutionary",
                  "seamless", "cutting-edge", "industry-leading", "trusted by",
                  "#1", "fastest", "most advanced", "unparalleled",
                  "game-changing", "next-generation")


def _looks_like_a_claim(text: str) -> bool:
    """Marketing superlative rather than a checkable statement.

    Separating these is the whole product in the sparse case: the founder
    learns which of their sentences a stranger would treat as evidence and
    which as advertising.
    """
    return any(m in (text or "").lower() for m in _CLAIM_MARKERS)

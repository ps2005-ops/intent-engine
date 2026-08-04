"""The scrollable executive decision narrative — the default founder result.

WHAT WAS WRONG
--------------
Measured on the deployed preview (Palantir, commit a6866d6), three surfaces
built from ONE run disagreed about whether a conclusion existed at all:

    /runs/<id>          "No strategic conclusion is being asserted about
                         this company."
    /runs/<id>/slides    "The choice: Commit to the reading now versus hold
                         and verify first" — two options, a cost on each
                         side, and the one check that separates them
    /runs/<id>/brief     a third decision again, and a topic printed raw

The decision was composed correctly every time. The DEFAULT screen simply
never asked for it: `render_brief` reads `brief.key_insight`, and when the
thesis view is withheld that field is None — so the page fell through to a
refusal while the deck three clicks away carried the answer. A founder who
stopped at the first screen, which is what a first screen is for, was told
the product had nothing to say.

WHAT THIS MODULE DOES
---------------------
It renders the ONE decision, vertically, in the order a founder reads:

    executive answer -> why now -> what changed -> business consequence
    -> the decision -> options -> next move -> evidence for -> evidence
    against -> what could make this wrong -> what to watch -> what was
    prepared

Nothing here interprets. Every string is lifted from the composed
`FounderDecision`, the `FounderBrief`, or the report's own observations, and
the sentence-fitting helpers are imported from the composer rather than
restated — two renderers that each phrase the mechanism their own way is how
one mechanism comes to read as two.

A SECTION WITH NOTHING BEHIND IT IS NOT RENDERED
------------------------------------------------
`Section.is_substantive` is the gate, and `build_narrative` drops what fails
it. A heading over a blank tells a reader the product forgot to fill it in;
an absent heading tells them nothing, which is the truth when there is
nothing. The states that carry no options say so in their own words rather
than rendering an empty comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape as _e
from typing import List, Optional, Sequence

from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD, as_clause,
    decision_from_dict, decision_of, end_sentence, lower_first,
)
from intent_engine.strategic_intelligence.editorial import SaidOnce

NARRATIVE_VERSION = "founder_narrative.v1"

#: Section keys, in reading order. Public because the consistency tests and
#: the slide builder both address sections by name, and a typo in a string
#: literal is otherwise a silently missing section.
EXECUTIVE_ANSWER = "executive_answer"
WHY_NOW = "why_now"
WHAT_CHANGED = "what_changed"
BUSINESS_CONSEQUENCE = "business_consequence"
THE_DECISION = "the_decision"
OPTIONS = "options"
NEXT_MOVE = "next_move"
EVIDENCE_FOR = "evidence_for"
EVIDENCE_AGAINST = "evidence_against"
COULD_BE_WRONG = "could_be_wrong"
#: Outside conditions. Placed AFTER the decision, its options and what could
#: make it wrong, so a reader meets the company's own answer first and the
#: market as context on it. Before them, the page reads as though the market
#: drove the conclusion -- which is exactly the causal misreading that makes
#: market context dangerous to show at all.
OUTSIDE = "outside"
WHAT_TO_WATCH = "what_to_watch"
PREPARED = "prepared"

SECTION_ORDER = (
    EXECUTIVE_ANSWER, WHY_NOW, WHAT_CHANGED, BUSINESS_CONSEQUENCE,
    THE_DECISION, OPTIONS, NEXT_MOVE, EVIDENCE_FOR, EVIDENCE_AGAINST,
    COULD_BE_WRONG, OUTSIDE, WHAT_TO_WATCH, PREPARED,
)

#: How a source is described to a reader who is not holding the taxonomy.
#: The enum name never reaches the page; this map is the only thing that does.
PROVENANCE_LABEL = {
    "company_owned": "Company claim",
    "executive_statement": "Company claim",
    "investor_material": "Regulatory or investor filing",
    "customer_voice": "Customer evidence",
    "competitor": "Competitor evidence",
    "independent_reporting": "Independent evidence",
    "historical_pattern": "Inference from a comparable case",
    "unavailable_or_failed": "Unknown — could not be retrieved",
}
_DEFAULT_PROVENANCE = "Unknown"

# WHICH PART OF THE BUSINESS A SUPPORTED SENTENCE SPEAKS TO.
#
# This labels sentences the analysis already produced; it never generates a
# consequence. A dimension appears only when a supported sentence actually
# mentions it, which is why an unrelated company cannot receive the same list.
_DIMENSIONS = (
    ("Revenue quality", ("revenue", "recurring", "one-off", "one off",
                         "bookings", "contract", "billing", "licence",
                         "license", "subscription")),
    ("Margins", ("margin", "gross", "cost per", "unit econom", "cheaper",
                 "expensive")),
    ("Implementation burden", ("implementation", "deploy", "engagement",
                               "onboarding", "integration", "services",
                               "forward-deployed", "bespoke", "custom")),
    ("Product scalability", ("scale", "scalab", "repeatab", "productis",
                             "productiz", "self-serve", "off the shelf",
                             "reusable", "template")),
    ("Sales cycles", ("sales cycle", "procurement", "pilot", "deal",
                      "close rate", "buying")),
    ("Retention", ("retention", "churn", "renew", "expansion revenue",
                   "stickiness")),
    ("Switching costs", ("switching", "lock-in", "lock in", "migrate",
                         "source of truth", "rails", "embedded", "entrenched")),
    ("Operating leverage", ("headcount", "linearly", "per engagement",
                            "operating leverage", "hire ahead", "staffing")),
    ("Competitive position", ("competitor", "competing", "alternative",
                              "differentiat", "moat", "defensib", "rival",
                              "point tool")),
    ("Organisational capacity", ("attention", "engineering are split",
                                 "roadmap", "focus", "split across",
                                 "org ", "team")),
    ("Market expectations", ("investor", "guidance", "expectations",
                             "valuation", "the market", "analyst")),
)


# --- data model ---------------------------------------------------------------

@dataclass
class EvidenceItem:
    """One thing a source actually said, labelled by what kind of thing it is."""
    text: str = ""
    source_title: str = ""
    provenance: str = _DEFAULT_PROVENANCE
    date: str = ""
    evidence_id: str = ""

    def as_dict(self) -> dict:
        return {"text": self.text, "source_title": self.source_title,
                "provenance": self.provenance, "date": self.date,
                "evidence_id": self.evidence_id}


@dataclass
class Section:
    """One vertical block. Renders only when it carries something."""
    key: str
    title: str
    kind: str = "prose"                  # prose|dated|labelled|options|evidence|actions
    paragraphs: tuple = ()
    items: tuple = ()                    # dated / labelled / evidence entries
    options: tuple = ()                  # DecisionOption
    actions: tuple = ()
    note: str = ""
    evidence_ids: tuple = ()

    @property
    def is_substantive(self) -> bool:
        """Enough to be worth a heading.

        A single fragment is not. The threshold is deliberately about CONTENT
        rather than character count: an options block with two options is
        substantive at any length, and a paragraph of nine words is not.
        """
        if self.options or self.actions or self.items:
            return True
        words = sum(len(p.split()) for p in self.paragraphs)
        # Six, not ten. "Check whether rails revenue is rising." is a complete
        # next move and a ten-word floor silently dropped it -- which would
        # have removed the one section a founder came for, to enforce a rule
        # meant to catch headings over nothing.
        return bool(self.paragraphs) and words >= 6

    def as_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "kind": self.kind,
            "paragraphs": list(self.paragraphs),
            "items": [i.as_dict() if isinstance(i, EvidenceItem) else i
                      for i in self.items],
            "options": [o.as_dict() for o in self.options],
            "actions": [a if isinstance(a, dict) else a.as_dict()
                        for a in self.actions],
            "note": self.note, "evidence_ids": list(self.evidence_ids),
        }


@dataclass
class Narrative:
    """The whole default screen, as data."""
    company: str = ""
    what_it_does: str = ""
    readiness: str = INVESTIGATION_REQUIRED
    sections: tuple = ()
    version: str = NARRATIVE_VERSION

    def section(self, key: str) -> Optional[Section]:
        for s in self.sections:
            if s.key == key:
                return s
        return None

    @property
    def keys(self) -> tuple:
        return tuple(s.key for s in self.sections)

    def as_dict(self) -> dict:
        return {"version": self.version, "company": self.company,
                "what_it_does": self.what_it_does,
                "readiness": self.readiness,
                "sections": [s.as_dict() for s in self.sections]}


# --- helpers ------------------------------------------------------------------

def _flat(text) -> str:
    return " ".join(str(text or "").split())


def _dedupe(texts) -> List[str]:
    """Same sentence, once.

    Compared on a normalised form, because the repetition this removes is
    "the engagement teaches the workflow" arriving from the mechanism, the
    option assumption and the blind spot with different punctuation each time.
    """
    seen, out = set(), []
    for text in texts:
        text = _flat(text)
        if not text:
            continue
        key = "".join(c for c in text.lower() if c.isalnum())
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _contains(haystack: Sequence[str], needle: str) -> bool:
    """True when `needle` already appears inside something already said."""
    key = "".join(c for c in _flat(needle).lower() if c.isalnum())
    if not key:
        return True
    return any(key in "".join(c for c in _flat(h).lower() if c.isalnum())
               for h in haystack)


def _observation_dicts(report: dict, fallback=()) -> List[dict]:
    obs = [o.as_dict() if hasattr(o, "as_dict") else o
           for o in (report.get("observations") or ())]
    obs = [o for o in obs if isinstance(o, dict)]
    return obs or [o for o in (fallback or ()) if isinstance(o, dict)]


def _hypotheses(report: dict) -> List[dict]:
    out = [h.as_dict() if hasattr(h, "as_dict") else h
           for h in (report.get("hypotheses") or ())]
    return [h for h in out if isinstance(h, dict)]


def _dates_differ(observations: Sequence[dict]) -> bool:
    """Whether the evidence carries a CHRONOLOGY or just a retrieval stamp.

    Every observation on a single run is stamped with the day it was fetched.
    Where that is the only date present, "what changed" is the analysis
    reporting when it ran — which is how one live page listed the same
    sentence under "Business momentum", "Strategic timeline" and "What
    changed", each with today's date, none of it a change.
    """
    dates = {_flat(o.get("date")) for o in observations if _flat(o.get("date"))}
    return len(dates) > 1


def _evidence_index(observations: Sequence[dict]) -> dict:
    return {_flat(o.get("observation_id")): o for o in observations
            if _flat(o.get("observation_id"))}


#: An excerpt is a POINTER to a source, not the source. Past this, a citation
#: stops being scannable and starts being the document.
_EXCERPT_WORDS = 32


def _excerpt(obs: dict) -> str:
    """The most readable thing this observation can show a founder.

    `strategic_signal` is a one-line strategic meaning and `excerpt` is raw
    page text, so the signal is preferred where extraction produced one. Three
    citations on the rich fixture were each a fifty-word keyword dump --
    "commerce infrastructure powering commerce. Shop Pay checkout and buyer
    identity, payments, capital, fulfillment, point of sale..." -- differing
    only in the page name at the front. That is a scraped nav bar wearing
    quotation marks.
    """
    # THE EXCERPT FIRST. `strategic_signal` is a PATTERN-level label, not a
    # per-source one, so several observations carry the identical signal --
    # and preferring it collapsed a thirteen-source citation list to one line,
    # and printed "exposes a surface others can build on" beside a source
    # titled "Basecamp 5 is all new for 2026".
    text = _flat(obs.get("excerpt")) or _flat(obs.get("strategic_signal")) \
        or _flat(obs.get("text"))
    words = text.split()
    if len(words) > _EXCERPT_WORDS:
        text = " ".join(words[:_EXCERPT_WORDS]).rstrip(",;:.") + "…"
    return text


def _evidence_items(ids, index: dict, limit: int = 3) -> List[EvidenceItem]:
    out = []
    seen = SaidOnce()
    for oid in dict.fromkeys(str(i) for i in (ids or ()) if i):
        obs = index.get(oid)
        if not obs:
            continue
        text = _excerpt(obs)
        # Three citations saying the same thing teach a reader nothing after
        # the first, and cost a third of this page's reading budget.
        if not text or seen.has(text):
            continue
        seen.remember(text)
        out.append(EvidenceItem(
            text=text, source_title=_flat(obs.get("source_title")),
            provenance=PROVENANCE_LABEL.get(_flat(obs.get("source_class")),
                                            _DEFAULT_PROVENANCE),
            date=_flat(obs.get("date")), evidence_id=oid))
        if len(out) >= limit:
            break
    return out


# --- section builders ---------------------------------------------------------

def _trim_option(option):
    """One option card, with nothing said twice INSIDE the card.

    Deduplicated within the card and not against the page: the first attempt
    at this on the deck deduplicated against everything already rendered and
    cost option one its upside. An option that cannot say what it wins is a
    worse card than a repetitive one.

    The key assumption is structurally the same sentence as the acting
    option's upside, and as the holding option's description. It is REPLACED
    by a pointer rather than removed -- a reader still has to be told what the
    option rests on, and "That the reading above is the correct one" says it
    without making them read one sentence twice in a single card.
    """
    from dataclasses import replace
    if not option.key_assumption:
        return option
    card = SaidOnce((option.description, option.upside, option.downside))
    if not card.has(option.key_assumption):
        return option
    # Which side this option is on decides which pointer is true. Matching the
    # assumption against the upside gets it wrong: the holding option's upside
    # restates the very alternative it assumes, so both cards read "that the
    # reading above is correct" -- and one of them meant the opposite.
    pointer = ("That the reading stated above is the correct one."
               if option.stance == "act" else
               "That the competing account stated above is the correct one.")
    return replace(option, key_assumption=pointer)

def _executive_answer(company, decision, brief, consequence, supporting,
                      said) -> Section:
    """Two to four complete sentences: what appears to be happening, why it
    matters, and the most important uncertainty.

    This is where the mechanism is STATED. Everything below refers back to it,
    which is why `said` is seeded here and consulted everywhere after.
    """
    paras: List[str] = []
    # The UNKNOWN leads here and the LIMITATION is left for "what could make
    # this wrong". Taking the limitation first emptied that section on every
    # pattern in the library, because the falsifier below it is the same
    # sentence as the next check -- so the page ended up naming what could
    # break the reading nowhere at all.
    unknown = _flat(getattr(brief, "biggest_unknown", "")) or _flat(
        getattr(brief, "biggest_risk", "")) or _flat(decision.limitation)

    if decision.readiness == WITHHELD:
        paras.append(f"No strategic reading of {company} cleared the evidence "
                     f"bar, so none is asserted here.")
        reason = _flat(decision.unsafe_because) or _flat(
            getattr(brief, "withheld_reason", ""))
        if reason:
            paras.append(end_sentence(
                f"That absence is itself the finding: "
                f"{as_clause(reason, company)}"))
            said.remember(reason)
        paras.append("A prospective customer, partner or investor researching "
                     "this company sees exactly what this analysis saw, and "
                     "they will not ask for the rest — they will move on.")
        return Section(EXECUTIVE_ANSWER, "The answer", paragraphs=tuple(paras))

    if decision.mechanism:
        lead = ("Across the public record for "
                f"{company}, {as_clause(decision.mechanism, company)}")
        if decision.readiness == INVESTIGATION_REQUIRED:
            lead = (f"Across the public record for {company}, one reading "
                    f"stands out: {as_clause(decision.mechanism, company)}")
        paras.append(end_sentence(lead))
        said.remember(decision.mechanism)

    if decision.readiness == DECISION_READY:
        # A REAL CONSEQUENCE BEATS THE STRUCTURAL ONE.
        #
        # Live on the preview, Palantir's answer said "it matters because the
        # two courses of action it implies do not cost the same" -- true of
        # every decision ever made, and therefore about no company -- while
        # the section directly below it carried two supported consequences.
        # The fallback is for when there is genuinely nothing better.
        why = next((c for c in (consequence, *supporting) if c
                    and not said.has(c)), "")
        if why:
            paras.append(end_sentence(
                f"That matters because {as_clause(why, company)}"))
            said.remember(why)
        elif len(decision.options) >= 2:
            paras.append(
                f"It matters because the two courses of action it implies do "
                f"not cost the same: {decision.options[0].label} versus "
                f"{lower_first(decision.options[1].label)}.")
    elif decision.unsafe_because:
        paras.append(end_sentence(
            f"It is not yet safe to act on, because "
            f"{as_clause(decision.unsafe_because, company)}"))
        said.remember(decision.unsafe_because)

    if unknown and not said.has(unknown):
        # A colon, not "is that": the limitation arrives as a full clause
        # ("every source here is published by the company itself, so...") and
        # "The largest uncertainty is every source here is published" is not
        # a sentence.
        paras.append(end_sentence(
            f"What most limits this: {as_clause(unknown, company)}"))
        said.remember(unknown)
    return Section(EXECUTIVE_ANSWER, "The answer", paragraphs=tuple(paras))


def _why_now(company, decision, brief, observations, said) -> Section:
    """The strategic trigger, or an honest statement that there is not one.

    A publication date is not a trigger and neither is the newest page title.
    Where every observation carries the same date, that date is when the
    analysis ran, and presenting it as urgency would be the product inventing
    a reason to act now.
    """
    dated = [i for i in (getattr(brief, "what_changed", ()) or ())
             if _flat(i.get("when")) and _flat(i.get("what"))]
    if _dates_differ(observations) and dated:
        item = dated[0]
        said.remember(item["what"])
        return Section(
            WHY_NOW, "Why this matters now",
            paragraphs=(end_sentence(
                f"A dated development moved this: "
                f"{as_clause(item['what'], company)}"),
                f"That is what makes the question live rather than perennial — "
                f"it is recent, it is on the public record as of "
                f"{_flat(item['when'])}, and a competitor or customer "
                f"researching {company} would see it too."))

    paras = ["This is strategically important but not newly urgent. Nothing "
             "in the public record carries a date that marks a change — the "
             "material is dated to when it was read, not to when anything "
             "happened."]
    if decision.readiness != WITHHELD and decision.mechanism:
        paras.append("The question therefore stands on the structure of the "
                     "business rather than on a recent event, which is an "
                     "argument for settling it deliberately rather than "
                     "quickly.")
    return Section(WHY_NOW, "Why this matters now", paragraphs=tuple(paras))


def _what_changed(company, brief, observations, said) -> Section:
    """Concrete dated developments — or the stated absence of any."""
    if not _dates_differ(observations):
        # "Why this matters now" has just said there is no dated trigger, in
        # those words. A second heading explaining the same absence at greater
        # length is the padding this rebuild removes, so the section carries
        # only what the one above did not: that the silence is a limit on the
        # analysis rather than a finding about the company.
        return Section(
            WHAT_CHANGED, "What changed",
            paragraphs=("No dated change could be established — read that as "
                        "a limit on this analysis and not as a finding about "
                        "the company. A change may well have happened where "
                        "nothing published records it.",))
    # The trigger above is drawn from this same list. Repeating it under a
    # second heading is the duplication the dashboard already shipped, where
    # one sentence appeared as "Business momentum", "Strategic timeline" and
    # "What changed" on a single page.
    items = []
    for entry in (getattr(brief, "what_changed", ()) or ()):
        what = _flat(entry.get("what"))
        if not what or said.has(what):
            continue
        said.remember(what)
        items.append({"when": _flat(entry.get("when")), "what": what})
        if len(items) >= 3:
            break
    return Section(WHAT_CHANGED, "What changed", kind="dated",
                   items=tuple(items))


def _business_consequence(company, decision, brief, consequence, statements,
                          said) -> Section:
    """Only the consequences the evidence actually supports, each labelled with
    the part of the business it lands on.

    The mechanism is a candidate of last resort and only survives when the
    answer above did not already state it — a heading called "what this costs"
    over the same sentence the reader met four lines earlier is padding.
    """
    candidates = [c for c in _dedupe([
        consequence,
        *(o.business_consequence for o in decision.options),
        getattr(getattr(brief, "key_insight", None), "so_what", ""),
        *statements,
        decision.mechanism,
    ]) if not said.has(c)]
    items, used = [], set()
    for text in candidates:
        low = text.lower()
        for name, markers in _DIMENSIONS:
            if name in used:
                continue
            if any(m in low for m in markers):
                items.append({"label": name,
                              "text": end_sentence(
                                  text[:1].upper() + text[1:])})
                used.add(name)
                said.remember(text)
                break
        if len(items) >= 4:
            break
    if items:
        return Section(BUSINESS_CONSEQUENCE, "What this costs or wins",
                       kind="labelled", items=tuple(items))
    if candidates:
        said.remember(candidates[0])
        return Section(BUSINESS_CONSEQUENCE, "What this costs or wins",
                       paragraphs=(end_sentence(
                           candidates[0][:1].upper() + candidates[0][1:]),))
    return Section(BUSINESS_CONSEQUENCE, "What this costs or wins")


#: A homepage slogan is not a verified finding. Live on the deployed Basecamp
#: page, "What was verified:" led with "trusted by millions, Basecamp puts
#: everything you need to get work done in one place. It's the calm, organized
#: way to manage projects..." -- the company's own marketing, presented by the
#: product as something it had checked. Where nothing survives this, the line
#: is omitted, which is the honest outcome for a run that verified nothing.
_PROMOTIONAL = (
    "trusted by millions", "everything you need", "the calm,", "loved by",
    "get started free", "try it free", "join thousands", "world's best",
    "#1 ", "award-winning", "all you need", "made simple", "sign up",
)


def _is_promotional(text: str) -> bool:
    low = _flat(text).lower()
    return any(marker in low for marker in _PROMOTIONAL)


def _the_decision(company, decision, said) -> Section:
    """The composed decision in plain language. Never the raw internal topic.

    The headline names the reading when the option labels are generic ("...
    — on whether <mechanism>"). On a deck that tail is essential, because the
    decision slide may be the first one a reader lands on. Here the answer two
    sections above already said it, so the tail is dropped rather than making
    the reader read one sentence twice. The CHOICE itself is never dropped.
    """
    headline = _flat(decision.headline)
    if " — on whether " in headline:
        head, _, tail = headline.partition(" — on whether ")
        if said.has(tail):
            headline = end_sentence(head)
    paras = [headline]
    said.remember(headline)
    if decision.readiness != DECISION_READY and decision.undecided_question:
        paras.append(f"The open question is: {decision.undecided_question}")
        said.remember(decision.undecided_question)
    if decision.readiness == INVESTIGATION_REQUIRED:
        verified = next((v for v in (_flat(x) for x in decision.verified)
                         if v and not said.has(v) and not _is_promotional(v)),
                        "")
        if verified:
            paras.append(end_sentence(
                f"What was verified: {as_clause(verified, company)}"))
            said.remember(verified)
    return Section(THE_DECISION, "The decision this bears on",
                   paragraphs=tuple(p for p in paras if _flat(p)))


def _options(company, decision, said) -> Section:
    """Two real options, or the reason there are not two.

    The trade-off is deliberately allowed to state the mechanism twice — as
    what acting WINS on option one and what waiting COSTS on option two. That
    symmetry is the comparison, not a repetition. What is dropped is the key
    assumption when it is the same sentence as the option's own upside or
    cost, which is a card telling a reader the same thing three times.
    """
    if decision.readiness == DECISION_READY and len(decision.options) >= 2:
        options = tuple(_trim_option(o) for o in decision.options[:2])
        # A WATCH ITEM THE DECISION ALREADY OWNS IS NOT OPTION-SPECIFIC.
        #
        # Both cards carry the same falsification check whenever the pattern
        # states only one, and the acting card's check is always the decision's
        # own falsifier -- which "what to do next" states below and "what to
        # watch" lists again. Left alone, one sentence appeared four times on
        # a single page. A check that genuinely differs between the two
        # options survives, because then it really is telling them apart.
        from dataclasses import replace
        shared = len({_flat(o.watch_item) for o in options}) == 1
        options = tuple(
            replace(o, watch_item="")
            if shared or _flat(o.watch_item) == _flat(decision.falsifier)
            else o
            for o in options)
        for option in options:
            for field_value in (option.upside, option.downside,
                                option.description, option.watch_item):
                if field_value:
                    said.remember(field_value)
        return Section(OPTIONS, "The options, and what each costs",
                       kind="options", options=options)
    paras = []
    if decision.readiness == INVESTIGATION_REQUIRED:
        paras.append("No options are put forward, because a choice between "
                     "one supported course of action and a blank is not a "
                     "choice. What is missing is named below.")
        gap = _flat(decision.evidence_required[0]) \
            if decision.evidence_required else ""
        # "What to do next" states this gap when no falsification check exists,
        # and it renders after this section -- so claiming it here printed the
        # same sentence under two headings on the live bounded page. The more
        # important place keeps it.
        if gap and not SaidOnce([decision.recommended_next_move]).has(gap):
            paras.append(end_sentence(
                f"The evidence that would produce a second option: "
                f"{as_clause(gap, company)}"))
            said.remember(gap)
    elif decision.readiness == WITHHELD:
        paras.append("No options are put forward. Nothing was established "
                     "firmly enough for one course of action to be weighed "
                     "against another, and options built on that would be "
                     "the product inventing a choice.")
        if decision.evidence_required:
            paras.append(end_sentence(
                f"The minimum needed before any of this becomes decidable: "
                f"{as_clause(decision.evidence_required[0], company)}"))
            said.remember(decision.evidence_required[0])
    return Section(OPTIONS, "The options, and what each costs",
                   paragraphs=tuple(paras))


def _next_move(company, decision, said) -> Section:
    """One concrete next action, why it is the safe one, and what settles it.

    `recommendation_reason` is a statement about the EVIDENCE ("all support
    comes from company-owned pages..."), so it is introduced as the reason the
    move is cautious rather than as the reason it is correct. Writing "it is
    the safest move because <evidence weakness>" asserted a causal link the
    data does not carry — visible on the first composed narrative.
    """
    paras = []
    move = _flat(decision.recommended_next_move)
    if move:
        paras.append(move)
        said.remember(move)
    if decision.readiness == DECISION_READY and decision.recommendation_reason \
            and not said.has(decision.recommendation_reason):
        paras.append(end_sentence(
            f"Checking before committing is the cautious order here because "
            f"{as_clause(decision.recommendation_reason, company)}"))
        said.remember(decision.recommendation_reason)
    if decision.what_each_result_would_favour and not said.has(
            decision.what_each_result_would_favour):
        paras.append(decision.what_each_result_would_favour)
        said.remember(decision.what_each_result_would_favour)
    if decision.reconsider_when and not said.has(decision.reconsider_when):
        paras.append(decision.reconsider_when)
        said.remember(decision.reconsider_when)
    elif decision.readiness == DECISION_READY and decision.falsifier:
        paras.append("Revisit this the moment that check returns an answer, "
                     "or sooner if a source outside the company reports on it.")
    return Section(NEXT_MOVE, "What to do next",
                   paragraphs=tuple(p for p in paras if _flat(p)))


# EVIDENCE ROLES ARE THE READING'S, NOT EACH OPTION'S.
#
# The two options carry MIRRORED lineage by construction: what supports acting
# is what the holding option must argue against, so option two's
# `supporting_evidence_ids` are option one's counters. Concatenating across
# both options therefore put every source in both lists, and the first
# composed narrative showed one company page under "What supports this" and
# again, unchanged, under "What argues against it". The roles below are taken
# from the ACTING option and the hypothesis — one reading, one set of roles —
# and the against list is then made disjoint from the for list.

def _decided_hypothesis(decision, hypotheses):
    """The hypothesis the DECISION is about -- not necessarily the top-ranked.

    `decide_across` walks the portfolio: when the best-ranked reading cannot
    state a usable mechanism, the decision is composed on the next one that
    can. Reading evidence off `hypotheses[0]` regardless therefore attributed
    one reading's sources to another reading's decision. Matched by evidence
    lineage, which is the only thing the composed object carries back.
    """
    if not hypotheses:
        return {}
    # The mechanism is derived from a hypothesis's own reasoning, so equality
    # identifies it exactly. Evidence overlap alone did not: hypotheses share
    # observations, so the first overlapping one won -- and the live Hugging
    # Face page argued against "the source of truth still lives elsewhere"
    # while its options were about a second buyer segment.
    from intent_engine.strategic_intelligence.decision import mechanism_sentence
    if decision.mechanism:
        for h in hypotheses:
            if mechanism_sentence(h) == decision.mechanism:
                return h
    owned = set()
    for option in decision.options:
        owned |= set(option.supporting_evidence_ids)
        owned |= set(option.contradicting_evidence_ids)
    if owned:
        for h in hypotheses:
            ids = set(h.get("strongest_support_ids") or ()) \
                | set(h.get("supporting_observation_ids") or ()) \
                | set(h.get("strongest_counter_ids") or ()) \
                | set(h.get("counter_observation_ids") or ())
            if ids & owned:
                return h
    return hypotheses[0]


def _support_ids(decision, hypotheses) -> list:
    # Curated ids FIRST, then that hypothesis's full set. Taking only the
    # curated list left the live Palantir page citing one sentence fragment
    # behind a reading built from thirteen sources -- `strongest_support_ids`
    # is a ranking, not a limit, and is frequently a single entry.
    ids = list(decision.options[0].supporting_evidence_ids) \
        if decision.options else []
    h = _decided_hypothesis(decision, hypotheses)
    ids.extend(h.get("strongest_support_ids") or ())
    ids.extend(h.get("supporting_observation_ids") or ())
    return ids


def _counter_ids(decision, hypotheses) -> list:
    ids = list(decision.options[0].contradicting_evidence_ids) \
        if decision.options else []
    h = _decided_hypothesis(decision, hypotheses)
    ids.extend(h.get("strongest_counter_ids") or ())
    ids.extend(h.get("counter_observation_ids") or ())
    return ids


def _evidence_for(decision, hypotheses, index) -> Section:
    items = _evidence_items(_support_ids(decision, hypotheses), index)
    return Section(EVIDENCE_FOR, "What supports this", kind="evidence",
                   items=tuple(items),
                   evidence_ids=tuple(i.evidence_id for i in items))


def _evidence_against(company, decision, hypotheses, index) -> Section:
    """Counter-evidence and competing accounts, ON the primary page.

    Contradiction hidden behind the evidence viewer is contradiction a reader
    does not weigh. Where the retrieval genuinely found no counter-source,
    that is said here rather than left as a silence that reads like agreement.
    """
    supporting = {i for i in _support_ids(decision, hypotheses)}
    ids = [i for i in _counter_ids(decision, hypotheses) if i not in supporting]
    items = _evidence_items(ids, index)

    alternatives = _dedupe([
        _flat(alt if isinstance(alt, str) else alt.get("text"))
        for alt in (_decided_hypothesis(decision, hypotheses)
                    .get("alternative_explanations") or ())])[:3]

    paras = []
    if alternatives:
        paras.append("The same evidence supports these competing accounts, "
                     "and each one would imply a different course of action:")
    elif not items:
        paras.append("Nothing retrieved argues against this reading — but "
                     "that is a statement about what was retrieved, not a "
                     "second opinion. No customer, competitor or independent "
                     "source was reachable, so the reading stands untested "
                     "rather than confirmed.")
    return Section(EVIDENCE_AGAINST, "What argues against it", kind="evidence",
                   paragraphs=tuple(paras), items=tuple(items),
                   evidence_ids=tuple(i.evidence_id for i in items),
                   note=" | ".join(alternatives))


def _could_be_wrong(company, decision, said) -> Section:
    """The falsifier, phrased so a reader knows which way settles it.

    The falsification entry is a CONDITION that would break the reading
    ("published pricing that assumes no implementation engagement"), so it is
    introduced as the thing to look for. "This is wrong if the opposite of
    this turns out to be true" was the first phrasing, and a double negative
    over a condition is not something a reader can act on.
    """
    paras = []
    if decision.falsifier and not said.has(decision.falsifier):
        paras.append(end_sentence(
            f"Finding this would break the reading: "
            f"{as_clause(decision.falsifier, company)}"))
        said.remember(decision.falsifier)
    if decision.limitation and not said.has(decision.limitation):
        paras.append(end_sentence(
            f"It also rests on evidence with a known hole in it: "
            f"{as_clause(decision.limitation, company)}"))
        said.remember(decision.limitation)
    if not paras:
        # The falsifier and the next check are the same sentence by design,
        # and the limitation is often already the answer's closing line -- so
        # on a rich run this section had nothing left and vanished. A second
        # falsification check, where the pattern states one, is genuinely
        # different material rather than the first one reworded.
        for item in decision.watch_items:
            if said.has(item):
                continue
            paras.append(end_sentence(
                f"The other thing that would break it: "
                f"{as_clause(item, company)}"))
            said.remember(item)
            break
    return Section(COULD_BE_WRONG, "What could make this wrong",
                   paragraphs=tuple(paras))


#: Shapes that describe what the RETRIEVAL lacked, not what a founder could go
#: and observe. Measured live: "What to watch" listed "no investor material,
#: customer account, competitor, independent report has corroborated this yet"
#: and "Whether customers actually moved their source of truth is not
#: observable from outside" -- the second one says outright that it cannot be
#: watched, under a heading promising things to watch.
_NOT_OBSERVABLE = ("is not observable", "not observable from",
                   "has corroborated this", "could not be retrieved",
                   "could not be established", "is not public",
                   "is not disclosed", "no source outside")


def _is_observable(text: str) -> bool:
    low = _flat(text).lower()
    if not low or low.startswith("no "):
        return False
    return not any(marker in low for marker in _NOT_OBSERVABLE)


def _what_to_watch(decision, brief, said) -> Section:
    """Observable indicators, minus the one already named as the falsifier.

    `evidence_required` is included because it is the same kind of thing: a
    named, specific piece of public record whose appearance would move the
    reading. Without it this section emptied on the live Palantir run -- the
    single falsification check was already the next move -- and a page that
    tells a founder to act but not what to keep an eye on is the shorter,
    worse page.
    """
    watch = []
    for text in _dedupe(list(decision.watch_items)
                        + list(decision.evidence_required) + [
            getattr(getattr(brief, "key_insight", None), "watch", "")]):
        if said.has(text) or not _is_observable(text):
            continue
        said.remember(text)
        watch.append(text[:1].upper() + text[1:])
        if len(watch) >= 3:
            break
    return Section(WHAT_TO_WATCH, "What to watch", kind="bullets",
                   items=tuple({"when": "", "what": w} for w in watch))


def _prepared(company, decision, actions, said) -> Section:
    """What the product has drafted from this decision, and what stays manual.

    The customer's question was whether the product researches or does
    something. Each card answers four things in order: what was found, which
    decision it affects, what was prepared, and what the founder does next.
    """
    cards = []
    if decision.readiness == DECISION_READY and len(decision.options) >= 2:
        cards.append({
            "kind": "options_comparison",
            "title": "Options comparison, one page",
            # A back-reference, not the mechanism again: by the time a reader
            # reaches this card the reading has been stated, weighed and
            # cited, and printing it a fourth time is the padding this cycle
            # removes.
            "found": "The reading set out above, with the evidence that "
                     "supports it and the evidence that does not.",
            "decision": f"{decision.options[0].label} versus "
                        f"{lower_first(decision.options[1].label)}.",
            "prepared": (f"A side-by-side of the two, each with its upside, "
                         f"its cost, the assumption it rests on and the "
                         f"sources behind it."),
            "next": "Take it to the next leadership meeting and have each "
                    "side argued by someone who has to live with it.",
        })
    # A BOUNDED RESULT STILL PREPARES SOMETHING.
    #
    # `build_actions` keys everything off `brief.key_insight`, which is absent
    # on exactly the runs that reach INVESTIGATION_REQUIRED and WITHHELD -- so
    # the states that most need direction produced no artefact at all, and the
    # section vanished. The evidence the decision says is missing IS the
    # checklist; it is already named, already specific to this company, and
    # already the thing that would unblock the choice.
    if decision.readiness != DECISION_READY and decision.evidence_required:
        wanted = "; ".join(_flat(e).rstrip(".")
                           for e in decision.evidence_required[:3])
        cards.append({
            "kind": "evidence_request",
            "title": "Evidence request, ready to send",
            "found": "The reading could not be settled on what is public.",
            "decision": decision.undecided_question,
            "prepared": end_sentence(
                f"A numbered request for exactly what is missing: {wanted}"),
            "next": "Send it to whoever can answer it — the company, an "
                    "existing customer, or an analyst who covers them.",
        })
    for action in (actions or ()):
        d = action if isinstance(action, dict) else action.as_dict()
        cards.append({
            "kind": d.get("kind", ""), "title": d.get("title", ""),
            "found": _flat(d.get("intelligence", "")),
            # `why` is why the ARTEFACT is worth having, not which decision it
            # serves. Rendered under "Decision it affects", the risk register
            # read "Decision it affects: it is the single most consequential
            # thing this analysis found that could go wrong" -- which is not a
            # decision, and was measured on the deployed page.
            "why": _flat(d.get("why", "")),
            "prepared": _flat(d.get("recommended_action", "")),
            "next": _flat(d.get("expected_result", "")),
        })

    # These cards come LAST on the page, so anything they restate has already
    # been read -- the decision headline, the mechanism, the open question. A
    # card still has to say which decision it serves, so a repeat becomes a
    # pointer rather than a blank.
    # Only the two CONTEXT rows may collapse. `prepared` and `next` are what
    # the card is and what the founder does with it -- blanking those leaves a
    # titled card that offers nothing, which is worse than a repeat. Measured:
    # the decision memo's "Write up the choice: ..." is the decision headline
    # by construction, so it emptied on every ready run.
    for card in cards:
        for key in ("found", "decision", "why"):
            value = card.get(key, "")
            if value and said.has(value):
                card[key] = ("The choice set out above." if key == "decision"
                             else "")
            elif value:
                said.remember(value)
    return Section(PREPARED, "What this has prepared for you", kind="actions",
                   actions=tuple(cards[:3]),
                   note="Drafted here and nothing more. Nothing is sent, "
                        "published, scheduled or shared without your explicit "
                        "approval.")


# --- assembly -----------------------------------------------------------------

#: Where an outside block sits on the primary screen. AFTER the decision, its
#: options and what could be wrong -- so a reader meets the company's own
#: answer first and outside conditions as context on it. Before it, and the
#: page reads as though the market drove the conclusion, which is exactly the
#: causal misreading market context is dangerous for.
def _outside_conditions(external, said) -> Section:
    """Market, macro and competitive context, only where it changes something.

    ONE BLOCK PER CONTEXT AT MOST, and only the contexts that earned a place.
    A company whose evidence establishes no macro exposure gets no macro
    paragraph -- not an "unavailable" one.

    WRITTEN SHORT ON PURPOSE. The first version carried each block's fact, its
    why-this-matters, its decision AND its limitation, and took a real run
    from 900 words to 1020 -- past the narrative's ceiling. The page's budget
    is the discipline that keeps it readable in one sitting, so the fix was to
    say less here rather than to raise it.

    What survives is the FACT and the DECISION it bears on, which is the pair
    a founder can act on. The non-causal frame moves to the section note,
    stated once for the whole section instead of repeated in every entry, and
    each block's full limitation waits in the Executive Brief and the Full
    Analysis, where there is room to state it properly.
    """
    if external is None or not external.relevant_sections():
        return Section(OUTSIDE, "What is happening outside the company")

    from intent_engine.external_intel import presenter as _pres
    items = []
    for block in _pres.leading_blocks(external):
        if said.has(block.fact):
            continue
        said.remember(block.fact)
        text = block.fact
        if block.decision and not said.has(block.decision):
            said.remember(block.decision)
            text += f" It bears on one choice: {lower_first(block.decision)}"
        items.append({"label": block.title, "text": end_sentence(text)})
    if not items:
        return Section(OUTSIDE, "What is happening outside the company")
    return Section(
        OUTSIDE, "What is happening outside the company", kind="labelled",
        items=tuple(items),
        note=("Outside conditions bound this decision; they do not make it. "
              "A share-price move records what the market expects, not "
              "whether the strategy is working. Each of these is stated with "
              "its full limitation in the executive brief."))


def build_narrative(*, company: str, brief, report: Optional[dict] = None,
                    observations: Optional[Sequence[dict]] = None,
                    decision=None, actions=(), external=None) -> Narrative:
    """The whole default screen, from the one decision and the one brief.

    `decision` is accepted so a caller that already resolved it does not
    resolve it twice; omitted, it is read from the report by the same
    `decision_of` every other surface uses.

    `external` adds outside context ONLY where it bears on the decision, and
    at most one block per context -- market, macro, competitive. This page has
    a reading budget the deep documents do not: a founder reading a 60-second
    answer will not read six more sections, and three sections where one is
    relevant is the padding the whole rebuild exists to remove.
    """
    report = report or {}
    if decision is None:
        decision = decision_of(report)
    elif isinstance(decision, dict):
        decision = decision_from_dict(decision)

    obs = _observation_dicts(report, observations)
    index = _evidence_index(obs)
    hypotheses = _hypotheses(report)

    # A hypothesis STATEMENT is a supported claim about the business and is
    # not the mechanism, so it is real material for the consequence section.
    # Without it that section had one candidate, which the answer above had
    # usually already spent, and a page that names no consequence fails the
    # thing this rebuild exists for.
    statements = _dedupe([_flat(h.get("statement")) for h in hypotheses])[:3]

    consequence = ""
    for spot in (report.get("blind_spots") or ()):
        d = spot.as_dict() if hasattr(spot, "as_dict") else spot
        if isinstance(d, dict) and _flat(d.get("why_it_may_matter")):
            consequence = _flat(d["why_it_may_matter"])
            break

    # ONE MEMORY FOR THE WHOLE PAGE, IN READING ORDER.
    #
    # The page is one screen a reader scrolls, not twelve independent cards,
    # so "have I already said this" spans the whole of it. The builders are
    # called in the order the reader meets them, which is what makes the FIRST
    # statement of an idea the one that survives.
    said = SaidOnce()
    built = [
        _executive_answer(company, decision, brief, consequence,
                          statements, said),
        _why_now(company, decision, brief, obs, said),
        _what_changed(company, brief, obs, said),
        _business_consequence(company, decision, brief, consequence,
                              statements, said),
        _the_decision(company, decision, said),
        _options(company, decision, said),
        _next_move(company, decision, said),
        _evidence_for(decision, hypotheses, index),
        _evidence_against(company, decision, hypotheses, index),
        _could_be_wrong(company, decision, said),
        _outside_conditions(external, said),
        _what_to_watch(decision, brief, said),
        _prepared(company, decision, actions, said),
    ]
    return Narrative(
        company=company, what_it_does=_flat(getattr(brief, "what_it_does", "")),
        readiness=decision.readiness,
        sections=tuple(s for s in built if s.is_substantive))


# --- the comprehension contract ------------------------------------------------

#: What a first-time, non-technical business owner must be able to answer from
#: this page alone -- without paging a deck, opening the full analysis, holding
#: any internal vocabulary, or inferring the action for themselves.
COMPREHENSION_QUESTIONS = (
    "What is happening?",
    "Why does it matter?",
    "What decision is affected?",
    "What options exist?",
    "What should happen next?",
    "What supports the conclusion?",
    "What weakens the conclusion?",
    "What is still unknown?",
    "What has the product prepared?",
)


def comprehension(narrative) -> dict:
    """Which of the nine the page answers, judged on what is VISIBLE.

    Judged from rendered sections rather than from the decision object: a
    field that exists and never reaches the page is exactly the defect this
    module was built for, and an object-level check would have passed the
    version that told founders no conclusion was being asserted.

    Collapsed detail does not count. Nothing on this page is behind a
    disclosure control, and if something is ever put there it stops counting
    here rather than quietly keeping the score.
    """
    present = {s.key for s in narrative.sections if s.is_substantive}
    bounded = narrative.readiness != DECISION_READY
    answers = {
        COMPREHENSION_QUESTIONS[0]: EXECUTIVE_ANSWER in present,
        COMPREHENSION_QUESTIONS[1]: bool(
            present & {BUSINESS_CONSEQUENCE, WHY_NOW, EXECUTIVE_ANSWER}),
        COMPREHENSION_QUESTIONS[2]: THE_DECISION in present,
        # A bounded result answers this by saying, in its own words, why there
        # are no options -- which is an answer. An empty comparison is not.
        COMPREHENSION_QUESTIONS[3]: OPTIONS in present,
        COMPREHENSION_QUESTIONS[4]: NEXT_MOVE in present or bounded and bool(
            present & {OPTIONS, PREPARED}),
        COMPREHENSION_QUESTIONS[5]: EVIDENCE_FOR in present,
        COMPREHENSION_QUESTIONS[6]: bool(
            present & {EVIDENCE_AGAINST, COULD_BE_WRONG}),
        COMPREHENSION_QUESTIONS[7]: bool(
            present & {COULD_BE_WRONG, WHAT_TO_WATCH, EXECUTIVE_ANSWER}),
        COMPREHENSION_QUESTIONS[8]: PREPARED in present,
    }
    unanswered = [q for q, ok in answers.items() if not ok]
    return {"answers": answers, "unanswered": unanswered,
            "passed": not unanswered,
            "answered": sum(1 for ok in answers.values() if ok),
            "of": len(answers)}


# --- rendering ----------------------------------------------------------------

NARRATIVE_CSS = """
<style>
main.nar{max-width:52rem;margin:0 auto;padding:1.5rem 1.15rem 4rem}
.nar h1{font-size:1.7rem;line-height:1.2;margin:.2rem 0 .3rem;
letter-spacing:-.015em}
.nar .does{font-size:1rem;color:var(--muted);margin:0 0 1.1rem;max-width:42rem}
.nar section{padding:1.5rem 0;border-top:1px solid var(--line)}
.nar section:first-of-type{border-top:0;padding-top:.4rem}
.nar h2{font-size:.74rem;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);margin:0 0 .6rem;font-weight:700}
.nar p{margin:0 0 .7rem;max-width:42rem}
.nar section:first-of-type p{font-size:1.14rem;line-height:1.55}
.nar section:first-of-type p:first-child{font-weight:600;font-size:1.24rem;
letter-spacing:-.01em}
.nar .lead{border-left:3px solid var(--accent);padding-left:1.1rem}
.dl{display:grid;gap:.5rem;margin:0}
.dl .row{display:grid;grid-template-columns:11rem 1fr;gap:.9rem;
padding:.55rem 0;border-top:1px solid var(--line)}
.dl .row:first-child{border-top:0}
.dl .k{color:var(--muted);font-size:.82rem;text-transform:uppercase;
letter-spacing:.05em;font-weight:650;padding-top:.15rem}
@media(max-width:680px){.dl .row{grid-template-columns:1fr;gap:.15rem}}
.opts{display:grid;gap:.8rem;grid-template-columns:1fr 1fr;margin:.2rem 0 0}
@media(max-width:820px){.opts{grid-template-columns:1fr}}
.opt{border:1px solid var(--line);border-radius:12px;padding:1rem 1.05rem;
background:var(--card);display:flex;flex-direction:column}
.opt h3{margin:0 0 .5rem;font-size:1.04rem;line-height:1.3}
.opt .tag{display:inline-block;font-size:.68rem;font-weight:700;
text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
margin-bottom:.35rem}
.opt dl{margin:.3rem 0 0}
.opt dt{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;
color:var(--muted);font-weight:700;margin-top:.7rem}
.opt dd{margin:.15rem 0 0;font-size:.94rem}
.opt .up{color:var(--ok)}
.opt .down{color:var(--warn)}
.ev{margin:0;padding:0;list-style:none}
.ev li{border-top:1px solid var(--line);padding:.7rem 0}
.ev li:first-child{border-top:0}
.ev .src{display:block;font-size:.8rem;color:var(--muted);margin-top:.25rem}
.ev .prov{display:inline-block;border:1px solid var(--line);border-radius:999px;
padding:.05rem .5rem;font-size:.72rem;margin-right:.4rem}
.ev q{font-style:normal}
.alts{margin:.4rem 0 0;padding-left:1.1rem}
.alts li{margin:.3rem 0}
.prep{display:grid;gap:.7rem;margin:.2rem 0 0}
.prep .card{margin:0}
.prep h3{margin:0 0 .5rem;font-size:1rem}
.nar .foot{color:var(--muted);font-size:.88rem;margin-top:.6rem}
</style>
"""


def _para(text: str) -> str:
    return f"<p>{_e(text)}</p>" if _flat(text) else ""


def _evidence_link(item: EvidenceItem, run_id: str, labels) -> str:
    label = (labels or {}).get(item.evidence_id) or item.source_title \
        or item.evidence_id
    if not run_id or not item.evidence_id:
        return _e(label)
    return (f'<a href="/runs/{_e(run_id)}/evidence/{_e(item.evidence_id)}">'
            f'{_e(label)}</a>')


def _render_options(options) -> str:
    out = ['<div class="opts">']
    for i, option in enumerate(options, start=1):
        out.append('<div class="opt">')
        out.append(f'<span class="tag">Option {i}</span>')
        out.append(f'<h3>{_e(option.label)}</h3>')
        if option.description:
            out.append(f'<p>{_e(option.description)}</p>')
        out.append("<dl>")
        for label, value, cls in (
                ("Upside", option.upside, "up"),
                ("Cost", option.downside, "down"),
                ("This assumes", option.key_assumption, ""),
                ("Watch", option.watch_item, "")):
            if _flat(value):
                klass = f' class="{cls}"' if cls else ""
                out.append(f"<dt>{_e(label)}</dt>"
                           f"<dd{klass}>{_e(_flat(value))}</dd>")
        out.append("</dl></div>")
    out.append("</div>")
    return "".join(out)


def _render_evidence(section, run_id, labels) -> str:
    out = []
    for para in section.paragraphs:
        out.append(_para(para))
    if section.note:
        out.append('<ul class="alts">')
        out.extend(f"<li>{_e(a)}</li>" for a in section.note.split(" | ") if a)
        out.append("</ul>")
    if section.items:
        out.append('<ul class="ev">')
        for item in section.items:
            out.append("<li>")
            out.append(f'<span class="prov">{_e(item.provenance)}</span>'
                       + (f"<q>{_e(item.text)}</q>" if item.text else
                          '<span class="muted">read in full; no single '
                          'passage is quoted here</span>'))
            out.append(f'<span class="src">'
                       f"{_evidence_link(item, run_id, labels)}</span>")
            out.append("</li>")
        out.append("</ul>")
    return "".join(out)


def render_narrative(narrative, *, run_id: str = "", citation_labels=None,
                     links: bool = True, trailing: str = "") -> str:
    """The whole scrollable screen. One `<main>`, one `<h1>`, headings in order.

    Every section is reached by scrolling. There is no Next button between the
    reader and the answer, and the answer is the first thing under the title.
    """
    out = [NARRATIVE_CSS, '<main class="nar">']
    out.append(f"<h1>{_e(narrative.company)}</h1>")
    if narrative.what_it_does:
        out.append(f'<p class="does">{_e(narrative.what_it_does)}</p>')

    for section in narrative.sections:
        lead = ' class="lead"' if section.key == EXECUTIVE_ANSWER else ""
        out.append(f'<section id="{_e(section.key)}"{lead}>')
        out.append(f"<h2>{_e(section.title)}</h2>")

        if section.kind == "options":
            out.extend(_para(p) for p in section.paragraphs)
            out.append(_render_options(section.options))
        elif section.kind == "evidence":
            out.append(_render_evidence(section, run_id, citation_labels))
        elif section.kind == "labelled":
            out.append('<dl class="dl">')
            for item in section.items:
                out.append(f'<div class="row"><dt class="k">'
                           f'{_e(item["label"])}</dt>'
                           f'<dd>{_e(item["text"])}</dd></div>')
            out.append("</dl>")
        elif section.kind in ("dated", "bullets"):
            out.append('<ul class="ev">')
            for item in section.items:
                when = (f'<span class="src">{_e(item["when"])}</span>'
                        if _flat(item.get("when")) else "")
                out.append(f'<li>{_e(_flat(item["what"]))}{when}</li>')
            out.append("</ul>")
        elif section.kind == "actions":
            out.append('<div class="prep">')
            for card in section.actions:
                out.append('<div class="card"><h3>'
                           f'{_e(card["title"])}</h3><dl class="dl">')
                for label, key in (("What was found", "found"),
                                   ("Decision it affects", "decision"),
                                   ("Why it is worth having", "why"),
                                   ("What it prepared", "prepared"),
                                   ("What you do next", "next")):
                    if _flat(card.get(key)):
                        out.append(f'<div class="row"><dt class="k">'
                                   f'{_e(label)}</dt>'
                                   f'<dd>{_e(_flat(card[key]))}</dd></div>')
                out.append("</dl></div>")
            out.append("</div>")
        else:
            out.extend(_para(p) for p in section.paragraphs)

        if section.note and section.kind != "evidence":
            out.append(f'<p class="foot">{_e(section.note)}</p>')
        out.append("</section>")

    # Content, then the follow-up, then navigation -- in that order and all
    # inside the one `<main>`. Depth links are navigation; a reader who meets
    # them before the answer has been shown a menu instead of a conclusion.
    if trailing:
        out.append(trailing)
    if links and run_id:
        from intent_engine.founder_brief.render import _deeper
        out.append(_deeper(run_id))
    out.append("</main>")
    return "".join(out)

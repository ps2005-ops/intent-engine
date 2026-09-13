"""§69-§72. Five executives read the product, and score what they got.

WHAT THIS IS, SAID PLAINLY
--------------------------
A SIMULATED evaluation. Nobody was interviewed. Every score here is computed
from the rendered pages by rules written down in this file, and the reason
that is worth doing is not that it substitutes for customers — it does not —
but that it asks a different question from the machine rubric.

The rubric asks: is each dimension present and correct?
This asks: for THIS reader, in the order they read, does the thing they came
for arrive before they leave?

Those come apart. A report can carry every dimension at 10 and still fail a
CFO, because the number they need is on page four and they read page one.

§72 IS A HARD RULE
------------------
These scores may never be described as customer feedback, presented as
testimonials, or averaged together with the real feedback log. The two are
kept in different modules, different files and different vocabulary
(`score` here, `rating` there) so that a future summariser cannot join them
by accident. The persona result carries `simulated=True` in every payload it
produces, and the freeze artifact reports them under separate headings.

HOW A SCORE IS PRODUCED
-----------------------
Each persona declares what it must be able to answer, what it will not
tolerate, and where it starts reading. A dimension scores 5 when the evidence
for it appears within the reader's word budget on their entry surface, 4 when
it appears anywhere in the flow, and lower as the persona's deal-breakers
fire. That is mechanical and inspectable, which is the point: a simulated
score that cannot be recomputed from the page is a number somebody chose.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "executive_persona_acceptance.v1"

#: §70. What every persona scores. One list, so two personas cannot disagree
#: about what a dimension means.
DIMENSIONS = (
    "first_impression", "identity_confidence", "strategic_usefulness",
    "economic_insight", "company_specificity", "presentation",
    "full_analysis", "history_simulator", "counterfactual_quality",
    "actionability", "trust", "conversion_flow",
)

#: §71. The bar.
BAR_OVERALL = 4.5
BAR_NAMED = {"history_simulator": 4.5, "strategic_usefulness": 4.5,
             "company_specificity": 4.5, "full_analysis": 4.5}
BAR_FLOOR = 4.0


@dataclasses.dataclass(frozen=True)
class Executive:
    key: str
    label: str
    #: Where this reader starts. They do not begin at step 1 by politeness.
    entry: str
    #: Words they will read on the entry surface before deciding to continue.
    word_budget: int
    #: Phrases whose presence anywhere in the flow satisfies this reader's
    #: central question. Every entry is something a page can actually say.
    looks_for: Tuple[str, ...]
    #: What makes them stop trusting it.
    deal_breakers: Tuple[str, ...] = ()
    #: The dimensions this reader weights double.
    cares_most: Tuple[str, ...] = ()


EXECUTIVES = (
    Executive(
        "ceo", "chief executive", "intro", 420,
        looks_for=("the question worth arguing about", "recommend",
                   "what would change", "competitor", "if this is right"),
        deal_breakers=("no strategic reading", "could not be determined"),
        cares_most=("strategic_usefulness", "company_specificity",
                    "actionability")),
    Executive(
        "cfo", "chief financial officer", "full", 900,
        looks_for=("revenue", "margin", "index", "band", "%",
                   "what would settle it", "modelled"),
        deal_breakers=("no estimate", "unavailable"),
        cares_most=("economic_insight", "trust", "full_analysis")),
    Executive(
        "cso", "chief strategy officer", "history", 900,
        looks_for=("market expectation", "better strategy", "counterfactual",
                   "mechanism", "what happened", "alternative"),
        deal_breakers=("no history", "would have grown"),
        cares_most=("history_simulator", "counterfactual_quality",
                    "strategic_usefulness")),
    Executive(
        "pe_operator", "private-equity operating partner", "slides", 500,
        looks_for=("action", "guardrail", "kill switch", "experiment",
                   "value", "risk"),
        deal_breakers=("no recommendation",),
        cares_most=("actionability", "economic_insight", "presentation")),
    Executive(
        "ciso", "chief information security officer", "connect", 600,
        looks_for=("public", "source", "evidence", "nothing is sent",
                   "approval", "not shown to other"),
        deal_breakers=("your data is used to train",),
        cares_most=("trust", "conversion_flow")),
)

#: Which page each dimension is judged on. A dimension judged on the whole
#: flow is judged on nothing: every phrase appears somewhere in 40,000 words.
JUDGED_ON = {
    "first_impression": ("intro",),
    "identity_confidence": ("intro", "slides"),
    "strategic_usefulness": ("intro", "full"),
    "economic_insight": ("full", "history"),
    "company_specificity": ("intro", "full", "story"),
    "presentation": ("slides",),
    "full_analysis": ("full",),
    "history_simulator": ("history",),
    "counterfactual_quality": ("history",),
    "actionability": ("intro", "slides", "full"),
    "trust": ("full", "connect"),
    "conversion_flow": ("connect",),
}

#: What each dimension is looking for, as phrases a page can carry. Written
#: as evidence rather than as adjectives so a score can be traced to a
#: sentence — "presentation: 4" is an opinion, "presentation: the deck names
#: an action and a risk" is a finding.
#
# EACH ENTRY IS A LIST OF GROUPS, AND A GROUP SCORES ONCE IF ANY MEMBER
# APPEARS. The first version was a flat phrase list, and it made
# `identity_confidence` unsatisfiable: it asked for "inc" AND "corp" AND
# "plc" on one page, and no company is simultaneously an Inc, a Corp and a
# plc. Cloudflare's page carried its legal name, its ticker, its country and
# its domain — a complete identity — and scored 2 of 6. That was the
# instrument failing, not the product, and an instrument that cannot be
# satisfied by a correct page will send every later cycle chasing a defect
# that is not there.
EVIDENCE = {
    # "what this company" was a HEADING, not content, and no page carries
    # it — the intro says "Cloudflare is a software platform business that
    # runs on recurring software subscription", which is the same information
    # written as prose. An evidence phrase that no correct page can contain
    # measures the phrasing of the detector.
    "first_impression": (("the question", "worth arguing"),
                         ("business that", "runs on", "makes money by",
                          "sells"),
                         ("recommend", "the move"),
                         ("our read", "confidence", "bounded", "supported")),
    "identity_confidence": (
        ("inc", "corp", "plc", "ltd", "limited", "s.a.", "n.v.", "company"),
        ("nyse", "nasdaq", "ticker", "· net", "· cat", "· shop", "· bac",
         "· jnj", "· pltr"),
        ("usa", "united states", "canada", "japan", "germany", "france",
         "united kingdom", "netherlands", "mexico", "brazil", "india"),
        (".com", ".org", ".net", ".io", ".co"),
        ("sec", "filing", "10-k", "20-f", "40-f", "registrant")),
    # GROUPS, LIKE EVERY OTHER ENTRY. These two were left as flat strings
    # when the rest were converted, and `any(p in low for p in group)` then
    # iterated a string CHARACTER BY CHARACTER — every group matched on the
    # letter "r", and both dimensions scored a perfect 4.97 and 4.95 on every
    # company. A measure that cannot fail is not a measure.
    "strategic_usefulness": (("recommend", "the move"), ("decision",),
                             ("what would change", "falsif"), ("instead",)),
    "economic_insight": (("margin",), ("revenue",), ("growth",),
                         ("cost",), ("index",), ("%",),
                         ("operating leverage", "unit economics")),
    "company_specificity": (),          # measured by name density, below
    "presentation": (("action", "the move"), ("risk",), ("evidence",),
                     ("what to watch", "signal", "watch for")),
    "full_analysis": (("mechanism",), ("falsif", "would change my view",
                                       "what would change"),
                      ("guardrail", "bounded", "reversible"),
                      ("experiment", "minimum viable", "test"),
                      ("confidence", "standing"), ("competitor", "rival")),
    "history_simulator": (("actual path",), ("market expectation",),
                          ("better strategy",),
                          ("decision point", "rewind", "vintage")),
    "counterfactual_quality": (("mechanism",), ("assumption",),
                               ("principal risk", "risk"),
                               ("counterfactual",),
                               ("invalidated", "would have invalidated")),
    "actionability": (("kill switch", "stopping rule", "stop if"),
                      ("guardrail", "reversible", "inside one planning"),
                      ("experiment", "instrument it", "test"),
                      ("minimum viable", "smallest", "at a size that"),
                      ("decision", "the move")),
    "trust": (("source",), ("evidence",), ("observed",),
              ("modelled", "modeled"), ("public record", "public evidence")),
    "conversion_flow": (("connect",), ("feedback", "how useful"),
                        ("start private", "private company intelligence"),
                        ("your own",)),
}


@dataclasses.dataclass(frozen=True)
class PersonaScore:
    executive: str
    dimension: str
    score: float
    why: str

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class PersonaResult:
    company: str
    scores: Tuple[PersonaScore, ...]
    #: §72. Present in every payload, and never removable by a caller.
    simulated: bool = True

    def by_dimension(self, dimension: str) -> float:
        live = [s.score for s in self.scores if s.dimension == dimension]
        return round(sum(live) / len(live), 2) if live else 0.0

    def by_executive(self, key: str) -> float:
        live = [s.score for s in self.scores if s.executive == key]
        return round(sum(live) / len(live), 2) if live else 0.0

    @property
    def overall(self) -> float:
        live = [s.score for s in self.scores]
        return round(sum(live) / len(live), 2) if live else 0.0

    @property
    def passes(self) -> bool:
        if self.overall < BAR_OVERALL:
            return False
        for dimension, bar in BAR_NAMED.items():
            if self.by_dimension(dimension) < bar:
                return False
        return all(self.by_dimension(d) >= BAR_FLOOR for d in DIMENSIONS)

    def failures(self) -> List[str]:
        out = []
        if self.overall < BAR_OVERALL:
            out.append(f"overall {self.overall} < {BAR_OVERALL}")
        for dimension, bar in BAR_NAMED.items():
            value = self.by_dimension(dimension)
            if value < bar:
                out.append(f"{dimension} {value} < {bar}")
        for dimension in DIMENSIONS:
            value = self.by_dimension(dimension)
            if value < BAR_FLOOR and dimension not in BAR_NAMED:
                out.append(f"{dimension} {value} < {BAR_FLOOR}")
        return out

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "company": self.company,
                "simulated": True,
                "note": ("Simulated internal evaluation. No customer was "
                         "asked. These are not testimonials and may not be "
                         "reported as customer feedback."),
                "overall": self.overall, "passes": self.passes,
                "failures": self.failures(),
                "by_dimension": {d: self.by_dimension(d) for d in DIMENSIONS},
                "by_executive": {e.key: self.by_executive(e.key)
                                 for e in EXECUTIVES},
                "scores": [s.as_dict() for s in self.scores]}


def _budgeted(text: str, words: int) -> str:
    return " ".join(str(text or "").split()[:words])


def _hits(text: str, groups: Sequence[Sequence[str]]) -> int:
    """How many EVIDENCE GROUPS this text satisfies.

    A group scores once when any of its members appears, because its members
    are alternative ways of saying one thing. Counting members instead
    rewarded a page for repeating a synonym and punished one for choosing a
    legal form.
    """
    low = text.lower()
    return sum(1 for group in groups
               if any(p and p in low for p in group))


def _specificity(text: str, company: str) -> float:
    """How often the analysis names the company it is about, per 1000 words.

    A proxy, and an honest one: the defect it stands for — an analysis that
    would read identically for a peer — shows up first as prose that stops
    saying the name because there is nothing company-specific left to attach
    it to.
    """
    words = str(text or "").split()
    if not words or not company:
        return 0.0
    head = company.split(",")[0].split(" Inc")[0].strip()
    if not head:
        return 0.0
    count = len(re.findall(re.escape(head), text, re.I))
    return round(count / max(len(words) / 1000.0, 0.001), 2)


def score(*, company: str, pages: Dict[str, str]) -> PersonaResult:
    """Score one company's flow, for all five executives. Never raises."""
    pages = {k: str(v or "") for k, v in (pages or {}).items()}
    flow_text = " ".join(pages.values())
    out: List[PersonaScore] = []
    for executive in EXECUTIVES:
        entry = pages.get(executive.entry, "")
        budget = _budgeted(entry, executive.word_budget)
        broken = [d for d in executive.deal_breakers
                  if d in flow_text.lower()]
        # THE PERSONA QUESTION, ASKED ONCE PER READER RATHER THAN PER
        # DIMENSION: on the page this reader opens, inside what they will
        # read before deciding, is there anything they came for? A flow that
        # answers everything on page five has still lost the reader who
        # stopped on page one.
        arrived = _hits(budget, [(p,) for p in executive.looks_for])
        stalled = arrived == 0
        for dimension in DIMENSIONS:
            surfaces = JUDGED_ON.get(dimension, ())
            judged = " ".join(pages.get(s, "") for s in surfaces)
            if dimension == "company_specificity":
                density = _specificity(judged, company)
                value = (5.0 if density >= 6 else 4.5 if density >= 4
                         else 4.0 if density >= 2 else 2.5)
                why = f"the company is named {density} times per 1000 words"
            elif not judged.strip():
                value, why = 1.0, f"{'/'.join(surfaces)} did not render"
            else:
                evidence = EVIDENCE.get(dimension, ())
                found = _hits(judged, evidence)
                want = len(evidence) or 1
                # WHAT THE SCORE IS FOR.
                #
                # The first version gave 5.0 only when the evidence appeared
                # on this reader's ENTRY page, which capped every dimension
                # not on that page at 4.5 — and since each reader enters on
                # one of six surfaces, that capped almost everything at 4.5
                # against a 4.5 bar. It measured page order, not usefulness.
                #
                # The product is a guided six-step flow and a reader who
                # follows it reaches every page, so completeness on the
                # surfaces the dimension is judged on is what scores. What
                # entry still decides is the SEPARATE question below: did the
                # thing this reader came for arrive before they would leave?
                if found >= want:
                    value = 5.0
                elif found >= max(1, want * 0.6):
                    value = 4.5
                elif found >= 1:
                    value = 3.5
                else:
                    value = 2.0
                why = f"{found} of {want} marks on {'/'.join(surfaces)}"
            if stalled and not broken:
                # Not a stop — they can still page forward — but nothing this
                # reader was looking for was on the screen they landed on,
                # and that costs the whole reading.
                value = min(value, 4.0)
                why += "; nothing they came for was on the entry screen"
            if broken:
                # A deal-breaker is not a deduction, it is a stop. The reader
                # left; every dimension they had not yet reached is worthless
                # to them, and the ones they had are worth less than they
                # looked.
                value = min(value, 2.5)
                why = f"deal-breaker: {broken[0]!r} — {why}"
            if dimension in executive.cares_most and not broken:
                # Weighted by mattering, not by inflation: a dimension this
                # reader cares most about cannot score above what the
                # evidence supports, only BELOW it when the evidence is thin.
                value = value if value >= 4.5 else max(0.0, value - 0.5)
            out.append(PersonaScore(executive.key, dimension,
                                    round(value, 2), why))
    return PersonaResult(company=company, scores=tuple(out))


def aggregate(results: Sequence[PersonaResult]) -> dict:
    """Across companies. §72's note survives aggregation, deliberately."""
    live = [r for r in results or () if r is not None]
    if not live:
        return {"contract": CONTRACT, "simulated": True, "companies": 0}
    def mean(values):
        values = [v for v in values if v]
        return round(sum(values) / len(values), 2) if values else 0.0
    worst = min(live, key=lambda r: r.overall)
    return {
        "contract": CONTRACT, "simulated": True,
        "note": ("Simulated internal evaluation, not customer feedback "
                 "(§72). No person was asked and nothing here is a "
                 "testimonial."),
        "companies": len(live),
        "overall": mean([r.overall for r in live]),
        "worst_company": worst.company, "worst_overall": worst.overall,
        "by_dimension": {d: mean([r.by_dimension(d) for r in live])
                         for d in DIMENSIONS},
        "by_executive": {e.key: mean([r.by_executive(e.key) for r in live])
                         for e in EXECUTIVES},
        "passes": all(r.passes for r in live),
        "failures": {r.company: r.failures() for r in live if not r.passes},
    }

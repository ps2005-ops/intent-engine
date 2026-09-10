"""The chain from a change in the world to a decision this company has to take.

THE SHAPE
---------
    CHANGE -> MECHANISM -> EXPOSURE -> SECOND ORDER -> COMPETITIVE RESPONSE
           -> CONSEQUENCE -> DECISION

Seven positions, and NOT seven required links. A chain is built as far as the
evidence supports and then stops: three honest links beat five invented ones,
and a missing position is rendered as missing rather than filled with the step
that "must" be there. `stopped_because` says where the evidence ran out, which
is the sentence a reader actually needs.

EVERY EDGE IS LABELLED
----------------------
    EVIDENCED   a retrieved observation says this, and its id is attached
    INFERENCE   it follows from something evidenced plus the structural
                economics of this business model
    HYPOTHESIS  it is a reasonable next step and nothing establishes it

A chain that does not distinguish these is a chain whose weakest link is
invisible, and the weakest link is the whole load-bearing question.

THE GENERICITY DETECTOR
-----------------------
The test is stated as a question a reader can check for themselves: could this
same chain be shown, unchanged, to an unrelated company? `generic_links`
answers it structurally rather than by taste -- a link naming nothing this
company holds, does, sells or depends on could be about anyone, and
`rates -> demand -> revenue` is the canonical case. Flagged links are shown
FLAGGED rather than deleted, because a true-but-generic link is still true
and hiding it would misrepresent how much of the chain is company-specific.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Tuple

CONTRACT = "company_causal_chain.v1"

EVIDENCED = "EVIDENCED"
INFERENCE = "INFERENCE"
HYPOTHESIS = "HYPOTHESIS"

POSITIONS = ("change", "mechanism", "exposure", "second_order",
             "competitive_response", "consequence", "decision")

POSITION_LABEL = {
    "change": "What changed",
    "mechanism": "How it reaches this company",
    "exposure": "What is exposed here",
    "second_order": "What that causes next",
    "competitive_response": "What a competitor does about it",
    "consequence": "What it means strategically",
    "decision": "What management has to decide",
}

#: Words that are long enough to be picked up as "content" and carry none.
#: A company's own self-description contains "that", "this", "with" and
#: "their"; counting them as company vocabulary means any sentence sharing a
#: conjunction reads as company-specific. Measured: a break proof that
#: reverted the prefix rule ran GREEN because the test fixture happened to
#: contain the word "that".
_STOPWORDS = {
    "that", "this", "these", "those", "with", "from", "their", "them",
    "they", "have", "has", "had", "been", "were", "will", "would", "your",
    "you", "our", "ours", "which", "what", "when", "where", "than", "then",
    "into", "over", "under", "about", "after", "before", "because", "each",
    "more", "most", "some", "such", "only", "also", "very", "much", "both",
    "other", "another", "same", "just", "like", "make", "makes", "made",
    "help", "helps", "need", "needs", "want", "wants", "give", "gives",
}

#: Vocabulary that belongs to no company in particular. A link built only out
#: of these is the canonical generic chain.
_MACRO_ONLY = {
    "rates", "rate", "inflation", "demand", "revenue", "growth", "margin",
    "margins", "costs", "cost", "spending", "budgets", "economy", "economic",
    "market", "markets", "customers", "competition", "pressure", "headwind",
    "tailwind", "uncertainty", "macro", "consumer", "enterprise",
}


@dataclasses.dataclass(frozen=True)
class CausalLink:
    position: str
    label: str
    text: str
    standing: str = HYPOTHESIS
    evidence: Tuple[str, ...] = ()
    #: True when this link names nothing specific to this company
    generic: bool = False
    generic_reason: str = ""

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["evidence"] = list(self.evidence)
        return out


@dataclasses.dataclass(frozen=True)
class CausalChain:
    links: Tuple[CausalLink, ...] = ()
    stopped_because: str = ""
    evidence_coverage: float = 0.0
    generic_links: int = 0
    reason: str = ""
    contract: str = CONTRACT

    def __bool__(self) -> bool:
        return bool(self.links)

    @property
    def evidenced(self) -> int:
        return sum(1 for l in self.links if l.standing == EVIDENCED)

    def as_dict(self) -> dict:
        return {"links": [l.as_dict() for l in self.links],
                "stopped_because": self.stopped_because,
                "evidence_coverage": self.evidence_coverage,
                "generic_links": self.generic_links,
                "evidenced": self.evidenced,
                "reason": self.reason, "contract": self.contract}


def _company_vocabulary(profile, company: str) -> set:
    """The words that make a sentence about THIS company rather than any.

    Drawn only from the profile's company-specific facts -- what this company
    says it holds, depends on, sells and is paid for. A class prior does not
    contribute: "recurring software subscription" is true of every
    subscription business, so counting it as company vocabulary would make
    every chain look specific.
    """
    vocab = set()
    for word in re.findall(r"[A-Za-z]{4,}", str(company or "")):
        vocab.add(word.lower())
    for group in ("strategic_assets", "critical_dependencies", "data_assets",
                  "current_strategic_tensions"):
        for fact in (getattr(profile, group, ()) or ()):
            vocab.update(w.lower() for w in
                         re.findall(r"[A-Za-z]{4,}", fact.value))
    for attr in ("customer_job", "economic_engine", "business_model",
                 "technology_exposure", "margin_drivers"):
        fact = getattr(profile, attr, None)
        if fact is not None and getattr(fact, "company_specific", False):
            vocab.update(w.lower() for w in
                         re.findall(r"[A-Za-z]{5,}", fact.value))
    said = getattr(profile, "self_description", None)
    if said is not None and getattr(said, "company_specific", False):
        vocab.update(w.lower() for w in
                     re.findall(r"[A-Za-z]{4,}", said.value))
    return vocab - _MACRO_ONLY - _STOPWORDS


def _is_generic(text: str, vocab: set) -> Tuple[bool, str]:
    """Would this link be true, unchanged, of an unrelated company?

    PREFIX MATCHED, for the reason recorded in `opportunity._genericity_of`:
    an exact match makes "renewal" and "renewed" different words, and marked
    a chain built entirely out of this company's own vocabulary as generic
    because the profile wrote one inflection and the chain wrote the other.
    Measured before the fix: 4 of 7 links on a company-specific chain.
    """
    words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", str(text or ""))]
    if not words:
        return True, "the link carries no content words"
    stems = {w[:5] for w in vocab if len(w) >= 4}
    hits = [w for w in words if w[:5] in stems]
    if hits:
        return False, ""
    macro = [w for w in words if w in _MACRO_ONLY]
    if len(macro) >= 2:
        return True, (
            f"built only out of general economic vocabulary "
            f"({', '.join(sorted(set(macro))[:4])}) and names nothing this "
            f"company holds, sells or depends on -- the same sentence would "
            f"be true of an unrelated business")
    return True, ("names nothing this company holds, sells or depends on, so "
                  "it could be shown unchanged to another company")


def build_causal_chain(*, company: str, profile=None, analysis=None,
                       opportunity=None, lens_selection=None,
                       observations=()) -> CausalChain:
    """Compose the chain from what the run actually established.

    Positions are filled from DIFFERENT producers on purpose. Taking all seven
    from one field would be one sentence cut into seven, which is what a
    template looks like from the inside.
    """
    vocab = _company_vocabulary(profile, company)
    insight = getattr(analysis, "the_insight", None) or {}
    if not isinstance(insight, dict):
        insight = {}
    competitive = getattr(analysis, "competitive", None) or {}
    if not isinstance(competitive, dict):
        competitive = {}
    consequence_chain = [str(s) for s in (insight.get("consequence_chain")
                                          or []) if str(s).strip()]
    citations = tuple(str(c) for c in (insight.get("citations") or []) if c)
    economics = insight.get("economics") or {}
    mechanism = str(economics.get("mechanism") or "") if isinstance(
        economics, dict) else ""

    if not (consequence_chain or mechanism or competitive):
        return CausalChain(
            reason=("No causal chain is shown. The run did not establish a "
                    "mechanism connecting an external change to this "
                    "company, and a chain composed without one would be an "
                    "illustration rather than a finding."),
            stopped_because="no mechanism was established")

    built = []

    def _add(position, text, standing, evidence=()):
        text = " ".join(str(text or "").split())
        if not text:
            return
        generic, why = _is_generic(text, vocab)
        built.append(CausalLink(
            position=position, label=POSITION_LABEL[position], text=text,
            standing=standing, evidence=tuple(evidence),
            generic=generic, generic_reason=why))

    # CHANGE. The first link of the analyst's own chain is the first-order
    # effect; `why_now` is the change that produced it.
    _add("change", insight.get("why_now") or (
        consequence_chain[0] if consequence_chain else ""),
         EVIDENCED if citations else INFERENCE, citations[:2])

    # MECHANISM. How it reaches the financial statements, from the analyst's
    # economics field -- the one place the contract requires a mechanism.
    _add("mechanism", mechanism, EVIDENCED if citations else INFERENCE,
         citations[:2])

    # EXPOSURE. What of THIS company's is in the path. Preferring its own
    # named holdings over the class's macro channels, because a holding is a
    # fact about the company and a channel is a fact about its kind.
    holdings = tuple(getattr(profile, "strategic_assets", ()) or ()) + \
        tuple(getattr(profile, "critical_dependencies", ()) or ())
    if holdings:
        first = holdings[0]
        _add("exposure",
             f"It reaches {company} through {first.value}, which this "
             f"company names as its own in the material that was read.",
             EVIDENCED, ())
    else:
        job = getattr(profile, "customer_job", None)
        if job is not None and getattr(job, "company_specific", False):
            _add("exposure",
                 f"The exposure runs through what customers are actually "
                 f"paying {company} for: {job.value}", INFERENCE, ())
        else:
            channels = tuple(getattr(profile, "macro_exposures", ()) or ())
            if channels:
                _add("exposure",
                     f"No holding of this company's was established, so the "
                     f"exposure is the one its business model carries: "
                     f"{', '.join(c.lower() for c in channels[:3])}.",
                     HYPOTHESIS, ())

    # SECOND ORDER. The middle of the analyst's chain.
    for step in consequence_chain[1:-1][:2]:
        _add("second_order", step, EVIDENCED if citations else INFERENCE,
             citations[:1])

    # COMPETITIVE RESPONSE. From the competitive block, which asks who must
    # respond rather than who exists.
    who = str(competitive.get("who_must_respond") or "")
    if_none = str(competitive.get("if_nobody_responds") or "")
    if who:
        _add("competitive_response",
             f"{who}" + (f" If nobody does: {if_none}" if if_none else ""),
             INFERENCE, ())

    # CONSEQUENCE. The last link of the analyst's chain, or the insight.
    _add("consequence",
         (consequence_chain[-1] if len(consequence_chain) > 1
          else insight.get("sentence") or ""),
         EVIDENCED if citations else INFERENCE, citations[:2])

    # DECISION. The top-ranked opportunity, which is where the map and the
    # chain meet: the chain says why, the map says which.
    if opportunity is not None and opportunity.decision_description:
        _add("decision", opportunity.decision_description,
             EVIDENCED if opportunity.supporting_evidence else INFERENCE,
             opportunity.supporting_evidence[:2])

    if not built:
        return CausalChain(
            reason="Nothing the run established could be placed on a chain.",
            stopped_because="no link could be composed")

    filled = {l.position for l in built}
    missing = [p for p in POSITIONS if p not in filled]
    stopped = ""
    if missing:
        stopped = (
            "The chain stops before "
            + ", ".join(POSITION_LABEL[p].lower() for p in missing[:3])
            + ": the evidence did not carry "
            + ("a competitor who has to respond"
               if "competitive_response" in missing else
               "a further step")
            + ", and a link invented to complete the shape would be the "
              "weakest thing on the page.")

    evidenced = sum(1 for l in built if l.standing == EVIDENCED)
    generic = sum(1 for l in built if l.generic)
    return CausalChain(
        links=tuple(built), stopped_because=stopped,
        evidence_coverage=round(evidenced / float(len(built)), 3),
        generic_links=generic,
        reason=("" if generic == 0 else
                f"{generic} of {len(built)} links name nothing specific to "
                f"this company and are marked as such. A link that would be "
                f"true of an unrelated business is still true; it is just "
                f"not a finding about this one."))

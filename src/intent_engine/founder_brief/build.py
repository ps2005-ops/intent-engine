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


def _sentence(text: str, limit: int = 220) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[:cut.rfind(" ")] + "…" if " " in cut else cut


def build(*, company: str, mode: str, report: Optional[dict] = None,
          observations: Optional[Sequence[dict]] = None,
          market: Optional[dict] = None) -> FounderBrief:
    """Assemble the brief for one company in one mode."""
    report = report or {}
    observations = list(observations or ())

    brief = FounderBrief(company=company, mode=mode)
    brief.what_it_does = _what_it_does(report, observations)

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
    brief.confidence, brief.confidence_reason = _confidence(
        observations, report, brief.key_insight)
    brief.market_context = market
    if not brief.key_insight:
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


def _what_it_does(report: dict, observations: Sequence[dict]) -> str:
    """One plain sentence. Drawn from the company's own description, because
    that is the one thing a marketing site is a reliable source for."""
    for key in ("what_it_does", "offering", "summary", "description"):
        value = report.get(key)
        if isinstance(value, str) and len(value.split()) >= 4:
            return _sentence(value, 180)
    for obs in observations:
        text = obs.get("text") or obs.get("summary") or ""
        if len(text.split()) >= 8:
            return _sentence(text, 180)
    return ""


def _what_changed(observations: Sequence[dict]) -> tuple:
    """Up to three DATED developments, newest first.

    Dated only: an undated item is not a change, it is a fact with no
    before-and-after, and listing it under "what changed" is a small lie that
    compounds across a page.
    """
    dated = [o for o in observations if (o.get("date") or "")[:4].isdigit()]
    dated.sort(key=lambda o: o.get("date", ""), reverse=True)
    out = []
    for obs in dated[:3]:
        text = _sentence(obs.get("text") or obs.get("summary") or "", 160)
        if text:
            out.append({"when": obs.get("date", "")[:10], "what": text,
                        "evidence_id": obs.get("observation_id", "")})
    return tuple(out)


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
            # the TENSION is why a founder should care: two things that cannot
            # both stay true
            so_what=_sentence(
                thesis.get("tension")
                or _first(report.get("decision_implications")), 280),
            # `why_care` is phrased as a real choice ("whether to X vs Y")
            decision=_sentence(
                thesis.get("why_care")
                or _first(report.get("decision_implications")), 240),
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
            so_what=_sentence(
                _first(hypothesis.get("decision_implications"))
                or thesis.get("tension") or "", 280),
            decision=_sentence(
                _first(hypothesis.get("decision_implications"))
                or thesis.get("why_care") or "", 240),
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
    for gap in (report.get("evidence_gaps") or ())[:2]:
        text = gap if isinstance(gap, str) else gap.get("text")
        if text:
            actions.append(_sentence(f"Find out: {text}", 180))
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
    n = len(observations)
    independent = sum(1 for o in observations
                      if o.get("source_class") not in
                      ("company_owned", "executive_statement", None, ""))
    dated = sum(1 for o in observations if (o.get("date") or "")[:4].isdigit())

    if not insight:
        return ("Low", "No conclusion cleared the evidence bar. What follows "
                       "describes what could be verified, not what it means.")
    if independent == 0:
        return ("Low", f"Everything here comes from the company's own "
                       f"material ({n} source(s)). Nothing independent "
                       f"confirms it, so treat it as what the company says "
                       f"about itself.")
    if independent >= 2 and dated >= 3:
        return ("Moderate", f"{independent} independent source(s) and {dated} "
                            f"dated item(s) agree. Still a public-information "
                            f"view — it cannot see inside the business.")
    return ("Low to moderate", f"{independent} independent source(s) and "
                               f"{dated} dated item(s). Thin enough that one "
                               f"new disclosure could change it.")


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

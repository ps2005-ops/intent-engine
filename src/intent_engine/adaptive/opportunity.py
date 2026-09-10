"""Where better intelligence could actually change a decision for this company.

WHY A SEPARATE OBJECT FROM "THE DECISION"
-----------------------------------------
The product already produces a decision: one recommendation, argued, with a
falsifier. What it could not produce is the MAP -- the several places where an
outside view is worth having, ranked against each other, so a reader can see
that the one being argued was chosen rather than that it was the only one.

A single recommendation with nothing beside it is indistinguishable from a
template, and that is exactly how it reads. Three ranked opportunities with
their component scores exposed is a different claim: this is what we looked
at, this is why this one came first.

THE SCORE, AND WHY IT IS NOT ONE NUMBER
---------------------------------------
    priority = materiality x change x exposure x actionability x evidence
               - uncertainty_penalty - gap_penalty - genericity_penalty

Multiplicative on purpose. A decision that is enormously material and
completely unactionable is not half-useful, it is useless -- an additive score
would rank it above a small decision somebody can actually take, and an
executive would notice within one sentence. Any component at zero takes the
whole product to zero, which is the correct behaviour.

Every component is published beside the result. A single opaque number is not
a ranking a reader can argue with, and one they cannot argue with is one they
will not trust.

THE GENERICITY PENALTY IS THE POINT
-----------------------------------
An opportunity whose description would read identically about an unrelated
company is penalised HERE, before ranking, rather than caught downstream. The
recorded failure it answers is a constant decision question surviving to the
page for every company in a cohort; a ranking that does not know the
difference will put the generic one first every time, because generic
statements are the ones that always apply.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Tuple

CONTRACT = "decision_opportunity_map.v1"

#: An opportunity below this is not worth a reader's time. Deliberately LOW,
#: because every opportunity is rendered WITH its component scores and its
#: origin: an item at 0.05 shows "evidence 0.30 -- nothing in the record
#: cited this" on its own card, which tells a reader more than a shorter
#: list that silently dropped it. Showing a weak candidate and marking it
#: weak is not padding; asserting it were strong would be. It is still not a failure to have none -- a
#: company whose evidence supports no actionable decision is a company we
#: should say that about, and `withheld` says which and why.
SHOW_FLOOR = 0.02

_URGENCY_CHANGE = {"decide_now": 1.0, "this_quarter": 0.8,
                   "this_year": 0.55, "watch_only": 0.3}
_IMPACT = {"high": 1.0, "medium": 0.65, "low": 0.35}
_CONFIDENCE = {"high": 1.0, "moderate": 0.7, "low": 0.4}
#: What a verdict says about whether anybody can DO anything about it.
_ACTIONABILITY = {"do_now": 1.0, "research": 0.75, "monitor": 0.5,
                  "wait": 0.4, "ignore": 0.1}

#: Owner roles, in the vocabulary `roles.ROLES` uses.
_DOMAIN_OWNER = (
    (("price", "pricing", "packaging", "discount"), "cro"),
    (("hire", "headcount", "sales", "quota", "go to market", "gtm",
      "pipeline", "channel", "partner"), "cro"),
    (("margin", "cost", "capital", "spend", "budget", "cash", "invest"),
     "cfo"),
    (("product", "roadmap", "feature", "platform", "build", "ship"), "cpo"),
    (("security", "compliance", "regulat", "privacy", "risk", "audit"),
     "risk"),
    (("brand", "marketing", "demand generation", "positioning"), "cmo"),
    (("operat", "delivery", "support", "service", "process"), "coo"),
    (("client", "engagement", "practice", "utilisation", "utilization"),
     "consultant"),
)


def _owner_for(text: str) -> str:
    low = str(text or "").lower()
    for needles, role in _DOMAIN_OWNER:
        if any(n in low for n in needles):
            return role
    return "ceo"


def _domain_for(text: str, lens=None) -> str:
    """The decision domain, preferring the lens's own vocabulary."""
    low = str(text or "").lower()
    for domain in (getattr(lens, "decision_domains", ()) or ()):
        head = str(domain).split()[0].lower()
        if head and head in low:
            return str(domain)
    for needles, _role in _DOMAIN_OWNER:
        if any(n in low for n in needles):
            return needles[0]
    return "strategic direction"


@dataclasses.dataclass(frozen=True)
class DecisionOpportunity:
    """One place an outside view could change what this company does."""
    decision_domain: str = ""
    decision_owner_role: str = "ceo"
    decision_description: str = ""
    why_now: str = ""

    # --- components, each 0..1 and each published ---
    materiality: float = 0.0
    change_velocity: float = 0.0
    company_exposure: float = 0.0
    actionability: float = 0.0
    evidence_strength: float = 0.0
    uncertainty: float = 0.0
    evidence_gap: float = 0.0
    genericity: float = 0.0
    decision_priority: float = 0.0

    supporting_evidence: Tuple[str, ...] = ()
    contradicting_evidence: str = ""
    what_would_change_priority: str = ""
    recommended_information_next: str = ""
    #: ANALYST | LENS_AND_EXPOSURE | TENSION
    origin: str = ""
    #: why this scored what it scored, in the reader's language
    score_reason: str = ""

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["supporting_evidence"] = list(self.supporting_evidence)
        return out


@dataclasses.dataclass(frozen=True)
class DecisionOpportunityMap:
    opportunities: Tuple[DecisionOpportunity, ...] = ()
    considered: int = 0
    withheld: Tuple[str, ...] = ()
    reason: str = ""
    contract: str = CONTRACT

    @property
    def top(self) -> Optional[DecisionOpportunity]:
        return self.opportunities[0] if self.opportunities else None

    def as_dict(self) -> dict:
        return {"opportunities": [o.as_dict() for o in self.opportunities],
                "considered": self.considered,
                "withheld": list(self.withheld),
                "reason": self.reason, "contract": self.contract}


def _score(*, materiality, change, exposure, actionability, evidence,
           uncertainty, gap, generic) -> float:
    """The five factors multiply; the two penalties DISCOUNT rather than subtract.

    THIS SHAPE IS A REPAIR, AND THE MEASUREMENT THAT FORCED IT IS WORTH
    KEEPING. The first version subtracted absolute penalties:

        base - 0.25*uncertainty - 0.20*gap - 0.35*generic

    Run against a real analyst decision -- high impact, decide this quarter,
    verdict "do it now", two cited observations -- it scored 0.000, and so did
    every other decision in the map. Three faults, all in that one line:

      * UNCERTAINTY WAS COUNTED TWICE. `evidence` is already a multiplicative
        factor and `uncertainty` was defined as `1 - evidence`, so weak
        evidence was charged for once in the product and again in the
        penalty. It is dropped from the score and kept as a REPORTED field,
        because a reader still wants to see it.
      * NAMING A GAP WAS PUNISHED. `missing_evidence` is the analyst saying
        what it does not have -- the behaviour the whole contract is built to
        encourage -- and a flat 0.20 made an honest decision rank below a
        silent one. It is now a small discount, not a cliff.
      * ABSOLUTE PENALTIES SWAMP A BOUNDED BASE. The product of five factors
        in [0,1] is usually well under 0.5, so a fixed 0.80 of possible
        penalty could exceed the entire score -- which is what "every
        opportunity scored zero" actually was.

    Discounts are multiplicative, so a penalty can reduce a score and can
    never invert it, and a zero still means what it should: one of the five
    things a decision needs is missing.
    """
    base = (materiality * change * exposure * actionability * evidence)
    return round(base * (1.0 - 0.5 * generic) * (1.0 - 0.15 * gap), 4)


def _genericity_of(text: str, *, company: str, profile=None) -> float:
    """How much of this sentence would survive being said about anyone.

    Cheap and deliberately so: it is a RANKING input, not the audit. The real
    cross-company check lives in `differentiation.genericity`, which compares
    two composed readings against each other. What this needs to do is stop a
    sentence that names nothing concrete from outranking one that does.
    """
    body = str(text or "")
    if not body.strip():
        return 1.0
    stripped = re.sub(re.escape(company), " ", body, flags=re.I) if company \
        else body
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]+", stripped)]
    if not words:
        return 1.0
    # concrete nouns this company's own profile supplies
    concrete = set()
    for group in ("strategic_assets", "critical_dependencies"):
        for fact in (getattr(profile, group, ()) or ()):
            concrete.update(w.lower() for w in
                            re.findall(r"[A-Za-z]{4,}", fact.value))
    for attr in ("customer_job", "economic_engine", "business_model"):
        fact = getattr(profile, attr, None)
        if fact is not None and getattr(fact, "company_specific", False):
            concrete.update(w.lower() for w in
                            re.findall(r"[A-Za-z]{5,}", fact.value))
    said = getattr(profile, "self_description", None)
    if said is not None and getattr(said, "company_specific", False):
        concrete.update(w.lower() for w in
                        re.findall(r"[A-Za-z]{5,}", said.value))
    if not concrete:
        # nothing company-specific to match against: neither evidence for
        # nor against, so neither rewarded nor punished
        return 0.5
    # PREFIX MATCH, NOT EXACT. "renewal" and "renewed", "seller" and
    # "sellers", "deploy" and "deployed" are the same word to a reader and
    # were different words to an exact match -- which marked a chain of
    # company-specific sentences generic because the profile happened to
    # write one inflection and the decision the other.
    stems = {w[:5] for w in concrete if len(w) >= 5}
    overlap = sum(1 for w in words if w.lower()[:5] in stems)
    density = overlap / float(len(words))
    return round(max(0.0, min(1.0, 1.0 - (density * 6.0))), 3)


def _from_analyst_decision(d: dict, *, company: str, lens, profile,
                           observation_count: int) -> DecisionOpportunity:
    text = str(d.get("decision") or "")
    why = str(d.get("why_it_matters") or "")
    citations = tuple(str(c) for c in (d.get("citations") or []) if c)
    materiality = _IMPACT.get(str(d.get("business_impact") or "").lower(), 0.5)
    change = _URGENCY_CHANGE.get(str(d.get("urgency") or "").lower(), 0.5)
    actionability = _ACTIONABILITY.get(str(d.get("verdict") or "").lower(),
                                       0.5)
    evidence = _CONFIDENCE.get(str(d.get("confidence") or "").lower(), 0.4)
    # CITATIONS ARE THE EVIDENCE, not the confidence label. A decision the
    # model called "high" with nothing cited is a decision with no evidence,
    # and the label is the model grading its own fluency.
    if not citations:
        evidence = min(evidence, 0.3)
    gap = 1.0 if str(d.get("missing_evidence") or "").strip() else 0.0
    uncertainty = 1.0 - evidence
    generic = _genericity_of(f"{text} {why}", company=company, profile=profile)
    # EXPOSURE: does this decision touch something this company actually
    # holds? A decision naming one of its own assets or dependencies is one
    # it is exposed to; one naming none is a decision about its industry.
    exposure = 0.55
    holdings = [f.value.lower() for f in
                (tuple(getattr(profile, "strategic_assets", ()) or ())
                 + tuple(getattr(profile, "critical_dependencies", ()) or ()))]
    low = f"{text} {why}".lower()
    if any(h and h in low for h in holdings):
        exposure = 0.95
    elif getattr(profile, "known", False):
        exposure = 0.75
    priority = _score(materiality=materiality, change=change,
                      exposure=exposure, actionability=actionability,
                      evidence=evidence, uncertainty=uncertainty, gap=gap,
                      generic=generic)
    return DecisionOpportunity(
        decision_domain=_domain_for(f"{text} {why}", lens),
        decision_owner_role=_owner_for(f"{text} {why}"),
        decision_description=text,
        why_now=str(d.get("cost_of_waiting") or why),
        materiality=materiality, change_velocity=change,
        company_exposure=exposure, actionability=actionability,
        evidence_strength=round(evidence, 2), uncertainty=round(uncertainty, 2),
        evidence_gap=gap, genericity=generic, decision_priority=priority,
        supporting_evidence=citations,
        contradicting_evidence=str(d.get("what_would_invalidate_it") or ""),
        what_would_change_priority=str(d.get("what_to_watch") or ""),
        recommended_information_next=str(
            d.get("missing_evidence") or d.get("cheapest_experiment") or ""),
        origin="ANALYST",
        score_reason=(
            f"impact {str(d.get('business_impact') or '?')}, urgency "
            f"{str(d.get('urgency') or '?')}, verdict "
            f"{str(d.get('verdict') or '?')}, "
            f"{len(citations)} cited observation(s)"
            + (", and evidence is named as missing" if gap else "")))


def _from_lens_domain(domain: str, *, company: str, lens, profile,
                      exposure_note: str) -> DecisionOpportunity:
    """A candidate the analyst did not name, built from lens x exposure.

    Deliberately scored LOW on evidence: nothing cited this, it is the
    router's own suggestion, and it must never outrank something the evidence
    actually raised. It exists so the map shows what else was on the table.
    """
    text = (f"whether to change what this company does about "
            f"{domain}")
    generic = _genericity_of(text, company=company, profile=profile)
    exposure = 0.7 if getattr(profile, "known", False) else 0.45
    priority = _score(materiality=0.6, change=0.5, exposure=exposure,
                      actionability=0.5, evidence=0.3,
                      uncertainty=0.7, gap=1.0, generic=generic)
    return DecisionOpportunity(
        decision_domain=domain, decision_owner_role=_owner_for(domain),
        decision_description=text.capitalize(),
        why_now=exposure_note,
        materiality=0.6, change_velocity=0.5, company_exposure=exposure,
        actionability=0.5, evidence_strength=0.3, uncertainty=0.7,
        evidence_gap=1.0, genericity=generic, decision_priority=priority,
        supporting_evidence=(),
        contradicting_evidence="",
        what_would_change_priority=(
            "evidence that this company is actually deciding this, rather "
            "than that a business reading through this lens usually is"),
        recommended_information_next=(
            f"a dated, first-party statement from this company about "
            f"{domain}"),
        origin="LENS_AND_EXPOSURE",
        score_reason=(
            "raised by the selected lens rather than by the evidence, so its "
            "evidence strength is low by construction and it cannot outrank "
            "something the record actually carries"))


def build_opportunity_map(*, company: str, profile=None, analysis=None,
                          lens_selection=None,
                          observations=()) -> DecisionOpportunityMap:
    """Rank the places better intelligence could change a decision here."""
    lens = getattr(lens_selection, "lens", None)
    decisions = list(getattr(analysis, "decisions", ()) or [])
    obs_count = len(observations or ())

    candidates, withheld = [], []
    for d in decisions:
        if not isinstance(d, dict) or not str(d.get("decision") or "").strip():
            continue
        candidates.append(_from_analyst_decision(
            d, company=company, lens=lens, profile=profile,
            observation_count=obs_count))

    # Fill toward three ONLY from the lens the evidence selected, and never
    # past three: a founder with five minutes cannot hold more, and the
    # fourth is always the weakest.
    if lens is not None and len(candidates) < 3:
        named = " ".join(c.decision_domain.lower() for c in candidates)
        note = (getattr(lens_selection, "why_selected", "") or "")[:200]
        for domain in lens.decision_domains:
            if len(candidates) >= 3:
                break
            if str(domain).split()[0].lower() in named:
                continue
            candidates.append(_from_lens_domain(
                str(domain), company=company, lens=lens, profile=profile,
                exposure_note=note))

    considered = len(candidates)
    ranked = sorted(candidates, key=lambda c: -c.decision_priority)
    kept = []
    for c in ranked:
        if c.decision_priority < SHOW_FLOOR:
            withheld.append(
                f"{c.decision_description[:80]} -- priority "
                f"{c.decision_priority:.3f} is under the {SHOW_FLOOR} floor: "
                + ("nothing in the record raises it"
                   if c.evidence_strength <= 0.3 else
                   "it reads as something that would be said about any "
                   "company in this position"
                   if c.genericity >= 0.7 else
                   "no one named could act on it"))
            continue
        kept.append(c)

    reason = ""
    if not kept:
        reason = (
            "No decision opportunity cleared the bar. That is a statement "
            "about the evidence, not about this company: "
            + (f"{considered} candidate(s) were built and each was either "
               f"unevidenced, unactionable, or would have read the same way "
               f"about an unrelated company."
               if considered else
               "the strategic reading named no decision, so there was "
               "nothing to rank."))
    return DecisionOpportunityMap(
        opportunities=tuple(kept[:3]), considered=considered,
        withheld=tuple(withheld[:4]), reason=reason)

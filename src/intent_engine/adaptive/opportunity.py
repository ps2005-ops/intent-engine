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

from intent_engine.adaptive.spans import trim_to_word

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


#: The three states this map can honestly be in.
DECISION_READING = "DECISION_READING"      #: the evidence raised real ones
POTENTIAL_DOMAINS = "POTENTIAL_DOMAINS"    #: we know where, not what
NOTHING = "NOTHING"                        #: not even a lens to reason from


@dataclasses.dataclass(frozen=True)
class DecisionOpportunityMap:
    """Ranked opportunities, or the areas a reading of this company suggests.

    `state` is the field every renderer must branch on. An empty
    `opportunities` tuple is NOT the same fact as an empty map: the first
    means "we understand this company and cannot yet say what to do", the
    second means "we could not get far enough to say even that", and showing
    the same card for both is what makes a product look broken when it is
    being careful.
    """
    opportunities: Tuple[DecisionOpportunity, ...] = ()
    domains: Tuple["PotentialDomain", ...] = ()
    state: str = NOTHING
    considered: int = 0
    withheld: Tuple[str, ...] = ()
    reason: str = ""
    #: what the evidence lacked, in the reader's language
    evidence_limitation: str = ""
    #: what would move this from POTENTIAL_DOMAINS to DECISION_READING
    what_would_unlock_a_decision: str = ""
    contract: str = CONTRACT

    @property
    def top(self) -> Optional[DecisionOpportunity]:
        return self.opportunities[0] if self.opportunities else None

    @property
    def has_reading(self) -> bool:
        return self.state == DECISION_READING

    def as_dict(self) -> dict:
        return {"opportunities": [o.as_dict() for o in self.opportunities],
                "domains": [d.as_dict() for d in self.domains],
                "state": self.state,
                "considered": self.considered,
                "withheld": list(self.withheld),
                "reason": self.reason,
                "evidence_limitation": self.evidence_limitation,
                "what_would_unlock_a_decision":
                    self.what_would_unlock_a_decision,
                "contract": self.contract}


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


@dataclasses.dataclass(frozen=True)
class PotentialDomain:
    """An area worth investigating. NOT a recommendation, and labelled so.

    WHY THIS IS A DIFFERENT TYPE FROM `DecisionOpportunity`, and not a
    low-scoring one.

    These used to be built as opportunities with a deliberately low evidence
    score, ranked against real ones, and then withheld under the floor. That
    produced the worst of both: a card that said "no decision opportunity
    cleared the bar" followed by three lines of what had been rejected --
    an empty state dressed as a finding, on the screen that matters most.

    The distinction the product actually needs is not a score. It is a
    KIND. Knowing what sort of business this is tells you which decisions
    tend to matter for a business like it; it does not tell you what THIS
    management should do. A type that cannot be ranked beside a real
    opportunity is how that stays true no matter who renders it.
    """
    domain: str
    owner_role: str = "ceo"
    why_it_could_matter: str = ""
    what_would_make_it_a_recommendation: str = ""
    #: the lens that raised it, so the reader can see it is derived
    raised_by: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _potential_domain(domain: str, *, lens, lens_name: str,
                      profile, own_words=()) -> PotentialDomain:
    """One area worth investigating, in THIS company's own vocabulary.

    `own_words` are the phrases from this company's own material that
    selected the lens. Without them, two companies sharing a lens received
    byte-identical domain cards -- measured on BigID and Cyera, both
    correctly routed to data security and governance and both shown the same
    three sentences. The lens is genuinely the same; what each company says
    about itself is not, and the card should show the difference it has
    rather than the one it does not.
    """
    model = str(getattr(profile, "business_model_class", "") or "")
    pretty = model.replace("_", " ").lower() if model != "UNKNOWN" else ""
    words = [w for w in own_words if w][:3]

    # THE LENS'S VOCABULARY IS NOT THE COMPANY'S, AND USING IT HERE IS
    # CIRCULAR. `own_words` are the phrases the lens searched for and found;
    # two companies routed to the same lens will, by construction, tend to
    # have matched the same highest-weighted ones. Measured on their real
    # sites: BigID and Cyera both fired "dspm, sensitive data, data
    # governance" as their top three, so every domain card was identical --
    # while their own sentences about themselves have nothing in common.
    #
    # So the company's OWN description comes first, its named dependencies
    # second, and the lens vocabulary only when it has neither.
    said = getattr(profile, "self_description", None)
    deps = tuple(getattr(profile, "critical_dependencies", ()) or ())
    distinguishing = ""
    if said is not None and said.value:
        clause = said.value.rstrip(".")
        distinguishing = (clause.split(" is ", 1)[-1] if " is " in clause
                          else clause)
    elif deps:
        distinguishing = f"a business built on {deps[0].value}"
    return PotentialDomain(
        domain=str(domain), owner_role=_owner_for(str(domain)),
        # ONE SENTENCE, AND IT IS THIS COMPANY'S. The lens rationale is
        # stated ONCE at the section level; repeating it on all three cards
        # put the same sentence on the page three times per company and six
        # times across any two companies sharing a lens -- which is what the
        # collapse detector was reporting for BigID and Cyera.
        why_it_could_matter=(
            (f"It describes itself as {distinguishing}, which is what puts "
             f"{domain} in scope."
             if distinguishing else
             f"Its own material is about " + ", ".join(words) + ", which is "
             f"what puts {domain} in scope."
             if words else
             f"A {pretty} business usually has something at stake in "
             f"{domain}." if pretty else
             f"This is an area {lens_name.lower()} treats as material.")),
        what_would_make_it_a_recommendation=(
            f"a dated, first-party statement from this company about "
            f"{domain}, or a third-party account of it -- at present nothing "
            f"in the retrieved record raises it"),
        raised_by=lens_name)


def build_opportunity_map(*, company: str, profile=None, analysis=None,
                         lens_selection=None,
                         observations=(),
                         evidence_limitation: str = ""
                         ) -> DecisionOpportunityMap:
    """Rank what the evidence raised; name what it did not.

    Returns one of three states and never blends them. The old behaviour --
    build lens-derived candidates, score them low, rank them beside real ones
    and then withhold them under a floor -- produced a card reading "no
    decision opportunity cleared the bar" followed by the rejects. That is an
    empty state wearing the clothes of a finding.
    """
    lens = getattr(lens_selection, "lens", None)
    lens_name = str(getattr(lens_selection, "primary_name", "") or "")
    decisions = list(getattr(analysis, "decisions", ()) or [])

    candidates, withheld = [], []
    for d in decisions:
        if not isinstance(d, dict) or not str(d.get("decision") or "").strip():
            continue
        candidates.append(_from_analyst_decision(
            d, company=company, lens=lens, profile=profile,
            observation_count=len(observations or ())))

    considered = len(candidates)
    ranked = sorted(candidates, key=lambda c: -c.decision_priority)
    kept = []
    for c in ranked:
        if c.decision_priority < SHOW_FLOOR:
            withheld.append(
                f"{trim_to_word(c.decision_description, 80)} -- priority "
                f"{c.decision_priority:.3f} is under the {SHOW_FLOOR} floor: "
                + ("nothing in the record cites it"
                   if c.evidence_strength <= 0.3 else
                   "it reads as something that would be said about any "
                   "company in this position"
                   if c.genericity >= 0.7 else
                   "no one named could act on it"))
            continue
        kept.append(c)

    if kept:
        return DecisionOpportunityMap(
            opportunities=tuple(kept[:3]), state=DECISION_READING,
            considered=considered, withheld=tuple(withheld[:4]))

    # NO DECISION READING. Two different facts follow, and they are not the
    # same product state.
    if lens is not None:
        fired = ()
        for score in (getattr(lens_selection, "scores", ()) or ()):
            if score.lens_id == getattr(lens_selection, "primary", ""):
                fired = tuple(phrase for phrase, _w in score.fired[:4])
                break
        domains = tuple(
            _potential_domain(d, lens=lens, lens_name=lens_name,
                              profile=profile, own_words=fired)
            for d in lens.decision_domains[:3])
        return DecisionOpportunityMap(
            domains=domains, state=POTENTIAL_DOMAINS,
            considered=considered, withheld=tuple(withheld[:4]),
            reason=(
                f"We can say what KIND of decisions matter for a company "
                f"like this one. We cannot yet say what this management "
                f"should do about them"
                + (f", because {considered} candidate decision(s) were built "
                   f"from the evidence and none of them cited enough of it"
                   if considered else
                   ", because the retrieved record raised none")
                + "."),
            evidence_limitation=(
                evidence_limitation
                or "the run did not retrieve enough independent material to "
                   "test this company's own account of itself"),
            what_would_unlock_a_decision=(
                "a dated, third-party account of something this company has "
                "actually decided or changed -- a filing, a customer or "
                "competitor statement, or reporting that is not the "
                "company's own"))

    return DecisionOpportunityMap(
        state=NOTHING, considered=considered, withheld=tuple(withheld[:4]),
        reason=(
            "No decision reading and no decision domains. This company's own "
            "published material did not say clearly enough what it is for, "
            "so there is no basis even for saying which decisions would "
            "matter."),
        evidence_limitation=(
            evidence_limitation
            or "what kind of business this is was not established"),
        what_would_unlock_a_decision=(
            "one page or filing stating what this company sells and how it "
            "is paid"))

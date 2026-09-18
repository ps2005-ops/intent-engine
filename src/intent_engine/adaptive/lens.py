"""Which strategic lens this company's evidence selects, and which it refuses.

WHY NOT ROUTE BY INDUSTRY
-------------------------
Eight of the ten companies this phase qualifies against are the same business
model class -- subscription software -- and routing on the class would hand
all eight the same analysis, which is the collapse the whole phase exists to
end. It would also be a `class prior` standing in for an answer, the recorded
failure where per-class business-model text made five software companies
byte-identical.

What separates them is not how they are paid. It is WHAT DECISION their
customers are buying help with, and every one of them states that in its own
published material: a sales-enablement vendor writes about quota, ramp and
pipeline; a data-governance vendor writes about discovery, retention and
regulation. Those are different worlds with the same P&L shape.

So the lens is routed on:

    business model  (applicability -- can this lens describe a business of
                     this kind at all)
  + the subject's own evidence   (activation -- what this company says it is
                     for)
  + exposures       (what actually reaches it)
  + decision opportunity  (where intelligence could change something)

APPLICABILITY IS NOT OPTIONAL
-----------------------------
A library entry that fires on signal names alone reaches the wrong kind of
company -- recorded, and the reason `eligible_business_models` is a hard gate
rather than a weight. `Supply Chain & External Shock` may score highly on a
software company writing about "supply chain security"; it is refused there
because a business with no physical inputs has no supply-chain exposure to
have, and the phrase is about the product rather than about the firm.

WHY THE REFUSALS ARE PUBLISHED
------------------------------
`why_others_were_not_selected` is not decoration. A router that only ever
shows its winner cannot be audited: a reader has no way to tell a considered
choice from the only option that was ever on the table. Every eligible lens
that lost is named with the reason it lost.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Dict, Tuple

CONTRACT = "strategic_lens_router.v1"

#: A lens must clear this to be asserted as PRIMARY. Below it the router
#: reports NO_LENS_SELECTED, which is a real answer: a company whose own
#: material does not say what decision it serves has not told us, and the
#: honest reading is the generic one plus the reason it stayed generic.
ACTIVATION_FLOOR = 4.0

#: A SECONDARY is a lens that is genuinely also activated, not merely the
#: next one down. Expressed as a SHARE of the winner rather than an absolute
#: distance, because the winner's score depends on how much material was
#: retrieved: a fixed band of 6 points admits every runner-up on a thin
#: corpus and none at all on a rich one, which is the wrong way round.
#:
#: Measured on the ten: BigID's runner-up is Enterprise Data & AI at 16
#: against 26 (0.62) and ZoomInfo's is Market & Competitive at 12 against 22
#: (0.55) -- both real second readings a strategist would name. Highspot's is
#: Decision to Execution at 10 against 35 (0.29), which is a related idea and
#: not a second reading of the company. The threshold sits between them.
SECONDARY_SHARE = 0.40
MAX_SECONDARY = 2


def _rx(phrase: str) -> "re.Pattern":
    body = re.escape(phrase).replace(r"\ ", r"[\s\-]+")
    left = r"\b" if phrase[:1].isalnum() else ""
    right = r"\b" if phrase[-1:].isalnum() else ""
    return re.compile(left + body + right, re.I)


_SOFTWARE = ("SUBSCRIPTION_SOFTWARE", "MULTI_ENGINE_PLATFORM",
             "ADVERTISING_PLATFORM")
_SERVICES = ("PEOPLE_OR_ROUTE_BASED_SERVICES",)
_PHYSICAL = ("DESIGN_AND_MANUFACTURE", "MANUFACTURE_AND_AFTERMARKET",
             "COMMODITY_PRODUCER", "BRANDED_CONSUMER", "SCALE_RETAIL",
             "CONTRACTED_OR_RATE_BASE_ASSETS")
_ALL = _SOFTWARE + _SERVICES + _PHYSICAL + (
    "BALANCE_SHEET_OR_NETWORK", "REGULATED_PRODUCT_OR_PROVIDER")


@dataclasses.dataclass(frozen=True)
class Lens:
    """One way of reading a company, and the conditions under which it applies."""
    lens_id: str
    name: str
    #: what a report under this lens is ABOUT, in the reader's language
    decision_domains: Tuple[str, ...]
    #: HARD GATE. A lens outside these classes is never scored.
    eligible_business_models: Tuple[str, ...]
    #: (phrase, weight) drawn from the subject's OWN published material
    signals_that_activate: Tuple[Tuple[str, float], ...]
    #: (phrase, weight) that argue the lens is describing the PRODUCT rather
    #: than the FIRM, or that another lens fits better
    signals_that_reduce_relevance: Tuple[Tuple[str, float], ...] = ()
    preferred_report_modules: Tuple[str, ...] = ()
    preferred_q_and_a_topics: Tuple[str, ...] = ()
    role_priority: Tuple[str, ...] = ()
    required_evidence: Tuple[str, ...] = ()
    #: What a GENERIC analysis of a company in this space would say. Used by
    #: `differentiation` as the thing the company-specific reading must beat,
    #: never as output on its own.
    generic_reading: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


LENS_LIBRARY: Tuple[Lens, ...] = (
    Lens(
        lens_id="enterprise_data_ai",
        name="Enterprise Data & AI Strategy",
        decision_domains=("where enterprise data is allowed to go",
                          "what an AI programme can be trained on",
                          "platform consolidation"),
        eligible_business_models=_SOFTWARE + _SERVICES,
        signals_that_activate=(
            ("ai ready", 4.0), ("ai-ready data", 5.0), ("data platform", 3.5),
            ("enterprise data", 3.0), ("unstructured data", 3.0),
            ("data estate", 4.0), ("large language model", 2.5),
            ("generative ai", 2.5), ("data management", 3.0),
            ("hybrid cloud", 2.0), ("data protection", 2.5),
            ("workloads", 2.0), ("backup", 2.0), ("recovery", 2.0),
            ("resilience", 2.5), ("ransomware", 2.5),
        ),
        signals_that_reduce_relevance=(("quota", 2.0), ("pipeline", 1.5)),
        preferred_report_modules=("data_ai_exposure", "economic_exposure",
                                  "competitive_response", "decision_delta"),
        preferred_q_and_a_topics=(
            "Which parts of the data estate is this actually about?",
            "What does an AI programme change about this decision?",
            "Who else is competing to be the platform of record?"),
        role_priority=("ceo", "cso", "cpo", "risk"),
        required_evidence=("a first-party statement about enterprise data or "
                           "AI workloads",),
        generic_reading=(
            "that enterprise AI adoption is accelerating and every software "
            "vendor should position around it"),
    ),
    Lens(
        lens_id="data_security_governance",
        name="Data Security & Governance",
        decision_domains=("what sensitive data exists and where",
                          "who may reach it", "what regulation requires"),
        eligible_business_models=_SOFTWARE + _SERVICES,
        signals_that_activate=(
            ("sensitive data", 4.5), ("data security", 4.0),
            ("data governance", 4.5), ("privacy", 3.0),
            ("data discovery", 4.5), ("dspm", 5.0),
            ("access governance", 4.0), ("gdpr", 3.0), ("ccpa", 3.0),
            ("compliance", 2.0), ("data classification", 4.0),
            ("data risk", 3.5), ("shadow data", 4.5),
            ("least privilege", 3.5), ("regulated data", 4.0),
        ),
        signals_that_reduce_relevance=(("quota", 2.0),
                                       ("comparable sales", 3.0)),
        preferred_report_modules=("regulatory_exposure", "data_ai_exposure",
                                  "competitive_response", "contradictions"),
        preferred_q_and_a_topics=(
            "Which regulation actually binds this decision?",
            "What sensitive data is in scope and who says so?",
            "What happens to this thesis if enforcement does not arrive?"),
        role_priority=("risk", "ceo", "cso", "cpo"),
        required_evidence=("a first-party statement about sensitive or "
                           "regulated data",),
        generic_reading=(
            "that regulation is tightening and enterprises will buy more "
            "security software"),
    ),
    Lens(
        lens_id="revenue_gtm",
        name="Revenue & Go-To-Market Strategy",
        decision_domains=("how revenue is produced",
                          "what the sales organisation is asked to do",
                          "which assumption the plan rests on"),
        eligible_business_models=_SOFTWARE + _SERVICES,
        signals_that_activate=(
            ("sales enablement", 5.0), ("revenue teams", 4.5),
            ("go to market", 3.5), ("quota", 4.0), ("pipeline", 3.0),
            ("sales reps", 4.0), ("win rate", 4.0), ("ramp time", 4.5),
            ("buyer", 2.5), ("seller", 3.0), ("sales cycle", 4.0),
            ("revenue execution", 5.0), ("sales productivity", 4.5),
            ("prospecting", 3.5), ("sales intelligence", 4.5),
            ("account executives", 4.0), ("crm", 3.0),
        ),
        signals_that_reduce_relevance=(("ransomware", 2.5),
                                       ("rate base", 3.0)),
        preferred_report_modules=("customer_signals", "competitive_response",
                                  "economic_exposure", "decision_delta",
                                  "scenario_comparison"),
        preferred_q_and_a_topics=(
            "Which assumption in the revenue plan is load-bearing?",
            "What would a buyer do differently if this is right?",
            "Where does the sales motion break first?"),
        role_priority=("cro", "ceo", "cmo", "cso"),
        required_evidence=("a first-party statement about how revenue is "
                           "produced or sold",),
        generic_reading=(
            "that sales productivity matters and buyers have become more "
            "cautious"),
    ),
    Lens(
        lens_id="market_competitive",
        name="Market & Competitive Strategy",
        decision_domains=("who this is actually competing with",
                          "which position is defensible",
                          "what a rival does first"),
        eligible_business_models=_ALL,
        signals_that_activate=(
            ("market intelligence", 4.5), ("competitive intelligence", 4.5),
            ("market data", 3.5), ("company data", 3.0),
            ("buyer intent", 4.5), ("market coverage", 3.0),
            ("category", 2.0), ("market leader", 2.5),
            ("consolidation", 3.0), ("displace", 3.0),
        ),
        preferred_report_modules=("competitive_response", "market_belief",
                                  "alternative_interpretation",
                                  "scenario_comparison"),
        preferred_q_and_a_topics=(
            "Who is actually competing for this budget?",
            "What is the defensible position here?",
            "What does the strongest rival do next?"),
        role_priority=("ceo", "cso", "cro"),
        required_evidence=("evidence naming a rival or a contested market",),
        generic_reading=(
            "that the category is consolidating and the leaders will take "
            "share"),
    ),
    Lens(
        lens_id="data_infrastructure",
        name="Data Infrastructure & Decision Trust",
        decision_domains=("whether the numbers can be relied on",
                          "who is allowed to answer a question",
                          "what breaks when the data is wrong"),
        eligible_business_models=_SOFTWARE,
        signals_that_activate=(
            ("data observability", 5.0), ("data quality", 4.5),
            ("data reliability", 5.0), ("data downtime", 5.0),
            ("data pipelines", 4.0), ("analytics", 3.0),
            ("business intelligence", 3.5), ("data warehouse", 4.0),
            ("data lakehouse", 4.0), ("dashboards", 2.5),
            ("data trust", 4.5), ("lineage", 4.0), ("data teams", 3.5),
            ("self service analytics", 4.5), ("spreadsheet", 3.0),
        ),
        signals_that_reduce_relevance=(("quota", 2.0),),
        preferred_report_modules=("data_ai_exposure", "customer_signals",
                                  "competitive_response", "causal_chain"),
        preferred_q_and_a_topics=(
            "What decision goes wrong when this data is wrong?",
            "Who inside the customer actually owns this?",
            "Why would a customer pay for trust rather than for speed?"),
        role_priority=("cpo", "cso", "ceo"),
        required_evidence=("a first-party statement about data reliability, "
                           "analytics or pipelines",),
        generic_reading=(
            "that data volumes are growing and quality tooling will follow"),
    ),
    Lens(
        lens_id="consulting_portfolio",
        name="Client Portfolio & Multi-Client Intelligence",
        decision_domains=("which client exposure is concentrated",
                          "which practice to staff against",
                          "what a client is about to decide"),
        eligible_business_models=_SERVICES,
        signals_that_activate=(
            ("our clients", 3.5), ("client engagements", 4.5),
            ("consulting", 4.0), ("consultancy", 4.5),
            ("transformation", 3.0), ("advisory", 3.5),
            ("practice areas", 4.0), ("our consultants", 4.5),
            ("industries we serve", 3.5), ("delivery", 2.0),
            ("partners with", 2.0),
        ),
        preferred_report_modules=("client_portfolio", "competitive_response",
                                  "economic_exposure", "decision_delta"),
        preferred_q_and_a_topics=(
            "Which client industries carry the most exposure right now?",
            "What decision are those clients about to face?",
            "Where is the practice mix most concentrated?"),
        role_priority=("consultant", "ceo", "cso"),
        required_evidence=("a first-party statement about clients or "
                           "engagements",),
        generic_reading=(
            "that consulting demand follows enterprise technology spending"),
    ),
    Lens(
        lens_id="regulatory_risk",
        name="Regulatory & Risk Intelligence",
        decision_domains=("what a regulator is about to require",
                          "what exposure is already on the books",
                          "what a failure would cost"),
        eligible_business_models=_ALL,
        signals_that_activate=(
            ("regulator", 3.5), ("regulatory", 3.0), ("audit", 2.5),
            ("sox", 3.5), ("hipaa", 4.0), ("pci", 3.5),
            ("enforcement", 3.5), ("statutory", 3.0),
            ("legal hold", 4.0), ("retention policy", 3.5),
        ),
        preferred_report_modules=("regulatory_exposure", "contradictions",
                                  "scenario_comparison", "decision_delta"),
        preferred_q_and_a_topics=(
            "Which specific rule is this about?",
            "What is the exposure if nothing changes?",
            "What would a regulator have to do for this to matter?"),
        role_priority=("risk", "ceo", "cso"),
        required_evidence=("evidence naming a regulator, rule or "
                           "enforcement action",),
        generic_reading=(
            "that the regulatory environment is tightening across the board"),
    ),
    Lens(
        lens_id="operational_intelligence",
        name="Operational Intelligence",
        decision_domains=("what the operation can absorb",
                          "where throughput is lost",
                          "which cost moves with volume"),
        eligible_business_models=_ALL,
        signals_that_activate=(
            ("uptime", 3.0), ("service levels", 3.5), ("throughput", 3.5),
            ("operational efficiency", 3.5), ("automation", 2.5),
            ("workflow", 3.0), ("orchestration", 3.0),
            ("incident", 3.0), ("mean time to", 4.0),
        ),
        preferred_report_modules=("economic_exposure", "causal_chain",
                                  "decision_delta"),
        preferred_q_and_a_topics=(
            "Where does the operation actually bind?",
            "Which cost moves with volume and which does not?"),
        role_priority=("coo", "ceo", "cso"),
        required_evidence=("a first-party statement about operations or "
                           "service delivery",),
        generic_reading=("that operational efficiency is a durable priority"),
    ),
    Lens(
        lens_id="supply_chain_shock",
        name="Supply Chain & External Shock",
        decision_domains=("what the inputs cost",
                          "what happens when one does not arrive",
                          "how much can be passed through"),
        # HARD REFUSAL FOR SOFTWARE, deliberately. A software vendor writing
        # about "supply chain security" is describing its PRODUCT; a firm
        # with no physical inputs has no supply-chain exposure to have, and
        # scoring it here is how a lens reaches the wrong kind of company.
        eligible_business_models=_PHYSICAL + ("REGULATED_PRODUCT_OR_PROVIDER",),
        signals_that_activate=(
            ("raw materials", 4.5), ("suppliers", 3.5), ("freight", 4.0),
            ("logistics", 3.0), ("inventory", 3.5), ("tariff", 4.0),
            ("lead times", 4.0), ("input costs", 4.0),
        ),
        preferred_report_modules=("supply_chain_exposure",
                                  "economic_exposure", "scenario_comparison"),
        preferred_q_and_a_topics=(
            "Which input is the binding one?",
            "How much of a cost move can be passed through?"),
        role_priority=("coo", "cfo", "ceo"),
        required_evidence=("evidence about physical inputs or logistics",),
        generic_reading=("that supply chains remain volatile"),
    ),
    Lens(
        lens_id="financial_capital",
        name="Financial & Capital Allocation",
        decision_domains=("where the next dollar goes",
                          "what the balance sheet can carry",
                          "which return is being assumed"),
        eligible_business_models=_ALL,
        signals_that_activate=(
            ("capital allocation", 4.5), ("free cash flow", 4.0),
            ("operating margin", 3.5), ("share repurchase", 4.0),
            ("guidance", 3.0), ("cost of capital", 4.0),
            ("balance sheet", 3.0), ("working capital", 3.5),
        ),
        preferred_report_modules=("financial_sensitivity",
                                  "economic_exposure", "scenario_comparison",
                                  "decision_delta"),
        preferred_q_and_a_topics=(
            "What return is being assumed here?",
            "What does the balance sheet allow?"),
        role_priority=("cfo", "ceo", "cso"),
        required_evidence=("evidence carrying a financial disclosure",),
        generic_reading=("that capital discipline is being rewarded"),
    ),
    Lens(
        lens_id="planning_assumption",
        name="Planning & Assumption Validation",
        decision_domains=("which assumption the plan rests on",
                          "what would falsify it",
                          "what to watch"),
        eligible_business_models=_ALL,
        signals_that_activate=(
            ("forecast", 3.0), ("planning", 2.5), ("scenario", 3.0),
            ("assumptions", 3.0), ("budget", 2.5),
            ("annual plan", 3.5), ("targets", 2.0),
        ),
        preferred_report_modules=("what_would_change_our_mind",
                                  "scenario_comparison", "contradictions",
                                  "information_priority"),
        preferred_q_and_a_topics=(
            "Which assumption is load-bearing?",
            "What would have to be true for this to be wrong?"),
        role_priority=("cso", "cfo", "ceo"),
        required_evidence=("evidence about plans, targets or forecasts",),
        generic_reading=("that planning assumptions should be revisited"),
    ),
    Lens(
        lens_id="decision_execution",
        name="Decision to Execution",
        decision_domains=("what happens after the decision",
                          "who has to change what they do",
                          "where the strategy stops"),
        eligible_business_models=_SOFTWARE + _SERVICES,
        signals_that_activate=(
            ("execution", 3.0), ("adoption", 3.0), ("enablement", 3.5),
            ("change management", 4.0), ("onboarding", 3.0),
            ("time to value", 4.0), ("coaching", 3.5),
            ("training", 2.5), ("rollout", 3.0),
        ),
        preferred_report_modules=("decision_delta", "customer_signals",
                                  "causal_chain", "information_priority"),
        preferred_q_and_a_topics=(
            "Who has to do something differently for this to work?",
            "Where does a decision like this usually stop?"),
        role_priority=("coo", "cpo", "ceo"),
        required_evidence=("a first-party statement about adoption, "
                           "enablement or rollout",),
        generic_reading=("that strategy fails in execution"),
    ),
)

_BY_ID = {lens.lens_id: lens for lens in LENS_LIBRARY}


@dataclasses.dataclass(frozen=True)
class LensScore:
    lens_id: str
    name: str
    score: float
    eligible: bool
    #: the phrases that fired, strongest first
    fired: Tuple[Tuple[str, float], ...] = ()
    reduced_by: Tuple[Tuple[str, float], ...] = ()
    #: the quoted span the strongest signal sat in
    evidence_span: str = ""
    why: str = ""

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["fired"] = [list(f) for f in self.fired]
        out["reduced_by"] = [list(f) for f in self.reduced_by]
        return out


@dataclasses.dataclass(frozen=True)
class LensSelection:
    """The routing decision, with its reasoning attached.

    `primary` is "" when nothing cleared `ACTIVATION_FLOOR`. That is a real
    result and it is NOT a failure: a company whose published material does
    not say what decision it serves has not told us, and the honest surface
    is the generic reading plus the reason it stayed generic.
    """
    primary: str = ""
    primary_name: str = ""
    secondary: Tuple[str, ...] = ()
    secondary_names: Tuple[str, ...] = ()
    why_selected: str = ""
    why_others_were_not_selected: Tuple[str, ...] = ()
    scores: Tuple[LensScore, ...] = ()
    confidence: str = "none"
    evidence_span: str = ""
    contract: str = CONTRACT

    @property
    def lens(self):
        return _BY_ID.get(self.primary)

    def as_dict(self) -> dict:
        return {
            "primary": self.primary, "primary_name": self.primary_name,
            "secondary": list(self.secondary),
            "secondary_names": list(self.secondary_names),
            "why_selected": self.why_selected,
            "why_others_were_not_selected":
                list(self.why_others_were_not_selected),
            "scores": [s.as_dict() for s in self.scores],
            "confidence": self.confidence,
            "evidence_span": self.evidence_span,
            "contract": self.contract,
        }


def _span_around(text: str, match: "re.Match") -> str:
    """See `adaptive.spans`. Two of the three quotes on the first live page
    were drawn from a press-release index, which is furniture and is not
    evidence that a lens applies."""
    from intent_engine.adaptive.spans import quote_around
    return quote_around(text, match.start(), match.end(), max_chars=280)


def select_lens(*, evidence_text: str, business_model: str = "",
                exposures: Tuple[str, ...] = (),
                decision_domains: Tuple[str, ...] = ()) -> LensSelection:
    """Route this company to a lens on its own evidence.

    `business_model` is the HARD applicability gate. An empty model means the
    business kind was never established, and every lens is then scored --
    because refusing all of them would leave a company with no reading at all
    for a reason that is about our classification rather than about them.
    That widening is recorded in `why_selected` so it is never silent.
    """
    body = str(evidence_text or "")[:200_000]
    model = str(business_model or "").strip().upper()
    exposure_text = " ".join(str(e) for e in exposures).lower()
    domain_text = " ".join(str(d) for d in decision_domains).lower()

    scored = []
    for lens in LENS_LIBRARY:
        eligible = (not model) or (model in lens.eligible_business_models)
        if not eligible:
            scored.append(LensScore(
                lens.lens_id, lens.name, 0.0, False,
                why=(f"refused: a {model.replace('_', ' ').lower()} business "
                     f"cannot carry this lens, whatever its material says "
                     f"about the subject")))
            continue
        total, fired, span, best = 0.0, [], "", 0.0
        for phrase, weight in lens.signals_that_activate:
            m = _rx(phrase).search(body)
            if m is None:
                continue
            total += weight
            fired.append((phrase, weight))
            if weight > best:
                best, span = weight, _span_around(body, m)
        reduced = []
        for phrase, weight in lens.signals_that_reduce_relevance:
            if _rx(phrase).search(body):
                total -= weight
                reduced.append((phrase, weight))
        # EXPOSURES AND DECISION DOMAINS CORROBORATE, they never carry. A
        # lens with no first-party activation is not rescued by an exposure
        # list this layer computed for itself.
        if fired:
            for dom in lens.decision_domains:
                head = dom.split()[0].lower()
                if head and (head in exposure_text or head in domain_text):
                    total += 1.0
        scored.append(LensScore(
            lens.lens_id, lens.name, round(total, 1), True,
            fired=tuple(sorted(fired, key=lambda f: -f[1])),
            reduced_by=tuple(reduced), evidence_span=span))

    live = sorted((s for s in scored if s.eligible), key=lambda s: -s.score)
    if not live or live[0].score < ACTIVATION_FLOOR:
        best = live[0] if live else None
        return LensSelection(
            scores=tuple(scored),
            why_selected=(
                "No strategic lens was selected. This company's published "
                "material does not say clearly enough what decision it "
                "serves"
                + (f" -- the strongest reading, {best.name}, scored "
                   f"{best.score:.1f} against the {ACTIVATION_FLOOR:.0f} "
                   f"needed" if best else "")
                + ". The reading below is therefore the general one, and it "
                  "is labelled as such rather than dressed as a "
                  "company-specific finding."),
            why_others_were_not_selected=tuple(
                f"{s.name}: {s.why}" for s in scored if not s.eligible)[:4])

    top = live[0]
    secondary = [s for s in live[1:]
                 if s.score >= ACTIVATION_FLOOR
                 and s.score >= top.score * SECONDARY_SHARE][:MAX_SECONDARY]
    losers = []
    for s in live[1:]:
        if s in secondary:
            continue
        if s.score <= 0:
            losers.append(f"{s.name}: nothing in this company's own material "
                          f"activates it")
        else:
            losers.append(
                f"{s.name}: scored {s.score:.1f} against {top.score:.1f}"
                + (f", and {', '.join(p for p, _w in s.reduced_by)} argues "
                   f"the match is about the product rather than the firm"
                   if s.reduced_by else
                   f", carried by {', '.join(p for p, _w in s.fired[:2])} "
                   f"alone" if s.fired else ""))
    for s in scored:
        if not s.eligible:
            losers.append(f"{s.name}: {s.why}")

    lead = ", ".join(f"“{p}”" for p, _w in top.fired[:3])
    runner = live[1].score if len(live) > 1 else 0.0
    confidence = ("high" if top.score >= ACTIVATION_FLOOR * 3
                  and runner <= top.score * SECONDARY_SHARE
                  else "moderate" if top.score >= ACTIVATION_FLOOR * 2
                  else "low")
    widened = ("" if model else
               " The business model was never established for this company, "
               "so every lens was scored rather than filtered by kind; the "
               "selection rests on the published material alone.")
    return LensSelection(
        primary=top.lens_id, primary_name=top.name,
        secondary=tuple(s.lens_id for s in secondary),
        secondary_names=tuple(s.name for s in secondary),
        why_selected=(
            f"This company's own material is about {lead}, which is what "
            f"{top.name.lower()} reads. It scored {top.score:.1f} against "
            f"{(live[1].score if len(live) > 1 else 0.0):.1f} for the next "
            f"eligible lens.{widened}"),
        why_others_were_not_selected=tuple(losers)[:6],
        scores=tuple(scored), confidence=confidence,
        evidence_span=top.evidence_span)


def lens_by_id(lens_id: str):
    return _BY_ID.get(str(lens_id or ""))

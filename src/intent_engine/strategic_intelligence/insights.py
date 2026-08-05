"""V1.3 executive insights — surprises, opportunities, vulnerabilities,
underexamined questions, multi-signal agenda, and meeting-relevance.

All deterministic and evidence-driven. An insight is only emitted when the
evidence (signals in tension, fired patterns, source-class mismatches) supports
it, then instantiated from a curated analyst playbook and parameterized by the
company — the same philosophy as the pattern library. A generic-insight gate
rejects findings that could apply to any company.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from intent_engine.strategic_intelligence.patterns import TENSIONS

from intent_engine.strategic_intelligence.evidence_classes import (
    INDEPENDENT_CLASSES as _INDEPENDENT,
)

# phrases that make an "insight" generic (fail the executive quality gate)
_GENERIC_MARKERS = (
    "is investing in ai", "wants to grow", "expanding its product suite",
    "faces competition", "is growing", "focuses on customers",
    "invests in technology", "is innovating", "improving its product",
)


def _mr_label(n_signals, recent, exec_attention, independent):
    """Meeting-relevance label + explanation. No fake precise number."""
    score = n_signals + (1 if recent else 0) + (1 if exec_attention else 0) \
        + (1 if independent else 0)
    if score >= 5:
        label = "Very likely active"
    elif score >= 4:
        label = "Likely active"
    elif score >= 3:
        label = "Emerging"
    elif score >= 2:
        label = "Longer-term"
    else:
        label = "Weakly supported"
    why = (f"{n_signals} distinct public signal(s)"
           + (", recent" if recent else "")
           + (", with explicit executive attention" if exec_attention else "")
           + (", independently corroborated" if independent else "") + ".")
    return label, why


@dataclass
class StrategicSurprise:
    finding: str
    why_surprising: str
    signals_in_tension: list
    evidence_side_a: list
    evidence_side_b: list
    alternative_explanation: str
    likely_implication: str
    decision_affected: str
    confidence: str
    what_would_resolve: str
    meeting_relevance: str = ""
    meeting_relevance_why: str = ""

    def as_dict(self):
        return asdict(self)


@dataclass
class StrategicOpportunity:
    statement: str
    why_now: str
    asymmetry: str
    evidence: list
    assumptions: list
    affected_segment: str
    advantage: str
    execution_difficulty: str
    downside: str
    evidence_needed: list
    leading_indicators: list
    decision_required: str
    confidence: str

    def as_dict(self):
        return asdict(self)


@dataclass
class StrategicVulnerability:
    exposed_layer: str
    mechanism: str
    why_increasing: str
    market_force: str
    evidence: list
    counterpoint: str
    likely_impact: str
    leading_indicator: str
    decision_affected: str
    confidence: str

    def as_dict(self):
        return asdict(self)


@dataclass
class UnderexaminedQuestion:
    question: str
    why_underexamined: str
    evidence_that_triggered_it: list
    what_answers_imply: str
    decision_affected: str

    def as_dict(self):
        return asdict(self)


def is_generic_insight(text: str) -> bool:
    low = " ".join((text or "").lower().split())
    return any(m in low for m in _GENERIC_MARKERS)


def passes_specificity(text: str, company: str) -> bool:
    """The company-name-removal test: a strong insight names something
    company-specific (a product, layer, segment, mechanism) beyond the name."""
    if is_generic_insight(text):
        return False
    specific = ("checkout", "identity", "rails", "enterprise", "smb",
                "partner", "agent", "storefront", "payments", "ecosystem",
                "distribution", "developer", "api", "pricing", "data",
                "infrastructure", "merchant", "product breadth", "brand",
                "value proposition", "lock-in", "simplicity", "suite")
    low = (text or "").lower()
    return sum(1 for w in specific if w in low) >= 1


def _live_tensions(observations):
    present = set()
    for o in observations:
        present.update(o.signals)
    live = []
    for t in TENSIONS:
        if any(s in present for s in t["left"]) and \
                any(s in present for s in t["right"]):
            live.append(t)
    return live


def _obs_for(observations, signals, weak_ok=False):
    out = []
    for o in observations:
        if set(o.signals) & set(signals) and (weak_ok or not o.weak):
            out.append(o)
    return out


def _cite(obs, limit=2):
    return [{"excerpt": o.excerpt or o.text, "source_title": o.source_title,
             "source_class": o.source_class, "date": o.date}
            for o in obs[:limit]]


def detect_surprises(company, observations, hypotheses):
    """A surprise is a meaningful mismatch, not a fact. Built from live tensions
    plus a cross-source-class emphasis check."""
    surprises = []
    classes = {o.source_class for o in observations}
    exec_present = "executive_statement" in classes
    for t in _live_tensions(observations):
        a = _obs_for(observations, t["left"])
        b = _obs_for(observations, t["right"])
        if not (a and b):
            continue
        indep = bool({o.source_class for o in a + b} & set(_INDEPENDENT))
        recent = any(o.date >= "2025-01-01" for o in a + b if o.date)
        label, why = _mr_label(2, recent, exec_present, indep)
        finding = f"For {company}, {t['observed_tension'][0].lower()}{t['observed_tension'][1:]}"
        if not passes_specificity(finding, company):
            continue
        surprises.append(StrategicSurprise(
            finding=finding,
            why_surprising="Two public signals point in different strategic "
                           "directions and do not obviously reconcile.",
            signals_in_tension=list(t["left"]) + list(t["right"]),
            evidence_side_a=_cite(a), evidence_side_b=_cite(b),
            alternative_explanation=t["counter_explanation"],
            likely_implication=t["why_it_may_matter"],
            decision_affected=t["decision_affected"],
            confidence="moderate" if indep else "low",
            what_would_resolve=(t["evidence_needed"][0]
                                if t["evidence_needed"] else
                                "clearer public evidence on either side"),
            meeting_relevance=label, meeting_relevance_why=why))
    # rank: independent + recent first, cap 3
    surprises.sort(key=lambda s: (s.confidence == "moderate",
                                  s.meeting_relevance), reverse=True)
    return surprises[:3]


_OPPORTUNITY_PLAYBOOK = {
    "enterprise_vs_smb_simplicity": dict(
        statement="Isolate enterprise complexity so the SMB experience stays "
                  "simple — sell 'grows with you', not two products.",
        asymmetry="The company can serve enterprises without forcing SMB users "
                  "to absorb enterprise complexity; focused rivals cannot span "
                  "both cleanly.",
        affected_segment="the original SMB base",
        advantage="protects the acquisition engine while opening up-market",
        difficulty="moderate — requires packaging and org discipline",
        downside="a botched split confuses positioning and slows both segments",
        decision="How to segment product and packaging across SMB and enterprise."),
    "control_vs_partner_openness": dict(
        statement="Use owned checkout/identity/data rails to make partners more "
                  "successful rather than to displace them.",
        asymmetry="Owning the rails is a distribution advantage partners cannot "
                  "replicate; sharing it buys ecosystem loyalty rivals lack.",
        affected_segment="the partner/app ecosystem",
        advantage="turns a control asset into an ecosystem moat",
        difficulty="moderate — requires credible partner economics",
        downside="over-reach converts partners into competitors",
        decision="Where to draw the first-party vs partner value line."),
    "breadth_vs_clear_value_prop": dict(
        statement="Package the underused product cluster around one merchant "
                  "outcome instead of a feature list.",
        asymmetry="Breadth already exists; a unifying outcome narrative is "
                  "cheap to state and hard for point solutions to match.",
        affected_segment="mid-market buyers evaluating suites vs point tools",
        advantage="raises attach and clarifies the pitch without new build",
        difficulty="low-to-moderate — narrative and pricing, not new product",
        downside="an outcome promise the product cannot yet keep",
        decision="Whether to lead with an outcome narrative or a product suite."),
}


def detect_opportunities(company, observations, hypotheses):
    opps = []
    for t in _live_tensions(observations):
        play = _OPPORTUNITY_PLAYBOOK.get(t["tension_id"])
        if not play:
            continue
        ev = _cite(_obs_for(observations, t["left"] + t["right"]), 2)
        stmt = f"{company}: {play['statement']}"
        if not passes_specificity(stmt, company):
            continue
        opps.append(StrategicOpportunity(
            statement=stmt, why_now=t["why_it_may_matter"],
            asymmetry=play["asymmetry"], evidence=ev,
            assumptions=[t["counter_explanation"]],
            affected_segment=play["affected_segment"],
            advantage=play["advantage"],
            execution_difficulty=play["difficulty"], downside=play["downside"],
            evidence_needed=t["evidence_needed"],
            leading_indicators=t["evidence_needed"],
            decision_required=play["decision"],
            confidence="moderate"))
    return opps[:3]


_VULNERABILITY_PLAYBOOK = {
    "human_to_agent_workflow": dict(
        layer="demand capture at the storefront",
        mechanism="if buying is mediated by AI agents, the owned human-facing "
                  "storefront matters less than the rails an agent calls",
        why="agentic-commerce signals are appearing before the interface moat "
            "is replaced",
        force="AI shopping agents / answer engines",
        impact="erosion of the interface advantage that drives acquisition",
        indicator="share of orders originating from agent surfaces"),
    "ecosystem_control_vs_openness": dict(
        layer="the partner ecosystem",
        mechanism="consolidating checkout/identity/data can turn partners into "
                  "competitors and shrink the ecosystem the platform depends on",
        why="rails consolidation is advancing alongside partner reliance",
        force="partner/app developers and regulators",
        impact="partner attrition and governance/regulatory pressure",
        indicator="partner-sourced value vs first-party rails over time"),
    "smb_wedge_to_enterprise": dict(
        layer="the original SMB wedge",
        mechanism="enterprise complexity can erode the simplicity that won the "
                  "SMB base, opening room for a simpler challenger",
        why="enterprise investment is rising while the brand stays SMB",
        force="focused SMB-first challengers",
        impact="slower SMB activation/retention — the core growth engine",
        indicator="SMB activation and retention trend"),
    "differentiator_commoditization": dict(
        layer="the original product surface",
        mechanism="as the core product commoditizes, pricing power moves to "
                  "adjacent rails the company must now defend",
        why="the entry product is widely available while value shifts to rails",
        force="low-cost and open-source alternatives",
        impact="pricing pressure on the core product",
        indicator="standalone pricing power on the core product"),
}


def detect_vulnerabilities(company, observations, hypotheses):
    vulns = []
    obs_by_id = {o.observation_id: o for o in observations}
    for h in hypotheses:
        play = _VULNERABILITY_PLAYBOOK.get(h.pattern_id)
        if not play:
            continue
        counter = [obs_by_id[i] for i in h.counter_observation_ids
                   if i in obs_by_id]
        ev = _cite(counter or [obs_by_id[i] for i in h.supporting_observation_ids
                               if i in obs_by_id], 2)
        vulns.append(StrategicVulnerability(
            exposed_layer=play["layer"], mechanism=play["mechanism"],
            why_increasing=play["why"], market_force=play["force"],
            evidence=ev,
            counterpoint=(h.alternative_explanations or [""])[0],
            likely_impact=play["impact"],
            leading_indicator=play["indicator"],
            decision_affected=(h.decision_implications or [""])[0],
            confidence=("moderate" if counter else "low")))
    return vulns[:3]


def underexamined_questions(company, observations, hypotheses, blind_spots):
    """Distinct from leadership questions: second-order, contradiction-driven,
    and company-specific."""
    qs = []
    obs_by_id = {o.observation_id: o for o in observations}
    for h in hypotheses[:3]:
        counter = [obs_by_id[i].excerpt or obs_by_id[i].text
                   for i in h.counter_observation_ids if i in obs_by_id][:2]
        if h.pattern_id == "product_to_platform":
            q = (f"If {company} becomes the rails, which of today's partners "
                 f"quietly become competitors — and does that shrink the "
                 f"ecosystem faster than rails revenue grows?")
        elif h.pattern_id == "human_to_agent_workflow":
            q = (f"If AI agents mediate buying, does {company} still own the "
                 f"customer relationship, or does the agent platform capture "
                 f"it — and what does that do to merchant demand?")
        elif h.pattern_id == "smb_wedge_to_enterprise":
            q = (f"Is enterprise focus quietly raising the complexity SMBs "
                 f"experience in {company}'s core flows, eroding the wedge "
                 f"before the enterprise revenue compensates?")
        else:
            q = (f"As {company} adds breadth, which single outcome still makes "
                 f"the whole suite worth more than the sum of point tools?")
        if not passes_specificity(q, company):
            continue
        qs.append(UnderexaminedQuestion(
            question=q,
            why_underexamined="It is a second-order effect of the current "
                              "strategy that rarely shows up in public "
                              "messaging.",
            evidence_that_triggered_it=counter or [h.why_now],
            what_answers_imply="A 'yes' reframes the strategy's downside; a "
                               "'no' strengthens the current direction.",
            decision_affected=(h.decision_implications or [""])[0]))
    return qs[:3]

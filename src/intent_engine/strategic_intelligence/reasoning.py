"""V1.2 strategic reasoning engine — deterministic, evidence-driven.

It consumes structured StrategicObservations (from approved live sources or a
curated validation fixture), matches their controlled-vocabulary signals
against the auditable pattern library, and instantiates strategic hypotheses
with the full reasoning apparatus. It performs retrieval-fed comparative
reasoning and pattern matching — NOT live model training. No network, no LLM,
no randomness: the same evidence always yields the same report.
"""
from __future__ import annotations

from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY, TENSIONS,
)
from intent_engine.strategic_intelligence.records import (
    BlindSpot, StrategicHypothesis, StrategicObservation, StrategicQuestion,
    StrategicReport,
)

_CONF_RANK = {"speculative": 0, "low": 1, "moderate": 2, "high": 3}
# source classes that make a report more than one-sided
_EXTERNAL_CLASSES = ("executive_statement", "investor_material",
                     "customer_voice", "competitor", "independent_reporting")
# genuinely outside the company's own publishing (cross-source corroboration)
_INDEPENDENT_CLASSES = ("independent_reporting", "customer_voice", "competitor")


def _signals_present(observations) -> set:
    present = set()
    for o in observations:
        present.update(o.signals)
    return present


def _obs_with_any(observations, wanted) -> list:
    wanted = set(wanted)
    return [o for o in observations if wanted & set(o.signals)]


def _confidence(matched_qual, support_classes, counter_count) -> tuple:
    """Return (level, reasons). Confidence rises with the number of qualifying
    signals matched and the diversity of source classes supporting them, and
    is tempered when counter-evidence is present."""
    base = len(matched_qual)
    diversity = len(support_classes)
    reasons = [
        f"{base} qualifying signal(s) matched: {', '.join(sorted(matched_qual))}",
        f"supported by {diversity} source class(es): "
        f"{', '.join(sorted(support_classes))}",
    ]
    only_company = support_classes == {"company_owned"}
    independent = support_classes & set(_INDEPENDENT_CLASSES)
    if only_company:
        reasons.append("all support comes from company-owned pages, which is "
                       "one-sided; independent corroboration is missing")
    elif independent:
        reasons.append("corroborated across an independent vantage point ("
                       + ", ".join(sorted(independent)) + "), not only the "
                       "company's own publishing")
    if counter_count:
        reasons.append(f"{counter_count} observation(s) point the other way "
                       "and are held as explicit counter-evidence")

    if diversity >= 3 and base >= 3:
        level = "high"
    elif diversity >= 2 and base >= 2:
        level = "moderate"
    elif base >= 2:
        level = "low"
    else:
        level = "speculative"
    # one-sided or well-countered claims are not allowed to read as high
    if only_company and level == "high":
        level = "moderate"
    if counter_count >= max(1, base) and _CONF_RANK[level] > 1:
        level = "low"
    return level, reasons


def _hypothesis_for(pattern, scaffold, observations, company_name):
    present = _signals_present(observations)
    matched_qual = tuple(s for s in pattern.qualifying_signals if s in present)
    if len(matched_qual) < scaffold.get("threshold", 2):
        return None
    matched_disc = tuple(s for s in pattern.disconfirming_signals
                         if s in present)
    support = _obs_with_any(observations, matched_qual)
    counter = _obs_with_any(observations, matched_disc)
    support_classes = {o.source_class for o in support}

    level, reasons = _confidence(matched_qual, support_classes, len(counter))
    # never let evidence push a hypothesis above the pattern's own reliability
    if _CONF_RANK[level] > _CONF_RANK[pattern.confidence]:
        level = pattern.confidence
        reasons.append(f"capped at the pattern's reliability ({level}); the "
                       "historical analogue is not more certain than this")
    named = "; ".join(f'"{o.text}"' for o in support[:3])
    reasoning = (scaffold["reasoning"] + " Signals matched here: "
                 + ", ".join(matched_qual) + ". This reads directly off: "
                 + named + ".")
    gaps = list(scaffold["gaps"])
    missing_external = [c for c in _EXTERNAL_CLASSES
                        if c not in support_classes]
    if missing_external:
        gaps.append("no " + " / ".join(missing_external)
                    + " source corroborates this yet")
    h = StrategicHypothesis(
        hypothesis_id=f"hyp-{pattern.pattern_id}",
        title=scaffold["title"],
        statement=scaffold["statement"].format(company=company_name),
        reasoning=reasoning,
        supporting_observation_ids=[o.observation_id for o in support],
        counter_observation_ids=[o.observation_id for o in counter],
        alternative_explanations=list(scaffold["alternatives"]),
        confidence=level,
        confidence_reasons=reasons,
        evidence_gaps=gaps,
        decision_implications=list(scaffold["implications"]),
        falsification_questions=list(scaffold["falsification"]),
        pattern_id=pattern.pattern_id,
        source_classes=tuple(sorted(support_classes)),
    )
    h.validate()
    return h


def _build_shifts(observations):
    """Meaningful, dated changes — the fixture/derivation dates exactly the
    observations that represent a movement, so we surface those."""
    shifts, seen_types = [], set()
    dated = [o for o in observations if o.date]
    dated.sort(key=lambda o: (o.date, o.observation_id), reverse=True)
    for o in dated:
        if o.observation_type in seen_types:
            continue
        seen_types.add(o.observation_type)
        shifts.append({
            "title": o.text, "evidence": o.excerpt or o.text,
            "date": o.date, "source_class": o.source_class,
            "observation_id": o.observation_id})
        if len(shifts) >= 5:
            break
    return shifts


def _build_blind_spots(observations):
    present = _signals_present(observations)
    blind = []
    for t in TENSIONS:
        left = [s for s in t["left"] if s in present]
        right = [s for s in t["right"] if s in present]
        if not (left and right):
            continue                      # a tension needs BOTH sides observed
        supp = [o.observation_id for o in
                _obs_with_any(observations, t["left"] + t["right"])]
        blind.append(BlindSpot(
            blind_spot_id=f"blind-{t['tension_id']}",
            observed_tension=t["observed_tension"],
            why_it_may_matter=t["why_it_may_matter"],
            counter_explanation=t["counter_explanation"],
            evidence_needed=list(t["evidence_needed"]),
            decision_affected=t["decision_affected"],
            supporting_observation_ids=supp))
    return blind


def _build_questions(hypotheses, observations):
    obs_by_id = {o.observation_id: o for o in observations}
    questions = []
    for h in hypotheses:
        trigger = [obs_by_id[i].excerpt or obs_by_id[i].text
                   for i in h.supporting_observation_ids[:2]
                   if i in obs_by_id]
        q = StrategicQuestion(
            question=h.falsification_questions[0],
            why_it_matters=(f"It directly tests the hypothesis that "
                            f"{h.title.lower()}; if it fails, that view is "
                            f"wrong. " + h.confidence_reasons[0]),
            evidence_that_triggered_it=trigger,
            possible_answer_paths=[
                "Evidence confirms the transition → invest ahead of it.",
                "Evidence is mixed → stage investment and watch indicators.",
                "Evidence disconfirms → the hypothesis is rejected.",
            ],
            decision_affected=h.decision_implications[0],
            source_refs=[{"observation_id": i}
                         for i in h.supporting_observation_ids[:3]])
        q.validate()
        questions.append(q)
    return questions


def _build_thesis(company_name, hypotheses, blind_spots):
    if not hypotheses:
        return {"view": f"There is not yet enough approved strategic evidence "
                        f"to form a defensible outside-in view of "
                        f"{company_name}.",
                "transition": "", "tension": "", "why_care": ""}
    top = hypotheses[0]
    tension = (blind_spots[0].observed_tension if blind_spots
               else "how much to invest ahead of the transition")
    return {
        "view": (f"{company_name} appears to be {top.title[0].lower()}"
                 f"{top.title[1:]}. The evidence supports this as a "
                 f"{top.confidence}-confidence hypothesis, not a settled "
                 f"fact."),
        "transition": top.statement,
        "tension": tension,
        "why_care": top.decision_implications[0],
    }


def _decision_implications(hypotheses, blind_spots):
    out = []
    for h in hypotheses[:5]:
        out.append({
            "decision": h.decision_implications[0],
            "options": h.alternative_explanations,
            "evidence_needed": h.evidence_gaps,
            "watch": h.falsification_questions,
            "hypothesis_id": h.hypothesis_id})
    for b in blind_spots:
        out.append({
            "decision": b.decision_affected,
            "options": [b.observed_tension, b.counter_explanation],
            "evidence_needed": b.evidence_needed,
            "watch": b.evidence_needed,
            "blind_spot_id": b.blind_spot_id})
    return out


def _build_evidence_graph(company_name, observations, hypotheses, patterns,
                          blind_spots, questions) -> dict:
    """A typed evidence graph linking sources → observations → hypotheses →
    patterns / counter-observations / questions / decisions. This single
    structure drives the report, the conversation, and downstream analytics —
    there is no second representation."""
    nodes, edges = [], []
    seen_sources = set()
    for o in observations:
        nodes.append({"id": o.observation_id, "type": "observation",
                      "label": o.text, "source_class": o.source_class,
                      "directly_observed": o.directly_observed})
        src = o.origin or o.source_title or o.source_class
        if src and src not in seen_sources:
            seen_sources.add(src)
            nodes.append({"id": f"src:{src}", "type": "source",
                          "label": o.source_title or src,
                          "source_class": o.source_class})
        if src:
            edges.append({"from": o.observation_id, "to": f"src:{src}",
                          "type": "from_source"})
    for h in hypotheses:
        nodes.append({"id": h.hypothesis_id, "type": "hypothesis",
                      "label": h.title, "confidence": h.confidence})
        for oid in h.supporting_observation_ids:
            edges.append({"from": oid, "to": h.hypothesis_id,
                          "type": "supports"})
        for oid in h.counter_observation_ids:
            edges.append({"from": oid, "to": h.hypothesis_id,
                          "type": "contradicts"})
        if h.pattern_id:
            edges.append({"from": h.hypothesis_id, "to": f"pat:{h.pattern_id}",
                          "type": "matches_pattern"})
    for p in patterns:
        nodes.append({"id": f"pat:{p.pattern_id}", "type": "pattern",
                      "label": p.name})
    for b in blind_spots:
        nodes.append({"id": b.blind_spot_id, "type": "blind_spot",
                      "label": b.observed_tension})
        for oid in b.supporting_observation_ids:
            edges.append({"from": oid, "to": b.blind_spot_id,
                          "type": "reveals_tension"})
    for i, q in enumerate(questions):
        qid = f"q:{i}"
        nodes.append({"id": qid, "type": "question", "label": q.question})
        for ref in q.source_refs:
            oid = ref.get("observation_id")
            if oid:
                edges.append({"from": oid, "to": qid, "type": "raises"})
    return {"nodes": nodes, "edges": edges,
            "counts": {"observations": len(observations),
                       "hypotheses": len(hypotheses),
                       "patterns": len(patterns),
                       "edges": len(edges)}}


def build_strategic_report(*, company_name, observations,
                           patterns=None, scaffolds=None,
                           user_accepts_limited_scope=False) -> StrategicReport:
    """Compose a StrategicReport from structured observations. Status is left
    to the quality gate (:func:`quality.evaluate_report`), which the caller
    should apply; this function sets a provisional status of the gate result."""
    patterns = patterns if patterns is not None else PATTERN_LIBRARY
    scaffolds = scaffolds if scaffolds is not None else HYPOTHESIS_SCAFFOLDS
    for o in observations:
        _require_obs(o)

    coverage = {}
    for o in observations:
        coverage[o.source_class] = coverage.get(o.source_class, 0) + 1

    patterns_by_id = {p.pattern_id: p for p in patterns}
    hypotheses = []
    for pattern in patterns:
        scaffold = scaffolds.get(pattern.pattern_id)
        if not scaffold:
            continue
        h = _hypothesis_for(pattern, scaffold, observations, company_name)
        if h is not None:
            hypotheses.append(h)

    # Dominance filter: drop a hypothesis when its own disconfirming signals are
    # the QUALIFYING signals of a strictly higher-confidence hypothesis that
    # also fired — i.e. the same evidence more strongly supports the opposite
    # reading, so surfacing the weaker one would mislead.
    present = _signals_present(observations)
    kept = []
    for h in hypotheses:
        pat = patterns_by_id[h.pattern_id]
        disc_here = {s for s in pat.disconfirming_signals if s in present}
        dominated = any(
            disc_here & set(patterns_by_id[g.pattern_id].qualifying_signals)
            and _CONF_RANK[g.confidence] > _CONF_RANK[h.confidence]
            for g in hypotheses if g is not h)
        if not dominated:
            kept.append(h)
    hypotheses = kept

    hypotheses.sort(
        key=lambda h: (_CONF_RANK[h.confidence],
                       len(h.supporting_observation_ids)), reverse=True)
    hypotheses = hypotheses[:5]

    fired_pattern_ids = {h.pattern_id for h in hypotheses}
    used_patterns = [p for p in patterns if p.pattern_id in fired_pattern_ids]

    blind_spots = _build_blind_spots(observations)
    questions = _build_questions(hypotheses, observations)
    thesis = _build_thesis(company_name, hypotheses, blind_spots)
    shifts = _build_shifts(observations)

    evidence_gaps = []
    for h in hypotheses:
        for g in h.evidence_gaps:
            if g not in evidence_gaps:
                evidence_gaps.append(g)
    external_present = [c for c in _EXTERNAL_CLASSES if c in coverage]
    independent_present = [c for c in _INDEPENDENT_CLASSES if c in coverage]
    if not external_present:
        evidence_gaps.insert(
            0, "the analysis rests only on company-owned pages; executive, "
               "investor, independent, and customer-voice sources are needed "
               "to corroborate or challenge these hypotheses")
    elif not independent_present:
        evidence_gaps.insert(
            0, "all evidence is company-published (owned/executive/investor); "
               "an independent, customer, or competitor source is needed for "
               "cross-source corroboration")

    graph = _build_evidence_graph(company_name, observations, hypotheses,
                                  used_patterns, blind_spots, questions)
    report = StrategicReport(
        company_name=company_name, status="",
        thesis=thesis, shifts=shifts, hypotheses=hypotheses,
        patterns=used_patterns, blind_spots=blind_spots, questions=questions,
        evidence_gaps=evidence_gaps,
        decision_implications=_decision_implications(hypotheses, blind_spots),
        observations=list(observations), source_class_coverage=coverage,
        limited_scope_accepted=user_accepts_limited_scope, evidence_graph=graph)

    # provisional status via the quality gate (importing here avoids a cycle)
    from intent_engine.strategic_intelligence.quality import evaluate_report
    report.status, report.quality_findings = evaluate_report(report)
    return report


def _require_obs(o):
    if not isinstance(o, StrategicObservation):
        raise TypeError("observations must be StrategicObservation instances")
    o.validate()

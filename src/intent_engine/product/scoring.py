"""Deterministic multi-dimensional scoring (T020).

There is no single "importance", and no HIGH / MEDIUM / LOW pulled from
intuition. Separate dimensions are computed from recorded facts, each
carrying its version, the exact inputs used, the formula stated rather
than implied, per-dimension reasons, and an honest status.

Hard rules, each individually tested:

    a dimension with no recorded input is UNAVAILABLE — not 0, not a
        default
    a composite containing an UNAVAILABLE dimension is itself UNAVAILABLE
        with the gap NAMED — it is not silently imputed
    strategic_alignment comes only from a human declaration; with none
        recorded it is UNAVAILABLE, because an agent does not decide
        strategy
    research whose stance is CONFLICTING or INSUFFICIENT lowers
        confidence, and the reason says so
    a score does not depend on how recently a proposal was created
    identical inputs produce identical scores

Four confidences are tracked separately, because they measure different
things and collapsing them hides which one is weak:

    problem_confidence      how much the evidence for the PROBLEM bears
    opportunity_confidence  how much the framing of the OPPORTUNITY bears
    proposal_confidence     how much this particular SOLUTION bears
    execution_confidence    how ready this is to be built at all

Cost of delay is computed SEPARATELY and is never folded into
opportunity_score: "how valuable" and "how expensive to postpone" are
different questions, and averaging them destroys both.

SCORING POLICY (structural, not advisory): scores describe proposals.
They do not shape them. A proposal is never modified in order to improve
its computed score, and an author-supplied score is rejected rather than
recorded — see `assert_not_score_shaped`.
"""
from __future__ import annotations

from datetime import datetime

from intent_engine.product.records import (
    ProductError, find_forbidden_fields,
)

OK = "OK"
UNAVAILABLE = "UNAVAILABLE"

SCORE_VERSIONS = {
    "evidence_coverage": "evidence_coverage.v1",
    "customer_coverage": "customer_coverage.v1",
    "experiment_coverage": "experiment_coverage.v1",
    "research_coverage": "research_coverage.v1",
    "strategic_alignment": "strategic_alignment.v1",
    "freshness": "freshness.v1",
    "opportunity_score": "opportunity_score.v1",
    "problem_confidence": "problem_confidence.v1",
    "opportunity_confidence": "opportunity_confidence.v1",
    "proposal_confidence": "proposal_confidence.v1",
    "execution_confidence": "execution_confidence.v1",
    "cost_of_delay": "cost_of_delay.v1",
}

# Human-declared alignment levels. An agent may read these; it may not
# author them.
ALIGNMENT_LEVELS = {"core": 1.0, "adjacent": 0.6, "exploratory": 0.3}

# Labels that carry unresolved uncertainty forward from their origin.
UNSETTLED_EXPERIMENT_LABELS = {"INCONCLUSIVE", "TOO FEW OBSERVATIONS",
                              "GUARDRAIL BREACHED", "STOPPED EARLY — DEGRADED",
                              "OBSERVATIONAL ONLY"}
UNSETTLED_RESEARCH_STANCES = {"CONFLICTING", "INSUFFICIENT", "UNKNOWN",
                              "NOT INVESTIGATED", "MIXED", "CONTRADICTED"}

# The ceiling an unsettled origin imposes on any confidence derived from
# it. Uncertainty travels; it does not evaporate on the way downstream.
UNSETTLED_CONFIDENCE_CEILING = 0.4

DEFAULT_FRESHNESS_POLICY_DAYS = 90

_COMPOSITE_WEIGHTS = {
    "evidence_coverage": 0.25,
    "research_coverage": 0.20,
    "customer_coverage": 0.20,
    "experiment_coverage": 0.15,
    "strategic_alignment": 0.15,
    "freshness": 0.05,
}
_CUSTOMER_COVERAGE_SCALE = 10       # stated, not hidden: 10+ entities is 1.0


def _score(name: str, *, value, status: str, inputs: dict, formula: str,
           reasons) -> dict:
    return {"dimension": name, "score_version": SCORE_VERSIONS[name],
            "value": value, "status": status, "inputs": inputs,
            "formula": formula, "reasons": list(reasons)}


def _unavailable(name: str, *, inputs: dict, formula: str, reason: str) -> dict:
    return _score(name, value=None, status=UNAVAILABLE, inputs=inputs,
                  formula=formula, reasons=[reason])


def _age_days(iso_ts: str, as_of: str) -> float:
    return (datetime.fromisoformat(as_of)
            - datetime.fromisoformat(iso_ts)).total_seconds() / 86400.0


def assert_not_score_shaped(payload: dict, *, where: str = "payload") -> None:
    """A drafted artifact may not carry its own score, priority, or
    confidence. Scores are computed from recorded facts at read time; an
    artifact that arrives pre-scored has been shaped to the formula, which
    is the failure this wall exists to prevent."""
    present = find_forbidden_fields(payload or {})
    scoring_fields = [f for f in present
                      if f in ("score", "scores", "priority", "priority_rank",
                               "opportunity_score", "confidence",
                               "cost_of_delay", "strategic_alignment")]
    if scoring_fields:
        raise ProductError(
            f"{where} carries author-supplied scoring fields {scoring_fields} "
            "— a score describes a proposal and does not shape it, so scores "
            "are computed from recorded facts rather than accepted as input")


# =============================================================================
# Dimensions
# =============================================================================

def evidence_coverage(facts: dict) -> dict:
    """From the T019 package coverage buckets — reused, not recomputed."""
    totals = (facts.get("research") or {}).get("coverage_totals") or {}
    inputs = {"coverage_totals": dict(totals)}
    formula = ("(covered + 0.5 * partially_covered) / questions_total, where "
               "the buckets come from the T019 evidence package")
    questions = sum(totals.values()) if totals else 0
    if not questions:
        return _unavailable(
            "evidence_coverage", inputs=inputs, formula=formula,
            reason="no research package is linked, so coverage has no "
                   "recorded input")
    value = round((totals.get("covered", 0)
                   + 0.5 * totals.get("partially_covered", 0)) / questions, 4)
    reasons = [f"{questions} question(s) in the linked package: "
               + ", ".join(f"{k}={v}" for k, v in sorted(totals.items()) if v)]
    if totals.get("not_investigated"):
        reasons.append(
            f"{totals['not_investigated']} question(s) were not investigated "
            "— that is a different gap from investigated-and-found-nothing")
    if totals.get("contradicted"):
        reasons.append(f"{totals['contradicted']} question(s) carry "
                       "conflicting evidence the sources did not settle")
    return _score("evidence_coverage", value=value, status=OK, inputs=inputs,
                  formula=formula, reasons=reasons)


def customer_coverage(facts: dict) -> dict:
    """Distinct crm_entity_ids, deduplicated. References, never copies."""
    entities = sorted({e for e in (facts.get("affected_customers") or []) if e})
    inputs = {"distinct_crm_entity_ids": entities,
              "scale": _CUSTOMER_COVERAGE_SCALE}
    formula = (f"min(distinct crm_entity_ids, {_CUSTOMER_COVERAGE_SCALE}) / "
               f"{_CUSTOMER_COVERAGE_SCALE}")
    if not entities:
        return _unavailable(
            "customer_coverage", inputs=inputs, formula=formula,
            reason="no affected customer is referenced, so customer coverage "
                   "has no recorded input")
    value = round(min(len(entities), _CUSTOMER_COVERAGE_SCALE)
                  / _CUSTOMER_COVERAGE_SCALE, 4)
    return _score("customer_coverage", value=value, status=OK, inputs=inputs,
                  formula=formula,
                  reasons=[f"{len(entities)} distinct customer entity "
                           "reference(s), deduplicated"])


def experiment_coverage(facts: dict) -> dict:
    """Linked experiments and their LABELS — the label is the fact, not the
    existence of the experiment."""
    experiments = list(facts.get("experiments") or [])
    inputs = {"experiments": [{"experiment_id": e.get("experiment_id"),
                               "label": e.get("label")}
                              for e in experiments]}
    formula = ("settled_experiments / linked_experiments, where an "
               "experiment is settled when its T018 label is outside "
               f"{sorted(UNSETTLED_EXPERIMENT_LABELS)}")
    if not experiments:
        return _unavailable(
            "experiment_coverage", inputs=inputs, formula=formula,
            reason="no experiment is linked, so experiment coverage has no "
                   "recorded input")
    unsettled = [e for e in experiments
                 if e.get("label") in UNSETTLED_EXPERIMENT_LABELS]
    value = round((len(experiments) - len(unsettled)) / len(experiments), 4)
    reasons = [f"{len(experiments)} linked experiment(s): "
               + ", ".join(sorted(f"{e.get('experiment_id')}={e.get('label')}"
                                  for e in experiments))]
    if unsettled:
        reasons.append(
            f"{len(unsettled)} experiment(s) carry an unsettled label, so "
            "they constrain rather than support this opportunity")
    return _score("experiment_coverage", value=value, status=OK, inputs=inputs,
                  formula=formula, reasons=reasons)


def research_coverage(facts: dict) -> dict:
    """Stance distribution across the linked claims."""
    stances = list((facts.get("research") or {}).get("stances") or [])
    inputs = {"stances": sorted(stances)}
    formula = "count(stance == SUPPORTED) / count(stances)"
    if not stances:
        return _unavailable(
            "research_coverage", inputs=inputs, formula=formula,
            reason="no research stance is linked, so research coverage has "
                   "no recorded input")
    supported = [s for s in stances if s == "SUPPORTED"]
    value = round(len(supported) / len(stances), 4)
    reasons = ["stance distribution: "
               + ", ".join(f"{s}={stances.count(s)}" for s in sorted(set(stances)))]
    unsettled = [s for s in stances if s in UNSETTLED_RESEARCH_STANCES]
    if unsettled:
        reasons.append(
            f"{len(unsettled)} linked claim(s) are unsettled "
            f"({', '.join(sorted(set(unsettled)))}); current evidence "
            "suggests review is required before this is treated as settled")
    return _score("research_coverage", value=value, status=OK, inputs=inputs,
                  formula=formula, reasons=reasons)


def strategic_alignment(facts: dict) -> dict:
    """Human declaration only. An agent does not infer strategy."""
    declaration = facts.get("alignment")
    inputs = {"declaration": dict(declaration) if declaration else None,
              "levels": dict(ALIGNMENT_LEVELS)}
    formula = ("the level recorded in a human strategic-alignment "
               "declaration, mapped through ALIGNMENT_LEVELS")
    if not declaration or not declaration.get("declared_by"):
        return _unavailable(
            "strategic_alignment", inputs=inputs, formula=formula,
            reason="no human strategic-alignment declaration is recorded — "
                   "strategy comes from a person, so this dimension stays "
                   "UNAVAILABLE rather than being inferred")
    level = declaration.get("level")
    if level not in ALIGNMENT_LEVELS:
        return _unavailable(
            "strategic_alignment", inputs=inputs, formula=formula,
            reason=f"the declared level {level!r} is outside the recorded "
                   f"vocabulary {sorted(ALIGNMENT_LEVELS)}")
    return _score("strategic_alignment", value=ALIGNMENT_LEVELS[level],
                  status=OK, inputs=inputs, formula=formula,
                  reasons=[f"declared {level!r} by {declaration['declared_by']}"])


def freshness(facts: dict) -> dict:
    """Age of the NEWEST load-bearing input. Old inputs label a proposal;
    they do not silently leave it active."""
    timestamps = sorted(t for t in (facts.get("input_timestamps") or []) if t)
    policy = facts.get("freshness_policy_days", DEFAULT_FRESHNESS_POLICY_DAYS)
    as_of = facts.get("as_of")
    inputs = {"input_timestamps": timestamps, "policy_days": policy,
              "as_of": as_of}
    formula = ("max(0, 1 - age_days(newest load-bearing input) / "
               "policy_days)")
    if not timestamps or not as_of:
        return _unavailable(
            "freshness", inputs=inputs, formula=formula,
            reason="no load-bearing input carries a timestamp, so freshness "
                   "has no recorded input")
    newest_age = _age_days(timestamps[-1], as_of)
    oldest_age = _age_days(timestamps[0], as_of)
    value = round(max(0.0, 1.0 - newest_age / policy), 4)
    label = "FRESH" if newest_age <= policy else "NEEDS_REFRESH"
    reasons = [f"newest load-bearing input is {newest_age:.0f} day(s) old "
               f"against a {policy}-day policy: {label}",
               f"oldest load-bearing input is {oldest_age:.0f} day(s) old"]
    out = _score("freshness", value=value, status=OK, inputs=inputs,
                 formula=formula, reasons=reasons)
    out["label"] = label
    out["newest_age_days"] = round(newest_age, 2)
    out["oldest_age_days"] = round(oldest_age, 2)
    return out


# =============================================================================
# Composite
# =============================================================================

def opportunity_score(dimensions: dict) -> dict:
    """The composite. An UNAVAILABLE dimension makes the composite
    UNAVAILABLE with the gap NAMED — it is not imputed, defaulted, or
    quietly dropped from the denominator."""
    weights = dict(_COMPOSITE_WEIGHTS)
    inputs = {name: {"value": dimensions[name]["value"],
                     "status": dimensions[name]["status"],
                     "weight": weights[name]}
              for name in sorted(weights) if name in dimensions}
    formula = ("sum(weight_d * value_d) over the six dimensions, weights "
               + ", ".join(f"{k}={v}" for k, v in sorted(weights.items())))
    missing = sorted(name for name in weights
                     if name not in dimensions
                     or dimensions[name]["status"] != OK)
    if missing:
        gaps = []
        for name in missing:
            reason = (dimensions[name]["reasons"][0]
                      if name in dimensions and dimensions[name]["reasons"]
                      else "no recorded input")
            gaps.append(f"{name}: {reason}")
        out = _unavailable(
            "opportunity_score", inputs=inputs, formula=formula,
            reason="composite withheld because " + str(len(missing))
                   + " dimension(s) have no recorded input: "
                   + ", ".join(missing))
        out["gaps"] = gaps
        out["available_dimensions"] = sorted(
            name for name in weights
            if name in dimensions and dimensions[name]["status"] == OK)
        return out
    value = round(sum(weights[name] * dimensions[name]["value"]
                      for name in weights), 4)
    out = _score("opportunity_score", value=value, status=OK, inputs=inputs,
                 formula=formula,
                 reasons=[f"{name}={dimensions[name]['value']} "
                          f"(weight {weights[name]})"
                          for name in sorted(weights)])
    out["gaps"] = []
    out["available_dimensions"] = sorted(weights)
    return out


# =============================================================================
# The four confidences
# =============================================================================

def _unsettled_reasons(facts: dict) -> list:
    reasons = []
    stances = [s for s in ((facts.get("research") or {}).get("stances") or [])
               if s in UNSETTLED_RESEARCH_STANCES]
    if stances:
        reasons.append(
            "linked research is unsettled ("
            + ", ".join(sorted(set(stances)))
            + "), which lowers confidence rather than being averaged away")
    labels = [e.get("label") for e in (facts.get("experiments") or [])
              if e.get("label") in UNSETTLED_EXPERIMENT_LABELS]
    if labels:
        reasons.append(
            "linked experiment(s) carry an unsettled label ("
            + ", ".join(sorted(set(labels)))
            + "), and that uncertainty travels to anything derived from them")
    origin_label = (facts.get("origin") or {}).get("label")
    if origin_label in (UNSETTLED_EXPERIMENT_LABELS
                        | UNSETTLED_RESEARCH_STANCES):
        reasons.append(
            f"this opportunity originated from a {origin_label} artifact, so "
            "a confident score is not available to it")
    return reasons


def problem_confidence(facts: dict) -> dict:
    """How much the evidence FOR THE PROBLEM can bear."""
    refs = list(facts.get("evidence_references") or [])
    customers = sorted({e for e in (facts.get("affected_customers") or []) if e})
    kinds = sorted({r.get("kind") for r in refs if r.get("kind")})
    inputs = {"reference_count": len(refs), "reference_kinds": kinds,
              "distinct_customers": len(customers)}
    formula = ("0.4 * min(reference_count, 3)/3 + 0.3 * min(distinct "
               "reference kinds, 3)/3 + 0.3 * min(distinct customers, 3)/3, "
               f"then capped at {UNSETTLED_CONFIDENCE_CEILING} when a linked "
               "input is unsettled")
    if not refs:
        return _unavailable(
            "problem_confidence", inputs=inputs, formula=formula,
            reason="no evidence reference is recorded for this problem")
    value = (0.4 * min(len(refs), 3) / 3
             + 0.3 * min(len(kinds), 3) / 3
             + 0.3 * min(len(customers), 3) / 3)
    reasons = [f"{len(refs)} evidence reference(s) across {len(kinds)} kind(s)"
               f"; {len(customers)} distinct customer reference(s)"]
    unsettled = _unsettled_reasons(facts)
    if unsettled and value > UNSETTLED_CONFIDENCE_CEILING:
        value = UNSETTLED_CONFIDENCE_CEILING
        reasons.append(f"capped at {UNSETTLED_CONFIDENCE_CEILING}")
    reasons.extend(unsettled)
    return _score("problem_confidence", value=round(value, 4), status=OK,
                  inputs=inputs, formula=formula, reasons=reasons)


def opportunity_confidence(facts: dict, problem_conf: dict,
                           dimensions: dict) -> dict:
    """How much the FRAMING of the opportunity can bear. Distinct from the
    problem's confidence: a well-evidenced problem can carry a poorly
    evidenced opportunity."""
    research = dimensions.get("research_coverage", {})
    experiment = dimensions.get("experiment_coverage", {})
    inputs = {"problem_confidence": problem_conf.get("value"),
              "research_coverage": research.get("value"),
              "research_status": research.get("status"),
              "experiment_coverage": experiment.get("value"),
              "experiment_status": experiment.get("status"),
              "origin": dict(facts.get("origin") or {})}
    formula = ("mean of the available inputs among problem_confidence, "
               "research_coverage and experiment_coverage, then capped at "
               f"{UNSETTLED_CONFIDENCE_CEILING} when the origin or a linked "
               "input is unsettled")
    available = [v for v in (problem_conf.get("value"),
                             research.get("value") if research.get("status") == OK
                             else None,
                             experiment.get("value") if experiment.get("status") == OK
                             else None)
                 if v is not None]
    if not available:
        return _unavailable(
            "opportunity_confidence", inputs=inputs, formula=formula,
            reason="neither the problem, the research, nor an experiment "
                   "carries a recorded input for this opportunity")
    value = sum(available) / len(available)
    reasons = [f"mean of {len(available)} available input(s)"]
    for name, block in (("research_coverage", research),
                        ("experiment_coverage", experiment)):
        if block and block.get("status") != OK:
            reasons.append(f"{name} is UNAVAILABLE and was excluded rather "
                           "than counted as zero")
    unsettled = _unsettled_reasons(facts)
    if unsettled and value > UNSETTLED_CONFIDENCE_CEILING:
        value = UNSETTLED_CONFIDENCE_CEILING
        reasons.append(f"capped at {UNSETTLED_CONFIDENCE_CEILING}")
    reasons.extend(unsettled)
    return _score("opportunity_confidence", value=round(value, 4), status=OK,
                  inputs=inputs, formula=formula, reasons=reasons)


def proposal_confidence(facts: dict, opportunity_conf: dict) -> dict:
    """How much THIS SOLUTION can bear. Unknowns and open questions lower
    it; that is what they are for."""
    unknowns = list(facts.get("unknowns") or [])
    assumptions = list(facts.get("assumptions") or [])
    open_questions = list(facts.get("open_questions") or [])
    inputs = {"unknown_count": len(unknowns),
              "assumption_count": len(assumptions),
              "open_question_count": len(open_questions),
              "opportunity_confidence": opportunity_conf.get("value")}
    formula = ("opportunity_confidence * (1 - min(unknowns + open_questions, "
               "6)/12), then capped when a linked input is unsettled")
    if opportunity_conf.get("status") != OK:
        return _unavailable(
            "proposal_confidence", inputs=inputs, formula=formula,
            reason="opportunity_confidence is UNAVAILABLE, so a proposal "
                   "derived from it has no recorded basis either")
    open_count = len(unknowns) + len(open_questions)
    value = opportunity_conf["value"] * (1 - min(open_count, 6) / 12)
    reasons = [f"{len(unknowns)} unknown(s), {len(open_questions)} open "
               f"question(s), {len(assumptions)} stated assumption(s)"]
    unsettled = _unsettled_reasons(facts)
    if unsettled and value > UNSETTLED_CONFIDENCE_CEILING:
        value = UNSETTLED_CONFIDENCE_CEILING
        reasons.append(f"capped at {UNSETTLED_CONFIDENCE_CEILING}")
    reasons.extend(unsettled)
    return _score("proposal_confidence", value=round(value, 4), status=OK,
                  inputs=inputs, formula=formula, reasons=reasons)


def execution_confidence(facts: dict) -> dict:
    """How ready this is to be built — a different question again, and the
    one an execution system would actually ask."""
    spec = facts.get("spec") or {}
    inputs = {"spec_present": bool(spec.get("exists")),
              "spec_debt_count": len(spec.get("debt") or []),
              "acceptance_criteria": spec.get("acceptance_criteria", 0),
              "unmet_dependencies": facts.get("dependencies_unmet", 0),
              "decision_linked": bool(facts.get("decision_id"))}
    formula = ("0.4 * spec_present + 0.2 * (acceptance_criteria > 0) + 0.2 * "
               "(1 - min(spec_debt, 5)/5) + 0.1 * (unmet_dependencies == 0) + "
               "0.1 * decision_linked")
    if not spec.get("exists"):
        return _unavailable(
            "execution_confidence", inputs=inputs, formula=formula,
            reason="no spec draft is bound to this proposal version, so "
                   "readiness to build has no recorded input")
    debt = len(spec.get("debt") or [])
    value = (0.4
             + 0.2 * (1 if spec.get("acceptance_criteria", 0) > 0 else 0)
             + 0.2 * (1 - min(debt, 5) / 5)
             + 0.1 * (1 if not facts.get("dependencies_unmet") else 0)
             + 0.1 * (1 if facts.get("decision_id") else 0))
    reasons = [f"spec draft present with "
               f"{spec.get('acceptance_criteria', 0)} acceptance criterion(s) "
               f"and {debt} recorded spec-debt item(s)"]
    if facts.get("dependencies_unmet"):
        reasons.append(f"{facts['dependencies_unmet']} dependency(ies) are "
                       "not yet met, which lowers readiness")
    if not facts.get("decision_id"):
        reasons.append("no Decision Record is linked; review is required "
                       "before this becomes an execution candidate")
    return _score("execution_confidence", value=round(value, 4), status=OK,
                  inputs=inputs, formula=formula, reasons=reasons)


# =============================================================================
# Cost of delay — separate, deliberately
# =============================================================================

def cost_of_delay(facts: dict) -> dict:
    """What it costs to postpone. Computed apart from opportunity_score,
    because "how valuable" and "how expensive to wait" are different
    questions and averaging them destroys both.

    The revenue input comes only from a human declaration: this repository
    holds no revenue data, and inventing one would be the kind of number
    that later gets quoted as though it were measured.
    """
    customers = sorted({e for e in (facts.get("affected_customers") or []) if e})
    at_risk = sorted({f.get("crm_entity_id") for f in (facts.get("crm_facts") or [])
                      if f.get("event_type") in ("crm.churned",
                                                 "crm.customer_at_risk")
                      and f.get("crm_entity_id")})
    guardrail = [e for e in (facts.get("experiments") or [])
                 if e.get("label") == "GUARDRAIL BREACHED"]
    risks = list(facts.get("risks") or [])
    revenue = facts.get("revenue_at_risk_declared")
    fresh = freshness(facts)

    components = {
        "declared_revenue_at_risk": {
            "value": revenue,
            "status": OK if revenue is not None else UNAVAILABLE,
            "note": ("a human declaration; this repository records no revenue "
                     "data, so an undeclared value stays UNAVAILABLE")},
        "customer_pain": {
            "value": len(at_risk) or None,
            "status": OK if at_risk else UNAVAILABLE,
            "note": f"{len(at_risk)} referenced entity(ies) carry a churn or "
                    "at-risk fact"},
        "research_freshness": {
            "value": fresh.get("newest_age_days"),
            "status": fresh["status"],
            "note": fresh["reasons"][0] if fresh["reasons"] else ""},
        "growth_urgency": {
            "value": len(guardrail) or None,
            "status": OK if guardrail else UNAVAILABLE,
            "note": f"{len(guardrail)} linked experiment(s) breached a "
                    "pre-registered guardrail"},
        "risk": {
            "value": len(risks) or None,
            "status": OK if risks else UNAVAILABLE,
            "note": f"{len(risks)} recorded risk(s) on the proposal"},
    }
    inputs = {"components": components,
              "distinct_affected_customers": len(customers)}
    formula = ("reported per component; a composite is withheld until a "
               "human declares revenue_at_risk, because every other "
               "component is a count and averaging counts with an undeclared "
               "money figure would invent the figure")

    missing = sorted(name for name, block in components.items()
                     if block["status"] != OK)
    if missing:
        out = _unavailable(
            "cost_of_delay", inputs=inputs, formula=formula,
            reason="composite withheld; component(s) with no recorded input: "
                   + ", ".join(missing))
        out["gaps"] = [f"{name}: {components[name]['note']}"
                       for name in missing]
        out["components"] = components
        return out
    value = round(min(1.0, (0.4 * min(len(at_risk), 5) / 5
                            + 0.3 * min(len(guardrail), 2) / 2
                            + 0.2 * min(len(risks), 5) / 5
                            + 0.1)), 4)
    out = _score("cost_of_delay", value=value, status=OK, inputs=inputs,
                 formula=formula,
                 reasons=[f"{len(at_risk)} at-risk or churned entity "
                          f"reference(s); {len(guardrail)} guardrail "
                          f"breach(es); {len(risks)} recorded risk(s)"])
    out["gaps"] = []
    out["components"] = components
    return out


# =============================================================================
# The whole block
# =============================================================================

def score_block(facts: dict) -> dict:
    """Every dimension, every confidence, and cost of delay — computed once
    from one deterministic fact set."""
    dimensions = {
        "evidence_coverage": evidence_coverage(facts),
        "customer_coverage": customer_coverage(facts),
        "experiment_coverage": experiment_coverage(facts),
        "research_coverage": research_coverage(facts),
        "strategic_alignment": strategic_alignment(facts),
        "freshness": freshness(facts),
    }
    composite = opportunity_score(dimensions)
    problem_conf = problem_confidence(facts)
    opportunity_conf = opportunity_confidence(facts, problem_conf, dimensions)
    proposal_conf = proposal_confidence(facts, opportunity_conf)
    execution_conf = execution_confidence(facts)
    return {
        "dimensions": dimensions,
        "opportunity_score": composite,
        "confidence": {
            "problem_confidence": problem_conf,
            "opportunity_confidence": opportunity_conf,
            "proposal_confidence": proposal_conf,
            "execution_confidence": execution_conf,
        },
        "cost_of_delay": cost_of_delay(facts),
        "score_versions": dict(SCORE_VERSIONS),
        "policy": ("scores describe proposals; a proposal is not modified in "
                   "order to improve one"),
    }

"""Six independent readiness dimensions, impact, and reversibility (T021).

There is no overall executive score. Six dimensions are computed
separately, because they fail separately and a founder needs to know
WHICH one is missing:

    evidence_readiness      is there enough recorded evidence
    execution_readiness     could this be built if chosen
    strategic_readiness     does it sit under a declared theme
    financial_readiness     is the money question answered
    operational_readiness   is there an owner and a clear path
    decision_readiness      YES/NO — could a person decide this today

`decision_readiness` is deliberately NOT a confidence. It is a yes-or-no
with stated reasons, because "62% ready" is not a thing a founder can act
on, while "no — the experiment has not run and nobody owns it" is.

IMPACT is computed from recorded scope, never asked of a model.
REVERSIBILITY is DECLARED per option and aggregated to the worst case,
never inferred — whether a thing can be undone is a judgment about the
world, and a wrong guess errs in the most expensive direction.

READINESS POLICY (structural, not advisory): readiness describes
decisions. It does not shape them. A candidate is never modified in order
to improve its readiness, and an author-supplied readiness value is
rejected rather than recorded — see `assert_not_readiness_shaped`.
"""
from __future__ import annotations

from intent_engine.executive.records import (
    IMPACT_LARGE, IMPACT_LEVELS, IMPACT_MEDIUM, IMPACT_RULE_VERSION,
    IMPACT_SMALL, IMPACT_TRANSFORMATIONAL, REVERSIBILITY_IRREVERSIBLE,
    ExecutiveError, find_forbidden_fields, least_reversible,
)

OK = "OK"
UNAVAILABLE = "UNAVAILABLE"

READINESS_VERSIONS = {
    "evidence_readiness": "evidence_readiness.v1",
    "execution_readiness": "execution_readiness.v1",
    "strategic_readiness": "strategic_readiness.v1",
    "financial_readiness": "financial_readiness.v1",
    "operational_readiness": "operational_readiness.v1",
    "decision_readiness": "decision_readiness.v1",
}

_UNSETTLED_STANCES = {"CONFLICTING", "CONTRADICTED", "MIXED", "INSUFFICIENT",
                      "UNKNOWN", "NOT INVESTIGATED"}
_UNSETTLED_LABELS = {"INCONCLUSIVE", "TOO FEW OBSERVATIONS",
                     "GUARDRAIL BREACHED", "OBSERVATIONAL ONLY",
                     "STOPPED EARLY — DEGRADED"}


def _dimension(name: str, *, value, status: str, inputs: dict, formula: str,
               reasons) -> dict:
    return {"dimension": name, "readiness_version": READINESS_VERSIONS[name],
            "value": value, "status": status, "inputs": inputs,
            "formula": formula, "reasons": list(reasons)}


def _unavailable(name: str, *, inputs: dict, formula: str,
                 reason: str) -> dict:
    return _dimension(name, value=None, status=UNAVAILABLE, inputs=inputs,
                      formula=formula, reasons=[reason])


def assert_not_readiness_shaped(payload: dict, *, where: str = "payload") -> None:
    """An artifact may not carry its own readiness, impact, reversibility,
    or priority. Those are computed from recorded facts at read time; an
    artifact that arrives pre-scored has been shaped to the formula, which
    is the failure this wall prevents."""
    present = find_forbidden_fields(payload or {})
    shaped = [f for f in present
              if f in ("readiness", "decision_readiness", "evidence_readiness",
                       "execution_readiness", "strategic_readiness",
                       "financial_readiness", "operational_readiness",
                       "impact", "reversibility", "score", "scores",
                       "priority", "priority_rank", "escalation",
                       "queue_position")]
    if shaped:
        raise ExecutiveError(
            f"{where} carries author-supplied readiness fields {shaped} — "
            "readiness describes a decision and does not shape it, so it is "
            "computed from recorded facts rather than accepted as input")


# =============================================================================
# The six dimensions
# =============================================================================

def evidence_readiness(facts: dict) -> dict:
    research = facts.get("research") or {}
    stances = list(research.get("stances") or [])
    references = list(facts.get("references") or [])
    inputs = {"stance_count": len(stances),
              "stances": sorted(set(stances)),
              "reference_count": len(references)}
    formula = ("settled_stances / total_stances, where a stance is settled "
               f"when it lies outside {sorted(_UNSETTLED_STANCES)}")
    if not stances:
        return _unavailable(
            "evidence_readiness", inputs=inputs, formula=formula,
            reason="no research stance is linked, so evidence readiness has "
                   "no recorded input")
    unsettled = [s for s in stances if s in _UNSETTLED_STANCES]
    value = round((len(stances) - len(unsettled)) / len(stances), 4)
    reasons = [f"{len(stances)} linked stance(s); {len(unsettled)} unsettled"]
    if unsettled:
        reasons.append(
            "unsettled research lowers evidence readiness and is named "
            "rather than averaged away: "
            + ", ".join(sorted(set(unsettled))))
    return _dimension("evidence_readiness", value=value, status=OK,
                      inputs=inputs, formula=formula, reasons=reasons)


def execution_readiness(facts: dict) -> dict:
    """Read from T020: is there a spec, how much spec debt, how many
    dependencies are unmet. Not recomputed here."""
    product = facts.get("product") or {}
    inputs = {"spec_present": bool(product.get("spec_present")),
              "spec_debt": product.get("spec_debt_count"),
              "unmet_dependencies": len(facts.get("unmet_dependencies") or []),
              "proposal_status": product.get("proposal_status")}
    formula = ("0.5 * spec_present + 0.3 * (1 - min(spec_debt, 5)/5) + "
               "0.2 * (unmet_dependencies == 0)")
    if not product:
        return _unavailable(
            "execution_readiness", inputs=inputs, formula=formula,
            reason="no product proposal is linked, so execution readiness "
                   "has no recorded input")
    if not product.get("spec_present"):
        return _unavailable(
            "execution_readiness", inputs=inputs, formula=formula,
            reason="the linked proposal carries no spec draft, so readiness "
                   "to build has no recorded input")
    debt = product.get("spec_debt_count") or 0
    unmet = len(facts.get("unmet_dependencies") or [])
    value = round(0.5 + 0.3 * (1 - min(debt, 5) / 5)
                  + 0.2 * (1 if not unmet else 0), 4)
    reasons = [f"spec draft present with {debt} recorded spec-debt item(s)"]
    if unmet:
        reasons.append(f"{unmet} dependency(ies) are not yet met")
    return _dimension("execution_readiness", value=value, status=OK,
                      inputs=inputs, formula=formula, reasons=reasons)


def strategic_readiness(facts: dict) -> dict:
    """From a human alignment declaration only. An agent does not decide
    whether something is strategic."""
    alignment = facts.get("alignment")
    inputs = {"declaration": dict(alignment) if alignment else None}
    formula = ("1.0 when a human has declared this candidate aligned to a "
               "theme, otherwise UNAVAILABLE")
    if not alignment or not alignment.get("declared_by"):
        return _unavailable(
            "strategic_readiness", inputs=inputs, formula=formula,
            reason="no human alignment declaration is recorded — whether "
                   "this belongs to a strategic theme comes from a person")
    return _dimension("strategic_readiness", value=1.0, status=OK,
                      inputs=inputs, formula=formula,
                      reasons=[f"declared {alignment.get('level')!r} by "
                               f"{alignment['declared_by']}"])


def financial_readiness(facts: dict) -> dict:
    """Structurally UNAVAILABLE without a human declaration. This
    repository records no budget or revenue data, and a proxied figure is
    the kind of number that later gets quoted as though it were
    measured."""
    budget = facts.get("budget")
    inputs = {"declaration": dict(budget) if budget else None,
              "needs_budget": bool(facts.get("needs_budget"))}
    formula = ("1.0 when a human has declared an available budget covering "
               "this decision, otherwise UNAVAILABLE — no figure is derived")
    if not budget or budget.get("amount_available") is None:
        return _unavailable(
            "financial_readiness", inputs=inputs, formula=formula,
            reason="no budget declaration is recorded; this repository holds "
                   "no financial data, so the dimension stays UNAVAILABLE "
                   "rather than being estimated from something else")
    return _dimension("financial_readiness", value=1.0, status=OK,
                      inputs=inputs, formula=formula,
                      reasons=[f"budget declared by {budget.get('declared_by')}"])


def operational_readiness(facts: dict) -> dict:
    """Is there an owner, and is the path clear right now."""
    owner = facts.get("owner")
    blocked = list(facts.get("unmet_dependencies") or [])
    open_debt = list(facts.get("open_debt") or [])
    inputs = {"owner": owner, "unmet_dependencies": len(blocked),
              "open_decision_debt": len(open_debt)}
    formula = ("0.5 * owner_present + 0.25 * (unmet_dependencies == 0) + "
               "0.25 * (open_decision_debt == 0)")
    if owner is None and not blocked and not open_debt:
        return _unavailable(
            "operational_readiness", inputs=inputs, formula=formula,
            reason="no owner, dependency, or debt fact is recorded, so "
                   "operational readiness has no recorded input")
    value = round(0.5 * (1 if owner else 0)
                  + 0.25 * (1 if not blocked else 0)
                  + 0.25 * (1 if not open_debt else 0), 4)
    reasons = []
    reasons.append(f"owner: {owner}" if owner else
                   "no owner is recorded for this decision")
    if blocked:
        reasons.append(f"{len(blocked)} unmet dependency(ies)")
    if open_debt:
        reasons.append(f"{len(open_debt)} open decision-debt item(s)")
    return _dimension("operational_readiness", value=value, status=OK,
                      inputs=inputs, formula=formula, reasons=reasons)


def decision_readiness(facts: dict, dimensions: dict) -> dict:
    """YES or NO, with reasons. Not a confidence, and not a percentage.

    A founder can act on "no — the experiment has not run and nobody owns
    it". Nobody can act on "0.62".
    """
    missing = []
    if dimensions["evidence_readiness"]["status"] != OK:
        missing.append("missing evidence")
    elif dimensions["evidence_readiness"]["value"] < 1.0:
        unsettled = dimensions["evidence_readiness"]["inputs"]["stances"]
        missing.append(f"unsettled evidence ({', '.join(unsettled)})")
    for name, label in (("strategic_readiness", "missing strategy"),
                        ("operational_readiness", "missing owner or a clear "
                                                  "path")):
        if dimensions[name]["status"] != OK:
            missing.append(label)
    if dimensions["operational_readiness"]["status"] == OK \
            and not facts.get("owner"):
        missing.append("missing owner")
    if facts.get("needs_budget") and \
            dimensions["financial_readiness"]["status"] != OK:
        missing.append("missing budget")
    for item in (facts.get("open_debt") or []):
        if item.get("kind") == "need_experiment":
            missing.append("missing experiment")
        elif item.get("kind") == "need_customer_validation":
            missing.append("missing customer validation")
        elif item.get("kind") == "need_legal_review":
            missing.append("missing legal review")
        elif item.get("kind") == "need_engineering_estimate":
            missing.append("missing engineering estimate")

    missing = sorted(set(missing))
    inputs = {"blocking_gaps": missing,
              "dimension_statuses": {name: block["status"]
                                     for name, block in sorted(dimensions.items())}}
    formula = ("YES when no blocking gap is recorded across the other five "
               "dimensions and the open decision debt; otherwise NO with "
               "every gap named")
    if missing:
        return _dimension("decision_readiness", value=False, status=OK,
                          inputs=inputs, formula=formula,
                          reasons=[f"not ready: {gap}" for gap in missing])
    return _dimension("decision_readiness", value=True, status=OK,
                      inputs=inputs, formula=formula,
                      reasons=["every recorded input a decision needs is "
                               "present; review required before anything "
                               "follows from it"])


# =============================================================================
# Impact — computed from recorded scope
# =============================================================================

def decision_impact(facts: dict) -> dict:
    """From recorded scope: how many customers, how many downstream
    decisions, how many initiatives, and whether the choice can be undone.

    Never asked of a model, and never declared as a bare adjective.
    """
    customers = sorted({c for c in (facts.get("affected_customers") or []) if c})
    downstream = list(facts.get("downstream_decisions") or [])
    initiatives = sorted({i for i in (facts.get("initiatives") or []) if i})
    reversibility = facts.get("reversibility")
    inputs = {"distinct_customers": len(customers),
              "downstream_decisions": len(downstream),
              "initiatives": len(initiatives),
              "reversibility": reversibility}
    formula = ("scope = distinct_customers + 2*downstream_decisions + "
               "2*initiatives; small <2, medium <6, large <12, "
               "transformational otherwise; an irreversible decision is "
               "raised one level, because an undoable mistake and a "
               "permanent one differ in kind")
    if not customers and not downstream and not initiatives:
        return {"dimension": "impact", "rule_version": IMPACT_RULE_VERSION,
                "value": None, "status": UNAVAILABLE, "inputs": inputs,
                "formula": formula,
                "reasons": ["no scope fact is recorded, so impact has no "
                            "recorded input"]}

    scope = len(customers) + 2 * len(downstream) + 2 * len(initiatives)
    if scope < 2:
        level = IMPACT_SMALL
    elif scope < 6:
        level = IMPACT_MEDIUM
    elif scope < 12:
        level = IMPACT_LARGE
    else:
        level = IMPACT_TRANSFORMATIONAL
    reasons = [f"scope score {scope} from {len(customers)} customer "
               f"reference(s), {len(downstream)} downstream decision(s), "
               f"{len(initiatives)} initiative(s)"]
    if reversibility == REVERSIBILITY_IRREVERSIBLE and level != IMPACT_TRANSFORMATIONAL:
        raised = IMPACT_LEVELS[IMPACT_LEVELS.index(level) + 1]
        reasons.append(f"raised from {level} to {raised}: the declared "
                       "reversibility is irreversible")
        level = raised
    return {"dimension": "impact", "rule_version": IMPACT_RULE_VERSION,
            "value": level, "status": OK, "inputs": inputs,
            "formula": formula, "reasons": reasons}


# =============================================================================
# Reversibility — declared, aggregated to the worst case
# =============================================================================

def aggregate_reversibility(options: list) -> dict:
    """A candidate is as reversible as its least reversible option."""
    declared = [o.get("reversibility") for o in options]
    worst = least_reversible(declared)
    inputs = {"declared_per_option": declared}
    if worst is None:
        return {"dimension": "reversibility", "value": None,
                "status": UNAVAILABLE, "inputs": inputs,
                "formula": "the least reversible declared option",
                "reasons": ["no option declares a reversibility, so this is "
                            "UNAVAILABLE rather than assumed easy — "
                            "reversibility is declared, not inferred"]}
    return {"dimension": "reversibility", "value": worst, "status": OK,
            "inputs": inputs,
            "formula": "the least reversible declared option",
            "reasons": [f"least reversible of {len(declared)} option(s): "
                        f"{worst}"]}


# =============================================================================
# The whole block
# =============================================================================

def readiness_block(facts: dict, options=None) -> dict:
    """Every dimension, impact, and reversibility, from one fact set.

    No composite exists. Six statuses side by side is the artifact.
    """
    dimensions = {
        "evidence_readiness": evidence_readiness(facts),
        "execution_readiness": execution_readiness(facts),
        "strategic_readiness": strategic_readiness(facts),
        "financial_readiness": financial_readiness(facts),
        "operational_readiness": operational_readiness(facts),
    }
    dimensions["decision_readiness"] = decision_readiness(facts, dimensions)
    reversibility = aggregate_reversibility(list(options or []))
    impact = decision_impact({**facts,
                              "reversibility": reversibility.get("value")})
    return {
        "dimensions": dimensions,
        "impact": impact,
        "reversibility": reversibility,
        "readiness_versions": dict(READINESS_VERSIONS),
        "unavailable_dimensions": sorted(
            name for name, block in dimensions.items()
            if block["status"] != OK),
        "policy": ("readiness describes decisions; a candidate is not "
                   "modified in order to improve one"),
        "note": ("six statuses side by side, with no composite — a single "
                 "number would hide which one is missing, and which one is "
                 "missing is the actionable part"),
    }

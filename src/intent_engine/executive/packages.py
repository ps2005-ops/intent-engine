"""Decision packages and option sets (T021).

A decision package is the artifact a founder opens from the queue. It
RENDERS a Decision Context and adds the argument: the decision in
question, the options with their tradeoffs, the disagreement, the
unknowns, the predictions, and the debt.

The escalation decision — WHO should decide — is separate from the
recommendation. Not every candidate deserves founder attention; some
should be monitored, some reviewed next month, some taken to the board.
The executive layer decides who should decide, and says so.

"No recommendation" is a first-class outcome. Forcing a recommendation
out of thin evidence is exactly the overclaim the walls exist to prevent,
so a package may honestly decline — stating its reason, its evidence gap,
and a review date.
"""
from __future__ import annotations

from intent_engine.executive.records import (
    ESCALATION_LEVELS, ESCALATION_MONITOR, ESCALATION_NEEDS_BOARD,
    ESCALATION_NEEDS_FOUNDER, ESCALATION_REVIEW_SCHEDULED,
    ESCALATION_RULE_VERSION, IMPACT_LARGE, IMPACT_TRANSFORMATIONAL,
    REQUIRED_OPTION_PARTS, REVERSIBILITY_HARD, REVERSIBILITY_IRREVERSIBLE,
    REVERSIBILITY_LEVELS, ExecutiveError, assert_no_certainty,
    assert_recommendation_language,
)

PACKAGE_VERSION = "decision_package.v1"


def build_option(*, label: str, benefits, costs, risks, unknowns,
                 dependencies, reversibility: str,
                 evidence_label: str = "UNKNOWN") -> dict:
    """One option in a set. All six parts mandatory; reversibility
    declared, not inferred."""
    if not str(label or "").strip():
        raise ExecutiveError("an option states what it is")
    parts = {"benefits": list(benefits or []), "costs": list(costs or []),
             "risks": list(risks or []), "unknowns": list(unknowns or []),
             "dependencies": list(dependencies or [])}
    for name in ("benefits", "costs", "risks", "unknowns"):
        if not parts[name]:
            raise ExecutiveError(
                f"an option states its {name}; an option with none has had "
                "them omitted rather than examined")
    if reversibility not in REVERSIBILITY_LEVELS:
        raise ExecutiveError(
            f"an option declares reversibility from {list(REVERSIBILITY_LEVELS)}"
            " — whether a choice can be undone is a judgment about the world, "
            "declared rather than inferred")
    body = "\n".join([label] + [str(v) for values in parts.values()
                                for v in values])
    assert_recommendation_language(body, where="option")
    assert_no_certainty(body, evidence_label, where="option")
    # `dependencies` is stated explicitly (possibly empty) rather than
    # omitted, so the reviewer sees "no dependencies" as a claim.
    return {"label": label.strip(), "reversibility": reversibility, **parts}


def build_package(*, decision_question: str, references, unknowns,
                  dependencies, risks, prediction_references=None,
                  conflict_summary=None, research_debt=None, spec_debt=None,
                  decision_debt=None, recommended_next_review: str = "",
                  provenance=None, evidence_label: str = "UNKNOWN") -> dict:
    """The package body. Options are recorded separately (they have their
    own lifecycle event), but a package heading to review must carry at
    least two — enforced in state.py."""
    if not str(decision_question or "").strip():
        raise ExecutiveError("a package states the decision in question")
    if not references:
        raise ExecutiveError("a package cites at least one reference")
    if not unknowns:
        raise ExecutiveError(
            "a package states at least one unknown — a package claiming none "
            "is hiding them, which is the failure this bar catches")

    body = "\n".join([decision_question]
                     + [str(u) for u in unknowns]
                     + [str(r) for r in (risks or [])]
                     + [recommended_next_review])
    assert_recommendation_language(body, where="package")
    assert_no_certainty(body, evidence_label, where="package")

    return {
        "package_contract_version": PACKAGE_VERSION,
        "decision_question": decision_question.strip(),
        "references": list(references),
        "unknowns": list(unknowns),
        "dependencies": list(dependencies or []),
        "risks": list(risks or []),
        "prediction_references": list(prediction_references or []),
        "conflict_summary": conflict_summary or {"total": 0, "kinds": []},
        "research_debt": list(research_debt or []),
        "spec_debt": list(spec_debt or []),
        "decision_debt": list(decision_debt or []),
        "recommended_next_review": recommended_next_review,
        "provenance": dict(provenance or {}),
        "candidate": True,
        "disposition_note": ("a decision package for review; accept, reject, "
                             "defer, and merge are founder acts recorded "
                             "separately"),
    }


def build_no_recommendation(*, reason: str, evidence_gap: str,
                            review_date: str) -> dict:
    """A first-class successful outcome. Declining to recommend when the
    evidence cannot bear a recommendation is honest, not a failure."""
    for name, value in (("reason", reason), ("evidence_gap", evidence_gap),
                        ("review_date", review_date)):
        if not str(value or "").strip():
            raise ExecutiveError(f"a no-recommendation states its {name}")
    assert_recommendation_language(reason, where="no-recommendation reason")
    return {"outcome": "no_recommendation", "reason": reason.strip(),
            "evidence_gap": evidence_gap.strip(), "review_date": review_date,
            "note": ("no recommendation is a legitimate outcome; the gap is "
                     "named and a review date is set rather than forcing a "
                     "recommendation out of thin evidence")}


def cross_agent_provenance(*, versions: dict, contributing) -> dict:
    """Every package states which subsystems it was generated from, with
    versions. This is what makes a recommendation debuggable six months
    later."""
    return {"generated_from": sorted(set(contributing)),
            "versions": dict(versions),
            "note": ("the subsystems this recommendation drew on, with their "
                     "versions — so a later reader can reproduce the inputs "
                     "or find where one changed")}


# =============================================================================
# Escalation — who should decide
# =============================================================================

def assign_escalation(*, readiness_block: dict, impact: dict,
                      conflict_summary: dict, decision_class: str) -> dict:
    """Deterministic: WHO should decide, from recorded facts. A stated
    ladder, not a judgment call."""
    decision_ready = readiness_block["dimensions"]["decision_readiness"]["value"]
    impact_level = impact.get("value")
    reversibility = readiness_block["reversibility"].get("value")
    conflicts = conflict_summary.get("total", 0)

    reasons = []
    level = ESCALATION_MONITOR

    if not decision_ready:
        level = ESCALATION_REVIEW_SCHEDULED
        reasons.append("not decision-ready yet; scheduled for review rather "
                       "than surfaced for a choice now")
    else:
        level = ESCALATION_NEEDS_FOUNDER
        reasons.append("decision-ready: it is a choice a person can make now")

    if impact_level in (IMPACT_LARGE, IMPACT_TRANSFORMATIONAL) \
            or reversibility in (REVERSIBILITY_HARD, REVERSIBILITY_IRREVERSIBLE) \
            or decision_class == "governance":
        if impact_level == IMPACT_TRANSFORMATIONAL \
                or reversibility == REVERSIBILITY_IRREVERSIBLE \
                or decision_class == "governance":
            level = ESCALATION_NEEDS_BOARD
            reasons.append(
                f"raised to board: impact={impact_level}, "
                f"reversibility={reversibility}, class={decision_class} — a "
                "transformational or irreversible or governance decision")
        elif level != ESCALATION_REVIEW_SCHEDULED:
            level = ESCALATION_NEEDS_FOUNDER
            reasons.append(f"kept at founder: impact={impact_level}, "
                           f"reversibility={reversibility}")

    if conflicts and level == ESCALATION_MONITOR:
        level = ESCALATION_REVIEW_SCHEDULED
        reasons.append(f"{conflicts} unresolved conflict(s) — reviewed rather "
                       "than left monitored")

    return {"escalation_version": ESCALATION_RULE_VERSION, "level": level,
            "reasons": reasons,
            "note": ("who should decide is a separate question from what to "
                     "recommend; not every candidate deserves founder "
                     "attention today")}

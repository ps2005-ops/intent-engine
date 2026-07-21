"""Proposals and solution sets (T020) — structured artifacts, not tickets.

A proposal is a CANDIDATE solution to one recorded problem. It carries
what is known, what is unknown, and what is assumed — all three,
separately stored, all three mandatory. A proposal claiming no unknowns
is rejected: that is a tell, not a strength.

Proposals live inside a SOLUTION SET, because the founder is choosing
among options rather than approving one in isolation:

    Solution set for problem P
        Proposal A  (candidate)
        Proposal B  (candidate, alternative_to A)
        Proposal C  (candidate, alternative_to A and B)

Proposals also go stale. A proposal whose load-bearing inputs have aged
past the freshness policy is labelled NEEDS_REFRESH rather than quietly
remaining active, and a proposal that has stopped being sound is RETIRED
— which is a different fact from having been rejected.
"""
from __future__ import annotations

from intent_engine.product.records import (
    RETIREMENT_REASONS, WORK_CATEGORIES, ProductError, assert_no_certainty,
    assert_product_language,
)
from intent_engine.product.scoring import assert_not_score_shaped

PROPOSAL_VERSION = "product_proposal.v1"

REQUIRED_PROPOSAL_PARTS = ("candidate_solution", "tradeoffs", "risks",
                           "known", "unknown", "assumptions")


def build_proposal(*, candidate_solution: str, tradeoffs, risks, known,
                   unknown, assumptions, open_questions=None,
                   dependencies=None, work_category: str = "unknown",
                   solution_set_id: str = None,
                   evidence_label: str = "UNKNOWN") -> dict:
    """The structural bars, applied before anything is written."""
    if not str(candidate_solution or "").strip():
        raise ProductError(
            "a proposal states a candidate solution; an empty one is not a "
            "proposal")
    if work_category not in WORK_CATEGORIES:
        raise ProductError(
            f"unknown work_category {work_category!r} — one of "
            f"{sorted(WORK_CATEGORIES)}")

    parts = {"tradeoffs": list(tradeoffs or []), "risks": list(risks or []),
             "known": list(known or []), "unknown": list(unknown or []),
             "assumptions": list(assumptions or [])}
    for name in ("known", "unknown", "assumptions"):
        if not parts[name]:
            raise ProductError(
                f"{name} is mandatory and separately stored on every "
                "proposal — a proposal that states no unknowns is hiding "
                "them, which is the failure this bar exists to catch")
    for name in ("tradeoffs", "risks"):
        if not parts[name]:
            raise ProductError(
                f"{name} is mandatory: a candidate solution with none stated "
                "has had them omitted rather than examined")

    body = "\n".join([candidate_solution]
                     + [str(v) for values in parts.values() for v in values]
                     + [str(q) for q in (open_questions or [])])
    assert_product_language(body, where="proposal")
    assert_no_certainty(body, evidence_label, where="proposal")

    return {
        "proposal_contract_version": PROPOSAL_VERSION,
        "candidate_solution": candidate_solution.strip(),
        "candidate": True,
        "solution_set_id": solution_set_id,
        "work_category": work_category,
        "tradeoffs": parts["tradeoffs"],
        "risks": parts["risks"],
        "known": parts["known"],
        "unknown": parts["unknown"],
        "assumptions": parts["assumptions"],
        "open_questions": list(open_questions or []),
        "dependencies": list(dependencies or []),
        "disposition_note": ("this is a proposal for review; acceptance, "
                             "rejection, merging, and deferral are founder "
                             "acts recorded separately"),
    }


def assert_drafted_payload_is_clean(payload: dict, *, where: str) -> list:
    """A drafted body may not smuggle in a reference, an identifier, or a
    score. Returns the offending fields so the refusal can be recorded as
    a typed fact rather than raised into silence."""
    assert_not_score_shaped(payload, where=where)
    return []


def freshness_label(newest_age_days, policy_days: int) -> str:
    if newest_age_days is None:
        return "UNAVAILABLE"
    return "FRESH" if newest_age_days <= policy_days else "NEEDS_REFRESH"


def validate_retirement(reason: str) -> str:
    """Retirement is not rejection. A rejected proposal was declined on its
    merits; a retired one stopped being sound."""
    if reason not in RETIREMENT_REASONS:
        raise ProductError(
            f"a retirement reason is one of {sorted(RETIREMENT_REASONS)}; "
            f"{reason!r} is outside that vocabulary. Rejection is a separate "
            "founder act with its own record")
    return reason


def solution_set_report(index, problem_id: str) -> dict:
    """What the founder is actually choosing between, for one problem."""
    proposals = index.proposals_for_problem(problem_id)
    return {
        "problem_id": problem_id,
        "proposal_count": len(proposals),
        "proposals": [{"proposal_id": p["proposal_id"],
                       "version": p["version"],
                       "status": p["status"],
                       "opportunity_id": p["opportunity_id"],
                       "work_category": p.get("work_category", "unknown")}
                      for p in proposals],
        "note": ("one problem may carry several candidate solutions; the "
                 "founder chooses among the set rather than approving one in "
                 "isolation"),
    }

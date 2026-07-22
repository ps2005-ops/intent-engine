"""Automatic decision-candidate intake (T021).

The executive layer does not invent decisions. It reads what the other
subsystems have already surfaced and turns each into a candidate that
cites its origin:

    an ACCEPTED T020 proposal linked to a Decision Record
                                    -> a decision candidate
    an open decision-debt item      -> a decision candidate
    an EXPIRED decision (a load-bearing input changed underneath it)
                                    -> a decision candidate to revisit

Bars, each individually tested:

    intake is deterministic and idempotent — the candidate's dedup key
        derives from its origin, so re-running creates no duplicates
    every candidate cites its origin and carries >= 1 reference
    a candidate is a CANDIDATE: it enters the index and a triage queue,
        and it produces no package, no decision, and no execution
    the origin's uncertainty travels: an expired decision does not become
        confidently-ready just because it was re-surfaced
"""
from __future__ import annotations

import hashlib

from intent_engine.executive.records import (
    REF_DECISION, REF_OPPORTUNITY, REF_PROPOSAL, ExecutiveError,
)

INTAKE_VERSION = "executive_intake.v1"


def _dedup_key(origin_kind: str, origin_id: str) -> str:
    payload = f"{origin_kind}|{origin_id}"
    return "deccand-" + hashlib.sha256(payload.encode()).hexdigest()[:32]


def _candidate(*, intake_kind, origin, references, decision_class,
               decision_horizon, title):
    if not references:
        raise ExecutiveError(
            "an intake candidate carries at least one reference — a decision "
            "candidate that resolves to nothing is invalid")
    return {
        "intake_version": INTAKE_VERSION,
        "intake_kind": intake_kind,
        "candidate": True,
        "title": title,
        "origin": origin,
        "references": references,
        "decision_class": decision_class,
        "decision_horizon": decision_horizon,
        "dedup_key": _dedup_key(origin["kind"], origin["origin_id"]),
    }


def candidate_from_accepted_proposal(proposal: dict, *, proposal_id: str,
                                     decision_id: str = None) -> dict:
    """A T020 proposal the founder accepted becomes a decision candidate:
    the product question was settled, and the execution question — commit
    to it, when, at what cost — is a decision."""
    refs = [{"kind": REF_PROPOSAL, "ref_id": proposal_id,
             "version": proposal.get("proposal_version")}]
    if proposal.get("opportunity_id"):
        refs.append({"kind": REF_OPPORTUNITY,
                     "ref_id": proposal["opportunity_id"]})
    if decision_id:
        refs.append({"kind": REF_DECISION, "ref_id": decision_id})
    work = proposal.get("work_category", "unknown")
    decision_class = {"customer_work": "product", "growth_bet": "marketing",
                      "technical_debt": "technical", "research": "operational",
                      "compliance": "governance"}.get(work, "operational")
    return _candidate(
        intake_kind="accepted_proposal",
        origin={"kind": "product_proposal", "origin_id": proposal_id,
                "work_category": work},
        references=refs, decision_class=decision_class,
        decision_horizon="short_term",
        title=f"Commit to accepted proposal {proposal_id}?")


def candidate_from_decision_debt(debt_item: dict, *, candidate_id: str) -> dict:
    """An open decision-debt item is itself a decision the founder owes:
    somebody has to choose to run the experiment, get the review, or set
    the price."""
    kind = debt_item.get("kind")
    return _candidate(
        intake_kind="decision_debt",
        origin={"kind": "decision_debt", "origin_id": f"{candidate_id}:{kind}",
                "debt_kind": kind},
        references=[{"kind": REF_PROPOSAL, "ref_id": candidate_id,
                     "detail": debt_item.get("detail", "")}],
        decision_class="operational", decision_horizon="short_term",
        title=f"Resolve decision debt: {kind}")


def candidate_from_expired_decision(*, decision_id: str, expiry: dict,
                                    references) -> dict:
    """An expired decision — a load-bearing input changed underneath it —
    becomes a candidate to revisit, carrying WHICH input moved so the
    founder is not asked to rediscover it."""
    validated = list(references or [])
    if not any(r.get("kind") == REF_DECISION for r in validated):
        validated.append({"kind": REF_DECISION, "ref_id": decision_id})
    return _candidate(
        intake_kind="expired_decision",
        origin={"kind": "expired_decision", "origin_id": decision_id,
                "changed_inputs": expiry.get("changed_inputs"),
                "reasons": expiry.get("reasons", [])},
        references=validated, decision_class="operational",
        decision_horizon="short_term",
        title=f"Revisit decision {decision_id} — a load-bearing input changed")

"""Decision debt (T021) — the counterpart of research debt and spec debt.

What a decision waits on that only a person resolves. Continuously
surfaced, never hidden, and each item states both what it waits on and
what would clear it — so a founder reading the queue sees the unblock,
not just the block.

Debt is DERIVED deterministically from recorded facts (an INCONCLUSIVE
experiment implies `need_experiment`; an unmet budget implies
`need_budget`) and from what a candidate's origin already stated. Nothing
here is drafted.
"""
from __future__ import annotations

from intent_engine.executive.records import DECISION_DEBT_KINDS, ExecutiveError

DEBT_VERSION = "decision_debt.v1"

# What clears each kind, stated once so the queue can render the unblock.
_CLEARS_WHEN = {
    "need_founder_choice": "the founder records a choice among the options",
    "need_legal_review": "a legal review is recorded",
    "need_pricing": "a pricing decision is recorded",
    "need_experiment": "a growth experiment settles the open question",
    "need_customer_validation": "customer validation is recorded",
    "need_research": "a research package addresses the open question",
    "need_budget": "a budget is declared covering this decision",
    "need_engineering_estimate": "an engineering estimate is recorded",
}


def _item(kind: str, detail: str) -> dict:
    if kind not in DECISION_DEBT_KINDS:
        raise ExecutiveError(f"unknown decision-debt kind: {kind!r}")
    return {"kind": kind, "detail": detail,
            "clears_when": _CLEARS_WHEN[kind], "debt_version": DEBT_VERSION}


def derive_decision_debt(facts: dict) -> list:
    """Deterministic: the same facts produce the same debt, in a stable
    order, with no duplicates."""
    debt = []

    research = facts.get("research") or {}
    stances = list(research.get("stances") or [])
    if not stances:
        debt.append(_item("need_research",
                          "no research stance is linked to this decision"))
    elif any(s in ("INSUFFICIENT", "UNKNOWN", "NOT INVESTIGATED")
             for s in stances):
        debt.append(_item("need_research",
                          "linked research withholds a direction on the "
                          "question that would settle this"))

    for experiment in (facts.get("experiments") or []):
        label = experiment.get("label")
        if label in ("INCONCLUSIVE", "TOO FEW OBSERVATIONS"):
            debt.append(_item("need_experiment",
                             f"experiment {experiment.get('experiment_id')} "
                             f"closed {label} without settling its question"))

    crm = facts.get("crm") or {}
    if crm.get("category") == "AT_RISK":
        debt.append(_item("need_customer_validation",
                          "customer facts indicate urgency; direct validation "
                          "of the cause is not recorded"))

    if facts.get("needs_budget") and facts.get("budget_declared") is False:
        debt.append(_item("need_budget",
                          "this decision would spend, and no budget covering "
                          "it is declared"))

    if facts.get("alignment") is None and facts.get("decision_class") in (
            "strategic", "governance"):
        debt.append(_item("need_founder_choice",
                          "a strategic or governance decision with no "
                          "recorded alignment needs a founder direction"))

    product = facts.get("product") or {}
    if product and not product.get("spec_present"):
        debt.append(_item("need_engineering_estimate",
                          "the linked proposal has no spec draft, so its "
                          "build cost is unestimated"))

    # carry through any origin-stated debt kinds verbatim
    for stated in (facts.get("stated_debt") or []):
        kind = stated.get("kind")
        if kind in DECISION_DEBT_KINDS:
            debt.append(_item(kind, stated.get("detail", "stated by origin")))

    seen, unique = set(), []
    for item in debt:
        key = (item["kind"], item["detail"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def debt_report(items: list) -> dict:
    by_kind = {}
    for item in items:
        by_kind.setdefault(item["kind"], []).append(item["detail"])
    return {"debt_version": DEBT_VERSION, "total": len(items),
            "by_kind": {k: sorted(v) for k, v in sorted(by_kind.items())},
            "items": items,
            "note": ("decision debt is surfaced continuously; every item "
                     "names what it waits on and what would clear it")}

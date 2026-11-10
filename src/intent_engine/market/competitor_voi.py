"""Competitive uncertainty worth paying to resolve — and the rest, refused.

WHY MOST COMPETITIVE UNCERTAINTY IS NOT WORTH ANYTHING
------------------------------------------------------
"Are these two firms broadly peers?" has no answer that changes anything a
founder does. It is the kind of question a competitive-intelligence system
produces endlessly because it is easy to ask and impossible to be wrong
about.

So an item is admitted only when resolving it would change a NAMED decision
field — pricing, timing, migration risk, distribution, differentiation. An
item with no decision field is refused at construction, which is the same
rule `value_of_information` already applies to belief uncertainty and the
same reason.

WHAT MAKES A COMPETITIVE QUESTION ANSWERABLE
--------------------------------------------
Each item names the SOURCE FAMILY that could resolve it, taken from the
measured routing rather than from a guess. A question nobody can answer with
any source the engine has is still a real uncertainty and it is recorded as
UNRESOLVABLE rather than as a research priority — because putting it in the
queue would consume budget forever.
"""
from __future__ import annotations

import collections
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "competitor_voi.v1"

# --- decision fields a competitive answer may move --------------------------
PRICING_WATCH = "PRICING_WATCH"
MIGRATION_RISK = "MIGRATION_RISK"
DISTRIBUTION_RISK = "DISTRIBUTION_RISK"
DIFFERENTIATION = "DIFFERENTIATION"
OPTION_TIMING = "OPTION_TIMING"
SWITCHING_COST = "SWITCHING_COST"
CUSTOMER_LOSS_RISK = "CUSTOMER_LOSS_RISK"

DECISION_FIELDS = (PRICING_WATCH, MIGRATION_RISK, DISTRIBUTION_RISK,
                   DIFFERENTIATION, OPTION_TIMING, SWITCHING_COST,
                   CUSTOMER_LOSS_RISK)

HIGH = "VOI_HIGH"
MEDIUM = "VOI_MEDIUM"
LOW = "VOI_LOW"
UNRESOLVABLE = "UNRESOLVABLE"
PRIORITIES = (HIGH, MEDIUM, LOW, UNRESOLVABLE)


class ItemRejected(ValueError):
    """A question was proposed that no decision depends on."""


@dataclass(frozen=True)
class CompetitorVOIItem:
    item_id: str
    uncertainty: str
    subject: str
    counterparty: str
    decision_field: str
    decision_relevance: str
    competing_explanations: Tuple[str, ...]
    evidence_needed: str
    source_family: str
    resolution_window: str
    priority: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "item_id": self.item_id,
            "uncertainty": self.uncertainty, "subject": self.subject,
            "counterparty": self.counterparty,
            "decision_field": self.decision_field,
            "decision_relevance": self.decision_relevance,
            "competing_explanations": list(self.competing_explanations),
            "evidence_needed": self.evidence_needed,
            "source_family": self.source_family,
            "resolution_window": self.resolution_window,
            "priority": self.priority, "reason": self.reason,
        }


def item(*, uncertainty: str, subject: str, counterparty: str,
         decision_field: str, decision_relevance: str,
         competing_explanations: Sequence[str], evidence_needed: str,
         source_family: str = "", resolution_window: str = "") -> \
        CompetitorVOIItem:
    """Admit one competitive question, or refuse it for changing nothing."""
    if decision_field not in DECISION_FIELDS:
        raise ItemRejected(
            f"{decision_field!r} is not a decision this engine holds; a "
            f"question that moves no named field is a fact nobody acts on")
    if not decision_relevance.strip():
        raise ItemRejected(
            "state what would change if this resolved; 'it would be good to "
            "know' is the sentence this gate exists to refuse")
    alternatives = tuple(a for a in competing_explanations if a.strip())
    if len(alternatives) < 2:
        raise ItemRejected(
            "a question with fewer than two competing answers is not "
            "uncertain; it is a lookup")
    if not evidence_needed.strip():
        raise ItemRejected("name the observation that would resolve it")

    priority, reason = _priority(decision_field, source_family)
    raw = f"{subject}|{counterparty}|{uncertainty}".lower()
    return CompetitorVOIItem(
        item_id="cvoi_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        uncertainty=" ".join(uncertainty.split()), subject=subject,
        counterparty=counterparty, decision_field=decision_field,
        decision_relevance=decision_relevance.strip(),
        competing_explanations=alternatives,
        evidence_needed=evidence_needed.strip(),
        source_family=source_family, resolution_window=resolution_window,
        priority=priority, reason=reason)


#: Fields where being wrong costs money soonest. Ordinal, not scored: there
#: is no sample against which a number could be calibrated.
_URGENT = frozenset({PRICING_WATCH, CUSTOMER_LOSS_RISK, MIGRATION_RISK})


def _priority(decision_field: str, source_family: str) -> Tuple[str, str]:
    if not source_family:
        return UNRESOLVABLE, (
            "no source family the engine has measured could answer this. It "
            "is a real uncertainty and it is not a research priority — "
            "queueing it would consume budget forever")
    if decision_field in _URGENT:
        return HIGH, (f"{decision_field} moves before the others do, and the "
                      f"answer is reachable through {source_family}")
    return MEDIUM, (f"{decision_field} is real and slower-moving; "
                    f"{source_family} could resolve it")


def from_state(*, relationships: Sequence = (), actions: Sequence = (),
               objects_by_action: Optional[Dict[str, object]] = None,
               routing: Optional[Dict[str, Tuple[str, ...]]] = None
               ) -> Tuple[CompetitorVOIItem, ...]:
    """Build the watchlist from real competitive state, refusing the rest.

    Generates from what is UNCERTAIN, never from what is merely known: a
    relationship that exists is not a question, and a relationship whose
    workflow scope is unestablished is.
    """
    routes = routing or {}
    objects = objects_by_action or {}
    out: List[CompetitorVOIItem] = []

    for rel in relationships:
        subject = getattr(rel, "actor_b", "") or ""
        counterparty = getattr(rel, "actor_a", "") or ""
        obj = getattr(rel, "competitive_object", "")
        # The rivalry is established; what is uncertain is how WIDE it is.
        # That is decision-relevant because a rivalry confined to one
        # workflow implies a different response than one across a platform.
        try:
            out.append(item(
                uncertainty=(f"whether {counterparty} and {subject} contest "
                             f"{obj} in the same buying decision, or only "
                             f"share a category"),
                subject=subject, counterparty=counterparty,
                decision_field=DIFFERENTIATION,
                decision_relevance=(
                    "a rivalry confined to one workflow calls for a feature "
                    "answer; one across the buying decision calls for a "
                    "pricing or packaging answer"),
                competing_explanations=(
                    "they contest the same buyer's decision directly",
                    "they serve adjacent workflows for the same buyer",
                    "one is a component the other resells"),
                evidence_needed=("a buyer document naming both and the "
                                 "decision it was making"),
                source_family=(routes.get("COMPETITOR_RELATIONSHIP") or
                               ("",))[0]))
        except ItemRejected:
            continue

    for act in actions:
        obj = objects.get(getattr(act, "action_id", ""))
        if obj is not None and getattr(obj, "is_usable", False):
            continue          # established: not uncertain any more
        try:
            out.append(item(
                uncertainty=(f"what buying decision {getattr(act, 'actor', '')}"
                             f"'s {getattr(act, 'action_type', '')} targets"),
                subject=getattr(act, "actor", ""), counterparty="",
                decision_field=OPTION_TIMING,
                decision_relevance=(
                    "an action aimed at the same buyer changes what to watch "
                    "next; one aimed elsewhere changes nothing, and the "
                    "engine currently cannot tell which"),
                competing_explanations=(
                    "it targets the same buyer and workflow",
                    "it targets an adjacent segment",
                    "it is unrelated to the contested decision"),
                evidence_needed=("a launch, pricing or migration page naming "
                                 "the buyer segment the action is for"),
                source_family=(routes.get("ACTION_OBJECT") or ("",))[0]))
        except ItemRejected:
            continue
    return tuple(out)


def summarise(items: Sequence[CompetitorVOIItem]) -> dict:
    counts = collections.Counter(i.priority for i in items)
    return {
        "contract": CONTRACT,
        "items": len(items),
        "by_priority": {p: counts.get(p, 0) for p in PRIORITIES},
        "by_decision_field": dict(collections.Counter(i.decision_field
                                                      for i in items)),
        "actionable": sum(1 for i in items if i.priority in (HIGH, MEDIUM)),
        "unresolvable": counts.get(UNRESOLVABLE, 0),
        "highest": next((i.uncertainty for i in items if i.priority == HIGH),
                        ""),
        "note": ("an item is admitted only when resolving it would move a "
                 "NAMED decision field; 'are these firms peers' moves none "
                 "and is refused at construction"),
    }

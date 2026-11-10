"""What to go and find out, phrased so the answer is allowed to be either way.

THE FAILURE THIS AVOIDS
-----------------------
    bad    "Find evidence that Salesforce competes with Shopify."
    bad    "Find evidence this belief is wrong."
    good   "Retrieve the buyer segment Salesforce names for Commerce Cloud."

The first two commission a conclusion. A pipeline that asks them will find
them, because the corpus is large and the query is a filter. The third asks
for an OBSERVATION and lets it come back either way — which is the only kind
of question whose answer is worth anything.

ROUTING IS BY MISSING FACT, NOT BY HABIT
----------------------------------------
Wave 10 measured release_notes as the only family that ever established an
object, and the next instinct was to route everything there. But a release
note cannot tell you who a product is FOR, and a pricing page cannot tell
you WHEN something shipped. The missing fact chooses the family; measured
performance orders what remains.
"""
from __future__ import annotations

import collections
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "research_priority.v1"

# --- what is missing --------------------------------------------------------
NEED_DATE = "NEED_DATE"
NEED_BUYER = "NEED_BUYER"
NEED_WORKFLOW = "NEED_WORKFLOW"
NEED_SUBSTITUTE = "NEED_SUBSTITUTE"
NEED_RESPONSE = "NEED_RESPONSE"
NEED_SUPPLIER = "NEED_SUPPLIER"
NEED_CREDIT = "NEED_CREDIT"
NEED_OUTCOME = "NEED_OUTCOME"

MISSING_FACTS = (NEED_DATE, NEED_BUYER, NEED_WORKFLOW, NEED_SUBSTITUTE,
                 NEED_RESPONSE, NEED_SUPPLIER, NEED_CREDIT, NEED_OUTCOME)

#: Which document classes can answer each. A family absent from a row cannot
#: answer that question however well it performs elsewhere — the same
#: predicate-first rule the source planner already uses.
ROUTES: Dict[str, Tuple[str, ...]] = {
    NEED_DATE: ("newsroom", "release_notes", "changelog", "investor_release"),
    NEED_BUYER: ("pricing_page", "solution_page", "customer_launch_page",
                 "plan_comparison"),
    NEED_WORKFLOW: ("product_docs", "release_notes", "product_launch_page"),
    NEED_SUBSTITUTE: ("migration_page", "comparison_page",
                      "customer_migration_story"),
    NEED_RESPONSE: ("pricing_page", "release_notes", "migration_page",
                    "investor_release"),
    NEED_SUPPLIER: ("regulatory_filing", "supplier_disclosure",
                    "procurement_record"),
    NEED_CREDIT: ("regulatory_filing", "debt_filing", "investor_release"),
    NEED_OUTCOME: ("regulatory_filing", "investor_release",
                   "customer_case_study"),
}

#: Phrasings that commission a conclusion instead of asking for a fact.
_LEADING = re.compile(
    r"\b(?:find\s+evidence\s+that|prove|confirm\s+that|show\s+that|"
    r"demonstrate\s+that|verify\s+that\s+\w+\s+competes|"
    r"evidence\s+(?:against|the\s+belief\s+is\s+wrong))\b", re.I)

_TEMPLATES: Dict[str, str] = {
    NEED_DATE: "Retrieve the publication or effective date {actor} states "
               "for: {detail}",
    NEED_BUYER: "Retrieve the buyer segment or customer type {actor} names "
                "for: {detail}",
    NEED_WORKFLOW: "Retrieve the workflow or capability {actor} says is "
                   "affected by: {detail}",
    NEED_SUBSTITUTE: "Retrieve the product or platform {actor} names as "
                     "being replaced in: {detail}",
    NEED_RESPONSE: "Retrieve {actor}'s next published pricing, packaging or "
                   "product change bearing on: {detail}",
    NEED_SUPPLIER: "Retrieve the suppliers or dependencies {actor} names in "
                   "its own disclosures for: {detail}",
    NEED_CREDIT: "Retrieve {actor}'s reported borrowing cost, covenant or "
                 "capital position bearing on: {detail}",
    NEED_OUTCOME: "Retrieve the next reported outcome for {actor} bearing "
                  "on: {detail}",
}


class PriorityRejected(ValueError):
    pass


@dataclass(frozen=True)
class ResearchPriority:
    priority_id: str
    subject: str
    missing_fact: str
    question: str
    why_it_matters: str
    hypotheses_discriminated: Tuple[str, ...]
    eligible_source_families: Tuple[str, ...]
    voi: float
    resolution_window: str
    provenance: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "priority_id": self.priority_id,
            "subject": self.subject, "missing_fact": self.missing_fact,
            "question": self.question, "why_it_matters": self.why_it_matters,
            "hypotheses_discriminated": list(self.hypotheses_discriminated),
            "eligible_source_families": list(self.eligible_source_families),
            "voi": round(self.voi, 4),
            "resolution_window": self.resolution_window,
            "provenance": dict(self.provenance),
        }


def route(missing_fact: str,
          performance: Optional[Dict[str, float]] = None) -> Tuple[str, ...]:
    """Families that can answer, best-measured first.

    Membership is by what the question NEEDS; order is by what has actually
    worked. A family that has never been tried keeps a neutral position
    rather than sinking below one measured at zero.
    """
    families = ROUTES.get(missing_fact, ())
    if not performance:
        return families
    return tuple(sorted(
        families,
        key=lambda f: (-(performance.get(f, 0.5)), families.index(f))))


def priority(*, subject: str, missing_fact: str, detail: str,
             why_it_matters: str, hypotheses: Sequence[str] = (),
             voi: float = 0.0, resolution_window: str = "",
             performance: Optional[Dict[str, float]] = None,
             provenance: Optional[Dict[str, str]] = None) -> ResearchPriority:
    if missing_fact not in MISSING_FACTS:
        raise PriorityRejected(f"{missing_fact!r} is not a missing fact")
    if not detail.strip():
        raise PriorityRejected("a priority with no subject matter asks nothing")
    question = _TEMPLATES[missing_fact].format(
        actor=subject.strip() or "the actor", detail=" ".join(detail.split()))
    if _LEADING.search(question) or _LEADING.search(why_it_matters or ""):
        raise PriorityRejected(
            "this commissions a conclusion rather than asking for an "
            "observation; a pipeline asked to find evidence FOR something "
            "will find it")
    raw = f"{subject}|{missing_fact}|{detail}".lower()
    return ResearchPriority(
        priority_id="rpr_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        subject=subject.strip(), missing_fact=missing_fact, question=question,
        why_it_matters=" ".join((why_it_matters or "").split()),
        hypotheses_discriminated=tuple(hypotheses),
        eligible_source_families=route(missing_fact, performance),
        voi=float(voi), resolution_window=resolution_window[:10],
        provenance=dict(provenance or {}))


def rank(priorities: Sequence[ResearchPriority]
         ) -> Tuple[ResearchPriority, ...]:
    return tuple(sorted(priorities, key=lambda p: (-p.voi, p.subject)))


def summarise(priorities: Sequence[ResearchPriority]) -> dict:
    by_fact = collections.Counter(p.missing_fact for p in priorities)
    return {
        "contract": CONTRACT,
        "priorities": len(priorities),
        "by_missing_fact": {f: by_fact.get(f, 0) for f in MISSING_FACTS
                            if by_fact.get(f, 0)},
        "families_used": sorted({f for p in priorities
                                 for f in p.eligible_source_families}),
        "note": ("routing is by the MISSING FACT. A release note cannot say "
                 "who a product is for, and a pricing page cannot say when "
                 "something shipped, however well either has performed."),
    }

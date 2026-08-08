"""The thing being contested — read off the document, never handed to it.

THE DISCIPLINE THIS COMPLETES
-----------------------------
Wave 6 scored 18 RELEVANT action/rivalry pairs. Every one was a Salesforce
post about AI agents, and every one "contested" an e-commerce platform,
because the harness that fetched the pages had LABELLED them that way and
the relevance check trusted the label. The system was narrating its own
assumption back to itself with a confidence score attached.

That is the same failure the project has already fixed four times under
different names — subject ownership, event attribution, mechanism gating,
causal status. Here it is competitive-object ownership: **the evidence must
establish what economic object is being contested.**

So `extract` reads the action's own sentence and nothing else. Nothing in
this module imports the universe, the curated competitor list, or the
fetching harness's opinion. Those may label an evaluation set; they may not
supply an object.

WHY FOUR STATES AND NOT TWO
---------------------------
"Salesforce launches Agentforce" establishes nothing. "Salesforce launches
Commerce Cloud checkout for enterprise retailers" establishes a product, a
workflow and a buyer. Between them sits a large middle — a product with no
buyer, a buyer with no product — and forcing that middle into either bucket
is how a system either fabricates relevance or throws away real signal.

    ESTABLISHED   enough to locate the action economically
    PARTIAL       one axis, not two; readable, not usable
    UNKNOWN       nothing locates it
    CONTRADICTED  the document names an object that rules the rivalry out

PARTIAL never creates an interaction. It is reported so the gap is legible
and so a later document can complete it.
"""
from __future__ import annotations

import collections
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "competitive_object.v1"

# --- categories -------------------------------------------------------------
PRODUCT = "PRODUCT"
WORKFLOW = "WORKFLOW"
BUYING_DECISION = "BUYING_DECISION"
BUDGET = "BUDGET"
DISTRIBUTION_CHANNEL = "DISTRIBUTION_CHANNEL"
CUSTOMER_SEGMENT = "CUSTOMER_SEGMENT"
GEOGRAPHIC_MARKET = "GEOGRAPHIC_MARKET"
PLATFORM_LAYER = "PLATFORM_LAYER"

CATEGORIES = (PRODUCT, WORKFLOW, BUYING_DECISION, BUDGET,
              DISTRIBUTION_CHANNEL, CUSTOMER_SEGMENT, GEOGRAPHIC_MARKET,
              PLATFORM_LAYER)

# --- standing ---------------------------------------------------------------
ESTABLISHED = "ESTABLISHED"
PARTIAL = "PARTIAL"
UNKNOWN = "UNKNOWN"
CONTRADICTED = "CONTRADICTED"
STANDINGS = (ESTABLISHED, PARTIAL, UNKNOWN, CONTRADICTED)

#: Words that look like an economic object and locate nothing. Each of these
#: appeared in the live corpus attached to an action that established no
#: object whatever.
_VACUOUS = frozenset({
    "ai", "artificial intelligence", "agent", "agents", "agentic",
    "commerce", "enterprise", "platform", "cloud", "software", "data",
    "digital", "technology", "solution", "solutions", "product", "products",
    "service", "services", "business", "innovation", "experience",
    "experiences", "the future", "work", "productivity",
})

#: A named buyer or segment. "for enterprise retailers", "for SMB merchants",
#: "for financial-services customers". The qualifier is what makes it a
#: buyer rather than an adjective.
_BUYER = re.compile(
    r"\bfor\s+((?:small|mid[-\s]?market|midmarket|enterprise|smb|large|"
    r"global|independent|emerging|financial[-\s]services|retail|healthcare|"
    r"public[-\s]sector|government|b2b|b2c|direct[-\s]to[-\s]consumer)"
    r"(?:[-\s]\w+){0,3}?\s+"
    r"(?:merchants?|retailers?|customers?|buyers?|businesses|companies|"
    r"brands?|sellers?|firms?|institutions?|agencies|teams?|developers?))",
    re.I)

#: The workflow or job the action touches. Needs a concrete noun, not a
#: category: "checkout", "order management", "customer support".
_WORKFLOW = re.compile(
    r"\b(checkout|order\s+management|inventory\s+management|fulfil?lment|"
    r"payments?|billing|subscription\s+management|customer\s+support|"
    r"point\s+of\s+sale|storefront|catalog(?:ue)?\s+management|"
    r"warehouse\s+workloads?|data\s+warehouse|identity\s+management|"
    r"content\s+management|marketing\s+automation|returns?\s+processing|"
    r"tax\s+calculation|shipping\s+labels?|replatform(?:ing)?|migration)\b",
    re.I)

#: A named product being launched or changed. Capitalised, multi-token, and
#: not the actor's own name alone.
_PRODUCT_NAME = re.compile(
    r"\b(?:launch(?:ed|es|ing)?|introduc(?:ed|es|ing)|announc(?:ed|es|ing)|"
    r"unveil(?:ed|s|ing)|releas(?:ed|es|ing))\s+"
    r"(?:the\s+|its\s+|a\s+|new\s+)?"
    r"([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,3})")

#: A budget the action targets. "CRM seat budget", "commerce spend".
_BUDGET = re.compile(
    r"\b((?:\w+\s+){0,2}(?:seat|licence|license|subscription|platform|"
    r"software|infrastructure)\s+(?:budget|spend|spending|cost|costs))\b",
    re.I)

#: A priced tier is a "what": "cut its Plus pricing", "raised Enterprise
#: rates". The tier name locates the action inside a product line, which is
#: what a price change contests.
_TIER = re.compile(
    r"\b(?:its\s+|the\s+)?([A-Z][A-Za-z0-9]+)\s+"
    r"(?:pricing|plan|tier|edition|subscription)\b")

#: The document names an object that puts the action OUTSIDE the rivalry.
_ELSEWHERE = re.compile(
    r"\bnot\s+(?:a\s+)?(?:commerce|retail|storefront)\b|"
    r"\bunrelated\s+to\s+(?:commerce|retail)\b", re.I)


@dataclass(frozen=True)
class CompetitiveObject:
    object_id: str
    category: str
    workflow: str
    buyer: str
    budget: str
    use_case: str
    market_scope: str
    geography: str
    evidence_ids: Tuple[str, ...]
    source_spans: Tuple[str, ...]
    standing: str
    created_at: str
    missing: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "object_id": self.object_id,
            "category": self.category, "workflow": self.workflow,
            "buyer": self.buyer, "budget": self.budget,
            "use_case": self.use_case, "market_scope": self.market_scope,
            "geography": self.geography,
            "evidence_ids": list(self.evidence_ids),
            "source_spans": list(self.source_spans),
            "standing": self.standing, "created_at": self.created_at,
            "missing": list(self.missing),
        }

    @property
    def is_usable(self) -> bool:
        """Only ESTABLISHED may reach relevance. PARTIAL is legible, not usable."""
        return self.standing == ESTABLISHED


@dataclass(frozen=True)
class ActionObjectEvidence:
    """The span that established it, so a disputed object is argued from text."""
    action_id: str
    object_id: str
    matched_span: str
    subject: str
    buyer_or_workflow: str
    source: str
    standing: str

    def as_dict(self) -> dict:
        return {"action_id": self.action_id, "object_id": self.object_id,
                "matched_span": self.matched_span, "subject": self.subject,
                "buyer_or_workflow": self.buyer_or_workflow,
                "source": self.source, "standing": self.standing}


def _vacuous(text: str) -> bool:
    return " ".join((text or "").lower().split()) in _VACUOUS


def extract(span: str, *, action_id: str, actor: str, source: str,
            created_at: str, evidence_ids: Sequence[str] = ()
            ) -> Tuple[Optional[CompetitiveObject],
                       Optional[ActionObjectEvidence]]:
    """Read the object off the ACTION'S OWN SENTENCE, or return UNKNOWN.

    There is no parameter through which a caller can supply an object. That
    is deliberate and it is the whole point of the module: a competitive
    object that arrives from outside the document cannot be evidence of what
    the document's action contests.
    """
    text = " ".join((span or "").split())
    spans: List[str] = []

    buyer_hit = _BUYER.search(text)
    buyer = buyer_hit.group(1).strip() if buyer_hit else ""
    if buyer:
        spans.append(buyer_hit.group(0))

    workflow_hit = _WORKFLOW.search(text)
    workflow = workflow_hit.group(1).strip() if workflow_hit else ""
    if workflow:
        spans.append(workflow_hit.group(0))

    product_hit = _PRODUCT_NAME.search(text)
    product = product_hit.group(1).strip() if product_hit else ""
    if product and (_vacuous(product)
                    or product.lower() == (actor or "").lower()):
        product = ""
    if product:
        spans.append(product_hit.group(0))

    tier_hit = _TIER.search(text)
    tier = tier_hit.group(1).strip() if tier_hit else ""
    if tier and (_vacuous(tier) or tier.lower() == (actor or "").lower()):
        tier = ""
    if tier:
        spans.append(tier_hit.group(0))
        product = product or f"{tier} tier"

    budget_hit = _BUDGET.search(text)
    budget = budget_hit.group(1).strip() if budget_hit else ""
    if budget:
        spans.append(budget_hit.group(0))

    if _ELSEWHERE.search(text):
        standing, category = CONTRADICTED, WORKFLOW
    else:
        # ESTABLISHED needs TWO axes: something being contested, and who is
        # choosing. One alone locates nothing economically — a product with
        # no buyer could be sold to anybody, and a buyer with no product
        # could be sold anything.
        axes = sum(1 for value in (buyer, workflow or product, budget)
                   if value)
        has_who = bool(buyer)
        has_what = bool(workflow or product or budget)
        if has_who and has_what:
            standing = ESTABLISHED
        elif axes:
            standing = PARTIAL
        else:
            standing = UNKNOWN
        category = (WORKFLOW if workflow else
                    BUDGET if budget else
                    PRODUCT if product else
                    CUSTOMER_SEGMENT if buyer else PLATFORM_LAYER)

    missing = tuple(name for name, value in
                    (("buyer", buyer), ("workflow_or_product",
                                        workflow or product)) if not value)
    if standing == UNKNOWN:
        return None, None

    raw = f"{category}|{workflow or product}|{buyer}|{budget}".lower()
    obj = CompetitiveObject(
        object_id="obj_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        category=category, workflow=workflow, buyer=buyer, budget=budget,
        use_case=workflow or product, market_scope="", geography="",
        evidence_ids=tuple(evidence_ids) or (f"doc:{source}",),
        source_spans=tuple(spans), standing=standing,
        created_at=created_at[:10], missing=missing)
    return obj, ActionObjectEvidence(
        action_id=action_id, object_id=obj.object_id,
        matched_span=text[:280], subject=actor,
        buyer_or_workflow=(f"{buyer} / {workflow or product}").strip(" /"),
        source=source, standing=standing)


# --- overlap ----------------------------------------------------------------
STRONG = "STRONG"
ADJACENT = "ADJACENT"
NONE = "NONE"


def overlap(action_object: CompetitiveObject,
            relationship_object: str) -> Tuple[str, str]:
    """How much the action's object and the rivalry's object share.

    Conservative on purpose. Fuzzy semantic similarity alone never produces
    STRONG: the two must agree on the WORKFLOW or the BUYER as written, or
    the pair is at most ADJACENT, and ADJACENT never builds an interaction.
    """
    theirs = " ".join((relationship_object or "").lower().split())
    if not theirs or not action_object:
        return NONE, "the relationship states no object to compare against"
    mine_parts = [p for p in (action_object.workflow, action_object.buyer,
                              action_object.use_case) if p]
    for part in mine_parts:
        low = part.lower()
        if low in theirs or theirs in low:
            return STRONG, (f"the action's {part!r} and the rivalry's "
                            f"{relationship_object!r} name the same thing")
    shared = (set(theirs.split()) & {w for p in mine_parts
                                     for w in p.lower().split()}) - _VACUOUS
    if shared:
        return ADJACENT, (
            f"they share {sorted(shared)} and nothing more; an adjacent "
            f"workflow is not the same buying decision, and ADJACENT never "
            f"builds an interaction")
    return NONE, (f"the action is about {mine_parts or ['nothing stated']} "
                  f"and the rivalry about {relationship_object!r}")


def summarise(objects: Sequence[CompetitiveObject],
              evidence: Sequence[ActionObjectEvidence] = ()) -> dict:
    counts = collections.Counter(o.standing for o in objects)
    return {
        "contract": CONTRACT,
        "objects": len(objects),
        "by_standing": {s: counts.get(s, 0) for s in STANDINGS},
        "usable": sum(1 for o in objects if o.is_usable),
        "by_category": dict(collections.Counter(o.category for o in objects)),
        "buyers": sorted({o.buyer for o in objects if o.buyer}),
        "workflows": sorted({o.workflow for o in objects if o.workflow}),
        "evidence": [e.as_dict() for e in evidence[:10]],
        "note": ("an object is read off the action's own sentence. There is "
                 "no parameter through which a caller can supply one, "
                 "because an object that arrives from outside the document "
                 "cannot be evidence of what the document's action contests"),
    }

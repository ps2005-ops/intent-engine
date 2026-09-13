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

#: The head noun of a buyer phrase must denote an ECONOMIC AGENT — somebody
#: who can hold a budget and make a choice. This is the discriminating test,
#: and it is why a closed list of QUALIFIERS was the wrong shape: the live
#: pricing pages say "for solo entrepreneurs" and "for small teams", whose
#: qualifiers are not on any list, while "for global reach" and "for the
#: future" carry perfectly good qualifiers and name nobody at all.
_AGENT_NOUN = (r"merchants?|retailers?|customers?|buyers?|businesses|"
               r"business|companies|brands?|sellers?|firms?|institutions?|"
               r"agencies|teams?|developers?|entrepreneurs?|founders?|"
               r"stores?|shops?|organi[sz]ations?|enterprises|"
               r"manufacturers?|wholesalers?|operators?|marketers?|owners?")

#: A named buyer or segment. "for enterprise retailers", "for SMB merchants",
#: "for solo entrepreneurs", "for complex businesses".
#:
#: Second person is refused: "for your business" addresses whoever is reading
#: the page. It names no segment, and every vendor page on the internet says
#: it. So is a bare agent noun with no qualifier — "helping businesses grow"
#: locates nothing.
_BUYER = re.compile(
    r"\bfor\s+((?!your\b|our\b|their\b|his\b|her\b|its\b|my\b|the\s+future\b)"
    r"(?:[a-z][\w-]*\s+){1,3}?"
    r"(?:" + _AGENT_NOUN + r"))\b", re.I)

#: The same buyer, stated WITHOUT "for". Live pricing tables carry a
#: "Who It's For" column whose cells are bare noun phrases: "High-volume,
#: actively growing businesses", "New businesses with up to $30K in annual
#: sales". A scale or stage marker is required, because it is what separates
#: a segment from the generic plural.
_SEGMENT_MARKER = (r"new|small|solo|independent|growing|fast[-\s]growing|"
                   r"high[-\s]volume|established|scaling|large|global|"
                   r"mid[-\s]?market|midmarket|enterprise|enterprise[-\s]grade|"
                   r"emerging|complex|lean|high[-\s]growth|multi[-\s]brand|"
                   r"omnichannel|b2b|b2c|smb")
#: The intervening words may not contain "for", "your" or "our": without
#: that, "New pricing for your business" reads as the segment "New ...
#: business" and every second-person sentence on a vendor page establishes a
#: buyer.
_SEGMENT = re.compile(
    r"\b((?:" + _SEGMENT_MARKER + r")"
    r"(?:[,\s]+(?!for\b|your\b|our\b|their\b)[a-z][\w-]*){0,3}?\s+"
    r"(?:" + _AGENT_NOUN + r"))\b", re.I)

#: A buyer named by the CONSEQUENCE clause instead of by "for". Live release
#: notes carry it constantly: "Introducing 10 new granular permissions ... so
#: store owners have better control over staff access" names its buyer every
#: bit as plainly as "for store owners" would. The verb is required — "so
#: store owners" alone is a subordinate clause that may be going anywhere.
_BENEFICIARY = re.compile(
    r"\bso\s+((?!your\b|our\b|their\b)(?:[a-z][\w-]*\s+){0,3}?"
    r"(?:" + _AGENT_NOUN + r"))\s+"
    r"(?:have|has|get|gets|can|gain|gains|receive|see)\b", re.I)

#: A named edition or plan carrying no price in the same sentence. "Bundled
#: with Unlimited Edition" names a priced tier; the price lives in the
#: pricing table two screens away. The noun is what makes it safe — Edition,
#: Plan, Tier and Package are what a vendor calls a thing you buy, and a
#: capitalised word alone is not.
_NAMED_TIER = re.compile(
    r"\b([A-Z][A-Za-z0-9+]*\s+(?:Edition|Plan|Tier|Package))\b")

#: A tier name sitting immediately on top of its price. This is the shape of
#: every pricing table on the internet — "Basic. CA$37/mo.", "Scale. $299." —
#: and the adjacency is what makes it tight: a capitalised token next to a
#: currency amount is a priced plan, not prose.
_PRICED_TIER = re.compile(
    r"\b([A-Z][A-Za-z0-9+]*)\d?\.?\s+(?:from\s+)?"
    r"(?:CA\$|US\$|A\$|\$|£|€)\s?[\d,]+")

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

#: The named product as the SUBJECT of the sentence rather than its object:
#: "Shopify Shipping expands to Italy", "Commerce Cloud is now available in
#: Japan". Market-entry and availability sentences put the product first, and
#: reading only the post-verb position missed every one of them.
_PRODUCT_SUBJECT = re.compile(
    r"\b([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,3})\s+"
    r"(?:expand(?:ed|s|ing)|arriv(?:ed|es|ing)|is\s+now\s+available|"
    r"are\s+now\s+available|com(?:es|ing)\s+to|now\s+supports?)\b")

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

#: What the action DISPLACES — the named incumbent a buyer would be leaving.
#: This is the one dimension a company-published page reliably supplies about
#: somebody else, because a migration page cannot do its job without naming
#: what you are migrating from.
#: Only CONSECUTIVE capitalised tokens are one name. Letting the pattern run
#: across "and"/"or" turned "migrate from Shopify, WooCommerce and Adobe
#: Commerce" into the single incumbent "Shopify and Adobe Commerce", which is
#: nobody. The list is recovered separately, into `substitutes`.
_SUBSTITUTE_LEAD = (r"\b(?:migrat(?:e|ing|ion)\s+from|switch(?:ing)?\s+from|"
                    r"mov(?:e|ing)\s+(?:off|from)|replatform(?:ing)?\s+from|"
                    r"replac(?:e|ing)|alternative\s+to|coming\s+from)\s+")
_SUBSTITUTE = re.compile(
    _SUBSTITUTE_LEAD + r"([A-Z][A-Za-z0-9.]*(?:\s+[A-Z][A-Za-z0-9.]*){0,2})")

#: The whole enumeration after the lead-in, so a migration page that names
#: three incumbents is recorded as naming three.
_SUBSTITUTE_LIST = re.compile(
    _SUBSTITUTE_LEAD +
    r"((?:[A-Z][A-Za-z0-9.]*(?:\s+[A-Z][A-Za-z0-9.]*){0,2})"
    r"(?:\s*,\s*|\s+and\s+|\s+or\s+)?)+")

#: Where the action lands. Only a NAMED place counts: "expanded into
#: Germany", "now available in Canada". "Global" and "international" are
#: adjectives on an ambition, not a market anybody can be contested in.
_GEOGRAPHY = re.compile(
    r"\b(?:expand(?:ed|s|ing)\s+(?:into|to)|enter(?:ed|s|ing)\s+"
    r"(?:the\s+)?|(?:now\s+)?available\s+in|launch(?:ed|es|ing)\s+in)\s+"
    r"((?!the\b|new\b|a\b)[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})")

#: When the change takes effect. A price change with no date is a price.
_EFFECTIVE = re.compile(
    r"\b(?:starting|effective|beginning|as\s+of|from)\s+"
    r"((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})",
    re.I)

#: The document names an object that puts the action OUTSIDE the rivalry.
_ELSEWHERE = re.compile(
    r"\bnot\s+(?:a\s+)?(?:commerce|retail|storefront)\b|"
    r"\bunrelated\s+to\s+(?:commerce|retail)\b", re.I)

# --- dimensions -------------------------------------------------------------
#
# A schema is not a bar. Requiring every dimension of every action would
# refuse real signal to satisfy a shape; requiring none would let "Salesforce
# launches something" through. Each action type names the combination that
# actually locates IT, and nothing more.
WHAT = "WHAT"
WHO = "WHO"
WHERE = "WHERE"
BUDGET_DIM = "BUDGET"
SUBSTITUTE = "SUBSTITUTE"
DIMENSIONS = (WHAT, WHO, WHERE, BUDGET_DIM, SUBSTITUTE)

#: What each action type must establish before it counts as ESTABLISHED.
#: The default — a what and a who — is what wave 7 required of everything.
#: EVERY action type requires a WHAT. This is not a schema preference: an
#: action with no "what" cannot be located economically no matter how much
#: else it names. The first live run established "Shopify Shipping expands
#: to Italy and Spain" on its geography ALONE, because MARKET_ENTRY had been
#: allowed to pass on WHERE — and "somebody entered Italy" contests nothing
#: until you know what they brought.
_REQUIRED: Dict[str, Tuple[str, ...]] = {
    "PRICE_CHANGE": (WHAT, WHO),
    "PRODUCT_LAUNCH": (WHAT, WHO),
    "MIGRATION_PROGRAMME": (WHAT, WHO, SUBSTITUTE),
    "BUNDLE_CHANGE": (WHAT, WHO),
    "SEGMENT_EXPANSION": (WHAT, WHO),
    "MARKET_ENTRY": (WHAT, WHERE),
    # A partnership between two companies says nothing about who either of
    # them is competing with. It needs the use case or it establishes
    # nothing — the announcement alone is not rivalry.
    "PARTNERSHIP": (WHAT, WHO),
}
DEFAULT_REQUIRED: Tuple[str, ...] = (WHAT, WHO)


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
    #: The named incumbent this action displaces, when the document says so.
    substitute: str = ""
    #: Every incumbent the document named, when it named several.
    substitutes: Tuple[str, ...] = ()
    #: When the change takes effect, when the document says so.
    effective_date: str = ""
    #: Which dimensions the DOCUMENT supplied, and which the action's type
    #: required. Reported so a PARTIAL names the gap a later document fills.
    dimensions_present: Tuple[str, ...] = ()
    dimensions_required: Tuple[str, ...] = ()
    action_type: str = ""

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
            "missing": list(self.missing), "substitute": self.substitute,
            "substitutes": list(self.substitutes),
            "effective_date": self.effective_date,
            "dimensions_present": list(self.dimensions_present),
            "dimensions_required": list(self.dimensions_required),
            "action_type": self.action_type,
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


#: One name in an enumeration: consecutive capitalised tokens, nothing else.
_NAME_RUN = re.compile(r"[A-Z][A-Za-z0-9.]*(?:\s+[A-Z][A-Za-z0-9.]*){0,2}")


def _enumerate_substitutes(tail: str, actor: str) -> Tuple[str, ...]:
    """Every incumbent named in the run following a migration lead-in.

    A migration page routinely names three or four platforms in one breath.
    Recording only the first understates what the document says about who
    this vendor believes it is taking business from. The walk stops at the
    first token that is not a name or a joiner, because past that point the
    sentence has moved on to something else.
    """
    names: List[str] = []
    cursor = 0
    while cursor < len(tail):
        match = _NAME_RUN.match(tail, cursor)
        if not match:
            break
        candidate = match.group(0).strip(" .,;:")
        if candidate and not _vacuous(candidate) \
                and candidate.lower() != (actor or "").lower():
            names.append(candidate)
        cursor = match.end()
        joiner = re.match(r"(?:\s*,\s*|\s+and\s+|\s+or\s+)", tail[cursor:])
        if not joiner:
            break
        cursor += joiner.end()
    return tuple(dict.fromkeys(names))


def extract(span: str, *, action_id: str, actor: str, source: str,
            created_at: str, evidence_ids: Sequence[str] = (),
            action_type: str = ""
            ) -> Tuple[Optional[CompetitiveObject],
                       Optional[ActionObjectEvidence]]:
    """Read the object off the ACTION'S OWN SENTENCE, or return UNKNOWN.

    There is no parameter through which a caller can supply an object. That
    is deliberate and it is the whole point of the module: a competitive
    object that arrives from outside the document cannot be evidence of what
    the document's action contests.

    `action_type` is NOT such a parameter. It selects which dimensions this
    KIND of action must establish; it contributes no text, and every value
    the object carries is still a span cut out of `span`. Passing
    MIGRATION_PROGRAMME cannot invent a substitute — it can only require one
    that the document did not supply, which makes the result stricter.
    """
    text = " ".join((span or "").split())
    spans: List[str] = []

    buyer_hit = _BUYER.search(text)
    buyer = buyer_hit.group(1).strip() if buyer_hit else ""
    if buyer and _vacuous(buyer):
        buyer = ""
    if buyer:
        spans.append(buyer_hit.group(0))
    else:
        # Same buyer, other constructions: a bare qualified segment, and the
        # consequence clause a release note uses instead of "for".
        for pattern in (_SEGMENT, _BENEFICIARY):
            hit = pattern.search(text)
            if hit and not _vacuous(hit.group(1)):
                buyer = hit.group(1).strip()
                spans.append(hit.group(0))
                break

    workflow_hit = _WORKFLOW.search(text)
    workflow = workflow_hit.group(1).strip() if workflow_hit else ""
    if workflow:
        spans.append(workflow_hit.group(0))

    product_hit = _PRODUCT_NAME.search(text) or _PRODUCT_SUBJECT.search(text)
    product = product_hit.group(1).strip() if product_hit else ""
    if product and (_vacuous(product)
                    or product.lower() == (actor or "").lower()):
        product = ""
    if product:
        spans.append(product_hit.group(0))

    tier_hit = (_TIER.search(text) or _PRICED_TIER.search(text)
                or _NAMED_TIER.search(text))
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

    substitute_hit = _SUBSTITUTE.search(text)
    substitute = (substitute_hit.group(1).strip(" .,;:")
                  if substitute_hit else "")
    if substitute and (_vacuous(substitute)
                       or substitute.lower() == (actor or "").lower()):
        substitute = ""
    substitutes: Tuple[str, ...] = ()
    if substitute:
        spans.append(substitute_hit.group(0))
        substitutes = _enumerate_substitutes(
            text[substitute_hit.start(1):], actor)

    effective_hit = _EFFECTIVE.search(text)
    effective = effective_hit.group(1).strip() if effective_hit else ""

    geography_hit = _GEOGRAPHY.search(text)
    geography = geography_hit.group(1).strip() if geography_hit else ""
    if geography:
        spans.append(geography_hit.group(0))

    if _ELSEWHERE.search(text):
        standing, category = CONTRADICTED, WORKFLOW
        present: Tuple[str, ...] = ()
        required: Tuple[str, ...] = ()
    else:
        # Which dimensions the document actually supplied. A "what" is any of
        # a workflow, a named product, a priced tier or a budget: all four
        # name something a buyer chooses between.
        present = tuple(dim for dim, value in (
            (WHAT, workflow or product or budget),
            (WHO, buyer),
            (WHERE, geography),
            (BUDGET_DIM, budget),
            (SUBSTITUTE, substitute),
        ) if value)
        required = _REQUIRED.get(action_type or "", DEFAULT_REQUIRED)
        if all(dim in present for dim in required):
            standing = ESTABLISHED
        elif present:
            standing = PARTIAL
        else:
            standing = UNKNOWN
        category = (WORKFLOW if workflow else
                    BUDGET if budget else
                    PRODUCT if product else
                    CUSTOMER_SEGMENT if buyer else
                    GEOGRAPHIC_MARKET if geography else PLATFORM_LAYER)

    missing = tuple(dim.lower() for dim in required if dim not in present)
    if standing == UNKNOWN:
        return None, None

    raw = f"{category}|{workflow or product}|{buyer}|{budget}".lower()
    obj = CompetitiveObject(
        object_id="obj_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        category=category, workflow=workflow, buyer=buyer, budget=budget,
        use_case=workflow or product, market_scope="", geography=geography,
        evidence_ids=tuple(evidence_ids) or (f"doc:{source}",),
        source_spans=tuple(spans), standing=standing,
        created_at=created_at[:10], missing=missing, substitute=substitute,
        substitutes=substitutes,
        effective_date=effective, dimensions_present=present,
        dimensions_required=required, action_type=action_type)
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

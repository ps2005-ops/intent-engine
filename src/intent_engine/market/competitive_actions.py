"""What a rival actually DID — and whether it touches the thing being contested.

THE GAP THIS SITS IN
--------------------
Wave 5 established three real rivalries and produced zero strategic
interactions, for a reason that was precise and new: the named rivals —
Magento, Salesforce — are observed ZERO times as a subject. The engine
tracks 25 companies and none of them is a rival it discovered.

An interaction needs an action from one side and a response from the other.
Knowing who competes with whom buys nothing until both sides are watched.

A HOMEPAGE IS A LOOKUP; RIVALRY IS A CLAIM
------------------------------------------
The registry below maps a rival's name to its own site. That is the same
kind of fact as the universe's `website` field — an address, checkable, and
carrying no assertion about anybody's competitive position. It is
deliberately NOT the curated `competitors` list, which asserts rivalry and
is refused everywhere in this codebase.

The distinction is load-bearing: without it, "we look at Magento's site
because Shopify's case study named it" quietly becomes "we know Magento is a
competitor", and the engine is back to model knowledge with extra steps.

AN ACTION IS NOT AN INTERACTION
-------------------------------
`CompetitiveAction` records what happened. `ActionRelevance` asks the
separate question of whether it touches the competitive object of a
particular relationship. Shopify shipping a checkout feature is relevant to
a commerce-platform rivalry and may be irrelevant to a CRM one, and merging
those two steps is how "these two companies both did something this quarter"
becomes a strategic interaction.

Relevance defaults to UNKNOWN. No interaction is built on UNKNOWN.
"""
from __future__ import annotations

import collections
import hashlib
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

CONTRACT = "competitive_action.v1"

# --- action types -----------------------------------------------------------
PRICE_CHANGE = "PRICE_CHANGE"
PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
BUNDLE_CHANGE = "BUNDLE_CHANGE"
DISTRIBUTION_CHANGE = "DISTRIBUTION_CHANGE"
CUSTOMER_WIN = "CUSTOMER_WIN"
PARTNERSHIP = "PARTNERSHIP"
ACQUISITION = "ACQUISITION"
MARKET_ENTRY = "MARKET_ENTRY"
SEGMENT_EXPANSION = "SEGMENT_EXPANSION"
MIGRATION_PROGRAMME = "MIGRATION_PROGRAMME"

ACTION_TYPES = (PRICE_CHANGE, PRODUCT_LAUNCH, BUNDLE_CHANGE,
                DISTRIBUTION_CHANGE, CUSTOMER_WIN, PARTNERSHIP, ACQUISITION,
                MARKET_ENTRY, SEGMENT_EXPANSION, MIGRATION_PROGRAMME)

# --- relevance --------------------------------------------------------------
RELEVANT = "RELEVANT"
IRRELEVANT = "IRRELEVANT"
UNKNOWN = "UNKNOWN"
RELEVANCE = (RELEVANT, IRRELEVANT, UNKNOWN)


class ActionRejected(ValueError):
    """An action was claimed without the parts that make it one."""


# --- the rival registry -----------------------------------------------------
#
# Populated only for rivals the CORPUS has already named in an admissible
# competitive claim. Adding an entry does not create a relationship and
# cannot: `competitive_relationships` is the only thing that admits one.
@dataclass(frozen=True)
class RivalSite:
    rival: str
    home_url: str
    #: Why this address is here, in the record, so nobody later reads the
    #: registry as a list of competitors.
    basis: str = ("an address for a rival the corpus already named; it "
                  "asserts nothing about competitive position")


REGISTRY: Tuple[RivalSite, ...] = (
    RivalSite("Magento", "https://business.adobe.com"),
    RivalSite("Salesforce", "https://www.salesforce.com"),
    RivalSite("Salesforce Commerce Cloud", "https://www.salesforce.com"),
    RivalSite("BigCommerce", "https://www.bigcommerce.com"),
)


def site_for(rival: str) -> str:
    want = " ".join((rival or "").lower().split())
    for entry in REGISTRY:
        if entry.rival.lower() == want:
            return entry.home_url
    # Longest prefix, so "Magento Commerce" finds "Magento".
    for entry in sorted(REGISTRY, key=lambda e: -len(e.rival)):
        if want.startswith(entry.rival.lower()):
            return entry.home_url
    return ""


# --- what an action looks like in prose -------------------------------------
#
# Each pattern must state a DOING, in the past or the present. A page that
# describes a product is not a page announcing a change to it, and the
# difference is the whole value of an action record.
_PATTERNS: Tuple[Tuple[str, str], ...] = (
    # An ANNOUNCEMENT frame, not a verb. A bare "ships" matched "the other
    # ships the agent and moves on" and "one agent is a bit better than the
    # day it shipped" — narrative prose, measured live at ~4/16 precision.
    # The frame requires the actor, or a today/date marker, near the verb.
    (r"\b(?:today\s+)?(?:announc(?:ed|es|ing)|launch(?:ed|es|ing)|"
     r"introduc(?:ed|es|ing)|unveil(?:ed|s|ing)|releas(?:ed|es|ing))\s+"
     r"(?:the\s+|a\s+|its\s+|new\s+)?[A-Z0-9]"
     r"|\bis\s+now\s+(?:generally\s+)?available\b"
     r"|\bgeneral\s+availability\s+of\b",
     PRODUCT_LAUNCH),
    # A tier name sits between the verb and the noun more often than not:
    # "cut its Plus pricing", "raised Enterprise rates".
    (r"\b(?:cut|cuts|lowered?|lowers|reduc(?:ed|es)|rais(?:ed|es)|"
     r"increas(?:ed|es))\s+(?:its\s+)?(?:\w+\s+){0,2}"
     r"(?:price|prices|pricing|fees?|rates?)"
     r"\b|\bnew\s+pricing\b|\bprice\s+(?:cut|reduction|increase)\b"
     # A restructuring is a price change and says none of those verbs.
     # BigCommerce's real announcement reads "Starting June 1, 2026,
     # BigCommerce is updating its plan structure and pricing" — no cut, no
     # raise, no "new pricing". The DATED frame is what keeps this from
     # matching every footer that mentions updated pricing: a change nobody
     # dated is a description of the current price.
     r"|\b(?:starting|effective|beginning)\s+"
     r"(?:January|February|March|April|May|June|July|August|September|"
     r"October|November|December)\s+\d{1,2},?\s+\d{4}[^.]{0,120}?"
     r"\b(?:updat(?:ed|es|ing)|chang(?:ed|es|ing)|introduc(?:ed|es|ing))"
     r"[^.]{0,80}?\b(?:pricing|prices|plan\s+structure|fees?|rates?)\b",
     PRICE_CHANGE),
    (r"\b(?:bundl(?:ed|es|ing)|packag(?:ed|es|ing)\s+together|"
     r"included\s+at\s+no\s+(?:extra\s+)?(?:cost|charge))\b", BUNDLE_CHANGE),
    # "acquired in 2025 by Salesforce, where his portfolio…" is a BIO. The
    # acquisition frame needs a present-tense corporate announcement.
    (r"\b(?:has\s+)?(?:agreed\s+to\s+acquire|to\s+acquire|"
     r"completed\s+the\s+acquisition\s+of|announc\w+\s+the\s+"
     r"acquisition\s+of)\b", ACQUISITION),
    (r"\b(?:partner(?:ed|ship|s)?\s+with|alliance\s+with)\b", PARTNERSHIP),
    (r"\b(?:migration\s+(?:programme|program|offer|incentive)|"
     r"switch(?:ing)?\s+(?:programme|program|offer)|"
     r"replatform(?:ing)?\s+(?:programme|program|offer))\b",
     MIGRATION_PROGRAMME),
    (r"\b(?:expand(?:ed|s|ing)\s+(?:into|to)|enter(?:ed|s|ing)\s+the\s+"
     r"\w+\s+market|now\s+available\s+in)\b", MARKET_ENTRY),
    (r"\b(?:selected\s+by|chosen\s+by|wins?\s+(?:the\s+)?(?:contract|deal)|"
     r"won\s+(?:the\s+)?(?:contract|deal))\b", CUSTOMER_WIN),
)
_COMPILED = tuple((re.compile(p, re.I), kind) for p, kind in _PATTERNS)

#: A sentence about what a product IS rather than what somebody DID.
_NOT_AN_ACTION = re.compile(
    r"\b(?:helps?\s+you|allows?\s+you|lets?\s+you|designed\s+to|built\s+to|"
    r"can\s+be\s+used|learn\s+more|contact\s+(?:us|sales)|sign\s+up|"
    r"read\s+the\s+(?:docs|guide)|our\s+mission|"
    # Biography and narrative, both of which carry action verbs about
    # things that are not this company doing something now.
    r"was\s+formerly|co-?founder\s+of|previously\s+(?:served|led|was)|"
    r"served\s+as|joined\s+(?:us|the\s+company)|"
    r"^(?:one|the\s+other|another)\b|\bmoves?\s+on\b)", re.I)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class CompetitiveAction:
    action_id: str
    actor: str
    counterparties: Tuple[str, ...]
    relationship_ids: Tuple[str, ...]
    action_type: str
    competitive_object: str
    #: Whether the DOCUMENT established that object, or a caller asserted it.
    #: Asserted objects make relevance circular — every action "contests"
    #: whatever the caller said it was about — and the first live run scored
    #: 18 RELEVANT pairs that way, all of them Salesforce AI-agent posts
    #: labelled "E-commerce platform" by the harness that fetched them.
    object_established: bool
    buyer_or_market: str
    event_time: str
    evidence_ids: Tuple[str, ...]
    source_family: str
    standing: str
    materiality: str
    possible_effects: Tuple[str, ...]
    span: str
    created_at: str = ""

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "action_id": self.action_id,
            "actor": self.actor, "counterparties": list(self.counterparties),
            "relationship_ids": list(self.relationship_ids),
            "action_type": self.action_type,
            "competitive_object": self.competitive_object,
            "object_established": self.object_established,
            "buyer_or_market": self.buyer_or_market,
            "event_time": self.event_time,
            "evidence_ids": list(self.evidence_ids),
            "source_family": self.source_family, "standing": self.standing,
            "materiality": self.materiality,
            "possible_effects": list(self.possible_effects),
            "span": self.span, "created_at": self.created_at,
            "caution": ("an action is what was done; it carries no motive "
                        "and no claim that anybody responded"),
        }


def action(*, actor: str, action_type: str, competitive_object: str,
           event_time: str, evidence_ids: Sequence[str], span: str,
           source_family: str, counterparties: Sequence[str] = (),
           relationship_ids: Sequence[str] = (), buyer_or_market: str = "",
           materiality: str = "UNMEASURED",
           object_established: bool = False) -> CompetitiveAction:
    """Admit one action, or refuse it for not being one."""
    if action_type not in ACTION_TYPES:
        raise ActionRejected(f"unknown action type {action_type!r}")
    if not actor.strip():
        raise ActionRejected("an action with no actor is a rumour")
    if not evidence_ids:
        raise ActionRejected(
            "an action with no evidence is model knowledge wearing a schema")
    if not event_time.strip():
        raise ActionRejected(
            "an action with no time cannot precede or follow anything, and "
            "an interaction is an ordering before it is anything else")
    if not span.strip():
        raise ActionRejected("the span that states the action is required")
    raw = f"{actor}|{action_type}|{span[:80]}".lower()
    return CompetitiveAction(
        action_id="act_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        actor=actor.strip(), counterparties=tuple(counterparties),
        relationship_ids=tuple(relationship_ids), action_type=action_type,
        competitive_object=competitive_object,
        object_established=object_established,
        buyer_or_market=buyer_or_market, event_time=event_time[:10],
        evidence_ids=tuple(evidence_ids), source_family=source_family,
        # Observed: a document stated it. Never "strategic", which would be
        # a claim about why.
        standing="OBSERVED", materiality=materiality,
        possible_effects=(), span=span.strip()[:300], created_at=event_time[:10])


def extract(text: str, *, actor: str, competitive_object: str,
            event_time: str, source: str, source_family: str
            ) -> Tuple[Tuple[CompetitiveAction, ...], Dict[str, int]]:
    """Pull stated actions out of one document."""
    refused: Dict[str, int] = collections.Counter()
    found: List[CompetitiveAction] = []
    seen: set = set()
    for raw in _SENTENCE.split(" ".join((text or "").split())):
        sentence = raw.strip()
        if len(sentence) < 30 or len(sentence) > 400:
            continue
        if _NOT_AN_ACTION.search(sentence):
            refused["describes_the_product_rather_than_a_change"] += 1
            continue
        for pattern, kind in _COMPILED:
            if not pattern.search(sentence):
                continue
            try:
                made = action(
                    actor=actor, action_type=kind,
                    competitive_object=competitive_object,
                    event_time=event_time, evidence_ids=(f"doc:{source}",),
                    span=sentence, source_family=source_family)
            except ActionRejected:
                refused["rejected_by_contract"] += 1
                break
            if made.action_id in seen:
                refused["duplicate_in_document"] += 1
                break
            seen.add(made.action_id)
            found.append(made)
            break
    return tuple(found), dict(refused)


# --- relevance --------------------------------------------------------------
@dataclass(frozen=True)
class ActionRelevance:
    action_id: str
    relationship_id: str
    relevant: str
    reason: str
    evidence: str
    standing: str = "ASSESSED"

    def as_dict(self) -> dict:
        return {"action_id": self.action_id,
                "relationship_id": self.relationship_id,
                "relevant": self.relevant, "reason": self.reason,
                "evidence": self.evidence, "standing": self.standing}


#: Which action types can contest which kind of competitive object. An
#: acquisition contests a market; a price cut contests a buyer's budget for a
#: specific product. Wrong pairings are the ones that make "both companies
#: did something" look like a strategic exchange.
_CONTESTS = {
    PRICE_CHANGE: "the buyer's budget for the contested product",
    PRODUCT_LAUNCH: "the capability the buyer is choosing between",
    BUNDLE_CHANGE: "what the buyer gets for the same money",
    MIGRATION_PROGRAMME: "the switching cost between the two parties",
    DISTRIBUTION_CHANGE: "how the buyer reaches either party",
    CUSTOMER_WIN: "a specific buyer, directly",
    SEGMENT_EXPANSION: "which buyers are contested at all",
    MARKET_ENTRY: "whether the two parties contest anything yet",
}


def assess(act: CompetitiveAction, *, relationship_id: str,
           relationship_object: str,
           relationship_actors: Sequence[str],
           established_object=None) -> ActionRelevance:
    """Does this action touch what THIS relationship says is contested?

    UNKNOWN is the default and is not a soft no: an interaction may never be
    built on it, so an unassessable action stops the chain rather than
    passing through it.
    """
    if act.actor and not any(
            act.actor.lower() in a.lower() or a.lower() in act.actor.lower()
            for a in relationship_actors):
        return ActionRelevance(
            act.action_id, relationship_id, IRRELEVANT,
            f"{act.actor} is not a party to this relationship", act.span[:120])
    if not act.object_established or established_object is None:
        return ActionRelevance(
            act.action_id, relationship_id, UNKNOWN,
            f"the action's competitive object was asserted by the caller, "
            f"not established by the document. Trusting it makes relevance "
            f"circular: every action then contests whatever it was labelled "
            f"with, and an interaction is not built on UNKNOWN",
            act.span[:120])
    # The overlap is computed from the object the DOCUMENT established, not
    # from a string comparison of two labels. ADJACENT never reaches
    # RELEVANT: an adjacent workflow is not the same buying decision.
    from . import competitive_objects as CO

    kind, why = CO.overlap(established_object, relationship_object)
    if kind != CO.STRONG:
        return ActionRelevance(
            act.action_id, relationship_id,
            IRRELEVANT if kind == CO.NONE else UNKNOWN, why, act.span[:120])
    contests = _CONTESTS.get(act.action_type)
    if not contests:
        return ActionRelevance(
            act.action_id, relationship_id, UNKNOWN,
            f"{act.action_type} contests nothing this model can name; an "
            f"interaction is not built on UNKNOWN", act.span[:120])
    # The label comparison that used to live here is gone: `overlap` above
    # decides, from the object the DOCUMENT established, and a second check
    # against `act.competitive_object` would reintroduce the very label the
    # module refuses to trust.
    return ActionRelevance(
        act.action_id, relationship_id, RELEVANT,
        f"a {act.action_type} contests {contests}, which is what this "
        f"relationship says the two parties are contesting", act.span[:120])


def summarise(actions: Sequence[CompetitiveAction],
              relevance: Sequence[ActionRelevance] = (),
              refused: Optional[Dict[str, int]] = None) -> dict:
    by_relevance = collections.Counter(r.relevant for r in relevance)
    return {
        "contract": CONTRACT,
        "actions": len(actions),
        "actors": sorted({a.actor for a in actions}),
        "by_action_type": dict(collections.Counter(a.action_type
                                                   for a in actions)),
        "relevance_assessed": len(relevance),
        "by_relevance": {k: by_relevance.get(k, 0) for k in RELEVANCE},
        "eligible_for_interaction": by_relevance.get(RELEVANT, 0),
        "registry_entries": len(REGISTRY),
        "refused": dict(sorted((refused or {}).items())),
        "note": ("the registry is a list of addresses, not of competitors: "
                 "it asserts nothing about competitive position, and only "
                 "`competitive_relationships` admits a rivalry"),
    }

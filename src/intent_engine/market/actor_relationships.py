"""Who is connected to whom, and how we are entitled to know it.

WHY THIS IS THE CURRENT PREREQUISITE
------------------------------------
`interaction_binding` is built and correctly returns zero: a strategic
interaction needs a counterparty that had a reason to respond, and nothing in
the system records that two companies are rivals, or that one buys from the
other. Sector adjacency was tried and produced fiction — ASML "responding to"
Infosys because both are Technology.

So the chain the engine is trying to learn

    evidence -> entity -> RELATIONSHIP -> action -> response -> reconciliation

is broken at the third link, and everything after it is starved.

WHAT THE HEADLINE CORPUS CANNOT DO
----------------------------------
Measured before building: across 219 real evidence items, relationship-bearing
language with two NAMED actors appears essentially once. The corpus is Google
News headlines about a single subject company, and a headline about one
company by construction rarely names its counterparty. Three "SELLS_TO" hits
were all the same JPMorgan scale statement — 86.6M consumers, no counterparty
named — and the two "acquisition" hits were one Shopify fact duplicated.

That is a retrieval finding, not an extraction one, and it decides the design:
relationships are extracted from FILINGS, where a company is obliged to name
its material customers, its supplier concentrations and its competitors.

ADMISSION IS DELIBERATELY HARSH
-------------------------------
Both ends must be named in the same sentence, the predicate must be stated
rather than inferred from adjacency, and the spans that justify each end are
stored so a disputed edge can be argued about in terms of the text rather than
the extractor. Everything else is refused, with a reason.

Nothing here may come from model world knowledge. "Microsoft competes with
AWS" is common knowledge and is still refused unless a document says it,
because a graph that mixes what was read with what was already believed cannot
be audited later.
"""
from __future__ import annotations

import collections
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "actor_relationship.v1"

# --- predicates -------------------------------------------------------------
SELLS_TO = "SELLS_TO"
BUYS_FROM = "BUYS_FROM"
SUPPLIES = "SUPPLIES"
COMPETES_WITH = "COMPETES_WITH"
PARTNERS_WITH = "PARTNERS_WITH"
DEPENDS_ON = "DEPENDS_ON"
DISTRIBUTES = "DISTRIBUTES"
FINANCES = "FINANCES"
REGULATES = "REGULATES"
SUBSTITUTES_FOR = "SUBSTITUTES_FOR"
COMPLEMENTS = "COMPLEMENTS"

PREDICATES = frozenset({
    SELLS_TO, BUYS_FROM, SUPPLIES, COMPETES_WITH, PARTNERS_WITH, DEPENDS_ON,
    DISTRIBUTES, FINANCES, REGULATES, SUBSTITUTES_FOR, COMPLEMENTS})

# --- epistemic status -------------------------------------------------------
OBSERVED = "OBSERVED"
INFERRED = "INFERRED"
HYPOTHESIZED = "HYPOTHESIZED"
STATUSES = frozenset({OBSERVED, INFERRED, HYPOTHESIZED})

# --- actor kinds ------------------------------------------------------------
LEGAL_ENTITY = "LEGAL_ENTITY"
OPERATING_BRAND = "OPERATING_BRAND"
PRODUCT = "PRODUCT"
BUSINESS_UNIT = "BUSINESS_UNIT"
PERSON = "PERSON"
GOVERNMENT = "GOVERNMENT"
REGULATOR = "REGULATOR"
UNKNOWN_ACTOR = "UNKNOWN_ACTOR"

ACTOR_KINDS = frozenset({
    LEGAL_ENTITY, OPERATING_BRAND, PRODUCT, BUSINESS_UNIT, PERSON,
    GOVERNMENT, REGULATOR, UNKNOWN_ACTOR})


class RelationshipRejected(ValueError):
    """The graph was asked to hold a connection it cannot account for."""


#: The predicate must be STATED. Each pattern captures the verb phrase that
#: licenses the edge, and the direction it licenses.
_PATTERNS: Tuple[Tuple[str, str, bool], ...] = (
    # (regex, predicate, subject_is_left)
    (r"\bcompet(?:es?|ing|ition)\s+(?:directly\s+)?with\b", COMPETES_WITH, True),
    (r"\bcompetitors?\s+(?:include|are)\b", COMPETES_WITH, True),
    (r"\bour\s+(?:principal\s+)?competitors?\s+(?:include|are)\b",
     COMPETES_WITH, True),
    (r"\bpartner(?:ed|ship|s)?\s+with\b", PARTNERS_WITH, True),
    (r"\b(?:strategic\s+)?alliance\s+with\b", PARTNERS_WITH, True),
    (r"\bsupplies?\s+(?:to\s+)?\b", SUPPLIES, True),
    (r"\bsupplier\s+(?:to|of)\b", SUPPLIES, True),
    (r"\bpurchas\w+\s+from\b", BUYS_FROM, True),
    (r"\bsources?\s+from\b", BUYS_FROM, True),
    (r"\bsells?\s+to\b", SELLS_TO, True),
    (r"\bdistributes?\s+(?:through|via)\b", DISTRIBUTES, True),
    (r"\bdepend(?:s|ent|ence)\s+(?:up)?on\b", DEPENDS_ON, True),
    (r"\brel(?:ies|iance)\s+(?:up)?on\b", DEPENDS_ON, True),
    (r"\bregulated\s+by\b", REGULATES, False),
    (r"\bsubstitutes?\s+for\b", SUBSTITUTES_FOR, True),
    (r"\bcomplements?\b", COMPLEMENTS, True),
)
_COMPILED = tuple((re.compile(p, re.I), pred, left)
                  for p, pred, left in _PATTERNS)

#: Category nouns that look like actors and are not. An edge whose object is
#: one of these names no counterparty at all, which is the failure that lets
#: "competitors include other large technology companies" into a graph.
_NOT_AN_ACTOR = re.compile(
    r"^(?:other|others|various|certain|numerous|many|several|some|"
    r"large|small|major|leading|global|regional|local|new|existing|"
    r"compan(?:y|ies)|competitors?|customers?|suppliers?|vendors?|"
    r"partners?|clients?|firms?|businesses|players|providers?|"
    r"organi[sz]ations?|institutions?|entities|parties|markets?|"
    r"industry|industries|sector|sectors|technolog(?:y|ies)|"
    r"products?|services?|solutions?|platforms?|others in|"
    r"third[- ]part(?:y|ies))\b", re.I)

#: A named actor: capitalised tokens, optionally with a corporate suffix.
_ACTOR = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,3}"
    r"(?:\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|LLC|PLC|plc|"
    r"N\.V\.|S\.A\.|AG|SE|Group|Holdings|Technologies|Systems)\.?)?)")


@dataclass(frozen=True)
class ActorRelationship:
    """One connection, and the text that licenses it."""
    relationship_id: str
    subject_actor: str
    predicate: str
    object_actor: str
    subject_kind: str
    object_kind: str
    epistemic_status: str
    evidence_ids: Tuple[str, ...]
    source_document: str
    subject_span: str
    object_span: str
    relationship_span: str
    valid_from: str = ""
    valid_to: str = ""
    created_at: str = ""
    last_confirmed_at: str = ""

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT,
            "relationship_id": self.relationship_id,
            "subject_actor_id": self.subject_actor,
            "predicate": self.predicate,
            "object_actor_id": self.object_actor,
            "subject_kind": self.subject_kind,
            "object_kind": self.object_kind,
            "epistemic_status": self.epistemic_status,
            "evidence_ids": list(self.evidence_ids),
            "source_document_ids": [self.source_document],
            "subject_span": self.subject_span,
            "object_span": self.object_span,
            "relationship_span": self.relationship_span,
            "valid_from": self.valid_from, "valid_to": self.valid_to,
            "created_at": self.created_at,
            "last_confirmed_at": self.last_confirmed_at,
        }


def is_named_actor(text: str) -> bool:
    """Whether this string names somebody, rather than a category of somebody.

    "Amazon Web Services" names an actor. "other large technology companies"
    names a set with no members, and an edge to it connects nothing while
    looking exactly like an edge that does.
    """
    candidate = " ".join((text or "").split()).strip(" .,;:")
    if not candidate or len(candidate) < 3:
        return False
    if _NOT_AN_ACTOR.match(candidate):
        return False
    return bool(re.match(r"^[A-Z]", candidate))


def normalise_self(name: str) -> str:
    """A comparable form, for the one check every predicate needs: that the
    two ends are not the same actor under two spellings."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split())


def relationship(*, subject_actor: str, predicate: str, object_actor: str,
                 evidence_ids: Sequence[str], source_document: str,
                 subject_span: str, object_span: str,
                 relationship_span: str,
                 subject_kind: str = LEGAL_ENTITY,
                 object_kind: str = LEGAL_ENTITY,
                 epistemic_status: str = OBSERVED,
                 valid_from: str = "", created_at: str = ""
                 ) -> ActorRelationship:
    """Admit one relationship, or refuse it with a reason.

    OBSERVED means the document STATED the connection. It does not mean the
    connection is true — a company describing its own competitors is a party
    with an interest — it means nobody inferred it. That distinction is the
    only thing separating a graph that can be audited from one that cannot.
    """
    if predicate not in PREDICATES:
        raise RelationshipRejected(f"unknown predicate {predicate!r}")
    if epistemic_status not in STATUSES:
        raise RelationshipRejected(f"unknown status {epistemic_status!r}")
    if subject_kind not in ACTOR_KINDS or object_kind not in ACTOR_KINDS:
        raise RelationshipRejected("unknown actor kind")
    if not evidence_ids:
        raise RelationshipRejected(
            "a relationship with no evidence is model knowledge wearing a "
            "schema; cite the observation that states it")
    for end, value in (("subject", subject_actor), ("object", object_actor)):
        if not is_named_actor(value):
            raise RelationshipRejected(
                f"the {end} names no actor: {value!r} is a category, not a "
                f"counterparty, and an edge to it connects nothing")
    if " ".join(subject_actor.lower().split()) == \
            " ".join(object_actor.lower().split()):
        raise RelationshipRejected("an actor cannot relate to itself")
    if not relationship_span.strip():
        raise RelationshipRejected(
            "the span that states the relationship is required; without it "
            "the edge cannot be argued about in terms of the text")

    raw = f"{subject_actor}|{predicate}|{object_actor}".lower()
    rid = "rel_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:14]
    return ActorRelationship(
        relationship_id=rid, subject_actor=subject_actor.strip(),
        predicate=predicate, object_actor=object_actor.strip(),
        subject_kind=subject_kind, object_kind=object_kind,
        epistemic_status=epistemic_status,
        evidence_ids=tuple(evidence_ids), source_document=source_document,
        subject_span=subject_span.strip(), object_span=object_span.strip(),
        relationship_span=relationship_span.strip(),
        valid_from=valid_from, created_at=created_at,
        last_confirmed_at=created_at)


def extract(sentences: Sequence[Tuple[str, str]], *, subject_actor: str,
            evidence_id_of: Optional[Dict[str, str]] = None,
            as_of: str = "") -> Tuple[Tuple[ActorRelationship, ...],
                                      Dict[str, int]]:
    """Pull stated relationships out of real document sentences.

    `sentences` is (sentence, source_document). The focal company is supplied
    rather than guessed: a filing is written by somebody, and which end of the
    sentence they are is not recoverable from the sentence alone.
    """
    refused: Dict[str, int] = collections.Counter()
    out: List[ActorRelationship] = []
    seen: set = set()

    for sentence, document in sentences:
        text = " ".join((sentence or "").split())
        if not text:
            continue
        for pattern, predicate, subject_is_left in _COMPILED:
            match = pattern.search(text)
            if not match:
                continue
            tail = text[match.end():].lstrip(" ,:")
            # A leading article is not part of the name. "regulated by
            # the Federal Reserve" is a named regulator; without this the
            # match failed on "the" and the edge was lost.
            tail = re.sub(r"^(?:the|a|an)\s+", "", tail, flags=re.I)
            other = _ACTOR.match(tail)
            if not other:
                refused["no_named_counterparty"] += 1
                continue
            counterparty = other.group(1).strip(" .,;:")
            if not is_named_actor(counterparty):
                refused["counterparty_is_a_category"] += 1
                continue
            left, right = ((subject_actor, counterparty) if subject_is_left
                           else (counterparty, subject_actor))
            key = (left.lower(), predicate, right.lower())
            if key in seen:
                refused["duplicate"] += 1
                continue
            try:
                out.append(relationship(
                    subject_actor=left, predicate=predicate,
                    object_actor=right,
                    evidence_ids=((evidence_id_of or {}).get(text)
                                  or (f"doc:{document}",)),
                    source_document=document,
                    subject_span=subject_actor, object_span=counterparty,
                    relationship_span=text[:280], valid_from=as_of,
                    created_at=as_of))
                seen.add(key)
            except RelationshipRejected:
                refused["rejected_by_contract"] += 1
            break
    return tuple(out), dict(refused)


def summarise(relationships: Sequence[ActorRelationship],
              refused: Dict[str, int]) -> dict:
    by_predicate = collections.Counter(r.predicate for r in relationships)
    return {
        "contract": CONTRACT,
        "relationships": len(relationships),
        "predicates_represented": len(by_predicate),
        "by_predicate": dict(by_predicate),
        "actors": len({r.subject_actor for r in relationships}
                      | {r.object_actor for r in relationships}),
        "by_status": dict(collections.Counter(
            r.epistemic_status for r in relationships)),
        "refused": dict(sorted(refused.items())),
    }


def competitor_map(relationships: Sequence[ActorRelationship]
                   ) -> Dict[str, frozenset]:
    """The rival index `interaction_binding` needs, keyed for its lookup.

    Symmetric on purpose: if A's filing names B as a competitor, B is a
    plausible responder to A's actions and A to B's, whichever side wrote it
    down.
    """
    pairs: Dict[str, set] = collections.defaultdict(set)
    for row in relationships:
        if row.predicate != COMPETES_WITH:
            continue
        a, b = row.subject_actor.lower(), row.object_actor.lower()
        pairs[a].add(b)
        pairs[b].add(a)
    return {k: frozenset(v) for k, v in pairs.items()}

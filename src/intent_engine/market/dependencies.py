"""Using something is not depending on it.

THE DISTINCTION THAT DOES THE WORK
----------------------------------
    USES        "our platform runs on AWS"
    BUYS_FROM   "we purchase compute from AWS"
    DEPENDS_ON  "we rely on a single supplier for X, and a disruption would
                 materially affect our ability to deliver"

Every company on earth uses cloud infrastructure. Almost none of those
sentences is a dependency in the economic sense, and a graph that records
them all as DEPENDS_ON has learned that everyone depends on everyone —
which is the same as knowing nothing while looking like a supply-chain map.

DEPENDENCY NEEDS A STATED CONSEQUENCE
-------------------------------------
This module admits DEPENDS_ON only where the document itself supplies a
materiality marker: single-source, no readily available substitute, a
material adverse effect, a critical function. Those phrases exist because
securities law makes companies write them down, which is exactly why the
filing is the right source and the marketing page is not.

NOTHING IS INFERRED FROM SECTOR KNOWLEDGE
-----------------------------------------
"Semiconductor firms depend on ASML" is true and is not evidence. If the
document does not name the party and state the reliance, there is no edge.
"""
from __future__ import annotations

import collections
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "dependency.v1"

# --- what the document actually established ---------------------------------
USES = "USES"
BUYS_FROM = "BUYS_FROM"
SUPPLIES = "SUPPLIES"
DEPENDS_ON = "DEPENDS_ON"

KINDS = (USES, BUYS_FROM, SUPPLIES, DEPENDS_ON)

#: Phrases that make a reliance MATERIAL. Drawn from the language filings
#: are obliged to use, which is why this reads like a prospectus.
_MATERIALITY = re.compile(
    r"\b(?:sole\s+source|single\s+source|single\s+supplier|only\s+supplier|"
    r"no\s+readily\s+available\s+(?:substitute|alternative)|"
    r"materially\s+adverse|material\s+adverse\s+effect|"
    r"substantially\s+all\s+of\s+our|"
    r"critical\s+(?:supplier|component|dependency|function)|"
    r"depend(?:s|ent)?\s+(?:heavily|substantially|significantly)|"
    r"a\s+significant\s+portion\s+of\s+our)\b", re.I)

#: A purchase or supply relation, stated.
_TRADE = re.compile(
    r"\b(?:purchases?|procures?|sources?|buys?)\s+(?:[\w\s-]{0,30}?)\bfrom\b"
    r"|\bsupplies?\s+(?:us|the\s+company)\b"
    r"|\bis\s+our\s+(?:supplier|vendor|provider)\b", re.I)

#: Mere usage. The commonest sentence on the internet and the weakest.
_USAGE = re.compile(
    r"\b(?:runs?\s+on|built\s+on|hosted\s+on|powered\s+by|uses?|using|"
    r"leverages?|deployed\s+on)\b", re.I)

#: A named party: capitalised, not a sentence opener, not a category.
_PARTY = re.compile(r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,3})\b")

_NOT_A_PARTY = frozenset({
    "we", "our", "the", "this", "that", "these", "those", "it", "they",
    "a", "an", "in", "on", "at", "to", "for", "and", "or", "but", "if",
    "company", "group", "business", "customers", "suppliers", "vendors",
    "third", "certain", "some", "many", "most", "all",
})


class DependencyRejected(ValueError):
    pass


@dataclass(frozen=True)
class DependencyClaim:
    claim_id: str
    subject: str
    counterparty: str
    kind: str
    evidence_span: str
    source: str
    materiality_span: str = ""
    observed_at: str = ""
    provenance: Dict[str, str] = field(default_factory=dict)

    @property
    def predicate(self) -> str:
        return self.kind

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "claim_id": self.claim_id,
            "subject_actor_id": self.subject,
            "object_actor_id": self.counterparty,
            "predicate": self.kind, "relationship_object": self.kind,
            "evidence_span": self.evidence_span, "source": self.source,
            "materiality_span": self.materiality_span,
            "observed_at": self.observed_at,
            "provenance": dict(self.provenance),
        }


def _named_parties(sentence: str, subject: str) -> List[str]:
    """Capitalised names that are plausibly companies.

    A LONE capitalised word at the start of a sentence is refused: every
    sentence begins with a capital, so "Fast-growing stir-fry concept
    leverages Olo Pay" offered "Fast-growing" as a supplier. This is the
    third module to meet that shape after "Regular releases keep your org
    secure" and "Is migrating from Shopify difficult?".
    """
    out: List[str] = []
    own = {w.lower() for w in (subject or "").split()}
    for hit in _PARTY.finditer(sentence or ""):
        if hit.start() == 0 and len(hit.group(1).split()) == 1:
            continue
        candidate = hit.group(1).strip(" .,;:")
        words = candidate.split()
        while words and words[0].lower() in _NOT_A_PARTY:
            words.pop(0)
        candidate = " ".join(words)
        if len(candidate) < 3:
            continue
        if {w.lower() for w in candidate.split()} & own:
            continue
        if candidate not in out:
            out.append(candidate)
    return out


def classify(sentence: str) -> Tuple[str, str]:
    """The STRONGEST relation this sentence actually establishes.

    Order matters: a sentence carrying both a materiality marker and the
    word "uses" is a dependency, and a sentence carrying only "uses" is not
    one however important the named party happens to be.
    """
    text = " ".join((sentence or "").split())
    material = _MATERIALITY.search(text)
    if material:
        return DEPENDS_ON, material.group(0)
    if _TRADE.search(text):
        return BUYS_FROM, ""
    if _USAGE.search(text):
        return USES, ""
    return "", ""


def extract(text: str, *, subject: str, source: str, observed_at: str = ""
            ) -> Tuple[Tuple[DependencyClaim, ...], Dict[str, int]]:
    """Pull supplier and dependency claims out of one document."""
    refused: Dict[str, int] = collections.Counter()
    found: List[DependencyClaim] = []
    seen: set = set()
    for raw in re.split(r"(?<=[.!?])\s+", " ".join((text or "").split())):
        sentence = raw.strip()
        if len(sentence) < 25 or len(sentence) > 400:
            continue
        kind, materiality = classify(sentence)
        if not kind:
            continue
        parties = _named_parties(sentence, subject)
        if not parties:
            refused["names_no_counterparty"] += 1
            continue
        counterparty = parties[0]
        key = f"{subject}|{kind}|{counterparty}".lower()
        if key in seen:
            refused["duplicate_in_document"] += 1
            continue
        seen.add(key)
        found.append(DependencyClaim(
            claim_id="dep_" + hashlib.sha256(key.encode()).hexdigest()[:12],
            subject=subject.strip(), counterparty=counterparty, kind=kind,
            evidence_span=sentence[:300], source=source,
            materiality_span=materiality, observed_at=observed_at[:10]))
    return tuple(found), dict(refused)


def summarise(claims: Sequence[DependencyClaim]) -> dict:
    by_kind = collections.Counter(c.kind for c in claims)
    return {
        "contract": CONTRACT,
        "claims": len(claims),
        "by_kind": {k: by_kind.get(k, 0) for k in KINDS if by_kind.get(k, 0)},
        "dependencies": by_kind.get(DEPENDS_ON, 0),
        "distinct_counterparties": len({c.counterparty for c in claims}),
        "note": ("DEPENDS_ON requires a materiality marker the DOCUMENT "
                 "supplies — single-source, no available substitute, "
                 "material adverse effect. Everyone uses cloud "
                 "infrastructure; a graph recording that as dependency has "
                 "learned that everyone depends on everyone."),
    }

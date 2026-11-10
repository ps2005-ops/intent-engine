"""The Economic Evidence Graph: one node type both products write into.

WHAT THIS REPLACES
------------------
Before this module the two products each had a complete, careful, and
completely separate account of "a fact about the economy".

    market side    `market.micro_evidence.MicroEvidence` — dated, sourced,
                   attributable, with an independence grade. Company facts.
    market side    `market.macro_state.MacroObservation` — a published
                   statistic with three times. Macro facts.
    founder side   `external_intel.macro_contract.MacroFactor` — a macro
                   series bound to a company exposure mechanism.
    founder side   `strategic_intelligence.observations.StrategicObservation`
                   — a retrieved document's claim about a company.

Four node types, no shared identity, so nothing either side learned could
corroborate — or contradict — anything the other side learned. This is the
substrate they translate into. It is deliberately POORER than any of them:
it carries what both sides can honestly populate and refuses the rest.

THREE TIMES, AND THE ONE THAT DECIDES
-------------------------------------
    occurred_at    when the thing being described happened
    available_at   the first moment this engine could have known it
    retrieved_at   when we actually fetched it

`available_at` is the only one a replay may read (Section 24). A 10-K
describes a year that closed in January and is filed in March; scoring a
February decision with the March filing hands the engine two months of
foresight and nothing raises. `visible_at` is the only supported way to ask
what was knowable.

VISIBILITY IS A PROPERTY OF THE FACT
------------------------------------
`visibility` travels ON the node, not on the caller. A board memo carried
into an aggregate would be a privacy breach whichever function carried it, so
the check lives where the data is — `assert_public` — and the aggregate
builder calls it on every input rather than trusting its own call site.

LINEAGE IS NOT DECORATION
-------------------------
`depends_on` is what makes Section 35 enforceable. When Cloudflare's 10-K
becomes an input to a software-demand index, the index node names the 10-K
node. Later, when the Cloudflare analysis asks "is this index independent
corroboration of my filing?", `lineage.independent` answers no — by reading
the graph, not by remembering.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import (
    ALL_KINDS, ANCHORING, CURRENT, EconError, FRESHNESS, NODE_CLASSES,
    NODE_KINDS, PUBLIC, PrivacyViolation, STANDINGS, TENANT_PRIVATE,
    VISIBILITIES, require,
)

CONTRACT = "econ_evidence.v1"


@dataclass(frozen=True)
class Provenance:
    """Where a node came from, in enough detail to go back and check.

    `publisher` is WHO SAID IT and `venue` is WHERE IT APPEARED, and they are
    two fields because collapsing them made every SEC filing one origin: the
    venue was sec.gov for all of them, so twenty companies' filings counted as
    one independent source. The author is the registrant; the venue is the
    regulator.
    """

    publisher: str
    venue: str = ""
    url: str = ""
    document_id: str = ""
    #: The subsystem that translated this into a node — "market",
    #: "founder", "macro_ingest". Not a source; an audit trail for the bridge.
    producer: str = ""

    def as_dict(self) -> dict:
        return {"publisher": self.publisher, "venue": self.venue,
                "url": self.url, "document_id": self.document_id,
                "producer": self.producer}


@dataclass(frozen=True)
class EconomicNode:
    """One dated, sourced, attributable economic fact."""

    node_id: str
    node_class: str
    kind: str
    #: What the fact is ABOUT. A company id, an area code ("US"), an
    #: instrument, a sector. Never empty: a reading with no subject is a
    #: number, and a number corroborates everything.
    subject: str
    standing: str
    occurred_at: str
    available_at: str
    provenance: Provenance
    value: Optional[float] = None
    unit: str = ""
    #: Free text, for the kinds that are linguistic rather than numeric —
    #: "management described demand as softening". A COMPANY node may be
    #: qualitative; a MACRO node whose standing is OBSERVED may not.
    statement: str = ""
    confidence: float = 0.5
    freshness: str = CURRENT
    visibility: str = PUBLIC
    #: Node ids this one is DERIVED FROM. Empty for a directly observed fact.
    depends_on: Tuple[str, ...] = ()
    retrieved_at: str = ""
    #: Prior versions of this same fact, newest last. A revision APPENDS.
    revisions: Tuple["EconomicNode", ...] = field(default=(), repr=False)

    # --- invariants ---------------------------------------------------------
    def __post_init__(self) -> None:
        require(self.node_class in NODE_CLASSES,
                f"unknown node class {self.node_class!r}")
        require(self.kind in NODE_KINDS[self.node_class],
                f"{self.kind!r} is not a kind of {self.node_class}; the "
                "vocabulary is closed so that two spellings of one quantity "
                "cannot fail to corroborate each other")
        require(bool(self.subject.strip()),
                "a node with no subject is a number, and a number "
                "corroborates everything")
        require(self.standing in STANDINGS, f"unknown standing {self.standing!r}")
        require(self.visibility in VISIBILITIES,
                f"unknown visibility {self.visibility!r}")
        require(self.freshness in FRESHNESS,
                f"unknown freshness {self.freshness!r}")
        require(0.0 <= self.confidence <= 1.0,
                "confidence is a probability")
        require(bool(self.available_at),
                "available_at is what replay reads; a node without one "
                "cannot be walled off from the future")
        require(self.available_at >= self.occurred_at,
                f"available_at {self.available_at} precedes occurrence "
                f"{self.occurred_at}: nothing is knowable before it happens")
        if self.value is None and not self.statement:
            raise EconError("a node states either a measured value or a "
                            "sentence; one with neither says nothing")

    # --- reading ------------------------------------------------------------
    @property
    def anchors(self) -> bool:
        """May a decision rest on this? OBSERVED and INFERRED only."""
        return self.standing in ANCHORING

    @property
    def derived(self) -> bool:
        return bool(self.depends_on)

    def visible_at(self, when: str) -> bool:
        """Could the engine have known this on `when`? The vintage question."""
        return bool(when) and self.available_at <= when

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "node_id": self.node_id,
            "node_class": self.node_class, "kind": self.kind,
            "subject": self.subject, "standing": self.standing,
            "occurred_at": self.occurred_at,
            "available_at": self.available_at,
            "retrieved_at": self.retrieved_at,
            "value": self.value, "unit": self.unit,
            "statement": self.statement, "confidence": self.confidence,
            "freshness": self.freshness, "visibility": self.visibility,
            "depends_on": list(self.depends_on),
            "provenance": self.provenance.as_dict(),
            "revision_count": len(self.revisions),
        }


def node_id_for(*, node_class: str, kind: str, subject: str,
                occurred_at: str, publisher: str, value: Optional[float],
                statement: str) -> str:
    """A content id — WITHOUT the retrieval date.

    THE DEFECT THIS CLOSES, twice measured in this repository: a content hash
    that included the date the document was READ made every nightly re-read a
    new fact. The self-test rate climbed because the corpus was growing, and
    the corpus was growing because the same filing arrived under a new id
    every night. What identifies a fact is what it says about what, when it
    happened, and who said it.
    """
    material = json.dumps(
        [node_class, kind, subject.strip().lower(), occurred_at,
         publisher.strip().lower(), value,
         " ".join(statement.split()).lower()[:400]],
        sort_keys=True)
    return "en-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def node(*, node_class: str, kind: str, subject: str, standing: str,
         occurred_at: str, available_at: str, publisher: str,
         value: Optional[float] = None, unit: str = "", statement: str = "",
         confidence: float = 0.5, visibility: str = PUBLIC,
         freshness: str = CURRENT, venue: str = "", url: str = "",
         document_id: str = "", producer: str = "",
         depends_on: Sequence[str] = (), retrieved_at: str = "",
         ) -> EconomicNode:
    """Build a node with a content-derived id. The only supported constructor."""
    nid = node_id_for(node_class=node_class, kind=kind, subject=subject,
                      occurred_at=occurred_at, publisher=publisher,
                      value=value, statement=statement)
    return EconomicNode(
        node_id=nid, node_class=node_class, kind=kind, subject=subject,
        standing=standing, occurred_at=occurred_at,
        available_at=available_at, value=value, unit=unit,
        statement=statement, confidence=confidence, freshness=freshness,
        visibility=visibility, depends_on=tuple(depends_on),
        retrieved_at=retrieved_at,
        provenance=Provenance(publisher=publisher, venue=venue, url=url,
                              document_id=document_id, producer=producer))


def revise(existing: EconomicNode, *, value: Optional[float] = None,
           statement: str = "", available_at: str = "",
           reason: str = "") -> EconomicNode:
    """A revision APPENDS the old reading and keeps the id.

    Statistical agencies revise, and "we now think Q2 grew 1.4%" is a
    different fact from "we thought Q2 grew 2.1%". Overwriting the first
    destroys the only record of what the engine could have known when it
    decided — which is precisely what a vintage-correct replay needs.
    """
    require(bool(available_at),
            "a revision is a new observation and needs its own availability")
    return replace(
        existing,
        value=existing.value if value is None else value,
        statement=statement or existing.statement,
        available_at=available_at,
        revisions=existing.revisions + (existing,),
        provenance=existing.provenance)


# --- the privacy boundary (Section 31) --------------------------------------
def assert_public(nodes: Iterable[EconomicNode], *, where: str) -> None:
    """Refuse if any node is tenant-private. Called by every public surface.

    Deliberately not a filter. Silently dropping private nodes would let an
    aggregate be built from three public facts and eleven private ones and
    report itself as built from three — a number that is quietly conditioned
    on material it may not use. The caller must not have offered them.
    """
    offenders = [n.node_id for n in nodes if n.visibility != PUBLIC]
    if offenders:
        raise PrivacyViolation(
            f"{where}: {len(offenders)} tenant-private node(s) reached a "
            f"public surface ({offenders[:3]}). Private evidence may inform a "
            "tenant's own CompanyEconomicState and may never reach a market "
            "aggregate, a public belief, or another tenant.")


def public_only(nodes: Iterable[EconomicNode]) -> List[EconomicNode]:
    """The public subset, for callers whose job is to SELECT rather than use."""
    return [n for n in nodes if n.visibility == PUBLIC]


# --- the graph --------------------------------------------------------------
class EvidenceGraph:
    """A set of nodes, addressable by id, with a stable dependency closure.

    Not a database. The durable form is `store.append`; this is the in-memory
    view a cycle assembles and hands to the belief engine.
    """

    def __init__(self, nodes: Sequence[EconomicNode] = ()) -> None:
        self._nodes: Dict[str, EconomicNode] = {}
        for n in nodes:
            self.add(n)

    def add(self, n: EconomicNode) -> EconomicNode:
        """Idempotent by construction: the id is the content.

        A node already present is NOT replaced. Re-reading an unchanged
        filing every night must not produce a second fact, and must not
        silently reset a revision chain.
        """
        existing = self._nodes.get(n.node_id)
        if existing is not None:
            return existing
        for parent in n.depends_on:
            require(parent in self._nodes,
                    f"node {n.node_id} depends on {parent}, which is not in "
                    "the graph; lineage that names absent parents cannot be "
                    "checked and is worse than no lineage")
        self._nodes[n.node_id] = n
        return n

    def get(self, node_id: str) -> Optional[EconomicNode]:
        return self._nodes.get(node_id)

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes

    def nodes(self, *, node_class: str = "", kind: str = "",
              subject: str = "", visible_at: str = "") -> List[EconomicNode]:
        out = list(self._nodes.values())
        if node_class:
            out = [n for n in out if n.node_class == node_class]
        if kind:
            out = [n for n in out if n.kind == kind]
        if subject:
            out = [n for n in out if n.subject == subject]
        if visible_at:
            out = [n for n in out if n.visible_at(visible_at)]
        return sorted(out, key=lambda n: (n.available_at, n.node_id))

    def ancestors(self, node_id: str) -> frozenset:
        """Every node this one is transitively derived from.

        Cycle-safe: a malformed lineage that pointed at itself would otherwise
        hang the double-counting wall, and the wall is what a founder-facing
        independence count depends on.
        """
        seen, stack = set(), [node_id]
        while stack:
            current = stack.pop()
            n = self._nodes.get(current)
            if n is None:
                continue
            for parent in n.depends_on:
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        return frozenset(seen)

    def summary(self) -> dict:
        by_class: Dict[str, int] = {}
        for n in self._nodes.values():
            by_class[n.node_class] = by_class.get(n.node_class, 0) + 1
        derived = sum(1 for n in self._nodes.values() if n.derived)
        private = sum(1 for n in self._nodes.values()
                      if n.visibility == TENANT_PRIVATE)
        return {"contract": CONTRACT, "nodes": len(self._nodes),
                "by_class": by_class, "derived": derived,
                "tenant_private": private,
                "publishers": len({n.provenance.publisher
                                   for n in self._nodes.values()})}

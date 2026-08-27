"""The double-counting wall (Section 35).

THE FAILURE, CONCRETELY
-----------------------
Cloudflare's 10-K produces a company observation: enterprise security spend
described as consolidating. That observation is one of forty inputs to a
`security_consolidation_index`. The index is published as shared economic
state. The next Cloudflare analysis reads the index, finds it agrees with
Cloudflare's own filing, and reports two independent sources.

There is one source. The agreement is arithmetic, not corroboration, and the
confidence it buys is entirely manufactured. Worse, it is SELF-REINFORCING:
the more the company says, the more the index says, the more corroborated the
company appears.

WHY A GRAPH AND NOT A FLAG
--------------------------
The obvious fix — mark derived signals and refuse to count them — is wrong in
the other direction. A hiring index built from thirty OTHER companies IS
independent evidence for Cloudflare, and refusing it would throw away the
whole point of the cross-domain flywheel. Independence is a question about
two specific things, not a property of one of them, so it has to be answered
by walking lineage.

THE RULE
--------
    A derived node is not independent evidence for any node in its own
    transitive input set, and is not independent of another derived node
    that shares an input with it.

The second clause matters as much as the first. Two indices built from
overlapping company panels are not two witnesses; they are one panel counted
twice, and this is where an "independence: 4 origins" line on a founder's
screen turns into a lie.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

from .evidence import EconomicNode, EvidenceGraph
from .vocabulary import LineageViolation

CONTRACT = "econ_lineage.v1"


@dataclass(frozen=True)
class IndependenceVerdict:
    """Why two nodes may or may not both be counted."""

    independent: bool
    reason: str
    #: The inputs they have in common, when they have any. Named rather than
    #: counted, because "shares 3 inputs" is unactionable and "both read
    #: Cloudflare's 2026 10-K" tells a reader exactly what happened.
    shared_inputs: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "independent": self.independent,
                "reason": self.reason,
                "shared_inputs": list(self.shared_inputs)}


def independent(graph: EvidenceGraph, a: str, b: str) -> IndependenceVerdict:
    """Are `a` and `b` two witnesses, or one witness counted twice?"""
    if a == b:
        return IndependenceVerdict(False, "the same node")
    node_a, node_b = graph.get(a), graph.get(b)
    if node_a is None or node_b is None:
        # Fail closed. An unknown node's lineage is unknown, and an unknown
        # lineage that defaults to "independent" is exactly the manufactured
        # corroboration this module exists to stop.
        return IndependenceVerdict(
            False, "one of the two is not in the graph, so its lineage "
                   "cannot be established; unknown lineage is not "
                   "independence")
    anc_a, anc_b = graph.ancestors(a), graph.ancestors(b)
    if b in anc_a:
        return IndependenceVerdict(
            False, f"{a} is derived from {b}; a derived signal is not "
                   "independent evidence of its own input",
            shared_inputs=(b,))
    if a in anc_b:
        return IndependenceVerdict(
            False, f"{b} is derived from {a}; a derived signal is not "
                   "independent evidence of its own input",
            shared_inputs=(a,))
    shared = tuple(sorted(anc_a & anc_b))
    if shared:
        return IndependenceVerdict(
            False, "both are derived from the same underlying evidence; two "
                   "readings of one panel are one witness",
            shared_inputs=shared[:8])
    # Two directly-observed nodes from the same publisher are not two
    # witnesses either. This is the non-derived half of the same idea and it
    # is where the "every SEC filing is one origin" error lives in reverse:
    # the publisher is the author, never the venue.
    if (not node_a.derived and not node_b.derived
            and node_a.provenance.publisher
            and node_a.provenance.publisher == node_b.provenance.publisher):
        return IndependenceVerdict(
            False, f"both were published by {node_a.provenance.publisher}; "
                   "one author saying something twice is one source")
    return IndependenceVerdict(True, "no shared input and no shared author")


def independent_support(graph: EvidenceGraph, claim_node: str,
                        candidates: Sequence[str]) -> Tuple[List[str], List[IndependenceVerdict]]:
    """Which candidates may be counted as support for `claim_node`.

    Returns the admissible ids AND the refusals, because a count with no
    account of what it dropped is the same opaque number the wall replaced.
    Candidates are also checked against EACH OTHER, greedily in the order
    given: three indices over the same panel contribute one, not three.
    """
    kept: List[str] = []
    refusals: List[IndependenceVerdict] = []
    for cid in candidates:
        verdict = independent(graph, claim_node, cid)
        if not verdict.independent:
            refusals.append(verdict)
            continue
        clash = next((v for v in (independent(graph, k, cid) for k in kept)
                      if not v.independent), None)
        if clash is not None:
            refusals.append(clash)
            continue
        kept.append(cid)
    return kept, refusals


def assert_not_self_corroborating(graph: EvidenceGraph, *, claim_node: str,
                                  support: Iterable[str], where: str) -> None:
    """Raise rather than quietly drop, for surfaces that publish a count."""
    bad = [s for s in support
           if not independent(graph, claim_node, s).independent]
    if bad:
        raise LineageViolation(
            f"{where}: {len(bad)} of the offered supporting node(s) are not "
            f"independent of the claim ({bad[:3]}). A derived aggregate "
            "cannot corroborate the evidence it was built from.")


def provenance_chain(graph: EvidenceGraph, node_id: str) -> List[dict]:
    """The readable account of where a derived signal came from.

    Ordered shallowest-first so a reader sees "built from 40 company
    observations" before the forty ids.
    """
    out: List[dict] = []
    frontier = [(node_id, 0)]
    seen = set()
    while frontier:
        current, depth = frontier.pop(0)
        if current in seen:
            continue
        seen.add(current)
        n = graph.get(current)
        if n is None:
            continue
        out.append({"node_id": current, "depth": depth, "kind": n.kind,
                    "subject": n.subject,
                    "publisher": n.provenance.publisher,
                    "derived": n.derived})
        frontier.extend((p, depth + 1) for p in n.depends_on)
    return out

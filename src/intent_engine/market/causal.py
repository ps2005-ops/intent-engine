"""Causal pathways: mechanisms with lags, conditions and competing stories.

WHY A GRAPH RATHER THAN RULES
-----------------------------
An if-then rule — "oil up, therefore equipment makers up" — hides every step
that could break. The pathway is what actually carries the effect:

    oil price → producer margins → cash flow → capex → supplier orders
    → equipment revenue → employment and capacity

Written out, it becomes checkable. Each edge has its own lag, its own
conditions, and its own competing explanation, so when the chain fails a
reader can see *which link* failed instead of discarding the whole idea.

CORRELATION IS NOT PROMOTED BY ACCUMULATION
-------------------------------------------
The single most dangerous thing this module could do is let an edge drift from
"we noticed these move together" to "this causes that" because it kept being
observed. Co-movement, repeated, is still co-movement. So `promote` refuses to
move an edge to SUPPORTED without a stated mechanism AND a stated competing
explanation that the evidence actually discriminates against — and there is no
code path that reaches SUPPORTED any other way.

STATUS IS A CLAIM ABOUT EVIDENCE, NOT ABOUT AGE
-----------------------------------------------
    HYPOTHESIZED   proposed, mechanism stated, not yet tested
    SUPPORTED      tested, survived, competing explanation addressed
    CONTRADICTED   tested, failed
    UNDER_REVIEW   was supported, has since failed or gone stale
    RETIRED        withdrawn

LAGS ARE PART OF THE CLAIM
--------------------------
A pathway that says "rates affect demand" without a lag cannot be wrong at any
particular moment. `lag_days` makes the claim testable, and `expected_effect_at`
turns an edge into a date a reconciliation can be scored on.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

CONTRACT_VERSION = "causal_graph.v1"

HYPOTHESIZED = "HYPOTHESIZED"
SUPPORTED = "SUPPORTED"
CONTRADICTED = "CONTRADICTED"
UNDER_REVIEW = "UNDER_REVIEW"
RETIRED = "RETIRED"
EDGE_STATUSES = frozenset({HYPOTHESIZED, SUPPORTED, CONTRADICTED,
                           UNDER_REVIEW, RETIRED})

POSITIVE = "POSITIVE"
NEGATIVE = "NEGATIVE"
AMBIGUOUS = "AMBIGUOUS"
DIRECTIONS = frozenset({POSITIVE, NEGATIVE, AMBIGUOUS})


class CausalError(ValueError):
    """An operation that would have claimed causation without evidence."""


@dataclass(frozen=True)
class CausalEdge:
    """One link in a pathway, with everything needed to falsify it."""
    edge_id: str
    cause: str
    effect: str
    direction: str
    mechanism: str
    lag_days: Optional[int] = None
    conditions: Tuple[str, ...] = ()
    competing_explanations: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    status: str = HYPOTHESIZED
    uncertainty: float = 0.5
    last_validated: str = ""
    observations: int = 0

    @property
    def is_asserted(self) -> bool:
        return self.status == SUPPORTED

    def expected_effect_at(self, cause_date: str) -> Optional[str]:
        """When the effect should be visible — the date a test can score."""
        if self.lag_days is None:
            return None
        from datetime import date, timedelta
        try:
            return (date.fromisoformat(cause_date[:10])
                    + timedelta(days=self.lag_days)).isoformat()
        except (TypeError, ValueError):
            return None

    def as_dict(self) -> dict:
        return {"edge_id": self.edge_id, "cause": self.cause,
                "effect": self.effect, "direction": self.direction,
                "mechanism": self.mechanism, "lag_days": self.lag_days,
                "conditions": list(self.conditions),
                "competing_explanations": list(self.competing_explanations),
                "evidence_ids": list(self.evidence_ids),
                "status": self.status, "uncertainty": self.uncertainty,
                "last_validated": self.last_validated,
                "observations": self.observations}


def edge(*, cause: str, effect: str, direction: str, mechanism: str,
         lag_days: Optional[int] = None, conditions: Sequence[str] = (),
         competing_explanations: Sequence[str] = (),
         evidence_ids: Sequence[str] = (), uncertainty: float = 0.5
         ) -> CausalEdge:
    """Propose an edge. It starts HYPOTHESIZED, always.

    There is no constructor argument for `status`. An edge cannot be born
    asserted; it has to be promoted, and promotion has its own gate.
    """
    if not (cause or "").strip() or not (effect or "").strip():
        raise CausalError("an edge needs both a cause and an effect")
    if direction not in DIRECTIONS:
        raise CausalError(f"unknown direction {direction!r}")
    if not (mechanism or "").strip():
        raise CausalError(
            "an edge needs a stated mechanism; without one it records that "
            "two things moved together, which is not a causal claim")
    eid = "edge_" + hashlib.sha256(
        f"{cause}|{effect}".lower().encode("utf-8")).hexdigest()[:12]
    return CausalEdge(edge_id=eid, cause=cause.strip(), effect=effect.strip(),
                      direction=direction, mechanism=mechanism.strip(),
                      lag_days=lag_days, conditions=tuple(conditions),
                      competing_explanations=tuple(competing_explanations),
                      evidence_ids=tuple(evidence_ids),
                      uncertainty=min(max(float(uncertainty), 0.0), 1.0))


def observe_covariation(e: CausalEdge, *, at: str,
                        evidence_ids: Sequence[str] = ()) -> CausalEdge:
    """Record that the two moved together again. Does NOT promote.

    Deliberately separate from `promote`. Counting co-movements is useful and
    cheap; treating the count as proof is the error this separation prevents.
    An edge observed a hundred times is still HYPOTHESIZED until something
    discriminates it from its competing explanation.
    """
    return replace(e, observations=e.observations + 1,
                   evidence_ids=e.evidence_ids + tuple(evidence_ids),
                   last_validated=at[:10])


def promote(e: CausalEdge, *, at: str, discriminating_evidence: str,
            evidence_ids: Sequence[str] = ()) -> CausalEdge:
    """Move an edge to SUPPORTED. The only route, and it is gated.

    Requires evidence that discriminates this mechanism from its stated
    rivals. "They moved together again" is not discriminating and is refused,
    however many times it has been observed.
    """
    if not e.competing_explanations:
        raise CausalError(
            f"{e.edge_id}: cannot promote an edge that has never named a "
            f"competing explanation; without a rival there is nothing for "
            f"evidence to discriminate against")
    if not (discriminating_evidence or "").strip():
        raise CausalError(
            f"{e.edge_id}: promotion requires evidence that discriminates "
            f"this mechanism from its competing explanations; repeated "
            f"co-movement is not that evidence")
    if not evidence_ids:
        raise CausalError(f"{e.edge_id}: promotion requires cited evidence")
    return replace(e, status=SUPPORTED, last_validated=at[:10],
                   evidence_ids=e.evidence_ids + tuple(evidence_ids),
                   mechanism=e.mechanism,
                   conditions=e.conditions + (
                       f"discriminated by: {discriminating_evidence.strip()}",))


def contradict(e: CausalEdge, *, at: str, reason: str,
               evidence_ids: Sequence[str] = ()) -> CausalEdge:
    """Demote on a failed test. SUPPORTED goes to UNDER_REVIEW, not straight out.

    One failure against an edge that has survived discrimination is more
    likely to be a condition nobody wrote down than a refutation, so the edge
    is flagged for review rather than discarded.
    """
    status = UNDER_REVIEW if e.status == SUPPORTED else CONTRADICTED
    return replace(e, status=status, last_validated=at[:10],
                   evidence_ids=e.evidence_ids + tuple(evidence_ids),
                   conditions=e.conditions + (f"failed {at[:10]}: {reason}",))


@dataclass(frozen=True)
class CausalPathway:
    """An ordered chain of edges from a root cause to an outcome."""
    pathway_id: str
    name: str
    edges: Tuple[CausalEdge, ...]

    @property
    def nodes(self) -> Tuple[str, ...]:
        seen: List[str] = []
        for e in self.edges:
            for node in (e.cause, e.effect):
                if node not in seen:
                    seen.append(node)
        return tuple(seen)

    @property
    def total_lag_days(self) -> Optional[int]:
        """Cumulative lag, or None if any link has not stated one.

        None rather than a partial sum: a chain with an unknown link has an
        unknown total, and silently summing the known ones would understate
        it every time.
        """
        if any(e.lag_days is None for e in self.edges):
            return None
        return sum(e.lag_days or 0 for e in self.edges)

    @property
    def weakest_link(self) -> Optional[CausalEdge]:
        """The edge most likely to break the chain — where to look first."""
        rank = {CONTRADICTED: 0, UNDER_REVIEW: 1, HYPOTHESIZED: 2,
                SUPPORTED: 3, RETIRED: 0}
        return min(self.edges,
                   key=lambda e: (rank.get(e.status, 2), -e.uncertainty),
                   default=None)

    @property
    def status(self) -> str:
        """A chain is only as strong as its weakest link, never stronger."""
        if not self.edges:
            return HYPOTHESIZED
        if any(e.status in (CONTRADICTED, RETIRED) for e in self.edges):
            return CONTRADICTED
        if any(e.status == UNDER_REVIEW for e in self.edges):
            return UNDER_REVIEW
        if all(e.status == SUPPORTED for e in self.edges):
            return SUPPORTED
        return HYPOTHESIZED

    def narrate(self) -> str:
        """The chain as a founder-readable sentence, arrows and all."""
        if not self.edges:
            return ""
        return " → ".join(self.nodes)

    def as_dict(self) -> dict:
        weakest = self.weakest_link
        return {"pathway_id": self.pathway_id, "name": self.name,
                "nodes": list(self.nodes), "narrative": self.narrate(),
                "status": self.status,
                "total_lag_days": self.total_lag_days,
                "weakest_link": weakest.edge_id if weakest else None,
                "edges": [e.as_dict() for e in self.edges]}


def pathway(name: str, edges: Sequence[CausalEdge]) -> CausalPathway:
    """Assemble a chain, checking that it actually connects.

    A "pathway" whose links do not join is a list of unrelated claims wearing
    the authority of a mechanism, which is worse than either honest form.
    """
    if not edges:
        raise CausalError("a pathway needs at least one edge")
    for earlier, later in zip(edges, edges[1:]):
        if earlier.effect != later.cause:
            raise CausalError(
                f"pathway break: {earlier.effect!r} does not lead into "
                f"{later.cause!r}; a chain whose links do not join is a list "
                f"of claims, not a mechanism")
    pid = "path_" + hashlib.sha256(
        name.lower().encode("utf-8")).hexdigest()[:12]
    return CausalPathway(pathway_id=pid, name=name, edges=tuple(edges))


class CausalGraph:
    """The mutable store. Rebuildable, and never a second source of truth."""

    def __init__(self, edges: Sequence[CausalEdge] = ()):
        self._edges: Dict[str, CausalEdge] = {e.edge_id: e for e in edges}

    def add(self, e: CausalEdge) -> CausalEdge:
        existing = self._edges.get(e.edge_id)
        if existing is not None:
            return existing
        self._edges[e.edge_id] = e
        return e

    def get(self, edge_id: str) -> Optional[CausalEdge]:
        return self._edges.get(edge_id)

    def replace(self, e: CausalEdge) -> None:
        self._edges[e.edge_id] = e

    def all(self) -> Tuple[CausalEdge, ...]:
        return tuple(self._edges.values())

    def downstream(self, node: str, *, max_depth: int = 6
                   ) -> Tuple[CausalEdge, ...]:
        """Everything `node` reaches. Cycle-safe by construction.

        The visited set is on EDGES, not nodes: a feedback loop (capacity →
        price → demand → capacity) is a real economic structure that must be
        representable, so the traversal tolerates it rather than the model
        forbidding it.
        """
        out: List[CausalEdge] = []
        seen: Set[str] = set()
        frontier = [(node, 0)]
        while frontier:
            current, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            for e in self._edges.values():
                if e.cause == current and e.edge_id not in seen:
                    seen.add(e.edge_id)
                    out.append(e)
                    frontier.append((e.effect, depth + 1))
        return tuple(out)

    def summarise(self, before: Sequence[CausalEdge] = ()) -> dict:
        """Edges added, strengthened, weakened — for the session report."""
        prior = {e.edge_id: e.status for e in before}
        added = strengthened = weakened = 0
        for e in self._edges.values():
            was = prior.get(e.edge_id)
            if was is None:
                added += 1
            elif was != e.status:
                if e.status == SUPPORTED:
                    strengthened += 1
                elif e.status in (CONTRADICTED, UNDER_REVIEW, RETIRED):
                    weakened += 1
        by_status: Dict[str, int] = {}
        for e in self._edges.values():
            by_status[e.status] = by_status.get(e.status, 0) + 1
        return {"edges_total": len(self._edges), "added": added,
                "strengthened": strengthened, "weakened": weakened,
                "by_status": by_status,
                "asserted": sum(1 for e in self._edges.values()
                                if e.is_asserted)}

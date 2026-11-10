"""The structural causal graph, and the ladder that decides what may be said.

WHY A LADDER RATHER THAN A STATUS
---------------------------------
`market.causal` already carries a status — HYPOTHESIZED / SUPPORTED /
CONTRADICTED — and it is a good design: `promote` refuses SUPPORTED without a
stated mechanism and a discriminating competing explanation. What it cannot
express is HOW the edge was established, and that is the distinction Section 4
exists to force. Two edges can both be SUPPORTED, one from a lagged
correlation over 60 observations and one from a natural experiment, and a
reader has no way to tell them apart.

    LEVEL 0  contemporaneous correlation
    LEVEL 1  lagged predictive relationship
    LEVEL 2  transfer entropy / nonlinear dependence
    LEVEL 3  structural restrictions (SVAR-style identification)
    LEVEL 4  natural experiment / event identification
    LEVEL 5  synthetic control / credible causal estimate

TRANSFER ENTROPY IS NOT A LICENCE
---------------------------------
This is the specific error the ladder is built to prevent. Transfer entropy
measures information flow. Information flows from a thermometer to a
weather report and the report does not cause the weather. An edge at LEVEL 2
has an INFORMATION claim, not a causal one, and `statement()` refuses to
produce the word "causes" below LEVEL 3 — not by convention, by returning a
different sentence.

WHAT AN EDGE MUST CARRY
-----------------------
Every field below is load-bearing. `lag_days` is what makes the claim
falsifiable at a particular moment; `sample_window` is what makes it possible
to notice the relationship was fitted to eleven observations; `falsifier` is
what makes the edge a scientific object rather than an opinion; `stability`
is how the engine notices a relationship that held for two years and stopped.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_causal.v1"

# --- the ladder -------------------------------------------------------------
L0_CORRELATION = 0
L1_LAGGED = 1
L2_INFORMATION = 2
L3_STRUCTURAL = 3
L4_EXPERIMENT = 4
L5_SYNTHETIC = 5

LEVEL_NAMES = {
    L0_CORRELATION: "contemporaneous correlation",
    L1_LAGGED: "lagged predictive relationship",
    L2_INFORMATION: "transfer entropy / nonlinear dependence",
    L3_STRUCTURAL: "structural restriction (SVAR-style identification)",
    L4_EXPERIMENT: "natural experiment / event identification",
    L5_SYNTHETIC: "synthetic control / credible causal estimate",
}

#: The line the whole module exists to draw. At or above this, the engine may
#: use causal language on a surface a human reads.
CAUSAL_LANGUAGE_FLOOR = L3_STRUCTURAL

#: What each level requires before it may be claimed. Checked, not documented:
#: `edge()` refuses a level whose evidence field is empty.
LEVEL_REQUIREMENTS = {
    L0_CORRELATION: "a measured co-movement over a stated window",
    L1_LAGGED: "a stated lag and out-of-sample predictive content at it",
    L2_INFORMATION: "a directional dependence estimate and its null",
    L3_STRUCTURAL: "the restriction that identifies the direction, stated",
    L4_EXPERIMENT: "the event, its date, and why assignment was plausibly "
                   "exogenous",
    L5_SYNTHETIC: "the donor pool, the pre-period fit, and the placebo test",
}

UP, DOWN = "UP", "DOWN"
SIGNS = (UP, DOWN)

STABLE = "STABLE"
DRIFTING = "DRIFTING"
BROKEN = "BROKEN"
STABILITIES = (STABLE, DRIFTING, BROKEN)


@dataclass(frozen=True)
class CausalEdge:
    """One directed candidate mechanism between two economic quantities."""

    cause: str
    effect: str
    #: Sign of the effect of an INCREASE in `cause`.
    sign: str
    mechanism: str
    evidence_level: int
    #: What was actually done to establish it, at this level.
    evidence: str
    falsifier: str
    lag_days: int
    sample_start: str
    sample_end: str
    sample_n: int
    confidence: float = 0.5
    stability: str = STABLE
    #: The rival account this edge has to beat. An edge with no competing
    #: explanation has not been tested against anything.
    competing_explanation: str = ""
    #: Node ids in the evidence graph that established it.
    evidence_nodes: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(bool(self.cause and self.effect), "an edge needs both ends")
        require(self.cause != self.effect,
                "a quantity does not transmit to itself")
        require(self.sign in SIGNS, f"unknown sign {self.sign!r}")
        require(self.evidence_level in LEVEL_NAMES,
                f"evidence level {self.evidence_level} is not on the ladder")
        require(bool(self.mechanism.strip()),
                "an edge without a mechanism is a correlation with an arrow "
                "drawn on it")
        require(bool(self.evidence.strip()),
                f"level {self.evidence_level} requires "
                f"{LEVEL_REQUIREMENTS[self.evidence_level]}, and this edge "
                "states none")
        require(bool(self.falsifier.strip()),
                "an edge that cannot be wrong is not a finding")
        require(self.stability in STABILITIES,
                f"unknown stability {self.stability!r}")
        require(0.0 <= self.confidence <= 1.0, "confidence is a probability")
        require(self.sample_n >= 0, "sample size cannot be negative")
        if self.evidence_level >= CAUSAL_LANGUAGE_FLOOR:
            require(bool(self.competing_explanation.strip()),
                    f"level {self.evidence_level} permits causal language, "
                    "so it must name the competing explanation the evidence "
                    "discriminates against; without one, repetition is being "
                    "mistaken for identification")

    @property
    def may_state_causation(self) -> bool:
        return self.evidence_level >= CAUSAL_LANGUAGE_FLOOR

    @property
    def key(self) -> Tuple[str, str]:
        return (self.cause, self.effect)

    def statement(self) -> str:
        """The sentence a human is allowed to read for this edge.

        Below the floor this returns an ASSOCIATION sentence. That is the
        whole enforcement: there is no argument, no flag and no override that
        produces "causes" from a level-2 edge, because the string is not
        constructed anywhere on that branch.
        """
        move = "a rise" if self.sign == UP else "a fall"
        if self.may_state_causation:
            return (f"a rise in {self.cause} causes {move} in {self.effect} "
                    f"after about {self.lag_days} days "
                    f"({LEVEL_NAMES[self.evidence_level]})")
        return (f"a rise in {self.cause} has been ASSOCIATED WITH {move} in "
                f"{self.effect} after about {self.lag_days} days; this is "
                f"{LEVEL_NAMES[self.evidence_level]} and does not establish "
                "direction")

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "cause": self.cause,
                "effect": self.effect, "sign": self.sign,
                "mechanism": self.mechanism,
                "evidence_level": self.evidence_level,
                "evidence_level_name": LEVEL_NAMES[self.evidence_level],
                "may_state_causation": self.may_state_causation,
                "evidence": self.evidence, "falsifier": self.falsifier,
                "lag_days": self.lag_days, "confidence": self.confidence,
                "stability": self.stability,
                "sample": {"start": self.sample_start,
                           "end": self.sample_end, "n": self.sample_n},
                "competing_explanation": self.competing_explanation,
                "evidence_nodes": list(self.evidence_nodes),
                "statement": self.statement()}


def edge(**kwargs) -> CausalEdge:
    """The only supported constructor; every invariant runs in __post_init__."""
    return CausalEdge(**kwargs)


def raise_level(e: CausalEdge, *, to: int, evidence: str,
                competing_explanation: str = "") -> CausalEdge:
    """Move an edge UP the ladder, and only for new evidence of that kind.

    A level is not reached by accumulating more of the evidence that
    established the level below. Ten years of correlation is still LEVEL 0;
    what moves an edge to LEVEL 3 is a restriction, and to LEVEL 4 an event.
    So `evidence` is required and must be new text — passing the same
    sentence up a level is refused.
    """
    require(to > e.evidence_level,
            "raise_level moves up; use `contradict` or `destabilise` to move "
            "an edge down")
    require(bool(evidence.strip()) and evidence.strip() != e.evidence.strip(),
            f"level {to} requires {LEVEL_REQUIREMENTS[to]}; repeating the "
            "evidence that established the level below is how a correlation "
            "becomes a cause by attrition")
    return replace(e, evidence_level=to, evidence=evidence,
                   competing_explanation=(competing_explanation
                                          or e.competing_explanation))


def destabilise(e: CausalEdge, *, to: str, reason: str) -> CausalEdge:
    require(to in STABILITIES, f"unknown stability {to!r}")
    require(bool(reason.strip()), "a stability change states what changed")
    return replace(e, stability=to,
                   evidence=f"{e.evidence} | {to}: {reason}")


class StructuralCausalGraph:
    """Directed candidate mechanisms, addressable by (cause, effect)."""

    def __init__(self, edges: Sequence[CausalEdge] = ()) -> None:
        self._edges: Dict[Tuple[str, str], CausalEdge] = {}
        for e in edges:
            self.add(e)

    def add(self, e: CausalEdge) -> CausalEdge:
        """Later evidence wins, but only upward.

        Re-adding a weaker version of an edge already established at a higher
        level is refused rather than accepted: a nightly correlation refresh
        must not silently demote a natural experiment.
        """
        existing = self._edges.get(e.key)
        if existing is not None and e.evidence_level < existing.evidence_level:
            raise EconError(
                f"edge {e.cause}->{e.effect} is already established at level "
                f"{existing.evidence_level}; re-adding it at level "
                f"{e.evidence_level} would demote it. Use `destabilise` to "
                "record that it stopped holding.")
        self._edges[e.key] = e
        return e

    def get(self, cause: str, effect: str) -> Optional[CausalEdge]:
        return self._edges.get((cause, effect))

    def edges(self, *, min_level: int = L0_CORRELATION,
              cause: str = "", effect: str = "") -> List[CausalEdge]:
        out = [e for e in self._edges.values()
               if e.evidence_level >= min_level]
        if cause:
            out = [e for e in out if e.cause == cause]
        if effect:
            out = [e for e in out if e.effect == effect]
        return sorted(out, key=lambda e: (-e.evidence_level, e.cause, e.effect))

    def quantities(self) -> List[str]:
        names = {e.cause for e in self._edges.values()}
        names |= {e.effect for e in self._edges.values()}
        return sorted(names)

    def downstream(self, cause: str, *, max_depth: int = 3,
                   min_level: int = L0_CORRELATION) -> List[Tuple[int, CausalEdge]]:
        """Breadth-first propagation, depth-bounded and cycle-safe.

        Depth IS the order of effect: depth 1 is first-order, 2 second-order,
        3 the interaction terms. A reader needs that distinction because the
        confidence in a third-order effect is not the confidence in the edges
        that produced it — see `shock.propagate`, which multiplies it out.
        """
        out: List[Tuple[int, CausalEdge]] = []
        frontier = [(cause, 1)]
        seen_edges = set()
        while frontier:
            node, depth = frontier.pop(0)
            if depth > max_depth:
                continue
            for e in self.edges(cause=node, min_level=min_level):
                if e.key in seen_edges:
                    continue
                seen_edges.add(e.key)
                out.append((depth, e))
                frontier.append((e.effect, depth + 1))
        return out

    def summary(self) -> dict:
        by_level: Dict[int, int] = {}
        for e in self._edges.values():
            by_level[e.evidence_level] = by_level.get(e.evidence_level, 0) + 1
        causal = sum(1 for e in self._edges.values() if e.may_state_causation)
        return {"contract": CONTRACT, "edges": len(self._edges),
                "quantities": len(self.quantities()),
                "by_level": {str(k): v for k, v in sorted(by_level.items())},
                "may_state_causation": causal,
                "association_only": len(self._edges) - causal,
                "unstable": sum(1 for e in self._edges.values()
                                if e.stability != STABLE)}

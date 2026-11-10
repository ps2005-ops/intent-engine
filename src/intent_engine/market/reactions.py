"""Bounded reaction trees: who can respond, how, and at what cost.

WHAT THIS REFUSES TO DO
-----------------------
It does not solve for equilibrium. Equilibrium requires payoffs this engine has
not measured, and a computed Nash outcome over invented numbers is the most
persuasive wrong answer available — it looks like mathematics. What it produces
instead is a bounded set of responses, each labelled by how much evidence
stands behind it:

    LIKELY          the actor has done this before in comparable conditions,
                    can afford it, and is permitted to do it
    PLAUSIBLE       feasible and consistent with stated objectives, but not
                    demonstrated
    LOW_EVIDENCE    a scenario worth watching, explicitly not a prediction
    UNKNOWN         the actor's capability or constraint is not established

FEASIBILITY IS CHECKED BEFORE PROBABILITY
-----------------------------------------
A response an actor cannot execute has no probability worth discussing. The
tree checks the actor's action set and constraints FIRST, so "the competitor
cuts price 30%" is dropped when that competitor is capital-constrained,
rather than being carried forward with a small weight that a reader will
misread as a real possibility.

STRATEGIC FACTORS ARE EVIDENCE SLOTS, NOT ADJECTIVES
-----------------------------------------------------
First-mover advantage, commitment credibility, retaliation capability,
switching costs, capacity, regulatory constraint, repeated-game incentives,
coordination risk, entry deterrence and bargaining power each get a field that
is either evidenced or explicitly unassessed. Unassessed is common and is
reported, because a factor silently omitted reads as a factor judged absent.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import strategic_interaction as SI

CONTRACT_VERSION = "reaction_tree.v1"

LIKELY = "LIKELY"
PLAUSIBLE = "PLAUSIBLE"
LOW_EVIDENCE = "LOW_EVIDENCE"
UNKNOWN = "UNKNOWN"
INFEASIBLE = "INFEASIBLE"
CONFIDENCE_LABELS = (LIKELY, PLAUSIBLE, LOW_EVIDENCE, UNKNOWN, INFEASIBLE)

# Actions important enough to warrant a tree. Anything else is an event, not
# a move — the distinction keeps trees from being built for press releases.
STRATEGIC_ACTIONS = frozenset({
    "PRICE_CUT", "PRICE_INCREASE", "BUNDLING", "MARKET_ENTRY",
    "CAPACITY_EXPANSION", "ACQUISITION", "REGULATORY_CHALLENGE",
    "AUCTION_BID", "CONTRACT_BID", "PLATFORM_RULE_CHANGE", "EXCLUSIVITY",
    "OPEN_SOURCE_RELEASE", "SUPPLIER_RENEGOTIATION", "VERTICAL_INTEGRATION",
})

# The ten factors §9 requires. Each is either evidenced or reported unassessed.
STRATEGIC_FACTORS = (
    "first_mover_advantage", "commitment_credibility",
    "retaliation_capability", "switching_costs", "capacity",
    "regulatory_constraint", "repeated_game_incentives",
    "coordination_risk", "entry_deterrence", "bargaining_power",
)


class ReactionError(ValueError):
    """A reaction tree that would have asserted an unevidenced response."""


@dataclass(frozen=True)
class ResponseOption:
    """One thing an actor could do, and how well that is established."""
    responder: str
    response: str
    confidence: str
    payoff_effect: str
    rationale: str
    evidence_ids: Tuple[str, ...] = ()
    second_order: Tuple[str, ...] = ()
    precedents: Tuple[str, ...] = ()

    @property
    def is_prediction(self) -> bool:
        """Only LIKELY is stated as an expectation. Everything else watches."""
        return self.confidence == LIKELY

    def as_dict(self) -> dict:
        return {"responder": self.responder, "response": self.response,
                "confidence": self.confidence,
                "payoff_effect": self.payoff_effect,
                "rationale": self.rationale,
                "evidence_ids": list(self.evidence_ids),
                "second_order": list(self.second_order),
                "precedents": list(self.precedents),
                "is_prediction": self.is_prediction}


@dataclass(frozen=True)
class ReactionTree:
    """An action, its feasible responses, and what remains unassessed."""
    tree_id: str
    actor: str
    action: str
    action_kind: str
    at: str
    responses: Tuple[ResponseOption, ...] = ()
    infeasible: Tuple[ResponseOption, ...] = ()
    factors: Tuple[Tuple[str, str], ...] = ()
    equilibrium_risk: str = ""
    uncertainty: str = ""

    @property
    def unassessed_factors(self) -> Tuple[str, ...]:
        assessed = {k for k, v in self.factors if v}
        return tuple(f for f in STRATEGIC_FACTORS if f not in assessed)

    @property
    def likely_responses(self) -> Tuple[ResponseOption, ...]:
        return tuple(r for r in self.responses if r.confidence == LIKELY)

    def as_dict(self) -> dict:
        return {
            "tree_id": self.tree_id, "actor": self.actor,
            "action": self.action, "action_kind": self.action_kind,
            "at": self.at,
            "responses": [r.as_dict() for r in self.responses],
            "infeasible_responses": [r.as_dict() for r in self.infeasible],
            "factors": dict(self.factors),
            "unassessed_factors": list(self.unassessed_factors),
            "equilibrium_risk": self.equilibrium_risk,
            "uncertainty": self.uncertainty,
            "stated_as_prediction": [r.response for r in self.likely_responses],
        }


def classify_response(*, responder: SI.Actor, response: str,
                      precedents: Sequence[str] = (),
                      evidence_ids: Sequence[str] = (),
                      consistent_with_objective: bool = False) -> str:
    """How much evidence stands behind this response. Feasibility first.

    The order is the point. An infeasible response is not a low-probability
    response — it is not a response — and collapsing the two is how a
    capital-constrained rival ends up modelled as launching a price war.
    """
    if responder.available_actions and not responder.can(response):
        return INFEASIBLE
    if precedents and evidence_ids:
        return LIKELY
    if consistent_with_objective and responder.available_actions:
        return PLAUSIBLE
    if responder.available_actions or evidence_ids:
        return LOW_EVIDENCE
    return UNKNOWN


def build_tree(*, actor: str, action: str, action_kind: str, at: str,
               candidates: Sequence[dict],
               factors: Optional[Dict[str, str]] = None,
               equilibrium_risk: str = "",
               uncertainty: str = "") -> ReactionTree:
    """Assemble a tree, separating feasible responses from infeasible ones.

    `candidates` items carry `responder` (an SI.Actor), `response`,
    `payoff_effect`, `rationale`, and optionally `precedents`,
    `evidence_ids`, `second_order`, `consistent_with_objective`.
    """
    if action_kind not in STRATEGIC_ACTIONS:
        raise ReactionError(
            f"{action_kind!r} is not a strategic action; a reaction tree for "
            f"an ordinary event manufactures strategic weight it lacks")

    feasible: List[ResponseOption] = []
    blocked: List[ResponseOption] = []
    for c in candidates:
        responder = c["responder"]
        if not isinstance(responder, SI.Actor):
            raise ReactionError("each candidate needs a modelled Actor; a "
                                "bare name has no constraints to check")
        confidence = classify_response(
            responder=responder, response=c["response"],
            precedents=c.get("precedents", ()),
            evidence_ids=c.get("evidence_ids", ()),
            consistent_with_objective=c.get("consistent_with_objective",
                                            False))
        option = ResponseOption(
            responder=responder.name, response=c["response"],
            confidence=confidence,
            payoff_effect=c.get("payoff_effect", SI.UNKNOWN),
            rationale=c.get("rationale", ""),
            evidence_ids=tuple(c.get("evidence_ids", ())),
            second_order=tuple(c.get("second_order", ())),
            precedents=tuple(c.get("precedents", ())))
        (blocked if confidence == INFEASIBLE else feasible).append(option)

    tid = "tree_" + hashlib.sha256(
        f"{actor}|{action}|{at[:10]}".encode("utf-8")).hexdigest()[:12]
    return ReactionTree(
        tree_id=tid, actor=actor, action=action, action_kind=action_kind,
        at=at[:10], responses=tuple(feasible), infeasible=tuple(blocked),
        factors=tuple(sorted((factors or {}).items())),
        equilibrium_risk=equilibrium_risk, uncertainty=uncertainty)


def assert_no_equilibrium_claim(tree: ReactionTree) -> None:
    """Refuse language that asserts a solved game.

    Checked on the way out rather than trusted at the call sites. "The
    equilibrium is" reads as a derived result; this engine has not derived
    one, and saying so would be a false claim wearing mathematical clothes.
    """
    banned = ("the equilibrium is", "equilibrium outcome is",
              "nash equilibrium", "will necessarily", "is guaranteed to",
              "the optimal response is")
    haystacks = [tree.equilibrium_risk] + [r.rationale for r in tree.responses]
    for text in haystacks:
        low = (text or "").lower()
        for phrase in banned:
            if phrase in low:
                raise ReactionError(
                    f"reaction tree asserts a solved game ({phrase!r}); "
                    f"payoffs here are not measured, so scenarios may be "
                    f"stated but an equilibrium may not")

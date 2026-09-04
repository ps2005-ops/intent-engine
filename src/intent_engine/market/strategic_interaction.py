"""Actors, payoffs, and the interaction sequences that are the real memory.

WHY SEQUENCES AND NOT FACTS
---------------------------
"Company A cut prices" is a fact. "A cut prices, B matched within a week, C
responded by bundling instead, and A's volumes did not recover" is a
mechanism — and only the second one transfers to the next situation. Storing
the fact and discarding the sequence is why a system can accumulate a great
deal of information and remain unable to anticipate anything.

So the stored unit is the interaction: an action, who responded, how, and what
that implies about their objectives.

ACTORS, NOT JUST COMPANIES
--------------------------
A company-only model cannot express the situations that decide outcomes: a
regulator who can veto, a supplier who can withhold, a capital market that can
close, a customer who can simply wait. Each actor carries objectives,
constraints and a feasible action set, because a response that an actor cannot
afford or is not permitted to make is not a plausible response however
strategically attractive it looks.

INFERRED OBJECTIVES ARE INFERENCES, AND STAY LABELLED
-----------------------------------------------------
`inferred_objective` always travels with `alternative_explanations`. An
observed action underdetermines motive — a price match defends share, clears
inventory, or punishes a defector, and the tape looks identical. Any
interaction recorded without at least one alternative is rejected by
`record`, because a single-explanation record is where a hypothesis quietly
becomes a fact.

PATTERNS ARE CANDIDATES, NEVER CONCLUSIONS
------------------------------------------
A historical analog matches only if its *mechanism* is present now.
`match_pattern` reports matched and missing preconditions and refuses to
conclude from name similarity alone: "this looks like the 2019 price war" is
an invitation to check, not a finding.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT_VERSION = "strategic_interaction.v1"

# --- actor kinds ----------------------------------------------------------
COMPANY = "COMPANY"
MANAGEMENT = "MANAGEMENT"
CUSTOMERS = "CUSTOMERS"
COMPETITORS = "COMPETITORS"
SUPPLIERS = "SUPPLIERS"
REGULATORS = "REGULATORS"
EMPLOYEES = "EMPLOYEES"
CAPITAL_MARKETS = "CAPITAL_MARKETS"
GOVERNMENTS = "GOVERNMENTS"
PARTNERS = "PARTNERS"
DISTRIBUTORS = "DISTRIBUTORS"
COMPLEMENTORS = "COMPLEMENTORS"

ACTOR_KINDS = frozenset({COMPANY, MANAGEMENT, CUSTOMERS, COMPETITORS,
                         SUPPLIERS, REGULATORS, EMPLOYEES, CAPITAL_MARKETS,
                         GOVERNMENTS, PARTNERS, DISTRIBUTORS, COMPLEMENTORS})

# --- interaction status ---------------------------------------------------
OPEN = "OPEN"
RESPONDED = "RESPONDED"
RESOLVED = "RESOLVED"
ABANDONED = "ABANDONED"
STATUSES = frozenset({OPEN, RESPONDED, RESOLVED, ABANDONED})

# --- payoff direction -----------------------------------------------------
IMPROVED = "IMPROVED"
WORSENED = "WORSENED"
UNCHANGED = "UNCHANGED"
UNKNOWN = "UNKNOWN"
PAYOFF_DIRECTIONS = frozenset({IMPROVED, WORSENED, UNCHANGED, UNKNOWN})


class InteractionRejected(ValueError):
    """The record would have asserted motive without alternatives."""


@dataclass(frozen=True)
class Actor:
    """A party whose incentives change what is feasible for everyone else."""
    actor_id: str
    name: str
    kind: str
    objectives: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()
    available_actions: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    uncertainty: float = 0.5

    def can(self, action: str) -> bool:
        """Is this action in the actor's feasible set?

        Used to reject fabricated responses. A competitor with no capacity to
        expand cannot be modelled as expanding capacity, however neat the
        story.
        """
        return action in self.available_actions

    def as_dict(self) -> dict:
        return {"actor_id": self.actor_id, "name": self.name,
                "kind": self.kind, "objectives": list(self.objectives),
                "constraints": list(self.constraints),
                "available_actions": list(self.available_actions),
                "evidence_ids": list(self.evidence_ids),
                "uncertainty": self.uncertainty}


def actor(*, name: str, kind: str, objectives: Sequence[str] = (),
          constraints: Sequence[str] = (),
          available_actions: Sequence[str] = (),
          evidence_ids: Sequence[str] = (),
          uncertainty: float = 0.5) -> Actor:
    if kind not in ACTOR_KINDS:
        raise InteractionRejected(f"unknown actor kind {kind!r}")
    if not (name or "").strip():
        raise InteractionRejected("an actor needs a name")
    aid = "act_" + hashlib.sha256(
        f"{name.strip().lower()}|{kind}".encode("utf-8")).hexdigest()[:12]
    return Actor(actor_id=aid, name=name.strip(), kind=kind,
                 objectives=tuple(objectives), constraints=tuple(constraints),
                 available_actions=tuple(available_actions),
                 evidence_ids=tuple(evidence_ids),
                 uncertainty=min(max(float(uncertainty), 0.0), 1.0))


@dataclass(frozen=True)
class StrategicInteraction:
    """An action, a response, and what the pair implies."""
    interaction_id: str
    focal_actor: str
    responding_actor: str
    initial_action: str
    at: str
    response: str = ""
    response_at: str = ""
    payoff_change: str = UNKNOWN
    payoff_note: str = ""
    inferred_objective: str = ""
    alternative_explanations: Tuple[str, ...] = ()
    market_context: str = ""
    evidence_ids: Tuple[str, ...] = ()
    outcome: str = ""
    status: str = OPEN

    @property
    def response_lag_days(self) -> Optional[int]:
        from datetime import date
        try:
            return (date.fromisoformat(self.response_at[:10])
                    - date.fromisoformat(self.at[:10])).days
        except (TypeError, ValueError):
            return None

    def as_dict(self) -> dict:
        return {"interaction_id": self.interaction_id,
                "focal_actor": self.focal_actor,
                "responding_actor": self.responding_actor,
                "initial_action": self.initial_action, "at": self.at,
                "response": self.response, "response_at": self.response_at,
                "response_lag_days": self.response_lag_days,
                "payoff_change": self.payoff_change,
                "payoff_note": self.payoff_note,
                "inferred_objective": self.inferred_objective,
                "alternative_explanations":
                    list(self.alternative_explanations),
                "market_context": self.market_context,
                "evidence_ids": list(self.evidence_ids),
                "outcome": self.outcome, "status": self.status}


def record(*, focal_actor: str, responding_actor: str, initial_action: str,
           at: str, response: str = "", response_at: str = "",
           payoff_change: str = UNKNOWN, payoff_note: str = "",
           inferred_objective: str = "",
           alternative_explanations: Sequence[str] = (),
           market_context: str = "", evidence_ids: Sequence[str] = (),
           outcome: str = "", status: str = OPEN) -> StrategicInteraction:
    """Record an interaction, refusing single-explanation motive claims."""
    if not (focal_actor or "").strip() or not (initial_action or "").strip():
        raise InteractionRejected("an interaction needs an actor and action")
    if payoff_change not in PAYOFF_DIRECTIONS:
        raise InteractionRejected(f"unknown payoff {payoff_change!r}")
    if status not in STATUSES:
        raise InteractionRejected(f"unknown status {status!r}")
    if inferred_objective and not alternative_explanations:
        raise InteractionRejected(
            "an inferred objective must travel with at least one alternative "
            "explanation; an observed action underdetermines motive, and a "
            "single-explanation record is how an inference becomes a fact")
    if response and not response_at:
        raise InteractionRejected(
            "a recorded response needs its own date; without one the "
            "sequence cannot be ordered and causality cannot be checked")
    if not evidence_ids:
        raise InteractionRejected(
            "an interaction with no evidence is a story; cite the "
            "observations that establish the action and the response")

    raw = f"{focal_actor}|{initial_action}|{at[:10]}|{responding_actor}"
    iid = "int_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:14]
    return StrategicInteraction(
        interaction_id=iid, focal_actor=focal_actor.strip(),
        responding_actor=(responding_actor or "").strip(),
        initial_action=initial_action.strip(), at=at[:10],
        response=response.strip(), response_at=(response_at or "")[:10],
        payoff_change=payoff_change, payoff_note=payoff_note.strip(),
        inferred_objective=inferred_objective.strip(),
        alternative_explanations=tuple(alternative_explanations),
        market_context=market_context.strip(),
        evidence_ids=tuple(evidence_ids), outcome=outcome.strip(),
        status=RESPONDED if response and status == OPEN else status)


def sequence(interactions: Sequence[StrategicInteraction]
             ) -> Tuple[StrategicInteraction, ...]:
    """Order an episode by when each move actually happened."""
    return tuple(sorted(interactions, key=lambda i: (i.at, i.response_at)))


# --------------------------------------------------------------------------
# interaction memory — reusable patterns (§14)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class InteractionPattern:
    """A named mechanism, its preconditions, and how to tell it is NOT this."""
    pattern_id: str
    name: str
    mechanism: str
    actors: Tuple[str, ...]
    stages: Tuple[str, ...]
    preconditions: Tuple[str, ...]
    falsifier: str
    historical_examples: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"pattern_id": self.pattern_id, "name": self.name,
                "mechanism": self.mechanism, "actors": list(self.actors),
                "stages": list(self.stages),
                "preconditions": list(self.preconditions),
                "falsifier": self.falsifier,
                "historical_examples": list(self.historical_examples)}


PATTERNS: Tuple[InteractionPattern, ...] = (
    InteractionPattern(
        pattern_id="pat_price_war", name="price war",
        mechanism=("One participant cuts to win share; rivals match because "
                   "conceding share is more costly than the margin lost; "
                   "prices ratchet down until capacity or capital binds."),
        actors=(COMPANY, COMPETITORS, CUSTOMERS),
        stages=("initial cut", "rival match", "second cut",
                "margin compression", "capacity or capital constraint binds"),
        preconditions=("low switching costs", "comparable products",
                       "spare capacity", "share is measurable to rivals"),
        falsifier=("rivals do not match within a normal response lag, or "
                   "switching costs keep customers in place despite the gap"),
        historical_examples=("US airline fare wars", "streaming price resets")),
    InteractionPattern(
        pattern_id="pat_platform_enclosure", name="platform enclosure",
        mechanism=("A platform absorbs a complement's function into itself, "
                   "converting a partner into a competitor and capturing the "
                   "margin the complement had earned."),
        actors=(COMPANY, PARTNERS, COMPLEMENTORS, CUSTOMERS),
        stages=("complement thrives on platform", "platform observes demand",
                "platform ships native equivalent",
                "complement loses distribution", "margin shifts to platform"),
        preconditions=("platform controls distribution",
                       "complement's function is observable to the platform",
                       "no contractual bar to entry"),
        falsifier=("the platform lacks the data or the right to build the "
                   "equivalent, or regulation bars self-preferencing")),
    InteractionPattern(
        pattern_id="pat_open_source_commoditization",
        name="open-source commoditization",
        mechanism=("A rival releases as free software the layer a competitor "
                   "charges for, moving profit to an adjacent layer it "
                   "already owns."),
        actors=(COMPANY, COMPETITORS, CUSTOMERS, PARTNERS),
        stages=("incumbent monetises a layer", "rival open-sources it",
                "buyers gain an unpaid option", "price pressure",
                "profit relocates to the adjacent layer"),
        preconditions=("the layer is separable",
                       "rival profits from an adjacent layer",
                       "buyers can adopt without prohibitive integration"),
        falsifier=("buyers will not operate the free option, or the layer "
                   "cannot be separated from the paid product")),
    InteractionPattern(
        pattern_id="pat_vertical_integration", name="vertical integration",
        mechanism=("A buyer acquires or builds its supplier's function to "
                   "secure supply or capture that margin, changing the "
                   "supplier from partner to rival."),
        actors=(COMPANY, SUPPLIERS, CUSTOMERS),
        stages=("supply constraint or margin envy", "build or buy decision",
                "in-house capability", "supplier loses volume",
                "bargaining power shifts"),
        preconditions=("supplier margin is visible", "scale justifies build",
                       "capability is acquirable"),
        falsifier=("the capability requires scale or IP the buyer cannot "
                   "reach, so the build stalls")),
    InteractionPattern(
        pattern_id="pat_procurement_escalation", name="procurement escalation",
        mechanism=("A large buyer runs repeated competitive rounds to convert "
                   "a differentiated purchase into a price contest."),
        actors=(COMPANY, CUSTOMERS, COMPETITORS, GOVERNMENTS),
        stages=("sole-source or negotiated award",
                "buyer introduces a second qualified vendor",
                "repeated bidding rounds", "price convergence",
                "margin compression for all bidders"),
        preconditions=("buyer concentration", "specification can be written "
                       "neutrally", "at least two qualified vendors"),
        falsifier=("switching cost or accreditation keeps a single vendor "
                   "qualified, so the second round never materialises")),
    InteractionPattern(
        pattern_id="pat_regulatory_retaliation",
        name="regulatory retaliation",
        mechanism=("A party that cannot win commercially shifts the contest "
                   "to a regulator who can impose a constraint it could not "
                   "impose itself."),
        actors=(COMPANY, COMPETITORS, REGULATORS, GOVERNMENTS),
        stages=("commercial loss", "complaint or lobbying",
                "regulatory inquiry", "constraint or remedy",
                "competitive position changes without a product change"),
        preconditions=("a regulator with jurisdiction",
                       "a plausible theory of harm",
                       "the complainant has standing"),
        falsifier=("no regulator has jurisdiction, or the theory of harm "
                   "fails on the facts")),
)

PATTERNS_BY_ID = {p.pattern_id: p for p in PATTERNS}


@dataclass(frozen=True)
class PatternMatch:
    """How well a present situation matches a stored mechanism."""
    pattern_id: str
    name: str
    matched: Tuple[str, ...]
    missing: Tuple[str, ...]
    falsifier: str
    evidence_ids: Tuple[str, ...] = ()

    @property
    def coverage(self) -> float:
        total = len(self.matched) + len(self.missing)
        return round(len(self.matched) / total, 3) if total else 0.0

    @property
    def verdict(self) -> str:
        """Never 'this IS a price war'. Always how much is actually present.

        A pattern missing any precondition is a CANDIDATE, because the missing
        one is usually the reason the analogy fails.
        """
        if not self.missing:
            return "MECHANISM_PRESENT"
        if self.coverage >= 0.5:
            return "CANDIDATE"
        return "WEAK_MATCH"

    def as_dict(self) -> dict:
        return {"pattern_id": self.pattern_id, "name": self.name,
                "matched": list(self.matched), "missing": list(self.missing),
                "coverage": self.coverage, "verdict": self.verdict,
                "falsifier": self.falsifier,
                "evidence_ids": list(self.evidence_ids)}


def match_pattern(pattern_id: str, *, present_conditions: Sequence[str],
                  evidence_ids: Sequence[str] = ()) -> PatternMatch:
    """Score a pattern against conditions actually evidenced right now.

    Returns matched AND missing. A caller that only reads `matched` would
    conclude from a half-match; the missing list is what makes the analogy
    checkable instead of persuasive.
    """
    pattern = PATTERNS_BY_ID.get(pattern_id)
    if pattern is None:
        raise InteractionRejected(f"unknown pattern {pattern_id!r}")
    present = {_norm(c) for c in present_conditions}
    matched = tuple(p for p in pattern.preconditions
                    if _norm(p) in present
                    or any(_norm(p) in c or c in _norm(p) for c in present))
    missing = tuple(p for p in pattern.preconditions if p not in matched)
    return PatternMatch(pattern_id=pattern.pattern_id, name=pattern.name,
                        matched=matched, missing=missing,
                        falsifier=pattern.falsifier,
                        evidence_ids=tuple(evidence_ids))


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def summarise(interactions: Sequence[StrategicInteraction]) -> dict:
    by_status: Dict[str, int] = {}
    for i in interactions:
        by_status[i.status] = by_status.get(i.status, 0) + 1
    responded = [i for i in interactions if i.response_lag_days is not None]
    return {"interactions": len(interactions), "by_status": by_status,
            "with_response": len(responded),
            "median_response_lag_days": _median(
                [i.response_lag_days for i in responded]),
            "actors_involved": len({i.responding_actor for i in interactions
                                    if i.responding_actor})}


def _median(values: List[Optional[int]]) -> Optional[float]:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    return float(clean[mid]) if len(clean) % 2 else \
        round((clean[mid - 1] + clean[mid]) / 2, 1)

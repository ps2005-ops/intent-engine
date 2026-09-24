"""Dynamic Bayesian updating, and the classification of what evidence did.

ARRIVAL IS NOT LEARNING
-----------------------
Section 10's last line is the reason this module exists rather than being an
inline formula. A cycle that counts rows and calls the total "learning" will
report 554 units of learning for a cycle that learned three things -- this
codebase has produced that exact number. So every update returns not just a
posterior but a NAMED EFFECT, and the effects that merely arrived are named
separately from the effects that moved something.

WHY THE UPDATE IS PRECISION-WEIGHTED
------------------------------------
A survey of 300 people and a payments panel of 40 million should not move a
posterior by the same amount, and a rule that averaged them would let the
weaker instrument dominate simply by being published more often. Combining
by precision (1/variance) is the smallest rule that gets that right, and it
has the property the ledger needs: uncertainty can only shrink when evidence
actually arrives, never as a side effect of restating a prior.

WHAT A CONTRADICTION IS
-----------------------
Not "the observation was low". A contradiction is an observation that sits
outside the posterior's credible band -- it is surprising given what we
believed. That distinction matters because a stream of mildly-low readings is
CONFIRMATION of a low state, and calling each one a contradiction is how a
belief ledger churns without learning.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from .collective import DimensionEstimate
from .vocabulary import (
    CONFIRMATION, CONTRADICTION, DUPLICATE_EVIDENCE, EVIDENCE_EFFECTS,
    INFORMATIVE_EFFECTS, NO_INFORMATION, STRENGTHENING, WEAKENING, require,
)

CONTRACT = "econ_bayes.v1"

#: How many posterior standard deviations away an observation must sit before
#: it counts as surprising rather than as more of the same.
CONTRADICTION_SIGMA = 2.0

#: A posterior move smaller than this is not a movement anyone can act on;
#: reporting it as learning is how a stagnant cycle looks busy.
NEGLIGIBLE_MOVE = 0.005


@dataclass(frozen=True)
class Observation:
    """One behavioural reading, already mapped onto a construct's 0-1 scale."""

    node_id: str
    value: float
    #: The instrument's own noise, as a standard deviation on the 0-1 scale.
    #: Not optional: an observation with no stated precision cannot be
    #: combined with another one except by pretending they are equally good.
    noise: float
    as_of: str
    publisher: str = ""

    def __post_init__(self) -> None:
        require(bool(self.node_id), "an observation names its evidence node")
        require(0.0 <= self.value <= 1.0,
                f"{self.node_id} value {self.value} is off the 0-1 construct "
                "scale; map it in the proxy, not here")
        require(self.noise > 0.0,
                f"{self.node_id} claims zero noise. No instrument is exact, "
                "and a zero here would let one reading pin the posterior "
                "forever.")

    @property
    def precision(self) -> float:
        return 1.0 / (self.noise ** 2)


@dataclass(frozen=True)
class Update:
    """What one batch of evidence did to one dimension."""

    dimension: str
    prior_mean: Optional[float]
    prior_uncertainty: float
    posterior_mean: float
    posterior_uncertainty: float
    effect: str
    explanation: str
    at: str
    evidence_nodes: Tuple[str, ...] = ()
    duplicate_nodes: Tuple[str, ...] = ()
    model_version: str = "collective-state-v1"

    def __post_init__(self) -> None:
        require(self.effect in EVIDENCE_EFFECTS,
                f"unknown evidence effect {self.effect!r}")

    @property
    def delta(self) -> Optional[float]:
        if self.prior_mean is None:
            return None
        return round(self.posterior_mean - self.prior_mean, 4)

    @property
    def uncertainty_delta(self) -> float:
        return round(self.posterior_uncertainty - self.prior_uncertainty, 4)

    @property
    def informative(self) -> bool:
        return self.effect in INFORMATIVE_EFFECTS

    def as_dict(self) -> dict:
        return {"dimension": self.dimension, "prior_mean": self.prior_mean,
                "prior_uncertainty": self.prior_uncertainty,
                "posterior_mean": self.posterior_mean,
                "posterior_uncertainty": self.posterior_uncertainty,
                "delta": self.delta,
                "uncertainty_delta": self.uncertainty_delta,
                "effect": self.effect, "informative": self.informative,
                "explanation": self.explanation, "at": self.at,
                "evidence_nodes": list(self.evidence_nodes),
                "duplicate_nodes": list(self.duplicate_nodes),
                "model_version": self.model_version}


def _classify(prior_mean: Optional[float], prior_sd: float,
              obs_mean: float, moved: float) -> Tuple[str, str]:
    """Name what the evidence did, before anyone can count it as learning."""
    if prior_mean is None:
        return (STRENGTHENING,
                "first evidence for this construct; the posterior is the "
                "observation, and there was no prior to contradict")
    z = abs(obs_mean - prior_mean) / prior_sd if prior_sd > 0 else 0.0
    if z >= CONTRADICTION_SIGMA:
        return (CONTRADICTION,
                f"observation sits {z:.1f} posterior sd from the prior; this "
                "is surprising given what was believed, not more of the same")
    if abs(moved) < NEGLIGIBLE_MOVE:
        return (CONFIRMATION,
                "the observation is where the prior expected it; belief is "
                "confirmed and the posterior did not need to move")
    if abs(obs_mean - 0.5) > abs(prior_mean - 0.5):
        return (STRENGTHENING,
                "the observation lies further from the midpoint than the "
                "prior; the reading is more pronounced, not merely repeated")
    return (WEAKENING,
            "the observation pulls the estimate toward the midpoint; the "
            "reading is less pronounced than it was")


def update(estimate: DimensionEstimate, observations: Sequence[Observation],
           *, at: str, seen_nodes: Sequence[str] = ()) -> Update:
    """Precision-weighted posterior, plus a name for what the evidence did.

    `seen_nodes` is what makes DUPLICATE_EVIDENCE a real category rather than
    a word in a docstring: a node already folded into this estimate is dropped
    from the update and reported separately, so it cannot be counted twice as
    either evidence or as learning.
    """
    require(bool(at), "an update is dated")
    already = set(seen_nodes) | set(estimate.evidence)
    fresh = [o for o in observations if o.node_id not in already]
    dupes = tuple(o.node_id for o in observations if o.node_id in already)

    prior_mean = estimate.posterior_mean
    prior_sd = estimate.uncertainty

    if not fresh:
        return Update(
            dimension=estimate.dimension, prior_mean=prior_mean,
            prior_uncertainty=prior_sd,
            posterior_mean=prior_mean if prior_mean is not None else 0.5,
            posterior_uncertainty=prior_sd,
            effect=DUPLICATE_EVIDENCE if dupes else NO_INFORMATION,
            explanation=(
                f"{len(dupes)} observation(s) had already been folded into "
                "this estimate; re-reading them is arrival, not learning"
                if dupes else
                "no observation in this batch measures this construct"),
            at=at, duplicate_nodes=dupes,
            model_version=estimate.model_version)

    # Precision-weighted combination of the fresh evidence.
    obs_precision = sum(o.precision for o in fresh)
    obs_mean = sum(o.value * o.precision for o in fresh) / obs_precision

    if prior_mean is None:
        post_mean = obs_mean
        post_sd = math.sqrt(1.0 / obs_precision)
    else:
        prior_precision = 1.0 / (prior_sd ** 2) if prior_sd > 0 else 1e6
        total = prior_precision + obs_precision
        post_mean = (prior_mean * prior_precision
                     + obs_mean * obs_precision) / total
        post_sd = math.sqrt(1.0 / total)

    post_mean = min(1.0, max(0.0, post_mean))
    post_sd = min(1.0, post_sd)
    moved = post_mean - (prior_mean if prior_mean is not None else post_mean)
    effect, why = _classify(prior_mean, prior_sd, obs_mean, moved)

    return Update(dimension=estimate.dimension, prior_mean=prior_mean,
                  prior_uncertainty=prior_sd,
                  posterior_mean=round(post_mean, 4),
                  posterior_uncertainty=round(post_sd, 4),
                  effect=effect, explanation=why, at=at,
                  evidence_nodes=tuple(o.node_id for o in fresh),
                  duplicate_nodes=dupes,
                  model_version=estimate.model_version)


def apply(estimate: DimensionEstimate, upd: Update) -> DimensionEstimate:
    """Fold an update into the estimate, keeping the prior visible.

    Contradictory evidence is RETAINED, not discarded. Section 5 requires
    `contradictory_evidence[]` on every estimate, and a posterior that has
    quietly absorbed the observations that disagreed with it is exactly the
    object that cannot later be audited.
    """
    from dataclasses import replace
    contra = estimate.contradictory_evidence
    if upd.effect == CONTRADICTION:
        contra = tuple(dict.fromkeys(contra + upd.evidence_nodes))
    if not upd.informative:
        return estimate
    return replace(
        estimate,
        prior_mean=estimate.posterior_mean,
        posterior_mean=upd.posterior_mean,
        uncertainty=upd.posterior_uncertainty,
        confidence=round(max(0.0, 1.0 - upd.posterior_uncertainty * 2), 3),
        evidence=tuple(dict.fromkeys(estimate.evidence + upd.evidence_nodes)),
        contradictory_evidence=contra)


def summarise(updates: Sequence[Update]) -> dict:
    """The counts a learning dashboard may print, with arrival separated out."""
    by_effect = {e: 0 for e in EVIDENCE_EFFECTS}
    for u in updates:
        by_effect[u.effect] += 1
    informative = [u for u in updates if u.informative]
    return {"updates": len(updates),
            "informative": len(informative),
            "arrived_without_informing": len(updates) - len(informative),
            "by_effect": by_effect,
            "mean_absolute_move": (
                round(sum(abs(u.delta) for u in informative
                          if u.delta is not None)
                      / max(1, sum(1 for u in informative
                                   if u.delta is not None)), 4)
                if informative else 0.0),
            "duplicate_nodes": sorted({n for u in updates
                                       for n in u.duplicate_nodes})}

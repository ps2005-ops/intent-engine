"""Causal bleeds: where a mechanism should have fired and did not.

WHAT A BLEED IS
---------------
Section 22. A conventional transmission -- lower rates raise credit demand --
is expected to move a quantity by some amount. It moves less, or not at all.
The gap is the bleed, and the interesting question is what absorbed it.

WHY THIS IS THE SYSTEM'S SHARPEST OUTPUT
----------------------------------------
Section 21: the engine is supposed to ATTACK consensus economic beliefs, not
restate them. Restating consensus is free and worthless -- the consensus is
already priced. A bleed is the only object here that can say "the textbook
chain is not firing, and here is the candidate reason, and here is the
preregistered prediction that would confirm it". Everything else in the
collective-state layer exists to make bleeds detectable.

WHY A CANDIDATE INTERRUPTION IS NOT AN EXPLANATION
--------------------------------------------------
The temptation is overwhelming and it is exactly the failure Section 7 warns
about: rates fell, demand did not respond, therefore fear. That is a story,
not a finding. So a bleed records the candidate as a CANDIDATE, requires a
falsifier, and requires that the candidate construct be measurable -- a bleed
attributed to a construct nobody can measure is unfalsifiable by construction
and is refused.

PRIORITY IS A PRODUCT, NOT A RANKING
------------------------------------
Section 22: loss x impact x controllability x confidence. All four, multiplied
rather than averaged, because a bleed that is enormous and uncontrollable is
not actionable and averaging would hide that behind the size.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .collective import CollectiveStateEstimate
from .construct import Construct
from .transmission import Chain
from .vocabulary import (
    COLLECTIVE_DIMENSIONS, PROMOTED, EconError, require,
)

CONTRACT = "econ_bleed.v1"

# --- how well established the bleed itself is -------------------------------
SUSPECTED = "SUSPECTED"      # the gap is measured; the cause is a guess
CANDIDATE_NAMED = "CANDIDATE_NAMED"   # a measurable construct is proposed
CORROBORATED = "CORROBORATED"         # the construct moved as the story needs
PREREGISTERED = "PREREGISTERED"       # a forward test is open
LEVELS = (SUSPECTED, CANDIDATE_NAMED, CORROBORATED, PREREGISTERED)

#: A gap smaller than this is measurement noise, not a bleed. Naming every
#: small miss a bleed is how a queue of "findings" becomes unreadable.
MIN_EFFICIENCY_LOSS = 0.15


class BleedRefused(EconError):
    """A bleed was proposed that could not be checked."""


@dataclass(frozen=True)
class CausalBleed:
    """One place a mechanism under-delivered, and what may have absorbed it."""

    bleed_id: str
    mechanism: str
    expected_transition: str
    source_state: str
    target_state: str
    observed_behavior: str
    expected_probability: float
    observed_probability: float
    #: Which collective construct is proposed as the interruption. Must be
    #: measurable, or the bleed is unfalsifiable.
    candidate_interruption: str
    falsifier: str
    as_of: str
    impact: float = 0.5
    controllability: float = 0.5
    confidence: float = 0.4
    level: str = SUSPECTED
    human_state_contribution: Optional[float] = None
    evidence_nodes: Tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        require(bool(self.bleed_id), "a bleed is identified")
        require(0.0 <= self.expected_probability <= 1.0,
                "expected transition probability is a probability")
        require(0.0 <= self.observed_probability <= 1.0,
                "observed transition probability is a probability")
        require(bool(self.falsifier.strip()),
                f"{self.bleed_id}: a bleed with no falsifier is a story about "
                "why the model was right all along")
        require(self.level in LEVELS, f"unknown bleed level {self.level!r}")
        for f in ("impact", "controllability", "confidence"):
            v = getattr(self, f)
            require(0.0 <= v <= 1.0, f"{f} is on 0-1")
        if self.candidate_interruption:
            require(self.candidate_interruption in COLLECTIVE_DIMENSIONS,
                    f"{self.bleed_id}: {self.candidate_interruption!r} is not "
                    "a declared construct. A bleed attributed to something "
                    "nobody measures cannot be confirmed or refuted, which "
                    "makes it an excuse rather than a finding.")
        elif self.level != SUSPECTED:
            raise BleedRefused(
                f"{self.bleed_id} is at level {self.level} but names no "
                "candidate interruption. Only a SUSPECTED bleed may be "
                "anonymous; naming a level above it without a candidate is "
                "claiming progress that has not happened.")

    @property
    def efficiency_loss(self) -> float:
        """How much of the expected transmission did not arrive."""
        if self.expected_probability <= 0:
            return 0.0
        gap = self.expected_probability - self.observed_probability
        return round(max(0.0, gap / self.expected_probability), 4)

    @property
    def material(self) -> bool:
        return self.efficiency_loss >= MIN_EFFICIENCY_LOSS

    @property
    def priority(self) -> float:
        """Section 22's product. All four factors, never averaged."""
        return round(self.efficiency_loss * self.impact
                     * self.controllability * self.confidence, 5)

    def statement(self) -> str:
        pct = f"{self.efficiency_loss:.0%}"
        head = (f"{self.mechanism}: expected {self.expected_probability:.2f}, "
                f"observed {self.observed_probability:.2f} — {pct} of the "
                f"expected transmission did not arrive")
        if not self.candidate_interruption:
            return (f"{head}. No candidate interruption has been named; the "
                    "gap is measured and unexplained.")
        who = self.candidate_interruption.replace("_", " ")
        if self.level == CORROBORATED:
            return (f"{head}. {who.capitalize()} moved as this account "
                    f"requires over the same window — consistent with it, "
                    f"not established by it.")
        if self.level == PREREGISTERED:
            return (f"{head}. {who.capitalize()} is the named candidate and a "
                    f"forward test is open: {self.falsifier}")
        return (f"{head}. {who.capitalize()} is proposed as the interruption "
                f"and has not yet been tested against it.")

    def as_dict(self) -> dict:
        return {"bleed_id": self.bleed_id, "mechanism": self.mechanism,
                "expected_transition": self.expected_transition,
                "source_state": self.source_state,
                "target_state": self.target_state,
                "observed_behavior": self.observed_behavior,
                "expected_probability": self.expected_probability,
                "observed_probability": self.observed_probability,
                "efficiency_loss": self.efficiency_loss,
                "material": self.material,
                "candidate_interruption": self.candidate_interruption,
                "human_state_contribution": self.human_state_contribution,
                "impact": self.impact,
                "controllability": self.controllability,
                "confidence": self.confidence, "priority": self.priority,
                "level": self.level, "falsifier": self.falsifier,
                "as_of": self.as_of, "evidence_nodes": list(self.evidence_nodes),
                "statement": self.statement(), "note": self.note}


def detect(*, chain: Chain, expected_probability: float,
           observed_probability: float, as_of: str,
           candidate_interruption: str = "", falsifier: str = "",
           impact: float = 0.5, controllability: float = 0.5,
           confidence: float = 0.4,
           evidence_nodes: Sequence[str] = ()) -> Optional[CausalBleed]:
    """A bleed against a declared chain, or None if the chain delivered.

    Returns None rather than a zero-loss bleed, because a queue containing
    every mechanism that worked is not a queue.
    """
    b = CausalBleed(
        bleed_id=f"bleed/{chain.name}@{as_of}",
        mechanism=chain.name,
        expected_transition=" -> ".join(chain.path),
        source_state=chain.path[0], target_state=chain.path[-1],
        observed_behavior=f"{chain.path[-1]} moved less than the chain implies",
        expected_probability=expected_probability,
        observed_probability=observed_probability,
        candidate_interruption=candidate_interruption,
        falsifier=falsifier or (
            f"{chain.path[-1]} moves as the chain implies over the next "
            f"{chain.total_lag_days} days with no change in "
            f"{candidate_interruption or 'any collective construct'}"),
        as_of=as_of, impact=impact, controllability=controllability,
        confidence=confidence, evidence_nodes=tuple(evidence_nodes))
    return b if b.material else None


def corroborate(b: CausalBleed, *, state: CollectiveStateEstimate,
                register: Sequence[Construct] = ()) -> CausalBleed:
    """Did the named construct actually move the way the account requires?

    Raises the bleed to CORROBORATED only when the construct is PROMOTED and
    its posterior moved in the direction the story needs. A construct that is
    merely present, or merely CANDIDATE, does not corroborate anything --
    which is the whole reason the register is a parameter here.
    """
    from dataclasses import replace
    if not b.candidate_interruption:
        return b
    by_dim = {c.dimension: c for c in register}
    c = by_dim.get(b.candidate_interruption)
    if c is None or c.state != PROMOTED:
        return replace(b, level=CANDIDATE_NAMED, note=(
            f"{b.candidate_interruption} is "
            f"{c.state if c else 'not in the register'}; only a PROMOTED "
            "construct may corroborate a bleed, because an untested "
            "construct explains everything equally well"))
    est = state.dimension(b.candidate_interruption)
    moved = est.moved
    if moved is None or not est.usable:
        return replace(b, level=CANDIDATE_NAMED, note=(
            f"{b.candidate_interruption} has no usable movement this cycle; "
            "the account is untested rather than unsupported"))
    # The interruption must have STRENGTHENED for it to absorb transmission.
    if moved <= 0:
        return replace(b, level=CANDIDATE_NAMED,
                       human_state_contribution=0.0, note=(
            f"{b.candidate_interruption} moved {moved:+.4f} — the wrong way "
            "for this account. The gap is real and this explanation is not "
            "supported by it."))
    return replace(b, level=CORROBORATED,
                   human_state_contribution=round(min(1.0, moved * 2), 4),
                   note=(f"{b.candidate_interruption} rose {moved:+.4f} over "
                         "the same window; consistent with the account, and "
                         "not by itself evidence of it"))


def queue(bleeds: Sequence[CausalBleed], *, limit: int = 10) -> List[dict]:
    ranked = sorted((b for b in bleeds if b.material),
                    key=lambda b: b.priority, reverse=True)
    return [b.as_dict() for b in ranked[:limit]]


def summarise(bleeds: Sequence[CausalBleed]) -> dict:
    material = [b for b in bleeds if b.material]
    by_level = {l: sum(1 for b in material if b.level == l) for l in LEVELS}
    named = [b for b in material if b.candidate_interruption]
    return {"contract": CONTRACT, "detected": len(bleeds),
            "material": len(material),
            "immaterial": len(bleeds) - len(material),
            "by_level": by_level,
            "with_named_candidate": len(named),
            "unexplained": len(material) - len(named),
            "top": queue(material, limit=5),
            "mean_efficiency_loss": (
                round(sum(b.efficiency_loss for b in material)
                      / len(material), 4) if material else 0.0)}

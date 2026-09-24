"""Learning Value — what an evaluation is actually worth to the engine.

WHY LEARNING VELOCITY WAS REPLACED
----------------------------------
LV counted resolvable evaluations. It correctly identified the right build for
one cycle and then failed its own integrity test the next day: ten companies
moving inside the noise floor scored LV 0 at the shipped threshold and LV 10
after a one-character edit to `MIN_ABS_RETURN`. Same evidence, same reasoning,
same prices — a 10x metric gain for a system that had become *worse*, because
it would now be making ten confident predictions about noise.

A count of resolvable records also cannot tell these apart:

  A. 100 predictions at 51% accuracy, every one a momentum trade
  B.  20 well-calibrated predictions that each taught something new

LV scores A five times higher. B is obviously the better engine.

WHAT REPLACES IT, AND WHAT DELIBERATELY DOES NOT
------------------------------------------------
Learning Value weights each evaluation by resolution quality, information
gain, novelty and calibration impact. **Three of those four cannot be measured
today** — zero predictions have resolved, there is no knowledge base, and
calibration is gated behind `A-M5` until at least thirty resolutions exist.

They are therefore NOT estimated. A multiplicative score assembled from
self-assigned factors is not a measurement; it is a number its author controls
completely, wearing the costume of rigour — and it would fail the metric-
integrity test far more badly than the metric it replaced, because moving LV
at least costs a code edit whereas moving an estimated factor costs an
opinion.

So an unmeasurable factor returns `UNMEASURABLE`, and `LearningValue.score`
refuses to produce a number while any factor is in that state. It reports what
it can measure and names what it cannot. **A metric that declines to score
itself is behaving correctly.**

NOVELTY IS MEASURABLE TODAY, AND IT IS THE URGENT ONE
-----------------------------------------------------
It is the factor that guards against exactly failure mode A, and it is already
relevant: `baseline_momentum.v1` produces one shape of prediction — "up
because it went up". The tenth such trade teaches almost nothing the first
taught. Measuring novelty now means the baseline's real contribution is
visible before volume is mistaken for learning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# A factor that cannot honestly be computed yet. Distinct from 0.0, which is a
# measurement meaning "this taught nothing". Conflating them is how an
# unmeasured system starts looking like a well-understood one.
UNMEASURABLE = None

# What makes two predictions "the same lesson": same signal, same direction,
# same company. A second identical row is a duplicate observation of a rule
# already being tested, not a new test.
_NOVELTY_KEYS = ("market_source", "direction", "company_id")


def novelty(evaluation: Dict[str, Any],
            prior: Sequence[Dict[str, Any]]) -> float:
    """How much of this evaluation the engine has not already seen. 0.0–1.0.

    **Diminishing returns within a shape.** The first test of a rule teaches a
    great deal; the fiftieth teaches almost nothing. Credit therefore decays
    harmonically in the number of times that shape has already been tried:

        novelty = 1 / (1 + k)      k = prior evaluations of the same shape

    Harmonic because that is how repeated sampling of one hypothesis actually
    behaves — each additional observation shrinks the remaining uncertainty by
    a smaller fraction — not because it produces a preferred answer. Sum over
    n identical shapes grows like ln(n), so a hundred repeats are worth roughly
    five first-attempts rather than a hundred.

    A first attempt at a genuinely exact repeat (same signal, same direction,
    same company) decays twice as fast again: it adds a calibration sample and
    no new coverage.

    Never zero. A repeated trade does add a sample to a calibration curve; it
    just must not be counted as though it added a lesson.
    """
    source = evaluation.get("market_source") or ""
    direction = evaluation.get("direction") or ""
    company = evaluation.get("company_id") or ""

    shape_seen = sum(
        1 for p in prior
        if (p.get("market_source") or "") == source
        and (p.get("direction") or "") == direction)
    if not shape_seen:
        return 1.0

    exact_seen = sum(
        1 for p in prior
        if (p.get("market_source") or "") == source
        and (p.get("direction") or "") == direction
        and (p.get("company_id") or "") == company)

    decayed = 1.0 / (1 + shape_seen)
    if exact_seen:
        # the same rule, on the same company, again
        decayed /= (1 + exact_seen)
    return round(max(decayed, 0.01), 4)


def resolution_quality(evaluation: Dict[str, Any]) -> Optional[float]:
    """Was there a clean, trustworthy outcome? Unmeasurable until one exists."""
    outcome = evaluation.get("outcome")
    if outcome is None:
        return UNMEASURABLE
    # A resolved outcome with a price the market actually printed is clean; one
    # resolved by timeout or with a missing price is not.
    if evaluation.get("resolution_note") == "no_price":
        return 0.2
    return 1.0 if outcome in ("happened", "did_not_happen") else 0.5


def information_gain(evaluation: Dict[str, Any],
                     knowledge: Sequence[Dict[str, Any]] = ()) -> Optional[float]:
    """Did this change what the engine knows?

    Unmeasurable until resolved outcomes and a knowledge base exist. It is NOT
    approximated by "did we write a lesson down" — that would measure diligence
    at note-taking, not knowledge.
    """
    if evaluation.get("outcome") is None:
        return UNMEASURABLE
    return UNMEASURABLE


def calibration_impact(evaluation: Dict[str, Any]) -> Optional[float]:
    """Did this improve confidence calibration?

    Unmeasurable, and gated: `A-M5` forbids accuracy claims before >=30
    live-resolved predictions per source plus a human calibration review.
    Computing this earlier would produce exactly the claim that gate exists to
    prevent.
    """
    return UNMEASURABLE


@dataclass(frozen=True)
class LearningValue:
    """The value of one evaluation, or an honest statement that it is unknown."""
    novelty: float
    resolution_quality: Optional[float] = None
    information_gain: Optional[float] = None
    calibration_impact: Optional[float] = None
    missing: tuple = ()

    @property
    def is_measurable(self) -> bool:
        return not self.missing

    @property
    def score(self) -> Optional[float]:
        """The product — or None while any factor is unmeasurable.

        Returning a partial product would silently treat "unknown" as 1.0,
        which is the single most dangerous default available here: it makes an
        unmeasured system score identically to a perfectly-understood one.
        """
        if not self.is_measurable:
            return None
        total = 1.0
        for factor in (self.novelty, self.resolution_quality,
                       self.information_gain, self.calibration_impact):
            total *= float(factor)
        return round(total, 4)

    def as_dict(self) -> dict:
        return {"novelty": self.novelty,
                "resolution_quality": self.resolution_quality,
                "information_gain": self.information_gain,
                "calibration_impact": self.calibration_impact,
                "score": self.score, "missing": list(self.missing)}


def learning_value(evaluation: Dict[str, Any],
                   prior: Sequence[Dict[str, Any]] = (),
                   knowledge: Sequence[Dict[str, Any]] = ()) -> LearningValue:
    factors = {
        "resolution_quality": resolution_quality(evaluation),
        "information_gain": information_gain(evaluation, knowledge),
        "calibration_impact": calibration_impact(evaluation),
    }
    missing = tuple(sorted(k for k, v in factors.items() if v is UNMEASURABLE))
    return LearningValue(novelty=novelty(evaluation, prior),
                         missing=missing, **factors)


def assess_cycle(evaluations: Sequence[Dict[str, Any]]) -> dict:
    """What a cycle's evaluations were worth, reported honestly.

    Resolvable count is kept — it is still a useful diagnostic — but it is
    reported ALONGSIDE novelty rather than as the headline, because on its own
    it scores a noise-predicting system higher than a careful one.
    """
    resolvable: List[Dict[str, Any]] = [
        e for e in evaluations
        if e.get("classification") in ("BUY", "SELL")]

    seen: List[Dict[str, Any]] = []
    values = []
    for evaluation in resolvable:
        values.append(learning_value(evaluation, prior=list(seen)))
        seen.append(evaluation)

    novelty_total = round(sum(v.novelty for v in values), 3)
    missing = sorted({m for v in values for m in v.missing})
    return {
        "evaluations": len(evaluations),
        "resolvable": len(resolvable),
        # The headline. Ten repeats of one momentum trade sum to 1.9, not 10.
        "novelty_weighted": novelty_total,
        "distinct_shapes": len({
            (e.get("market_source"), e.get("direction")) for e in resolvable}),
        "learning_value": (None if missing else
                           round(sum(v.score or 0 for v in values), 4)),
        "unmeasurable_factors": missing,
        "why_unscored": (
            "Learning Value is unscored while these factors cannot be "
            "measured; reporting a partial product would treat unknown as 1.0 "
            "and make an unmeasured system score like a understood one."
            if missing else ""),
    }

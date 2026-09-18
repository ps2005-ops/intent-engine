"""Collective human state: what a POPULATION appears to be feeling and doing.

WHY THIS IS A SEPARATE STATE FAMILY
-----------------------------------
Section 3 draws a line this module exists to hold: credit stress is not fear,
and market volatility is not anxiety. They may turn out to be causally linked
-- that is Section 18's question, answered by measurement -- but they are
different objects and they are estimated from different evidence. The moment
"fear" is allowed to be a synonym for "the VIX", the engine loses the only
interesting question it could have asked, which is whether people knew
something the aggregates had not yet shown.

So `CollectiveStateEstimate` is not an `EconomicState` with different field
names. It carries things an economic reading does not: a POPULATION, a SCALE,
a LAG MODEL, and a posterior with an uncertainty attached to it.

WHY EVERY ESTIMATE NAMES A POPULATION
-------------------------------------
Section 6. "The market is fearful" is not a state; it is a sentence with no
subject. Fear among first-time homebuyers, fear among hedge funds and fear
among bank risk officers are three different estimates supported by three
different bodies of evidence, and an engine that collapses them will report
that "people" are afraid on the strength of a survey of one of them.

WHY THE RENDERING RULE IS CODE
------------------------------
Section 5 forbids "Americans are 73% afraid". That prohibition cannot live in
a style guide, because the number is right there in the dataclass and the
sentence writes itself. `narrate()` is the only supported way to turn an
estimate into prose, and it refuses to emit a bare percentage of a population.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not decide whether any of these dimensions are worth keeping. That is
`incremental.py`, and until a dimension has passed it, `promotion_state`
reads CANDIDATE and the dashboard says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import (
    CANDIDATE, COLLECTIVE_DIMENSIONS, COLLECTIVE_STATES, CONTRACT_COLLECTIVE,
    PRIVATE_SCALES, PUBLIC, SCALES, CollectiveStateViolation,
    UnsupportedInference, require,
)

CONTRACT = CONTRACT_COLLECTIVE

#: Directional readings for a dimension that has no natural 0-1 level.
#: `time_horizon` is the motivating case: "0.41" says nothing, "SHORTENING"
#: says the thing a decision depends on.
LENGTHENING, SHORTENING, STEADY = "LENGTHENING", "SHORTENING", "STEADY"
TRENDS = (LENGTHENING, SHORTENING, STEADY)

#: Above this, an estimate is too uncertain to support any claim at all. Not a
#: style choice: an estimate with an uncertainty this wide is consistent with
#: the opposite reading, and saying anything directional about it is the
#: false-precision failure with extra steps.
UNUSABLE_UNCERTAINTY = 0.30


# =============================================================================
# POPULATION
# =============================================================================

@dataclass(frozen=True)
class Population:
    """WHO, WHERE and in WHAT CONTEXT (Section 6).

    A population with no scale is refused. So is an INDIVIDUAL scale, in this
    package, always -- Section 52 keeps individual state inside a tenant, and
    the enforcement is that the public core cannot construct one.
    """

    name: str
    scale: str
    geography: str = "US"
    #: What narrows this population inside its scale: "first_time_buyers",
    #: "sub_640_fico", "manufacturing". Empty means the whole scale.
    cohort: str = ""
    context: str = ""

    def __post_init__(self) -> None:
        require(bool(self.name), "a population is named")
        require(self.scale in SCALES,
                f"unknown scale {self.scale!r}; known: {SCALES}")
        if self.scale in PRIVATE_SCALES:
            raise CollectiveStateViolation(
                f"{self.name!r} is at scale {self.scale}, which the public "
                "world model may not hold. An individual's state is a "
                "Personal-AI object inside one tenant (Section 52); the "
                "public core refuses to build one rather than trusting its "
                "caller not to ask for one.")
        require(bool(self.geography), "a population is somewhere")

    @property
    def key(self) -> str:
        return "/".join(p for p in (self.geography, self.scale, self.name,
                                    self.cohort) if p)

    def as_dict(self) -> dict:
        return {"name": self.name, "scale": self.scale,
                "geography": self.geography, "cohort": self.cohort,
                "context": self.context, "key": self.key}


def population(name: str, scale: str, **kw) -> Population:
    return Population(name=name, scale=scale, **kw)


# =============================================================================
# LAG MODEL
# =============================================================================

@dataclass(frozen=True)
class LagModel:
    """How long after the world moves does this population's state move.

    Section 5 requires it on every estimate, and the reason is Section 18:
    an incremental-value test run at the wrong lag will find nothing and
    retire a dimension that was real. The lag is part of the hypothesis.
    """

    typical_days: int
    lower_days: int
    upper_days: int
    basis: str = ""

    def __post_init__(self) -> None:
        require(self.lower_days <= self.typical_days <= self.upper_days,
                f"incoherent lag band [{self.lower_days}, {self.typical_days},"
                f" {self.upper_days}]")
        require(self.lower_days >= 0, "a lag is not negative; a state that "
                                      "moves before its cause is a leak")

    def as_dict(self) -> dict:
        return {"typical_days": self.typical_days,
                "lower_days": self.lower_days, "upper_days": self.upper_days,
                "basis": self.basis}


UNKNOWN_LAG = LagModel(typical_days=30, lower_days=0, upper_days=90,
                       basis="not yet estimated; band is deliberately wide")


# =============================================================================
# ONE DIMENSION'S ESTIMATE
# =============================================================================

@dataclass(frozen=True)
class DimensionEstimate:
    """A posterior over one candidate construct, for one population.

    `posterior_mean` is on 0-1 and means "where in this construct's range does
    this population currently sit", NOT "what fraction of them feel it". The
    distinction is the whole of Section 5's rendering rule, and it is why
    `narrate()` exists and `f"{mean:.0%}"` is a bug.
    """

    dimension: str
    posterior_mean: Optional[float]
    uncertainty: float
    #: Directional reading, for constructs where a level is meaningless.
    trend: str = ""
    confidence: float = 0.0
    prior_mean: Optional[float] = None
    evidence: Tuple[str, ...] = ()
    contradictory_evidence: Tuple[str, ...] = ()
    lag_model: LagModel = UNKNOWN_LAG
    promotion_state: str = CANDIDATE
    model_version: str = "collective-state-v1"

    def __post_init__(self) -> None:
        require(self.dimension in COLLECTIVE_DIMENSIONS,
                f"{self.dimension!r} is not a declared collective dimension; "
                f"a construct nobody declared cannot be tested or retired")
        require(self.promotion_state in COLLECTIVE_STATES,
                f"unknown promotion state {self.promotion_state!r}")
        if self.trend:
            require(self.trend in TRENDS, f"unknown trend {self.trend!r}")
        if self.posterior_mean is not None:
            require(0.0 <= self.posterior_mean <= 1.0,
                    f"{self.dimension} posterior {self.posterior_mean} is off "
                    "the 0-1 scale the construct is defined on")
        require(0.0 <= self.uncertainty <= 1.0,
                f"uncertainty {self.uncertainty} is not a standard deviation "
                "on a 0-1 construct")
        require(0.0 <= self.confidence <= 1.0, "confidence is a probability")
        if self.posterior_mean is None and not self.trend:
            raise CollectiveStateViolation(
                f"{self.dimension} states neither a level nor a trend. An "
                "estimate that says nothing is not an estimate; use "
                "`unmeasured()` so the absence is legible as an absence.")
        if self.posterior_mean is not None and not self.evidence:
            raise CollectiveStateViolation(
                f"{self.dimension} carries a posterior of "
                f"{self.posterior_mean} and names no evidence. A number with "
                "no evidence behind it is the thing this package exists to "
                "refuse.")

    @property
    def usable(self) -> bool:
        """Wide enough to be consistent with the opposite reading?"""
        return self.uncertainty <= UNUSABLE_UNCERTAINTY

    @property
    def contested(self) -> bool:
        return bool(self.contradictory_evidence)

    @property
    def moved(self) -> Optional[float]:
        if self.posterior_mean is None or self.prior_mean is None:
            return None
        return round(self.posterior_mean - self.prior_mean, 4)

    def as_dict(self) -> dict:
        return {"dimension": self.dimension,
                "posterior_mean": self.posterior_mean,
                "uncertainty": self.uncertainty, "trend": self.trend,
                "confidence": self.confidence, "prior_mean": self.prior_mean,
                "moved": self.moved,
                "evidence": list(self.evidence),
                "contradictory_evidence": list(self.contradictory_evidence),
                "lag_model": self.lag_model.as_dict(),
                "promotion_state": self.promotion_state,
                "model_version": self.model_version,
                "usable": self.usable, "contested": self.contested}


def unmeasured(dimension: str, reason: str) -> DimensionEstimate:
    """An absence that reads as an absence.

    Deliberately given trend=STEADY *and* a maximal uncertainty rather than a
    posterior of 0.5, because 0.5 renders as a real reading and this is not
    one. `usable` is False, so nothing downstream can rest on it.
    """
    require(bool(reason), "an absence states what is missing")
    return DimensionEstimate(dimension=dimension, posterior_mean=None,
                             uncertainty=1.0, trend=STEADY, confidence=0.0,
                             evidence=(), model_version="unmeasured")


# =============================================================================
# THE ESTIMATE
# =============================================================================

@dataclass(frozen=True)
class CollectiveStateEstimate:
    """One population's collective state, as of one date."""

    population: Population
    as_of: str
    dimensions: Dict[str, DimensionEstimate] = field(default_factory=dict)
    #: Which BEHAVIORAL evidence nodes this whole estimate was built from.
    source_nodes: Tuple[str, ...] = ()
    model_version: str = "collective-state-v1"
    visibility: str = PUBLIC
    provenance: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require(bool(self.as_of), "a collective state is dated")
        for name, est in self.dimensions.items():
            if name != est.dimension:
                raise CollectiveStateViolation(
                    f"dimension filed under {name!r} calls itself "
                    f"{est.dimension!r}")

    @property
    def key(self) -> str:
        return f"{self.population.key}@{self.as_of}"

    def dimension(self, name: str) -> DimensionEstimate:
        """Never a KeyError. An unmeasured dimension is an estimate too."""
        return self.dimensions.get(name) or unmeasured(
            name, "no behavioural evidence in this cycle measures it")

    @property
    def measured(self) -> List[str]:
        return sorted(n for n, e in self.dimensions.items()
                      if e.posterior_mean is not None)

    @property
    def usable_dimensions(self) -> List[str]:
        return sorted(n for n, e in self.dimensions.items() if e.usable
                      and e.posterior_mean is not None)

    @property
    def promoted_dimensions(self) -> List[str]:
        from .vocabulary import PROMOTED
        return sorted(n for n, e in self.dimensions.items()
                      if e.promotion_state == PROMOTED)

    @property
    def coverage(self) -> dict:
        total = len(COLLECTIVE_DIMENSIONS)
        return {"measured": len(self.measured), "vocabulary": total,
                "usable": len(self.usable_dimensions),
                "promoted": len(self.promoted_dimensions),
                "coverage": round(len(self.measured) / total, 3),
                "unmeasured": sorted(set(COLLECTIVE_DIMENSIONS)
                                     - set(self.measured))}

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "as_of": self.as_of,
                "population": self.population.as_dict(),
                "key": self.key,
                "dimensions": {n: e.as_dict()
                               for n, e in sorted(self.dimensions.items())},
                "source_nodes": list(self.source_nodes),
                "coverage": self.coverage,
                "model_version": self.model_version,
                "visibility": self.visibility,
                "provenance": dict(self.provenance)}


def build(*, population: Population, as_of: str,
          dimensions: Sequence[DimensionEstimate] = (),
          source_nodes: Sequence[str] = (),
          provenance: Optional[dict] = None) -> CollectiveStateEstimate:
    return CollectiveStateEstimate(
        population=population, as_of=as_of,
        dimensions={d.dimension: d for d in dimensions},
        source_nodes=tuple(source_nodes),
        provenance=dict(provenance or {}))


# =============================================================================
# RENDERING (Section 5)
# =============================================================================

#: Sentence shapes that turn a posterior into a claim about how many people
#: feel something. Checked against the OUTPUT of narrate(), not its input,
#: because the failure is a rendering failure.
_FORBIDDEN_RENDERINGS = (
    "% afraid", "% of americans", "% are afraid", "percent are",
    "% of the population", "% of people", "% feel",
)

_PHRASE = {
    "financial_anxiety": ("financial anxiety", "rising", "easing"),
    "perceived_control": ("perceived control over their finances",
                          "improving", "deteriorating"),
    "institutional_trust": ("trust in institutions", "recovering", "eroding"),
    "interpersonal_trust": ("trust in one another", "recovering", "eroding"),
    "hope": ("hopefulness", "rising", "fading"),
    "anger": ("expressed anger", "rising", "cooling"),
    "stress": ("stress", "rising", "easing"),
    "agency": ("sense of agency", "strengthening", "weakening"),
    "belonging": ("sense of belonging", "strengthening", "weakening"),
    "risk_appetite": ("appetite for risk", "increasing", "retreating"),
    "time_horizon": ("planning horizon", "lengthening", "shortening"),
    "certainty": ("certainty about the near future", "firming", "fraying"),
    "perceived_security": ("sense of financial security",
                           "improving", "deteriorating"),
    "perceived_fairness": ("sense that outcomes are fair",
                           "improving", "deteriorating"),
    "willingness_to_experiment": ("willingness to try new things",
                                  "increasing", "narrowing"),
    "future_orientation": ("orientation toward the future",
                           "lengthening", "shortening"),
}

_BAND = ((0.30, "little"), (0.45, "subdued"), (0.55, "middling"),
         (0.70, "elevated"), (1.01, "high"))


def _band(mean: float) -> str:
    for ceiling, word in _BAND:
        if mean < ceiling:
            return word
    return "high"


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


def _hedge(est: DimensionEstimate) -> str:
    if est.uncertainty <= 0.08:
        return "with narrow uncertainty"
    if est.uncertainty <= 0.15:
        return "with moderate uncertainty"
    return "with wide uncertainty"


def narrate(est: DimensionEstimate, pop: Population) -> str:
    """The ONLY supported way to render a dimension as prose.

    Section 5's rule, as a function: the sentence says what the evidence is
    consistent with, names the population, and carries the uncertainty. It
    never says a percentage of people feel a thing, because the posterior is
    not a headcount.
    """
    if not est.usable or est.posterior_mean is None:
        return (f"Available evidence does not support a reading of "
                f"{_PHRASE.get(est.dimension, (est.dimension,))[0]} among "
                f"{pop.name.replace('_', ' ')}.")
    label, up, down = _PHRASE.get(
        est.dimension, (est.dimension.replace("_", " "), "rising", "easing"))
    moved = est.moved
    # A participle, not a finite verb: the sentence frame is "consistent with
    # X rising", and "consistent with X is rising" is what an f-string writes
    # if nobody reads the output.
    if moved is None:
        motion = f"at {_article(_band(est.posterior_mean))} {_band(est.posterior_mean)} level"
    elif abs(moved) < 0.02:
        motion = f"stable at {_article(_band(est.posterior_mean))} {_band(est.posterior_mean)} level"
    else:
        motion = up if moved > 0 else down
    who = pop.name.replace("_", " ")
    # Only add the geography when the population's own name does not already
    # carry it, or the reading comes out as "US households in US".
    place = ("" if pop.geography.lower() in who.lower()
             else f" in {pop.geography}")
    cohort = f" ({pop.cohort.replace('_', ' ')})" if pop.cohort else ""
    sentence = (f"Available behavioural evidence is consistent with {label} "
                f"{motion} among {who}{cohort}{place}, {_hedge(est)}.")
    assert_renderable(sentence)
    return sentence


def assert_renderable(text: str) -> None:
    """Refuse a sentence that turns a posterior into a headcount."""
    low = text.lower()
    for bad in _FORBIDDEN_RENDERINGS:
        if bad in low:
            raise UnsupportedInference(
                f"rendering says {bad!r}: {text!r}. A posterior over a "
                "construct is not the fraction of a population that feels it "
                "(Section 5). Use narrate().")


def summarise(est: CollectiveStateEstimate) -> dict:
    """What a dashboard prints. Prose comes from narrate(), never from f-strings."""
    lines = []
    for name in est.usable_dimensions:
        lines.append({"dimension": name,
                      "sentence": narrate(est.dimensions[name],
                                          est.population),
                      "promotion_state": est.dimensions[name].promotion_state,
                      "moved": est.dimensions[name].moved})
    return {"population": est.population.as_dict(), "as_of": est.as_of,
            "coverage": est.coverage, "readings": lines,
            "unusable": sorted(set(est.measured) - set(est.usable_dimensions))}

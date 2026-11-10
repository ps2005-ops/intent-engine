"""§24: a counterfactual must say what kind of claim it is making.

THE ERROR THIS PREVENTS
-----------------------
"If rates had stayed at 2%, housing turnover would have been 18% higher."

That sentence is read as a fact about the world. It might be any of three
completely different things:

    CAUSAL_ESTIMATE        an identified effect, with a design behind it
    STRUCTURAL_SIMULATION  a model's output under stated assumptions
    SCENARIO_ASSUMPTION    a hypothetical somebody typed in

They differ by orders of magnitude in what they license, and once rendered
they are indistinguishable. So the label is not metadata attached to the
sentence -- it is part of the sentence, and `statement()` is the only
supported way to produce one.

WHY THE LABEL CANNOT BE ERASED
------------------------------
A renderer that drops the label turns a scenario into a finding. So:

  - every `Counterfactual` carries a type, and there is no default
  - `statement()` emits the label inline, not as a suffix a caller may trim
  - `assert_labelled()` scans finished prose and refuses counterfactual
    grammar that carries none of the three markers
  - CAUSAL_ESTIMATE additionally requires an identification strategy and an
    evidence level at or above the causal-language floor, so the strongest
    label is the hardest to obtain rather than the default

WHY A MAGNITUDE IS OPTIONAL AND A DIRECTION IS NOT
---------------------------------------------------
"Turnover would have been higher" is defensible from a sign-identified
mechanism. "18% higher" needs a magnitude the evidence usually cannot
support. A counterfactual may therefore state a direction with no number, and
`magnitude` on a SCENARIO_ASSUMPTION is refused outright -- a made-up
scenario with a precise number is the most misleading object in the system.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from .causal import CAUSAL_LANGUAGE_FLOOR, LEVEL_NAMES
from .vocabulary import EconError, require

CONTRACT = "econ_counterfactual.v1"

CAUSAL_ESTIMATE = "CAUSAL_ESTIMATE"
STRUCTURAL_SIMULATION = "STRUCTURAL_SIMULATION"
SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
TYPES = (CAUSAL_ESTIMATE, STRUCTURAL_SIMULATION, SCENARIO_ASSUMPTION)

#: The marker each type must put into rendered prose. Deliberately verbose:
#: a one-letter code would be trimmed by the first renderer that wanted a
#: tidier line.
MARKERS = {
    CAUSAL_ESTIMATE: "[CAUSAL ESTIMATE]",
    STRUCTURAL_SIMULATION: "[STRUCTURAL SIMULATION]",
    SCENARIO_ASSUMPTION: "[SCENARIO ASSUMPTION]",
}

#: What each type licenses a reader to do, in one clause each.
LICENCE = {
    CAUSAL_ESTIMATE: "an identified effect; may inform a decision about "
                     "changing the cause",
    STRUCTURAL_SIMULATION: "a model's output under stated assumptions; only "
                           "as good as the assumptions, which are listed",
    SCENARIO_ASSUMPTION: "a hypothesis somebody proposed; carries no evidence "
                         "at all and must not be read as a finding",
}

UP, DOWN, UNCHANGED = "HIGHER", "LOWER", "UNCHANGED"
DIRECTIONS = (UP, DOWN, UNCHANGED)


class MislabelledCounterfactual(EconError):
    """A counterfactual claimed more than its evidence licenses."""


class UnlabelledCounterfactual(EconError):
    """Counterfactual prose reached a surface with no type marker."""


@dataclass(frozen=True)
class Counterfactual:
    """One 'what if', with the kind of claim it is making attached."""

    question: str
    #: What is being varied, and to what.
    intervention: str
    outcome: str
    direction: str
    cf_type: str
    as_of: str
    #: Required for CAUSAL_ESTIMATE: what makes the effect identified rather
    #: than merely observed.
    identification: str = ""
    evidence_level: int = 0
    #: Required for STRUCTURAL_SIMULATION: what the model assumed.
    assumptions: Tuple[str, ...] = ()
    magnitude: Optional[float] = None
    magnitude_unit: str = ""
    uncertainty: str = ""
    evidence_nodes: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(self.cf_type in TYPES,
                f"unknown counterfactual type {self.cf_type!r}; there is no "
                "default, because a default is what a caller reaches for "
                "when they have not thought about which claim they are making")
        require(self.direction in DIRECTIONS,
                f"unknown direction {self.direction!r}")
        require(bool(self.question.strip()), "a counterfactual asks something")
        require(bool(self.intervention.strip()),
                "a counterfactual names what is being varied")

        if self.cf_type == CAUSAL_ESTIMATE:
            require(bool(self.identification.strip()),
                    f"{self.question!r} claims CAUSAL_ESTIMATE and names no "
                    "identification strategy. Without one this is an "
                    "observed association with a stronger word on it.")
            require(self.evidence_level >= CAUSAL_LANGUAGE_FLOOR,
                    f"{self.question!r} claims CAUSAL_ESTIMATE at evidence "
                    f"level {self.evidence_level}; the floor is "
                    f"{CAUSAL_LANGUAGE_FLOOR} "
                    f"({LEVEL_NAMES[CAUSAL_LANGUAGE_FLOOR]}). The strongest "
                    "label must be the hardest to obtain.")
        if self.cf_type == STRUCTURAL_SIMULATION:
            require(bool(self.assumptions),
                    f"{self.question!r} is a STRUCTURAL_SIMULATION and lists "
                    "no assumptions. A simulation is exactly as good as its "
                    "assumptions, so unlisted ones make it unauditable.")
        if self.cf_type == SCENARIO_ASSUMPTION:
            require(self.magnitude is None,
                    f"{self.question!r} is a SCENARIO_ASSUMPTION carrying a "
                    f"magnitude of {self.magnitude}. A hypothesis nobody "
                    "measured, stated to a decimal place, is the most "
                    "misleading object this package can produce.")
            require(self.evidence_level == 0,
                    "a scenario carries no evidence; an evidence level on one "
                    "is a claim it cannot support")

    @property
    def marker(self) -> str:
        return MARKERS[self.cf_type]

    @property
    def may_inform_intervention(self) -> bool:
        """Only an identified effect licenses acting on the cause."""
        return self.cf_type == CAUSAL_ESTIMATE

    def statement(self) -> str:
        """The ONLY supported rendering. The marker is inline, not a suffix."""
        move = {UP: "higher", DOWN: "lower",
                UNCHANGED: "unchanged"}[self.direction]
        if self.magnitude is not None and self.direction != UNCHANGED:
            amount = f" by about {self.magnitude}{self.magnitude_unit}"
        else:
            amount = ""
        tail = f" ({self.uncertainty})" if self.uncertainty else ""
        return (f"{self.marker} Had {self.intervention}, {self.outcome} "
                f"would have been {move}{amount}{tail}.")

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "question": self.question,
                "intervention": self.intervention, "outcome": self.outcome,
                "direction": self.direction, "cf_type": self.cf_type,
                "marker": self.marker, "licence": LICENCE[self.cf_type],
                "may_inform_intervention": self.may_inform_intervention,
                "identification": self.identification,
                "evidence_level": self.evidence_level,
                "assumptions": list(self.assumptions),
                "magnitude": self.magnitude,
                "magnitude_unit": self.magnitude_unit,
                "uncertainty": self.uncertainty, "as_of": self.as_of,
                "evidence_nodes": list(self.evidence_nodes),
                "statement": self.statement()}


# =============================================================================
# THE WALL
# =============================================================================

#: Grammar that makes a sentence counterfactual. Any of these, with no type
#: marker present, is an unlabelled counterfactual.
_CF_GRAMMAR = ("would have been", "would have", "had rates", "if rates had",
               "counterfactual", "absent the", "in the absence of",
               "what if", "had the")


def assert_labelled(text: str) -> None:
    """Refuse counterfactual prose carrying none of the three markers.

    Scans the OUTPUT, because the failure is a rendering failure: the object
    can be perfectly typed and the renderer can still drop the label.
    """
    low = text.lower()
    if not any(g in low for g in _CF_GRAMMAR):
        return
    if any(m in text for m in MARKERS.values()):
        return
    raise UnlabelledCounterfactual(
        f"counterfactual prose with no type marker: {text[:160]!r}. A reader "
        "cannot tell an identified effect from a hypothesis somebody typed "
        "in, and once rendered the two are indistinguishable. Use "
        "Counterfactual.statement().")


def assert_no_upgrade(before: Counterfactual, after: Counterfactual) -> None:
    """A counterfactual may be downgraded, never silently promoted.

    SCENARIO -> SIMULATION -> CAUSAL requires new evidence, and the
    constructor demands it. This catches the other route: relabelling an
    existing object in place.
    """
    order = {SCENARIO_ASSUMPTION: 0, STRUCTURAL_SIMULATION: 1,
             CAUSAL_ESTIMATE: 2}
    if order[after.cf_type] > order[before.cf_type]:
        raise MislabelledCounterfactual(
            f"{before.question!r} was relabelled {before.cf_type} -> "
            f"{after.cf_type}. Strengthening a counterfactual's claim "
            "requires new identification, not a new label.")


def scenario(*, question: str, intervention: str, outcome: str,
             direction: str, as_of: str, uncertainty: str = "") -> Counterfactual:
    return Counterfactual(question=question, intervention=intervention,
                          outcome=outcome, direction=direction,
                          cf_type=SCENARIO_ASSUMPTION, as_of=as_of,
                          uncertainty=uncertainty)


def simulation(*, question: str, intervention: str, outcome: str,
               direction: str, as_of: str, assumptions: Sequence[str],
               magnitude: Optional[float] = None, magnitude_unit: str = "",
               uncertainty: str = "") -> Counterfactual:
    return Counterfactual(question=question, intervention=intervention,
                          outcome=outcome, direction=direction,
                          cf_type=STRUCTURAL_SIMULATION, as_of=as_of,
                          assumptions=tuple(assumptions),
                          magnitude=magnitude, magnitude_unit=magnitude_unit,
                          uncertainty=uncertainty)


def causal(*, question: str, intervention: str, outcome: str, direction: str,
           as_of: str, identification: str, evidence_level: int,
           magnitude: Optional[float] = None, magnitude_unit: str = "",
           uncertainty: str = "",
           evidence_nodes: Sequence[str] = ()) -> Counterfactual:
    return Counterfactual(question=question, intervention=intervention,
                          outcome=outcome, direction=direction,
                          cf_type=CAUSAL_ESTIMATE, as_of=as_of,
                          identification=identification,
                          evidence_level=evidence_level, magnitude=magnitude,
                          magnitude_unit=magnitude_unit,
                          uncertainty=uncertainty,
                          evidence_nodes=tuple(evidence_nodes))


def summarise(cfs: Sequence[Counterfactual]) -> dict:
    by_type = {t: 0 for t in TYPES}
    for c in cfs:
        by_type[c.cf_type] += 1
    return {"contract": CONTRACT, "counterfactuals": len(cfs),
            "by_type": by_type,
            "may_inform_intervention": sum(1 for c in cfs
                                           if c.may_inform_intervention),
            "statements": [c.statement() for c in cfs]}

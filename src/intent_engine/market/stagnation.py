"""Working hard and learning nothing, stated as five separate questions.

WHY FIVE AND NOT ONE
--------------------
`learning_health.alerts` already fires when nothing has been learned at all.
The condition this module adds is different and worse, because it looks like
health from every angle an operator normally checks: throughput is high, the
counts are rising, the reports are longer — and none of it is turning into
knowledge that changes a decision.

That failure has five distinct causes, and a single "stagnation" score would
average them into a number nobody can act on:

    evidence arrives and produces no effects       the readers are wrong
    theses accumulate and never resolve            no falsifier is ever tested
    research spends and returns no value           the policy is picking badly
    discoveries pile up and none is validated      the validator is missing
    analyses ship and none changes a decision      the product is decoration

Each names a different team's next morning. They are computed independently
and reported independently, and none of them is combined with another.

EVERY ONE CAN REPORT THE NEGATIVE
---------------------------------
This project has shipped a metric that could only ever return a positive, and
the lesson was that a measurement which cannot come back negative is not a
measurement. So each check here has three outcomes, not two: FIRING, CLEAR,
and UNMEASURABLE — and UNMEASURABLE is returned whenever the denominator is
absent or too small, never a comfortable zero. "We looked and the rate is
fine" and "we cannot compute the rate" are different sentences and only the
first is reassuring.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "stagnation.v1"

# --- outcomes ----------------------------------------------------------------
FIRING = "FIRING"                # measured, and the ratio is bad
CLEAR = "CLEAR"                  # measured, and the ratio is fine
UNMEASURABLE = "UNMEASURABLE"    # not measured; NOT a passing grade
OUTCOMES = (FIRING, CLEAR, UNMEASURABLE)

# --- the five ----------------------------------------------------------------
EVIDENCE_WITHOUT_EFFECT = "EVIDENCE_WITHOUT_EFFECT"
THESES_WITHOUT_RESOLUTION = "THESES_WITHOUT_RESOLUTION"
SPEND_WITHOUT_VALUE = "SPEND_WITHOUT_VALUE"
DISCOVERY_WITHOUT_VALIDATION = "DISCOVERY_WITHOUT_VALIDATION"
ANALYSIS_WITHOUT_IMPACT = "ANALYSIS_WITHOUT_IMPACT"

CHECKS = (EVIDENCE_WITHOUT_EFFECT, THESES_WITHOUT_RESOLUTION,
          SPEND_WITHOUT_VALUE, DISCOVERY_WITHOUT_VALIDATION,
          ANALYSIS_WITHOUT_IMPACT)

#: What each one means for whoever reads it, and what they would do next.
CHECK_MEANING = {
    EVIDENCE_WITHOUT_EFFECT:
        "evidence is being ingested and almost none of it changes any "
        "knowledge object; the readers are the suspect, not the corpus",
    THESES_WITHOUT_RESOLUTION:
        "theses accumulate and none reaches a verdict; nothing is testing "
        "the falsifiers, so the engine cannot be wrong and cannot be right",
    SPEND_WITHOUT_VALUE:
        "research is spending and the value it returns does not track what "
        "it expected; the selection policy is the suspect",
    DISCOVERY_WITHOUT_VALIDATION:
        "structure is being discovered and none of it is validated against "
        "a downstream task; geometry is improving and usefulness is unknown",
    ANALYSIS_WITHOUT_IMPACT:
        "analyses are produced and none of them changes a decision; the "
        "product is generating output rather than changing minds",
}

#: The smallest numerator worth alerting on. Below this the ratio is noise —
#: two evidence rows producing no effects is a quiet night, not a defect.
MIN_ACTIVITY = {
    EVIDENCE_WITHOUT_EFFECT: 50,
    THESES_WITHOUT_RESOLUTION: 5,
    SPEND_WITHOUT_VALUE: 10,
    DISCOVERY_WITHOUT_VALIDATION: 3,
    ANALYSIS_WITHOUT_IMPACT: 5,
}

#: Below this ratio, the activity is not producing what it is for.
THRESHOLD = {
    EVIDENCE_WITHOUT_EFFECT: 0.05,
    THESES_WITHOUT_RESOLUTION: 0.10,
    SPEND_WITHOUT_VALUE: 0.10,
    DISCOVERY_WITHOUT_VALIDATION: 0.20,
    ANALYSIS_WITHOUT_IMPACT: 0.01,
}


@dataclass(frozen=True)
class Check:
    """One question, its arithmetic, and which of the three answers it got."""

    name: str
    outcome: str
    activity: Optional[float] = None
    produced: Optional[float] = None
    ratio: Optional[float] = None
    threshold: Optional[float] = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.name not in CHECKS:
            raise ValueError(f"unknown stagnation check {self.name!r}")
        if self.outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {self.outcome!r}")

    @property
    def meaning(self) -> str:
        return CHECK_MEANING[self.name]

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT, meaning=self.meaning)
        return out


def _check(name: str, activity, produced) -> Check:
    """One ratio, with the un-measurable case decided before the arithmetic."""
    floor = MIN_ACTIVITY[name]
    limit = THRESHOLD[name]
    if activity is None or produced is None:
        return Check(name=name, outcome=UNMEASURABLE,
                     detail="one side of the ratio was not reported; this is "
                            "not a rate of zero, it is the absence of a rate")
    activity = float(activity)
    produced = float(produced)
    if activity < floor:
        return Check(name=name, outcome=UNMEASURABLE, activity=activity,
                     produced=produced, threshold=limit,
                     detail=f"only {activity:g} unit(s) of activity, below "
                            f"the {floor} needed for the ratio to mean "
                            "anything; a quiet period is not a stalled one")
    ratio = produced / activity if activity else 0.0
    outcome = FIRING if ratio < limit else CLEAR
    return Check(name=name, outcome=outcome, activity=activity,
                 produced=produced, ratio=round(ratio, 6), threshold=limit,
                 detail=(f"{produced:g} of {activity:g} "
                         f"({ratio:.1%}) against a floor of {limit:.0%}"))


def evaluate(*, evidence_rows=None, knowledge_effects=None,
             theses=None, theses_resolved=None,
             research_cost=None, realised_value=None,
             discoveries=None, discoveries_validated=None,
             analyses=None, decision_impacts=None) -> Tuple[Check, ...]:
    """The five, computed independently and never combined.

    Keyword-only and all defaulting to None, because a caller that cannot
    supply one input should get UNMEASURABLE for that check and real answers
    for the rest — not a single score silently missing a term.
    """
    return (
        _check(EVIDENCE_WITHOUT_EFFECT, evidence_rows, knowledge_effects),
        _check(THESES_WITHOUT_RESOLUTION, theses, theses_resolved),
        _check(SPEND_WITHOUT_VALUE, research_cost, realised_value),
        _check(DISCOVERY_WITHOUT_VALIDATION, discoveries,
               discoveries_validated),
        _check(ANALYSIS_WITHOUT_IMPACT, analyses, decision_impacts),
    )


def summarise(checks: Sequence[Check]) -> dict:
    """Counts by outcome, with UNMEASURABLE reported rather than folded.

    There is deliberately no overall stagnation score. Five causes averaged
    into one number is a number nobody can act on, and the whole reason these
    are separate is that each names a different next morning.
    """
    by_outcome = {o: sum(1 for c in checks if c.outcome == o)
                  for o in OUTCOMES}
    firing = [c for c in checks if c.outcome == FIRING]
    return {
        "contract": CONTRACT,
        "checks": len(checks),
        "by_outcome": by_outcome,
        "firing": [c.name for c in firing],
        "unmeasurable": [c.name for c in checks
                         if c.outcome == UNMEASURABLE],
        "detail": [c.as_dict() for c in checks],
        "note": ("five independent questions, never averaged. UNMEASURABLE is "
                 "not a pass: it means the ratio could not be computed, and "
                 "an engine that cannot tell whether it is learning is in a "
                 "worse position than one that knows it is not"),
    }

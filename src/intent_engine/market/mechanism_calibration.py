"""Which economic mechanisms actually transmit, and which ones only sound true.

WHAT A MECHANISM IS HERE
------------------------
Not a textbook claim. A mechanism in this system is an existing, already-
committed object: a `belief_formation.Family` is a hypothesis about
transmission, and it has always had all four parts one needs —

    trigger      the evidence types that route to it, and in which direction
    claim        the proposition it asserts about the company's economic state
    consequence  the observation it commits to seeing (`expected_event`)
    falsifier    the observation that would refute it

so no new taxonomy is invented here. What was missing is that nothing ever
went back and asked whether the transmission held.

WHY THIS COULD NOT BE BUILT BEFORE
----------------------------------
Until `observation_binding` landed, the reconciliation loop had never produced
a single informative outcome — 46 expectations, all TOO_EARLY — so every
mechanism had a test count of zero and any "reliability" figure would have
been the prior with a decimal point. The first real cycle after that fix
produced 8 confirmed and 2 contradicted, which is the first time this module
had anything to compute from.

THE DISCIPLINE
--------------
A mechanism is not confirmed by one observation, and this refuses to imply
otherwise: below `MIN_TESTS` the reliability is `UNMEASURABLE`, never a
number. `demand_strengthening` having 8 confirmations and `pricing_power`
having 1 are not two points on the same scale, and averaging them would let a
single lucky family carry a whole report.

Contradictions are reported at equal weight to confirmations and never
netted. A mechanism that is right 8 times and wrong 2 times is a different
object from one that is right 6 times and never wrong, and "+6" erases the
difference that matters.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import belief_formation as BF
from . import expectation as EXP
from . import observation_binding as OB

CONTRACT = "mechanism_calibration.v1"

#: Below this many INFORMATIVE tests a reliability figure is noise wearing a
#: decimal point. Deliberately equal to the learning-health calibration floor:
#: two modules disagreeing about what counts as measurable is how a dashboard
#: ends up contradicting itself.
MIN_TESTS = 5

UNMEASURABLE = "UNMEASURABLE"

# --- maturity ---------------------------------------------------------------
UNTESTED = "UNTESTED"
EMERGING = "EMERGING"              # tested, but under the reporting floor
ESTABLISHED = "ESTABLISHED"        # enough tests, holds up
CONTESTED = "CONTESTED"            # enough tests, both directions observed
FAILING = "FAILING"                # enough tests, mostly contradicted
UNFALSIFIABLE_BY_OBSERVATION = "UNFALSIFIABLE_BY_OBSERVATION"

MATURITIES = frozenset({UNTESTED, EMERGING, ESTABLISHED, CONTESTED, FAILING,
                        UNFALSIFIABLE_BY_OBSERVATION})

#: Above this contradiction share a mechanism is failing rather than contested.
FAILING_ABOVE = 0.5
#: Below this contradiction share, with enough tests, it is established.
ESTABLISHED_BELOW = 0.2


@dataclass(frozen=True)
class Mechanism:
    """One transmission hypothesis and its record against real outcomes."""
    key: str
    proposition: str
    expected_event: str
    falsifier: str
    window_days: int
    trigger_types: Tuple[str, ...]
    falsifiable_by_observation: bool
    beliefs: int = 0
    expectations: int = 0
    tested: int = 0
    confirmed: int = 0
    contradicted: int = 0
    partially_confirmed: int = 0
    subjects_tested: Tuple[str, ...] = ()

    @property
    def reliability(self) -> object:
        """Share of informative tests that went the way the mechanism said.

        UNMEASURABLE below the floor. A partial confirmation counts as a
        confirmation of DIRECTION, which is what a mechanism claims — it says
        the move happens, not how large it is.
        """
        if self.tested < MIN_TESTS:
            return UNMEASURABLE
        return (self.confirmed + self.partially_confirmed) / self.tested

    @property
    def maturity(self) -> str:
        if not self.falsifiable_by_observation:
            # It can be proposed and never refuted through this channel, so
            # calling it established would be a category error, not a grade.
            return UNFALSIFIABLE_BY_OBSERVATION
        if not self.tested:
            return UNTESTED
        if self.tested < MIN_TESTS:
            return EMERGING
        wrong = self.contradicted / self.tested
        if wrong > FAILING_ABOVE:
            return FAILING
        if wrong < ESTABLISHED_BELOW:
            return ESTABLISHED
        return CONTESTED

    @property
    def independent_subjects(self) -> int:
        """How many DIFFERENT companies the tests came from.

        Eight confirmations from one company is one observation repeated, not
        eight. A mechanism has to survive across subjects before its
        reliability means anything about the mechanism rather than about that
        company.
        """
        return len(set(self.subjects_tested))

    def as_dict(self) -> dict:
        return {
            "mechanism": self.key,
            "claim": self.proposition,
            "transmits_to": self.expected_event,
            "falsifier": self.falsifier,
            "window_days": self.window_days,
            "trigger_evidence": list(self.trigger_types),
            "falsifiable_by_observation": self.falsifiable_by_observation,
            "beliefs": self.beliefs,
            "expectations": self.expectations,
            "tested": self.tested,
            "confirmed": self.confirmed,
            "partially_confirmed": self.partially_confirmed,
            "contradicted": self.contradicted,
            "reliability": self.reliability,
            "maturity": self.maturity,
            "independent_subjects": self.independent_subjects,
        }


def _triggers() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = collections.defaultdict(list)
    for etype, family, _direction in BF._ROUTES:
        if etype not in out[family]:
            out[family].append(etype)
    return out


def calibrate(rows: Sequence[dict]) -> Tuple[Mechanism, ...]:
    """Score every mechanism against the ledger's real reconciliations.

    `rows` is the raw learning ledger. Reconciliations are joined back to
    their expectation to recover which family made the claim — the
    reconciliation itself records the hypothesis, not the mechanism, and the
    mechanism is the thing worth grading.
    """
    triggers = _triggers()
    expectations = {r.get("expectation_id"): r for r in rows
                    if r.get("record") == "expectation"}
    beliefs = [r for r in rows if r.get("record") == "belief"]

    per_family_expectations: Dict[str, int] = collections.Counter()
    for row in expectations.values():
        metric = row.get("metric") or ""
        if metric:
            per_family_expectations[metric] += 1

    # A belief id is keyed on (subject, family), and the family is only
    # recoverable through the expectation preregistered alongside it -- the
    # belief row itself does not carry one.
    family_of_belief = {exp.get("hypothesis_id"): exp.get("metric") or ""
                        for exp in expectations.values()
                        if exp.get("hypothesis_id")}
    per_family_beliefs: Dict[str, int] = collections.Counter(
        family_of_belief[row["belief_id"]] for row in beliefs
        if row.get("belief_id") in family_of_belief)

    tested: Dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    subjects: Dict[str, List[str]] = collections.defaultdict(list)
    for row in rows:
        if row.get("record") != "reconciliation":
            continue
        outcome = row.get("outcome")
        if outcome not in EXP.INFORMATIVE:
            continue
        exp = expectations.get(row.get("expectation_id")) or {}
        family = exp.get("metric") or ""
        if not family:
            continue
        tested[family][outcome] += 1
        subjects[family].append(str(row.get("subject") or ""))

    out: List[Mechanism] = []
    for key, spec in sorted(BF.FAMILIES.items()):
        counts = tested.get(key, collections.Counter())
        informative = sum(counts.values())
        out.append(Mechanism(
            key=key,
            proposition=spec.proposition,
            expected_event=spec.expected_event,
            falsifier=spec.falsifier,
            window_days=spec.window_days,
            trigger_types=tuple(triggers.get(key, ())),
            falsifiable_by_observation=key in OB.FALSIFIABLE,
            beliefs=per_family_beliefs.get(key, 0),
            expectations=per_family_expectations.get(key, 0),
            tested=informative,
            confirmed=counts.get(EXP.CONFIRMED, 0),
            partially_confirmed=counts.get(EXP.PARTIALLY_CONFIRMED, 0),
            contradicted=counts.get(EXP.CONTRADICTED, 0),
            subjects_tested=tuple(subjects.get(key, ())),
        ))
    return tuple(out)


def summarise(mechanisms: Sequence[Mechanism]) -> dict:
    """The operator view: what has been tested, and what is still assumed."""
    by_maturity = collections.Counter(m.maturity for m in mechanisms)
    tested = [m for m in mechanisms if m.tested]
    graded = [m for m in mechanisms if m.reliability is not UNMEASURABLE]

    # The most important row in this report is the one naming a mechanism the
    # evidence ARGUED WITH, because that is the only kind that has taught the
    # engine anything it did not already assume.
    contradicted = sorted((m for m in mechanisms if m.contradicted),
                          key=lambda m: -m.contradicted)

    return {
        "contract": CONTRACT,
        "mechanisms_total": len(mechanisms),
        "mechanisms_tested": len(tested),
        "mechanisms_gradeable": len(graded),
        "by_maturity": dict(by_maturity),
        "tests_total": sum(m.tested for m in mechanisms),
        "confirmations": sum(m.confirmed + m.partially_confirmed
                             for m in mechanisms),
        "contradictions": sum(m.contradicted for m in mechanisms),
        "most_contradicted": (contradicted[0].key if contradicted else None),
        "assumed_but_never_tested": sorted(
            m.key for m in mechanisms
            if m.maturity == UNTESTED and m.falsifiable_by_observation),
        "unfalsifiable_by_observation": sorted(
            m.key for m in mechanisms if not m.falsifiable_by_observation),
        "mechanisms": [m.as_dict() for m in mechanisms if m.tested
                       or m.expectations],
    }

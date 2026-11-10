"""Preregistered expectations, and the reconciliation that scores them.

THE POINT
---------
A belief that never says what it expects to see cannot be wrong, and a belief
that cannot be wrong cannot teach anything. This module makes the engine commit
in advance: for each live hypothesis it writes down the observable it expects,
the direction, the window, and — critically — the observation that would
falsify it. Later, when the observation arrives, the comparison is mechanical.

WHY THIS IS THE FIX FOR NO-TRADE / NO-LEARNING
----------------------------------------------
The measured defect was that belief revision was reachable only through a
resolved paper trade. Preregistration breaks that dependency without inventing
progress, because an update now requires two things that are both external to
the engine: a commitment made before the fact, and a real observation after it.
A quiet week produces `TOO_EARLY` and changes nothing. That is a legitimate
zero, and it is a different zero from "nothing was ever tested".

PREREGISTRATION IS LOAD-BEARING, NOT CEREMONIAL
-----------------------------------------------
`preregistered_at` must precede the observation used to score it, and
`reconcile` enforces that rather than trusting the caller. Scoring an
expectation against an observation that predates it is retrodiction — writing
the prediction after seeing the answer — and it would produce a flawless
track record that means nothing.

WHY MISMATCH IS EVIDENCE
------------------------
Expect: hawkish Fed → banks outperform, utilities weaken. Observe: banks fall,
utilities hold, oil rises. Nothing was traded and nothing resolved, yet the
engine now knows its rate-transmission story is wrong in a specific, recorded
way. `CONTRADICTED` is the highest-information outcome this module produces,
and it costs nothing to obtain.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

CONTRACT_VERSION = "expected_observation.v1"

# --- direction ------------------------------------------------------------
UP = "UP"
DOWN = "DOWN"
FLAT = "FLAT"
DIRECTIONS = frozenset({UP, DOWN, FLAT})

# --- outcome classes ------------------------------------------------------
CONFIRMED = "CONFIRMED"
PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
CONTRADICTED = "CONTRADICTED"
UNINFORMATIVE = "UNINFORMATIVE"
UNMEASURABLE = "UNMEASURABLE"
TOO_EARLY = "TOO_EARLY"

OUTCOMES = frozenset({CONFIRMED, PARTIALLY_CONFIRMED, CONTRADICTED,
                      UNINFORMATIVE, UNMEASURABLE, TOO_EARLY})

# Outcomes that justify moving a posterior. The other three are silence:
# TOO_EARLY means the window is open, UNMEASURABLE means the observation does
# not exist, UNINFORMATIVE means it exists and discriminates nothing.
INFORMATIVE = frozenset({CONFIRMED, PARTIALLY_CONFIRMED, CONTRADICTED})


class ExpectationRejected(ValueError):
    """The expectation was not falsifiable, and says why."""


@dataclass(frozen=True)
class ExpectedObservation:
    """What a hypothesis commits to seeing, written down before it is seen."""
    expectation_id: str
    hypothesis_id: str
    subject: str
    expected_event: str
    expected_direction: str
    preregistered_at: str
    evaluation_window_ends: str
    falsifier: str
    evidence_basis: Tuple[str, ...] = ()
    expected_range: Optional[Tuple[float, float]] = None
    relevant_actors: Tuple[str, ...] = ()
    expected_reactions: Tuple[str, ...] = ()
    uncertainty: float = 0.5
    metric: str = ""

    def window_open_at(self, as_of: str) -> bool:
        return (as_of or "")[:10] <= self.evaluation_window_ends[:10]

    def as_dict(self) -> dict:
        return {
            "expectation_id": self.expectation_id,
            "hypothesis_id": self.hypothesis_id,
            "subject": self.subject,
            "expected_event": self.expected_event,
            "expected_direction": self.expected_direction,
            "expected_range": list(self.expected_range)
            if self.expected_range else None,
            "metric": self.metric,
            "relevant_actors": list(self.relevant_actors),
            "expected_reactions": list(self.expected_reactions),
            "evaluation_window_ends": self.evaluation_window_ends,
            "preregistered_at": self.preregistered_at,
            "evidence_basis": list(self.evidence_basis),
            "uncertainty": self.uncertainty,
            "falsifier": self.falsifier,
        }


@dataclass(frozen=True)
class Reconciliation:
    """The scored comparison of one expectation against what happened."""
    expectation_id: str
    hypothesis_id: str
    subject: str
    outcome: str
    observed_direction: Optional[str]
    observed_value: Optional[float]
    evaluated_at: str
    rationale: str
    evidence_ids: Tuple[str, ...] = ()

    @property
    def informative(self) -> bool:
        return self.outcome in INFORMATIVE

    def as_dict(self) -> dict:
        return {"expectation_id": self.expectation_id,
                "hypothesis_id": self.hypothesis_id,
                "subject": self.subject,
                "outcome": self.outcome,
                "observed_direction": self.observed_direction,
                "observed_value": self.observed_value,
                "evaluated_at": self.evaluated_at,
                "rationale": self.rationale,
                "informative": self.informative,
                "evidence_ids": list(self.evidence_ids)}


def preregister(*, hypothesis_id: str, subject: str, expected_event: str,
                expected_direction: str, preregistered_at: str,
                evaluation_window_ends: str, falsifier: str,
                metric: str = "", evidence_basis: Sequence[str] = (),
                expected_range: Optional[Tuple[float, float]] = None,
                relevant_actors: Sequence[str] = (),
                expected_reactions: Sequence[str] = (),
                uncertainty: float = 0.5) -> ExpectedObservation:
    """Commit to an observable, or refuse.

    The falsifier is mandatory. An expectation with no stated way to be wrong
    is a description of hope, and scoring it later would only ever confirm.
    """
    if not (hypothesis_id or "").strip():
        raise ExpectationRejected("expectation must name its hypothesis")
    if expected_direction not in DIRECTIONS:
        raise ExpectationRejected(
            f"unknown direction {expected_direction!r}")
    if not (falsifier or "").strip():
        raise ExpectationRejected(
            "an expectation without a falsifier cannot be wrong, so it cannot "
            "teach anything; state what observation would refute it")
    if not (expected_event or "").strip():
        raise ExpectationRejected("expectation must name the event")
    if evaluation_window_ends[:10] < preregistered_at[:10]:
        raise ExpectationRejected(
            "evaluation window closes before it was registered")
    if expected_range is not None:
        low, high = expected_range
        if low > high:
            raise ExpectationRejected("expected_range is inverted")

    raw = "|".join((hypothesis_id, subject, expected_event,
                    expected_direction, preregistered_at[:10]))
    eid = "exp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return ExpectedObservation(
        expectation_id=eid, hypothesis_id=hypothesis_id,
        subject=subject.strip(), expected_event=expected_event.strip(),
        expected_direction=expected_direction,
        preregistered_at=preregistered_at[:10],
        evaluation_window_ends=evaluation_window_ends[:10],
        falsifier=falsifier.strip(), metric=metric.strip(),
        evidence_basis=tuple(evidence_basis),
        expected_range=tuple(expected_range) if expected_range else None,
        relevant_actors=tuple(relevant_actors),
        expected_reactions=tuple(expected_reactions),
        uncertainty=min(max(float(uncertainty), 0.0), 1.0))


def reconcile(expectation: ExpectedObservation, *, as_of: str,
              observed_value: Optional[float] = None,
              observed_at: str = "",
              observed_direction: Optional[str] = None,
              evidence_ids: Sequence[str] = (),
              flat_band: float = 0.01) -> Reconciliation:
    """Score one expectation against what was actually observed.

    Order of checks matters and is deliberate:

    1. An observation that PREDATES preregistration is refused outright. That
       is retrodiction, and it is the one input that would make this module
       produce a flattering, meaningless record.
    2. No observation inside an open window is TOO_EARLY, not a failure. An
       engine that scored every unresolved expectation as wrong would decay
       every belief it held simply by holding it.
    3. Only then is direction compared.
    """
    def result(outcome: str, rationale: str,
               direction: Optional[str] = None) -> Reconciliation:
        return Reconciliation(
            expectation_id=expectation.expectation_id,
            hypothesis_id=expectation.hypothesis_id,
            subject=expectation.subject, outcome=outcome,
            observed_direction=direction, observed_value=observed_value,
            evaluated_at=(as_of or "")[:10], rationale=rationale,
            evidence_ids=tuple(evidence_ids))

    have_observation = observed_value is not None or observed_direction

    if have_observation and observed_at and \
            observed_at[:10] < expectation.preregistered_at[:10]:
        return result(
            UNMEASURABLE,
            "observation predates preregistration; scoring it would be "
            "retrodiction, so it is refused rather than counted")

    if not have_observation:
        if expectation.window_open_at(as_of):
            return result(TOO_EARLY,
                          "evaluation window is still open and no qualifying "
                          "observation has arrived")
        return result(UNMEASURABLE,
                      "window closed without a qualifying observation; the "
                      "absence is recorded, not treated as a refutation")

    direction = observed_direction or _direction_of(observed_value, flat_band)

    # A FLAT outcome against a directional expectation discriminates weakly:
    # it is neither the move nor its opposite. Calling it a refutation would
    # punish a correct-but-slow hypothesis for the market's timing.
    if direction == FLAT and expectation.expected_direction in (UP, DOWN):
        return result(UNINFORMATIVE,
                      f"observed move within the ±{flat_band:.1%} flat band, "
                      f"which does not discriminate for or against the "
                      f"expected {expectation.expected_direction}", direction)

    if direction != expectation.expected_direction:
        return result(CONTRADICTED,
                      f"expected {expectation.expected_direction}, observed "
                      f"{direction}; the mismatch is the finding",
                      direction)

    # Direction matched. A stated range decides whether that is full or
    # partial confirmation — getting the sign right while missing the
    # magnitude badly is real information about the mechanism's strength.
    if expectation.expected_range and observed_value is not None:
        low, high = expectation.expected_range
        if low <= observed_value <= high:
            return result(CONFIRMED,
                          f"direction and magnitude both as preregistered "
                          f"({low}–{high})", direction)
        return result(PARTIALLY_CONFIRMED,
                      f"direction as expected but magnitude {observed_value} "
                      f"fell outside the preregistered {low}–{high}",
                      direction)
    return result(CONFIRMED, "observed direction matches the preregistered "
                             "expectation", direction)


def _direction_of(value: Optional[float], flat_band: float) -> str:
    if value is None:
        return FLAT
    if value > flat_band:
        return UP
    if value < -flat_band:
        return DOWN
    return FLAT


def summarise(reconciliations: Sequence[Reconciliation]) -> dict:
    """Counts by outcome, for the session report.

    `informative` is reported separately because it — not the raw total — is
    the honest measure of whether a cycle learned anything.
    """
    counts = {o: 0 for o in sorted(OUTCOMES)}
    for r in reconciliations:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    return {"evaluated": len(reconciliations), "by_outcome": counts,
            "informative": sum(1 for r in reconciliations if r.informative)}

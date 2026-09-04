"""§23: typed trajectories, populated from the real historical panel.

WHY THIS EXISTS NOW AND NOT BEFORE
----------------------------------
The previous run refused to build this, and was right to: §59 forbids a
vertical with no producer, and a typed trajectory populated by nothing is a
class diagram. What changed is the panel. `Panel.history(series, as_of=T)`
returns exactly what a series looked like at T, revisions and all, which is
the only honest way to build an ActualTrajectory that a replay can trust.

THE FOUR KINDS, AND WHY THEY ARE NOT INTERCHANGEABLE
-----------------------------------------------------
    ACTUAL          what happened, from the panel
    EXPECTED        what the model said would happen, from a forecast
    DESIRED         what someone wanted to happen -- legitimate for a company
                    strategy, refused for a market price, because a "desired"
                    price path with no objective behind it is a wish
    COUNTERFACTUAL  what would have happened under an intervention

The last one carries a `CounterfactualType` and cannot be built without it.
That is the join to §24: a counterfactual trajectory rendered without its
label is the same defect as a counterfactual sentence rendered without one,
one dimension up.

WHY EVERY TRAJECTORY CARRIES A VINTAGE CUTOFF
----------------------------------------------
An ActualTrajectory built from today's data and an ExpectedTrajectory built
from what was knowable in 2015 are not comparable, and comparing them is how
a model looks prescient. `vintage_cutoff` is on both, and `compare` refuses a
pair whose cutoffs disagree without a stated reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .counterfactual import TYPES as CF_TYPES
from .counterfactual import MARKERS as CF_MARKERS
from .vocabulary import EconError, require

CONTRACT = "econ_trajectory.v1"

ACTUAL = "ACTUAL"
EXPECTED = "EXPECTED"
DESIRED = "DESIRED"
COUNTERFACTUAL = "COUNTERFACTUAL"
KINDS = (ACTUAL, EXPECTED, DESIRED, COUNTERFACTUAL)

#: Subjects for which a DESIRED trajectory is meaningful. A company may want
#: its margin to go up. "The market" wanting a price path is not a desire, it
#: is a position -- and Section 23 says not to create normative price
#: trajectories without a defined objective.
DESIRE_REQUIRES_OBJECTIVE = True


class TrajectoryRefused(EconError):
    """A trajectory claimed something its kind does not license."""


@dataclass(frozen=True)
class Point:
    at: str
    value: float
    #: Only on EXPECTED and COUNTERFACTUAL: the band around the point.
    low: Optional[float] = None
    high: Optional[float] = None

    def __post_init__(self) -> None:
        require(bool(self.at), "a trajectory point is dated")
        if self.low is not None and self.high is not None:
            require(self.low <= self.value <= self.high,
                    f"{self.at}: {self.value} is outside its own band "
                    f"[{self.low}, {self.high}]")

    @property
    def banded(self) -> bool:
        return self.low is not None and self.high is not None

    def as_dict(self) -> dict:
        return {"at": self.at, "value": self.value,
                "low": self.low, "high": self.high}


@dataclass(frozen=True)
class Trajectory:
    """One path through time, of one declared kind."""

    subject: str
    quantity: str
    kind: str
    as_of: str
    points: Tuple[Point, ...]
    #: The latest vintage any input to this trajectory came from. For ACTUAL
    #: this is what makes it comparable to an EXPECTED built at the same date.
    vintage_cutoff: str = ""
    source: str = ""
    #: COUNTERFACTUAL only, and required there.
    counterfactual_type: str = ""
    intervention: str = ""
    #: DESIRED only, and required there.
    objective: str = ""
    uncertainty: str = ""

    def __post_init__(self) -> None:
        require(self.kind in KINDS, f"unknown trajectory kind {self.kind!r}")
        require(bool(self.points), f"{self.quantity}: an empty trajectory is "
                                   "not a trajectory")
        require(bool(self.as_of), "a trajectory is dated")
        dates = [p.at for p in self.points]
        require(dates == sorted(dates),
                f"{self.quantity}: points are out of order; a trajectory read "
                "backwards is a different claim")
        if self.kind == COUNTERFACTUAL:
            require(self.counterfactual_type in CF_TYPES,
                    f"{self.quantity}: a COUNTERFACTUAL trajectory must "
                    "declare its counterfactual type. A counterfactual path "
                    "rendered without one is the same defect as a "
                    "counterfactual sentence without one, a dimension up.")
            require(bool(self.intervention.strip()),
                    "a counterfactual names what was varied")
        else:
            require(not self.counterfactual_type,
                    f"a {self.kind} trajectory carries no counterfactual type")
        if self.kind == DESIRED and DESIRE_REQUIRES_OBJECTIVE:
            require(bool(self.objective.strip()),
                    f"{self.subject}/{self.quantity}: a DESIRED trajectory "
                    "states the objective it is desired against. Without one "
                    "this is a wish, and Section 23 refuses normative price "
                    "paths for exactly that reason.")
        if self.kind == ACTUAL:
            require(not any(p.banded for p in self.points),
                    "an ACTUAL trajectory carries no uncertainty band; what "
                    "happened is not a forecast")

    @property
    def start(self) -> str:
        return self.points[0].at

    @property
    def end(self) -> str:
        return self.points[-1].at

    @property
    def net_change(self) -> Optional[float]:
        a, b = self.points[0].value, self.points[-1].value
        if a == 0:
            return None
        return round((b - a) / abs(a), 5)

    @property
    def direction(self) -> str:
        nc = self.net_change
        if nc is None:
            return "UNKNOWN"
        if abs(nc) < 0.005:
            return "FLAT"
        return "UP" if nc > 0 else "DOWN"

    def value_at(self, at: str) -> Optional[float]:
        for p in self.points:
            if p.at == at:
                return p.value
        return None

    def label(self) -> str:
        if self.kind == COUNTERFACTUAL:
            return f"{CF_MARKERS[self.counterfactual_type]} {self.quantity}"
        return f"[{self.kind}] {self.quantity}"

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "subject": self.subject,
                "quantity": self.quantity, "kind": self.kind,
                "as_of": self.as_of, "label": self.label(),
                "start": self.start, "end": self.end,
                "net_change": self.net_change, "direction": self.direction,
                "vintage_cutoff": self.vintage_cutoff, "source": self.source,
                "counterfactual_type": self.counterfactual_type,
                "intervention": self.intervention, "objective": self.objective,
                "uncertainty": self.uncertainty,
                "points": [p.as_dict() for p in self.points]}


# =============================================================================
# PRODUCERS
# =============================================================================

def actual_from_panel(panel, series_id: str, *, subject: str, as_of: str,
                      start: str = "", lookback: int = 0) -> Trajectory:
    """What actually happened, read at a stated vintage.

    `as_of` is passed straight to `Panel.history`, so an ACTUAL trajectory is
    always "actual as known at this date" rather than "actual, timelessly" --
    which is the only version that can be compared with a forecast made then.
    """
    hist = panel.history(series_id, as_of=as_of, lookback=lookback)
    if start:
        hist = [(d, v) for d, v in hist if d >= start]
    if not hist:
        raise TrajectoryRefused(
            f"{series_id}: no observations knowable at {as_of}. This is an "
            f"absence ({panel.absence(series_id, as_of)}), not an empty "
            "trajectory, and the two support different decisions.")
    return Trajectory(
        subject=subject, quantity=series_id, kind=ACTUAL, as_of=as_of,
        points=tuple(Point(at=d, value=v) for d, v in hist),
        vintage_cutoff=as_of, source="econ.panel")


def expected_from_forecast(*, subject: str, quantity: str, as_of: str,
                           points: Sequence[Tuple[str, float, float, float]],
                           source: str, vintage_cutoff: str,
                           uncertainty: str = "") -> Trajectory:
    """The path a model said to expect, with its band."""
    return Trajectory(
        subject=subject, quantity=quantity, kind=EXPECTED, as_of=as_of,
        points=tuple(Point(at=d, value=v, low=lo, high=hi)
                     for d, v, lo, hi in points),
        vintage_cutoff=vintage_cutoff, source=source,
        uncertainty=uncertainty)


def counterfactual_from(cf, *, subject: str, quantity: str, as_of: str,
                        points: Sequence[Tuple[str, float]],
                        vintage_cutoff: str = "") -> Trajectory:
    """A counterfactual path, inheriting its type from a `Counterfactual`."""
    return Trajectory(
        subject=subject, quantity=quantity, kind=COUNTERFACTUAL, as_of=as_of,
        points=tuple(Point(at=d, value=v) for d, v in points),
        counterfactual_type=cf.cf_type, intervention=cf.intervention,
        vintage_cutoff=vintage_cutoff, source="econ.counterfactual",
        uncertainty=cf.uncertainty)


# =============================================================================
# COMPARISON
# =============================================================================

@dataclass(frozen=True)
class Divergence:
    """Where an expected path and an actual one parted company."""

    quantity: str
    first_divergence_at: str
    max_gap: float
    max_gap_at: str
    expected_direction: str
    actual_direction: str
    direction_agreed: bool
    n_compared: int

    def statement(self) -> str:
        if self.direction_agreed:
            return (f"{self.quantity}: expected and actual both "
                    f"{self.actual_direction}; largest gap "
                    f"{self.max_gap:+.3f} at {self.max_gap_at}")
        return (f"{self.quantity}: expected {self.expected_direction}, "
                f"actual {self.actual_direction}; they part at "
                f"{self.first_divergence_at}, largest gap "
                f"{self.max_gap:+.3f} at {self.max_gap_at}")

    def as_dict(self) -> dict:
        return {"quantity": self.quantity,
                "first_divergence_at": self.first_divergence_at,
                "max_gap": self.max_gap, "max_gap_at": self.max_gap_at,
                "expected_direction": self.expected_direction,
                "actual_direction": self.actual_direction,
                "direction_agreed": self.direction_agreed,
                "n_compared": self.n_compared,
                "statement": self.statement()}


def compare(expected: Trajectory, actual: Trajectory, *,
            allow_cutoff_mismatch: str = "") -> Divergence:
    """Expected against actual, refusing an unfair comparison.

    An ACTUAL built from today's data against an EXPECTED built from 2015's
    is how a model looks prescient, so mismatched cutoffs are refused unless
    the caller states why the mismatch is intended.
    """
    require(expected.kind == EXPECTED,
            f"first argument is {expected.kind}, expected EXPECTED")
    require(actual.kind == ACTUAL,
            f"second argument is {actual.kind}, expected ACTUAL")
    require(expected.quantity == actual.quantity,
            f"comparing {expected.quantity} with {actual.quantity}")
    if (expected.vintage_cutoff and actual.vintage_cutoff
            and expected.vintage_cutoff != actual.vintage_cutoff
            and not allow_cutoff_mismatch):
        raise TrajectoryRefused(
            f"{expected.quantity}: expected was built at vintage "
            f"{expected.vintage_cutoff} and actual at "
            f"{actual.vintage_cutoff}. Comparing them scores a forecast "
            "against revisions published after it was made. Pass "
            "`allow_cutoff_mismatch` with a reason if that is intended.")

    shared = [(p.at, p.value, actual.value_at(p.at)) for p in expected.points
              if actual.value_at(p.at) is not None]
    if not shared:
        raise TrajectoryRefused(
            f"{expected.quantity}: the two trajectories share no dates")
    first_div, max_gap, max_at = "", 0.0, shared[0][0]
    for at, e, a in shared:
        gap = a - e
        if abs(gap) > abs(max_gap):
            max_gap, max_at = gap, at
        if not first_div and abs(gap) > 1e-9:
            first_div = at
    return Divergence(
        quantity=expected.quantity, first_divergence_at=first_div or "never",
        max_gap=round(max_gap, 5), max_gap_at=max_at,
        expected_direction=expected.direction,
        actual_direction=actual.direction,
        direction_agreed=expected.direction == actual.direction,
        n_compared=len(shared))


def summarise(trajectories: Sequence[Trajectory]) -> dict:
    by_kind = {k: 0 for k in KINDS}
    for t in trajectories:
        by_kind[t.kind] += 1
    return {"contract": CONTRACT, "trajectories": len(trajectories),
            "by_kind": by_kind,
            "counterfactual_types": sorted(
                {t.counterfactual_type for t in trajectories
                 if t.counterfactual_type}),
            "quantities": sorted({t.quantity for t in trajectories}),
            "labels": [t.label() for t in trajectories]}

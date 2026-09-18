"""What the engine expected the economy to do, and what it got instead.

WHY A DIRECTION IS NOT ENOUGH
-----------------------------
`macro_state` can say inflation moved UP. That is compatible with an economy
running hot and an economy cooling more slowly than everyone assumed, and
those two support opposite decisions. The fact that changes a plan is not the
move, it is the move RELATIVE TO WHAT WAS EXPECTED — and until something in
this engine writes down an expectation in advance, no observation can be a
surprise, because there was nothing for it to disagree with.

WHY THE BASELINES ARE HERE AND NOT SOMEWHERE CLEVERER
-----------------------------------------------------
Economic series are hard to beat. A random walk — "next month is this month" —
is the honest opponent for almost every macro forecast, and a model that
cannot beat it has not learned anything about the economy; it has learned to
produce more decimal places. So the baselines are first-class citizens with
the same interface as anything sophisticated, and `skill` is measured against
the random walk rather than against zero.

THE TEMPORAL WALL
-----------------
An expectation is only an expectation if it was formed before the answer was
publishable. `forecast` therefore takes `made_at` and reads the ledger through
`as_known_at`, and `reconcile` REFUSES a figure that was already public when
the forecast was made. Without that refusal every method scores perfectly and
the whole layer becomes an expensive way to copy a number.

WHAT A SURPRISE IS NOT
----------------------
A surprise is not a claim that anything will happen next. A big miss on
Canadian employment does not mean a Canadian company will miss its guidance;
it means one number differed from one expectation. Turning that into a company
statement requires an exposure and a mechanism, exactly as `macro_state`
refuses to do on its own.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import macro_state as MS

CONTRACT = "macro_expectation.v1"

# --- how the expectation was formed -----------------------------------------
#
# Every one of these is deliberately simple. They exist to be BEATEN, and a
# baseline that is already sophisticated cannot tell you whether sophistication
# helped.
RANDOM_WALK = "RANDOM_WALK"          # next value is this value
DRIFT = "DRIFT"                      # this value plus the average step
HISTORICAL_MEAN = "HISTORICAL_MEAN"  # the long-run average
ROLLING_MEAN = "ROLLING_MEAN"        # the average of the last k
SEASONAL_NAIVE = "SEASONAL_NAIVE"    # the value one year ago
AR1 = "AR1"                          # first-order autoregression, OLS

METHODS = (RANDOM_WALK, DRIFT, HISTORICAL_MEAN, ROLLING_MEAN,
           SEASONAL_NAIVE, AR1)

#: The opponent. Skill is measured against this and nothing else, because
#: "better than the historical mean" is a bar a broken clock clears.
BENCHMARK = RANDOM_WALK

# --- what the surprise was --------------------------------------------------
ABOVE = "ABOVE"
BELOW = "BELOW"
IN_LINE = "IN_LINE"
SURPRISE_DIRECTIONS = (ABOVE, BELOW, IN_LINE)

#: A miss inside this many residual standard deviations is not news.
IN_LINE_SIGMA = 1.0


class ExpectationRejected(ValueError):
    """An expectation that could not have been made when it claims."""


class Foresight(ExpectationRejected):
    """Raised when a forecast is scored against a figure it could have read."""


@dataclass(frozen=True)
class Expectation:
    """One dated prediction of one series, formed from one visible history."""

    series_id: str
    state_kind: str
    area: str
    target_period: str
    method: str
    value: float
    #: A prediction interval, in the units of the series. Empty when the
    #: history is too short to estimate dispersion — and empty is reported,
    #: never replaced with a comfortable default.
    low: Optional[float] = None
    high: Optional[float] = None
    sigma: Optional[float] = None
    #: The moment the forecast was formed. Everything it may read is bounded
    #: by this date.
    made_at: str = ""
    observations_used: int = 0
    note: str = ""

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise ExpectationRejected(f"unknown method {self.method!r}")
        if not self.made_at:
            raise ExpectationRejected(
                "an expectation with no date is not a prediction; it cannot "
                "be shown to have preceded the figure it is scored against")
        if not self.target_period:
            raise ExpectationRejected("an expectation needs a target period")

    @property
    def has_interval(self) -> bool:
        return self.low is not None and self.high is not None

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, has_interval=self.has_interval)
        return d


@dataclass(frozen=True)
class Surprise:
    """An observation set against what was expected of it."""

    expectation: Expectation
    observed: float
    surprise: float
    direction: str
    #: The miss in residual standard deviations, when dispersion is known.
    #: None is not zero: an unknown-sized surprise is not a small one.
    standardised: Optional[float] = None
    covered: Optional[bool] = None
    observed_published_at: str = ""

    @property
    def absolute(self) -> float:
        return abs(self.surprise)

    def as_dict(self) -> dict:
        return {"contract": CONTRACT,
                "series_id": self.expectation.series_id,
                "state_kind": self.expectation.state_kind,
                "area": self.expectation.area,
                "target_period": self.expectation.target_period,
                "method": self.expectation.method,
                "expected": self.expectation.value,
                "observed": self.observed,
                "surprise": self.surprise,
                "direction": self.direction,
                "standardised": self.standardised,
                "covered": self.covered,
                "made_at": self.expectation.made_at,
                "observed_published_at": self.observed_published_at}


def _series(observations: Sequence[MS.MacroObservation], series_id: str,
            *, as_of: str) -> List[MS.MacroObservation]:
    """The vintage of one series that was readable on `as_of`, in order."""
    mine = [o for o in MS.as_known_at(observations, as_of)
            if o.series_id == series_id]
    mine.sort(key=lambda o: o.reference_period)
    return mine


def _dispersion(values: Sequence[float], fitted: Sequence[float]
                ) -> Optional[float]:
    residuals = [v - f for v, f in zip(values, fitted)]
    if len(residuals) < 3:
        return None
    mean = sum(residuals) / len(residuals)
    var = sum((r - mean) ** 2 for r in residuals) / (len(residuals) - 1)
    return math.sqrt(var) if var > 0 else None


def _ar1_fit(values: Sequence[float]) -> Optional[Tuple[float, float]]:
    """OLS of x[t] on x[t-1]. Returns (intercept, slope), or nothing.

    Hand-rolled rather than pulled from a library: two coefficients from a
    dozen points does not need a dependency, and a dependency here would make
    the baseline layer harder to install than the thing it is benchmarking.
    """
    if len(values) < 4:
        return None
    xs, ys = list(values[:-1]), list(values[1:])
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return (my - slope * mx, slope)


def forecast(observations: Sequence[MS.MacroObservation], *, series_id: str,
             target_period: str, made_at: str, method: str = RANDOM_WALK,
             window: int = 6, seasonal_lag: int = 12) -> Optional[Expectation]:
    """What `method` expected of `series_id` for `target_period`, at `made_at`.

    Reads only the vintage available on `made_at`, and only periods strictly
    before the target. Returns None when the visible history cannot support
    the method — an under-determined forecast is an absence, not a zero.
    """
    if method not in METHODS:
        raise ExpectationRejected(f"unknown method {method!r}")
    history = [o for o in _series(observations, series_id, as_of=made_at)
               if o.reference_period < target_period]
    if not history:
        return None
    values = [o.value for o in history]
    last = history[-1]
    low = high = sigma = None
    note = ""

    if method == RANDOM_WALK:
        value = values[-1]
        fitted = values[:-1]
        sigma = _dispersion(values[1:], fitted)
    elif method == DRIFT:
        if len(values) < 2:
            return None
        steps = [b - a for a, b in zip(values, values[1:])]
        value = values[-1] + sum(steps) / len(steps)
        sigma = _dispersion(steps, [sum(steps) / len(steps)] * len(steps))
    elif method == HISTORICAL_MEAN:
        value = sum(values) / len(values)
        sigma = _dispersion(values, [value] * len(values))
    elif method == ROLLING_MEAN:
        if len(values) < 2:
            return None
        take = values[-min(window, len(values)):]
        value = sum(take) / len(take)
        sigma = _dispersion(take, [value] * len(take))
        note = f"window={len(take)}"
    elif method == SEASONAL_NAIVE:
        if len(values) <= seasonal_lag:
            return None
        value = values[-seasonal_lag]
        pairs = list(zip(values[seasonal_lag:], values[:-seasonal_lag]))
        sigma = _dispersion([a for a, _ in pairs], [b for _, b in pairs])
        note = f"lag={seasonal_lag}"
    else:  # AR1
        fit = _ar1_fit(values)
        if fit is None:
            return None
        intercept, slope = fit
        value = intercept + slope * values[-1]
        fitted = [intercept + slope * v for v in values[:-1]]
        sigma = _dispersion(values[1:], fitted)
        note = f"slope={slope:.4f}"

    if sigma:
        # A two-sigma band. Named as an assumption rather than a probability:
        # nothing here establishes that macro residuals are normal, and
        # calling this "95%" would be a claim the data has not earned.
        low, high = value - 2 * sigma, value + 2 * sigma
        note = (note + "; " if note else "") + \
            "interval is two residual sigma, not a fitted quantile"

    return Expectation(
        series_id=series_id, state_kind=last.state_kind, area=last.area,
        target_period=target_period, method=method, value=value,
        low=low, high=high, sigma=sigma, made_at=made_at,
        observations_used=len(values), note=note)


def reconcile(expectation: Expectation,
              observations: Sequence[MS.MacroObservation], *,
              as_of: str) -> Optional[Surprise]:
    """Set the expectation against the figure that eventually arrived.

    REFUSES A FIGURE THAT WAS ALREADY PUBLIC. If the target period's figure
    was published on or before `made_at`, the forecast was not a forecast, and
    scoring it would tell you only that the engine can read. Every method
    would look excellent and the comparison between them — the entire point of
    keeping six of them — would be noise.
    """
    matches = [o for o in MS.as_known_at(observations, as_of)
               if o.series_id == expectation.series_id
               and o.reference_period == expectation.target_period]
    if not matches:
        return None
    actual = max(matches, key=lambda o: o.published_at)
    if actual.published_at[:10] <= expectation.made_at[:10]:
        raise Foresight(
            f"{actual.series_id} for {actual.reference_period} was published "
            f"{actual.published_at}, on or before the forecast date "
            f"{expectation.made_at}: this is a lookup, not a prediction")

    surprise = actual.value - expectation.value
    standardised = (surprise / expectation.sigma) if expectation.sigma else None
    if standardised is None:
        direction = IN_LINE if surprise == 0 else (
            ABOVE if surprise > 0 else BELOW)
    elif abs(standardised) <= IN_LINE_SIGMA:
        direction = IN_LINE
    else:
        direction = ABOVE if surprise > 0 else BELOW
    covered = (None if not expectation.has_interval
               else bool(expectation.low <= actual.value <= expectation.high))
    return Surprise(expectation=expectation, observed=actual.value,
                    surprise=surprise, direction=direction,
                    standardised=standardised, covered=covered,
                    observed_published_at=actual.published_at)


# --- scoring ----------------------------------------------------------------

@dataclass(frozen=True)
class MethodScore:
    """How one method did on one series, against the random walk."""

    series_id: str
    method: str
    n: int
    mae: float
    rmse: float
    bias: float
    coverage: Optional[float]
    #: RMSE relative to the benchmark. Below 1 is skill; at or above 1 is a
    #: more complicated way of being no better.
    skill_vs_benchmark: Optional[float] = None

    @property
    def beats_benchmark(self) -> bool:
        return (self.skill_vs_benchmark is not None
                and self.skill_vs_benchmark < 1.0)

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, beats_benchmark=self.beats_benchmark)
        return d


def _score(series_id: str, method: str,
           surprises: Sequence[Surprise]) -> Optional[MethodScore]:
    if not surprises:
        return None
    errs = [s.surprise for s in surprises]
    n = len(errs)
    covered = [s.covered for s in surprises if s.covered is not None]
    return MethodScore(
        series_id=series_id, method=method, n=n,
        mae=sum(abs(e) for e in errs) / n,
        rmse=math.sqrt(sum(e * e for e in errs) / n),
        bias=sum(errs) / n,
        coverage=(sum(1 for c in covered if c) / len(covered)
                  if covered else None))


def backtest(observations: Sequence[MS.MacroObservation], *, series_id: str,
             methods: Sequence[str] = METHODS, min_history: int = 6,
             as_of: str = "9999-12-31") -> dict:
    """Walk the series forward, forecasting each period from its own past.

    Each origin is the day BEFORE the target figure was published, so the
    method sees the vintage a forecaster would have had and never the answer.
    That single choice is the difference between a backtest and a replay of
    the data through a formula.
    """
    ordered = _series(observations, series_id, as_of=as_of)
    if len(ordered) <= min_history:
        return {"contract": CONTRACT, "series_id": series_id,
                "scored": 0, "scores": [],
                "note": (f"{len(ordered)} observations is not enough history "
                         f"to score a forecast; {min_history + 1} needed")}

    per_method: Dict[str, List[Surprise]] = {m: [] for m in methods}
    for idx in range(min_history, len(ordered)):
        target = ordered[idx]
        origin = _day_before(target.published_at)
        for method in methods:
            exp = forecast(observations, series_id=series_id,
                           target_period=target.reference_period,
                           made_at=origin, method=method)
            if exp is None:
                continue
            try:
                got = reconcile(exp, observations, as_of=as_of)
            except Foresight:
                # Two figures for one period published a day apart: skip the
                # origin rather than score a lookup.
                continue
            if got is not None:
                per_method[method].append(got)

    scores = [s for s in (_score(series_id, m, per_method[m]) for m in methods)
              if s is not None]
    bench = next((s for s in scores if s.method == BENCHMARK), None)
    if bench and bench.rmse > 0:
        scores = [dataclasses.replace(s, skill_vs_benchmark=round(
            s.rmse / bench.rmse, 4)) for s in scores]
    scores.sort(key=lambda s: s.rmse)
    return {
        "contract": CONTRACT,
        "series_id": series_id,
        "scored": sum(len(v) for v in per_method.values()),
        "origins": len(ordered) - min_history,
        "benchmark": BENCHMARK,
        "scores": [s.as_dict() for s in scores],
        "best": scores[0].method if scores else "",
        "best_beats_benchmark": bool(scores and scores[0].beats_benchmark),
        "note": ("skill below 1.0 is a lower RMSE than the random walk; a "
                 "method that does not beat it has added complexity, not "
                 "knowledge"),
    }


def _day_before(date_str: str) -> str:
    import datetime
    day = datetime.date.fromisoformat(str(date_str)[:10])
    return (day - datetime.timedelta(days=1)).isoformat()


def summarise(surprises: Sequence[Surprise]) -> dict:
    """What the economy did that nobody expected."""
    by_direction: Dict[str, int] = {}
    for s in surprises:
        by_direction[s.direction] = by_direction.get(s.direction, 0) + 1
    notable = sorted((s for s in surprises if s.direction != IN_LINE),
                     key=lambda s: -(abs(s.standardised or 0)))
    return {
        "contract": CONTRACT,
        "reconciled": len(surprises),
        "by_direction": by_direction,
        "surprising": len(notable),
        "largest": [s.as_dict() for s in notable[:5]],
        "note": ("a surprise is a disagreement between one figure and one "
                 "expectation; it is not a claim about any company"),
    }

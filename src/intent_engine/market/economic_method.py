"""Which method works for which question, measured rather than assumed.

WHAT THIS IS FOR
----------------
The goal is not "we implemented forecasting methods". Nine estimators
implemented to satisfy a list is nine estimators nobody has a reason to trust.
The goal is that the engine can say:

    for short-horizon rate forecasting in this regime, AR1 currently beats
    drift; for unemployment, nothing has beaten persistence

and can show the held-out numbers behind both halves of that sentence.

A REGISTRY ENTRY IS NOT AN IMPLEMENTATION
-----------------------------------------
`METHODS` declares what each method needs, what it assumes, and how it fails.
Most entries have no estimator here and say so. That is deliberate: the
registry's job is to let a caller ask "may I use difference-in-differences for
this question?" and get a reasoned no, which is more useful than an estimate
produced by a method whose assumptions were never checked.

BASELINES ARE NOT A FORMALITY
-----------------------------
Persistence — "tomorrow looks like today" — is very hard to beat on
macroeconomic levels, and a method that does not beat it has demonstrated
nothing however sophisticated it is. So the baselines are implemented first
and every other method is scored against them, not against each other.

WALK-FORWARD, NEVER IN-SAMPLE
-----------------------------
Each prediction is made from data strictly before the point it predicts. A
model fitted on the whole series and scored on the whole series is measuring
its own memory. The split is enforced by construction here rather than left to
the caller.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

CONTRACT = "economic_method.v1"

# --- what a method can be asked -----------------------------------------------
FORECAST_LEVEL = "FORECAST_LEVEL"
FORECAST_CHANGE = "FORECAST_CHANGE"
EFFECT_OF_EVENT = "EFFECT_OF_EVENT"
EFFECT_OF_POLICY = "EFFECT_OF_POLICY"
QUESTION_TYPES = (FORECAST_LEVEL, FORECAST_CHANGE, EFFECT_OF_EVENT,
                  EFFECT_OF_POLICY)

# --- method names -------------------------------------------------------------
PERSISTENCE = "PERSISTENCE_BASELINE"
DRIFT = "DRIFT"
AR1 = "AR1"
STATE_SPACE = "STATE_SPACE"
EVENT_STUDY = "EVENT_STUDY"
INTERRUPTED_TIME_SERIES = "INTERRUPTED_TIME_SERIES"
DIFFERENCE_IN_DIFFERENCES = "DIFFERENCE_IN_DIFFERENCES"
SYNTHETIC_CONTROL = "SYNTHETIC_CONTROL"
LOCAL_PROJECTION = "LOCAL_PROJECTION"


class MethodRefused(ValueError):
    """A method was asked for a question its assumptions do not support."""


@dataclass(frozen=True)
class EconomicMethod:
    """What a method needs, assumes, and how it fails."""

    name: str
    question_types: Tuple[str, ...]
    minimum_sample: int
    assumptions: Tuple[str, ...] = ()
    inputs: Tuple[str, ...] = ("one numeric series",)
    output: str = "point forecast"
    failure_modes: Tuple[str, ...] = ()
    #: None means DECLARED BUT NOT IMPLEMENTED. Reported, never silently
    #: substituted with something simpler.
    estimator: Optional[Callable] = None
    is_baseline: bool = False

    @property
    def implemented(self) -> bool:
        return self.estimator is not None

    def as_dict(self) -> dict:
        out = {k: v for k, v in dataclasses.asdict(self).items()
               if k != "estimator"}
        out.update(contract=CONTRACT, implemented=self.implemented)
        return out


# --- the baselines, implemented ------------------------------------------------

def _persistence(history: Sequence[float]) -> float:
    """Tomorrow looks like today. The number every method must beat."""
    return float(history[-1])


def _drift(history: Sequence[float]) -> float:
    """Today plus the average step so far."""
    if len(history) < 2:
        return float(history[-1])
    span = (history[-1] - history[0]) / (len(history) - 1)
    return float(history[-1] + span)


def _ar1(history: Sequence[float]) -> float:
    """Mean-reverting first-order autoregression, fitted on the history given.

    Fitted by least squares on (x_t, x_{t+1}) pairs. Falls back to persistence
    when the regressor has no variance — a constant series has no slope, and
    inventing one would produce confident nonsense.
    """
    if len(history) < 3:
        return float(history[-1])
    xs, ys = list(history[:-1]), list(history[1:])
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    var = sum((x - mean_x) ** 2 for x in xs)
    if var <= 1e-12:
        return float(history[-1])
    beta = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var
    alpha = mean_y - beta * mean_x
    return float(alpha + beta * history[-1])


METHODS: Dict[str, EconomicMethod] = {
    m.name: m for m in (
        EconomicMethod(
            name=PERSISTENCE, question_types=(FORECAST_LEVEL,),
            minimum_sample=1, estimator=_persistence, is_baseline=True,
            assumptions=("the series has no reliable short-horizon drift",),
            failure_modes=("misses every turning point, by construction",
                           "looks excellent on a slow-moving level series, "
                           "which is why beating it is the bar")),
        EconomicMethod(
            name=DRIFT, question_types=(FORECAST_LEVEL, FORECAST_CHANGE),
            minimum_sample=2, estimator=_drift, is_baseline=True,
            assumptions=("the average historical step continues",),
            failure_modes=("extrapolates a trend through a regime change",
                           "a single outlier at either end tilts the slope")),
        EconomicMethod(
            name=AR1, question_types=(FORECAST_LEVEL, FORECAST_CHANGE),
            minimum_sample=8, estimator=_ar1,
            assumptions=("the series is roughly stationary over the window",
                         "one lag carries the dependence"),
            failure_modes=("a unit root makes the fitted coefficient "
                           "meaningless while the fit looks fine",
                           "a structural break is absorbed into the mean")),
        # --- declared, not implemented -------------------------------------
        EconomicMethod(
            name=STATE_SPACE, question_types=(FORECAST_LEVEL,),
            minimum_sample=40,
            assumptions=("an observation model and a state model are both "
                         "specified rather than fitted post hoc",),
            failure_modes=("degenerates to a smoother nobody can interpret",)),
        EconomicMethod(
            name=EVENT_STUDY, question_types=(EFFECT_OF_EVENT,),
            minimum_sample=30, output="effect over a window",
            inputs=("a dated event", "a series spanning the window"),
            assumptions=("the event is isolated within its window",
                         "no confounding event shares the window",
                         "the window was chosen before the effect was seen"),
            failure_modes=("a window widened until the effect appears",
                           "clustered events double-count one shock")),
        EconomicMethod(
            name=INTERRUPTED_TIME_SERIES,
            question_types=(EFFECT_OF_POLICY,), minimum_sample=40,
            output="level and slope change",
            assumptions=("the pre-period trend would have continued",
                         "the interruption date is known and not chosen"),
            failure_modes=("anticipation before the stated date",)),
        EconomicMethod(
            name=DIFFERENCE_IN_DIFFERENCES,
            question_types=(EFFECT_OF_POLICY,), minimum_sample=40,
            inputs=("a treated series", "a control series"),
            output="average treatment effect on the treated",
            assumptions=("parallel trends in the pre-period",
                         "no anticipation",
                         "no compositional change in either group"),
            failure_modes=("parallel trends assumed rather than shown",
                           "a control chosen because it makes the result")),
        EconomicMethod(
            name=SYNTHETIC_CONTROL, question_types=(EFFECT_OF_POLICY,),
            minimum_sample=40,
            inputs=("a treated unit", "a donor pool"),
            output="treated minus synthetic path",
            assumptions=("the donor pool can reproduce the pre-period",
                         "no donor is itself affected by the treatment"),
            failure_modes=("overfitting the pre-period with a large pool",)),
        EconomicMethod(
            name=LOCAL_PROJECTION, question_types=(EFFECT_OF_EVENT,),
            minimum_sample=60, output="impulse response by horizon",
            assumptions=("the shock is identified, not merely dated",),
            failure_modes=("a shock series that is itself endogenous",)),
    )
}


def eligible(question_type: str, sample: int) -> List[EconomicMethod]:
    """Methods that could answer this question with this much data.

    Returns implemented AND unimplemented matches; the caller can see that a
    method was appropriate and unavailable, which is a different fact from
    the method being wrong for the job.
    """
    return [m for m in METHODS.values()
            if question_type in m.question_types and sample >= m.minimum_sample]


def require(name: str, question_type: str, sample: int) -> EconomicMethod:
    """Fetch a method or refuse, with the reason."""
    method = METHODS.get(name)
    if method is None:
        raise MethodRefused(f"unknown method {name!r}")
    if question_type not in method.question_types:
        raise MethodRefused(
            f"{name} answers {list(method.question_types)}, not "
            f"{question_type!r}")
    if sample < method.minimum_sample:
        raise MethodRefused(
            f"{name} needs {method.minimum_sample} observations, got {sample}")
    if not method.implemented:
        raise MethodRefused(
            f"{name} is declared but not implemented here; substituting a "
            "simpler method under its name would misreport what was run")
    return method


# --- walk-forward evaluation ---------------------------------------------------

@dataclass(frozen=True)
class MethodPerformance:
    """How one method did on one question, on data it had not seen."""

    method: str
    question_type: str
    series: str
    predictions: int
    mae: Optional[float]
    rmse: Optional[float]
    #: Skill against persistence. Positive means better. None when persistence
    #: itself could not be scored, which is the only honest answer then.
    skill_vs_persistence: Optional[float] = None
    note: str = ""

    @property
    def beat_baseline(self) -> Optional[bool]:
        if self.skill_vs_persistence is None:
            return None
        return self.skill_vs_persistence > 0

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT, beat_baseline=self.beat_baseline)
        return out


def walk_forward(series: Sequence[float], method: EconomicMethod, *,
                 minimum_train: int = 0) -> Tuple[List[float], List[float]]:
    """Predict each point from data strictly before it.

    The split is enforced here rather than trusted to the caller, because
    in-sample scoring is the single easiest way to make a method look good and
    it leaves no trace in the output.
    """
    start = max(minimum_train or method.minimum_sample, 1)
    predicted: List[float] = []
    actual: List[float] = []
    for i in range(start, len(series)):
        history = series[:i]
        predicted.append(method.estimator(history))
        actual.append(float(series[i]))
    return predicted, actual


def score(series: Sequence[float], name: str, *, question_type=FORECAST_LEVEL,
          series_name: str = "", minimum_train: int = 0) -> MethodPerformance:
    method = require(name, question_type, len(series))
    predicted, actual = walk_forward(series, method,
                                     minimum_train=minimum_train)
    if not predicted:
        return MethodPerformance(
            method=name, question_type=question_type, series=series_name,
            predictions=0, mae=None, rmse=None,
            note="not enough observations after the training window to make a "
                 "single out-of-sample prediction")
    errors = [p - a for p, a in zip(predicted, actual)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    return MethodPerformance(
        method=name, question_type=question_type, series=series_name,
        predictions=len(predicted), mae=round(mae, 6), rmse=round(rmse, 6),
        note="walk-forward; every prediction used only earlier observations")


def compare(series: Sequence[float], *, names: Sequence[str] = (),
            series_name: str = "",
            question_type: str = FORECAST_LEVEL) -> dict:
    """Score several methods on ONE training window so they are comparable.

    The window is the largest `minimum_sample` among the methods compared. A
    method scored from an earlier start point gets more predictions AND easier
    ones, so comparing methods on their own windows silently favours whichever
    needs least history.
    """
    names = list(names) or [PERSISTENCE, DRIFT, AR1]
    usable, refused = [], {}
    for name in names:
        try:
            usable.append(require(name, question_type, len(series)))
        except MethodRefused as exc:
            refused[name] = str(exc)
    if not usable:
        return {"contract": CONTRACT, "series": series_name,
                "observations": len(series), "results": [], "refused": refused,
                "best": "", "note": "no declared method could take this series"}

    window = max(m.minimum_sample for m in usable)
    scored = [score(series, m.name, question_type=question_type,
                    series_name=series_name, minimum_train=window)
              for m in usable]
    base = next((s for s in scored if s.method == PERSISTENCE), None)
    out = []
    for got in scored:
        skill = None
        if base and base.mae not in (None, 0) and got.mae is not None:
            skill = round((base.mae - got.mae) / base.mae, 6)
        out.append(dataclasses.replace(got, skill_vs_persistence=skill))
    ranked = sorted([s for s in out if s.mae is not None],
                    key=lambda s: s.mae)
    return {
        "contract": CONTRACT,
        "series": series_name,
        "observations": len(series),
        "training_window": window,
        "results": [s.as_dict() for s in out],
        "refused": refused,
        "best": ranked[0].method if ranked else "",
        "beat_persistence": [s.method for s in out
                             if s.beat_baseline is True],
        "note": ("all methods scored on one training window so the "
                 "comparison is like-for-like; skill is relative MAE "
                 "improvement over persistence"),
    }


def summarise() -> dict:
    implemented = [m for m in METHODS.values() if m.implemented]
    return {
        "contract": CONTRACT,
        "methods": len(METHODS),
        "implemented": len(implemented),
        "declared_only": len(METHODS) - len(implemented),
        "baselines": [m.name for m in METHODS.values() if m.is_baseline],
        "by_question": {q: sorted(m.name for m in METHODS.values()
                                  if q in m.question_types)
                        for q in QUESTION_TYPES},
        "registry": [m.as_dict() for m in METHODS.values()],
        "note": ("a declared method with no estimator is reported as such; "
                 "it is never satisfied by running a simpler one under its "
                 "name"),
    }

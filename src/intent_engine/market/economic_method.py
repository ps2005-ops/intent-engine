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
import hashlib
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
    #: substituted with something simpler. Takes one history and returns the
    #: next value; this is the FORECASTING signature and `walk_forward` calls
    #: it directly.
    estimator: Optional[Callable] = None
    #: The EFFECT signature, which is a different function of different
    #: arguments: a treated unit, a comparison set, and a treatment time. Kept
    #: as a separate field rather than overloading `estimator` because
    #: `walk_forward` calls `estimator(history)` positionally, so a synthetic
    #: control bound there would satisfy `implemented`, pass `require`, and
    #: then raise inside the scorer — a method reported as available that
    #: cannot be run is worse than one honestly reported as declared-only.
    effect_estimator: Optional[Callable] = None
    is_baseline: bool = False

    @property
    def implemented(self) -> bool:
        return self.estimator is not None or self.effect_estimator is not None

    @property
    def forecasts(self) -> bool:
        return self.estimator is not None

    @property
    def estimates_effects(self) -> bool:
        return self.effect_estimator is not None

    def as_dict(self) -> dict:
        out = {k: v for k, v in dataclasses.asdict(self).items()
               if k not in ("estimator", "effect_estimator")}
        out.update(contract=CONTRACT, implemented=self.implemented,
                   forecasts=self.forecasts,
                   estimates_effects=self.estimates_effects)
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


def _fit_ar1(history: Sequence[float]) -> Optional[Tuple[float, float]]:
    """Least squares on (x_t, x_{t+1}) pairs, or None when there is no slope.

    Returned rather than folded into the prediction because the fitted
    coefficient is itself the thing the stationarity assumption is ABOUT: a
    beta at one says the series has a unit root and the model's mean
    reversion is a finite-sample artefact. Testing that on a statistic other
    than the coefficient the method actually fits would be testing a
    different model.
    """
    if len(history) < 3:
        return None
    xs, ys = list(history[:-1]), list(history[1:])
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    var = sum((x - mean_x) ** 2 for x in xs)
    if var <= 1e-12:
        return None
    beta = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var
    return mean_y - beta * mean_x, beta


def _ar1(history: Sequence[float]) -> float:
    """Mean-reverting first-order autoregression, fitted on the history given.

    Falls back to persistence when the regressor has no variance — a constant
    series has no slope, and inventing one would produce confident nonsense.
    """
    fit = _fit_ar1(history)
    if fit is None:
        return float(history[-1])
    alpha, beta = fit
    return float(alpha + beta * history[-1])


# --- the effect estimators, implemented elsewhere ------------------------------
#
# Imported inside the function rather than at module scope because
# `synthetic_control` names this module's method constants and importing it up
# here would close the loop. The indirection is one line and it keeps the
# dependency pointing one way: the registry knows about the estimator, the
# estimator does not know about the registry.

def _synthetic_control_estimator(treated, donors, *, treatment_index,
                                 **kwargs) -> Optional[float]:
    from . import synthetic_control

    return synthetic_control.estimator(
        treated, donors, treatment_index=treatment_index, **kwargs)


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
            effect_estimator=_synthetic_control_estimator,
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
    # IMPLEMENTED FOR WHICH JOB. A method can now carry a forecaster, an
    # effect estimator, or both, and the question type decides which one is
    # being asked for. Without this, SYNTHETIC_CONTROL — implemented for
    # EFFECT_OF_POLICY only — would pass `require` for a forecast and hand
    # `walk_forward` a None to call.
    forecasting = question_type in (FORECAST_LEVEL, FORECAST_CHANGE)
    if forecasting and not method.forecasts:
        raise MethodRefused(
            f"{name} estimates effects, not forecasts; it has no estimator "
            f"that could answer {question_type!r} from one series")
    if not forecasting and not method.estimates_effects:
        raise MethodRefused(
            f"{name} forecasts a series and has no effect estimator; "
            f"{question_type!r} needs a treated unit and a comparison set")
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


# --- assumptions, tested rather than listed -----------------------------------
#
# WHY A LEDGER AND NOT A DOCSTRING
# --------------------------------
# `EconomicMethod.assumptions` is a tuple of sentences. Sentences do not fail.
# A method whose assumptions are written down and never checked produces
# exactly the same number as one whose assumptions hold, and the number is
# reported with the same confidence — which is how "AR1 beat persistence"
# becomes a causal statement about an economy that happened to be trending.
#
# So each assumption gets a test, a result, and the evidence the result came
# from. An assumption nobody can test is recorded as UNTESTED, which is a
# third thing and must not be read as passing.

PASSED = "PASSED"
FAILED = "FAILED"
UNTESTED = "UNTESTED"
ASSUMPTION_RESULTS = (PASSED, FAILED, UNTESTED)

#: A failed CRITICAL assumption forbids the causal reading. A failed
#: ADVISORY one bounds it and is reported beside the estimate.
CRITICAL = "CRITICAL"
ADVISORY = "ADVISORY"
SEVERITIES = (CRITICAL, ADVISORY)

#: What may be said once the assumptions have been read.
USEFUL = "USEFUL"                      # assumptions hold; the estimate stands
BOUNDED = "BOUNDED"                    # advisory failures; stated limits
REFUSED = "REFUSED"                    # a critical assumption failed
NO_INCREMENTAL_VALUE = "NO_INCREMENTAL_VALUE"   # ran, did not beat the baseline
STANDINGS = (USEFUL, BOUNDED, REFUSED, NO_INCREMENTAL_VALUE)


@dataclass(frozen=True)
class MethodAssumptionCheck:
    """One assumption of one method, on one series, and what testing it said."""

    method: str
    question: str
    assumption: str
    severity: str
    result: str
    evidence: str
    series: str = ""
    statistic: Optional[float] = None
    threshold: Optional[float] = None
    as_of: str = ""

    def __post_init__(self) -> None:
        if self.result not in ASSUMPTION_RESULTS:
            raise MethodRefused(f"unknown assumption result {self.result!r}")
        if self.severity not in SEVERITIES:
            raise MethodRefused(f"unknown severity {self.severity!r}")
        if not self.evidence.strip():
            raise MethodRefused(
                f"the check of {self.assumption!r} states no evidence; an "
                "assumption recorded as passing with nothing behind it is "
                "weaker than one recorded as untested, because it reads as "
                "having been checked")

    @property
    def tested(self) -> bool:
        return self.result != UNTESTED

    @property
    def blocks_causal_reading(self) -> bool:
        return self.result == FAILED and self.severity == CRITICAL

    @property
    def check_id(self) -> str:
        raw = "|".join((self.method, self.series, self.assumption,
                        self.as_of))
        return "mac_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT, record="method_assumption_check",
                   check_id=self.check_id, tested=self.tested,
                   blocks_causal_reading=self.blocks_causal_reading)
        return out


def _first_difference(series: Sequence[float]) -> List[float]:
    return [series[i + 1] - series[i] for i in range(len(series) - 1)]


def _lag1_autocorrelation(values: Sequence[float]) -> Optional[float]:
    if len(values) < 3:
        return None
    n = len(values)
    mean = sum(values) / n
    denominator = sum((v - mean) ** 2 for v in values)
    if denominator <= 1e-12:
        return None
    numerator = sum((values[i] - mean) * (values[i + 1] - mean)
                    for i in range(n - 1))
    return numerator / denominator


#: An AR(1) coefficient this close to one is a random walk for practical
#: purposes: the fitted mean reversion is an artefact of a finite sample and
#: the model's own standard errors are wrong. Not a p-value — this is a
#: deliberately blunt screen, and it is reported with the statistic so a
#: reader can disagree with the threshold rather than with a verdict.
_UNIT_ROOT_RHO = 0.98

#: Residual autocorrelation above this says one lag did not carry the
#: dependence, so the coefficient is absorbing structure it does not model.
_RESIDUAL_AC = 0.30

#: Half the sample's steps in the same direction is a drift; more than this
#: much imbalance means "no reliable short-horizon drift" is false.
_DRIFT_IMBALANCE = 0.70


def check_assumptions(series: Sequence[float], name: str, *,
                      question: str = "", series_name: str = "",
                      as_of: str = "") -> List[MethodAssumptionCheck]:
    """Test what this method assumes about THIS series.

    Every assumption the registry declares comes back with a result, so the
    count of checks always equals the count of declared assumptions. A method
    whose assumptions are partly untestable here reports UNTESTED for those
    and the caller can see the gap; silently returning only the testable ones
    would make a partial check look complete.
    """
    method = METHODS.get(name)
    if method is None:
        raise MethodRefused(f"unknown method {name!r}")

    def build(assumption, severity, result, evidence, statistic=None,
              threshold=None):
        return MethodAssumptionCheck(
            method=name, question=question, assumption=assumption,
            severity=severity, result=result, evidence=evidence,
            series=series_name, statistic=statistic, threshold=threshold,
            as_of=as_of)

    values = [float(v) for v in series]
    out: List[MethodAssumptionCheck] = []
    for assumption in method.assumptions:
        lowered = assumption.lower()

        if "stationary" in lowered:
            fit = _fit_ar1(values)
            if fit is None:
                out.append(build(
                    assumption, CRITICAL, UNTESTED,
                    f"{len(values)} observations with no variance to fit a "
                    "lag-1 coefficient on"))
            else:
                beta = fit[1]
                out.append(build(
                    assumption, CRITICAL,
                    FAILED if beta >= _UNIT_ROOT_RHO else PASSED,
                    f"fitted AR(1) coefficient {beta:.4f} against a unit-root "
                    f"screen at {_UNIT_ROOT_RHO}; at or above it the fitted "
                    "mean reversion is a finite-sample artefact",
                    statistic=round(beta, 6), threshold=_UNIT_ROOT_RHO))

        elif "one lag carries" in lowered:
            # IN-SAMPLE RESIDUALS FROM ONE FIT. The first version differenced
            # walk-forward forecasts against the actuals, which measures
            # something else entirely: an expanding-window fit chases the
            # series, so its forecast errors are negatively autocorrelated by
            # construction and every series on earth "failed". The assumption
            # is about whether one lag captured the dependence, which is a
            # question about the residuals of a single fitted model.
            residual_ac = None
            fit = _fit_ar1(values)
            if fit is not None and len(values) >= 5:
                alpha, beta = fit
                residuals = [values[i + 1] - (alpha + beta * values[i])
                             for i in range(len(values) - 1)]
                residual_ac = _lag1_autocorrelation(residuals)
            if residual_ac is None:
                out.append(build(
                    assumption, ADVISORY, UNTESTED,
                    "too few observations to leave residuals to test"))
            else:
                out.append(build(
                    assumption, ADVISORY,
                    FAILED if abs(residual_ac) > _RESIDUAL_AC else PASSED,
                    f"residual lag-1 autocorrelation {residual_ac:.4f} "
                    f"against {_RESIDUAL_AC}; above it the single lag is "
                    "absorbing structure it does not model",
                    statistic=round(residual_ac, 6),
                    threshold=_RESIDUAL_AC))

        elif "average historical step continues" in lowered:
            steps = _first_difference(values)
            if not steps:
                out.append(build(assumption, CRITICAL, UNTESTED,
                                 "a single observation has no steps"))
            else:
                up = sum(1 for s in steps if s > 0)
                share = max(up, len(steps) - up) / len(steps)
                out.append(build(
                    assumption, ADVISORY,
                    PASSED if share >= _DRIFT_IMBALANCE else FAILED,
                    f"{share:.2%} of {len(steps)} steps share one sign; "
                    f"below {_DRIFT_IMBALANCE:.0%} the historical average "
                    "step is a wash and extrapolating it is extrapolating "
                    "noise",
                    statistic=round(share, 6), threshold=_DRIFT_IMBALANCE))

        elif "no reliable short-horizon drift" in lowered:
            steps = _first_difference(values)
            if not steps:
                out.append(build(assumption, ADVISORY, UNTESTED,
                                 "a single observation has no steps"))
            else:
                up = sum(1 for s in steps if s > 0)
                share = max(up, len(steps) - up) / len(steps)
                out.append(build(
                    assumption, ADVISORY,
                    FAILED if share >= _DRIFT_IMBALANCE else PASSED,
                    f"{share:.2%} of {len(steps)} steps share one sign; at or "
                    f"above {_DRIFT_IMBALANCE:.0%} there IS a drift and "
                    "persistence is leaving it on the table",
                    statistic=round(share, 6), threshold=_DRIFT_IMBALANCE))

        else:
            # DESIGN ASSUMPTIONS, NOT DATA ASSUMPTIONS. "the window was chosen
            # before the effect was seen" is a fact about how the study was
            # run and no series can answer it. Recorded UNTESTED with the
            # reason, never quietly counted as holding.
            out.append(build(
                assumption, CRITICAL, UNTESTED,
                "this is a statement about how the study was conducted, not "
                "about the series; no test of the data can establish it"))
    return out


#: Out-of-sample predictions below which a win is suggestive, not a result.
#: C-MET-001 measured AR1 beating persistence on four 24-point series — about
#: sixteen held-out predictions each — and recorded them as suggestive rather
#: than promoting them. A standing of USEFUL on sixteen points would undo
#: that judgement silently, which is the way a careful reading gets lost:
#: not by being argued down, but by a later layer not knowing it was made.
_MINIMUM_OUT_OF_SAMPLE = 30


def interpret(checks: Sequence[MethodAssumptionCheck], *,
              beat_baseline: Optional[bool] = None,
              predictions: Optional[int] = None) -> dict:
    """What may honestly be said, given what the assumptions came to.

    REFUSED IS NOT AN ERROR. A method whose critical assumption failed still
    produced a number, and that number may be a perfectly good DESCRIPTION of
    the sample. What it may not do is carry a causal reading. Both halves are
    returned, because discarding the descriptive result would push the caller
    toward a method that fails silently instead.
    """
    failed_critical = [c for c in checks if c.blocks_causal_reading]
    failed_advisory = [c for c in checks
                       if c.result == FAILED and c.severity == ADVISORY]
    untested_critical = [c for c in checks
                         if c.result == UNTESTED and c.severity == CRITICAL]
    if failed_critical:
        standing = REFUSED
        why = ("a critical assumption failed: "
               + "; ".join(c.assumption for c in failed_critical))
    elif untested_critical:
        standing = BOUNDED
        why = ("a critical assumption could not be tested here: "
               + "; ".join(c.assumption for c in untested_critical))
    elif beat_baseline is False:
        standing = NO_INCREMENTAL_VALUE
        why = ("every assumption held and the method did not beat the "
               "baseline; that is a result about the method, not a failure "
               "of the run")
    elif failed_advisory:
        standing = BOUNDED
        why = ("an advisory assumption failed: "
               + "; ".join(c.assumption for c in failed_advisory))
    elif predictions is not None and predictions < _MINIMUM_OUT_OF_SAMPLE:
        standing = BOUNDED
        why = (f"every assumption held, on {predictions} out-of-sample "
               f"predictions against a floor of {_MINIMUM_OUT_OF_SAMPLE}; "
               "a win this size is suggestive and is not promoted")
    else:
        standing = USEFUL
        why = "every declared assumption was tested and held"
    return {
        "contract": CONTRACT,
        "standing": standing,
        "out_of_sample_predictions": predictions,
        # IDENTIFICATION REQUIRES THE CRITICAL ASSUMPTIONS TO HAVE BEEN
        # CHECKED, not merely to have avoided failing. An untested one is
        # unknown, and unknown is not permission: "the window was chosen
        # before the effect was seen" can never be established from a series,
        # and an event study that treats it as satisfied is the exact study
        # the assumption exists to stop. BOUNDED still describes the sample;
        # it just may not claim to have identified an effect.
        "causal_reading_allowed": (not failed_critical
                                   and not untested_critical
                                   and standing in (USEFUL, BOUNDED)),
        "why": why,
        "checks": len(checks),
        "tested": sum(1 for c in checks if c.tested),
        "untested": sum(1 for c in checks if not c.tested),
        "failed_critical": len(failed_critical),
        "failed_advisory": len(failed_advisory),
        "descriptive_result_retained": True,
        "note": ("a refused causal reading does not discard the estimate; it "
                 "records that the estimate describes the sample and does "
                 "not identify an effect"),
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

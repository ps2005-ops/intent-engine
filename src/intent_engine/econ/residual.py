"""§16/§17: where the textbook chain did not fire, and what moved first.

TWO TESTS, DELIBERATELY SEPARATE
--------------------------------
§16 asks whether the collective block explains the RESIDUAL left by
conventional transmission. §17 asks whether the collective signal moves
BEFORE or AFTER the thing it is supposed to explain. They are separate
because a variable can pass the first and fail the second, and that
combination has a name: it is a coincident indicator being read as a cause.

WHY A RESIDUAL TEST AND NOT A REGRESSION WITH MORE TERMS
--------------------------------------------------------
Adding the collective block to a regression and finding the fit improves is
compatible with the block being a slightly better proxy for the SAME
information the economic block already carries. The residual test is
narrower and answers the interesting question: on the origins where the
conventional mechanism pointed one way and the economy went the other, does
the collective block do better than it does everywhere else?

That is a DIFFERENCE OF DIFFERENCES, and the interval is computed on the
difference rather than on each side, because two overlapping intervals are
not a comparison.

WHY IT IS STILL NOT CAUSAL
--------------------------
`bleed.py` already says this and it bears repeating here: rates fell, demand
did not respond, therefore fear -- is a story. This module produces a
measured association on a preregistered subset. It is named `residual` and
not `cause` for that reason, and the verdict vocabulary never contains the
word.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_residual.v1"

# --- §17 classifications ----------------------------------------------------
LEADING = "LEADING"
COINCIDENT = "COINCIDENT"
LAGGING = "LAGGING"
UNRELATED = "UNRELATED"
ORDERS = (LEADING, COINCIDENT, LAGGING, UNRELATED)

#: Below this absolute correlation at every lag, the pair is UNRELATED and no
#: temporal claim is made. A lag argmax over noise is a number, not a finding.
MIN_ABS_CORRELATION = 0.15

#: Lags within this many periods of zero count as coincident rather than
#: leading. One month of apparent lead on monthly data is inside the
#: publication timing of most of these series.
COINCIDENT_BAND = 1

#: How far the driver must move over a year before the mechanism counts as
#: having made a prediction at all.
#:
#: WHY THIS IS NEEDED. Without it, "the mechanism FAILED" collapses into "the
#: target did its usual thing". Real consumption rises in 92% of these
#: windows, so "inflation ticked up 0.2% and consumption rose anyway" was
#: scored as a transmission failure, and 2,316 of 2,716 origins landed in the
#: failure arm. An arm that contains five sixths of the sample is not the
#: subset where the textbook broke; it is the sample.
#:
#: Five percent over a year, on the driver's own scale. A round number, and
#: both the gated and ungated splits are reported so the choice is visible.
MIN_DRIVER_MOVE = 0.05


@dataclass(frozen=True)
class Mechanism:
    """One conventional transmission, as a testable directional claim."""

    key: str
    driver: str
    target: str
    #: +1 when a rise in the driver should raise the target, -1 when it
    #: should lower it.
    sign: int
    statement: str

    def predicts_rise(self, driver_change: float, *,
                      min_move: float = MIN_DRIVER_MOVE) -> Optional[bool]:
        """What the textbook says the target does.

        None when the driver did not move enough to make a prediction --
        which is a real answer, not a missing one: a mechanism that was never
        engaged cannot have failed.
        """
        if abs(driver_change) < min_move:
            return None
        return (driver_change * self.sign) > 0

    def as_dict(self) -> dict:
        return {"key": self.key, "driver": self.driver,
                "target": self.target, "sign": self.sign,
                "statement": self.statement}


#: The six mechanisms §16 names, written as claims that can be wrong.
MECHANISMS: Tuple[Mechanism, ...] = (
    Mechanism("rates_to_housing", "DFF", "HOUST", -1,
              "higher policy rates lower housing starts"),
    Mechanism("rates_to_consumption", "DFF", "PCEC96", -1,
              "higher policy rates lower real consumption"),
    Mechanism("credit_to_investment", "DGS10", "INDPRO", -1,
              "a higher long rate lowers investment and, through it, "
              "industrial production"),
    Mechanism("unemployment_to_spending", "UNRATE", "PCEC96", -1,
              "rising unemployment lowers real consumption"),
    Mechanism("inflation_to_real_income", "CPIAUCSL", "PCEC96", -1,
              "faster inflation erodes real income and lowers real "
              "consumption"),
    Mechanism("curve_to_risk_appetite", "DGS10", "HOUST", 1,
              "a steeper curve accompanies more risk-taking, visible in "
              "housing starts"),
)

BY_KEY: Dict[str, Mechanism] = {m.key: m for m in MECHANISMS}


@dataclass(frozen=True)
class Origin:
    """One origin's reading of one mechanism."""

    mechanism: str
    origin: str
    driver_change: float
    predicted_rise: Optional[bool]
    actual_rise: Optional[bool]

    @property
    def status(self) -> str:
        if self.predicted_rise is None or self.actual_rise is None:
            return "NO_PREDICTION"
        return ("TRANSMITTED" if self.predicted_rise == self.actual_rise
                else "FAILED")


def read_mechanism(m: Mechanism, *, origins: Sequence[str],
                   driver_change: Dict[str, float],
                   actual_rise: Dict[str, bool],
                   min_move: float = MIN_DRIVER_MOVE) -> List[Origin]:
    out = []
    for o in origins:
        dc = driver_change.get(o)
        if dc is None:
            continue
        out.append(Origin(mechanism=m.key, origin=o, driver_change=dc,
                          predicted_rise=m.predicts_rise(dc,
                                                         min_move=min_move),
                          actual_rise=actual_rise.get(o)))
    return out


@dataclass(frozen=True)
class ResidualResult:
    """Did the block help MORE where the mechanism failed?"""

    mechanism: str
    n_failed: int
    n_transmitted: int
    delta_failed: float
    delta_transmitted: float
    difference: float
    diff_ci_low: Optional[float]
    diff_ci_high: Optional[float]
    episodes_failed: int = 0
    note: str = ""

    @property
    def verdict(self) -> str:
        from .incremental import MIN_EPISODES, MIN_PAIRED
        if self.n_failed < MIN_PAIRED or self.n_transmitted < MIN_PAIRED:
            return "INSUFFICIENT_SAMPLE"
        if self.diff_ci_low is None:
            return "INSUFFICIENT_SAMPLE"
        if self.episodes_failed < MIN_EPISODES:
            return "INSUFFICIENT_EPISODES"
        if self.diff_ci_low > 0:
            return "SUPPORTED"
        return "NOT_SUPPORTED"

    def as_dict(self) -> dict:
        return {"mechanism": self.mechanism, "n_failed": self.n_failed,
                "n_transmitted": self.n_transmitted,
                "delta_failed": round(self.delta_failed, 5),
                "delta_transmitted": round(self.delta_transmitted, 5),
                "difference": round(self.difference, 5),
                "difference_ci": ([self.diff_ci_low, self.diff_ci_high]
                                  if self.diff_ci_low is not None else None),
                "episodes_failed": self.episodes_failed,
                "verdict": self.verdict, "note": self.note}


def test_residual(*, mechanism: str, readings: Sequence[Origin],
                  diffs_by_origin: Dict[str, List[float]],
                  seed: int = 20260827) -> ResidualResult:
    """Difference-in-differences on the paired Brier improvement.

    `diffs_by_origin` maps an origin to the per-row (base loss - augmented
    loss) values at that origin. The comparison is between origins where the
    mechanism FAILED and origins where it TRANSMITTED, so the interval is
    computed on the DIFFERENCE of the two means -- resampling origins, not
    rows, in both arms at once.
    """
    import random
    from .incremental import _quantile, BOOTSTRAP_DRAWS, CI_LEVEL
    from .power import count_episodes

    failed = sorted({r.origin for r in readings if r.status == "FAILED"})
    trans = sorted({r.origin for r in readings if r.status == "TRANSMITTED"})
    f_vals = {o: diffs_by_origin[o] for o in failed if o in diffs_by_origin}
    t_vals = {o: diffs_by_origin[o] for o in trans if o in diffs_by_origin}
    n_f = sum(len(v) for v in f_vals.values())
    n_t = sum(len(v) for v in t_vals.values())

    def mean(groups):
        flat = [x for g in groups for x in g]
        return sum(flat) / len(flat) if flat else 0.0

    d_f, d_t = mean(f_vals.values()), mean(t_vals.values())
    if len(f_vals) < 2 or len(t_vals) < 2:
        return ResidualResult(mechanism=mechanism, n_failed=n_f,
                              n_transmitted=n_t, delta_failed=d_f,
                              delta_transmitted=d_t, difference=d_f - d_t,
                              diff_ci_low=None, diff_ci_high=None,
                              episodes_failed=count_episodes(failed),
                              note="one arm has fewer than two origins")
    rng = random.Random(seed)
    fk, tk = sorted(f_vals), sorted(t_vals)
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        fs = [f_vals[fk[rng.randrange(len(fk))]] for _ in range(len(fk))]
        ts = [t_vals[tk[rng.randrange(len(tk))]] for _ in range(len(tk))]
        draws.append(mean(fs) - mean(ts))
    draws.sort()
    a = (1.0 - CI_LEVEL) / 2.0
    return ResidualResult(
        mechanism=mechanism, n_failed=n_f, n_transmitted=n_t,
        delta_failed=d_f, delta_transmitted=d_t, difference=d_f - d_t,
        diff_ci_low=round(_quantile(draws, a), 5),
        diff_ci_high=round(_quantile(draws, 1 - a), 5),
        episodes_failed=count_episodes(failed),
        note=("the interval is on the DIFFERENCE between the two arms; two "
              "overlapping one-arm intervals would not be a comparison"))


# =============================================================================
# §17: TEMPORAL ORDER
# =============================================================================

def _corr(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    if n < 3 or n != len(b):
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / (va ** 0.5 * vb ** 0.5)


@dataclass(frozen=True)
class TemporalOrder:
    """Which of two series moved first, measured rather than assumed."""

    signal: str
    target: str
    best_lag: int
    best_correlation: float
    lag_profile: Tuple[Tuple[int, float], ...]
    n: int

    @property
    def classification(self) -> str:
        """LEADING means the signal moves BEFORE the target.

        The sign convention is fixed here and stated because it is the one
        thing in this file that is easy to get backwards: a POSITIVE lag
        means the signal at time t lines up with the target at t+lag, i.e.
        the signal came first.
        """
        if abs(self.best_correlation) < MIN_ABS_CORRELATION:
            return UNRELATED
        if self.best_lag > COINCIDENT_BAND:
            return LEADING
        if self.best_lag < -COINCIDENT_BAND:
            return LAGGING
        return COINCIDENT

    @property
    def usable_as_driver(self) -> bool:
        """§17: a signal that moves after its target cannot be its early
        driver. It may still be a real consequence, which is a different and
        much less useful claim."""
        return self.classification == LEADING

    def as_dict(self) -> dict:
        return {"signal": self.signal, "target": self.target,
                "best_lag": self.best_lag,
                "best_correlation": round(self.best_correlation, 4),
                "classification": self.classification,
                "usable_as_driver": self.usable_as_driver,
                "n": self.n,
                "lag_profile": [[l, round(c, 4)] for l, c in
                                self.lag_profile]}


def temporal_order(signal: Sequence[Tuple[str, float]],
                   target: Sequence[Tuple[str, float]], *,
                   max_lag: int = 12) -> TemporalOrder:
    """Cross-correlate two aligned series over +/- `max_lag` periods."""
    s = dict(signal)
    t = dict(target)
    keys = sorted(set(s) & set(t))
    require(len(keys) >= 3,
            "a temporal order needs at least three aligned observations")
    idx = {k: i for i, k in enumerate(keys)}
    sv = [s[k] for k in keys]
    tv = [t[k] for k in keys]
    profile = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a, b = sv[:len(sv) - lag], tv[lag:]
        else:
            a, b = sv[-lag:], tv[:len(tv) + lag]
        if len(a) < 3:
            continue
        profile.append((lag, _corr(a, b)))
    best_lag, best_c = max(profile, key=lambda x: abs(x[1]))
    return TemporalOrder(signal="", target="", best_lag=best_lag,
                         best_correlation=best_c,
                         lag_profile=tuple(profile), n=len(keys))


class CausalOverreach(EconError):
    """A temporal order was promoted to a causal or predictive claim."""


#: The only states a temporal-order measurement may confer on its own.
LEAD_ONLY_STATES = ("OBSERVED", "LEADING_BUT_REDUNDANT", "RETIRE",
                    "INSUFFICIENT_DATA", "TESTED_NOT_PROMOTED")


def assert_lead_is_not_causal(order: "TemporalOrder", verdict: str) -> None:
    """§9/§25: leading a series does not make you its cause.

    THE DEFECT THIS CATCHES. `UMCSENT -> HOUST, lag +6, LEADING` is a
    correlation between two lagged series. It is compatible with sentiment
    driving housing, with housing driving sentiment through a slower channel,
    with a third variable driving both, and -- as this run measured -- with
    the lead being a property of which origins were sampled. A promotion
    needs the incremental test, not the lag.
    """
    if verdict not in LEAD_ONLY_STATES:
        raise CausalOverreach(
            f"a temporal order (lag {order.best_lag:+d}, correlation "
            f"{order.best_correlation:+.3f}) was given the verdict "
            f"{verdict!r}. A lead may confer only {LEAD_ONLY_STATES}; "
            "anything stronger requires an incremental-value or lead-time "
            "result, and this run's own housing lead turned out to be an "
            "artifact of the sampled origins.")

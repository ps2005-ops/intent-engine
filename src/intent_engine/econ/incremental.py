"""The killer experiment: does knowing how people feel predict anything?

WHY THIS MODULE IS THE GATE AND NOT A REPORT
--------------------------------------------
Section 18 is the only thing standing between a psychological world model and
astrology. A collective-state layer will always produce plausible narrative:
every crisis can be retold as fear, every bubble as greed, and the retelling
will fit because it was written afterwards. Fitting is free. So the layer is
not credited for explaining anything. It is credited only when adding it to a
conventional economic model makes FORWARD forecasts measurably better, out of
sample, across regimes, after correcting for the fact that we ran many tests.

The engine must be able to conclude "fear adds nothing" and delete it
(Section 42). That sentence is the design requirement, and everything here
that looks like pessimism -- the sample floors, the FDR correction, the
refusal to call a positive point estimate an improvement when its interval
straddles zero -- is there so that conclusion can actually be reached.

WHY PAIRED, AND WHY BOOTSTRAP
-----------------------------
The two models forecast the SAME targets from the SAME cutoffs. The only
difference is the collective-state feature. So the right statistic is the
per-target difference in loss, and its sampling distribution is obtained by
resampling those paired differences. No distributional assumption is needed
and none is made -- which matters, because forecast losses are skewed and a
t-test on them would overstate significance in exactly the direction that
flatters the new feature.

WHY STDLIB
----------
This package imports nothing (`test_econ_core_is_neutral`). A numerical
dependency reached through another package's transitive tree is how a broad
except clause turns into a silent zero on a production path.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_incremental.v1"

# --- verdicts ---------------------------------------------------------------
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
NO_IMPROVEMENT = "NO_IMPROVEMENT"          # delta <= 0 point estimate
NOT_ROBUST = "NOT_ROBUST"                  # positive, but interval straddles 0
IMPROVEMENT = "IMPROVEMENT"                # positive and robust
VERDICTS = (INSUFFICIENT_SAMPLE, NO_IMPROVEMENT, NOT_ROBUST, IMPROVEMENT)

#: Below this many paired forecasts, no verdict is offered at all. A delta
#: measured on eleven observations is the "fitted to eleven points" failure
#: the causal ladder already names; here it would promote a variable.
MIN_PAIRED = 30

#: Two-sided interval. Not tunable per-test: choosing the level after seeing
#: the interval is the oldest way to manufacture a result.
CI_LEVEL = 0.95
BOOTSTRAP_DRAWS = 2000

#: False-discovery rate for the family of comparisons (Section 18's
#: "multiple-testing controls"). Sixteen dimensions x four regimes x three
#: horizons is 192 tests; at p<0.05 roughly ten will look significant with no
#: signal present at all.
FDR_Q = 0.10


class HindsightLeak(EconError):
    """A forecast used information published after the thing it forecast."""


# =============================================================================
# FORECASTS
# =============================================================================

@dataclass(frozen=True)
class Forecast:
    """One model's prediction of one target, made at one cutoff.

    `information_cutoff` is load-bearing and checked. Section 18 requires
    vintage-correct data, and the failure it prevents is the one that makes
    every backtest look brilliant: scoring a forecast against an outcome whose
    revision was published before the forecast was supposedly made.
    """

    target_id: str
    #: Probability assigned to the outcome being UP / the event occurring.
    probability: float
    information_cutoff: str
    horizon_days: int
    model: str
    regime: str = "ALL"

    def __post_init__(self) -> None:
        require(bool(self.target_id), "a forecast names its target")
        require(0.0 <= self.probability <= 1.0,
                f"{self.target_id}: {self.probability} is not a probability")
        require(bool(self.information_cutoff),
                f"{self.target_id}: a forecast with no information cutoff "
                "cannot be checked for hindsight, which makes its score "
                "meaningless rather than merely unverified")
        require(self.horizon_days > 0, "a forecast looks forward")


@dataclass(frozen=True)
class Outcome:
    """What actually happened, and when it became knowable."""

    target_id: str
    occurred: bool
    occurred_at: str
    #: When the resolving figure was PUBLISHED. For revised series this is
    #: later than `occurred_at`, and using the wrong one is how a walled
    #: backtest still leaks (see `two-dates-per-fact`).
    published_at: str = ""
    regime: str = "ALL"

    def __post_init__(self) -> None:
        require(bool(self.occurred_at), "an outcome is dated")

    @property
    def knowable_at(self) -> str:
        return self.published_at or self.occurred_at


def assert_no_hindsight(forecasts: Sequence[Forecast],
                        outcomes: Dict[str, Outcome]) -> None:
    """Every forecast must predate what it forecasts becoming knowable."""
    leaks = []
    for f in forecasts:
        o = outcomes.get(f.target_id)
        if o is None:
            continue
        if f.information_cutoff >= o.knowable_at:
            leaks.append(
                f"{f.model}/{f.target_id}: cutoff {f.information_cutoff} is "
                f"not before the outcome became knowable at {o.knowable_at}")
    if leaks:
        raise HindsightLeak(
            f"{len(leaks)} forecast(s) were made at or after their own "
            f"outcome became knowable. This is not a scoring inaccuracy; a "
            f"model scored this way is being credited for reading the answer."
            f"\n  " + "\n  ".join(leaks[:5]))


def brier(f: Forecast, o: Outcome) -> float:
    """Squared error of a probability. Lower is better; 0.25 is a coin."""
    return (f.probability - (1.0 if o.occurred else 0.0)) ** 2


# =============================================================================
# PAIRED COMPARISON
# =============================================================================

def _quantile(sorted_xs: Sequence[float], q: float) -> float:
    if not sorted_xs:
        return 0.0
    idx = q * (len(sorted_xs) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return sorted_xs[lo]
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (idx - lo)


def _bootstrap_ci(diffs: Sequence[float], *, seed: int
                  ) -> Tuple[float, float, float]:
    """Percentile interval and a two-sided p-value for mean(diffs) != 0.

    The p-value is the bootstrap proportion of resamples on the wrong side of
    zero, doubled. It is deliberately the same object the interval comes from,
    so a reader cannot be shown an interval that excludes zero beside a
    p-value that does not.
    """
    rng = random.Random(seed)
    n = len(diffs)
    means = []
    for _ in range(BOOTSTRAP_DRAWS):
        means.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    alpha = (1.0 - CI_LEVEL) / 2.0
    lo = _quantile(means, alpha)
    hi = _quantile(means, 1.0 - alpha)
    below = sum(1 for m in means if m <= 0.0) / BOOTSTRAP_DRAWS
    p = min(1.0, 2.0 * min(below, 1.0 - below))
    return lo, hi, p


@dataclass(frozen=True)
class Comparison:
    """MODEL A vs MODEL A + collective state, on one matched sample."""

    name: str
    dimension: str
    regime: str
    horizon_days: int
    population: str
    n_paired: int
    base_score: float
    augmented_score: float
    delta: float
    ci_low: float
    ci_high: float
    p_value: float
    verdict: str
    #: Set by `adjust()` once the whole family is known. Until then a single
    #: comparison cannot honestly claim significance.
    fdr_adjusted: bool = False
    survives_fdr: Optional[bool] = None
    note: str = ""

    @property
    def robust(self) -> bool:
        """Positive, interval clear of zero, AND it survived the family."""
        return (self.verdict == IMPROVEMENT
                and self.survives_fdr is True)

    def as_dict(self) -> dict:
        return {"name": self.name, "dimension": self.dimension,
                "regime": self.regime, "horizon_days": self.horizon_days,
                "population": self.population, "n_paired": self.n_paired,
                "base_score": self.base_score,
                "augmented_score": self.augmented_score,
                "delta": self.delta,
                "ci": [self.ci_low, self.ci_high], "p_value": self.p_value,
                "verdict": self.verdict, "fdr_adjusted": self.fdr_adjusted,
                "survives_fdr": self.survives_fdr, "robust": self.robust,
                "note": self.note}

    def statement(self) -> str:
        """Prose that cannot overstate the result.

        The IMPROVEMENT branch is the only one that may use the word
        "improves", and it may not use it before `adjust()` has run.
        """
        base = (f"{self.dimension} / {self.population} / {self.regime} / "
                f"{self.horizon_days}d (n={self.n_paired})")
        if self.verdict == INSUFFICIENT_SAMPLE:
            return (f"{base}: not tested — {self.n_paired} paired forecasts "
                    f"is below the floor of {MIN_PAIRED}.")
        if self.verdict == NO_IMPROVEMENT:
            return (f"{base}: adding this construct did NOT improve forecast "
                    f"skill (delta {self.delta:+.4f}).")
        if self.verdict == NOT_ROBUST:
            return (f"{base}: point estimate favours the augmented model "
                    f"(delta {self.delta:+.4f}) but the 95% interval "
                    f"[{self.ci_low:+.4f}, {self.ci_high:+.4f}] includes "
                    f"zero. Not evidence of value.")
        if not self.fdr_adjusted:
            return (f"{base}: delta {self.delta:+.4f}, interval clear of "
                    f"zero — pending multiple-testing adjustment.")
        if not self.survives_fdr:
            return (f"{base}: delta {self.delta:+.4f} did not survive "
                    f"false-discovery correction across the test family.")
        return (f"{base}: adding this construct improves forecast skill by "
                f"{self.delta:+.4f} Brier "
                f"[{self.ci_low:+.4f}, {self.ci_high:+.4f}], surviving FDR "
                f"correction at q={FDR_Q}.")


def compare(*, name: str, dimension: str, population: str,
            base: Sequence[Forecast], augmented: Sequence[Forecast],
            outcomes: Sequence[Outcome], regime: str = "ALL",
            horizon_days: int = 0, seed: int = 20260827) -> Comparison:
    """Score two models on the SAME targets and test whether B beats A.

    Delta is defined as base_score - augmented_score, so POSITIVE MEANS THE
    COLLECTIVE-STATE MODEL IS BETTER. Stated here because the sign convention
    on a loss is the easiest thing in this file to get backwards, and getting
    it backwards would promote every variable that fails.
    """
    by_id = {o.target_id: o for o in outcomes}
    assert_no_hindsight(list(base) + list(augmented), by_id)

    b_by = {f.target_id: f for f in base}
    a_by = {f.target_id: f for f in augmented}
    shared = sorted(set(b_by) & set(a_by) & set(by_id))
    if regime != "ALL":
        shared = [t for t in shared if by_id[t].regime == regime]
    if horizon_days:
        shared = [t for t in shared
                  if b_by[t].horizon_days == horizon_days]

    n = len(shared)
    if n < MIN_PAIRED:
        return Comparison(
            name=name, dimension=dimension, regime=regime,
            horizon_days=horizon_days, population=population, n_paired=n,
            base_score=0.0, augmented_score=0.0, delta=0.0,
            ci_low=0.0, ci_high=0.0, p_value=1.0,
            verdict=INSUFFICIENT_SAMPLE,
            note=(f"{n} paired forecasts; the floor is {MIN_PAIRED}. A delta "
                  "measured on fewer is not a weak result, it is not a "
                  "result."))

    b_losses = [brier(b_by[t], by_id[t]) for t in shared]
    a_losses = [brier(a_by[t], by_id[t]) for t in shared]
    diffs = [b - a for b, a in zip(b_losses, a_losses)]   # >0 = augmented won

    base_score = sum(b_losses) / n
    aug_score = sum(a_losses) / n
    delta = base_score - aug_score
    lo, hi, p = _bootstrap_ci(diffs, seed=seed)

    if delta <= 0:
        verdict, note = NO_IMPROVEMENT, (
            "the augmented model's mean loss is no better than the base "
            "model's; this construct is a retirement candidate")
    elif lo <= 0.0 <= hi:
        verdict, note = NOT_ROBUST, (
            "positive point estimate, interval includes zero; consistent "
            "with no effect")
    else:
        verdict, note = IMPROVEMENT, (
            "interval clear of zero; pending family-wide FDR correction")

    return Comparison(name=name, dimension=dimension, regime=regime,
                      horizon_days=horizon_days, population=population,
                      n_paired=n, base_score=round(base_score, 5),
                      augmented_score=round(aug_score, 5),
                      delta=round(delta, 5), ci_low=round(lo, 5),
                      ci_high=round(hi, 5), p_value=round(p, 5),
                      verdict=verdict, note=note)


# =============================================================================
# MULTIPLE TESTING (Section 18)
# =============================================================================

def adjust(comparisons: Sequence[Comparison], *, q: float = FDR_Q
           ) -> List[Comparison]:
    """Benjamini-Hochberg across the whole family of comparisons.

    Applied to every comparison that was actually TESTED, not only to the
    winners: selecting the family after seeing which tests won is the same
    error the correction exists to prevent.
    """
    from dataclasses import replace
    tested = [c for c in comparisons if c.verdict != INSUFFICIENT_SAMPLE]
    if not tested:
        return [replace(c, fdr_adjusted=True, survives_fdr=False)
                for c in comparisons]

    ranked = sorted(tested, key=lambda c: c.p_value)
    m = len(ranked)
    threshold_rank = 0
    for i, c in enumerate(ranked, start=1):
        if c.p_value <= (i / m) * q:
            threshold_rank = i
    survivors = {id(c) for c in ranked[:threshold_rank]}

    out = []
    for c in comparisons:
        if c.verdict == INSUFFICIENT_SAMPLE:
            out.append(replace(c, fdr_adjusted=True, survives_fdr=False))
        else:
            passed = id(c) in survivors and c.verdict == IMPROVEMENT
            out.append(replace(c, fdr_adjusted=True, survives_fdr=passed))
    return out


def report(comparisons: Sequence[Comparison]) -> dict:
    """Section 56's report, with the numbers a reader needs to disagree."""
    adjusted = (list(comparisons)
                if all(c.fdr_adjusted for c in comparisons)
                else adjust(comparisons))
    tested = [c for c in adjusted if c.verdict != INSUFFICIENT_SAMPLE]
    robust = [c for c in adjusted if c.robust]
    by_dimension: Dict[str, dict] = {}
    for c in adjusted:
        d = by_dimension.setdefault(
            c.dimension, {"tested": 0, "robust": 0, "best_delta": None,
                          "verdicts": []})
        if c.verdict != INSUFFICIENT_SAMPLE:
            d["tested"] += 1
        if c.robust:
            d["robust"] += 1
            d["best_delta"] = (c.delta if d["best_delta"] is None
                               else max(d["best_delta"], c.delta))
        d["verdicts"].append(c.verdict)

    base = (round(sum(c.base_score for c in tested) / len(tested), 5)
            if tested else None)
    aug = (round(sum(c.augmented_score for c in tested) / len(tested), 5)
           if tested else None)
    return {"contract": CONTRACT,
            "comparisons": len(adjusted),
            "tested": len(tested),
            "not_tested": len(adjusted) - len(tested),
            "robust_improvements": len(robust),
            "base_economic_model_score": base,
            "base_plus_collective_score": aug,
            "incremental_delta": (round(base - aug, 5)
                                  if base is not None else None),
            "fdr_q": FDR_Q, "ci_level": CI_LEVEL,
            "min_paired": MIN_PAIRED,
            "by_dimension": by_dimension,
            "statements": [c.statement() for c in adjusted],
            "detail": [c.as_dict() for c in adjusted]}

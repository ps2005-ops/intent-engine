"""Experiment registry, effective sample size, and false-discovery control.

THE PROBLEM THIS CYCLE CREATES
------------------------------
Replay can now produce tens of thousands of rows in minutes. That is a genuine
gain in measurement capacity and simultaneously the most dangerous thing this
project has ever built, for two reasons:

1. **Those rows are not independent.** 45 securities x 2,500 days x 3 horizons
   is not 337,500 experiments. The same market week appears in every overlapping
   window; the same sector moves together; one entry evaluated at three horizons
   is one decision measured three times. Raw count over-states information by
   more than an order of magnitude, and every confidence interval built on it is
   too narrow by the square root of that.

2. **Many combinations are tested at once.** Three strategies x several horizons
   is enough that the best-looking result is likely to look good by chance. A
   p-value that means something for ONE preregistered test means much less as
   the best of nine.

`sampling.py` already solved (1) for time windows and is REUSED here rather than
reimplemented; this module adds the clustering dimensions replay introduces and
the multiple-testing correction.

WHY BENJAMINI-HOCHBERG
----------------------
Preregistered at q = 0.10. The question is "which of these families is worth
continuing?", so the right error to control is the PROPORTION of continued
strategies that are false, not the probability of any single false positive.
Family-wise control (Bonferroni) over three families would be needlessly
conservative and would mostly guarantee retiring everything regardless of truth.

Deflated / probabilistic Sharpe and reality-check bootstraps are deliberately
NOT added. They are the right tools at a sample size and strategy count this
project does not have, and adding them here would be statistical decoration --
five methods reported to look rigorous, none of them load-bearing.
"""
from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.market.sampling import SampleSize, merge_windows

FDR_Q = 0.10
DEFAULT_PATH = "reports/market/experiments.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# EFFECTIVE SAMPLE SIZE
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EffectiveSample:
    """Raw versus effective, with the reason for the gap named.

    `n_eff` is the MINIMUM across clustering dimensions, not a blend. A blend
    would let a dimension with many clusters mask one with few, and the binding
    constraint on information is always the tightest dependency.
    """
    n_raw: int
    n_by_dimension: Dict[str, int]
    n_effective: int
    binding: str

    @property
    def design_effect(self) -> Optional[float]:
        if not self.n_effective:
            return None
        return round(self.n_raw / self.n_effective, 2)

    def as_dict(self) -> dict:
        return {"n_raw": self.n_raw, "n_by_dimension": self.n_by_dimension,
                "n_effective": self.n_effective, "binding": self.binding,
                "design_effect": self.design_effect}


def effective_sample(observations: Sequence[dict], *,
                     horizon_days: Optional[int] = None) -> EffectiveSample:
    """Collapse correlated observations along every dimension replay adds.

    Dimensions, each a real source of dependence measured here rather than
    assumed away:

      decision       one entry measured at N horizons is ONE decision
      security       repeated observations of one name are not independent
      time_window    overlapping holding periods resample the same market move
      sector_week    a sector moving together on one macro event is one event

    `time_window` reuses `sampling.merge_windows`, the routine that caught the
    0.359 false discovery on day 3.
    """
    if not observations:
        return EffectiveSample(0, {}, 0, "no observations")

    decisions = {(o.get("security"), str(o.get("as_of"))[:10])
                 for o in observations}
    securities = {o.get("security") for o in observations}
    sector_weeks = {(o.get("sector") or "?",) + _isoweek(str(o.get("as_of")))
                    for o in observations}

    # OVERLAPPING WINDOWS, MERGED PER SECURITY.
    #
    # Pooling every security's windows into one merge_windows call is wrong and
    # spectacularly so: with 77 securities trading daily, the union of all
    # holding periods is ONE continuous interval from 2015 to 2022, so n_eff
    # came back as 1 and every test was unmeasurable. Two overlapping windows on
    # DIFFERENT securities are correlated (they share a market factor) but they
    # are not the same observation -- that dependence is what `sector_week`
    # measures, separately.
    #
    # Within one security, overlapping windows genuinely do resample the same
    # price move, so they are merged. Summing the per-security counts gives the
    # number of non-overlapping price moves the sample actually contains.
    by_security: Dict[str, List[Tuple[str, str]]] = {}
    for o in observations:
        start = str(o.get("as_of"))[:10]
        end = str(o.get("resolved_at") or o.get("exit_at") or start)[:10]
        if start:
            by_security.setdefault(o.get("security"), []).append(
                (start, max(start, end)))
    merged = []
    for windows in by_security.values():
        merged.extend(merge_windows(windows))

    dims = {"decision": len(decisions),
            "security": len(securities),
            "time_window": len(merged),
            "sector_week": len(sector_weeks)}
    binding = min(dims, key=lambda k: dims[k])
    return EffectiveSample(len(observations), dims, dims[binding], binding)


def _isoweek(day: str) -> Tuple[int, int]:
    """(iso year, iso week). Both, because week 1 recurs every year and keying
    on the week alone would collapse eight years into fifty-two buckets."""
    try:
        cal = datetime.fromisoformat(day[:10]).isocalendar()
        return (cal[0], cal[1])
    except (TypeError, ValueError):
        return (0, 0)


# ---------------------------------------------------------------------------
# SIGNIFICANCE, ON EFFECTIVE n
# ---------------------------------------------------------------------------
def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


@dataclass(frozen=True)
class TestResult:
    """One preregistered comparison. p computed on n_EFFECTIVE, always."""
    name: str
    mean: Optional[float]
    n_raw: int
    n_effective: int
    stdev: Optional[float]
    t_stat: Optional[float]
    p_value: Optional[float]
    measurable: bool
    reason: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "mean": self.mean, "n_raw": self.n_raw,
                "n_effective": self.n_effective, "stdev": self.stdev,
                "t_stat": self.t_stat, "p_value": self.p_value,
                "measurable": self.measurable, "reason": self.reason}


MIN_EFFECTIVE_FOR_A_CLAIM = 30


def test_edge(name: str, net_returns: Sequence[float],
              sample: EffectiveSample) -> TestResult:
    """Is mean net return distinguishable from zero?

    The standard error uses n_EFFECTIVE. Using n_raw here is the single most
    common way a backtest manufactures significance, and it is exactly the error
    corrected on day 3 (0.359 at 64 rows became indistinguishable at 15 windows).
    """
    values = [v for v in net_returns if v is not None]
    n_eff = sample.n_effective
    if len(values) < 2 or n_eff < 2:
        return TestResult(name, None, sample.n_raw, n_eff, None, None, None,
                          False, "fewer than 2 observations")
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    sd = math.sqrt(var)
    if n_eff < MIN_EFFECTIVE_FOR_A_CLAIM:
        return TestResult(name, round(mean, 6), sample.n_raw, n_eff,
                          round(sd, 6), None, None, False,
                          f"n_effective {n_eff} < {MIN_EFFECTIVE_FOR_A_CLAIM}; "
                          f"UNMEASURABLE rather than a weak claim")
    if sd == 0:
        return TestResult(name, round(mean, 6), sample.n_raw, n_eff, 0.0,
                          None, None, False, "zero dispersion")
    t = mean / (sd / math.sqrt(n_eff))
    p = 2 * (1 - _norm_cdf(abs(t)))
    return TestResult(name, round(mean, 6), sample.n_raw, n_eff, round(sd, 6),
                      round(t, 4), round(p, 6), True, "")


def benjamini_hochberg(results: Sequence[TestResult], q: float = FDR_Q
                       ) -> dict:
    """BH step-up. Returns which tests survive FDR control at q.

    Only MEASURABLE results enter the procedure -- feeding in tests that
    returned no p-value would inflate the denominator and make the correction
    look more severe than the evidence warrants.
    """
    testable = [r for r in results if r.measurable and r.p_value is not None]
    m = len(testable)
    if not m:
        return {"method": "benjamini_hochberg", "q": q, "tests": 0,
                "discoveries": [], "threshold": None,
                "note": "no measurable test; nothing to correct"}
    ordered = sorted(testable, key=lambda r: r.p_value)
    threshold = None
    k = 0
    for i, r in enumerate(ordered, start=1):
        if r.p_value <= (i / m) * q:
            threshold, k = r.p_value, i
    discoveries = [r.name for r in ordered[:k]] if threshold is not None else []
    return {"method": "benjamini_hochberg", "q": q, "tests": m,
            "threshold": threshold, "discoveries": discoveries,
            "rejected": [r.name for r in ordered[k:]],
            "note": ("no strategy survives FDR control" if not discoveries
                     else None)}


# ---------------------------------------------------------------------------
# EXPERIMENT REGISTRY — append-only, so the denominator cannot shrink
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    at: str
    strategy_key: str
    horizon: int
    window: str            # research | validation | holdout
    universe_tier: int
    securities: int
    n_raw: int
    n_effective: int
    mean_net_return: Optional[float]
    p_value: Optional[float]
    measurable: bool
    note: str = ""

    def as_dict(self) -> dict:
        return {"record": "experiment", **self.__dict__}


class ExperimentRegistry:
    """Every comparison ever run. Append-only, because the multiple-testing
    denominator is only honest if failed experiments stay counted."""

    def __init__(self, path=DEFAULT_PATH):
        self.path = pathlib.Path(path)

    def record(self, experiment: Experiment) -> Experiment:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(experiment.as_dict(), sort_keys=True,
                                default=str) + "\n")
        return experiment

    def all(self) -> List[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def count(self) -> dict:
        rows = self.all()
        return {"experiments_total": len(rows),
                "strategies": len({r.get("strategy_key") for r in rows}),
                "horizons": len({r.get("horizon") for r in rows}),
                "windows": sorted({r.get("window") for r in rows}),
                "measurable": sum(1 for r in rows if r.get("measurable")),
                "note": ("this total is the multiple-testing denominator; it "
                         "only ever grows")}


HOLDOUT_START = "2025-01-01"


class HoldoutViolation(RuntimeError):
    """Something tried to read the untouched holdout."""


def assert_not_holdout(window: str, as_of: str) -> None:
    """The holdout is not consulted this cycle. Enforced, not intended."""
    if window != "holdout" and as_of[:10] >= HOLDOUT_START:
        raise HoldoutViolation(
            f"{as_of} is inside the holdout ({HOLDOUT_START}+) but the "
            f"experiment is labelled {window!r}. The holdout is untouched this "
            f"cycle; reading it while designing strategies is how a holdout "
            f"stops being one.")

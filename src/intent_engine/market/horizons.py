"""Holding horizons — preregistered, and never chosen after the outcome.

THE FAILURE THIS PREVENTS
-------------------------
Evaluate one entry at 1, 3, 5, 10, 20 and 60 days, then report the horizon that
looked best. It is the most natural thing in the world to do and it is
hindsight selection: the entry decision was made once, and picking its horizon
afterwards uses information that did not exist at entry.

So a horizon belongs to a STRATEGY SPECIFICATION, fixed before any replay runs.
`assert_preregistered` refuses any horizon a strategy did not declare, and a
test asserts that the best-performing horizon cannot be adopted retroactively.

THE OTHER FAILURE: SIX HORIZONS ARE NOT SIX EXPERIMENTS
-------------------------------------------------------
One entry evaluated at six horizons produces six outcomes that share an entry
price, a security, a date and most of their price path. Their correlation is
close to one at the short end. Counting them as six independent observations
would inflate every sample size by 6x and narrow every confidence interval by
roughly 2.4x on nothing.

`horizon_cluster_key` exists so the effective-sample-size machinery can collapse
them back to the one decision they actually came from.

TRADING DAYS, NOT CALENDAR DAYS
-------------------------------
A 5-day horizon is five SESSIONS. Counting calendar days would silently shorten
every horizon spanning a weekend by two days and every one spanning a holiday
by more, and the error is invisible in the output.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

from intent_engine.runtime.market_calendar import is_market_day

# The horizons this project supports at all. A strategy declares a SUBSET.
SUPPORTED = (1, 3, 5, 10, 20, 60)

# Rationale per horizon, so a strategy that claims one has to mean something by
# it. Recorded here rather than in prose because it is checked.
RATIONALE = {
    1: "overnight/next-session reaction; only defensible for effects claimed "
       "to act immediately",
    3: "short mean-reversion window; long enough to clear a single session's "
       "noise",
    5: "one trading week; the shortest horizon at which a weekly effect can "
       "express itself",
    10: "two trading weeks; typical window for a regime change to persist or "
        "fail",
    20: "one trading month; the horizon the baseline signal has always used",
    60: "one trading quarter; only defensible for slow fundamental mechanisms",
}


class HorizonError(ValueError):
    """A horizon that was not preregistered for this strategy."""


def trading_days_after(start: str, sessions: int) -> Optional[str]:
    """The date `sessions` TRADING days after `start`.

    Returns None if the walk runs past a sane bound -- a horizon that cannot be
    resolved is reported unresolved, never approximated to the nearest calendar
    date.
    """
    if sessions <= 0:
        raise HorizonError("a horizon must be at least one session")
    day = date.fromisoformat(start[:10])
    counted = 0
    # 3x calendar headroom covers weekends and any plausible holiday run.
    for _ in range(sessions * 3 + 15):
        day += timedelta(days=1)
        if is_market_day(day):
            counted += 1
            if counted == sessions:
                return day.isoformat()
    return None  # pragma: no cover - unreachable with the headroom above


def horizon_cluster_key(security: str, as_of: str) -> str:
    """What the six outcomes of one entry share.

    Deliberately EXCLUDES the horizon: that is the point. Every horizon of one
    (security, date) decision collapses to one cluster, so effective sample size
    counts decisions rather than measurements of decisions.
    """
    return f"{security}:{as_of[:10]}"


@dataclass(frozen=True)
class HorizonSet:
    """The horizons one strategy declared, before it ever ran."""
    strategy_id: str
    horizons: tuple
    registered_at: str

    def __post_init__(self):
        for h in self.horizons:
            if h not in SUPPORTED:
                raise HorizonError(
                    f"{h} is not a supported horizon {SUPPORTED}")
        if not self.horizons:
            raise HorizonError("a strategy must declare at least one horizon")

    def assert_preregistered(self, horizon: int) -> int:
        """The guard against hindsight selection."""
        if horizon not in self.horizons:
            raise HorizonError(
                f"{self.strategy_id} did not preregister horizon {horizon} "
                f"(declared: {list(self.horizons)}). A horizon adopted after "
                f"seeing which one performed best is hindsight selection, not "
                f"a decision.")
        return horizon

    def as_dict(self) -> dict:
        return {"strategy_id": self.strategy_id,
                "horizons": list(self.horizons),
                "registered_at": self.registered_at,
                "rationale": {h: RATIONALE[h] for h in self.horizons}}


def best_horizon_is_not_a_decision(results: Sequence[dict]) -> dict:
    """Report every horizon, and refuse to name a winner.

    Returns the full per-horizon table plus an explicit refusal. This function
    exists so that the obvious call site -- "which horizon worked best?" -- has
    an answer that is honest instead of one that is convenient.
    """
    table = {r["horizon"]: r for r in results}
    return {"per_horizon": table,
            "selected": None,
            "reason": ("horizons are preregistered per strategy; the "
                       "best-performing horizon is an OUTCOME and selecting on "
                       "it after the fact would be hindsight"),
            "correlated": True,
            "note": ("these outcomes share an entry decision and are not "
                     "independent; see effective sample size")}

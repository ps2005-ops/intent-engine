"""Bounded, resumable, point-in-time historical replay.

WHY REPLAY IS THE LEVER
-----------------------
Measured on Day 18: a live paper position resolves in 21 calendar days, and the
engine produces at most a couple of candidates a cycle. Ten years of daily
decisions across 45 securities resolves in minutes. For *expected information
gain per unit time* replay dominates the live path by orders of magnitude, and
it is the only way to reject a weak hypothesis before spending a quarter on it.

WHAT KEEPS IT HONEST
--------------------
* **Point-in-time by construction.** Every signal filters to closes dated
  <= as_of before computing anything, and the suite asserts that appending
  future bars cannot change a decision.
* **Costs always.** Every return is net. There is no gross-only path.
* **Membership dates.** A security is skipped on dates outside its listing
  window, so a delisted name stays in the sample right up to its delisting
  instead of vanishing from the whole history.
* **Holdout protection.** `assert_not_holdout` refuses to read 2025+ while a
  run is labelled research or validation.
* **n_effective, always.** The row count is never the sample size.

BOUNDED, BECAUSE THE OPERATING CYCLE COMES FIRST
------------------------------------------------
A replay that runs for an hour inside the 06:30 cycle turns a research tool into
an outage. Every run takes a budget in seconds and in observations, checkpoints
as it goes, and stops cleanly at the limit with `exhausted_budget` -- a partial
result that can be resumed, not a failure. The night cycle spends what is left
of its budget on replay; the day cycle spends almost nothing.

DETERMINISTIC IDENTITY
----------------------
    replay:<strategy_key>:<tier>:<start>:<end>:<window>

Same inputs, same id, so a rerun resumes rather than duplicating. The checkpoint
records which (security, date) pairs are already done.
"""
from __future__ import annotations

import json
import pathlib
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from intent_engine.market import experiments as EX
from intent_engine.market.costs import DEFAULT as DEFAULT_COSTS, CostModel
from intent_engine.market.horizons import horizon_cluster_key, trading_days_after
from intent_engine.market.universe_tiers import Security

CHECKPOINT_DIR = "reports/market/replay"

# Defaults sized so a night cycle can spend leftover budget without ever
# threatening the next morning's operating window.
DEFAULT_MAX_SECONDS = 300
DEFAULT_MAX_OBSERVATIONS = 200_000


def job_id(strategy_key: str, tier: int, start: str, end: str,
           window: str) -> str:
    return f"replay:{strategy_key}:{tier}:{start[:10]}:{end[:10]}:{window}"


@dataclass
class Budget:
    """A replay may not run longer than the operating cycle can afford."""
    max_seconds: float = DEFAULT_MAX_SECONDS
    max_observations: int = DEFAULT_MAX_OBSERVATIONS
    started: float = field(default_factory=time.monotonic)
    observations: int = 0

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def exhausted(self) -> bool:
        return (self.elapsed >= self.max_seconds
                or self.observations >= self.max_observations)

    def spend(self, n: int = 1) -> None:
        self.observations += n

    def as_dict(self) -> dict:
        return {"max_seconds": self.max_seconds,
                "max_observations": self.max_observations,
                "elapsed_seconds": round(self.elapsed, 2),
                "observations": self.observations,
                "exhausted": self.exhausted}


@dataclass
class Checkpoint:
    """What is already done, so a resumed run does not duplicate it."""
    job: str
    completed: set = field(default_factory=set)
    root: str = "."

    @property
    def path(self) -> pathlib.Path:
        safe = self.job.replace(":", "_").replace("/", "_")
        return pathlib.Path(self.root) / CHECKPOINT_DIR / f"{safe}.json"

    def load(self) -> "Checkpoint":
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.completed = set(tuple(x) for x in data.get("completed", []))
            except (json.JSONDecodeError, OSError, TypeError):
                self.completed = set()
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(
            {"job": self.job, "saved_at": datetime.now(timezone.utc)
             .isoformat(timespec="seconds"),
             "completed": sorted(list(x) for x in self.completed)}, indent=0))
        tmp.replace(self.path)

    def done(self, security: str, day: str) -> bool:
        return (security, day) in self.completed

    def mark(self, security: str, day: str) -> None:
        self.completed.add((security, day))


def _sessions(closes: Dict[str, float], start: str, end: str) -> List[str]:
    """Actual trading dates in range, from the price series itself.

    Taken from the data rather than generated from a calendar: a date the source
    has no bar for is not a session this engine can act on, and inventing one
    would create a decision that could never have been made.
    """
    return sorted(d for d in (closes or {}) if start[:10] <= d <= end[:10])


@dataclass
class ReplayResult:
    job: str
    strategy_key: str
    window: str
    tier: int
    securities: int
    sessions_scanned: int
    signals_fired: int
    observations: List[dict]
    budget: dict
    status: str
    skipped: Dict[str, int] = field(default_factory=dict)

    @property
    def resumable(self) -> bool:
        return self.status == "exhausted_budget"

    def as_dict(self) -> dict:
        return {"job": self.job, "strategy_key": self.strategy_key,
                "window": self.window, "tier": self.tier,
                "securities": self.securities,
                "sessions_scanned": self.sessions_scanned,
                "signals_fired": self.signals_fired,
                "observations": len(self.observations),
                "budget": self.budget, "status": self.status,
                "resumable": self.resumable, "skipped": dict(self.skipped)}


def run_replay(*, strategy_key: str, signal_fn: Callable,
               horizons: Sequence[int], securities: Sequence[Security],
               series_for: Callable[[str], Dict[str, float]],
               start: str, end: str, window: str, tier: int,
               costs: Optional[CostModel] = None,
               budget: Optional[Budget] = None,
               root: str = ".",
               checkpoint_every: int = 2000) -> ReplayResult:
    """Replay one strategy over one window. Bounded, resumable, PIT-safe."""
    costs = costs or DEFAULT_COSTS
    budget = budget or Budget()
    job = job_id(strategy_key, tier, start, end, window)
    checkpoint = Checkpoint(job, root=root).load()

    # HOLDOUT GUARD, before any data is touched.
    EX.assert_not_holdout(window, end)

    observations: List[dict] = []
    skipped: Dict[str, int] = {}
    scanned = fired = 0
    status = "completed"

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    for security in securities:
        if budget.exhausted:
            status = "exhausted_budget"
            break
        closes = series_for(security.symbol) or {}
        if not closes:
            skip("no_price_data")
            continue
        for day in _sessions(closes, start, end):
            if budget.exhausted:
                status = "exhausted_budget"
                break
            # MEMBERSHIP: a security is only eligible inside its listing
            # window. This is what keeps a delisted name in the sample up to
            # its delisting instead of erasing it from the whole history.
            if not security.eligible_on(day):
                skip("outside_listing_window")
                continue
            if checkpoint.done(security.symbol, day):
                skip("already_done")
                continue
            scanned += 1
            signal = signal_fn(closes, security=security.symbol, as_of=day)
            checkpoint.mark(security.symbol, day)
            if not signal.fired:
                continue
            fired += 1
            entry = closes.get(day)
            if not entry:
                skip("no_entry_price")
                continue
            for horizon in horizons:
                exit_day = trading_days_after(day, horizon)
                if not exit_day:
                    skip("horizon_unresolvable")
                    continue
                exit_price = closes.get(exit_day)
                if exit_price is None:
                    # Unresolved: never filled from a later bar, never
                    # approximated. A missing exit is a missing observation.
                    skip("unresolved_horizon")
                    continue
                priced = costs.apply(entry=entry, exit_=exit_price,
                                     direction=signal.direction)
                observations.append({
                    "strategy_key": strategy_key, "security": security.symbol,
                    "sector": security.sector, "as_of": day,
                    "horizon": horizon, "resolved_at": exit_day,
                    "direction": signal.direction,
                    "signal_value": signal.value,
                    "gross_return": priced["gross_return"],
                    "cost": priced["cost"],
                    "net_return": priced["net_return"],
                    "cost_model": priced["cost_model"],
                    "cluster": horizon_cluster_key(security.symbol, day),
                    "window": window,
                })
                budget.spend()
            if len(checkpoint.completed) % checkpoint_every == 0:
                checkpoint.save()
    checkpoint.save()
    return ReplayResult(job=job, strategy_key=strategy_key, window=window,
                        tier=tier, securities=len(securities),
                        sessions_scanned=scanned, signals_fired=fired,
                        observations=observations, budget=budget.as_dict(),
                        status=status, skipped=skipped)

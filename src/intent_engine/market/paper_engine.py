"""Live paper positions from price-behaviour signals — as CONTROLS, not alpha.

THE TENSION THIS MODULE RESOLVES
--------------------------------
Day 18 measured all three strategies at no edge: p >= 0.72, negative net
expectancy after costs, zero survivors of Benjamini-Hochberg. `PAPER_CHALLENGER`
requires passing all eight validation gates and **none of them passed**.

At the same time, Position Decision Quality, calibration, Brier, reliability,
the equity curve and the whole resolution pipeline have been UNMEASURABLE for
eighteen days -- not because any strategy is bad, but because **zero positions
have ever flowed through**. Those are properties of the ENGINE, not of a
strategy, and they cannot be validated without at least one position completing
the round trip.

So the honest move is neither "promote a failed strategy" nor "keep everything
at zero forever". It is a third state that says exactly what it is:

    PAPER_CONTROL -- runs live paper, makes NO alpha claim, exists to exercise
                     and measure the pipeline.

WHY THIS IS NOT A LOOPHOLE
--------------------------
A control is held to the INTEGRITY gates (data availability, economic rationale,
implementation integrity, cost robustness) and is explicitly exempt from the
EDGE gates (replay adequacy, holdout behaviour, multiple-testing control),
because it is not claiming an edge. The exemption is safe precisely because the
claim is absent.

Three structural guarantees stop it becoming a back door:

  1. A control can NEVER transition directly to champion. It has to earn
     challenger status through the full eight gates like anything else.
  2. Every metric derived from a control carries `alpha_claim: false` and the
     reports print the control label beside the number.
  3. The leaderboard already refuses to rank anything that has not survived
     FDR, so a control cannot drift to the top by accumulating rows.

WHAT STOPS THIS FORCING TRADES
------------------------------
Nothing here lowers a threshold. Every signal fires on the rule preregistered in
`strategy_library`, unchanged. The caps below only ever REDUCE the number of
positions:

  * one open position per (strategy, security) -- no pyramiding
  * a hard concurrent cap per strategy, so `baseline_momentum` (which fires on
    ~74% of security-days) cannot consume the entire paper-learning capacity
    and drown out the strategies that fire rarely
  * equal notional, so a high-priced security does not dominate the book

ISOLATION BY CONSTRUCTION
-------------------------
One `PaperTradingLoop` per strategy version, each with its own store path. The
existing paper loop is reused unchanged -- no second book implementation, and
no possibility of pooling two strategies' trades into one metric.

ONE HORIZON LIVE, NOT SIX
-------------------------
A strategy declares several horizons for replay analysis. Live paper uses only
its PRIMARY (first-declared) horizon and opens ONE position per signal. Opening
one position per horizon would create six positions that share an entry and are
almost perfectly correlated, then count them as six observations -- the exact
inflation `horizons.horizon_cluster_key` exists to prevent.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence

from intent_engine.market.costs import DEFAULT as DEFAULT_COSTS, CostModel
from intent_engine.market.horizons import trading_days_after
from intent_engine.market.trading_mode import assert_paper_only

# --- preregistered allocation ----------------------------------------------
# Fixed before the first position. Editing any of these after seeing results
# would be tuning an allocation rule against its own outcome.
ALLOCATION_VERSION = "paper_alloc.v2"
MAX_CONCURRENT_PER_STRATEGY = 20
NOTIONAL_PER_POSITION = 1000.0
STARTING_EQUITY = 100_000.0
MIN_BARS_FOR_ENTRY = 25          # >= the longest strategy lookback, plus slack

# CAPACITY PROTECTION (v2). A control exists to validate plumbing; it must
# never be the reason a genuine challenger cannot get a position.
MAX_AGGREGATE_CONTROL_POSITIONS = 45     # across ALL control strategies
MAX_CONTROL_NOTIONAL = 45_000.0          # 45% of starting equity, hard ceiling
MAX_PER_SECTOR = 8                       # correlated-exposure cap
BENCHMARK = "SPY"

# THE LABEL. One string, used everywhere, so it cannot drift between the
# position record, the book summary and the report.
CONTROL_LABEL = "PAPER_CONTROL — NO ALPHA CLAIM"

# GRADUATION. A control that runs forever has stopped being an experiment and
# become a habit. These are the preregistered conditions under which its
# infrastructure-validation purpose is complete.
GRADUATION = {
    "min_resolved": 200,
    "min_distinct_securities": 30,
    "min_distinct_sessions": 20,
    "max_operational_failure_rate": 0.02,
    "required_lifecycle_stages": ("entry", "reconciliation", "exit",
                                  "benchmark", "reporting"),
}
# After graduation the control keeps a small permanent canary so a regression
# in the pipeline is still detected -- but stops consuming learning capacity.
CANARY_MAX_POSITIONS = 3

# The state this module introduces. Deliberately NOT in strategy.STATES: it is
# an operating mode for the paper engine, not a claim about the strategy, and
# keeping it out of the lifecycle machine means it can never be confused with
# a promotion.
PAPER_CONTROL = "PAPER_CONTROL"

BOOK_DIR = "reports/market/paper"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Entry:
    """One paper position about to be opened, fully accounted for."""
    strategy_key: str
    security: str
    as_of: str
    direction: str
    entry_price: float
    horizon_days: int
    resolve_on: str
    signal_value: Optional[float]
    reason: str
    sector: str = ""
    alpha_claim: bool = False
    mode: str = PAPER_CONTROL
    label: str = CONTROL_LABEL

    def as_dict(self) -> dict:
        return {"strategy_key": self.strategy_key, "security": self.security,
                "as_of": self.as_of, "direction": self.direction,
                "entry_price": self.entry_price,
                "horizon_days": self.horizon_days,
                "resolve_on": self.resolve_on,
                "signal_value": self.signal_value, "reason": self.reason,
                "sector": self.sector, "alpha_claim": self.alpha_claim,
                "mode": self.mode, "label": self.label}


@dataclass(frozen=True)
class Resolution:
    strategy_key: str
    security: str
    opened_at: str
    resolved_at: str
    direction: str
    entry_price: float
    exit_price: float
    gross_return: float
    cost: float
    net_return: float
    horizon_days: int
    correct: bool
    # BENCHMARK, measured over the IDENTICAL holding window. Comparing a
    # position's return to a benchmark measured over a different window is the
    # quiet way to manufacture outperformance, so both endpoints come from the
    # same two dates or the field stays None.
    benchmark: Optional[str] = None
    benchmark_return: Optional[float] = None
    excess_return: Optional[float] = None
    alpha_claim: bool = False
    label: str = CONTROL_LABEL

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("strategy_key", "security", "opened_at", "resolved_at",
                 "direction", "entry_price", "exit_price", "gross_return",
                 "cost", "net_return", "horizon_days", "correct",
                 "benchmark", "benchmark_return", "excess_return",
                 "alpha_claim", "label")}


def benchmark_return(series: Dict[str, float], start: str,
                     end: str) -> Optional[float]:
    """Benchmark move over EXACTLY the position's holding window.

    Returns None -- never 0.0 -- when either endpoint is missing. A zero would
    silently turn "we could not measure the benchmark" into "the benchmark did
    not move", which flatters every excess-return figure computed from it.
    """
    a, b = (series or {}).get(start[:10]), (series or {}).get(end[:10])
    if not a or not b:
        return None
    return (b - a) / a


class PaperBook:
    """One strategy version's own book. Append-only; isolated by path."""

    def __init__(self, strategy_key: str, root="."):
        self.strategy_key = strategy_key
        safe = strategy_key.replace(".", "_")
        self.path = pathlib.Path(root) / BOOK_DIR / f"{safe}.jsonl"

    def _rows(self) -> List[dict]:
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

    def _append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def open_positions(self) -> List[dict]:
        """Folded from the log: opened, minus anything since resolved."""
        opened = {}
        for row in self._rows():
            key = (row.get("security"), row.get("as_of") or row.get("opened_at"))
            if row.get("record") == "entry":
                opened[key] = row
            elif row.get("record") == "resolution":
                opened.pop((row.get("security"), row.get("opened_at")), None)
        return list(opened.values())

    def resolutions(self) -> List[dict]:
        return [r for r in self._rows() if r.get("record") == "resolution"]

    def record_entry(self, entry: Entry) -> None:
        self._append({"record": "entry", "at": _now(), **entry.as_dict()})

    def record_resolution(self, resolution: Resolution) -> None:
        self._append({"record": "resolution", "at": _now(),
                      **resolution.as_dict()})

    def held_securities(self) -> set:
        return {r.get("security") for r in self.open_positions()}


def _closes_upto(closes: Dict[str, float], as_of: str) -> List[float]:
    return [v for _, v in sorted((d, v) for d, v in (closes or {}).items()
                                 if d <= as_of[:10] and v)]


def open_entries(*, strategy_key: str, signal_fn: Callable,
                 primary_horizon: int, securities: Sequence,
                 series_for: Callable[[str], Dict[str, float]],
                 as_of: str, book: PaperBook,
                 max_concurrent: int = MAX_CONCURRENT_PER_STRATEGY,
                 aggregate_open: int = 0, challenger_demand: int = 0,
                 canary: bool = False,
                 env: Optional[dict] = None) -> List[Entry]:
    """Open paper positions for whatever fired today, within the caps.

    PAPER ONLY, re-asserted here as well as at cycle start: this is the one
    function in the new code that creates a position, so it re-checks rather
    than trusting the caller.
    """
    assert_paper_only(env)
    held = book.held_securities()

    # CAPACITY, in priority order. A control yields to everything.
    #
    # `challenger_demand` is the number of positions a genuine PAPER_CHALLENGER
    # wants right now. Controls give up capacity to it first, because a control
    # validates plumbing and a challenger tests a hypothesis -- and a pipeline
    # that is already proven has nothing left to learn from position 46.
    remaining_aggregate = max(
        MAX_AGGREGATE_CONTROL_POSITIONS - aggregate_open - challenger_demand, 0)
    remaining_notional = int(
        max(MAX_CONTROL_NOTIONAL - aggregate_open * NOTIONAL_PER_POSITION, 0)
        // NOTIONAL_PER_POSITION)
    if canary:
        max_concurrent = min(max_concurrent, CANARY_MAX_POSITIONS)
    capacity = min(max(max_concurrent - len(held), 0),
                   remaining_aggregate, remaining_notional)
    entries: List[Entry] = []
    per_sector: Dict[str, int] = {}
    for row in book.open_positions():
        sec = row.get("sector") or "?"
        per_sector[sec] = per_sector.get(sec, 0) + 1

    for security in securities:
        if capacity <= 0:
            break
        symbol = getattr(security, "symbol", str(security))
        sector = getattr(security, "sector", "") or "?"
        if symbol in held:
            continue                      # no pyramiding
        # CORRELATED EXPOSURE. Twenty technology positions on one macro day is
        # one bet held twenty times, and it would make the book look far more
        # diversified than it is.
        if per_sector.get(sector, 0) >= MAX_PER_SECTOR:
            continue
        if hasattr(security, "eligible_on") and not security.eligible_on(as_of):
            continue                      # outside the listing window
        closes = series_for(symbol) or {}
        usable = _closes_upto(closes, as_of)
        if len(usable) < MIN_BARS_FOR_ENTRY:
            continue
        entry_price = closes.get(as_of[:10])
        if not entry_price:
            # No bar on the decision date. Never substituted with the previous
            # close: an entry at a price the market did not print on the day of
            # the decision is a fabricated fill.
            continue
        signal = signal_fn(closes, security=symbol, as_of=as_of)
        if not signal.fired:
            continue
        resolve_on = trading_days_after(as_of, primary_horizon)
        if not resolve_on:
            continue
        entries.append(Entry(
            strategy_key=strategy_key, security=symbol, as_of=as_of[:10],
            direction=signal.direction, entry_price=float(entry_price),
            horizon_days=primary_horizon, resolve_on=resolve_on,
            signal_value=signal.value, reason=signal.reason,
            sector=sector))
        per_sector[sector] = per_sector.get(sector, 0) + 1
        capacity -= 1

    for entry in entries:
        book.record_entry(entry)
    return entries


def resolve_due(*, book: PaperBook,
                series_for: Callable[[str], Dict[str, float]],
                today: str, costs: Optional[CostModel] = None,
                benchmark: str = BENCHMARK) -> List[Resolution]:
    """Close every position whose preregistered horizon has fully elapsed.

    Three refusals, each a lookahead guard and each identical in spirit to the
    ones in `signal_opportunity.resolve_outcome`:

      * horizon not elapsed        -> left open, never graded early
      * no bar on the resolve date -> left open, retried next cycle, never
                                      filled from a later or earlier price
      * already resolved           -> untouched, so a rerun cannot re-mark an
                                      outcome against a different price
    """
    costs = costs or DEFAULT_COSTS
    out: List[Resolution] = []
    for row in book.open_positions():
        resolve_on = row.get("resolve_on")
        if not resolve_on or resolve_on > today[:10]:
            continue
        closes = series_for(row["security"]) or {}
        exit_price = closes.get(resolve_on)
        if not exit_price:
            continue
        priced = costs.apply(entry=row["entry_price"], exit_=float(exit_price),
                             direction=row["direction"])
        bench = benchmark_return(series_for(benchmark) or {},
                                 row["as_of"], resolve_on)
        excess = (None if bench is None
                  else round(priced["net_return"] - bench, 6))
        resolution = Resolution(
            strategy_key=row["strategy_key"], security=row["security"],
            opened_at=row["as_of"], resolved_at=resolve_on,
            direction=row["direction"], entry_price=row["entry_price"],
            exit_price=float(exit_price),
            gross_return=priced["gross_return"], cost=priced["cost"],
            net_return=priced["net_return"],
            horizon_days=row.get("horizon_days", 0),
            correct=priced["net_return"] > 0,
            benchmark=benchmark,
            benchmark_return=(None if bench is None else round(bench, 6)),
            excess_return=excess)
        book.record_resolution(resolution)
        out.append(resolution)
    return out


def book_summary(book: PaperBook) -> dict:
    """One strategy's paper record, always labelled as a control.

    `alpha_claim: false` is on every row this engine writes and is repeated
    here, because a win rate printed without it will eventually be read as an
    edge by someone skimming.
    """
    resolutions = book.resolutions()
    nets = [r["net_return"] for r in resolutions
            if r.get("net_return") is not None]
    wins = [n for n in nets if n > 0]
    equity = STARTING_EQUITY
    for r in sorted(resolutions, key=lambda x: str(x.get("resolved_at"))):
        equity += NOTIONAL_PER_POSITION * (r.get("net_return") or 0.0)
    return {
        "strategy_key": book.strategy_key,
        "mode": PAPER_CONTROL,
        "alpha_claim": False,
        "open_positions": len(book.open_positions()),
        "resolved": len(resolutions),
        "win_rate": round(len(wins) / len(nets), 4) if nets else None,
        "mean_net_return": round(sum(nets) / len(nets), 6) if nets else None,
        "equity": round(equity, 2),
        "allocation": ALLOCATION_VERSION,
        "note": ("CONTROL — this strategy has no measured edge (Day 18: "
                 "p >= 0.72, zero FDR survivors). These observations validate "
                 "the resolution pipeline and feed calibration; they are not "
                 "evidence of alpha."),
    }


# ---------------------------------------------------------------------------
# CALIBRATION SEPARATION
#
# The distinction the whole contract turns on: a control validates the ENGINE,
# never the SIGNAL. Both would be computed from the same resolutions, so the
# only thing keeping them apart is that they are computed by different
# functions with different eligibility -- and that `strategy_calibration`
# refuses outright until the strategy has passed its own statistical gates.
# ---------------------------------------------------------------------------
ENGINE_CALIBRATION = "ENGINE CALIBRATION"
STRATEGY_CALIBRATION = "STRATEGY CALIBRATION"


def engine_calibration(resolutions: Sequence[dict]) -> dict:
    """Did the PLUMBING work? Answerable from control data.

    Every question here is about mechanics -- did a position open, did it
    reconcile, did it exit on the right date, was a cost applied, was a
    benchmark captured. None of them is about whether the signal was any good.
    """
    n = len(resolutions)
    if not n:
        return {"kind": ENGINE_CALIBRATION, "resolved": 0,
                "measurable": False,
                "reason": "no resolved control positions yet"}
    priced = sum(1 for r in resolutions if r.get("cost") is not None)
    benched = sum(1 for r in resolutions
                  if r.get("benchmark_return") is not None)
    dated = sum(1 for r in resolutions
                if r.get("resolved_at") and r.get("opened_at")
                and r["resolved_at"] > r["opened_at"])
    return {
        "kind": ENGINE_CALIBRATION,
        "resolved": n,
        "cost_accounting_coverage": round(priced / n, 4),
        "benchmark_coverage": round(benched / n, 4),
        "exit_after_entry_rate": round(dated / n, 4),
        "distinct_securities": len({r.get("security") for r in resolutions}),
        "distinct_sessions": len({r.get("opened_at") for r in resolutions}),
        "measurable": True,
        "validates": "execution, entry/exit correctness, cost accounting, "
                     "reconciliation, resolution and reporting mechanics",
        "does_not_validate": "signal quality",
    }


def strategy_calibration(strategy_key: str, passed_statistical_gates: bool,
                         resolutions: Sequence[dict]) -> dict:
    """Was the SIGNAL any good? REFUSED for a control.

    This is the function a future reader will be tempted to call on control
    data, so it refuses by contract rather than by convention. Control
    resolutions may only validate signal quality once the same strategy has
    independently passed its preregistered statistical gates -- and none has.
    """
    if not passed_statistical_gates:
        return {"kind": STRATEGY_CALIBRATION, "strategy_key": strategy_key,
                "measurable": False, "eligible": False,
                "reason": (f"{strategy_key} has not passed its preregistered "
                           f"statistical gates. Control outcomes validate the "
                           f"pipeline, not the signal, and using them here "
                           f"would be an alpha claim built from plumbing "
                           f"data."),
                "resolved_available": len(resolutions)}
    return {"kind": STRATEGY_CALIBRATION, "strategy_key": strategy_key,
            "measurable": True, "eligible": True,
            "resolved": len(resolutions)}


# ---------------------------------------------------------------------------
# GRADUATION — a control must not run forever by default
# ---------------------------------------------------------------------------
def graduation_status(resolutions: Sequence[dict],
                      operational_failures: int = 0,
                      integrity_incidents: int = 0) -> dict:
    """Has the infrastructure-validation purpose been achieved?

    When it has, the control does NOT become a challenger -- that would be
    exactly the promotion the contract forbids. It drops to a small permanent
    canary so a future regression in the pipeline is still caught, and hands
    its capacity back to genuine hypothesis tests.
    """
    n = len(resolutions)
    securities = len({r.get("security") for r in resolutions})
    sessions = len({r.get("opened_at") for r in resolutions})
    failure_rate = (operational_failures / (n + operational_failures)
                    if (n + operational_failures) else 0.0)
    benched = sum(1 for r in resolutions
                  if r.get("benchmark_return") is not None)

    checks = {
        "resolved": (n, GRADUATION["min_resolved"], n >= GRADUATION["min_resolved"]),
        "distinct_securities": (securities, GRADUATION["min_distinct_securities"],
                                securities >= GRADUATION["min_distinct_securities"]),
        "distinct_sessions": (sessions, GRADUATION["min_distinct_sessions"],
                              sessions >= GRADUATION["min_distinct_sessions"]),
        "operational_failure_rate": (round(failure_rate, 4),
                                     GRADUATION["max_operational_failure_rate"],
                                     failure_rate <= GRADUATION["max_operational_failure_rate"]),
        "benchmark_coverage": (round(benched / n, 4) if n else 0.0, 1.0,
                               bool(n) and benched == n),
        "integrity_incidents": (integrity_incidents, 0,
                                integrity_incidents == 0),
    }
    unmet = [k for k, (_, _, ok) in checks.items() if not ok]
    graduated = not unmet
    return {
        "graduated": graduated,
        "mode": "CANARY" if graduated else PAPER_CONTROL,
        "canary_max_positions": CANARY_MAX_POSITIONS if graduated else None,
        "checks": {k: {"value": v, "required": r, "met": ok}
                   for k, (v, r, ok) in checks.items()},
        "unmet": unmet,
        "note": ("infrastructure objective achieved — control drops to a "
                 "permanent canary and returns capacity to genuine "
                 "challengers. It does NOT become a challenger."
                 if graduated else
                 f"infrastructure objective not yet achieved; unmet: {unmet}"),
    }


def excluded_from_alpha(rows: Sequence[dict]) -> List[dict]:
    """Strip every control record before anything computes an alpha claim.

    The single choke point. Ranking, promotion, FDR selection and champion
    choice all call this first, so a control cannot contaminate them by being
    forgotten at one call site.
    """
    return [r for r in rows
            if not (r.get("mode") == PAPER_CONTROL
                    or r.get("alpha_claim") is False
                    and r.get("label") == CONTROL_LABEL)]

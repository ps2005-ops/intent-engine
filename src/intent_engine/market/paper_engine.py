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
ALLOCATION_VERSION = "paper_alloc.v1"
MAX_CONCURRENT_PER_STRATEGY = 20
NOTIONAL_PER_POSITION = 1000.0
STARTING_EQUITY = 100_000.0
MIN_BARS_FOR_ENTRY = 25          # >= the longest strategy lookback, plus slack

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
    alpha_claim: bool = False
    mode: str = PAPER_CONTROL

    def as_dict(self) -> dict:
        return {"strategy_key": self.strategy_key, "security": self.security,
                "as_of": self.as_of, "direction": self.direction,
                "entry_price": self.entry_price,
                "horizon_days": self.horizon_days,
                "resolve_on": self.resolve_on,
                "signal_value": self.signal_value, "reason": self.reason,
                "alpha_claim": self.alpha_claim, "mode": self.mode}


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
    alpha_claim: bool = False

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("strategy_key", "security", "opened_at", "resolved_at",
                 "direction", "entry_price", "exit_price", "gross_return",
                 "cost", "net_return", "horizon_days", "correct",
                 "alpha_claim")}


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
                 env: Optional[dict] = None) -> List[Entry]:
    """Open paper positions for whatever fired today, within the caps.

    PAPER ONLY, re-asserted here as well as at cycle start: this is the one
    function in the new code that creates a position, so it re-checks rather
    than trusting the caller.
    """
    assert_paper_only(env)
    held = book.held_securities()
    capacity = max(max_concurrent - len(held), 0)
    entries: List[Entry] = []

    for security in securities:
        if capacity <= 0:
            break
        symbol = getattr(security, "symbol", str(security))
        if symbol in held:
            continue                      # no pyramiding
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
            signal_value=signal.value, reason=signal.reason))
        capacity -= 1

    for entry in entries:
        book.record_entry(entry)
    return entries


def resolve_due(*, book: PaperBook,
                series_for: Callable[[str], Dict[str, float]],
                today: str, costs: Optional[CostModel] = None
                ) -> List[Resolution]:
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
        resolution = Resolution(
            strategy_key=row["strategy_key"], security=row["security"],
            opened_at=row["as_of"], resolved_at=resolve_on,
            direction=row["direction"], entry_price=row["entry_price"],
            exit_price=float(exit_price),
            gross_return=priced["gross_return"], cost=priced["cost"],
            net_return=priced["net_return"],
            horizon_days=row.get("horizon_days", 0),
            correct=priced["net_return"] > 0)
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

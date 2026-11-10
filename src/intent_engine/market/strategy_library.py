"""The three preregistered strategies, and the two that were refused.

WHAT IS HERE
------------
`baseline_momentum.v1`   the incumbent, already measured at 0.500 (no edge)
`mean_reversion.v1`      new
`volatility_breakout.v1` new

WHAT IS NOT HERE, AND WHY THAT IS THE MORE IMPORTANT PART
----------------------------------------------------------
`earnings_revision` and `sector_relative_strength` appear in the mission and are
NOT implemented, because GATE 1 fails: this project has no point-in-time
analyst-estimate feed and no point-in-time sector-membership history. Building
them on today's sector labels or on current consensus would be a lookahead bug
wearing the costume of a strategy. The refusal is recorded as a first-class
result in `REFUSED`, not omitted.

EVERY SIGNAL HERE IS POINT-IN-TIME BY CONSTRUCTION
--------------------------------------------------
Each takes the full `closes` map and filters to dates <= as_of as its first act.
The suite asserts that appending future bars cannot change any signal. That
single property is what makes replay results mean anything.

THE EXPECTED RESULT
-------------------
No edge, after costs, for any of them. Eleven hypotheses have been proposed here
and eleven retired; the one wired signal measures 0.500. These exist to convert
"we cannot tell" into "we measured it and it was flat", which is the honest
product of a research cycle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from intent_engine.market.horizons import HorizonSet
from intent_engine.market.strategy import StrategySpec

LONG = "long"
SHORT = "short"
FLAT = ""

# Refused strategies, kept visible. A gate failure is a finding.
REFUSED = {
    "earnings_revision": {
        "gate": "GATE_1_DATA_AVAILABILITY",
        "passed": False,
        "reason": "no point-in-time analyst-estimate feed exists in this "
                  "project. Current consensus applied to a past date is "
                  "lookahead, and a proxy built from price would not be an "
                  "earnings-revision strategy at all.",
    },
    "sector_relative_strength": {
        "gate": "GATE_1_DATA_AVAILABILITY",
        "passed": False,
        "reason": "no point-in-time sector-membership history exists. Today's "
                  "sector labels applied across ten years silently reclassify "
                  "every company that changed sector, and the bias runs "
                  "toward whatever grouping worked.",
    },
}


def _closes_upto(closes: Dict[str, float], as_of: str) -> List[float]:
    """THE point-in-time filter. First act of every signal in this module."""
    return [v for _, v in sorted((d, v) for d, v in (closes or {}).items()
                                 if d <= as_of[:10] and v)]


@dataclass(frozen=True)
class Signal:
    """A decision, with the numbers that produced it recorded."""
    strategy_key: str
    security: str
    as_of: str
    direction: str
    fired: bool
    value: Optional[float]
    threshold: float
    reason: str
    bars_used: int

    def as_dict(self) -> dict:
        return {"strategy_key": self.strategy_key, "security": self.security,
                "as_of": self.as_of, "direction": self.direction,
                "fired": self.fired, "value": self.value,
                "threshold": self.threshold, "reason": self.reason,
                "bars_used": self.bars_used}


def _flat(key, security, as_of, threshold, reason, bars) -> Signal:
    return Signal(key, security, as_of, FLAT, False, None, threshold, reason,
                  bars)


# --- 1. baseline momentum ---------------------------------------------------
MOMENTUM_LOOKBACK = 20
MOMENTUM_THRESHOLD = 0.02          # the shipped MIN_ABS_RETURN, unchanged


def baseline_momentum(closes, *, security: str, as_of: str) -> Signal:
    """Trailing direction persists. Measured at 0.500 — recorded, not hidden."""
    key = "baseline_momentum.v1"
    series = _closes_upto(closes, as_of)
    if len(series) < MOMENTUM_LOOKBACK + 1:
        return _flat(key, security, as_of, MOMENTUM_THRESHOLD,
                     "insufficient history", len(series))
    window = series[-(MOMENTUM_LOOKBACK + 1):]
    trailing = (window[-1] - window[0]) / window[0] if window[0] else 0.0
    if abs(trailing) < MOMENTUM_THRESHOLD:
        return Signal(key, security, as_of, FLAT, False, round(trailing, 6),
                      MOMENTUM_THRESHOLD, "move inside the noise floor",
                      len(series))
    return Signal(key, security, as_of, LONG if trailing > 0 else SHORT, True,
                  round(trailing, 6), MOMENTUM_THRESHOLD,
                  "trailing move exceeds the noise floor", len(series))


# --- 2. mean reversion ------------------------------------------------------
REVERSION_LOOKBACK = 20
REVERSION_ENTRY_Z = 2.0            # standard deviations from the mean


def mean_reversion(closes, *, security: str, as_of: str) -> Signal:
    """Short-horizon overextension against a 20-day mean partially reverts.

    Falsifiable: if extended names keep extending, this is negative-expectancy
    and gets retired. Direction is OPPOSITE the recent move, which is what makes
    it genuinely independent of momentum rather than a re-parameterisation --
    the two disagree by construction on the same input.
    """
    key = "mean_reversion.v1"
    series = _closes_upto(closes, as_of)
    if len(series) < REVERSION_LOOKBACK + 1:
        return _flat(key, security, as_of, REVERSION_ENTRY_Z,
                     "insufficient history", len(series))
    window = series[-REVERSION_LOOKBACK:]
    mean = sum(window) / len(window)
    var = sum((p - mean) ** 2 for p in window) / (len(window) - 1)
    sd = math.sqrt(var)
    if not sd:
        return _flat(key, security, as_of, REVERSION_ENTRY_Z,
                     "zero dispersion; no overextension is definable",
                     len(series))
    z = (series[-1] - mean) / sd
    if abs(z) < REVERSION_ENTRY_Z:
        return Signal(key, security, as_of, FLAT, False, round(z, 6),
                      REVERSION_ENTRY_Z, "not overextended", len(series))
    # stretched UP -> expect reversion DOWN
    return Signal(key, security, as_of, SHORT if z > 0 else LONG, True,
                  round(z, 6), REVERSION_ENTRY_Z,
                  "overextended against the 20-day mean", len(series))


# --- 3. volatility breakout -------------------------------------------------
BREAKOUT_LOOKBACK = 20
BREAKOUT_BUFFER = 0.005            # must clear the range by 0.5%, not touch it


def volatility_breakout(closes, *, security: str, as_of: str) -> Signal:
    """A close outside the 20-day range marks a regime change that persists.

    The buffer matters: a close exactly AT the prior high is not a breakout, it
    is the high. Without it the signal fires constantly on flat tape and the
    trade count rises while nothing is learned.
    """
    key = "volatility_breakout.v1"
    series = _closes_upto(closes, as_of)
    if len(series) < BREAKOUT_LOOKBACK + 1:
        return _flat(key, security, as_of, BREAKOUT_BUFFER,
                     "insufficient history", len(series))
    prior, last = series[-(BREAKOUT_LOOKBACK + 1):-1], series[-1]
    hi, lo = max(prior), min(prior)
    if last > hi * (1 + BREAKOUT_BUFFER):
        return Signal(key, security, as_of, LONG, True,
                      round((last - hi) / hi, 6), BREAKOUT_BUFFER,
                      "closed above the 20-day range", len(series))
    if last < lo * (1 - BREAKOUT_BUFFER):
        return Signal(key, security, as_of, SHORT, True,
                      round((last - lo) / lo, 6), BREAKOUT_BUFFER,
                      "closed below the 20-day range", len(series))
    return Signal(key, security, as_of, FLAT, False, 0.0, BREAKOUT_BUFFER,
                  "inside the 20-day range", len(series))


SIGNALS = {
    "baseline_momentum.v1": baseline_momentum,
    "mean_reversion.v1": mean_reversion,
    "volatility_breakout.v1": volatility_breakout,
}


def specs() -> List[StrategySpec]:
    """The preregistered specifications. Horizons are declared HERE, before any
    replay runs, which is what makes hindsight selection impossible."""
    from intent_engine.market.universe_tiers import TIER_1
    at = "2026-08-01T00:00:00+00:00"
    return [
        StrategySpec(
            strategy_id="baseline_momentum", family="momentum", version="v1",
            economic_hypothesis=(
                "Trailing 20-day direction persists over the following month. "
                "ALREADY MEASURED AT 0.500 on this universe — carried as the "
                "control, not as a candidate."),
            required_data=("daily_closes",), signal_direction="long_short",
            thresholds={"lookback": MOMENTUM_LOOKBACK,
                        "min_abs_return": MOMENTUM_THRESHOLD},
            entry_timing="close of as_of", exit_timing="close at horizon",
            horizons=HorizonSet("baseline_momentum.v1", (20,), at),
            invalidation="net expectancy <= 0 after costs at n_eff >= 100",
            universe_tier=TIER_1,
            retirement_rules=("no edge after 100 effective observations",
                              "negative net expectancy after costs")),
        StrategySpec(
            strategy_id="mean_reversion", family="mean_reversion", version="v1",
            economic_hypothesis=(
                "Short-horizon overextension (>2 sd from a 20-day mean) is "
                "partly liquidity-driven and partially reverts within days. "
                "False if extended names continue extending."),
            required_data=("daily_closes",), signal_direction="long_short",
            thresholds={"lookback": REVERSION_LOOKBACK,
                        "entry_z": REVERSION_ENTRY_Z},
            entry_timing="close of as_of", exit_timing="close at horizon",
            horizons=HorizonSet("mean_reversion.v1", (3, 5, 10), at),
            invalidation="net expectancy <= 0 after costs at n_eff >= 100",
            universe_tier=TIER_1,
            retirement_rules=("no edge after 100 effective observations",
                              "negative net expectancy after costs",
                              "correlation > 0.8 with a better strategy")),
        StrategySpec(
            strategy_id="volatility_breakout", family="breakout", version="v1",
            economic_hypothesis=(
                "A close decisively outside a 20-day range reflects new "
                "information still being absorbed, so the move persists. False "
                "if breakouts revert."),
            required_data=("daily_closes",), signal_direction="long_short",
            thresholds={"lookback": BREAKOUT_LOOKBACK,
                        "buffer": BREAKOUT_BUFFER},
            entry_timing="close of as_of", exit_timing="close at horizon",
            horizons=HorizonSet("volatility_breakout.v1", (5, 10, 20), at),
            invalidation="net expectancy <= 0 after costs at n_eff >= 100",
            universe_tier=TIER_1,
            retirement_rules=("no edge after 100 effective observations",
                              "negative net expectancy after costs")),
    ]

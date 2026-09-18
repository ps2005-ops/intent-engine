"""Transaction costs — subtracted from every return, never optional.

WHY THIS EXISTS AT ALL
----------------------
Before Day 18 this project had **no cost model**. That was survivable only
because it had never opened a position; the moment it can generate thousands of
replay observations, a gross return is not a conservative simplification, it is
a wrong number. A 10 bps round trip is larger than the entire edge most
short-horizon price effects have ever been credited with, so "we will add costs
later" is equivalent to "we will decide later whether our results are real".

THE DEFAULTS, AND WHY THEY ARE THESE
------------------------------------
Preregistered in `docs/PREREGISTRATION_day18_learning_rate.md` before any
result was computed:

  commission   0 bps    retail equity commissions are genuinely zero now
  slippage     5 bps    per side, applied on entry AND exit
  round trip  10 bps

5 bps per side is conservative for liquid large-cap names and ETFs and
optimistic for anything thin -- which is exactly why the universe eligibility
rules carry a liquidity floor. The two are a pair: a cost assumption is only
honest for securities that actually trade.

THE RULE THIS MODULE ENFORCES
-----------------------------
`net_return` is the only return the reports print. `gross` is available for
diagnosis and is never displayed on its own, because a gross Sharpe next to a
net one invites the reader to average them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Preregistered. Changing any of these requires a new model version and a new
# preregistration -- a cost assumption edited after seeing results is the
# cheapest possible way to manufacture an edge.
MODEL_VERSION = "cost.v1"
COMMISSION_BPS = 0.0
SLIPPAGE_BPS_PER_SIDE = 5.0
BPS = 1e-4


@dataclass(frozen=True)
class CostModel:
    """Explicit, versioned, and applied symmetrically to longs and shorts."""
    version: str = MODEL_VERSION
    commission_bps: float = COMMISSION_BPS
    slippage_bps_per_side: float = SLIPPAGE_BPS_PER_SIDE

    @property
    def round_trip_bps(self) -> float:
        return 2 * (self.commission_bps + self.slippage_bps_per_side)

    def net_return(self, gross: float) -> float:
        """Gross return minus the full round trip.

        Subtractive rather than multiplicative on purpose: the cost is paid on
        notional at both ends regardless of which way the trade went, and a
        multiplicative form would quietly charge a winner more than a loser.
        """
        return gross - self.round_trip_bps * BPS

    def apply(self, *, entry: float, exit_: float, direction: str) -> dict:
        """One trade, fully accounted.

        A SHORT's gross return is the negation of the price change -- stated
        explicitly rather than by sign convention, because getting it backwards
        produces a beautifully profitable strategy that is exactly wrong.
        """
        if not entry:
            raise ValueError("entry price must be non-zero")
        move = (exit_ - entry) / entry
        gross = move if direction == "long" else -move
        return {"direction": direction, "entry": entry, "exit": exit_,
                "gross_return": round(gross, 6),
                "cost": round(self.round_trip_bps * BPS, 6),
                "net_return": round(self.net_return(gross), 6),
                "cost_model": self.version}


DEFAULT = CostModel()


def survives_costs(gross_edge: float, model: Optional[CostModel] = None
                   ) -> bool:
    """Would this edge still exist after the round trip?

    GATE 5. An edge smaller than the cost of capturing it is not a small edge,
    it is a loss, and the difference is the single most common way a backtest
    flatters itself.
    """
    model = model or DEFAULT
    return model.net_return(gross_edge) > 0

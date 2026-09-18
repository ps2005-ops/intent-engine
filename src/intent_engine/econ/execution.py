"""Execution realism, and the boundary that keeps capital out of it.

WHAT STAGE THIS IS
------------------
PAPER. SHADOW. NO LIVE AUTONOMOUS ORDERS. That is the current stage and this
module is written to make the next one a deliberate, separately-authorised
decision rather than a configuration change somebody makes on a Tuesday.

WHY NOT LIVE MICRO-CAPITAL NOW
------------------------------
Not caution for its own sake: there are not yet enough resolved forward
predictions to calibrate against. `calibration` reports PRE_CALIBRATION, and
connecting execution feedback to beliefs before that is measured means the
first thing the belief system learns is the noise in its own fills.

THE THREE ADAPTERS
------------------
    PaperExecutionAdapter   fills against a reference price with modelled
                            cost and impact. What runs today.
    ShadowBrokerAdapter     replays a broker's own fill semantics without
                            sending anything. What must run before live.
    LiveBrokerAdapter       raises. Always. See below.

WHY THE LIVE ADAPTER IS A CLASS THAT RAISES RATHER THAN AN ABSENT FILE
-----------------------------------------------------------------------
An absent file is added by anyone in an afternoon, and the boundary would
live in a memory of a decision. A class that exists, is imported, is covered
by a test asserting it raises, and states in its own body what would have to
be true first, is a boundary someone has to argue with in a diff. Enabling it
requires a NEW authorisation constant that does not exist anywhere in this
repository -- so the change is visible as an addition, not as a flag flip.

ALMGREN-CHRISS, AND WHAT IT IS ACTUALLY FOR
--------------------------------------------
The impact model is not here to be right about impact. It is here to make
size COST something, so that a strategy which "works" only by assuming
frictionless fills of 40% of a day's volume is refused by arithmetic rather
than by review. Temporary impact scales with participation rate; permanent
impact scales with the fraction of daily volume traded. Both coefficients are
declared, adjustable, and reported with every fill.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_execution.v1"

PAPER = "PAPER"
SHADOW = "SHADOW"
LIVE = "LIVE"


class LiveExecutionRefused(EconError):
    """The live boundary. Raised unconditionally by `LiveBrokerAdapter`."""


class ImpossibleFill(EconError):
    """A fill that the stated market conditions could not have produced."""


# --- cost model -------------------------------------------------------------
@dataclass(frozen=True)
class MarketConditions:
    """What the venue looked like when the order was worked."""

    reference_price: float
    spread_bps: float
    daily_volume: float
    volatility_daily: float
    #: Fraction of daily volume this order may take. Above this the order is
    #: not executable in the window and `fill` refuses rather than modelling.
    max_participation: float = 0.10

    def __post_init__(self) -> None:
        require(self.reference_price > 0, "a price is positive")
        require(self.spread_bps >= 0, "a spread is non-negative")
        require(self.daily_volume > 0,
                "an instrument with no volume has no executable price; "
                "modelling a fill in it would be inventing liquidity")
        require(self.volatility_daily >= 0, "volatility is non-negative")


@dataclass(frozen=True)
class ImpactModel:
    """Almgren-Chriss-style, with both coefficients declared.

    Defaults are ORDER-OF-MAGNITUDE conventions from the public literature,
    not estimates from this engine's own fills -- it has none. They are
    stated here so that a reader knows the numbers are assumptions, and so a
    sensitivity run can move them.
    """

    #: temporary impact coefficient, in units of daily volatility
    eta: float = 0.10
    #: permanent impact coefficient, in units of daily volatility
    gamma: float = 0.05
    #: commission and fees, basis points of notional
    fee_bps: float = 1.0

    def temporary_bps(self, participation: float, vol_daily: float) -> float:
        """Scales with participation rate. Square-root is the usual shape."""
        return self.eta * vol_daily * 10000.0 * math.sqrt(
            max(participation, 0.0))

    def permanent_bps(self, participation: float, vol_daily: float) -> float:
        """Scales linearly with the fraction of the day's volume taken."""
        return self.gamma * vol_daily * 10000.0 * max(participation, 0.0)


@dataclass(frozen=True)
class Fill:
    """One simulated execution, with every component of its cost named."""

    side: str
    quantity: float
    signal_price: float
    executed_price: float
    spread_cost_bps: float
    temporary_impact_bps: float
    permanent_impact_bps: float
    fee_bps: float
    participation: float
    mode: str

    @property
    def slippage_bps(self) -> float:
        """Total distance from the price the signal saw."""
        direction = 1.0 if self.side == "BUY" else -1.0
        return direction * (self.executed_price - self.signal_price) / \
            self.signal_price * 10000.0

    @property
    def total_cost_bps(self) -> float:
        return (self.spread_cost_bps + self.temporary_impact_bps
                + self.permanent_impact_bps + self.fee_bps)

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "side": self.side,
                "quantity": self.quantity,
                "signal_price": round(self.signal_price, 6),
                "executed_price": round(self.executed_price, 6),
                "slippage_bps": round(self.slippage_bps, 3),
                "costs_bps": {
                    "spread": round(self.spread_cost_bps, 3),
                    "temporary_impact": round(self.temporary_impact_bps, 3),
                    "permanent_impact": round(self.permanent_impact_bps, 3),
                    "fees": round(self.fee_bps, 3),
                    "total": round(self.total_cost_bps, 3)},
                "participation": round(self.participation, 5),
                "mode": self.mode}


# --- adapters ---------------------------------------------------------------
class ExecutionAdapter:
    """The interface. Three implementations, one of which always raises."""

    mode = ""

    def fill(self, *, side: str, quantity: float,
             conditions: MarketConditions,
             impact: ImpactModel) -> Fill:      # pragma: no cover - abstract
        raise NotImplementedError


class PaperExecutionAdapter(ExecutionAdapter):
    """Modelled fills. What runs today, and what every number comes from."""

    mode = PAPER

    def fill(self, *, side: str, quantity: float,
             conditions: MarketConditions, impact: ImpactModel) -> Fill:
        require(side in ("BUY", "SELL"), f"unknown side {side!r}")
        require(quantity > 0, "a fill has positive quantity")
        participation = quantity / conditions.daily_volume
        if participation > conditions.max_participation:
            raise ImpossibleFill(
                f"the order is {participation:.1%} of daily volume, above "
                f"the {conditions.max_participation:.0%} participation cap. "
                "A model that fills this would be inventing liquidity, and a "
                "strategy that needs it does not exist at this size.")
        half_spread = conditions.spread_bps / 2.0
        temp = impact.temporary_bps(participation, conditions.volatility_daily)
        perm = impact.permanent_bps(participation, conditions.volatility_daily)
        # Costs always move the price AGAINST the order. This is the one
        # place a sign error would silently create alpha.
        adverse_bps = half_spread + temp + perm
        direction = 1.0 if side == "BUY" else -1.0
        executed = conditions.reference_price * (
            1.0 + direction * adverse_bps / 10000.0)
        return Fill(side=side, quantity=quantity,
                    signal_price=conditions.reference_price,
                    executed_price=executed, spread_cost_bps=half_spread,
                    temporary_impact_bps=temp, permanent_impact_bps=perm,
                    fee_bps=impact.fee_bps, participation=participation,
                    mode=self.mode)


class ShadowBrokerAdapter(PaperExecutionAdapter):
    """Broker-replay semantics, still sending nothing.

    Distinct from `PaperExecutionAdapter` in what it is FOR rather than in
    arithmetic today: this is where a specific broker's order types, minimum
    increments, partial-fill behaviour and rejection rules are reproduced, so
    that the difference between the model and the venue is measured BEFORE
    any capital is involved. It inherits the cost model deliberately -- a
    shadow that is more optimistic than paper would be worse than useless.
    """

    mode = SHADOW


class LiveBrokerAdapter(ExecutionAdapter):
    """Disabled. Permanently, at this stage, by construction.

    WHAT WOULD HAVE TO BE TRUE FIRST
    --------------------------------
    1. `calibration.status()` reports CALIBRATED rather than PRE_CALIBRATION,
       on a real forward sample meeting the declared minimum.
    2. The shadow adapter's fills have been reconciled against a broker's own
       fills over a stated period, and the divergence is measured.
    3. A separate, explicit authorisation object exists -- it does not exist
       anywhere in this repository -- and the person enabling it has to add
       it, which makes the change a visible addition rather than a flag.

    None of those is satisfied. This raises.
    """

    mode = LIVE

    def __init__(self, *args, **kwargs) -> None:
        raise LiveExecutionRefused(
            "live execution is not part of this system. Paper and shadow "
            "only: there are not yet enough resolved forward predictions to "
            "calibrate against, and connecting execution feedback to beliefs "
            "before that means the first thing the belief system learns is "
            "the noise in its own fills. See this class's docstring for the "
            "three conditions.")

    def fill(self, **kwargs):  # pragma: no cover - unreachable, __init__ raises
        raise LiveExecutionRefused("live execution is not part of this system")


def adapter_for(mode: str) -> ExecutionAdapter:
    """Resolve a mode to an adapter. LIVE resolves and then refuses."""
    if mode == PAPER:
        return PaperExecutionAdapter()
    if mode == SHADOW:
        return ShadowBrokerAdapter()
    if mode == LIVE:
        return LiveBrokerAdapter()          # raises, by design
    raise EconError(f"unknown execution mode {mode!r}")


# --- toxicity proxy (Section 13) -------------------------------------------
@dataclass(frozen=True)
class ToxicityProxy:
    """A VPIN-style order-flow imbalance reading. A PROXY, labelled as one.

    WHAT IT IS NOT: a measurement of informed trading. VPIN classifies volume
    into buy- and sell-initiated using a bulk rule, and the classification is
    an assumption, not an observation. At daily resolution -- which is what
    this engine has -- the rule is at its weakest, because a day's volume
    contains every kind of participant.

    So `value` is reported with `resolution`, `assumptions` and `limitations`
    attached, and nothing downstream is permitted to gate a decision on it
    alone. `ground_truth` is False and there is no setter.
    """

    value: Optional[float]
    buckets: int
    resolution: str
    assumptions: Tuple[str, ...]
    limitations: Tuple[str, ...]
    ground_truth: bool = field(default=False, init=False)

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "kind": "toxicity_proxy",
                "value": None if self.value is None else round(self.value, 4),
                "buckets": self.buckets, "resolution": self.resolution,
                "assumptions": list(self.assumptions),
                "limitations": list(self.limitations),
                "ground_truth": self.ground_truth}


def vpin(volumes: Sequence[float], returns: Sequence[float], *,
         buckets: int = 50, resolution: str = "daily") -> ToxicityProxy:
    """Bulk-classified order-flow imbalance over volume buckets.

    Returns `value=None` rather than a number when there is not enough data.
    A VPIN computed over four buckets is not a small-sample VPIN; it is a
    different statistic wearing the name.
    """
    require(len(volumes) == len(returns),
            "volume and return series must be the same length")
    limitations = (
        "buy/sell classification is a bulk rule, not observed order flow",
        f"{resolution} resolution is far coarser than the intraday data the "
        "estimator was designed for",
        "the value is not comparable across instruments with different "
        "volume distributions",
    )
    assumptions = (
        "volume is classified by the sign and magnitude of the period return",
        "equal-volume buckets approximate equal information arrival",
    )
    if len(volumes) < buckets:
        return ToxicityProxy(
            value=None, buckets=len(volumes), resolution=resolution,
            assumptions=assumptions,
            limitations=limitations + (
                f"{len(volumes)} periods against {buckets} buckets required; "
                "no value is reported rather than a small-sample one",))
    total = sum(volumes) or 1.0
    sigma = _stdev(returns) or 1e-9
    imbalance = 0.0
    for v, r in zip(volumes, returns):
        # Bulk classification: the share of the bucket treated as buy-
        # initiated is the normal CDF of the standardised return.
        buy_share = 0.5 * (1.0 + math.erf((r / sigma) / math.sqrt(2)))
        imbalance += abs(2.0 * buy_share - 1.0) * v
    return ToxicityProxy(value=imbalance / total, buckets=buckets,
                         resolution=resolution, assumptions=assumptions,
                         limitations=limitations)


def _stdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))

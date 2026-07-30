"""Market evidence — the input a strategic reading structurally cannot supply.

WHY THIS EXISTS
---------------
Learning Velocity, measured as evaluations that can ever be graded, was ZERO
for the whole phase. Every path terminated in WATCH or NO_TRADE, so records
accumulated and nothing ever told the engine whether it was right. Nothing
downstream — resolution, post-mortems, calibration, knowledge extraction —
could be built, because none of it has an input until a prediction exists that
can be scored.

This closes the loop.

WHY A BASELINE AND NOT A STRATEGY
---------------------------------
The honest thing a system with no track record can say about direction is very
little. So this does not pretend: it is a momentum baseline over real price
history, labelled unvalidated, and its job is to make predictions RESOLVABLE
rather than right.

That is a real scientific role. Without a baseline there is nothing for a
future signal to beat, and "our signal is good" is unfalsifiable. With one,
every later idea has to clear a bar that was recorded before anyone knew the
answer. It is also the on-ramp `A-M5` requires: accuracy claims are gated
behind >=30 live-resolved predictions plus a human calibration review, and
there is no way to reach thirty resolutions without first making predictions
that resolve.

WHAT IT MUST NOT BECOME
-----------------------
A baseline mistaken for skill. `MarketEvidence.source` is recorded on every
opportunity so calibration can segment by signal and this one can be held to
its own record. The probability is a stated prior, not a measurement, and it
stays fixed until real resolutions justify moving it — through the promotion
wall, not by editing this file.
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence

from intent_engine.market.opportunity import MarketEvidence

# The signal's identity, versioned. It goes on every record it produces, so a
# later calibration review can ask "how did baseline_momentum.v1 actually do?"
# and get an answer about THIS logic rather than about whatever the file says
# by then.
BASELINE_SOURCE = "baseline_momentum.v1"

# An UNVALIDATED prior, not a measurement. Deliberately barely off a coin flip:
# a momentum rule with no demonstrated edge on this universe has no business
# claiming more, and an inflated number here would poison the first calibration
# curve the engine ever draws. It moves only when resolved outcomes justify it,
# through the promotion wall.
BASELINE_PROBABILITY = 0.55

# Below this, a move is indistinguishable from noise at daily resolution and
# the honest output is no signal at all — which the reasoner renders as WATCH.
MIN_ABS_RETURN = 0.02


def _returns(prices: Sequence[float]) -> List[float]:
    out = []
    for earlier, later in zip(prices, prices[1:]):
        if earlier:
            out.append((later - earlier) / earlier)
    return out


def _volatility(prices: Sequence[float]) -> Optional[float]:
    rets = _returns(prices)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var)


def momentum_evidence(prices: Sequence[float], *, horizon_days: int = 21
                      ) -> MarketEvidence:
    """Direction from realised trailing return; size from realised volatility.

    Returns an EMPTY MarketEvidence when the series is too short or the move
    too small to distinguish from noise. Empty is a real answer here — the
    reasoner turns it into WATCH with `no_market_evidence`, which is the
    correct record for "we looked and the market said nothing".
    """
    series = [float(p) for p in prices or () if p]
    if len(series) < 3:
        return MarketEvidence(source=BASELINE_SOURCE)

    trailing = (series[-1] - series[0]) / series[0] if series[0] else 0.0
    if abs(trailing) < MIN_ABS_RETURN:
        return MarketEvidence(source=BASELINE_SOURCE)

    vol = _volatility(series) or 0.0
    # Expected move over the horizon, from realised daily volatility. Symmetric
    # on purpose: this baseline has no view on skew, and inventing one to make
    # the risk/reward look better would be exactly the flattering assumption
    # the reasoner's HOLD gate exists to catch.
    expected = round(vol * math.sqrt(max(horizon_days, 1)) * 100, 2)
    expected = max(expected, 1.0)

    return MarketEvidence(
        direction="up" if trailing > 0 else "down",
        probability=BASELINE_PROBABILITY,
        horizon_days=horizon_days,
        upside_pct=expected,
        downside_pct=expected,
        catalysts=(),          # a momentum rule knows of no catalyst
        source=BASELINE_SOURCE)


def price_history(price_at: Callable[[str, str], float], symbol: str,
                  days: Sequence[str]) -> List[float]:
    """Prices for a set of dates, skipping any the source cannot answer.

    A missing price is not fatal and not filled in. Interpolating a price the
    market never printed would put a fabricated number into the one part of
    this system that is supposed to be ground truth.
    """
    out: List[float] = []
    for day in days:
        try:
            out.append(float(price_at(symbol, day)))
        except Exception:  # noqa: BLE001 — a gap is data, not an error
            continue
    return out


def baseline_market_evidence(price_at, symbol: str, lookback_days: Sequence[str],
                             *, horizon_days: int = 21) -> MarketEvidence:
    """The wiring the daily sweep uses: fetch, then read."""
    if not symbol:
        return MarketEvidence(source=BASELINE_SOURCE)
    return momentum_evidence(price_history(price_at, symbol, lookback_days),
                             horizon_days=horizon_days)

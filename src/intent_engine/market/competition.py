"""Strategy competition — uncertainty-aware, and reluctant to rank.

THE QUESTION
------------
Not "did this strategy work?" but "which strategy is worth continuing, given
costs and given how little we actually know?"

WHY THE LEADERBOARD REFUSES TO RANK MOST OF THE TIME
-----------------------------------------------------
A ranking implies the order means something. With n_effective below 30, or with
overlapping confidence intervals, the order is noise wearing a number. So
`leaderboard` sorts but marks the result `RANKED: NO` and says why, and a
strategy without comparable evidence is reported as UNMEASURABLE rather than
placed last -- last implies it lost.

The specific failure this avoids: a strategy that fires often accumulates rows
fastest, so on raw count it looks best-evidenced and drifts to the top. Trade
frequency is not evidence, and `no_promotion_on_trade_count` asserts it.

METRICS ARE NET, ALWAYS
-----------------------
Every return here has costs already subtracted upstream in `replay`/`costs`.
There is no gross column, because a gross Sharpe printed beside a net one
invites the reader to split the difference.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from intent_engine.market import strategy as ST
from intent_engine.market.experiments import (
    MIN_EFFECTIVE_FOR_A_CLAIM, EffectiveSample, TestResult,
)

UNMEASURABLE = "UNMEASURABLE"

# Annualisation for a daily-decision strategy. Stated rather than hidden in a
# constant: 252 trading days.
TRADING_DAYS = 252


def _mean(v):
    return sum(v) / len(v) if v else None


@dataclass(frozen=True)
class Performance:
    """One strategy version's record. Every field may be UNMEASURABLE."""
    strategy_key: str
    state: str
    n_raw: int
    n_effective: int
    design_effect: Optional[float]
    win_rate: Optional[float]
    expectancy: Optional[float]
    profit_factor: Optional[float]
    sharpe: Optional[float]
    sortino: Optional[float]
    max_drawdown: Optional[float]
    turnover: Optional[int]
    mean_net_return: Optional[float]
    p_value: Optional[float]
    interval: Optional[tuple]
    measurable: bool
    reason: str = ""

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in
             ("strategy_key", "state", "n_raw", "n_effective", "design_effect",
              "win_rate", "expectancy", "profit_factor", "sharpe", "sortino",
              "max_drawdown", "turnover", "mean_net_return", "p_value",
              "measurable", "reason")}
        d["interval"] = list(self.interval) if self.interval else None
        return d


def evaluate(strategy_key: str, state: str, observations: Sequence[dict],
             sample: EffectiveSample, test: TestResult) -> Performance:
    """Compute the full record, refusing every metric the sample cannot carry."""
    rets = [o["net_return"] for o in observations
            if o.get("net_return") is not None]
    if not rets:
        return Performance(strategy_key, state, 0, 0, None, None, None, None,
                           None, None, None, 0, None, None, None, False,
                           "no resolved observations")

    n_eff = sample.n_effective
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    mean = _mean(rets)
    sd = (math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
          if len(rets) > 1 else 0.0)
    downside = [r for r in rets if r < 0]
    dsd = (math.sqrt(sum(r ** 2 for r in downside) / len(downside))
           if downside else 0.0)

    # Equity curve on equal-notional, sequential ordering by decision date.
    equity, peak, dd = 1.0, 1.0, 0.0
    for o in sorted(observations, key=lambda x: str(x.get("as_of"))):
        if o.get("net_return") is None:
            continue
        equity *= (1 + o["net_return"])
        peak = max(peak, equity)
        dd = min(dd, equity / peak - 1)

    # Sharpe/Sortino are only meaningful with enough INDEPENDENT observations.
    measurable = n_eff >= MIN_EFFECTIVE_FOR_A_CLAIM
    sharpe = sortino = interval = None
    if measurable and sd:
        sharpe = round(mean / sd * math.sqrt(TRADING_DAYS), 3)
        if dsd:
            sortino = round(mean / dsd * math.sqrt(TRADING_DAYS), 3)
        half = 1.96 * sd / math.sqrt(n_eff)
        interval = (round(mean - half, 6), round(mean + half, 6))

    return Performance(
        strategy_key=strategy_key, state=state, n_raw=sample.n_raw,
        n_effective=n_eff, design_effect=sample.design_effect,
        win_rate=round(len(wins) / len(rets), 4),
        expectancy=round(mean, 6),
        profit_factor=(round(gross_win / gross_loss, 3) if gross_loss else None),
        sharpe=sharpe, sortino=sortino, max_drawdown=round(dd, 4),
        turnover=len({(o.get("security"), o.get("as_of"))
                      for o in observations}),
        mean_net_return=round(mean, 6), p_value=test.p_value,
        interval=interval, measurable=measurable,
        reason=("" if measurable else
                f"n_effective {n_eff} < {MIN_EFFECTIVE_FOR_A_CLAIM}"))


def leaderboard(performances: Sequence[Performance],
                fdr: Optional[dict] = None) -> dict:
    """Ordered, but explicit about whether the order means anything."""
    measurable = [p for p in performances if p.measurable]
    unmeasurable = [p for p in performances if not p.measurable]
    ordered = sorted(measurable,
                     key=lambda p: (p.mean_net_return or -9e9), reverse=True)

    rankable = False
    reason = "no strategy has enough effective evidence to rank"
    if len(ordered) >= 2:
        top, second = ordered[0], ordered[1]
        if top.interval and second.interval:
            # Overlapping intervals mean the order is not distinguishable.
            if top.interval[0] > second.interval[1]:
                rankable = True
                reason = "top strategy's interval clears the runner-up's"
            else:
                reason = ("confidence intervals overlap; the ordering is not "
                          "distinguishable from noise")
    elif len(ordered) == 1:
        reason = "only one measurable strategy; nothing to rank it against"

    survivors = (fdr or {}).get("discoveries", [])
    return {
        "ranked": rankable,
        "reason": reason,
        "rows": [p.as_dict() for p in ordered + unmeasurable],
        "measurable": len(measurable),
        "unmeasurable": len(unmeasurable),
        "fdr": fdr,
        "surviving_fdr": survivors,
        "note": ("no strategy survives false-discovery control; none is "
                 "eligible for challenger status"
                 if fdr and not survivors else None),
    }


def no_promotion_on_trade_count(performances: Sequence[Performance]) -> dict:
    """The anti-Goodhart check for this leaderboard.

    A strategy that fires often accumulates rows fastest and therefore looks
    best-evidenced. Frequency is not evidence. This reports the correlation so
    the failure is visible rather than assumed absent.
    """
    pairs = [(p.n_raw, p.mean_net_return) for p in performances
             if p.mean_net_return is not None]
    if len(pairs) < 3:
        return {"checked": False,
                "reason": "fewer than 3 strategies; correlation meaningless"}
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = math.sqrt(sum((x - mx) ** 2 for x in xs)
                    * sum((y - my) ** 2 for y in ys))
    return {"checked": True,
            "corr_tradecount_vs_return": round(num / den, 4) if den else None,
            "rule": "trade count never promotes a strategy; only net edge on "
                    "effective observations does"}


def retirement_check(performance: Performance,
                     rules: Sequence[str]) -> Optional[dict]:
    """Do the preregistered retirement conditions fire?

    Only fires on MEASURABLE evidence: retiring a strategy for having no edge
    when the sample cannot detect one would be discarding a hypothesis for a
    fact about the sample size.
    """
    if not performance.measurable:
        return None
    triggered = []
    if performance.expectancy is not None and performance.expectancy <= 0:
        triggered.append("negative or zero net expectancy after costs")
    if (performance.p_value is not None and performance.p_value > 0.10
            and performance.n_effective >= MIN_EFFECTIVE_FOR_A_CLAIM):
        triggered.append(
            f"no edge distinguishable from zero at n_eff="
            f"{performance.n_effective} (p={performance.p_value})")
    if not triggered:
        return None
    return {"strategy_key": performance.strategy_key,
            "state": ST.UNDER_REVIEW, "triggered": triggered,
            "preregistered_rules": list(rules),
            "reason": "; ".join(triggered)}

"""The decision funnel — where throughput is actually lost.

WHY THIS EXISTS
---------------
Day 12 removed the `no_outside_source` bottleneck and I immediately named
strategic-reading yield the new #1. That was wrong on method: it ranked a
bottleneck from a single day, and a single day cannot distinguish three
different things that produce the same number.

  1. **Reading yield** — the company's public material does not support a view.
  2. **Signal inactivity** — the signal declines to fire on this company today.
  3. **Market conditions** — there is genuinely nothing to trade.

Only (1) is a deficiency. (2) and (3) are the system working, and a signal that
fires every day is a signal that has stopped discriminating. Ranking them
together would make "trade more often" look like an improvement, which is the
precise failure `METRIC_INTEGRITY.md` exists to prevent.

So the funnel is recorded per day and **ranked only across days**. A stage is a
bottleneck when it dominates the conversion loss repeatedly — not when it
happens to dominate on the day someone looked.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# The FILTER CHAIN. Each stage is a strict subset of the one above, so the
# conversion between adjacent stages is meaningful on its own.
CHAIN = (
    "evaluated",
    "tradable",
    "independent_evidence",
    "strategic_view",
    "signal_evaluated",
    "signal_fired",
    "positions_opened",
    "positions_resolved",
    "positions_correct",
)

# TERMINAL classifications. These PARTITION the evaluated set -- they branch,
# they do not filter -- so a conversion rate between them is meaningless.
# Treating them as chain links produced "no_trade: 833%" (25 measured against
# sell=0) and made `positions_opened` look like a 25 -> 0 collapse. Both were
# artefacts of forcing a branch into a sequence.
TERMINALS = ("buy", "sell", "watch", "no_trade")

STAGES = CHAIN + TERMINALS


@dataclass(frozen=True)
class Funnel:
    as_of: str
    counts: Dict[str, int] = field(default_factory=dict)

    def rate(self, stage: str) -> Optional[float]:
        """Conversion from the PREVIOUS CHAIN stage, not from the top.

        Measuring everything against the top hides where the loss actually is:
        a stage converting 100% looks bad if the stage above it lost 90%.

        Terminals return their share of the evaluated set instead, because
        they branch rather than filter.
        """
        if stage in TERMINALS:
            total = self.counts.get("evaluated", 0)
            return (self.counts.get(stage, 0) / total) if total else None
        index = CHAIN.index(stage)
        if index == 0:
            return None
        prior = self.counts.get(CHAIN[index - 1], 0)
        return (self.counts.get(stage, 0) / prior) if prior else None

    @property
    def largest_loss(self) -> Optional[dict]:
        """The single stage transition that loses the most throughput.

        Reported as a fact about today, never as a ranking. Terminal
        classifications (buy/sell/watch/no_trade) are excluded: they partition
        the decisions rather than filtering them, so a "loss" there is not a
        loss.
        """
        worst = None
        for stage in CHAIN[1:]:
            prior = self.counts.get(CHAIN[CHAIN.index(stage) - 1], 0)
            if not prior:
                continue
            lost = prior - self.counts.get(stage, 0)
            if lost <= 0:
                continue
            if worst is None or lost > worst["lost"]:
                worst = {"stage": stage, "lost": lost, "from": prior,
                         "rate": round(self.counts.get(stage, 0) / prior, 3)}
        return worst

    def as_dict(self) -> dict:
        return {"as_of": self.as_of, "counts": dict(self.counts),
                "rates": {s: self.rate(s) for s in STAGES if s != "evaluated"},
                "largest_loss": self.largest_loss}

    def render(self) -> str:
        lines = [f"{'stage':<24}{'count':>7}{'conv':>9}"]
        for stage in CHAIN:
            rate = self.rate(stage)
            shown = "—" if rate is None else f"{rate:.0%}"
            lines.append(f"{stage:<24}{self.counts.get(stage, 0):>7}{shown:>9}")
        lines.append(f"{'--- terminals ---':<24}")
        for stage in TERMINALS:
            rate = self.rate(stage)
            shown = "—" if rate is None else f"{rate:.0%}"
            lines.append(f"{stage:<24}{self.counts.get(stage, 0):>7}{shown:>9}")
        loss = self.largest_loss
        if loss:
            lines.append(f"\nlargest conversion loss: {loss['stage']} "
                         f"({loss['from']} -> {loss['from']-loss['lost']}, "
                         f"{loss['rate']:.0%})")
        return "\n".join(lines)


def from_rows(rows: Sequence[dict], *, as_of: str,
              signal_fired: int = 0, positions: int = 0,
              resolved: int = 0, correct: int = 0) -> Funnel:
    """Build a funnel from a live cycle's per-company rows."""
    counts = {s: 0 for s in STAGES}
    counts["evaluated"] = len(rows)
    for row in rows:
        gate = row.get("gate") or ""
        # EACH CHAIN STAGE IS A SUBSET OF THE ONE ABOVE, enforced rather than
        # assumed. Counting independent evidence across ALL companies gave
        # 28 of 27 tradable -- 104% -- because the private company has
        # independent evidence and can never be traded. A funnel stage that
        # can exceed its predecessor is not a funnel.
        tradable = gate != "not_tradable"
        if not tradable:
            continue
        counts["tradable"] += 1
        if not row.get("indep"):
            continue
        counts["independent_evidence"] += 1
        if not row.get("thesis"):
            continue
        counts["strategic_view"] += 1
        if gate == "no_market_evidence":
            counts["signal_evaluated"] += 1

    # Terminals are counted over EVERY evaluated company, in their own pass.
    # They partition the evaluated set, so nesting them inside the chain's
    # early-exits made them count only companies that survived every filter --
    # which reported no_trade = 0 on a day with 25 NO_TRADE decisions.
    for row in rows:
        cls = (row.get("classification") or "").lower()
        if cls in TERMINALS:
            counts[cls] += 1
    counts["signal_fired"] = signal_fired
    counts["positions_opened"] = positions
    counts["positions_resolved"] = resolved
    counts["positions_correct"] = correct
    return Funnel(as_of=as_of, counts=counts)


def append_history(funnel: Funnel, path="reports/funnel_history.json") -> List[dict]:
    """Append one day. History is the point: a stage is a bottleneck when it
    dominates repeatedly, not when it dominates once."""
    file = pathlib.Path(path)
    history = json.loads(file.read_text()) if file.exists() else []
    history = [h for h in history if h.get("as_of") != funnel.as_of]
    history.append(funnel.as_dict())
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(history, indent=1))
    return history


def dominant_bottleneck(history: Sequence[dict], *, min_days: int = 3
                        ) -> Optional[dict]:
    """The stage that dominates conversion loss ACROSS DAYS.

    Returns None below `min_days`. One day of data cannot distinguish a
    deficiency from a market that simply offered nothing, and naming a
    bottleneck from it is how a system talks itself into fixing the weather.
    """
    if len(history) < min_days:
        return {"verdict": "insufficient history",
                "days": len(history), "needed": min_days}
    tally: Dict[str, int] = {}
    for day in history:
        loss = day.get("largest_loss")
        if loss:
            tally[loss["stage"]] = tally.get(loss["stage"], 0) + 1
    if not tally:
        return None
    stage, days = max(tally.items(), key=lambda kv: kv[1])
    return {"stage": stage, "days_dominant": days, "of_days": len(history),
            "verdict": ("dominant" if days > len(history) / 2
                        else "no stage dominates")}

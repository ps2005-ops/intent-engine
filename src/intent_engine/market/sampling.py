"""Effective sample size — how many INDEPENDENT things a result rests on.

WHY THIS EXISTS
---------------
Day 2 produced an apparent discovery: a filing-drift signal at 0.359 over
n=64, comfortably outside a naive 2σ band. It was not real. Those 64
observations fell in 15 distinct months, and every filing inside a month shares
one market window — when the market fell that month, every "up" call lost
together. Treating them as 64 independent draws overstated precision by
roughly √(64/15) ≈ 2×, which was exactly the width that manufactured the
result.

The correction was done by hand that day. It is done here, always, because a
result that has to be manually second-guessed will eventually not be.

THE UNIT IS NOT THE ROW
-----------------------
Three different counts, deliberately kept apart:

  * **observations** — rows. Always the largest and always the least meaningful.
  * **independent information events** — distinct (company, event) pairs. Two
    signals derived from one 8-K are one event, not two.
  * **independent market windows** — disjoint spans of calendar time. Two
    events in different companies whose holding periods overlap are NOT
    independent: they share whatever the market did that fortnight.

Statistical confidence is computed on the smallest of these, because that is
what the result actually rests on.

WHY WINDOWS AND NOT MONTHS
--------------------------
Day 2 clustered by calendar month, which was a convenient proxy and wrong at
the edges: two filings 3 days apart either side of a month boundary are highly
correlated and counted as independent, while two 25 days apart inside one month
are nearly independent and counted as one. Merging overlapping [entry, exit]
windows is the thing the proxy was approximating, so it is used directly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

# Confidence in a METRIC, matching decision_quality's vocabulary.
HIGH, MEDIUM, LOW, UNMEASURABLE = "high", "medium", "low", "unmeasurable"
# `A-M5` gates accuracy claims at 30. Applied to n_eff, not to row count --
# thirty rows sharing three market windows is three observations wearing a
# larger number.
_MEDIUM_N, _HIGH_N = 10, 30


def merge_windows(windows: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Disjoint spans, from possibly-overlapping ones.

    Touching counts as overlapping: a position exiting the day another enters
    still shares the same market conditions at the join.
    """
    spans = sorted((s, e) for s, e in windows if s and e and s <= e)
    if not spans:
        return []
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


@dataclass(frozen=True)
class SampleSize:
    observations: int
    events: int
    windows: int

    @property
    def n_eff(self) -> int:
        """The smallest of the three. A result cannot be better supported than
        its most correlated dimension allows."""
        return min(self.observations, self.events, self.windows)

    @property
    def design_effect(self) -> Optional[float]:
        """How much the naive count overstates precision. 1.0 means the rows
        really were independent; 4.0 means the naive error bar is half what it
        should be."""
        if not self.n_eff:
            return None
        return round(self.observations / self.n_eff, 2)

    @property
    def confidence(self) -> str:
        n = self.n_eff
        if n <= 0:
            return UNMEASURABLE
        return HIGH if n >= _HIGH_N else MEDIUM if n >= _MEDIUM_N else LOW

    def as_dict(self) -> dict:
        return {"observations": self.observations, "events": self.events,
                "windows": self.windows, "n_eff": self.n_eff,
                "design_effect": self.design_effect,
                "confidence": self.confidence}


def measure(observations: Sequence[dict]) -> SampleSize:
    """Count all three units for a set of graded observations.

    Each row needs `entry_day` and `exit_day`; an `event_key` is used when
    present so several signals derived from one disclosure collapse to one
    event rather than counting separately.
    """
    rows = [r for r in observations or () if r.get("entry_day")
            and r.get("exit_day")]
    events = {r.get("event_key")
              or (r.get("company_id"), r.get("entry_day")) for r in rows}
    windows = merge_windows((r["entry_day"], r["exit_day"]) for r in rows)
    return SampleSize(observations=len(rows), events=len(events),
                      windows=len(windows))


def band(accuracy: Optional[float], size: SampleSize,
         sigmas: float = 2.0) -> dict:
    """The honest error bar, and the verdict against a 0.500 baseline.

    Computed on `n_eff`. The naive band is returned alongside it, not to be
    used but so the gap between them is visible — on Day 2 that gap was the
    entire finding.
    """
    n_eff, n_raw = size.n_eff, size.observations
    if accuracy is None or not n_eff:
        return {"accuracy": accuracy, "verdict": "unmeasurable",
                **size.as_dict()}
    se_eff = math.sqrt(0.25 / n_eff)
    se_raw = math.sqrt(0.25 / n_raw) if n_raw else None
    lo, hi = 0.5 - sigmas * se_eff, 0.5 + sigmas * se_eff
    if n_eff < _HIGH_N:
        verdict = f"unmeasurable (n_eff={n_eff} < 30, A-M5)"
    elif lo <= accuracy <= hi:
        verdict = "indistinguishable from 0.500"
    else:
        verdict = "DISTINGUISHABLE from 0.500"
    return {"accuracy": accuracy, "band": (round(lo, 3), round(hi, 3)),
            "naive_band": ((round(0.5 - sigmas * se_raw, 3),
                            round(0.5 + sigmas * se_raw, 3))
                           if se_raw else None),
            "verdict": verdict, **size.as_dict()}

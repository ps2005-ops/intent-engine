"""Learning throughput — the rate of VALID learning, honestly named.

THE NAMING IS THE FIRST HONEST DECISION
---------------------------------------
This is called LEARNING THROUGHPUT and not "information gain", because it is
not a measure of entropy reduction and pretending otherwise would be exactly
the kind of borrowed rigour this project keeps refusing. It is a composite of
things that are individually countable and individually defensible.

WHAT COUNTS
-----------
    resolved_effective      new INDEPENDENT resolved outcomes (never n_raw)
    hypotheses_resolved     a strategy moved to a terminal state on evidence
    calibration_eligible    resolutions that can enter a calibration curve
    assets_strengthened     research assets confirmed by new evidence
    assets_weakened         research assets undermined  -- SUBTRACTS
    interval_narrowed       measured reduction in a confidence-interval width

WHY IT SUBTRACTS
----------------
Same rule as Research Velocity: a cycle that undermines a held conclusion
leaves the project knowing less than it thought. A throughput metric that only
went up would reward running more experiments regardless of what they showed.

THE ANTI-GOODHART TEST, APPLIED TO THIS METRIC
----------------------------------------------
*Could it be moved by editing a constant?* Partly -- lowering a signal threshold
raises `resolved_effective`. That is why the denominator of every claim is
`n_effective` (which does NOT rise when you fire more often on the same
securities and dates), and why throughput is reported as a HEALTH signal, never
used to rank strategies. Ranking is `competition.leaderboard`, which is driven
by net edge and refuses to rank on volume.

ZERO IS A LEGITIMATE VALUE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass(frozen=True)
class LearningThroughput:
    """One cycle's valid learning. Every field is a count of something real."""
    resolved_raw: int = 0
    resolved_effective: int = 0
    hypotheses_resolved: int = 0
    calibration_eligible: int = 0
    assets_strengthened: int = 0
    assets_weakened: int = 0
    interval_narrowed: float = 0.0
    compute_seconds: float = 0.0

    @property
    def score(self) -> int:
        """LEARNING THROUGHPUT =
             resolved_effective + hypotheses_resolved + calibration_eligible
             + assets_strengthened - assets_weakened

        `resolved_raw` is deliberately absent from the score. It is reported
        beside it so the gap between raw and effective is visible, but a metric
        that counted rows would rise every time a threshold was loosened.
        """
        return (self.resolved_effective + self.hypotheses_resolved
                + self.calibration_eligible + self.assets_strengthened
                - self.assets_weakened)

    @property
    def per_compute_hour(self) -> Optional[float]:
        if not self.compute_seconds:
            return None
        return round(self.score / (self.compute_seconds / 3600), 2)

    @property
    def design_effect(self) -> Optional[float]:
        if not self.resolved_effective:
            return None
        return round(self.resolved_raw / self.resolved_effective, 2)

    def as_dict(self) -> dict:
        return {"resolved_raw": self.resolved_raw,
                "resolved_effective": self.resolved_effective,
                "design_effect": self.design_effect,
                "hypotheses_resolved": self.hypotheses_resolved,
                "calibration_eligible": self.calibration_eligible,
                "assets_strengthened": self.assets_strengthened,
                "assets_weakened": self.assets_weakened,
                "interval_narrowed": self.interval_narrowed,
                "compute_seconds": self.compute_seconds,
                "learning_throughput": self.score,
                "throughput_per_compute_hour": self.per_compute_hour}

    def render(self) -> str:
        lines = []
        for k, v in self.as_dict().items():
            label = k.replace("_", " ")
            lines.append(f"  {label:<30}{'—' if v is None else v}")
        if self.score == 0:
            lines.append("\n  NO NEW KNOWLEDGE — a legitimate result.")
        return "\n".join(lines)


@dataclass(frozen=True)
class LiveLearningRate:
    """The live path, kept strictly separate from replay.

    Separate because they are not comparable: replay resolves ten years in
    minutes, live resolves one position in 21 days. Averaging them would make
    the live path look productive because replay is, which is precisely the
    conflation this cycle exists to avoid.
    """
    securities_evaluated: int = 0
    strategic_views: int = 0
    signal_opportunities: int = 0
    signal_fires: int = 0
    positions_opened: int = 0
    positions_resolved: int = 0
    median_days_to_resolution: Optional[float] = None

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in
             ("securities_evaluated", "strategic_views", "signal_opportunities",
              "signal_fires", "positions_opened", "positions_resolved",
              "median_days_to_resolution")}
        d["note"] = ("live and replay learning are reported separately and "
                     "never averaged: replay resolves ten years in minutes, "
                     "live resolves one position in 21 days")
        return d


def limiting_factor(live: LiveLearningRate, throughput: LearningThroughput,
                    ) -> dict:
    """What is actually capping the learning rate right now?

    Reported every cycle so the next engineering decision is measured rather
    than guessed -- the project's engineering-prediction accuracy is 1-in-7,
    which is the whole reason this is computed instead of asserted.
    """
    if live.positions_opened == 0 and throughput.resolved_effective == 0:
        return {"factor": "no resolvable experiments",
                "detail": "neither the live path nor replay produced a "
                          "resolved observation this cycle"}
    if throughput.resolved_effective and live.positions_opened == 0:
        return {"factor": "live path produces no positions",
                "detail": (f"replay resolved {throughput.resolved_effective} "
                           f"effective observations; the live path opened "
                           f"none. Live learning is capped by the strategic-"
                           f"reading gate, not by universe size.")}
    if throughput.design_effect and throughput.design_effect > 10:
        return {"factor": "observation dependence",
                "detail": (f"design effect {throughput.design_effect}x — most "
                           f"rows are re-measurements, not new information")}
    return {"factor": "unknown", "detail": "no single factor dominates"}

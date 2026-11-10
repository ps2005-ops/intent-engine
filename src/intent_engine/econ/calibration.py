"""Forward calibration, and the refusal to report it before it exists.

THE ONE RULE
------------
Until there are enough RESOLVED FORWARD predictions, this reports
PRE_CALIBRATION and a count. It does not report an accuracy percentage, a
win rate, a Brier score, a hit rate, or anything a reader could quote as
performance. Not a rounded one, not a provisional one, not one in small type.

WHY A MINIMUM SAMPLE, AND WHY THIS ONE
--------------------------------------
`MIN_RESOLVED` is 30. It is not a power calculation, because the effect size
being estimated is not known in advance; it is the point below which a
directional accuracy figure's 95% interval is wider than the entire range of
interesting values. At n=10, 7 correct gives an interval of roughly 35%-93%:
the number 70% would be printed and would mean nothing.

The threshold is stated as a constant so it can be argued with, and
`status()` names it in its own output so a reader never has to find it.

BRIER IS THE PRIMARY SCORE, AND ACCURACY IS NOT
-----------------------------------------------
Directional accuracy rewards a system that only predicts easy things. Brier
scores the PROBABILITY, so a confident wrong answer costs more than an
uncertain one -- which is the behaviour this engine needs, because its whole
claim is that it knows how sure it is. Accuracy is reported alongside, never
alone.

A BASELINE IS PART OF THE SCORE
--------------------------------
A Brier score with no baseline is unreadable. Every report carries the score
of the always-0.5 forecaster and of the base-rate forecaster, so "0.21" can
be recognised as better or worse than saying nothing.

VOID IS EXCLUDED FROM THE DENOMINATOR
-------------------------------------
A prediction whose data source went dark did not fail. It is not scored and
it is COUNTED SEPARATELY, so a reader can see how much of the ledger could
not be evaluated -- which is itself a measurement of the engine's data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .belief import (
    CORRECT, Expectation, INCORRECT, NEAR_MISS, OPEN, RESOLVED, VOID,
)
from .vocabulary import require

CONTRACT = "econ_calibration.v1"

PRE_CALIBRATION = "PRE_CALIBRATION"
CALIBRATED = "CALIBRATED"

#: Resolved forward predictions required before any score may be reported.
#: See the module docstring for why 30 and not 10.
MIN_RESOLVED = 30

#: Bucket edges for the calibration curve.
BUCKETS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))


@dataclass(frozen=True)
class Bucket:
    low: float
    high: float
    n: int
    predicted_mean: Optional[float]
    observed_rate: Optional[float]

    @property
    def gap(self) -> Optional[float]:
        if self.predicted_mean is None or self.observed_rate is None:
            return None
        return round(self.observed_rate - self.predicted_mean, 4)

    def as_dict(self) -> dict:
        return {"range": [self.low, self.high], "n": self.n,
                "predicted_mean": (None if self.predicted_mean is None
                                   else round(self.predicted_mean, 4)),
                "observed_rate": (None if self.observed_rate is None
                                  else round(self.observed_rate, 4)),
                "gap": self.gap}


@dataclass(frozen=True)
class CalibrationReport:
    """What may be said about forward accuracy, and what may not."""

    status: str
    resolved: int
    voided: int
    open: int
    minimum_required: int
    reason: str
    brier: Optional[float] = None
    brier_always_half: Optional[float] = None
    brier_base_rate: Optional[float] = None
    directional_accuracy: Optional[float] = None
    near_miss_rate: Optional[float] = None
    buckets: Tuple[Bucket, ...] = ()

    @property
    def may_report_accuracy(self) -> bool:
        return self.status == CALIBRATED

    def headline(self) -> str:
        """The sentence a surface prints. Never a percentage before CALIBRATED."""
        if not self.may_report_accuracy:
            return (f"PRE-CALIBRATION — {self.resolved} resolved forward "
                    f"prediction(s) of the {self.minimum_required} required "
                    "before any accuracy figure is meaningful. No accuracy is "
                    "reported.")
        return (f"Brier {self.brier:.3f} against {self.brier_always_half:.3f} "
                f"for an always-uncertain forecaster, on {self.resolved} "
                "resolved forward predictions.")

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "status": self.status,
                "resolved_forward": self.resolved, "voided": self.voided,
                "open": self.open,
                "minimum_required": self.minimum_required,
                "may_report_accuracy": self.may_report_accuracy,
                "reason": self.reason, "headline": self.headline(),
                "brier": self.brier,
                "brier_always_half": self.brier_always_half,
                "brier_base_rate": self.brier_base_rate,
                "directional_accuracy": self.directional_accuracy,
                "near_miss_rate": self.near_miss_rate,
                "calibration_curve": [b.as_dict() for b in self.buckets]}


def _outcome_value(e: Expectation) -> Optional[float]:
    """1.0 if the prediction came true, 0.0 if not, None if unscoreable.

    A NEAR_MISS counts as 0.0 for the Brier score and is reported separately.
    Scoring it as a partial success would let a tolerance chosen after the
    fact improve the score.
    """
    if e.outcome == CORRECT:
        return 1.0
    if e.outcome in (INCORRECT, NEAR_MISS):
        return 0.0
    return None


def report(expectations: Sequence[Expectation], *,
           minimum: int = MIN_RESOLVED) -> CalibrationReport:
    """Score a ledger, or refuse to."""
    resolved = [e for e in expectations if e.outcome in RESOLVED]
    voided = sum(1 for e in expectations if e.outcome == VOID)
    still_open = sum(1 for e in expectations if e.outcome == OPEN)

    if len(resolved) < minimum:
        return CalibrationReport(
            status=PRE_CALIBRATION, resolved=len(resolved), voided=voided,
            open=still_open, minimum_required=minimum,
            reason=(f"{len(resolved)} resolved forward prediction(s); "
                    f"{minimum} are required. Below that, a directional "
                    "accuracy figure's interval is wider than the range of "
                    "values anyone would act on, so the number would be "
                    "quoted and would mean nothing."))

    outcomes = [(_outcome_value(e), e.confidence) for e in resolved]
    scored = [(o, c) for o, c in outcomes if o is not None]
    n = len(scored)
    brier = sum((c - o) ** 2 for o, c in scored) / n
    base_rate = sum(o for o, _ in scored) / n
    brier_half = sum((0.5 - o) ** 2 for o, _ in scored) / n
    brier_base = sum((base_rate - o) ** 2 for o, _ in scored) / n
    accuracy = sum(1 for o, _ in scored if o == 1.0) / n
    near_miss = sum(1 for e in resolved if e.outcome == NEAR_MISS) / len(resolved)

    buckets: List[Bucket] = []
    for low, high in BUCKETS:
        members = [(o, c) for o, c in scored
                   if low <= c < high or (high == 1.0 and c == 1.0)]
        if members:
            buckets.append(Bucket(
                low=low, high=high, n=len(members),
                predicted_mean=sum(c for _, c in members) / len(members),
                observed_rate=sum(o for o, _ in members) / len(members)))
        else:
            buckets.append(Bucket(low=low, high=high, n=0,
                                  predicted_mean=None, observed_rate=None))

    return CalibrationReport(
        status=CALIBRATED, resolved=len(resolved), voided=voided,
        open=still_open, minimum_required=minimum,
        reason=f"{len(resolved)} resolved forward predictions",
        brier=round(brier, 4), brier_always_half=round(brier_half, 4),
        brier_base_rate=round(brier_base, 4),
        directional_accuracy=round(accuracy, 4),
        near_miss_rate=round(near_miss, 4), buckets=tuple(buckets))


def status(expectations: Sequence[Expectation], *,
           minimum: int = MIN_RESOLVED) -> str:
    return report(expectations, minimum=minimum).status


def assert_no_unsupported_claim(text: str, rep: CalibrationReport) -> None:
    """Refuse prose that quotes performance the sample cannot support.

    Called by any surface that renders free text next to the engine's record.
    The failure it prevents is not deliberate: it is a template that says
    "our accuracy" and reads fine until somebody asks what n was.
    """
    if rep.may_report_accuracy:
        return
    banned = ("accuracy", "win rate", "hit rate", "sharpe", "alpha",
              "outperform", "beat the market", "% correct", "brier")
    #: A banned term is permitted when the SAME SENTENCE scopes it to the
    #: historical record. That is the distinction the wall is actually for:
    #: "historical out-of-sample Brier was 0.24" is a fact about a backtest,
    #: and "our accuracy is 78%" is a claim about the future that zero
    #: resolved predictions cannot support.
    #:
    #: The rule was previously a document-wide substring search, which
    #: refused an entire research report for containing the word "Brier"
    #: anywhere in it -- and a wall that cannot be satisfied by a truthful
    #: sentence gets removed rather than obeyed. Scoping it to the sentence
    #: makes it MORE precise, not weaker: an unqualified claim still raises
    #: even when a qualified one appears elsewhere in the same document.
    qualifiers = ("historical", "out-of-sample", "out of sample", "backtest",
                  "in this sample", "in-sample", "pre_calibration",
                  "pre-calibration")
    import re as _re
    found = []
    for sentence in _re.split(r"(?<=[.!?])\s+|\n", text):
        low = sentence.lower()
        if any(q in low for q in qualifiers):
            continue
        found.extend(f"{b} :: {sentence.strip()[:70]}"
                     for b in banned if b in low)
    if found:
        raise ValueError(
            f"{len(found)} unqualified performance claim(s) while "
            f"calibration status is {rep.status} on {rep.resolved} resolved "
            f"forward prediction(s):\n  " + "\n  ".join(found[:3])
            + f"\n{rep.headline()}\nA sentence may quote a historical "
            "figure when it says so in that sentence.")

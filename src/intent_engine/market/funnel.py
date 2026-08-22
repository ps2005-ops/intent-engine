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
    # Day 17. A qualifying opportunity was OBSERVABLE at decision time --
    # inserted above `signal_fired` because "the signal was silent" and "there
    # was nothing to be loud about" are different facts, and without this stage
    # the funnel cannot tell them apart. Point-in-time by construction; see
    # `signal_opportunity.observable_opportunity`.
    "signal_opportunity",
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

# OFF-CHAIN DIAGNOSTICS. Neither filters nor partitions -- an anomaly counter.
# `false_fire` is the signal firing WITHOUT a qualifying opportunity, which is
# not a step toward a position and must never be netted into one. It is carried
# beside the funnel so it stays countable and visible at zero.
DIAGNOSTICS = ("false_fire",)

STAGES = CHAIN + TERMINALS + DIAGNOSTICS


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
        if stage in DIAGNOSTICS:
            # Measured against the stage it is an anomaly OF, not against the
            # top: a false fire is a property of signal evaluation.
            total = self.counts.get("signal_evaluated", 0)
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
        lines.append(f"{'--- diagnostics ---':<24}")
        for stage in DIAGNOSTICS:
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
              signal_fired: int = 0, signal_opportunity: int = 0,
              positions: int = 0,
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
    # SUBSET DISCIPLINE. These stages are computed outside the per-company
    # rows, so the invariant is ENFORCED here rather than trusted -- a caller
    # that miscounts must not be able to make a stage larger than the one above
    # it. That defect produced `independent_evidence: 104%` once already and is
    # not getting in through a second door.
    #
    # `signal_fired` counts CORRECT FIRES: fired WITH a qualifying opportunity.
    # A fire without one is not progress down this funnel -- it is an anomaly,
    # and it gets its own named line (`false_fire`) instead of being buried
    # inside a conversion rate. Historically this changes nothing (the signal
    # has fired zero times, so correct fires and total fires are both zero),
    # and it keeps the chain a genuine chain.
    counts["signal_opportunity"] = min(signal_opportunity,
                                       counts["signal_evaluated"])
    counts["signal_fired"] = min(signal_fired, counts["signal_opportunity"])
    counts["false_fire"] = max(signal_fired - counts["signal_fired"], 0)
    counts["positions_opened"] = min(positions, counts["signal_fired"])
    counts["positions_resolved"] = min(resolved, counts["positions_opened"])
    counts["positions_correct"] = min(correct, counts["positions_resolved"])
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


# ---------------------------------------------------------------------------
# FUNNEL STABILITY
#
# Day 12 named a bottleneck from one cycle. Day 13 replaced that with a
# three-day minimum, which is better and still wrong: 3%, 8%, 4% over three
# days tells you almost nothing. Calendar time is not evidence.
#
# The rule is now about CONFIDENCE. A stage may only be promoted to #1 when
# there is enough history AND its conversion rate is statistically stable.
# Otherwise it is a CANDIDATE, and saying so is the honest output.
#
# The default output of this system is uncertainty. A conclusion has to earn
# its way out through repeated, stable measurement.
# ---------------------------------------------------------------------------

STABLE, UNSTABLE, INSUFFICIENT = "STABLE", "UNSTABLE", "INSUFFICIENT HISTORY"

# Below this many observations, no dispersion estimate is worth reading.
MIN_OBSERVATIONS = 5
# Coefficient of variation above which a stage is too noisy to rank on. A
# stage swinging ±40% of its own mean is measuring conditions, not capability.
MAX_STABLE_CV = 0.40


# ---------------------------------------------------------------------------
# INTERPRETATION — stability is not desirability.
#
# Day 16 fixed the inverse defect: zero dispersion was being reported UNSTABLE.
# The fix was right and it created the opposite hazard, which is subtler. Once
# `signal_fired` at a flat 0.00 reports STABLE, a reader skimming a column of
# green STABLE labels sees a healthy funnel — and one of those rows is saying
# the engine has never once acted.
#
# A coefficient of variation answers "is this number reliable?". It cannot
# answer "is this number good?", and it must not be read as though it did. So
# stability and interpretation are two columns, always.
# ---------------------------------------------------------------------------
STABLE_HEALTHY = "STABLE AT A HEALTHY VALUE"
STABLE_AT_ZERO = "STABLE AT ZERO"
STABLE_DEGRADED = "STABLE AT A DEGRADED VALUE"
NOT_INTERPRETABLE = "STABLE BUT NOT YET INTERPRETABLE"

# A chain stage converting below this, stably, is losing most of what reaches
# it. Not a target and never optimised against — it decides a LABEL, and the
# anti-Goodhart test applies: moving this constant changes what the report
# calls the number, and changes nothing about the engine.
DEGRADED_BELOW = 0.25


def interpret(stage: str, status: str, mean: Optional[float]) -> Optional[str]:
    """What a stable rate MEANS. Returns None when there is no stability claim
    to interpret — an unstable or under-observed stage has no interpretation,
    and inventing one would be the false precision this avoids."""
    if status != STABLE or mean is None:
        return None
    if stage in TERMINALS or stage in DIAGNOSTICS:
        # A terminal share has no better/worse direction: NO_TRADE at 89% is
        # not "healthy" or "degraded", it is the shape of the decision mix.
        return NOT_INTERPRETABLE
    if mean == 0:
        return STABLE_AT_ZERO
    return STABLE_DEGRADED if mean < DEGRADED_BELOW else STABLE_HEALTHY


@dataclass(frozen=True)
class StageStability:
    stage: str
    observations: int
    today: Optional[float]
    mean: Optional[float]
    median: Optional[float]
    stdev: Optional[float]
    cv: Optional[float]
    trend: str
    interval: Optional[tuple]
    status: str

    @property
    def interpretation(self) -> Optional[str]:
        return interpret(self.stage, self.status, self.mean)

    def as_dict(self) -> dict:
        return {"stage": self.stage, "observations": self.observations,
                "today": self.today, "mean": self.mean, "median": self.median,
                "stdev": self.stdev, "cv": self.cv, "trend": self.trend,
                "interval": list(self.interval) if self.interval else None,
                "status": self.status,
                "interpretation": self.interpretation}


def _trend(values: Sequence[float]) -> str:
    """Direction over the window, stated coarsely on purpose.

    A precise slope on five noisy points is false precision, and this exists to
    flag movement worth looking at, not to forecast.
    """
    if len(values) < 3:
        return "unknown"
    half = len(values) // 2
    early = sum(values[:half]) / half
    late = sum(values[-half:]) / half
    if early == 0:
        return "rising" if late > 0 else "flat"
    change = (late - early) / abs(early)
    return "rising" if change > 0.2 else "falling" if change < -0.2 else "stable"


def stage_stability(history: Sequence[dict], stage: str,
                    window: int = 7) -> StageStability:
    """Is this stage's conversion rate stable enough to rank on?"""
    import statistics
    series = [d.get("rates", {}).get(stage) for d in history[-window:]]
    values = [v for v in series if v is not None]
    today = values[-1] if values else None

    if len(values) < MIN_OBSERVATIONS:
        return StageStability(stage, len(values), today, None, None, None,
                              None, "unknown", None, INSUFFICIENT)

    mean = statistics.fmean(values)
    median = statistics.median(values)
    stdev = statistics.pstdev(values)
    cv = (stdev / mean) if mean else None
    # A normal-ish interval on a small sample is a rough guide, not a claim.
    half = 1.96 * (stdev / (len(values) ** 0.5)) if stdev else 0.0
    interval = (round(mean - half, 3), round(mean + half, 3))
    # A stage with ZERO dispersion is maximally stable, not unstable. CV is
    # undefined when the mean is 0 (x/0), and the first version fell through to
    # UNSTABLE -- so `signal_fired`, flat at 0.00 for five consecutive days,
    # was reported as too noisy to rank on. It is the single most stable
    # observation in the report, and it says the signal has never once fired.
    if stdev == 0:
        status = STABLE
    else:
        status = STABLE if (cv is not None and cv <= MAX_STABLE_CV) else UNSTABLE
    return StageStability(stage, len(values), today, round(mean, 3),
                          round(median, 3), round(stdev, 3),
                          (round(cv, 3) if cv is not None else None),
                          _trend(values), interval, status)


def stability_report(history: Sequence[dict], window: int = 7) -> List[dict]:
    return [stage_stability(history, s, window).as_dict()
            for s in CHAIN[1:] + TERMINALS + DIAGNOSTICS]


def promote_bottleneck(history: Sequence[dict], window: int = 7) -> dict:
    """A stage becomes #1 only on sufficient history AND stability.

    Replaces the calendar rule outright. Three days of 3%, 8%, 4% satisfies
    "three days" and establishes nothing, so the test is dispersion rather
    than duration.
    """
    tally: Dict[str, int] = {}
    for day in history:
        loss = day.get("largest_loss")
        if loss:
            tally[loss["stage"]] = tally.get(loss["stage"], 0) + 1
    if not tally:
        return {"verdict": "CANDIDATE BOTTLENECK", "stage": None,
                "reason": "no conversion loss recorded yet"}

    stage, days = max(tally.items(), key=lambda kv: kv[1])
    stability = stage_stability(history, stage, window)
    if stability.status == INSUFFICIENT:
        return {"verdict": "CANDIDATE BOTTLENECK", "stage": stage,
                "reason": (f"{stability.observations} observation(s); "
                           f"{MIN_OBSERVATIONS} needed before dispersion "
                           f"means anything"),
                "stability": stability.as_dict()}
    if stability.status == UNSTABLE:
        return {"verdict": "CANDIDATE BOTTLENECK", "stage": stage,
                "reason": (f"conversion varies too much to rank on "
                           f"(CV {stability.cv:.0%} > {MAX_STABLE_CV:.0%}) — "
                           f"this is measuring conditions, not capability"),
                "stability": stability.as_dict()}
    if days <= len(history) / 2:
        return {"verdict": "CANDIDATE BOTTLENECK", "stage": stage,
                "reason": f"led the loss on only {days} of {len(history)} days",
                "stability": stability.as_dict()}
    return {"verdict": "BOTTLENECK", "stage": stage,
            "reason": (f"led the loss on {days} of {len(history)} days and is "
                       f"statistically stable (CV {stability.cv:.0%})"),
            "stability": stability.as_dict()}


# ---------------------------------------------------------------------------
# EVIDENCE MATURITY
#
# How close a candidate is to being decidable, stated as a number rather than
# as "not yet". "Insufficient history" is honest and uninformative on its own:
# it does not say whether the answer is one day away or twenty, and a system
# whose default output is uncertainty owes the reader that distinction.
#
# It also enforces the other half of the promotion constitution. Once the
# floor is reached the system must DECIDE — promote or reject. Continuing to
# gather data purely to avoid committing is as wrong as committing too early,
# and is the failure mode a project this cautious is most likely to develop.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Maturity:
    stage: str
    observations: int
    required: int
    candidate_streak: int
    confidence: str
    days_to_earliest_promotion: int

    @property
    def maturity(self) -> float:
        return round(min(self.observations / self.required, 1.0), 3)

    @property
    def must_decide(self) -> bool:
        """The floor is reached: gathering more data is no longer neutral."""
        return self.observations >= self.required

    def as_dict(self) -> dict:
        return {"stage": self.stage, "observations": self.observations,
                "required": self.required, "maturity": self.maturity,
                "candidate_streak": self.candidate_streak,
                "confidence": self.confidence,
                "days_to_earliest_promotion":
                    self.days_to_earliest_promotion,
                "must_decide": self.must_decide}


def candidate_streak(history: Sequence[dict], stage: str) -> int:
    """Consecutive days this stage led the conversion loss, most recent first."""
    streak = 0
    for day in reversed(history):
        loss = day.get("largest_loss") or {}
        if loss.get("stage") == stage:
            streak += 1
        else:
            break
    return streak


def evidence_maturity(history: Sequence[dict], stage: str,
                      window: int = 7) -> Maturity:
    stability = stage_stability(history, stage, window)
    observed = stability.observations
    remaining = max(MIN_OBSERVATIONS - observed, 0)
    return Maturity(stage=stage, observations=observed,
                    required=MIN_OBSERVATIONS,
                    candidate_streak=candidate_streak(history, stage),
                    confidence=stability.status,
                    days_to_earliest_promotion=remaining)


# ---------------------------------------------------------------------------
# RESEARCH VELOCITY
#
# Not code written, not trades opened. What the project LEARNED this cycle.
#
# Zero is a legitimate value and is printed as zero. A research system that
# feels obliged to report a discovery every day will eventually manufacture
# one, and manufacturing findings is the failure this whole framework exists
# to prevent.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResearchVelocity:
    new_positive: int = 0
    new_negative: int = 0
    strengthened: int = 0
    weakened: int = 0
    hypotheses_retired: int = 0
    techniques_adopted: int = 0

    @property
    def net_knowledge_gain(self) -> int:
        """Findings weakened count AGAINST the total. A day that undermines a
        previously held conclusion has negative velocity, and that is correct:
        the project knows less than it thought it did."""
        return (self.new_positive + self.new_negative + self.strengthened
                + self.techniques_adopted - self.weakened)

    def as_dict(self) -> dict:
        return {"new_positive": self.new_positive,
                "new_negative": self.new_negative,
                "strengthened": self.strengthened, "weakened": self.weakened,
                "hypotheses_retired": self.hypotheses_retired,
                "techniques_adopted": self.techniques_adopted,
                "net_knowledge_gain": self.net_knowledge_gain}

    def render(self) -> str:
        d = self.as_dict()
        lines = [f"  {k.replace('_', ' '):<26}{v:>+4}" if k == "net_knowledge_gain"
                 else f"  {k.replace('_', ' '):<26}{v:>4}"
                 for k, v in d.items()]
        return "\n".join(lines)

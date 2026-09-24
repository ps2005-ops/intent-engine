"""§15: does the collective block warn EARLIER, and at what price in alarms?

WHY THIS MAY MATTER MORE THAN BRIER
-----------------------------------
A probability forecast scored at a fixed horizon rewards being right about
the level. What a decision-maker usually needs is the TURN: the first moment
the picture changed. Those are different questions, and a feature block can
be useless for one and useful for the other. Reporting only the Brier delta
would retire a construct for failing a test it was not the best test of.

THE TRAP, AND THE CONTROL
-------------------------
Warning earlier is trivially achievable: lower the threshold until the model
is always warning. Then the lead time is enormous and the model is useless.

So lead time is measured TWICE:

    RAW              at each model's own 0.5 decision boundary
    ALARM-MATCHED    at the threshold that makes the augmented model raise
                     the SAME NUMBER of alarm origins as the base model

The second is the one that means anything. If lead time improves raw and
vanishes alarm-matched, the improvement was bought with false alarms and the
verdict says so.

WHAT COUNTS AS A WARNING
------------------------
One origin above threshold is noise. A warning is `SUSTAIN` consecutive
origins above it -- fixed here, before any lead-time number was computed, for
the same reason every other threshold in this package is a round number
declared in advance.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_leadtime.v1"

#: Consecutive origins above threshold before it counts as a warning.
SUSTAIN = 2

#: A warning this far before an episode opens is credited to that episode.
#: Beyond it, the warning is early enough to be about something else and is
#: counted as a false alarm instead.
MAX_LEAD_DAYS = 730

#: A warning run in calm that is not followed by an episode inside this
#: window is a false alarm.
FALSE_ALARM_WINDOW_DAYS = 365


def _d(s: str) -> _dt.date:
    return _dt.date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def warning_runs(series: Sequence[Tuple[str, float]], threshold: float, *,
                 sustain: int = SUSTAIN) -> List[Tuple[str, str]]:
    """Maximal runs of >= `sustain` consecutive origins above `threshold`."""
    ordered = sorted(series)
    runs, cur = [], []
    for origin, p in ordered:
        if p >= threshold:
            cur.append(origin)
        else:
            if len(cur) >= sustain:
                runs.append((cur[0], cur[-1]))
            cur = []
    if len(cur) >= sustain:
        runs.append((cur[0], cur[-1]))
    return runs


def threshold_for_alarm_count(series: Sequence[Tuple[str, float]],
                              target_alarms: int, *,
                              sustain: int = SUSTAIN) -> float:
    """The lowest threshold whose alarm-origin count does not exceed target.

    Searched over the model's own predicted probabilities, so the comparison
    is between two models raising the same number of alarms rather than
    between two arbitrary cut points.
    """
    ps = sorted({round(p, 4) for _o, p in series}, reverse=True)
    best = 1.0
    for t in ps:
        origins = sum(1 for _o, p in series if p >= t)
        if origins <= target_alarms:
            best = t
        else:
            break
    return best


@dataclass(frozen=True)
class EpisodeLead:
    """One episode, seen by one model."""

    episode_id: str
    episode_start: str
    model: str
    first_warning: str
    lead_days: Optional[int]
    threshold: float

    def as_dict(self) -> dict:
        return {"episode_id": self.episode_id,
                "episode_start": self.episode_start, "model": self.model,
                "first_warning": self.first_warning,
                "lead_days": self.lead_days,
                "threshold": round(self.threshold, 4)}


@dataclass(frozen=True)
class LeadTimeResult:
    """Base vs augmented, on lead time AND on what the lead time cost."""

    mode: str
    base_threshold: float
    augmented_threshold: float
    episodes: int
    per_episode: Tuple[dict, ...]
    median_lead_base: Optional[float]
    median_lead_augmented: Optional[float]
    lead_delta_days: Optional[float]
    false_alarms_base: int
    false_alarms_augmented: int
    alarm_origins_base: int
    alarm_origins_augmented: int
    warned_episodes_base: int = 0
    warned_episodes_augmented: int = 0

    @property
    def verdict(self) -> str:
        """§15's rule, applied mechanically.

        More lead time is only an improvement when it did not come with more
        false alarms. The ordering of these branches is the whole point: the
        false-alarm check runs BEFORE the lead-time check, so a model cannot
        be credited for warning earlier by warning constantly.
        """
        if self.lead_delta_days is None:
            return "NOT_MEASURED"
        if self.false_alarms_augmented > self.false_alarms_base:
            return "LEAD_BOUGHT_WITH_FALSE_ALARMS"
        if self.warned_episodes_augmented < self.warned_episodes_base:
            return "LEAD_BOUGHT_BY_MISSING_EPISODES"
        if self.lead_delta_days > 0:
            return "EARLIER"
        if self.lead_delta_days < 0:
            return "LATER"
        return "NO_DIFFERENCE"

    def statement(self) -> str:
        if self.lead_delta_days is None:
            return (f"{self.mode}: no episode was warned by both models, so "
                    "lead time was not measured.")
        return (f"{self.mode}: augmented median lead "
                f"{self.median_lead_augmented:.0f}d vs base "
                f"{self.median_lead_base:.0f}d "
                f"(delta {self.lead_delta_days:+.0f}d) over "
                f"{self.episodes} episode(s); false alarms "
                f"{self.false_alarms_augmented} vs {self.false_alarms_base}; "
                f"alarm origins {self.alarm_origins_augmented} vs "
                f"{self.alarm_origins_base}. {self.verdict}")

    def as_dict(self) -> dict:
        return {"mode": self.mode, "verdict": self.verdict,
                "base_threshold": round(self.base_threshold, 4),
                "augmented_threshold": round(self.augmented_threshold, 4),
                "episodes": self.episodes,
                "median_lead_base": self.median_lead_base,
                "median_lead_augmented": self.median_lead_augmented,
                "lead_delta_days": self.lead_delta_days,
                "false_alarms_base": self.false_alarms_base,
                "false_alarms_augmented": self.false_alarms_augmented,
                "alarm_origins_base": self.alarm_origins_base,
                "alarm_origins_augmented": self.alarm_origins_augmented,
                "warned_episodes_base": self.warned_episodes_base,
                "warned_episodes_augmented": self.warned_episodes_augmented,
                "per_episode": list(self.per_episode),
                "statement": self.statement()}


def _leads(series, threshold, episodes, model):
    runs = warning_runs(series, threshold)
    out = []
    for ep in episodes:
        start = ep.start_as_known
        candidates = [lo for lo, _hi in runs
                      if lo <= start and 0 <= (_d(start) - _d(lo)).days
                      <= MAX_LEAD_DAYS]
        # A warning that begins INSIDE the episode still counts, with zero or
        # negative lead: the model noticed, late.
        inside = [lo for lo, hi in runs
                  if start <= lo <= ep.end_as_known]
        if candidates:
            first = min(candidates)
            lead = (_d(start) - _d(first)).days
        elif inside:
            first = min(inside)
            lead = -(_d(first) - _d(start)).days
        else:
            first, lead = "", None
        out.append(EpisodeLead(episode_id=ep.episode_id, episode_start=start,
                               model=model, first_warning=first,
                               lead_days=lead, threshold=threshold))
    return out, runs


def _false_alarms(runs, episodes) -> int:
    """Warning runs that no episode followed inside the window."""
    n = 0
    for lo, _hi in runs:
        followed = any(
            0 <= (_d(ep.start_as_known) - _d(lo)).days
            <= FALSE_ALARM_WINDOW_DAYS or ep.covers(lo)
            for ep in episodes)
        if not followed:
            n += 1
    return n


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return float(xs[m]) if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0


def compare(*, base: Sequence[Tuple[str, float]],
            augmented: Sequence[Tuple[str, float]],
            episodes: Sequence, mode: str = "RAW",
            base_threshold: float = 0.5) -> LeadTimeResult:
    """Lead time for two models over the same episodes.

    `base` and `augmented` are (origin, probability-of-deterioration) at every
    origin. In ALARM_MATCHED mode the augmented threshold is raised until it
    fires on no more origins than the base model does.
    """
    require(bool(episodes), "lead time needs at least one episode")
    b_alarm_origins = sum(1 for _o, p in base if p >= base_threshold)
    if mode == "ALARM_MATCHED":
        a_threshold = threshold_for_alarm_count(augmented, b_alarm_origins)
    else:
        a_threshold = base_threshold
    b_leads, b_runs = _leads(base, base_threshold, episodes, "BASE")
    a_leads, a_runs = _leads(augmented, a_threshold, episodes, "AUGMENTED")
    by_ep = {}
    for bl, al in zip(b_leads, a_leads):
        by_ep[bl.episode_id] = {
            "episode_id": bl.episode_id, "episode_start": bl.episode_start,
            "base": bl.as_dict(), "augmented": al.as_dict(),
            "delta_days": (None if bl.lead_days is None or al.lead_days is None
                           else al.lead_days - bl.lead_days)}
    paired = [v["delta_days"] for v in by_ep.values()
              if v["delta_days"] is not None]
    return LeadTimeResult(
        mode=mode, base_threshold=base_threshold,
        augmented_threshold=a_threshold, episodes=len(paired),
        per_episode=tuple(by_ep.values()),
        median_lead_base=_median([l.lead_days for l in b_leads]),
        median_lead_augmented=_median([l.lead_days for l in a_leads]),
        lead_delta_days=_median(paired),
        false_alarms_base=_false_alarms(b_runs, episodes),
        false_alarms_augmented=_false_alarms(a_runs, episodes),
        alarm_origins_base=b_alarm_origins,
        alarm_origins_augmented=sum(1 for _o, p in augmented
                                    if p >= a_threshold),
        warned_episodes_base=sum(1 for l in b_leads
                                 if l.lead_days is not None),
        warned_episodes_augmented=sum(1 for l in a_leads
                                      if l.lead_days is not None))

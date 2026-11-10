"""§5/§8: how much INFORMATION a sample carries, as opposed to how many rows.

THE NUMBER THAT LIED
--------------------
An INFLATION_SHOCK slice was reported as n=30 with a decisive-looking
interval. The 30 rows were five targets at two horizons from 14 forecast
origins, and those 14 origins were one contiguous episode. The honest sample
size was closer to one than to thirty, and no amount of bootstrap machinery
recovers that from a row count.

So a sample is described by FOUR numbers here, never one:

    raw_rows              what a naive count returns
    unique_origins        distinct forecast dates behind those rows
    effective_origins     origins discounted for how alike they are
    independent_episodes  separate economic events they fall into

`Sample.headline()` renders all four, and there is deliberately no method
that renders the first alone.

WHY EFFECTIVE ORIGINS AND NOT JUST ORIGINS
------------------------------------------
Moving from a quarterly origin grid to a monthly one multiplies rows by three
and origins by three. It does not multiply information by three: consecutive
monthly origins share most of their feature history and their outcome windows
overlap almost completely. The design effect

    n_eff = n / (1 + (m_bar - 1) * ICC)

is the standard correction for that, with the intra-cluster correlation
ESTIMATED FROM THE DATA rather than assumed. If monthly conversion raises
rows fourfold and n_eff by a tenth, this module says so in the same object
that reports the gain, which is the point.

WHY EPISODES ARE COUNTED AND NOT CORRECTED FOR
----------------------------------------------
A block bootstrap over two blocks is not meaningfully better than saying
"two". `MIN_EPISODES` in `incremental` is the gate; this module supplies the
count and the breakdown that makes the gate legible.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_power.v1"

#: Two origins more than this many days apart are in different episodes
#: unless something in between joins them. Set to two quarters: an economy
#: that has been quiet for six months has normalised, and the next stress is
#: a new event rather than a continuation.
EPISODE_GAP_DAYS = 200


def _to_date(s: str):
    import datetime as _dt
    return _dt.date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def intra_cluster_correlation(values: Sequence[float],
                              clusters: Sequence[str]) -> float:
    """One-way random-effects ICC of `values` grouped by `clusters`.

    The share of total variance that is BETWEEN clusters. Zero means the rows
    in a cluster are as unlike each other as rows from different clusters --
    clustering costs nothing. One means every row in a cluster is a copy, and
    the cluster is worth exactly one observation.

    Returned clamped to [0, 1]: a negative estimate is a small-sample
    artefact, and treating it as "better than independent" would inflate the
    sample size, which is the direction this module exists to refuse.
    """
    groups: Dict[str, List[float]] = {}
    for v, c in zip(values, clusters):
        groups.setdefault(c, []).append(v)
    k = len(groups)
    n = len(values)
    if k < 2 or n <= k:
        return 0.0
    grand = sum(values) / n
    ss_between = sum(len(g) * (sum(g) / len(g) - grand) ** 2
                     for g in groups.values())
    ss_within = sum((x - sum(g) / len(g)) ** 2
                    for g in groups.values() for x in g)
    ms_between = ss_between / (k - 1)
    ms_within = ss_within / (n - k) if n > k else 0.0
    sizes = [len(g) for g in groups.values()]
    m0 = (n - sum(s * s for s in sizes) / n) / (k - 1)
    if m0 <= 0 or ms_between + ms_within == 0:
        return 0.0
    var_between = (ms_between - ms_within) / m0
    denom = var_between + ms_within
    if denom <= 0:
        return 0.0
    return max(0.0, min(1.0, var_between / denom))


def count_episodes(origins: Sequence[str], *,
                   gap_days: int = EPISODE_GAP_DAYS) -> int:
    dates = sorted({o for o in origins if len(o) == 10 and o[4] == "-"})
    if not dates:
        return len(set(origins))
    episodes, prev = 1, None
    for d in dates:
        cur = _to_date(d)
        if prev is not None and (cur - prev).days > gap_days:
            episodes += 1
        prev = cur
    return episodes


def episode_spans(origins: Sequence[str], *,
                  gap_days: int = EPISODE_GAP_DAYS) -> List[Tuple[str, str]]:
    dates = sorted({o for o in origins if len(o) == 10 and o[4] == "-"})
    if not dates:
        return []
    spans, start, prev = [], dates[0], dates[0]
    for d in dates[1:]:
        if (_to_date(d) - _to_date(prev)).days > gap_days:
            spans.append((start, prev))
            start = d
        prev = d
    spans.append((start, prev))
    return spans


def lag1_autocorrelation(series: Sequence[Tuple[str, float]]) -> float:
    """Lag-1 autocorrelation of a time-ordered sequence of (date, value).

    THE QUANTITY §5 ACTUALLY NEEDS. The within-origin ICC says rows from one
    origin are alike, which the origin clustering already handles. What
    monthly conversion changes is whether ORIGINS are alike: a January and a
    February origin share eleven of twelve months of feature history and
    their outcome windows overlap by more than 95%. A quarterly pair shares
    less.

    Clamped to [0, 1) for the same reason the ICC is: a negative estimate is
    small-sample noise, and using it would report MORE independent units than
    there are origins.
    """
    xs = [v for _d, v in sorted(series)]
    n = len(xs)
    if n < 3:
        return 0.0
    mean = sum(xs) / n
    denom = sum((x - mean) ** 2 for x in xs)
    if denom <= 0:
        return 0.0
    num = sum((xs[i] - mean) * (xs[i + 1] - mean) for i in range(n - 1))
    return max(0.0, min(0.999, num / denom))


def effective_units(k: int, rho: float) -> float:
    """How many independent observations `k` autocorrelated ones are worth.

        n_eff = k * (1 - rho) / (1 + rho)

    The standard AR(1) effective-sample-size. At rho=0 it returns k; at
    rho=0.9 it returns k/19. This is the formula that makes "three times as
    many origins" and "three times as much information" different claims,
    which is the whole of §5.
    """
    if k <= 0:
        return 0.0
    return max(1.0, k * (1.0 - rho) / (1.0 + rho))


@dataclass(frozen=True)
class Sample:
    """What a count of rows actually amounts to.

    Constructed from the rows themselves, so the four numbers cannot drift
    apart the way a hand-maintained summary does.
    """

    raw_rows: int
    unique_origins: int
    effective_origins: float
    independent_episodes: int
    icc: float = 0.0
    #: Lag-1 autocorrelation of the per-origin means. The number that decides
    #: whether more origins are more information.
    origin_autocorrelation: float = 0.0
    mean_rows_per_origin: float = 0.0
    origins_per_episode: Tuple[int, ...] = ()
    rows_per_episode: Tuple[int, ...] = ()
    targets: int = 0
    horizons: int = 0
    span: Tuple[str, str] = ("", "")

    @property
    def pseudo_replication_factor(self) -> float:
        """How many times each independent unit is being counted."""
        if self.effective_origins <= 0:
            return float(self.raw_rows)
        return round(self.raw_rows / self.effective_origins, 2)

    def headline(self) -> str:
        """The only sanctioned way to state a sample size.

        There is no method here that prints `raw_rows` on its own. §2's rule
        -- never display raw n alone -- is enforced by the absence of the
        thing that would break it, not by remembering.
        """
        return (f"{self.raw_rows} rows / {self.unique_origins} origins / "
                f"{self.effective_origins:.1f} effective / "
                f"{self.independent_episodes} episodes")

    def as_dict(self) -> dict:
        return {"raw_rows": self.raw_rows,
                "unique_origins": self.unique_origins,
                "effective_origins": round(self.effective_origins, 2),
                "independent_episodes": self.independent_episodes,
                "icc": round(self.icc, 4),
                "origin_autocorrelation": round(self.origin_autocorrelation, 4),
                "mean_rows_per_origin": round(self.mean_rows_per_origin, 2),
                "origins_per_episode": list(self.origins_per_episode),
                "rows_per_episode": list(self.rows_per_episode),
                "targets": self.targets, "horizons": self.horizons,
                "span": list(self.span),
                "pseudo_replication_factor": self.pseudo_replication_factor,
                "headline": self.headline()}


def measure(*, origins: Sequence[str], values: Sequence[float] = (),
            targets: Sequence[str] = (), horizons: Sequence[int] = (),
            phase_of: Dict[str, str] = None,
            gap_days: int = EPISODE_GAP_DAYS) -> Sample:
    """Describe a sample of paired forecasts.

    `origins` is one entry PER ROW -- the forecast date that row came from.
    `values` is the per-row quantity whose dependence matters, normally the
    paired loss difference. Without it the ICC cannot be estimated and the
    effective count falls back to the origin count, which is the
    conservative reading rather than the flattering one.
    """
    require(bool(origins), "a sample is described by the origins behind it")
    rows = len(origins)
    uniq = sorted(set(origins))
    k = len(uniq)
    have_values = bool(values) and len(values) == rows
    icc = (intra_cluster_correlation(values, origins) if have_values else 1.0)
    m_bar = rows / k if k else 0.0
    # TWO discounts, applied in order, because they are two different kinds
    # of dependence and correcting only one leaves the other intact.
    #
    #   1. rows -> origins, via the within-origin ICC. Five targets at two
    #      horizons from one origin are not ten observations.
    #   2. origins -> effective origins, via the lag-1 autocorrelation of the
    #      per-origin means. Twelve monthly origins in a year are not twelve
    #      observations either, and THIS is the discount a monthly grid runs
    #      into.
    if have_values:
        by_origin: Dict[str, List[float]] = {}
        for o, v in zip(origins, values):
            by_origin.setdefault(o, []).append(v)
        means = [(o, sum(vs) / len(vs)) for o, vs in by_origin.items()]
        rho = lag1_autocorrelation(means)
    else:
        rho = 0.9      # unmeasurable: assume strong dependence, not none
    n_eff = effective_units(k, rho)
    # EPISODES: a MACROECONOMIC PHASE COUNT, not a contiguity count, when a
    # phase map is supplied.
    #
    # Contiguity alone is the right unit for a REGIME SLICE -- the origins of
    # an inflation slice really do fall into separate events. It is wrong for
    # the global sample, whose origins run consecutively month after month
    # and therefore form ONE contiguous block however many crises they
    # contain. That produced "4619 rows / 480 origins / 126.6 effective /
    # 1 episodes" for a sample spanning 1978-2026, and would have made every
    # global result fail MIN_EPISODES for the wrong reason.
    #
    # `phase_of` maps an origin to the discovered stress episode it belongs
    # to, or to the calm stretch between two of them. Both count: a calm
    # stretch is a separate macroeconomic situation, and a sample that saw
    # four crises and three intervening expansions saw seven.
    if phase_of:
        phases: Dict[str, List[str]] = {}
        for o in uniq:
            phases.setdefault(phase_of.get(o, "UNPHASED"), []).append(o)
        keys = sorted(phases)
        per_ep_origins = [len(phases[k]) for k in keys]
        per_ep_rows = [sum(1 for o in origins if phase_of.get(o) == k)
                       for k in keys]
        spans = [(min(phases[k]), max(phases[k])) for k in keys]
    else:
        spans = episode_spans(uniq, gap_days=gap_days)
        per_ep_origins, per_ep_rows = [], []
        for lo, hi in spans:
            o_in = [o for o in uniq if lo <= o <= hi]
            per_ep_origins.append(len(o_in))
            per_ep_rows.append(sum(1 for o in origins if lo <= o <= hi))
    return Sample(
        raw_rows=rows, unique_origins=k, effective_origins=n_eff,
        independent_episodes=len(spans), icc=icc, origin_autocorrelation=rho,
        mean_rows_per_origin=m_bar,
        origins_per_episode=tuple(per_ep_origins),
        rows_per_episode=tuple(per_ep_rows),
        targets=len(set(targets)), horizons=len(set(horizons)),
        span=(uniq[0], uniq[-1]) if uniq else ("", ""))


@dataclass(frozen=True)
class PowerDelta:
    """Before vs after, with the verdict §5 demands stated mechanically."""

    before: Sample
    after: Sample
    median_mde_before: Optional[float] = None
    median_mde_after: Optional[float] = None

    @property
    def row_gain(self) -> float:
        return (self.after.raw_rows / self.before.raw_rows
                if self.before.raw_rows else 0.0)

    @property
    def effective_gain(self) -> float:
        return (self.after.effective_origins / self.before.effective_origins
                if self.before.effective_origins else 0.0)

    @property
    def episode_gain(self) -> float:
        return (self.after.independent_episodes
                / self.before.independent_episodes
                if self.before.independent_episodes else 0.0)

    @property
    def verdict(self) -> str:
        """§5: more rows is not more information, and it must be SAID.

        The threshold is deliberately blunt. If the effective sample grew by
        less than a quarter while rows grew by half or more, the extra rows
        are re-descriptions of observations already held.
        """
        if self.episode_gain >= 1.5:
            return "INFORMATION_GAINED_EPISODES"
        if self.effective_gain >= 1.5:
            return "INFORMATION_GAINED_EFFECTIVE"
        if self.row_gain >= 1.5 and self.effective_gain < 1.25:
            return "ROWS_ONLY"
        if self.effective_gain > 1.0:
            return "MARGINAL_GAIN"
        return "NO_GAIN"

    def statement(self) -> str:
        v = self.verdict
        core = (f"rows x{self.row_gain:.2f}, effective origins "
                f"x{self.effective_gain:.2f}, episodes "
                f"x{self.episode_gain:.2f}")
        if v == "ROWS_ONLY":
            return (f"{core}. The reconstruction produced ROWS, NOT "
                    "INFORMATION: the added observations are re-descriptions "
                    "of periods already in the sample, and the detectable "
                    "effect size will barely move.")
        if v == "INFORMATION_GAINED_EPISODES":
            return (f"{core}. Genuine gain, and in the currency that was "
                    "actually scarce: separate economic events.")
        if v == "INFORMATION_GAINED_EFFECTIVE":
            return (f"{core}. Genuine gain in effective sample, though the "
                    "episode count is what governs whether a regime result "
                    "can be called robust.")
        if v == "MARGINAL_GAIN":
            return f"{core}. A real but small gain."
        return f"{core}. No gain."

    def as_dict(self) -> dict:
        return {"before": self.before.as_dict(), "after": self.after.as_dict(),
                "row_gain": round(self.row_gain, 3),
                "effective_gain": round(self.effective_gain, 3),
                "episode_gain": round(self.episode_gain, 3),
                "median_mde_before": self.median_mde_before,
                "median_mde_after": self.median_mde_after,
                "mde_reduction": (
                    round(1 - self.median_mde_after / self.median_mde_before, 3)
                    if self.median_mde_before and self.median_mde_after
                    else None),
                "verdict": self.verdict, "statement": self.statement()}


def projected_mde(current_mde: float, before: Sample, after: Sample) -> float:
    """What the detectable effect becomes when the effective sample grows.

    A bootstrap interval narrows with the square root of the number of
    INDEPENDENT units, not of rows. Projecting from rows is how a fourfold
    row increase gets sold as halving the detectable effect when it does
    nothing of the kind.
    """
    if before.effective_origins <= 0 or after.effective_origins <= 0:
        return current_mde
    return round(current_mde * math.sqrt(before.effective_origins
                                         / after.effective_origins), 5)


def phase_map(origins: Sequence[str], episodes: Sequence) -> Dict[str, str]:
    """origin -> the macroeconomic phase it sits in.

    A phase is either a DISCOVERED stress episode or the calm stretch between
    two of them. Built from `episodes.discover`, so the phases come from the
    contemporaneous classifier rather than from a list of remembered crises.
    """
    out: Dict[str, str] = {}
    eps = sorted(episodes, key=lambda e: e.start_as_known)
    for o in sorted(set(origins)):
        hit = next((e for e in eps
                    if e.start_as_known <= o <= e.end_as_known), None)
        if hit is not None:
            out[o] = hit.episode_id
            continue
        before = [e for e in eps if e.end_as_known < o]
        anchor = before[-1].episode_id if before else "PRE"
        out[o] = f"CALM_AFTER_{anchor}"
    return out

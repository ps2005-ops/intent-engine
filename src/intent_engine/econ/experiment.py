"""The shared harness: how a row is built, and which block it belongs to.

WHY THIS IS A MODULE AND NOT A SCRIPT SECTION
---------------------------------------------
Three scripts now build rows -- the global run, the regime run and the
lead-time run -- and the previous cycle shipped a defect that exists only
because they each did it their own way: the origin grid was inferred from a
date-string pattern in one and read from the manifest in another, and the two
disagreed by 229 origins. One builder, imported everywhere.

THE BALANCED BLOCK
------------------
`FC.Row.vector` fills a missing feature with 0.0. For a CHANGE feature, 0.0
is not "missing", it is "did not move" -- a substantive claim. DRCCLACBS has
vintages only from 2012, so in the previous run every origin before 2012
carried `DRCCLACBS_d4 = 0.0` and the model learned a feature that was a
disguised date indicator.

So a feature is admitted only if it is present at EVERY origin in the arm.
`balanced_names` is that filter, and the count it drops is reported rather
than silently absorbed.

CHANGES ARE PER-FREQUENCY, NOT PER-FOUR-PERIODS
------------------------------------------------
`_chg(h, 4)` is a year for a quarterly series and four months for a monthly
one. The regime classifier already had to learn this (`PERIODS_PER_YEAR`
exists because "inflation year on year" was being computed over a third of a
year and never once cleared the shock threshold). The same arithmetic error
was still live in the feature builder, where it made `INDPRO_d4` and
`TDSP_d4` different quantities under one naming convention.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import baselines as BS
from . import forecast as FC
from . import preregistration as PR
from . import regime as RG
from . import release as RL
from .vocabulary import EconError, require

CONTRACT = "econ_experiment.v1"

#: Rate levels are stationary enough to be informative. Every other level is
#: a proxy for the calendar -- the defect that manufactured a +0.134 housing
#: "win" in an earlier cycle.
STATIONARY_LEVELS = ("UNRATE", "DFF", "DGS2", "DGS10")

PERIODS_PER_YEAR = {RL.DAILY: 12, RL.MONTHLY: 12, RL.QUARTERLY: 4,
                    RL.ANNUAL: 1}


@dataclass(frozen=True)
class Arm:
    """One experiment arm: an origin range and the blocks readable in it."""

    name: str
    origins: Tuple[str, ...]
    base_series: Tuple[str, ...]
    behavioural_series: Tuple[str, ...]
    note: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "origins": len(self.origins),
                "span": [self.origins[0], self.origins[-1]] if self.origins
                        else [],
                "base_series": list(self.base_series),
                "behavioural_series": list(self.behavioural_series),
                "note": self.note}


def _periods_for_year(sid: str) -> int:
    rule = RL.BY_ID.get(sid)
    return PERIODS_PER_YEAR.get(rule.frequency if rule else RL.MONTHLY, 12)


def _chg(hist, periods: int) -> Optional[float]:
    if len(hist) <= periods:
        return None
    a, b = hist[-1 - periods][1], hist[-1][1]
    return None if a == 0 else (b - a) / abs(a)


def _diff(hist, periods: int) -> Optional[float]:
    if len(hist) <= periods:
        return None
    return hist[-1][1] - hist[-1 - periods][1]


def change(sid: str, hist, periods: int) -> Optional[float]:
    """The right change transform for this series.

    A PERCENTAGE-POINT series gets an arithmetic difference; everything else
    gets a relative change. See `release.PERCENTAGE_POINT_SERIES` for the
    measured reason -- a saving rate that crosses zero has no relative change,
    and asking for one made the feature undefined at three origins and
    meaningless at several more.
    """
    return (_diff(hist, periods) if RL.is_percentage_point(sid)
            else _chg(hist, periods))


def features_at(panel, origin: str, series: Sequence[str]) -> Dict[str, float]:
    """Walled features for one origin. Changes over a YEAR and a QUARTER."""
    out: Dict[str, float] = {}
    for sid in series:
        ppy = _periods_for_year(sid)
        h = panel.history(sid, as_of=origin, lookback=ppy * 2 + 4)
        if len(h) < 6:
            continue
        if sid in STATIONARY_LEVELS:
            out[f"{sid}_lvl"] = h[-1][1]
        yoy = change(sid, h, ppy)
        if yoy is not None:
            out[f"{sid}_yoy"] = yoy
        q = change(sid, h, max(1, ppy // 4))
        if q is not None:
            out[f"{sid}_q"] = q
    return out


def regime_features(reading) -> Dict[str, float]:
    """One indicator per regime, from the CONTEMPORANEOUS classifier.

    Named with a `REGIME_` prefix so `balanced_names` and the baseline ladder
    can select them the same way they select any other block.
    """
    return {f"REGIME_{r}": (1.0 if reading.holds(r) else 0.0)
            for r in RG.REGIMES}


def build_rows(panel, arm: Arm, *, readings: Dict[str, object] = None
               ) -> Tuple[List[FC.Row], dict]:
    """One Row per (origin, family). Inputs walled; outcome in hindsight."""
    truth = {t: dict(panel.history(t, as_of="2099-01-01"))
             for t in PR.TARGET_SERIES}
    periods = {t: sorted(truth[t]) for t in PR.TARGET_SERIES}
    rows: List[FC.Row] = []
    skipped = {"thin_base": 0, "thin_behavioural": 0, "no_outcome": 0}

    for origin in arm.origins:
        base_f = features_at(panel, origin, arm.base_series)
        beh_f = features_at(panel, origin, arm.behavioural_series)
        if len(base_f) < 6:
            skipped["thin_base"] += 1
            continue
        if len(beh_f) < 3:
            skipped["thin_behavioural"] += 1
            continue
        reg_f = (regime_features(readings[origin])
                 if readings and origin in readings else {})
        reg_label = ("|".join(readings[origin].regimes)
                     if readings and origin in readings else "ALL")
        for fam in PR.FAMILIES:
            t = fam.target_series
            past = [p for p in periods[t] if p <= origin]
            if len(past) < 3:
                skipped["no_outcome"] += 1
                continue
            now_p = past[-1]
            fut = [p for p in periods[t] if p > now_p]
            # The horizon in PERIODS of the target's own frequency.
            want = max(0, (fam.horizon_days // 30)
                       // max(1, 12 // _periods_for_year(t)))
            if len(fut) <= want:
                skipped["no_outcome"] += 1
                continue
            fut_p = fut[want]
            # PERSISTENCE, from the target's OWN last move as known at the
            # origin -- not from the previous row, which is a different
            # target at the same origin.
            last_move = 0.0
            if len(past) >= 2:
                prev = truth[t][past[-2]]
                last_move = (1.0 if truth[t][now_p] > prev
                             else (-1.0 if truth[t][now_p] < prev else 0.0))
            rows.append(FC.Row(
                origin=origin, target=fam.family_id,
                horizon_days=fam.horizon_days,
                features={**base_f, **beh_f, **reg_f,
                          BS.PERSISTENCE_FEATURE: last_move},
                outcome=truth[t][fut_p] > truth[t][now_p],
                regime=reg_label, outcome_knowable_at=fut_p))
    return rows, skipped


def balanced_names(rows: Sequence[FC.Row], prefixes: Sequence[str]
                   ) -> Tuple[List[str], List[str]]:
    """Feature names present at EVERY origin, and the ones dropped.

    Returns (kept, dropped). The dropped list is returned rather than logged
    because a block that lost half its columns to imbalance is a different
    experiment from the one that was declared, and the report has to be able
    to say so.
    """
    origins = sorted({r.origin for r in rows})
    if not origins:
        return [], []
    seen: Dict[str, set] = {}
    for r in rows:
        for n in r.features:
            if any(n.startswith(p + "_") for p in prefixes):
                seen.setdefault(n, set()).add(r.origin)
    kept = sorted(n for n, os in seen.items() if len(os) == len(origins))
    dropped = sorted(n for n, os in seen.items() if len(os) != len(origins))
    return kept, dropped


# =============================================================================
# STRUCTURAL GUARDS
# =============================================================================
# Each of these exists because the thing it refuses has actually happened in
# this codebase. They are called from the experiment runner, so a mutation
# that reintroduces the defect turns a run RED rather than producing a
# plausible number.

class BlockDefect(EconError):
    """The feature block is not the block that was declared."""


def assert_all_live_instruments_present(block: Sequence[str],
                                        expected: Sequence[str]) -> None:
    """Every live, non-superseded instrument must reach the model.

    THE DEFECT THIS CATCHES. `series_by_construct` once built `{spec.kind:
    spec.key}` -- a dict keyed by kind, keeping only the LAST series per
    kind. Four kinds have several live ids, so quits and participation
    vanished from the feature set the moment two superseded BLS ids were
    declared. The pooled delta moved by 0.005 and nothing in the report said
    why.
    """
    missing = sorted(set(expected) - set(block))
    if missing:
        raise BlockDefect(
            f"{len(missing)} live instrument(s) are declared and did not "
            f"reach the model: {missing}. A block that silently loses a "
            "series produces a delta about a different feature set from the "
            "one the report names.")


#: Series whose LEVEL grows almost monotonically. A model given one of these
#: as a level has been given the date.
TRENDING = ("CPIAUCSL", "PCEC96", "INDPRO", "GDPC1", "REVOLSL", "DGORDER",
            "HOUST", "HSN1F")


def assert_no_trending_levels(names: Sequence[str]) -> None:
    """No feature may be the raw level of a trending series.

    THE DEFECT THIS CATCHES. An earlier cycle reported +0.134 Brier on
    housing surviving FDR correction. CPIAUCSL and PCEC96 grow almost
    monotonically, so their level is a proxy for the calendar; the model fit
    the calendar on ~40 training rows and the delta between two models that
    both fit the calendar measured nothing.
    """
    bad = sorted(n for n in names
                 if n.endswith("_lvl") and n[:-4] in TRENDING)
    if bad:
        raise BlockDefect(
            f"{bad} are raw levels of trending series. A level that rises "
            "every period is the date wearing an economic name, and a model "
            "given the date will fit it.")


# =============================================================================
# §7/§12: ARBITRARY (target, horizon) ROWS, AND WHICH OF THEM ARE TESTABLE
# =============================================================================

def build_target_rows(panel, arm: "Arm", *, targets: Sequence[str],
                      horizons: Sequence[int],
                      readings: Dict[str, object] = None,
                      base_series: Sequence[str] = (),
                      extra_series: Sequence[str] = ()
                      ) -> Tuple[List[FC.Row], dict]:
    """Rows for a hypothesis that declares its own targets and horizons.

    `build_rows` reads `preregistration.FAMILIES`, which is right for H1-H6
    and wrong for H7: H7 declares HOUST and INDPRO at 180 and 240 days, and
    240 is not a preregistered family horizon. Adding it to FAMILIES would
    change the V1 declaration hash after the fact, which is precisely the
    mutation break proof 8 exists to catch.
    """
    base_block = tuple(base_series) or arm.base_series
    rows: List[FC.Row] = []
    skipped = {"thin_base": 0, "thin_extra": 0, "no_outcome": 0}
    truth = {t: dict(panel.history(t, as_of="2099-01-01")) for t in targets}
    periods = {t: sorted(truth[t]) for t in targets}

    for origin in arm.origins:
        base_f = features_at(panel, origin, base_block)
        extra_f = features_at(panel, origin, extra_series) if extra_series \
            else {}
        if len(base_f) < 6:
            skipped["thin_base"] += 1
            continue
        if extra_series and not extra_f:
            skipped["thin_extra"] += 1
            continue
        reg_f = (regime_features(readings[origin])
                 if readings and origin in readings else {})
        reg_label = ("|".join(readings[origin].regimes)
                     if readings and origin in readings else "ALL")
        for t in targets:
            for h in horizons:
                past = [p for p in periods[t] if p <= origin]
                if len(past) < 3:
                    skipped["no_outcome"] += 1
                    continue
                now_p = past[-1]
                fut = [p for p in periods[t] if p > now_p]
                want = max(0, (h // 30) // max(1, 12 // _periods_for_year(t)))
                if len(fut) <= want:
                    skipped["no_outcome"] += 1
                    continue
                fut_p = fut[want]
                last_move = 0.0
                if len(past) >= 2:
                    prev = truth[t][past[-2]]
                    last_move = (1.0 if truth[t][now_p] > prev
                                 else (-1.0 if truth[t][now_p] < prev else 0.0))
                rows.append(FC.Row(
                    origin=origin, target=f"{t}_{h}d", horizon_days=h,
                    features={**base_f, **extra_f, **reg_f,
                              BS.PERSISTENCE_FEATURE: last_move},
                    outcome=truth[t][fut_p] > truth[t][now_p],
                    regime=reg_label, outcome_knowable_at=fut_p))
    return rows, skipped


@dataclass(frozen=True)
class TargetEligibility:
    """§12: may this forecast family carry a human-state verdict at all?

    A family whose base model loses to a constant cannot. The previous run
    reported CollectiveHumanState verdicts on eight such families before the
    per-family gate existed, and every one of those verdicts was a statement
    about the harness.
    """

    target_id: str
    base_rate: float
    usable_origins: int
    effective_origins: float
    episodes: int
    baseline_clear: bool
    baseline_reason: str
    mde: Optional[float] = None

    @property
    def eligible_for_human_test(self) -> bool:
        from .incremental import MIN_EPISODES
        return (self.baseline_clear and self.episodes >= MIN_EPISODES
                and self.usable_origins > 0)

    @property
    def why_not(self) -> str:
        from .incremental import MIN_EPISODES
        if not self.baseline_clear:
            return f"BASELINE_INVALID: {self.baseline_reason}"
        if self.episodes < MIN_EPISODES:
            return (f"INSUFFICIENT_EPISODES: {self.episodes} of "
                    f"{MIN_EPISODES}")
        return ""

    def as_dict(self) -> dict:
        return {"target_id": self.target_id,
                "base_rate": round(self.base_rate, 4),
                "usable_origins": self.usable_origins,
                "effective_origins": round(self.effective_origins, 2),
                "episodes": self.episodes,
                "baseline_clear": self.baseline_clear,
                "baseline_reason": self.baseline_reason,
                "mde": self.mde,
                "eligible_for_human_test": self.eligible_for_human_test,
                "why_not": self.why_not}


def assert_origins_declared(origins: Sequence[str],
                            declared: Sequence[str]) -> None:
    """The forecast grid must come from the manifest, not from a pattern.

    THE DEFECT THIS CATCHES. `origins = [v for v in panel vintages if
    v.endswith("-15")]` admitted 344 origins where the acquisition planned
    115, because one quarterly series publishes on the fifteenth. An
    experiment must not take its sampling grid from one series' publication
    calendar.
    """
    extra = sorted(set(origins) - set(declared))
    if extra:
        raise BlockDefect(
            f"{len(extra)} origin(s) are not in the declared grid "
            f"(e.g. {extra[:3]}). The grid is declared by the acquisition "
            "manifest; anything else is a pattern match on a date string.")


def assert_per_family_baseline(ladder_by_family: Dict[str, object]) -> None:
    """§11: the ladder is scored per family, never pooled.

    THE DEFECT THIS CATCHES. One logistic fitted across ten families with
    base rates from 0.28 to 0.92 cannot represent any of them, lost to a
    per-fold constant everywhere, and produced a baseline-gate failure that
    was a statement about the harness rather than about the economy.
    """
    if len(ladder_by_family) < 2:
        raise BlockDefect(
            f"the baseline ladder was scored on {len(ladder_by_family)} "
            "family group(s). Families with base rates from 0.28 to 0.92 "
            "cannot share one fit, and a pooled ladder measures the harness.")

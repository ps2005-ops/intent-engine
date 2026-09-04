"""§4/§5/§6/§7/§8: the forward evidence engine.

WHY THIS IS THE HIGHEST-VALUE STREAM NOW
----------------------------------------
Three cycles of historical research reached an honest boundary: the collective
layer was not promoted, and the one replicated observation turned out to be a
property of which origins were sampled. Every remaining historical question is
data-limited, not method-limited.

What is NOT limited is the forward record. Twelve expectations are open, each
a BASE/AUGMENTED pair with identical target, cutoff, horizon and resolution
contract. When they resolve they will be the first evidence about this system
that nobody could have fitted, because it did not exist when the prediction
was made.

So the machinery around them has to be production-grade BEFORE the first one
comes due. A resolver that is wrong on the day the answer arrives cannot be
fixed afterwards without destroying the property that makes the record worth
having.

THE STATE MACHINE, AND WHY SIX STATES
-------------------------------------
    OPEN                    the horizon has not arrived
    ELIGIBLE_FOR_RESOLUTION the horizon HAS arrived and the data is present
    RESOLVED                scored, once, forever
    EXPIRED_UNRESOLVED      the horizon passed and the data never came
    INVALIDATED_DATA        the resolving series was redefined or withdrawn
    BLOCKED_EXTERNAL        the publisher has not released yet

The last three exist so that "we do not know" cannot be quietly recorded as
"we were wrong" or dropped. `EXPIRED_UNRESOLVED` in particular is the state a
lazy implementation would delete, and deleting it is how a track record
becomes a highlight reel.

FIRST RELEASE VERSUS LATEST REVISION
------------------------------------
A contract states WHICH vintage resolves it. If a prediction was about what
the world would print, a later revision is the wrong answer even though it is
a better estimate of the truth. Resolving a first-release contract with a
revised value is the forward-facing twin of the leak that cost this project a
whole panel, and `resolve_one` refuses it.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import forward_ledger as FL
from .vocabulary import EconError, require

CONTRACT = "econ_forward_engine.v1"

OPEN = "OPEN"
ELIGIBLE = "ELIGIBLE_FOR_RESOLUTION"
RESOLVED = "RESOLVED"
EXPIRED = "EXPIRED_UNRESOLVED"
INVALIDATED = "INVALIDATED_DATA"
BLOCKED = "BLOCKED_EXTERNAL"
STATES = (OPEN, ELIGIBLE, RESOLVED, EXPIRED, INVALIDATED, BLOCKED)

#: A resolution may only move along these edges. Anything else is a rewrite.
TRANSITIONS = {
    OPEN: (ELIGIBLE, BLOCKED, EXPIRED, INVALIDATED),
    ELIGIBLE: (RESOLVED, INVALIDATED, BLOCKED),
    BLOCKED: (ELIGIBLE, EXPIRED, INVALIDATED),
    RESOLVED: (),
    EXPIRED: (),
    INVALIDATED: (),
}

FIRST_RELEASE = "FIRST_RELEASE"
LATEST_REVISION = "LATEST_REVISION"
VINTAGE_POLICIES = (FIRST_RELEASE, LATEST_REVISION)

#: How long after the horizon we keep waiting before calling it expired.
#: A quarterly series published with a ten-week lag needs more slack than a
#: daily one, and 120 days covers the slowest publisher in this registry.
GRACE_DAYS = 120


class ResolutionRefused(EconError):
    """A resolution was attempted that the contract does not permit."""


def _d(s: str) -> _dt.date:
    return _dt.date(int(s[:4]), int(s[5:7]), int(s[8:10]))


@dataclass(frozen=True)
class ResolutionContract:
    """Exactly how one expectation gets scored. Fixed when it opens."""

    series_id: str
    #: The origin value the outcome is compared against.
    baseline_period: str
    #: UP means the series is higher at the horizon than at the baseline.
    direction: str
    horizon_days: int
    vintage_policy: str
    #: The vintage at or after which the resolving figure may be read. For a
    #: FIRST_RELEASE contract this is the release date of the horizon period.
    resolves_from: str

    def __post_init__(self) -> None:
        require(self.vintage_policy in VINTAGE_POLICIES,
                f"unknown vintage policy {self.vintage_policy!r}")
        require(self.direction in ("UP", "DOWN"),
                f"unknown direction {self.direction!r}")
        require(self.horizon_days > 0, "a forecast looks forward")

    def as_dict(self) -> dict:
        return {"series_id": self.series_id,
                "baseline_period": self.baseline_period,
                "direction": self.direction,
                "horizon_days": self.horizon_days,
                "vintage_policy": self.vintage_policy,
                "resolves_from": self.resolves_from}


def contract_from(record: dict) -> Optional[ResolutionContract]:
    c = record.get("resolution_contract")
    if not c:
        return None
    return ResolutionContract(**c)


def state_of(record: dict, *, at: str, panel=None) -> str:
    """Where this expectation stands right now.

    Reads the RECORD and the WORLD; never guesses. An expectation whose
    horizon has arrived but whose resolving figure has not been published is
    BLOCKED_EXTERNAL, which is a fact about the publisher and not a failure
    of the prediction.
    """
    if record.get("outcome") in (RESOLVED, "CORRECT", "INCORRECT"):
        return RESOLVED
    if record.get("outcome") in (EXPIRED, INVALIDATED, BLOCKED):
        return record["outcome"]
    expires = record.get("expires_at", "")
    if at < expires:
        return OPEN
    con = contract_from(record)
    if con is None:
        return BLOCKED
    if panel is None:
        return BLOCKED
    if _readable(panel, con, at) is None:
        deadline = (_d(expires) + _dt.timedelta(days=GRACE_DAYS)).isoformat()
        return EXPIRED if at > deadline else BLOCKED
    return ELIGIBLE


def _readable(panel, con: ResolutionContract, at: str):
    """The resolving value, under this contract's vintage policy.

    FIRST_RELEASE reads the EARLIEST stored vintage of the horizon period.
    LATEST_REVISION reads the newest one knowable by `at`. Using the second
    where the first was contracted is the forward twin of a hindsight leak.
    """
    periods = panel._periods(con.series_id)
    horizon_period = _horizon_period(con)
    revisions = periods.get(horizon_period)
    if not revisions:
        return None
    if con.vintage_policy == FIRST_RELEASE:
        first = revisions[0]
        return first.value if first.vintage_at <= at else None
    best = None
    for c in revisions:
        if c.vintage_at <= at:
            best = c
    return best.value if best is not None else None


def _horizon_period(con: ResolutionContract) -> str:
    """The period the outcome is read at."""
    base = _d(con.baseline_period)
    total = base.month - 1 + max(1, con.horizon_days // 30)
    y, m = base.year + total // 12, total % 12 + 1
    return f"{y}-{m:02d}-01"


def resolve_one(record: dict, *, panel, at: str) -> Optional[dict]:
    """Score one expectation, or explain why not. Never mutates the input."""
    st = state_of(record, at=at, panel=panel)
    if st != ELIGIBLE:
        return None
    con = contract_from(record)
    got = _readable(panel, con, at)
    if got is None:
        return None
    baseline = panel._periods(con.series_id).get(con.baseline_period)
    if not baseline:
        return None
    base_value = baseline[0].value if con.vintage_policy == FIRST_RELEASE \
        else baseline[-1].value
    rose = got > base_value
    correct = rose if con.direction == "UP" else (not rose)
    p = float(record.get("confidence", 0.5))
    # The probability was of the STATED direction, so the Brier score is
    # against 1.0 when the stated direction happened.
    y = 1.0 if correct else 0.0
    return {
        **{k: v for k, v in record.items()
           if k not in ("outcome", "resolved_at", "observed_value")},
        "outcome": RESOLVED, "resolved_at": at,
        "observed_value": got, "baseline_value": base_value,
        "realised_direction": "UP" if rose else "DOWN",
        "correct": correct,
        "squared_error": round((p - y) ** 2, 6),
        "log_loss": round(-(y * _safe_log(p) + (1 - y) * _safe_log(1 - p)), 6),
        "absolute_error": round(abs(p - y), 6),
        "resolution_note": (
            f"read {con.series_id} {_horizon_period(con)} under "
            f"{con.vintage_policy} at {at}: {got} against a baseline of "
            f"{base_value} at {con.baseline_period}"),
    }


def _safe_log(x: float) -> float:
    import math
    return math.log(max(1e-12, min(1.0 - 1e-12, x)))


def assert_transition(frm: str, to: str) -> None:
    require(frm in STATES and to in STATES,
            f"unknown state in transition {frm!r} -> {to!r}")
    if to not in TRANSITIONS[frm]:
        raise ResolutionRefused(
            f"{frm} -> {to} is not a permitted transition. A RESOLVED "
            "expectation is final; an EXPIRED one stays expired. Corrections "
            "append a superseding record, they do not move a terminal state.")


# =============================================================================
# §7 FORWARD SAMPLE QUALITY
# =============================================================================

@dataclass(frozen=True)
class ForwardSample:
    """What a set of resolved forward predictions is actually worth.

    The same discipline the historical programme learned the hard way: twenty
    correlated forecasts are not twenty successes. Every number the forward
    record reports carries all five.
    """

    raw_predictions: int
    unique_origins: int
    target_families: int
    overlapping_horizons: int
    regimes: int
    independent_episodes: int

    def headline(self) -> str:
        return (f"{self.raw_predictions} predictions / "
                f"{self.unique_origins} origins / "
                f"{self.target_families} families / "
                f"{self.independent_episodes} episodes")

    def as_dict(self) -> dict:
        return {"raw_predictions": self.raw_predictions,
                "unique_origins": self.unique_origins,
                "target_families": self.target_families,
                "overlapping_horizons": self.overlapping_horizons,
                "regimes": self.regimes,
                "independent_episodes": self.independent_episodes,
                "headline": self.headline()}


def forward_sample(records: Sequence[dict]) -> ForwardSample:
    from .power import count_episodes
    origins = [r.get("information_cutoff", "") for r in records]
    fams = {r.get("family") or r.get("quantity", "") for r in records}
    horizons = {r.get("horizon_days") for r in records}
    regimes = {r.get("regime", "UNKNOWN") for r in records}
    return ForwardSample(
        raw_predictions=len(records),
        unique_origins=len(set(o for o in origins if o)),
        target_families=len(fams),
        overlapping_horizons=len(horizons),
        regimes=len(regimes),
        independent_episodes=count_episodes(sorted(set(origins))) if origins
        else 0)


# =============================================================================
# §8 THE CALIBRATION LADDER
# =============================================================================
# Thresholds fixed HERE, before a single forward prediction has resolved, so
# that no stage can be reached by choosing its requirement afterwards.

PRE_CALIBRATION = "PRE_CALIBRATION"
EARLY_CALIBRATION = "EARLY_CALIBRATION"
CALIBRATION_ESTABLISHING = "CALIBRATION_ESTABLISHING"
CALIBRATED = "CALIBRATED"
LADDER = (PRE_CALIBRATION, EARLY_CALIBRATION, CALIBRATION_ESTABLISHING,
          CALIBRATED)

LADDER_REQUIREMENTS = {
    EARLY_CALIBRATION: {
        "resolved": 10, "origins": 4, "families": 2, "episodes": 1,
        "reports": "counts and per-prediction outcomes only. No aggregate "
                   "score of any kind."},
    CALIBRATION_ESTABLISHING: {
        "resolved": 30, "origins": 12, "families": 3, "episodes": 2,
        "reports": "descriptive Brier and directional counts, always beside "
                   "the five sample numbers, never as a headline percentage."},
    CALIBRATED: {
        "resolved": 60, "origins": 24, "families": 4, "episodes": 3,
        "reports": "calibration curves and a BASE-versus-AUGMENTED verdict."},
}


def ladder_stage(records: Sequence[dict]) -> dict:
    """Which rung the forward record has reached, and what it may report."""
    resolved = [r for r in records if r.get("outcome") == RESOLVED]
    s = forward_sample(resolved)
    stage = PRE_CALIBRATION
    for candidate in (EARLY_CALIBRATION, CALIBRATION_ESTABLISHING,
                      CALIBRATED):
        need = LADDER_REQUIREMENTS[candidate]
        if (len(resolved) >= need["resolved"]
                and s.unique_origins >= need["origins"]
                and s.target_families >= need["families"]
                and s.independent_episodes >= need["episodes"]):
            stage = candidate
        else:
            break
    nxt = (LADDER[LADDER.index(stage) + 1]
           if LADDER.index(stage) + 1 < len(LADDER) else None)
    gap = {}
    if nxt:
        need = LADDER_REQUIREMENTS[nxt]
        gap = {"resolved": max(0, need["resolved"] - len(resolved)),
               "origins": max(0, need["origins"] - s.unique_origins),
               "families": max(0, need["families"] - s.target_families),
               "episodes": max(0, need["episodes"] - s.independent_episodes)}
    return {"contract": CONTRACT, "stage": stage,
            "may_report": (LADDER_REQUIREMENTS.get(stage, {})
                           .get("reports", "nothing but the count of open "
                                           "and resolved expectations")),
            "resolved": len(resolved), "sample": s.as_dict(),
            "next_stage": nxt, "gap_to_next": gap,
            "requirements": LADDER_REQUIREMENTS,
            "frozen_before_any_resolution": True}


# =============================================================================
# §6 THE TOURNAMENT
# =============================================================================

def tournament(records: Sequence[dict]) -> dict:
    """BASE against AUGMENTED, on matched pairs only.

    A pair is matched when both sides share target, cutoff, horizon and
    contract. Scoring an unmatched side would compare two models on different
    questions, which is how a tournament becomes a selection.
    """
    by_key: Dict[str, Dict[str, dict]] = {}
    for r in records:
        q = r.get("quantity", "")
        model = r.get("model") or ("AUGMENTED" if "AUGMENTED" in q else "BASE")
        key = "|".join([str(r.get("family") or q.rsplit("/", 1)[0]),
                        r.get("information_cutoff", ""),
                        str(r.get("horizon_days"))])
        by_key.setdefault(key, {})[model] = r
    matched = {k: v for k, v in by_key.items()
               if "BASE" in v and "AUGMENTED" in v}
    resolved = {k: v for k, v in matched.items()
                if all(x.get("outcome") == RESOLVED for x in v.values())}
    out = {"pairs": len(matched), "resolved_pairs": len(resolved),
           "unmatched": len(by_key) - len(matched)}
    if not resolved:
        out["verdict"] = "AWAITING_RESOLUTION"
        out["why"] = (f"{len(matched)} matched pairs are open. A tournament "
                      "with no resolved pair has no result, and reporting "
                      "one would be reporting the historical backtest again "
                      "under a new name.")
        return out
    def agg(model, fn):
        xs = [v[model][fn] for v in resolved.values() if fn in v[model]]
        return round(sum(xs) / len(xs), 6) if xs else None
    out.update({
        "base": {m: agg("BASE", m) for m in
                 ("squared_error", "log_loss", "absolute_error")},
        "augmented": {m: agg("AUGMENTED", m) for m in
                      ("squared_error", "log_loss", "absolute_error")},
        "base_correct": sum(1 for v in resolved.values()
                            if v["BASE"].get("correct")),
        "augmented_correct": sum(1 for v in resolved.values()
                                 if v["AUGMENTED"].get("correct")),
        "sample": forward_sample(
            [x for v in resolved.values() for x in v.values()]).as_dict(),
    })
    stage = ladder_stage([x for v in resolved.values() for x in v.values()])
    out["calibration_stage"] = stage["stage"]
    out["verdict"] = ("DESCRIPTIVE_ONLY" if stage["stage"] in
                      (PRE_CALIBRATION, EARLY_CALIBRATION) else "SCORED")
    return out

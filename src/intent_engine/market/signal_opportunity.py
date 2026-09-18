"""Signal opportunity — separating "correctly quiet" from "broken".

THE QUESTION THIS ANSWERS
-------------------------
Five operating days produced `signal_fired = 0.00` with standard deviation
0.00. Day 16 classified that as *stable at zero* and then said, correctly, that
it could not yet be called a defect: a momentum baseline measured at 0.500
declining to fire may be the honest behaviour, or the signal may be broken, and
"it never fired" is identical in both worlds.

The distinguishing question is not *did the signal fire*. It is:

    Should a qualifying opportunity have existed at all?

That question is answerable at decision time, from information available at
decision time, and it splits one uninformative number into a 2x2 that says
something.

THE PRE-REGISTERED DEFINITION (v1)
----------------------------------
At `as_of`, for (instrument, horizon), a QUALIFYING OPPORTUNITY exists iff:

  1. at least `MIN_BARS` closes exist dated on or before `as_of`; and
  2. trailing realised volatility over the last `LOOKBACK` closes, scaled to
     the horizon (sigma * sqrt(horizon_days)), is at least `MIN_ABS_RETURN`.

In words: *does this instrument move enough over this horizon for a directional
call to be gradable rather than a coin flip on noise?*

WHY THIS IS NOT THE FIRING RULE RESTATED
----------------------------------------
It would be worthless if it were. `baseline_momentum.v1` fires on trailing
DIRECTION (|trailing return| >= MIN_ABS_RETURN). This condition is about
FEASIBLE MAGNITUDE (realised volatility over the horizon). An instrument can
easily be volatile with no net drift -- opportunity present, signal silent --
and it can drift steadily while barely moving day to day. The two conditions
are independent enough that all four cells are reachable, which is the only
reason the 2x2 carries information.

WHERE THE PARAMETERS CAME FROM
------------------------------
`MIN_ABS_RETURN` is imported from `signals.py`, where it has been fixed since
Phase 2 day 1. `LOOKBACK` and `MIN_BARS` are the standard 20-session month.
**None of the three was chosen by looking at outcomes**, which is the specific
guarantee that makes this pre-registration meaningful rather than decorative.
Changing any of them requires a new version string and a new pre-registration;
`v1` results stand as recorded.

THE LOOKAHEAD BOUNDARY
----------------------
Two things are kept strictly apart:

  * **Observable at decision time.** Uses only closes dated <= as_of. This is
    what labels a live decision. It NEVER consults a future return.
  * **Resolved outcome.** Attached only after the horizon has fully elapsed,
    and used only for evaluation.

A missed-opportunity CANDIDATE stays a candidate precisely because confirming
it requires the outcome, and the outcome is not available when the decision is
made. Collapsing those two would produce a system that labels its own past
decisions using information it did not have -- which is the most flattering
possible bug and the hardest to see afterwards.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

from intent_engine.market.signals import MIN_ABS_RETURN

# The pre-registered definition's identity. It is stamped on every record, so a
# later analysis can ask "under which definition?" and get an answer about the
# rule that was actually in force rather than whatever the file says by then.
DEFINITION = "volatility_feasibility.v1"

LOOKBACK = 20          # sessions of realised volatility
MIN_BARS = 20          # below this the volatility estimate is not worth having
HORIZON_DAYS = 21      # matches the baseline signal's horizon

# --- decision-time states ---------------------------------------------------
CORRECTLY_QUIET = "CORRECTLY_QUIET"
MISSED_OPPORTUNITY_CANDIDATE = "MISSED_OPPORTUNITY_CANDIDATE"
CORRECT_FIRE = "CORRECT_FIRE"
FALSE_FIRE_CANDIDATE = "FALSE_FIRE_CANDIDATE"
UNMEASURABLE = "UNMEASURABLE"

# --- outcome states ---------------------------------------------------------
UNRESOLVED = "UNRESOLVED"
RESOLVED = "RESOLVED"

STATES = (CORRECTLY_QUIET, MISSED_OPPORTUNITY_CANDIDATE, CORRECT_FIRE,
          FALSE_FIRE_CANDIDATE, UNMEASURABLE, UNRESOLVED)


def _returns(closes: Sequence[float]) -> List[float]:
    return [(b - a) / a for a, b in zip(closes, closes[1:]) if a]


def _volatility(closes: Sequence[float]) -> Optional[float]:
    rets = _returns(closes)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var)


@dataclass(frozen=True)
class Observable:
    """What was knowable at `as_of`. Contains no future information, by
    construction: `closes_used` is filtered on date before anything is
    computed."""
    definition: str
    as_of: str
    horizon_days: int
    bars_available: int
    volatility: Optional[float]
    expected_move: Optional[float]
    threshold: float
    qualifies: bool
    measurable: bool
    reason: str

    def as_dict(self) -> dict:
        return {"definition": self.definition, "as_of": self.as_of,
                "horizon_days": self.horizon_days,
                "bars_available": self.bars_available,
                "volatility": self.volatility,
                "expected_move": self.expected_move,
                "threshold": self.threshold, "qualifies": self.qualifies,
                "measurable": self.measurable, "reason": self.reason}


def observable_opportunity(closes: Dict[str, float], *, as_of: str,
                           horizon_days: int = HORIZON_DAYS) -> Observable:
    """Was a qualifying opportunity visible at `as_of`?

    `closes` may legitimately contain dates after `as_of` -- a live price
    series is fetched whole and reused across replay dates. The filter below is
    the single line that makes this point-in-time, and a regression test proves
    that adding future bars cannot change the answer.
    """
    usable = sorted((d, v) for d, v in (closes or {}).items()
                    if d <= as_of[:10] and v)
    bars = len(usable)
    if bars < MIN_BARS:
        return Observable(
            DEFINITION, as_of, horizon_days, bars, None, None,
            MIN_ABS_RETURN, False, False,
            f"{bars} bars on or before {as_of[:10]}; {MIN_BARS} required "
            f"before a volatility estimate is worth reading")

    window = [v for _, v in usable[-LOOKBACK:]]
    vol = _volatility(window)
    if vol is None:  # pragma: no cover - guarded by MIN_BARS above
        return Observable(DEFINITION, as_of, horizon_days, bars, None, None,
                          MIN_ABS_RETURN, False, False,
                          "volatility could not be estimated")
    expected = vol * math.sqrt(max(horizon_days, 1))
    qualifies = expected >= MIN_ABS_RETURN
    return Observable(
        DEFINITION, as_of, horizon_days, bars, round(vol, 6),
        round(expected, 6), MIN_ABS_RETURN, qualifies, True,
        (f"expected {horizon_days}d move {expected:.2%} "
         f"{'>=' if qualifies else '<'} {MIN_ABS_RETURN:.2%} noise floor"))


def label(observable: Observable, *, fired: bool) -> str:
    """The 2x2. Decision-time only -- no outcome is consulted."""
    if not observable.measurable:
        return UNMEASURABLE
    if observable.qualifies:
        return CORRECT_FIRE if fired else MISSED_OPPORTUNITY_CANDIDATE
    return FALSE_FIRE_CANDIDATE if fired else CORRECTLY_QUIET


@dataclass(frozen=True)
class AuditRecord:
    """One company at the signal-evaluated stage, fully accounted for.

    Every field the counterfactual audit requires. It exists so the question
    "why was the engine silent about this company on this day?" has a recorded
    answer rather than a reconstruction.
    """
    as_of: str
    cycle_id: str
    company_id: str
    instrument: str
    strategic_view: str
    evidence_ids: tuple
    signal: str
    signal_version: str
    inputs: dict
    threshold: float
    raw_value: Optional[float]
    fired: bool
    fire_reason: str
    opportunity_state: str
    opportunity: dict
    outcome_state: str = UNRESOLVED
    realized_return: Optional[float] = None
    resolved_at: str = ""
    data_unavailable: bool = False
    calibration_eligible: bool = False

    def as_dict(self) -> dict:
        return {"as_of": self.as_of, "cycle_id": self.cycle_id,
                "company_id": self.company_id, "instrument": self.instrument,
                "strategic_view": self.strategic_view,
                "evidence_ids": list(self.evidence_ids),
                "signal": self.signal, "signal_version": self.signal_version,
                "inputs": dict(self.inputs), "threshold": self.threshold,
                "raw_value": self.raw_value, "fired": self.fired,
                "fire_reason": self.fire_reason,
                "opportunity_state": self.opportunity_state,
                "opportunity": dict(self.opportunity),
                "outcome_state": self.outcome_state,
                "realized_return": self.realized_return,
                "resolved_at": self.resolved_at,
                "data_unavailable": self.data_unavailable,
                "calibration_eligible": self.calibration_eligible}


def horizon_end(as_of: str, horizon_days: int = HORIZON_DAYS) -> str:
    return (date.fromisoformat(as_of[:10])
            + timedelta(days=horizon_days)).isoformat()


def resolve_outcome(record: AuditRecord, closes: Dict[str, float], *,
                    today: str) -> AuditRecord:
    """Attach the realised outcome — ONLY once the horizon has fully elapsed.

    Three refusals, each one a lookahead guard:

    * the horizon end is in the future -> stays UNRESOLVED. Grading an
      unelapsed horizon is the textbook version of this bug.
    * no close at or before the horizon end -> stays UNRESOLVED, never filled
      from a later bar.
    * an already-resolved record is returned untouched, so a rerun cannot
      re-grade an outcome against a different (later) price.
    """
    if record.outcome_state == RESOLVED:
        return record
    end = horizon_end(record.as_of, record.opportunity.get(
        "horizon_days", HORIZON_DAYS))
    if end > today[:10]:
        return record
    usable = sorted((d, v) for d, v in (closes or {}).items()
                    if d <= end and v)
    entry = [v for d, v in usable if d <= record.as_of[:10]]
    if not usable or not entry:
        return record
    exit_price = usable[-1][1]
    entry_price = entry[-1]
    if not entry_price:  # pragma: no cover - filtered above
        return record
    realized = (exit_price - entry_price) / entry_price
    return AuditRecord(
        as_of=record.as_of, cycle_id=record.cycle_id,
        company_id=record.company_id, instrument=record.instrument,
        strategic_view=record.strategic_view, evidence_ids=record.evidence_ids,
        signal=record.signal, signal_version=record.signal_version,
        inputs=record.inputs, threshold=record.threshold,
        raw_value=record.raw_value, fired=record.fired,
        fire_reason=record.fire_reason,
        # THE LABEL IS NOT RECOMPUTED. It was decided at as_of from
        # decision-time information and stays exactly as it was. Only the
        # outcome fields are filled in.
        opportunity_state=record.opportunity_state,
        opportunity=record.opportunity, outcome_state=RESOLVED,
        realized_return=round(realized, 6), resolved_at=end,
        data_unavailable=record.data_unavailable, calibration_eligible=True)


def confirmed_miss(record: AuditRecord) -> Optional[bool]:
    """Did a MISSED_OPPORTUNITY_CANDIDATE turn out to be a real miss?

    Evaluation only, and it returns None until the outcome exists. This is the
    ONLY place a realised return touches an opportunity judgement, and it never
    writes back into `opportunity_state` -- the live label stays what it was.
    """
    if record.opportunity_state != MISSED_OPPORTUNITY_CANDIDATE:
        return None
    if record.outcome_state != RESOLVED or record.realized_return is None:
        return None
    return abs(record.realized_return) >= MIN_ABS_RETURN


def summarise(records: Sequence[AuditRecord]) -> dict:
    """Counts per state, plus the confirmation tallies that need outcomes.

    Reports UNMEASURABLE rather than 0 when nothing has resolved. A confirmed
    rate over zero resolutions is not a small number, it is not a number.
    """
    counts = {s: 0 for s in
              (CORRECTLY_QUIET, MISSED_OPPORTUNITY_CANDIDATE, CORRECT_FIRE,
               FALSE_FIRE_CANDIDATE, UNMEASURABLE)}
    resolved = unresolved = 0
    confirmed = denominator = 0
    for record in records:
        counts[record.opportunity_state] = counts.get(
            record.opportunity_state, 0) + 1
        if record.outcome_state == RESOLVED:
            resolved += 1
        else:
            unresolved += 1
        verdict = confirmed_miss(record)
        if verdict is not None:
            denominator += 1
            confirmed += int(verdict)
    return {"definition": DEFINITION, "evaluated": len(records),
            "states": counts, "resolved": resolved, "unresolved": unresolved,
            "confirmed_misses": confirmed if denominator else None,
            "confirmable_misses": denominator,
            "confirmed_miss_rate": (round(confirmed / denominator, 3)
                                    if denominator else None),
            "confirmed_miss_rate_note":
                None if denominator else
                "UNMEASURABLE — no candidate has completed its horizon"}


def render(summary: dict) -> str:
    lines = [f"definition            : {summary['definition']}",
             f"signal-evaluated      : {summary['evaluated']}"]
    for state, count in summary["states"].items():
        lines.append(f"  {state:<32}{count:>5}")
    lines.append(f"resolved / unresolved : {summary['resolved']} / "
                 f"{summary['unresolved']}")
    rate = summary["confirmed_miss_rate"]
    lines.append("confirmed miss rate   : " + (
        f"{rate:.0%} ({summary['confirmed_misses']}/"
        f"{summary['confirmable_misses']})" if rate is not None
        else summary["confirmed_miss_rate_note"]))
    return "\n".join(lines)

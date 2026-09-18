"""When a belief stops being current — and the events that say so.

WHY THIS IS NOT `belief_maturity`
---------------------------------
`belief_maturity` is a VIEW: recompute it and it agrees with the ledger.
Decay is the opposite kind of thing. "This belief went stale on 2026-11-14"
is a fact about a moment, and a view recomputed next March cannot tell you
that it *had already* gone stale in November and was revalidated in January.
So decay writes append-only LIFECYCLE EVENTS, and the view keeps deriving.

The two never disagree because they read the same clock; they answer
different questions. Maturity answers "what is this belief's standing now".
Decay answers "what happened to it, and when".

THE THREE STATES ARE NOT INTERCHANGEABLE
----------------------------------------
    WEAKENING  new evidence argued AGAINST the belief. Owned by
               `belief_maturity`, never produced here. The engine learned
               something.

    STALE      evidence has aged past the belief's OWN refresh cadence with
               nothing arguing either way. The engine learned nothing; time
               passed. Relying on it is now a choice.

    RETIRED    no longer operationally valid — stale well past its cadence
               with no revalidation, or the conditions it was declared under
               have structurally changed.

Contradiction outranks time, always. A belief that was argued against is
WEAKENING however old it is, because something happened to it; calling that
"stale" would erase the test. And a belief that merely aged is never
CONTRADICTED, because nothing argued. Both directions are proved.

WHY THERE IS NO GLOBAL "90 DAYS"
--------------------------------
`demand_strengthening` commits to the next reported revenue figure — one
quarter, padded, 120 days. `capacity_expansion` commits to capital actually
being spent — 365 days. A single global threshold either declares the capital
belief stale three times before its own test could resolve, or lets the
demand belief sit untested for a year. The belief already carries its family's
cadence in `review_interval_days`, written at declaration from the family's
`window_days`. Decay reads THAT. There is no module-level day count that
applies to every belief, and adding one would be the bug.

THE GATE THAT MAKES ZERO THE HONEST ANSWER
------------------------------------------
A belief is not eligible for decay until its own preregistered expectation
window has CLOSED. Before that, silence is exactly what was predicted: the
test has not had its chance yet. This is why the real ledger reports zero
stale beliefs and why that zero is a finding rather than a gap — the oldest
belief is days old against windows of 120 to 365 days. Forcing a non-zero
number out of it would require ignoring the engine's own preregistration.
"""
from __future__ import annotations

import collections
import datetime as _dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "knowledge_decay.v1"

# --- the event vocabulary ---------------------------------------------------
STALE = "belief.stale"
REVALIDATED = "belief.revalidated"
RETIRED = "belief.retired"
EVENT_KINDS = (STALE, REVALIDATED, RETIRED)

#: Retirement is a MULTIPLE of the belief's own cadence, never a fixed date.
#: Two full refresh windows with nothing arguing either way means the belief
#: outlived two chances to be tested, which is a different claim from "it is
#: old" and the only one that justifies dropping it.
RETIRE_AFTER_INTERVALS = 2

#: Used only when a belief row carries no cadence of its own. Not a policy —
#: a fallback for malformed input, and it is reported as such.
FALLBACK_INTERVAL_DAYS = 120

INFORMATIVE = frozenset({"CONFIRMED", "PARTIALLY_CONFIRMED", "CONTRADICTED"})

# --- why a belief decayed ---------------------------------------------------
AGED_PAST_CADENCE = "AGED_PAST_CADENCE"
REGIME_TRANSITION = "REGIME_TRANSITION"
STRUCTURAL_CHANGE = "STRUCTURAL_CHANGE"

# --- why a belief did NOT decay --------------------------------------------
WINDOW_OPEN = "WINDOW_OPEN"
TESTED = "TESTED"
WITHIN_CADENCE = "WITHIN_CADENCE"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
ALREADY_RETIRED = "ALREADY_RETIRED"


def _date(value: object) -> Optional[_dt.date]:
    text = str(value or "")[:10]
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class LifecycleEvent:
    """One append-only statement about a belief's currency.

    `event_id` is deterministic on (belief, kind, date) so a decay pass that
    runs twice in a day writes one event, matching every other idempotent
    record in this ledger.
    """
    event_id: str
    event: str
    belief_id: str
    subject: str
    proposition: str
    at: str
    reason_code: str
    reason: str
    cadence_days: int
    days_since_anchor: int
    anchor: str
    what_would_revalidate: str

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "event_id": self.event_id,
            "event": self.event, "belief_id": self.belief_id,
            "subject": self.subject, "proposition": self.proposition,
            "at": self.at, "reason_code": self.reason_code,
            "reason": self.reason, "cadence_days": self.cadence_days,
            "days_since_anchor": self.days_since_anchor,
            "anchor": self.anchor,
            "what_would_revalidate": self.what_would_revalidate,
        }


@dataclass(frozen=True)
class Assessment:
    """What decay concluded about one belief, including the negatives.

    The refusals are returned, not dropped. "37 beliefs were not stale
    because their expectation window is still open" is the finding; a bare
    `stale: 0` is the number this project has repeatedly mistaken for a gap.
    """
    belief_id: str
    subject: str
    eligible: bool
    outcome: str            # "" when nothing changed
    reason_code: str
    reason: str
    cadence_days: int
    days_since_anchor: Optional[int]
    window_closes: str
    decays_on: str          # the date it WOULD go stale, if nothing happens
    anchor: str = ""        # last thing that argued, or the declaration

    def as_dict(self) -> dict:
        return {
            "belief_id": self.belief_id, "subject": self.subject,
            "eligible_for_decay": self.eligible, "outcome": self.outcome,
            "reason_code": self.reason_code, "reason": self.reason,
            "cadence_days": self.cadence_days,
            "days_since_anchor": self.days_since_anchor,
            "window_closes": self.window_closes, "decays_on": self.decays_on,
            "anchor": self.anchor,
        }


def _cadence(belief: dict) -> int:
    raw = belief.get("review_interval_days")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return FALLBACK_INTERVAL_DAYS
    return days if days > 0 else FALLBACK_INTERVAL_DAYS


def assess(rows: Sequence[dict], *, as_of: str,
           regime_changes: Sequence[dict] = ()) -> Tuple[Assessment, ...]:
    """Decide, for every belief in the ledger, whether it is still current.

    `regime_changes` are dated statements that the conditions a belief was
    declared under no longer hold — each `{"subject": ..., "at": ...,
    "what_changed": ...}`. A regime transition makes a belief eligible
    IMMEDIATELY, whatever its age, because the clock was never the point: the
    ground the belief stood on moved.
    """
    today = _date(as_of)
    beliefs = [r for r in rows if r.get("record") == "belief"]

    # A belief's own preregistered window, and its own informative tests.
    window_of: Dict[str, str] = {}
    for row in rows:
        if row.get("record") != "expectation":
            continue
        bid = str(row.get("hypothesis_id") or "")
        end = str(row.get("evaluation_window_ends") or "")[:10]
        if bid and end:
            # The LAST window to close is the one that matters: a belief with
            # two open tests is not untested.
            window_of[bid] = max(window_of.get(bid, ""), end)

    tests: Dict[str, List[dict]] = collections.defaultdict(list)
    for row in rows:
        if row.get("record") != "reconciliation":
            continue
        if row.get("outcome") not in INFORMATIVE:
            continue
        bid = str(row.get("hypothesis_id") or "")
        if bid:
            tests[bid].append(row)

    changed_subjects: Dict[str, dict] = {}
    for change in regime_changes:
        subject = str(change.get("subject") or "")
        if subject:
            changed_subjects[subject] = dict(change)

    out: List[Assessment] = []
    for belief in beliefs:
        out.append(_assess_one(belief, today=today, window_of=window_of,
                               tests=tests, changed=changed_subjects))
    return tuple(out)


def _assess_one(belief: dict, *, today: Optional[_dt.date],
                window_of: Dict[str, str], tests: Dict[str, List[dict]],
                changed: Dict[str, dict]) -> Assessment:
    bid = str(belief.get("belief_id") or "")
    subject = str(belief.get("subject") or "")
    cadence = _cadence(belief)

    my_tests = tests.get(bid, [])
    test_dates = [d for d in (_date(t.get("evaluated_at")) for t in my_tests)
                  if d]
    declared = _date(belief.get("last_updated"))
    validated = _date(belief.get("last_validated"))

    # The clock restarts on the most recent thing that ARGUED. Declaration is
    # the floor, not the anchor, because a belief tested last week is fresh
    # however long ago it was declared.
    anchor_date = max([d for d in ([declared, validated] + test_dates) if d],
                      default=None)
    anchor = anchor_date.isoformat() if anchor_date else ""
    since = (today - anchor_date).days if today and anchor_date else None

    window = window_of.get(bid, "")
    window_closed = bool(window and today and
                         _date(window) and _date(window) < today)
    decays_on = ""
    if anchor_date:
        earliest = anchor_date + _dt.timedelta(days=cadence)
        window_end = _date(window)
        if window_end and window_end > earliest:
            earliest = window_end
        decays_on = earliest.isoformat()

    if str(belief.get("lifecycle_state") or "") == "RETIRED":
        return Assessment(bid, subject, False, "", ALREADY_RETIRED,
                          "the belief is already retired", cadence, since,
                          window, "", anchor)
    if not belief.get("decay_eligible", True):
        return Assessment(bid, subject, False, "", NOT_ELIGIBLE,
                          "the belief is declared not decay-eligible",
                          cadence, since, window, "", anchor)

    # --- regime transition: eligibility without waiting for the clock ------
    change = changed.get(subject)
    if change and _date(change.get("at")) and anchor_date and \
            _date(change.get("at")) >= anchor_date:
        what = str(change.get("what_changed") or "the operating regime")
        return Assessment(
            bid, subject, True, STALE, REGIME_TRANSITION,
            f"{what} changed on {str(change.get('at'))[:10]}, after the "
            f"evidence this belief rests on; its conditions no longer hold "
            f"whatever its age",
            cadence, since, window, decays_on, anchor)

    # --- contradiction outranks time, always -------------------------------
    if my_tests:
        return Assessment(
            bid, subject, False, "", TESTED,
            f"{len(my_tests)} informative test(s); evidence argued about "
            f"this belief, which is the opposite of nothing happening",
            cadence, since, window, decays_on, anchor)

    # --- the gate: an open window is a prediction, not a silence -----------
    if window and not window_closed:
        return Assessment(
            bid, subject, False, "", WINDOW_OPEN,
            f"its preregistered window runs to {window}; the test has not "
            f"had its chance yet",
            cadence, since, window, decays_on, anchor)

    if since is None or since < cadence:
        return Assessment(
            bid, subject, False, "", WITHIN_CADENCE,
            f"{since} day(s) since last support against its family's "
            f"{cadence}-day refresh cadence",
            cadence, since, window, decays_on, anchor)

    if since >= cadence * RETIRE_AFTER_INTERVALS:
        return Assessment(
            bid, subject, True, RETIRED, AGED_PAST_CADENCE,
            f"{since} days without support across "
            f"{RETIRE_AFTER_INTERVALS} full {cadence}-day refresh windows; "
            f"it outlived two chances to be tested",
            cadence, since, window, decays_on, anchor)

    return Assessment(
        bid, subject, True, STALE, AGED_PAST_CADENCE,
        f"{since} days without support past its family's {cadence}-day "
        f"refresh cadence, and its expectation window closed on {window} "
        f"without resolving",
        cadence, since, window, decays_on, anchor)


def events(assessments: Sequence[Assessment], *, as_of: str,
           prior_events: Sequence[dict] = ()) -> Tuple[LifecycleEvent, ...]:
    """Turn conclusions into append-only events, emitting each state once.

    A belief that was already marked stale and is still stale produces
    nothing: the event log records TRANSITIONS. A belief marked stale that
    now has support produces `belief.revalidated` — which is the only way
    back, and it is driven by evidence rather than by a rewrite.
    """
    standing: Dict[str, str] = {}
    for row in sorted(prior_events, key=lambda r: str(r.get("at") or "")):
        if row.get("event") in EVENT_KINDS:
            standing[str(row.get("belief_id") or "")] = str(row["event"])

    out: List[LifecycleEvent] = []
    for assessment in assessments:
        was = standing.get(assessment.belief_id, "")
        now = assessment.outcome
        if was == RETIRED:
            continue                       # retirement is terminal
        if now and now != was:
            out.append(_event(now, assessment, as_of))
        elif not now and was == STALE:
            out.append(_event(REVALIDATED, assessment, as_of))
    return tuple(out)


def _event(kind: str, a: Assessment, as_of: str) -> LifecycleEvent:
    reason = a.reason
    if kind == REVALIDATED:
        reason = (f"support returned: {a.reason}. The belief was stale and "
                  f"is current again — by evidence, not by rewriting the "
                  f"record that said it was stale")
    return LifecycleEvent(
        event_id=f"{kind}|{a.belief_id}|{as_of[:10]}",
        event=kind, belief_id=a.belief_id, subject=a.subject,
        proposition="", at=as_of[:10],
        reason_code=a.reason_code,
        reason=reason, cadence_days=a.cadence_days,
        days_since_anchor=int(a.days_since_anchor or 0), anchor=a.anchor,
        what_would_revalidate=(
            "one informative reconciliation, or independent evidence of the "
            "same behaviour from a source that did not open the belief"))


def summarise(assessments: Sequence[Assessment],
              emitted: Sequence[LifecycleEvent] = ()) -> dict:
    """The operator view — including why nothing decayed, when nothing did."""
    eligible = [a for a in assessments if a.eligible]
    counts = collections.Counter(a.outcome for a in eligible)
    refusals = collections.Counter(a.reason_code for a in assessments
                                   if not a.eligible)
    upcoming = sorted(a.decays_on for a in assessments
                      if a.decays_on and not a.eligible)
    oldest = max((a.days_since_anchor or 0 for a in assessments), default=0)
    cadences = collections.Counter(a.cadence_days for a in assessments)
    return {
        "contract": CONTRACT,
        "beliefs": len(assessments),
        "eligible_for_decay": len(eligible),
        "stale": counts.get(STALE, 0),
        "retired": counts.get(RETIRED, 0),
        "revalidated": sum(1 for e in emitted if e.event == REVALIDATED),
        "events_emitted": len(emitted),
        "oldest_active_belief_days": oldest,
        "next_decay_window": upcoming[0] if upcoming else "",
        "cadences_in_use": dict(sorted(cadences.items())),
        "not_eligible_because": dict(refusals),
        "note": ("STALE is time passing with nothing argued; WEAKENING is "
                 "evidence arguing against, and belongs to belief_maturity. "
                 "A tested belief is never stale however old, and an aged "
                 "belief is never contradicted"),
    }

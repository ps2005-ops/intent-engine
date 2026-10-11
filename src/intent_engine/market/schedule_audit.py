"""Which cycles were supposed to run, and what actually became of them.

WHY THIS EXISTS
---------------
Nothing in this engine ever asked that question. `RunStore` records what DID
run, `learning_health` measures the steps of cycles that ran, and the process
exits 0 on every deliberate skip -- so a cycle that never happened left no
trace anywhere. Measured on 2026-10-11 over the full history:

    expected slots 2026-07-31..2026-10-11 : 146
    slots that did no work                :  21   (14.4%)

and every monitoring surface reported healthy throughout, including a health
job claiming 100% step reliability.

THE TWO CAUSES, BOTH VERIFIED
-----------------------------
**1. A suspended predecessor holding the lock (17 slots).** Every
lock-contended day cycle was blocked by the PREVIOUS NIGHT's run. Those runs
recorded durations of 10-46 hours with all 15 steps `ok` and `attempts: 1`,
which is not a hang -- it is the host sleeping mid-cycle. `JobLock` is an
flock, so a *suspended* process keeps holding it; the 06:30 day cycle then
fails fast with `JobLockedError` and is discarded. When the predecessor was
still "running" at the next 20:30, launchd would not launch a second instance
of the same label, so that night slot got no record at all.

**2. Hibernation spanning whole slots (4 slots).** `pmset` for the last gap:

    2026-10-09 15:53  Sleep 'Low Power Sleep' Batt(Charge:1%) 137788 secs
    2026-10-11 06:09  Wake from Hibernate

38.3 hours. 2026-10-09 night, 2026-10-10 day and 2026-10-10 night never
existed. On wake launchd fired the coalesced jobs at 06:09, but a run's
identity is formed from `now`'s date -- so those fires became
`2026-10-11:*` and could never have satisfied 10-10's slot. The 20:30 night
job was then correctly refused as EARLY (06:09 precedes 20:30 on its own
operating day).

WHAT THIS MODULE DOES NOT CLAIM
-------------------------------
Neither cause is a code defect, and neither is fixable by code alone. A laptop
at 1% battery will hibernate through a scheduled time no matter what this
engine does. What was a defect is that the losses were **invisible and
unrecoverable**: nothing enumerated the expected slots, so nothing noticed.

So this module detects and classifies. It deliberately draws the line §3.5
asks for: *recovery after waking* is achievable and is what `catch_up_plan`
offers; *guaranteed execution while the host sleeps* is not, and no amount of
launchd configuration establishes it.
"""
from __future__ import annotations

import collections
import datetime as _dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import cycle as C
from . import session as S

CONTRACT = "schedule_audit.v1"

# --- per-slot outcomes ------------------------------------------------------
#: The cycle ran every step and advanced the statistics.
RAN_COMPLETED = "RAN_COMPLETED"
#: Ran every step and found no new market observation. A completed cycle
#: reporting an honest absence -- NOT a miss. Weekends live here.
RAN_NO_NEW_SESSION = "RAN_NO_NEW_SESSION"
#: Ran, and at least one step failed.
RAN_DEGRADED = "RAN_DEGRADED"
#: No record of any kind. The host was asleep, or launchd would not start a
#: second instance of a label whose previous run had not returned.
MISSED_NEVER_INVOKED = "MISSED_NEVER_INVOKED"
#: Fired, but before its scheduled time on its own operating day -- the
#: signature of a coalesced wake-time launch carrying the wrong date.
MISSED_EARLY_FIRE = "MISSED_EARLY_FIRE"
#: Fired on time and found the shared lock held, so it did nothing.
MISSED_LOCK_CONTENTION = "MISSED_LOCK_CONTENTION"
#: Fired and found its own identity already completed. Not a loss.
SUPERSEDED_DUPLICATE = "SUPERSEDED_DUPLICATE"
#: Its scheduled moment has not arrived yet.
NOT_YET_DUE = "NOT_YET_DUE"

#: Outcomes where no cycle work happened and none is recorded elsewhere.
LOST = (MISSED_NEVER_INVOKED, MISSED_EARLY_FIRE, MISSED_LOCK_CONTENTION)
#: Outcomes where the cycle genuinely ran.
WORKED = (RAN_COMPLETED, RAN_NO_NEW_SESSION, RAN_DEGRADED)

# --- recoverability ---------------------------------------------------------
RECOVERABLE = "RECOVERABLE"
UNRECOVERABLE_TOO_OLD = "UNRECOVERABLE_TOO_OLD"

#: How far back a missed cycle may be replayed. Beyond this the retrieval
#: layer no longer sees what that day saw -- news feeds roll off, "latest"
#: endpoints have moved on -- so a replay would compose a different day's
#: evidence under an old date and look like recovered history. Seven days is
#: chosen to cover a long weekend plus a flat battery, not tuned.
RECOVERY_LOOKBACK_DAYS = 7

#: Minutes before a scheduled slot at which catch-up stops starting new
#: replays.
#:
#: A replay is a full cycle and takes ~25 minutes on this host, so replaying
#: the seven recoverable slots is about three hours of work. Each replay takes
#: the shared lock. Start that chain shortly before 06:30 and the scheduled
#: cycle fires into a held lock and is LOST -- which is exactly the defect
#: catch-up exists to repair, recreated by the repair. So catch-up yields to
#: the schedule: the live slot always outranks a historical one.
YIELD_TO_SCHEDULE_MINUTES = 45


@dataclass(frozen=True)
class Slot:
    """One scheduled cycle, and what became of it."""
    as_of: str
    cycle: str
    run_id: str
    scheduled_local: str
    outcome: str
    recoverability: str
    attempts: int
    statuses: Tuple[str, ...]
    why: str

    @property
    def lost(self) -> bool:
        return self.outcome in LOST

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of, "cycle": self.cycle, "run_id": self.run_id,
            "scheduled_local": self.scheduled_local, "outcome": self.outcome,
            "recoverability": self.recoverability, "attempts": self.attempts,
            "statuses": list(self.statuses), "why": self.why,
        }


def normalise_status(row: dict) -> str:
    """The status a row WOULD carry under the current taxonomy.

    Records written before `SKIPPED_OUTSIDE_WINDOW` and
    `SKIPPED_LOCK_CONTENTION` existed all say `SKIPPED_DUPLICATE`, which is
    the one reading that is wrong in every one of those cases. The reason
    text is what distinguishes them, and it was always written.

    This reads history; it does not rewrite it. The stored rows are left
    exactly as they were -- see the module docstring on append-only
    discipline.
    """
    status = row.get("status") or ""
    if status != C.SKIPPED_DUPLICATE:
        return status
    reason = (row.get("reason") or "").lower()
    if "outside the" in reason:
        return C.SKIPPED_OUTSIDE_WINDOW
    if "holds the lock" in reason:
        return C.SKIPPED_LOCK_CONTENTION
    return C.SKIPPED_DUPLICATE


def expected_slots(start: str, end: str) -> Tuple[Tuple[str, str], ...]:
    """Every (operating day, cycle) pair in an inclusive date range.

    Both cycles are expected every single day, including weekends. That is
    deliberate and matches the engine: a weekend `day` cycle still runs
    research and still records `SKIPPED_NO_NEW_MARKET_SESSION` or COMPLETED.
    Treating a weekend as "not expected" would hide a genuine miss behind
    the calendar.
    """
    first = _dt.date.fromisoformat(start)
    last = _dt.date.fromisoformat(end)
    out: List[Tuple[str, str]] = []
    day = first
    while day <= last:
        for which in C.CYCLES:
            out.append((day.isoformat(), which))
        day += _dt.timedelta(days=1)
    return tuple(out)


def _scheduled_local(as_of: str, which: str) -> str:
    hour, minute = C.SCHEDULE[which]
    return f"{as_of}T{hour:02d}:{minute:02d}:00"


def _worked_on_time(rows: Sequence[dict]) -> bool:
    """Did this slot do its work WITHOUT a replay?

    Separated from `_classify` because a catch-up genuinely does the slot's
    work -- the evidence lands, the beliefs move -- but it does not make the
    schedule reliable. Folding replays into one number would let a chronically
    sleeping host report 100% reliability on the strength of its catch-ups,
    which is the opposite of what the figure is for.
    """
    for row in rows:
        if row.get("catch_up"):
            continue
        if normalise_status(row) in (C.COMPLETED,
                                     C.SKIPPED_NO_NEW_MARKET_SESSION,
                                     C.PARTIAL, C.FAILED):
            return True
    return False


def _classify(rows: Sequence[dict]) -> Tuple[str, str]:
    """(outcome, why) for one slot, from every record bearing its identity."""
    if not rows:
        return (MISSED_NEVER_INVOKED,
                "no record of any kind -- the host was asleep, or launchd "
                "would not start a second instance of a label whose previous "
                "run had not returned")
    statuses = [normalise_status(r) for r in rows]
    # A slot that ever ran, ran. Later skips against the same identity are
    # duplicate protection working, not a loss.
    if C.COMPLETED in statuses:
        return RAN_COMPLETED, "completed"
    if C.SKIPPED_NO_NEW_MARKET_SESSION in statuses:
        return (RAN_NO_NEW_SESSION,
                "ran every step; no new market observation to advance "
                "statistics with")
    if C.PARTIAL in statuses or C.FAILED in statuses:
        return RAN_DEGRADED, "ran with at least one failed step"
    if C.SKIPPED_LOCK_CONTENTION in statuses:
        return (MISSED_LOCK_CONTENTION,
                "fired on time and found the shared lock held -- almost "
                "always by a predecessor the host suspended mid-cycle")
    if C.SKIPPED_OUTSIDE_WINDOW in statuses:
        return (MISSED_EARLY_FIRE,
                "fired before its scheduled time on its own operating day, "
                "the signature of a coalesced wake-time launch")
    if C.SKIPPED_DUPLICATE in statuses:
        return (SUPERSEDED_DUPLICATE,
                "its own identity had already completed")
    return RAN_DEGRADED, f"unrecognised statuses {sorted(set(statuses))}"


def audit(*, root, start: Optional[str] = None, end: Optional[str] = None,
          now: Optional[_dt.datetime] = None,
          lookback_days: int = RECOVERY_LOOKBACK_DAYS) -> dict:
    """Join the expected schedule against the durable run ledger.

    `start` defaults to the first operating day on record, `end` to today in
    the operating timezone, so the default call audits the whole history.
    """
    store = C.RunStore(root)
    rows = store.all()
    by_slot: Dict[Tuple[str, str], List[dict]] = collections.defaultdict(list)
    for row in rows:
        if row.get("dry_run"):
            continue          # a rehearsal is not an operating cycle
        by_slot[(row.get("as_of"), row.get("cycle"))].append(row)

    now = now or S.now_local()
    if end is None:
        end = now.date().isoformat()
    if start is None:
        dates = [r.get("as_of") for r in rows if r.get("as_of")]
        start = min(dates) if dates else end

    slots: List[Slot] = []
    for as_of, which in expected_slots(start, end):
        found = by_slot.get((as_of, which), [])
        scheduled = _scheduled_local(as_of, which)
        # NOT_YET_DUE is decided by the clock ALONE, before any record is
        # read. An early fire leaves a `SKIPPED_OUTSIDE_WINDOW` record for a
        # slot whose real moment is still hours away -- a wake-time coalesced
        # launch does exactly that -- and classifying on the record would call
        # tonight's 20:30 cycle a recoverable miss at breakfast, put it in the
        # catch-up plan, and depress schedule reliability with a slot that has
        # not had its chance yet.
        if scheduled > now.strftime("%Y-%m-%dT%H:%M:%S"):
            outcome, why = (NOT_YET_DUE,
                            "its scheduled moment has not arrived")
        else:
            outcome, why = _classify(found)
        if outcome in LOST:
            age = (_dt.date.fromisoformat(end)
                   - _dt.date.fromisoformat(as_of)).days
            recoverability = (RECOVERABLE if age <= lookback_days
                              else UNRECOVERABLE_TOO_OLD)
        else:
            recoverability = ""
        slots.append(Slot(
            as_of=as_of, cycle=which,
            run_id=f"{as_of}:{which}:{S.TIMEZONE}",
            scheduled_local=scheduled, outcome=outcome,
            recoverability=recoverability, attempts=len(found),
            statuses=tuple(normalise_status(r) for r in found), why=why))

    counts = collections.Counter(s.outcome for s in slots)
    due = [s for s in slots if s.outcome != NOT_YET_DUE]
    lost = [s for s in slots if s.lost]
    worked = [s for s in slots if s.outcome in WORKED]
    on_time = [s for s in worked
               if _worked_on_time(by_slot.get((s.as_of, s.cycle), []))]
    replayed = len(worked) - len(on_time)
    return {
        "contract": CONTRACT,
        "start": start,
        "end": end,
        "slots_expected": len(slots),
        "slots_due": len(due),
        "slots_worked": len(worked),
        "slots_worked_on_time": len(on_time),
        "slots_worked_by_catch_up": replayed,
        "slots_lost": len(lost),
        #: Work done WITHOUT a replay, over due slots. The schedule's own
        #: number; a catch-up cannot raise it.
        "reliability": (len(on_time) / len(due)) if due else None,
        #: Work done by any means. Rises when a catch-up succeeds, which is
        #: the point of having both.
        "coverage": (len(worked) / len(due)) if due else None,
        "by_outcome": dict(counts),
        "lost": tuple(s.as_dict() for s in lost),
        "recoverable": tuple(s.as_dict() for s in lost
                             if s.recoverability == RECOVERABLE),
        "unrecoverable": tuple(s.as_dict() for s in lost
                               if s.recoverability == UNRECOVERABLE_TOO_OLD),
    }


def catch_up_plan(result: dict) -> Tuple[dict, ...]:
    """The missed slots worth replaying, newest first.

    Only `RECOVERABLE` slots appear. Each entry names the `--as-of` the
    replay must carry, because a run's identity comes from its operating day:
    a catch-up launched today with today's date would record a SECOND run for
    today and leave the missed slot exactly as empty as it was. That is the
    bug that made the wake-time coalesced fires useless.

    The caller must mark the replay as a catch-up and must NOT backdate its
    execution timestamps. A cycle replayed on Sunday for Friday is a Sunday
    execution of Friday's window, and the ledger has to say so -- otherwise
    the schedule reliability figure this module produces becomes a number
    about replays rather than about the schedule.
    """
    return tuple(sorted(result.get("recoverable", ()),
                        key=lambda s: (s["as_of"], s["cycle"]),
                        reverse=True))


def render(result: dict) -> List[str]:
    """Operator lines. Says 'no cycles lost' rather than printing nothing."""
    rel = result.get("reliability")
    lines = [
        f"- Schedule window: {result.get('start')} -> {result.get('end')}",
        f"- Slots expected: {result.get('slots_expected')} "
        f"({result.get('slots_due')} due)",
        f"- Cycles that did work: {result.get('slots_worked')}",
        f"- Cycles lost: **{result.get('slots_lost')}**"
        + (f" ({1 - rel:.1%} of due slots)" if rel is not None else ""),
        f"- Schedule reliability: "
        + (f"{rel:.1%}" if rel is not None else "UNMEASURABLE"),
    ]
    if not result.get("lost"):
        lines.append("- No cycle has been lost in this window.")
        return lines
    lines += ["", "| day | cycle | outcome | recoverable |",
              "|---|---|---|---|"]
    for slot in result["lost"]:
        lines.append(f"| {slot['as_of']} | {slot['cycle']} | "
                     f"`{slot['outcome']}` | {slot['recoverability']} |")
    return lines


def minutes_to_next_slot(now: _dt.datetime) -> float:
    """Minutes until the next scheduled cycle, for yielding to it."""
    best = None
    for which in C.CYCLES:
        hour, minute = C.SCHEDULE[which]
        slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if slot <= now:
            slot += _dt.timedelta(days=1)
        delta = (slot - now).total_seconds() / 60.0
        best = delta if best is None else min(best, delta)
    return best if best is not None else float("inf")


def catch_up(*, root, runner, limit: int = 0,
             lookback_days: int = RECOVERY_LOOKBACK_DAYS,
             yield_minutes: float = YIELD_TO_SCHEDULE_MINUTES,
             now: Optional[_dt.datetime] = None) -> dict:
    """Replay the recoverable missed slots, oldest first.

    `runner(cycle, as_of)` performs one cycle and returns its `CycleResult`;
    it is injected so this is testable without a live engine and so the CLI
    owns the probe/step wiring.

    FIVE THINGS THIS DELIBERATELY DOES
    ----------------------------------
    1. **Oldest first.** Evidence and beliefs accumulate forward, so replaying
       Friday before Saturday is the only order that reconstructs the same
       sequence the schedule would have produced.
    2. **Passes the missed slot's own `as_of`.** A run's identity is formed
       from its operating day, so a replay launched today with today's date
       records a SECOND run for today and leaves the gap exactly as empty.
       That is precisely why the wake-time coalesced launches were useless.
    3. **Inherits the leakage guard for free.** `session.leakage_cutoff(as_of)`
       is already applied in the evidence path, so a replay for Friday cannot
       ingest anything published after Friday. Nothing extra is needed here --
       and nothing here may bypass it.
    4. **Never backdates execution.** `started_at` / `finished_at` are the real
       instants; only `as_of` is historical, and `catch_up=True` marks the row
       so schedule reliability stays a statement about the schedule.
    5. **Re-audits after each slot.** A replay can satisfy more than its own
       slot (the engine drains a backlog), and a replay can also fail. Reading
       the plan once and trusting it would replay work already done.

    Stops at the first slot that does not do work: if the lock is held or the
    host is mid-cycle, continuing would queue a pile of contended runs.
    """
    done: List[dict] = []
    refused: List[dict] = []
    yielded: Optional[dict] = None
    attempted = 0
    # Audit exactly the recoverable window, not `audit`'s default of "since
    # the first record". Those coincide on a long history and diverge on a
    # sparse one: if the earliest record is newer than `end - lookback`, the
    # default start hides slots that are still replayable. Deriving the window
    # from the same constant that decides recoverability keeps the two from
    # disagreeing.
    anchor = (now or S.now_local()).date()
    window_start = (anchor - _dt.timedelta(days=lookback_days)).isoformat()
    window_end = anchor.isoformat()
    while True:
        result = audit(root=root, start=window_start, end=window_end,
                       now=now, lookback_days=lookback_days)
        plan = sorted(result.get("recoverable", ()),
                      key=lambda s: (s["as_of"], C.CYCLES.index(s["cycle"])))
        plan = [s for s in plan
                if (s["as_of"], s["cycle"]) not in
                {(d["as_of"], d["cycle"]) for d in done + refused}]
        if not plan:
            break
        if limit and attempted >= limit:
            break
        # Yield to the live schedule. A replay holds the shared lock for about
        # the length of a cycle, so starting one just before 06:30 would lose
        # the real 06:30 cycle to contention -- the defect this repairs.
        remaining = minutes_to_next_slot(now or S.now_local())
        if remaining < yield_minutes:
            yielded = {"reason": "YIELDED_TO_SCHEDULE",
                       "minutes_to_next_slot": round(remaining, 1)}
            break
        slot = plan[0]
        attempted += 1
        outcome = runner(slot["cycle"], slot["as_of"])
        row = {"as_of": slot["as_of"], "cycle": slot["cycle"],
               "was": slot["outcome"], "status": getattr(outcome, "status",
                                                         str(outcome))}
        if getattr(outcome, "status", "") in (C.COMPLETED,
                                              C.SKIPPED_NO_NEW_MARKET_SESSION,
                                              C.PARTIAL):
            done.append(row)
        else:
            refused.append(row)
            break
    after = audit(root=root, start=window_start, end=window_end,
                  now=now, lookback_days=lookback_days)
    return {
        "contract": CONTRACT,
        # The window these figures describe. `catch_up` audits only the
        # recoverable window, so its reliability/coverage are NOT the
        # whole-history numbers an operator just saw printed above them --
        # 53.3% over eight days is not a regression from 86.2% over ten
        # weeks. Naming the window is what stops that misreading.
        "window_start": window_start,
        "window_end": window_end,
        "attempted": attempted,
        "replayed": tuple(done),
        "refused": tuple(refused),
        "yielded_to_schedule": yielded,
        "slots_lost_before": None,
        "slots_lost_after": after.get("slots_lost"),
        "reliability_after": after.get("reliability"),
        "coverage_after": after.get("coverage"),
        "still_recoverable": len(after.get("recoverable", ()) or ()),
        "unrecoverable": len(after.get("unrecoverable", ()) or ()),
    }

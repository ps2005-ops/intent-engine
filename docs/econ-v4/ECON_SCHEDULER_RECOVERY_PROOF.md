# ECON_SCHEDULER_RECOVERY_PROOF

Wave 1. Before this, a cycle that never ran left **no trace in any surface**.
`RunStore` recorded what did run, `learning_health` measured the steps of
cycles that ran, and every deliberate skip exited 0 — so nothing in the engine
could answer "did every scheduled cycle happen?"

## What was actually lost

First audit of the expected schedule against the durable run ledger:

```
expected slots 2026-07-31 .. 2026-10-11 : 146  (145 due)
cycles that did work                    : 125
cycles LOST                             :  20   (13.8%)
schedule reliability                    : 86.2%
```

| outcome | count |
|---|---:|
| `RAN_NO_NEW_SESSION` | 77 |
| `RAN_COMPLETED` | 48 |
| `MISSED_LOCK_CONTENTION` | **14** |
| `MISSED_NEVER_INVOKED` | **6** |
| `NOT_YET_DUE` | 1 |

Every one of those 20 happened while the health job reported **100% step
reliability on every step**, because it measures the steps of cycles that ran.

## Root cause — two mechanisms, both verified, neither a code bug

### 1. A suspended predecessor holding the lock (17 slots)

Every lock-contended day cycle was blocked by **the previous night's run**:

```
BLOCKED: 2026-10-08:day  at 10:33:24
   held by 2026-10-07:night  00:43:24 -> 13:07:38   (12.4 h)
BLOCKED: 2026-09-08:day  at 10:35:47
   held by 2026-09-07:night  00:41:34 -> 22:41:13   (46.0 h)
```

Those long runs are not hangs. All 15 steps reported `ok`, and **all 1,935
steps in the entire history recorded `attempts: 1`** — nothing retried,
nothing failed. The process was *suspended*. `JobLock` is an `flock`, which a
suspended process keeps holding, so the 06:30 day cycle failed fast with
`JobLockedError` and was discarded.

When the predecessor was still "running" at the next 20:30, launchd would not
launch a second instance of the same label — which is why three night slots
(08-23, 09-02, 09-08) have **no record at all**.

### 2. Hibernation spanning whole slots (3 slots)

```
2026-10-09 15:53  Sleep 'Low Power Sleep'  Batt(Charge:1%)  137788 secs
2026-10-11 06:09  Wake from Hibernate      Batt(Charge:100%)
```

38.3 hours at 1% battery. 2026-10-09 night, 2026-10-10 day and 2026-10-10
night never existed.

On wake launchd fired the coalesced jobs at 06:09 — but **a run's identity is
formed from `now`'s date**, so those became `2026-10-11:*` and could never
have satisfied 10-10's slot. The night job was then correctly refused as
EARLY, because 06:09 precedes 20:30 on its own operating day.

`session.within_window` is *already* deliberately permissive for this host —
"at or after the scheduled time, on the same operating day", chosen so a
laptop waking at 23:00 still runs its 20:30 cycle. It was not the problem and
was not changed.

## What was built

### Detection — `market/schedule_audit.py`

Joins the expected schedule against the durable run ledger. Eight outcomes,
and the distinctions are the point:

- `RAN_COMPLETED`, `RAN_NO_NEW_SESSION`, `RAN_DEGRADED` — work happened.
  `RAN_NO_NEW_SESSION` is **not** a miss: it ran every step and reported an
  honest absence. Weekends live here.
- `MISSED_NEVER_INVOKED`, `MISSED_EARLY_FIRE`, `MISSED_LOCK_CONTENTION` —
  no work, and nothing retries it.
- `SUPERSEDED_DUPLICATE` — its own identity had already completed. Not a loss.
- `NOT_YET_DUE` — decided by the clock **alone**, before any record is read.

That last one is a defect this module found in itself. A wake-time coalesced
launch leaves a `SKIPPED_OUTSIDE_WINDOW` record for a slot whose real moment
is still hours away; classifying on the record called tonight's 20:30 cycle a
recoverable miss at breakfast, put it in the catch-up plan, and depressed
reliability with a slot that had not had its chance.

**Legacy records are read, never rewritten.** 27 rows predate
`SKIPPED_OUTSIDE_WINDOW` and `SKIPPED_LOCK_CONTENTION` and all say
`SKIPPED_DUPLICATE` — the one reading that is wrong in every such case. The
reason text always distinguished them, so `normalise_status` decomposes them
at read time: **14 lock contention, 3 early fires, 2 genuine duplicates.** The
stored rows are untouched.

### Two numbers, because a replay must not flatter the schedule

- `reliability` — work done **without** a replay, over due slots.
- `coverage` — work done by any means.

A catch-up raises coverage and can never raise reliability. Without that
split, a chronically sleeping host would report 100% reliability on the
strength of its catch-ups, which is the opposite of what the figure is for.

### Alerting — above the observation gate

`CYCLES_MISSED` (CRITICAL when recoverable) and `SCHEDULE_RELIABILITY_LOW`
(floor 95%) fire from `health.schedule`, which is read from the run ledger.

They sit **above** `MIN_CYCLES_FOR_ALERT`. Every other alert needs
observations, and an observation only exists for a cycle that ran — so the
more cycles were lost, the fewer alerts could fire. The engine went quietest
exactly when it was most broken. Pinned by
`test_missed_cycles_alert_fires_with_no_observations_at_all`.

Live, on the production ledger:

```
[CRITICAL] CYCLES_MISSED: 20 scheduled cycle(s) did no work and nothing
           retried them; 7 are still recoverable (`market catch-up` replays them)
[CRITICAL] SCHEDULE_RELIABILITY_LOW: 86.2% of due cycles did work (floor 95%);
           the schedule is the binding problem, not the learning rate
```

### Safe catch-up — `market catch-up`

Replays recoverable slots, oldest first. Five deliberate properties:

1. **Passes the missed slot's own `--as-of`.** Identity comes from the
   operating day; a replay launched today with today's date records a second
   run for today and leaves the gap as empty as it was. That is exactly why
   the wake-time coalesced launches were useless.
2. **Inherits the leakage guard for free.** `session.leakage_cutoff(as_of)` is
   already applied in the evidence path, so a replay for Friday cannot ingest
   anything published after Friday. Nothing here may bypass it.
3. **Never backdates execution.** `started_at`/`finished_at` are the real
   instants; only `as_of` is historical, and `catch_up=True` marks the row.
4. **No bar probe.** The probe answers "what is the newest bar *now*", which
   for a historical replay is future information. Left `None`, so the session
   reports `BAR_UNAVAILABLE` honestly rather than dating today's bar to a past
   operating day.
5. **Re-audits after every slot**, because a replay can satisfy more than its
   own slot and can also fail. Stops at the first slot that does no work.

**Recoverability is bounded to 7 days.** Beyond that the retrieval layer no
longer sees what that day saw — feeds roll off, "latest" endpoints have moved
— so a replay would compose a *different* day's evidence under an old date and
look like recovered history. 13 of the 20 losses are
`UNRECOVERABLE_TOO_OLD` and are reported as permanently lost.

### The repair must not recreate the defect

A replay is a full cycle (~25 min on this host) and takes the shared lock, so
replaying all seven recoverable slots is ~3 hours of lock-holding. Starting
that chain shortly before 06:30 would lose the real 06:30 cycle to
contention — the exact defect being repaired.

So catch-up **yields to the live schedule**: it starts no new replay within
`YIELD_TO_SCHEDULE_MINUTES` (45) of a scheduled slot. The live slot always
outranks a historical one. Pinned by
`test_catch_up_yields_rather_than_blocking_the_live_cycle`.

### A trap paid for during this work

`cmd_catch_up` first used `_root(args)`, which redirects to `<root>/dryrun`
whenever a `--dry-run` flag is set. Correct for rehearsing a cycle;
catastrophic here — the audit read an almost-empty sandbox and reported every
real cycle as `MISSED_NEVER_INVOKED`, then offered to replay 15 cycles that
had in fact completed. Fixed to `resolve_root`, and the flag renamed
`--plan-only`: "dry run" already means "write into the sandbox" in this CLI
and cannot also mean "read the real tree and change nothing."

## Live proof — one real replay

Run against an isolated copy of production state, `--limit 1`:

```
replaying 2026-10-04 day ...
  2026-10-04:day:America/Toronto  SKIPPED_NO_NEW_MARKET_SESSION
    no completed bar could be retrieved
replayed 1, refused 0
```

The run record it wrote:

```json
{"run_id": "2026-10-04:day:America/Toronto",
 "as_of":   "2026-10-04",
 "status":  "SKIPPED_NO_NEW_MARKET_SESSION",
 "catch_up": true,
 "started_at":  "2026-10-11T12:15:03+00:00",
 "finished_at": "2026-10-11T12:32:10+00:00"}
```

All five properties verified at once: the identity is the **missed** day's,
`catch_up` is marked, and the execution timestamps are the **real** instants
on 2026-10-11 — not backdated to 10-04.

It recovered real work: the ledger grew 21,358 → **21,378** (+20 records) and
`reports/market/2026-10-04_day.{json,md}` were written. Over the recoverable
window the two figures separated exactly as designed:

```
schedule reliability : 53.3%   (on-time only — the replay cannot raise it)
coverage             : 60.0%   (including replays — the replay did raise it)
```

### What a replay can and cannot recover

The status is `SKIPPED_NO_NEW_MARKET_SESSION`, and that is not a failure — it
is the honest consequence of property 4. No historical bar can be retrieved
for a past operating day, so a replay will **never** report `COMPLETED`.

So a catch-up recovers the **evidence, research and belief work** of a missed
day. It does **not** recover that day's market-session statistics, because the
bar that would have advanced them is no longer obtainable. Both halves are
true and the ledger says which one happened.

## The host limitation, stated plainly

**What is now achievable: recovery after waking.** Detection, alerting and
bounded replay all work, and a missed cycle is visible and nameable.

**What is NOT achievable in code: execution while the host is asleep.** A
MacBook at 1% battery will hibernate through a scheduled time regardless of
launchd configuration, and no change in this repository alters that. The
38-hour gap above would recur tonight under identical conditions.

Two paths exist and **neither was taken, because both are the user's to
authorize**:

- A scheduled power-management wake, e.g.
  `sudo pmset repeat wakeorpoweron MTWRFSU 06:25:00`. This is a system
  setting and needs the user's password; it is theirs to run, not mine. It
  also cannot help a machine that is out of battery.
- An always-on host. That is infrastructure provisioning and needs approval.

Until one of those happens, the honest verdict on daily operation is PARTIAL,
and `reliability` will keep reporting the truth.

## Tests

`tests/test_schedule_audit.py` — **37 tests**, including:

- the four legacy meanings of `SKIPPED_DUPLICATE`, decomposed
- `NOT_YET_DUE` winning over an early-fire record
- `RAN_NO_NEW_SESSION` counted as work, not loss
- a dry run never satisfying a slot
- the 7-day recoverability boundary, both sides
- a replay raising coverage but never reliability
- an all-replay window reporting **0.0** reliability
- catch-up ordering, limit, stop-on-refusal, and yielding to the schedule
- the alert firing with **zero** observations
- `assess` populating `health.schedule` *before* `alerts` consumes it

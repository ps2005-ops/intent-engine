# ECON_V4_DAILY_SCHEDULER_PROOF

## The schedule, verified

Three launchd agents on this Mac. Unchanged — no duplicate agent was created.

| label | schedule | runs @ 06:12 | runs @ 06:34 |
|---|---|---:|---:|
| `com.intentengine.market.day` | 06:30 America/Toronto | 64 | **65 (running)** |
| `com.intentengine.market.night` | 20:30 America/Toronto | 61 | 61 |
| `com.intentengine.market.health` | RunAtLoad + periodic | 739 | 739 |

`TRADING_MODE=PAPER` in every plist. `--enforce-window` set on day and night.

## Three cycles were lost, and every surface reported success

Measured 2026-10-11 during recovery:

| | 2026-10-09 06:58 | 2026-10-11 06:12 |
|---|---:|---:|
| ledger records | 21,065 | **21,065** |
| last health snapshot | 2026-10-09 | **2026-10-09** |

Two days, two launchd invocations, **zero records written.** The cause is in
the logs:

```
2026-10-11:day:America/Toronto    SKIPPED_DUPLICATE
  fired at 06:09 EDT, outside the 06:30 America/Toronto window — not running
2026-10-11:night:America/Toronto  SKIPPED_DUPLICATE
  fired at 06:09 EDT, outside the 20:30 America/Toronto window — not running
```

Both jobs fired **at the same moment, 06:09**, and neither was anywhere near
its window. The host had been asleep since 2026-10-09 15:10 (last
`health.out.log` write). On wake, launchd coalesced the missed
`StartCalendarInterval` firings and ran them immediately; `--enforce-window`
correctly refused both.

So **2026-10-09 night, 2026-10-10 day and 2026-10-10 night never ran at all.**
Nothing retries them. The work is gone.

And it was invisible, for three compounding reasons:

1. the status said `SKIPPED_DUPLICATE` — i.e. "the work already exists", the
   opposite of what happened;
2. the process exited **0**, so launchd recorded success;
3. the health job reported **100% step reliability on every step**, because it
   measures the steps of cycles that ran.

The window guard itself is correct and was not changed. Refusing a 06:09 fire
of a 06:30 job is right. The defect is that the refusal was indistinguishable
from a duplicate and nothing surfaced the loss.

## `SKIPPED_DUPLICATE` was doing four jobs

| situation | work done? | retried? | was reported as |
|---|---|---|---|
| run id already completed | yes, earlier | n/a | `SKIPPED_DUPLICATE` |
| completed while waiting for the lock | yes, by the other run | n/a | `SKIPPED_DUPLICATE` |
| fired outside its time window | **no** | **no** | `SKIPPED_DUPLICATE` |
| another cycle held the lock | **no** | **no** | `SKIPPED_DUPLICATE` |

Re-labelling the full launchd history under the corrected taxonomy:

| actual outcome | count |
|---|---:|
| `SKIPPED_NO_NEW_MARKET_SESSION` | 78 |
| `COMPLETED` | 44 |
| `SKIPPED_LOCK_CONTENTION` | **14** |
| `SKIPPED_OUTSIDE_WINDOW` | **3** |
| `SKIPPED_DUPLICATE` (genuine) | **2** |

**Only 2 of the 19 "duplicates" were duplicates.** The label was wrong 89% of
the time, and in 17 cases it reported work-already-done for a cycle that did
nothing.

## The repair

`market/cycle.py` now distinguishes:

- `SKIPPED_OUTSIDE_WINDOW` — a mistimed or coalesced fire. No work, no retry.
- `SKIPPED_LOCK_CONTENTION` — another cycle held the shared lock.
- `SKIPPED_DUPLICATE` — the run id genuinely completed already.

Two groups, because "did this process do the work" and "was this a failure"
are different questions:

- `SKIPPED_WITHOUT_RUNNING` — the four statuses that return *before* any step
  runs.
- `SKIPPED` — all of those plus `SKIPPED_NO_NEW_MARKET_SESSION`.

`SKIPPED_NO_NEW_MARKET_SESSION` is deliberately **excluded** from
`SKIPPED_WITHOUT_RUNNING`: it executes every step and reports an honest
absence of a new market observation. That is a completed cycle, not a skipped
one. Grouping it with the real skips immediately broke two "did it actually
run?" assertions — which is how the distinction was found rather than assumed.

Every skip still exits **0**. launchd must not thrash or back off over a
deliberate refusal, so the exit code deliberately *cannot* carry the
missed-cycle signal — `test_exit_code_cannot_distinguish_a_missed_cycle` pins
that, and it is the reason the signal has to live on the health report.

`exit_code` previously enumerated two statuses by hand, so any new skip kind
would have exited 1 and made a refusal look like a crash. It now reads the
group, and a structural test asserts no status is hand-listed there — reading
code with comments stripped, because the first version of that test matched
the comment explaining the rule.

## Live proof this session

A `day` cycle fired **on schedule at 06:30** on 2026-10-11 (`runs` 64 → 65,
`state = running`) while this work was in progress. On-schedule invocation
works; it is only the *missed* intervals that are lost. The runtime tree was
not edited during the cycle and its HEAD is still `9b01ff1b10d3`.

## Not done — and what remains

The taxonomy repair makes a missed cycle **visible and nameable**. It does not
yet make it *recoverable*, and it does not yet raise an alert. Still open:

- **Bounded catch-up.** The engine already replays a backlog of dates within
  one invocation, so the machinery exists; nothing currently invokes it for a
  cycle lost to sleep. A missed day should be runnable for its own date
  without pretending it ran on time.
- **Missed-cycle alert.** `learning_health.alerts` should fire when a
  scheduled cycle has no ledger entry, which is the surface the exit code
  cannot be.
- **Reliability accounting.** The health report should separate scheduled /
  attempted / completed / intentionally-skipped / unexpectedly-skipped /
  missed, instead of reporting 100% step reliability over the cycles that ran.
- **Lock contention at 14 occurrences** is worth a lease/ownership review; a
  long invocation replaying a backlog overlaps the next scheduled one.

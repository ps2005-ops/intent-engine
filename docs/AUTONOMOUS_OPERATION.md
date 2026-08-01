# Autonomous operation

How the market learning engine runs unattended: what it does, how to install
it, how to inspect it, and how to stop it.

> **Paper trading only.** There is no broker integration, no order-submission
> path, no capital and no live-trading mode. `TRADING_MODE` accepts exactly one
> value and any other value refuses to start. See [Paper only](#paper-only).

---

## 1. What runs, and when

| cycle | time (`America/Toronto`) | purpose |
|---|---|---|
| **day** | 06:30 daily | pre-market. Ingest evidence, evaluate the universe, update the funnel, evaluate signals, manage paper positions, publish the operating report. |
| **night** | 20:30 daily | post-close. Ingest the day's evidence, reconcile, resolve elapsed horizons, run opportunity analysis, update stability/maturity/assets, health-check, publish the research report. |
| **health** | hourly | reads run records off disk. No network, no research. Detects that a cycle *stopped firing* — which the cycle itself cannot do, because it is not running. |

Both cycles run **every calendar day**, including weekends and market holidays.
That is deliberate: evidence is published when markets are shut, and replay,
reporting, health checks and asset maintenance do not need a session.

### What happens while markets are closed

Everything except statistics. The cycle records
`SKIPPED_NO_NEW_MARKET_SESSION` and completes its research normally. The
guard is `MarketSession.has_new_market_observation`, and it is the highest-value
check in the system:

> Re-reading Friday's close on Saturday and Sunday would inflate the sample by
> 40% and narrow every confidence interval. **Nothing would error.**

Session states: `TRADING_DAY`, `EARLY_CLOSE`, `WEEKEND`, `HOLIDAY`.
Bar states: `BAR_AVAILABLE`, `BAR_NOT_YET_PUBLISHED`, `BAR_STALE`,
`BAR_UNCHANGED`, `BAR_UNAVAILABLE`. Only `BAR_AVAILABLE` may advance a sample.

### Day and night do not observe two market sessions

The day cycle reads the **previous** session's completed bar; the night cycle
reads **today's**. When both read the same bar — a weekend, a holiday, an
unpublished close — the second says so and counts nothing. Neither report ever
presents a re-read bar as a new session.

---

## 2. Install

### Prerequisite: a permanent checkout

The installer resolves the repository from its own location and writes that
path into the launchd plists. **The path must be permanent.** Installing from a
temporary worktree schedules jobs against a directory that will be deleted.

This branch is `feat/market-learning-engine`. If your main checkout is on a
different branch, add a dedicated worktree rather than switching it:

```bash
git -C ~/intent-engine worktree add ~/intent-engine-market feat/market-learning-engine
```

### Rehearse, then install

```bash
cd ~/intent-engine-market && ops/install_autonomous.sh --dry-run
```

Renders the plists, validates them with `plutil`, scans them for credentials,
checks the interpreter can import the package — and installs nothing.

```bash
cd ~/intent-engine-market && ops/install_autonomous.sh
```

Idempotent: it unloads any existing agent before loading, so re-running leaves
exactly one job per cycle. Overrides: `IE_PYTHON` (interpreter),
`IE_MARKET_ROOT` (runtime root, default `<repo>/data`).

### Verify — and do not confuse a template with a service

```bash
launchctl list | grep com.intentengine.market
```

A plist on disk schedules nothing until launchd loads it. `status` reports
`installed` and `loaded` as **separate** fields for exactly this reason.

### Cron fallback (not recommended)

launchd is correct on macOS: it survives reboot, handles DST, and records exit
status. If you must use cron, note it does **not** run missed jobs after a
wake, and `--enforce-window` will then skip a late fire:

```cron
30 6  * * * cd ~/intent-engine-market && TRADING_MODE=PAPER PYTHONPATH=src .venv/bin/python -m intent_engine.market day   --root data
30 20 * * * cd ~/intent-engine-market && TRADING_MODE=PAPER PYTHONPATH=src .venv/bin/python -m intent_engine.market night --root data
```

---

## 3. Inspect

```bash
python -m intent_engine.market status --root data
python -m intent_engine.market status --root data --json
python -m intent_engine.market runs   --root data --limit 20
```

`status` reports: overall state, trading mode and whether it is enforced,
storage writability, lock held/age, scheduler installed/loaded, last run and
last success per cycle, next expected run, missed runs, per-step reliability
over the last 14 runs, git commit and cleanliness, and the latest error.

### Logs

| what | where |
|---|---|
| launchd stdout/stderr | `~/Library/Logs/intent-engine/{day,night,health}.{out,err}.log` |
| run records (append-only) | `<root>/status/market_cycles.jsonl` |
| reports | `<root>/reports/market/YYYY-MM-DD_{day,night}.{md,json}` |
| latest-report pointer | `<root>/reports/market/latest_{day,night}.json` |
| counterfactual signal audit | `<root>/reports/market/signal_audit.jsonl` |
| research asset ledger | `<root>/reports/market/research_assets.jsonl` |

---

## 4. Run a cycle by hand

```bash
python -m intent_engine.market day   --root data
python -m intent_engine.market night --root data
python -m intent_engine.market day   --root data --dry-run
```

`--dry-run` writes to `<root>/dryrun` and uses a labelled offline stub instead
of the network. **A rehearsal never appends to the real funnel history or the
real asset ledger** — fabricated observations are indistinguishable from data
afterwards. A dry run also never satisfies the duplicate check, so rehearsing
at 06:00 cannot cancel the real 06:30 run.

Trigger a scheduled job through launchd itself:

```bash
launchctl kickstart -k gui/$(id -u)/com.intentengine.market.night
```

---

## 5. Run statuses

| status | meaning | exit |
|---|---|---|
| `COMPLETED` | every step succeeded and a new market observation was recorded | 0 |
| `PARTIAL` | some steps failed; the report names which | 1 |
| `FAILED` | every step failed, or an integrity violation, or a bad trading mode | 1 |
| `SKIPPED_DUPLICATE` | this identity already completed, or the lock was held, or it fired outside the window | 0 |
| `SKIPPED_NO_NEW_MARKET_SESSION` | research ran; the bar was not new | 0 |
| `SKIPPED_STALE_DATA` | reserved for a stale-data refusal | 1 |

**Exit status is the alerting channel.** launchd records it; `status` reads the
run records. No external service, no paid dependency.

### Run identity

```
YYYY-MM-DD:<cycle>:America/Toronto      e.g. 2026-07-31:night:America/Toronto
```

The date is the operating day *in the operating timezone*, never the machine's
local day and never UTC. This is what makes duplicate protection survive a
reboot, a DST transition, and a laptop that changed timezone.

### Duplicate and overlap protection

Four independent guards:

1. **Schedule window** (`--enforce-window`) — a fire outside the local-time
   window is skipped before the lock is taken.
2. **Run identity** — one completed record per operating day per cycle.
3. **flock** — two processes at the same instant. Day and night share **one**
   lock, so a slow day run cannot overlap the night run.
4. **Re-check under the lock** — two processes that both pass (2) then
   serialise on (3).

---

## 6. Recover from failure

```bash
python -m intent_engine.market status --root data      # what failed, and when
tail -50 ~/Library/Logs/intent-engine/night.err.log
python -m intent_engine.market night --root data       # idempotent rerun
```

A `PARTIAL` or `FAILED` run **never** blocks a retry — otherwise one bad night
would be permanently unrecoverable.

**A stale lock.** flock is released by the OS when the holder dies, so a crashed
run leaves a lock *file* but not a held *lock*, and the next run proceeds.
`status` distinguishes `exists` from `held` and flags `stale` only when a lock
has genuinely been held over six hours. If that happens, find the process
(`lsof <root>/locks/market-cycle.lock`) before deleting anything.

### Failure classes

`TRANSIENT_SOURCE_FAILURE` (retried, exponential backoff with jitter),
`PERMANENT_SOURCE_FAILURE`, `STALE_MARKET_DATA`, `INVALID_TIMESTAMP`,
`INTEGRITY_VIOLATION`, `LOCK_CONFLICT`, `STORAGE_FAILURE`,
`CONFIGURATION_FAILURE`, `TEST_FAILURE`, `PARTIAL_CYCLE`,
`UNEXPECTED_EXCEPTION`.

Only `TRANSIENT_SOURCE_FAILURE` is retried. **An integrity violation is never
retried and never partial** — once a guarantee is broken every measurement in
the run is suspect, and retrying is asking reality for a different answer.

---

## 7. Pause, resume, update

```bash
launchctl bootout gui/$(id -u)/com.intentengine.market.day      # pause
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.intentengine.market.day.plist   # resume
ops/uninstall_autonomous.sh                                     # remove entirely
```

Uninstalling removes **only the schedule**. Reports, run records, funnel
history and the asset ledger are untouched — turning off a timer is not consent
to erase research history.

**Updating the repo during an active run.** Check the lock first:

```bash
python -m intent_engine.market status --root data | grep lock
git pull
```

The lock is advisory, so `git pull` will not wait for it. Pulling mid-run can
swap code under a running cycle; the cycle would still finish, but its report
would describe a mix of two versions. Pull when the lock is free, or pause the
agents first.

---

## 8. Paper only

`TRADING_MODE` resolves as:

| value | result |
|---|---|
| unset / empty | `PAPER`, source `default` — absent config resolves to the **safe** state |
| `PAPER` | `PAPER`, source `env` |
| anything else | `TradingModeError`, **the cycle refuses to start** |

An unknown value is not coerced to paper silently. The error *is* the useful
output: it says the operator's intent and the system's capability disagree.

Enforced in three places: at cycle start before any step runs, in the positions
step, and by a test asserting no order-submission symbol exists anywhere in
`cycle.py` or `steps.py`.

There is no live path to enable and none is introduced in this cycle.

---

## 9. What "improvement" means

A cycle improves the system when it produces **any** of: another valid
operating observation, greater statistical power, a resolved paper position,
better calibration evidence, a strengthened or weakened research asset, a
validated negative, a detected integrity failure, a corrected defect, better
reproducibility, better uptime, sharper diagnostics, a justified reduction in
uncertainty — **or proof that nothing warranted changing.**

It is **never**: more trades, more BUY/SELL decisions, a higher apparent win
rate from too few observations, more code, more hypotheses, more indicators,
weaker gates, optimistic estimates, or a positive finding every day.

### Why zero knowledge gain is allowed

`NET KNOWLEDGE GAIN: 0` is a legitimate result and is printed as zero. A
research system that feels obliged to report a discovery every day will
eventually manufacture one. Weakened findings and findings placed under review
count **against** the total, because a day that undermines a held conclusion
leaves the project knowing less than it thought.

### Why historical replay is evaluation, not training

Replay never fits parameters. It evaluates a rule that was fixed *before* the
replay ran, on data the rule has never seen, walk-forward and point-in-time. A
replay that tuned anything would be reporting its own training error.

### Signal opportunity is not signal firing

*Did the signal fire?* is uninformative on its own — `signal_fired = 0.00` with
sd 0.00 looks identical whether the signal is correctly quiet or broken. The
question that separates them is *should a qualifying opportunity have existed?*,
which is answerable from decision-time information. See
[`PREREGISTRATION_day17_opportunity.md`](PREREGISTRATION_day17_opportunity.md).

### The 1-in-7 engineering prediction metric

`M8`: 1 of 7 engineering predictions about this system's bottlenecks has been
correct. It measures **engineering intuition** and is never mixed with signal
accuracy, trade win rate, Decision Quality, or calibration. It is the reason
measurement precedes building in every cycle.

---

## 10. What remains UNMEASURABLE, and why

| metric | why |
|---|---|
| Position Decision Quality, win rate, total return, expectancy, profit factor, Sharpe, Sortino, max drawdown, volatility, equity curve, SPY comparison, alpha | **0 paper positions have ever been opened.** The signal has never fired. |
| calibration, reliability, Brier, ECE | **0 resolved predictions.** Gated behind `A-M5` (>=30 resolutions plus human review). |
| confirmed-miss rate | no missed-opportunity candidate has completed its horizon yet |

These print as `UNMEASURABLE` with the reason — never `0`, never `--`, never
omitted. Zero positions is not a 0% win rate; it is the *absence* of a win
rate, and printing 0% invites a reader to compare it to something.

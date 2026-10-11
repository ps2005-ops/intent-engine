# ECON_V4_FINAL_QUALIFICATION

Session of 2026-10-11, continuing 2026-10-09. **Wave 1 complete, and Wave 6
(deployment + live proof) complete.** Waves 2–5 not reached. This document separates what is proven from what is not, and
distinguishes engineering improvement from predictive improvement — they are
not the same thing and must not be summed.

## Identity

| | |
|---|---|
| Runtime root | `/Users/prathamsharma/intent-engine-market` |
| Runtime HEAD at session start | `9b01ff1b10d3` |
| **Runtime HEAD now (deployed)** | **`3b53037044c3`** |
| Remote | `origin/fix/econ-v4-calibration` = `3b53037044c3`, verified |
| Development worktree | `/Users/prathamsharma/ie-econ-v4-dev` |
| Development branch | `fix/econ-v4-calibration` |
| Development HEAD | `9fe55742` repairs, `3b530370` artifacts |
| Preserved patch | 1,783 lines, sha256 `02fd77cb5fc7d41e…`, already applied |

## The guard

| run | deselected | failures |
|---|---:|---|
| pristine `9b01ff1b10d3` (2026-10-09) | 10 | 13 |
| after calibration + eligibility repairs | 10 | 12 |
| after the live-test split | 37 | 7 (newly exposed by `future_dated`) |
| **after anchoring the drifted fixtures** | **37** | **0** |

```
5894 passed, 5 skipped, 37 deselected, 10 warnings in 527.55s
guard: suite EXIT=0 (explicitly checked)
```

Committed through the normal hooks. **No `--no-verify`. No test skipped,
xfailed, or weakened. No threshold lowered to match a live value.**

## Before and after

Engineering state, 2026-10-09 baseline vs now:

| metric | baseline | after | kind of change |
|---|---:|---:|---|
| Full regression guard | 12 failures | **0** | engineering |
| Live tests inside the offline guard | 27 | **0** | engineering |
| Deterministic tests covering split modules | 54 | 54 + 25 new | engineering |
| Mechanism grade capped by causal standing | **no** | **yes** | scientific architecture |
| Published `ESTABLISHED` mechanisms | 1 (unjustified) | **0** | scientific architecture |
| Skip statuses distinguishable | 1 for 4 situations | **3** | operational |
| `exit_code` hand-enumerated statuses | 2 | **0** (reads the group) | engineering |
| Future-dated prediction rejected | no | **yes** | correctness |
| Mechanisms observable | 4 | 4 | *unchanged* |
| Mechanisms gradeable | 2 | 2 | *unchanged* |
| Beliefs | 131 | 132 | *unchanged by this work* — +1 from the scheduled cycle |
| Beliefs repeatedly tested | 0 | **0** | *unchanged* |
| Untested beliefs | 99 | **100** | *unchanged by this work* — the new belief is untested |
| Resolved expectations | 32 | 32 | *unchanged* |
| Brier | 0.2138 | 0.2138 | *unchanged* |
| Brier skill vs climatology | −0.0576 | −0.0576 | *unchanged* |
| Forecast skill vs persistence | −0.0636 | −0.0636 | *unchanged* |
| PAPER positions | 0 | 0 | *unchanged* |
| Founder consumption receipts (local) | 0 | 0 | *unchanged* |

**Nothing in the lower block moved because of this work, and nothing should
have.** The two belief counts advanced by one overnight, from the scheduled
cycle — and the new belief landed on `regulatory_pressure`, a family
classified `NOT_A_CAUSAL_MECHANISM`, so it is untested and untestable. That is
the audit's central finding reproducing itself in real time, not progress. Wave 1 repaired
measurement, publication and operational honesty. None of that can improve
predictive accuracy, and claiming otherwise would be the inflation this
execution was told to avoid.

## Defects found and repaired this session

1. **A causal ceiling computed and never applied.** No module under `src/`
   imported `calibration_consistency`, so `demand_strengthening` published as
   ESTABLISHED at reliability 0.95 under a CONTESTED causal family. Now capped
   at publication with the overridden grade preserved. Live-proven read-only;
   `ESTABLISHED` no longer appears in the published counts.
   → `ECON_V4_CAUSAL_CEILING_REPAIR.md`

2. **Twelve guard failures were production monitors.** All 12 read the live
   ledger; a scheduled cycle appending turns one red with nothing broken. Split
   into five `*_live.py` modules per existing repository convention, assertions
   intact. 27 moved, not 12 — the other 15 were the same latent fault.
   → `ECON_V4_GUARD_REPAIR_REPORT.md`

3. **A missed cycle looked like a duplicate.** `SKIPPED_DUPLICATE` served four
   situations; re-labelling the launchd history shows **only 2 of 19 were
   genuine duplicates.** Three cycles were lost to host sleep on 2026-10-09/10
   while every surface reported success.
   → `ECON_V4_DAILY_SCHEDULER_PROOF.md`

4. **A future-dated prediction passed the freshness gate.** `age > max` is
   False for every negative age; a prediction 17 days ahead of `as_of` was
   returned eligible. Rejected now under its own rule `future_dated`.

5. **Seven more drifted fixtures.** Adding (4) turned `test_market_runtime.py`
   red in seven places — hardcoded `AS_OF`/`FUTURE` against a `now()`-stamping
   factory. Both modules anchored to `date.today()`.

## Five verdicts

**1. ENGINEERING COMPLETION — PARTIAL.**
Wave 1 is complete and committed green. Waves 2–6 are not started.

**2. DAILY OPERATION — PARTIAL.**
Deployment is live-proven: runtime HEAD advanced to `3b53037044c3`, imports
verified under the plist environment, and a real 15-step cycle completed on
the deployed code (EXIT=0) with the capped mechanism and v2 contract persisted
to a durable report and surviving a fresh-process reload.
On-schedule invocation is live-proven: a `day` cycle fired at 06:30 on
2026-10-11 and ran. But three cycles were silently lost to host sleep in the
preceding two days, and while a lost cycle is now *nameable*, it is still not
*recoverable* and raises no alert. Calling this PROVEN would require a
catch-up path and a missed-cycle alert that do not exist.

**3. LEARNING ARCHITECTURE — PARTIAL.**
Calibration is now measured properly and the causal ceiling is enforced at
publication. Repeated belief testing, defensible (Beta-Binomial / likelihood)
inference, and the negative-knowledge decision delta remain unimplemented. The
belief update is still the ±0.060/−0.080 constant.

**4. REAL FORWARD LEARNING — NOT_YET_PROVEN.**
32 resolved expectations, 0 beliefs tested twice. Forward learning requires
elapsed time and preregistered expectations resolving against genuinely future
observations. No session can manufacture it, and the spec says so.

**5. PREDICTIVE PERFORMANCE IMPROVEMENT — INCONCLUSIVE.**
Brier 0.2138 against a climatology baseline of 0.2021 — skill **−0.0576**, n=32.
Unchanged this session, because nothing this session could change it. The
engine's probabilities still carry less information than the base rate. The one
actionable signal remains the reliability curve: both bins are
**under-confident** (+0.082 and +0.254), i.e. it says ~0.59 where reality is
~0.70.

That is a correctable bias, and correcting it is explicitly *not* done here:
tuning priors on the same 32 outcomes used to measure them would be fitting
the adjustment to its own evaluation set.

## What remains, in priority order

1. **Missed-cycle recovery and alert** — the taxonomy now names the loss;
   nothing retries it or reports it.
2. **Repeated belief testing** — 0 of 131 beliefs tested twice is the binding
   constraint on every statistical claim downstream.
3. **`DEMAND_SIGNAL` routing behind an ownership gate** — 81 ledger items, the
   second most common evidence type, routed nowhere; specified and measured in
   `MECHANISM_FALSIFIABILITY_AUDIT.md`, blocked on per-item claim attribution.
4. **Defensible inference** to replace the constant update.
5. **Founder bridge transport** — producer and consumer agree on schema and
   have never shared a root.

---

# ADDENDUM — 2026-10-11, Wave 1 (scheduler recovery) complete

| | |
|---|---|
| Runtime HEAD | **`dc4eb541e851`** (deployed, verified under the plist env) |
| Remote | `origin/fix/econ-v4-calibration` = `dc4eb541e851…`, verified |
| Guard | **5932 passed, 5 skipped, 37 deselected, EXIT=0** (+38 tests) |

## What changed

The binding constraint named at the end of the previous session — "the
missed-cycle alert" — is built, tested, deployed and live-proven. See
`ECON_SCHEDULER_RECOVERY_PROOF.md`.

The headline measurement is new and was previously unobtainable:

```
schedule reliability : 86.2%   (125 of 145 due cycles did work)
cycles lost          : 20      (14 lock contention, 6 never invoked)
recoverable          : 7
permanently lost     : 13
```

Root cause verified as a **host-power fact, not a code defect**: host sleep
suspends a cycle that keeps holding the `flock`, so the next scheduled cycle
is refused; and a 38-hour hibernation at 1% battery swallowed three slots
outright.

## Revised before/after

| metric | 2026-10-09 | now | kind |
|---|---:|---:|---|
| Full regression guard | 12 failures | **0** (5932 pass) | engineering |
| Can the engine see a missed cycle? | **no** | **yes** | operational |
| Schedule reliability | unmeasurable | **86.2%** | measurement |
| Missed-cycle alert | none | **CRITICAL, live** | operational |
| Safe catch-up | none | **live, bounded, proven** | operational |
| Mechanisms gradeable | 2 | 2 | *unchanged* |
| Beliefs repeatedly tested | 0 | **0** | *unchanged* |
| Brier / skill | 0.2138 / −0.0576 | 0.2138 / −0.0576 | *unchanged* |
| PAPER positions | 0 | 0 | *unchanged* |

## Revised verdicts

**1. ENGINEERING — PARTIAL.** Waves 1 and 6 complete. Waves 2–5 and 7–10 of
the current spec are not started.

**2. DAILY OPERATION — PARTIAL**, and now for a *stated* reason rather than an
unmeasured one. Detection, alerting and recovery are live and proven. What
remains is not code: a MacBook at 1% battery hibernates through a scheduled
time, and the two fixes (a `pmset` scheduled wake, or an always-on host) are
both the user's to authorize. Reliability will keep reporting the truth
meanwhile.

**3. LEARNING ARCHITECTURE — PARTIAL.** Unchanged. Repeated belief testing and
defensible inference remain the gap.

**4. REAL FORWARD LEARNING — NOT_YET_PROVEN.** Unchanged: 0 of 132 beliefs
tested twice.

**5. PREDICTIVE IMPROVEMENT — INCONCLUSIVE.** Unchanged, and nothing in this
wave could change it. Worth saying plainly: **recovering 20 lost cycles would
have produced more evidence, not better predictions.** The two are separate,
and conflating them is how "LEARNING_ACCELERATING" got printed over a negative
Brier skill in the first place.

## What remains, in priority order

1. **Repeated belief testing** — 0 of 132 is the binding constraint on every
   statistical claim downstream.
2. **`DEMAND_SIGNAL` routing behind a per-item ownership gate** — 81 ledger
   items, second most common evidence type, routed nowhere.
3. **Defensible inference** to replace the ±0.060/−0.080 constant.
4. **Automatic catch-up on wake** — the command exists and yields correctly;
   nothing invokes it unattended yet.
5. **Founder bridge transport** — schemas agree, roots have never been shared.

# ECON_FINAL_QUALIFICATION

Session of 2026-10-09. Scope executed: **Batch A in full, Batch B's audit,
and two Batch C repairs.** Batches D, E and F were not reached. This document
states what is proven, what is not, and the one blocker that stops anything
from being committed.

## Status ladder, per claim

| claim | level |
|---|---|
| Repository / runtime truth established | **LIVE_PROVEN** |
| Production state backed up before any change | **LIVE_PROVEN** |
| 20-day audit reproduced from canonical state | **LIVE_PROVEN** |
| Mechanism falsifiability audited (5-way, 16 families) | **LIVE_PROVEN** |
| Hit rate separated from calibration | **TESTED + LIVE_PROVEN** (read-only) |
| Brier / log loss / reliability computed | **TESTED + LIVE_PROVEN** (read-only) |
| Future-dated prediction rejected (lookahead hole) | **TESTED** |
| Repairs committed | **BLOCKED** — see below |
| Repairs deployed to the runtime | **NOT DONE** |
| Repeated belief testing | **NOT IMPLEMENTED** |
| Bayesian / likelihood-based updating | **NOT IMPLEMENTED** |
| Negative-knowledge decision delta | **NOT IMPLEMENTED** |
| Founder transport repair | **NOT IMPLEMENTED** |
| Dossier version/write separation | **NOT IMPLEMENTED** |
| No-trade learning first-class | **NOT IMPLEMENTED** |
| Daily scheduler repaired | **NOT DONE** (diagnosed only) |
| FORWARD_LEARNING_PROVEN | **NOT POSSIBLE THIS SESSION** — needs elapsed time |
| IMPROVEMENT_PROVEN | **NOT CLAIMED** |

## The blocker: the pre-commit guard is red on untouched code

`git commit` runs the offline suite and requires EXIT=0. On the **pristine
tree at the runtime SHA `9b01ff1b10d3`**, with none of this session's changes
applied:

```
13 failed, 5879 passed, 5 skipped, 10 deselected in 580.98s
GUARD FAIL (suite): pytest EXIT=1 (need EXIT=0). Commit blocked.
```

All 13 were confirmed pre-existing by stashing every change and re-running.
One of the 13 was then fixed in this session (`test_stale_prediction_rejected`,
which was masking a real defect — see below), leaving **12**.

`--no-verify` was not used and must not be.

### The 12 remaining, by cause

**Eleven pin live mutable production state.** Two test modules hardcode the
production path:

```
tests/test_market_calibration_consistency.py:18
    "/Users/prathamsharma/intent-engine-market/reports/market/"
tests/test_market_learning_acceleration.py:22
    MARKET_ROOT = pathlib.Path("/Users/prathamsharma/intent-engine-market")
```

They then assert constants that the nightly cycle moves. One states the
problem in its own comment:

```python
# The production runtime appends nightly, so this constant has an
# expiry date. What is durable is that the self-tests are SEEN.
assert got["windows"]["recent"]["metrics"]["self_tests_refused"] >= 20.0
#   -> live value is now 12.0
```

Others drifted the same way: `known_nodes == 4` (now 5), `established == 4`
(now 5), `weakest_link.source == ORDERS` (now `CUSTOMER_STATE`),
`len(got) == 1` (now 2), `contradicted == 0` (now 1 — this is the first
contradiction `demand_strengthening` ever took, which is real learning the
test forbade).

These were **deliberately not re-baselined in this session.** Each needs a
judgment about which property is durable, and lowering a threshold to match
today's live value is the failure mode the repository's own standards forbid.
Doing eleven of those quickly is how a real guard gets weakened by accident.

**One is a genuine live-state alarm and must not be re-baselined at all:**

```
Incoherence(kind='MECHANISM_ABOVE_ITS_CAUSAL_CEILING',
            family='demand_strengthening',
            why='the causal family is CONTESTED, so the rule may still
                 predict but must not be read as a mechanism above CONTESTED')
```

`demand_strengthening` is published as `ESTABLISHED` (reliability 0.95) while
its causal family is `CONTESTED`. The mechanism's maturity has outrun its
causal evidence. This appeared *because* the family took its first
contradiction during the audit window. The test is correctly raising it. It
needs investigation, not a new baseline.

## Defects found and repaired

### 1. A hit rate reported as a calibration

`learning_health.calibration` set both `expectation_calibration` and
`belief_calibration` to `confirmed / resolved`, and the report rendered it as
"Expectation calibration: 0.72". The first proper score ever computed on the
32 resolved expectations:

| measure | value |
|---|---:|
| hit rate | 0.719 |
| Brier | 0.2138 |
| Brier, climatology baseline | 0.2021 |
| **Brier skill vs climatology** | **−0.0576** |
| log loss | 0.6196 |
| log loss, climatology | 0.5941 |
| **log loss skill** | **−0.0428** |
| forecast range | 0.564 … 0.654 (sd 0.019) |

The engine's probabilities carry **less** information than always guessing the
base rate, while the headline read 0.72. Contract bumped to
`market_learning_health.v2`; 60 v1 snapshots keep their meaning.

**New finding from the reliability curve:** both bins show positive gaps
(+0.082 at 0.5–0.6, +0.254 at 0.6–0.7). The priors are systematically
**under-confident** — the engine says ~0.59 where reality is ~0.70. A hit rate
cannot see this. It is a correctable bias and the most concrete accuracy
improvement now available.

### 2. A future-dated prediction passed the freshness gate

`paper/eligibility.py` checked `age > max_data_age_days`. `_age_days` returns
`as_of - created_at`, which is **negative** when a prediction is stamped after
the evaluation date — and no negative number is greater than 5. Measured: a
prediction dated 17 days after `as_of` was returned `eligible=True`.

Now rejected under its own rule `future_dated`, kept distinct from
`stale_data` because a clock fault and a backfill fault are different
findings.

This also explains the 13th failure. `record_prediction` stamps the real
current date and takes no override, so the module-level `AS_OF = "2026-07-24"`
had drifted into the past: **every test in that file was exercising the
future-dated path** and passing only because the hole existed. The tests now
derive `as_of` from the prediction itself.

## Operational findings (not yet repaired)

**Day cycles are silently skipped.** Tallied from the launchd logs:
`SKIPPED_NO_NEW_MARKET_SESSION` 78, `COMPLETED` 43, `SKIPPED_DUPLICATE` 17,
with 14 occurrences of "another cycle holds the lock". A skipped cycle still
exits 0, so launchd records success and the health job reports **100% step
reliability for every step** while day cycles are missing from the ledger
entirely (none recorded for 2026-10-04, -05, -06, -08).

One launchd invocation also replays a backlog of dates, so a long-running
invocation collides with the next scheduled one — which is the lock
contention above. The day cycle observed during this session ran for over 11
minutes.

**`expectations_tested` is ~100 every cycle against 32 lifetime
resolutions.** The reconciliation path re-examines ~100 open expectations
daily and almost none can ever resolve, because they sit on families that are
unfalsifiable by construction. "Never tested" is not neglect — testing them
is a structural no-op.

## What was NOT done, explicitly

Batches D (founder integration), E (continuous operations) and F (live
qualification and freeze) were not started. No scheduler change was made. No
deployment was made to the runtime worktree — its HEAD is untouched at
`9b01ff1b10d3`, and the live tree was never edited while a cycle was in
flight.

Repeated belief testing, defensible Bayesian updating, the negative-knowledge
decision delta, dossier version/write separation and no-trade learning remain
unimplemented. The `DEMAND_SIGNAL` routing repair is specified and measured
but deliberately not applied — see `MECHANISM_FALSIFIABILITY_AUDIT.md` for the
attribution gate it needs first.

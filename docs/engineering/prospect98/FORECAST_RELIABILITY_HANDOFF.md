# Forecast registration reliability: handoff to the System Equilibrium runtime upgrade

| | |
|---|---|
| Fix | `origin/fix/forward-register-reliability` @ 360a996b (guard 13,159 passed) |
| Base | `integration/unified-2026-11-25` @ f2ebf46f; merges cleanly into the current integration head (checked 2026-11-28 14:41 EST) |
| Production | learning runtime `~/ie-learning-runtime` @ f7690938 -- **unchanged**; this program deploys nothing |
| Defect | 2026-11-27 19:17 ET: one SPY timeout, no retry, `KeyError('SPY')`, rc=1; nothing registered |
| Change | bounded retry (2 extra attempts, 2 s / 8 s) on transient network errors only; parse failures are answers; missing benchmark -> `BENCHMARK_UNAVAILABLE`, rc=2, writes nothing (no snapshot, no ledger row); no stale or alternate price; resolution was already safe (missing series = WAIT, never VOID within grace) |
| Contracts | untouched: 977 forward-shadow forecasts (resolvable from 2026-12-11), the econ expectation due 2026-12-25 (1 of 13; the other 12 mature 2027-02-23..2027-08-22), next cohort ~2026-12-09 under amendment A1 |

## Upgrade procedure (for the runtime owner; not run from here)

1. Merge `fix/forward-register-reliability` into the integration branch in a fresh worktree; run the full guard there.
2. Follow the existing `~/intent-engine-safety-backups/UPGRADE_*` pattern: back up the canonical ledgers with SHA256SUMS, create an immutable runtime worktree at the merged SHA, repoint `com.intentengine.learning.daily` only, refuse while a job holds its lock.
3. Verify on a copy of the forward ledger: `register --if-due` with the SPY fetch forced to time out returns rc=2 and appends nothing; a normal run is byte-identical in its decision to f7690938.
4. Do it **before ~2026-12-09** (the next cohort), and not inside the 2026-12-10..12-11 resolution window.

## Rollback

`git -C ~/ie-learning-runtime checkout --detach f7690938` (the current production SHA), then reload the learning plist.

## Still to verify (owner)

Today's 19:15 learning run (2026-11-28) -- whether the timeout recurs on f7690938.

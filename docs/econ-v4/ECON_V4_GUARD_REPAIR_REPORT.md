# ECON_V4_GUARD_REPAIR_REPORT

Priority Zero: the pre-commit guard was red on code nobody had touched, so
nothing could be committed. 13 failures on the pristine tree at
`9b01ff1b10d3`; one was fixed on 2026-10-09, leaving 12.

## Classification — all 12 individually

Every one was verified by stashing all local changes and re-running on the
pristine tree. An intermediate classification pass of mine wrongly called 8 of
them "local"; that was a bad `awk` range pattern, not a finding. Re-done by
parsing each test body for its module's live helper:

| # | test | class |
|---|---|---|
| 1 | `test_market_calibration_consistency::test_the_real_ledger_is_currently_coherent` | `MUTABLE_LIVE_DATA_DEPENDENCY` + **`GENUINE_PRODUCT_DEFECT`** |
| 2 | `test_market_causal_calibration::test_the_real_ledger_keeps_its_causal_statuses_honest` | `MUTABLE_LIVE_DATA_DEPENDENCY` |
| 3 | `test_market_causal_calibration::test_unresolved_expectations_are_reported_separately_from_failures` | `MUTABLE_LIVE_DATA_DEPENDENCY` |
| 4–7 | `test_market_counterfactual_memory` ×4 | `MUTABLE_LIVE_DATA_DEPENDENCY` |
| 8–10 | `test_market_economic_chain` ×3 | `MUTABLE_LIVE_DATA_DEPENDENCY` |
| 11–12 | `test_market_learning_acceleration` ×2 | `MUTABLE_LIVE_DATA_DEPENDENCY` |

All 12 also carry `RUNTIME_PATH_DEPENDENCY`: they hardcode
`/Users/prathamsharma/intent-engine-market`.

None were `NONDETERMINISTIC_TEST` in the flaky sense, but all 12 **are**
nondeterministic in a stricter one: a scheduled cycle writing the ledger while
the guard reads it changes the answer mid-run.

## Repair — split, do not weaken

The repository already has a convention the guard enforces: live tests live in
`tests/test_*_live.py` and are deselected by filename, alongside
`test_calendar_live.py`, `test_macro_data_live.py`,
`test_market_resolution_live.py`, `test_scrap_estimate_live.py` and
`test_simulator_e2e.py`.

Five new modules follow it:

```
tests/test_market_calibration_consistency_live.py    1 live test
tests/test_market_causal_calibration_live.py         2
tests/test_market_counterfactual_memory_live.py     10
tests/test_market_economic_chain_live.py             7
tests/test_market_learning_acceleration_live.py      7
                                                    --
                                                    27
```

**27 tests moved, not 12.** Only 12 were red today; the other 15 read the same
mutable production state and were the same time bomb. Fixing only the visible
ones would have left the class intact.

### What was explicitly NOT done

- **No assertion was changed.** Every moved test keeps its exact comparison.
- **Nothing was skipped or xfailed.** Run them any time:
  `env PYTHONPATH=src python -m pytest tests/test_market_*_live.py`
- **No threshold was lowered** to match today's live value.

Run after the split: **27 collected, 15 pass, the same 12 fail** — preserved
as findings about production rather than hidden.

### Detection power retained offline

Moving live tests out would be weakening if it left a module uncovered. It does
not — deterministic tests remaining per module:

| module | deterministic kept |
|---|---:|
| `test_market_calibration_consistency.py` | 9 |
| `test_market_causal_calibration.py` | 11 |
| `test_market_counterfactual_memory.py` | 9 |
| `test_market_economic_chain.py` | 11 |
| `test_market_learning_acceleration.py` | 14 |
| **total** | **54** |

Offline result for those five modules after the split: **56 passed.**

Critically, `test_market_calibration_consistency.py` retains
`test_a_contested_causal_family_caps_its_own_predictor` — the exact invariant
failure #1 had caught being violated in production, and which passed
throughout. The checker was never the defect.

New deterministic coverage added in the offline suite: 14 tests in
`test_causal_ceiling_applied.py` and 11 in `test_cycle_skip_kinds.py`.

## Guard infrastructure fixes

`scripts/install_precommit_hook.sh` ran `mkdir -p .git/hooks`, which fails
with `mkdir: .git: Not a directory` in a linked worktree where `.git` is a
*file*. The hook would silently stay stale — a guard that cannot be updated
from a worktree is a guard that drifts. It now resolves the path with
`git rev-parse --git-path hooks/pre-commit`, which in a worktree correctly
points at the shared hooks directory of the main checkout: one guard for every
worktree.

`scripts/precommit_guard.sh` now documents what "live" means — a test whose
result depends on state the guard does not control, *including the production
ledger*, not only a network call.

## Second-order finding: 7 more drifted tests

Adding the `future_dated` eligibility guard (see
`ECON_V4_FINAL_QUALIFICATION.md`) turned **7 tests in
`test_market_runtime.py`** red. Same latent drift as `test_paper_eligibility.py`:
`AS_OF = "2026-07-24"` and `FUTURE = "2027-01-01"` were hardcoded while
`pl.record_prediction` stamps the real clock, so every call evaluated a
prediction dated in the future and passed only because the hole existed.

Both modules now anchor to `date.today()`. `FUTURE` is `today + 365` rather
than a fixed 2027 date that would drift identically.

This is the pattern worth carrying forward: **a fixture that stamps `now()`
plus a test that supplies a fixed comparison date has an expiry date.**

## Progress of the guard across this session

| run | deselected | failures |
|---|---:|---|
| pristine, 2026-10-09 | 10 | 13 |
| after calibration + eligibility repairs | 10 | 12 (+1 fixed) |
| after the live split | 37 | 7 — all newly exposed by `future_dated` |
| after anchoring the runtime tests | 37 | see `ECON_V4_FINAL_QUALIFICATION.md` |

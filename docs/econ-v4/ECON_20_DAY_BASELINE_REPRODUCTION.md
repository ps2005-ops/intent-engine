# ECON_20_DAY_BASELINE_REPRODUCTION

Window **2026-09-19 -> 2026-10-08**, reproduced from
`learning_health_history.jsonl` and the append-only ledger. The original audit
figures are preserved; this is an independent re-read of the same canonical
state, not a replacement.

## Reproduced deltas

| metric | 2026-09-19 | 2026-10-08 | delta |
|---|---:|---:|---:|
| Beliefs held | 110 | 130 | +20 |
| Beliefs never tested | 86 | 98 | +12 |
| Evidence items | 757 | 923 | +166 |
| Validated knowledge | 24 | 32 | +8 |
| Expectations total | 110 | 130 | +20 |
| Expectations resolved | 24 | 32 | +8 |
| Companies observed | 28 | 28 | +0 |
| Dossiers counted | 62 | 62 | +0 |

**Verdict: the audit reproduces.** Growth is real on volume metrics and flat
on reach metrics; `beliefs_never_tested` grew by more in absolute terms than
tested beliefs did.

## Accuracy over the same window

- Through 2026-09-19: 18/24 = 75.0%
- Inside the window:     5/8 = 62.5%
- All time:              23/32 = 71.9%

The in-window cohort is **8 resolutions**. At that size the change
is not separable from noise (Fisher exact two-sided p = 0.65 on 18/24 vs 5/8),
so the honest reading is *no detectable change in accuracy*, not a decline.

## Status labels are not accuracy

`status` across the window moved between `LEARNING_ACCELERATING`,
`LEARNING_HEALTHY` and `LEARNING_DEGRADING` while the hit rate stayed inside
its confidence interval throughout. The label is computed from
validated-knowledge velocity, which is a volume measure.

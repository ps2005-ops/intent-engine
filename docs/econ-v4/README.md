# Economic Intelligence V4 — artifact index

Every numerical claim in these documents is read from canonical state — the
append-only ledger, the cycle reports, the launchd plists, or the routing
table in source. `scripts/generate_econ_v4_artifacts.py` regenerates the
data-derived ones, so a stale figure can be refuted by re-running it rather
than argued about.

## Wave 1 — recovery and the guard (COMPLETE)

| artifact | what it establishes |
|---|---|
| [ECON_V4_RECOVERY_AND_PATCH_PROOF.md](ECON_V4_RECOVERY_AND_PATCH_PROOF.md) | three-way patch verification; the preserved patch was already applied, byte-identical |
| [ECON_V4_GUARD_REPAIR_REPORT.md](ECON_V4_GUARD_REPAIR_REPORT.md) | all 12 guard failures classified and resolved; 27 live tests split out, 0 weakened |
| [ECON_V4_CAUSAL_CEILING_REPAIR.md](ECON_V4_CAUSAL_CEILING_REPAIR.md) | a ceiling computed since it was written and never applied; now applied, with live proof |
| [ECON_V4_DAILY_SCHEDULER_PROOF.md](ECON_V4_DAILY_SCHEDULER_PROOF.md) | three cycles lost to sleep; `SKIPPED_DUPLICATE` was wrong 17 of 19 times |

## Baseline and audit (from 2026-10-09, still current)

| artifact | what it establishes |
|---|---|
| [ECON_REPOSITORY_RUNTIME_TRUTH.md](ECON_REPOSITORY_RUNTIME_TRUTH.md) | roots, worktrees, interpreter, scheduler, ledger integrity |
| [ECON_20_DAY_BASELINE_REPRODUCTION.md](ECON_20_DAY_BASELINE_REPRODUCTION.md) | the 2026-09-19 → 10-08 audit, reproduced independently |
| [MECHANISM_FALSIFIABILITY_AUDIT.md](MECHANISM_FALSIFIABILITY_AUDIT.md) | 16 mechanisms, five-way classification, and why 12 must NOT be bound |
| [BELIEF_INFERENCE_AND_CALIBRATION.md](BELIEF_INFERENCE_AND_CALIBRATION.md) | the ±0.060/−0.080 constant, and the first proper score ever computed |

## Qualification

| artifact | what it establishes |
|---|---|
| [ECON_V4_FINAL_QUALIFICATION.md](ECON_V4_FINAL_QUALIFICATION.md) | current verdicts, before/after table, what is NOT done |
| [ECON_FINAL_QUALIFICATION.md](ECON_FINAL_QUALIFICATION.md) | the 2026-10-09 session's qualification, superseded but preserved |

## Not yet written

These correspond to waves not reached. They are absent rather than
stubbed, because an artifact asserting an unproven claim is worse than no
artifact:

`ECON_V4_OBSERVATION_ROUTING_PROOF` · `ECON_V4_REPEATED_LEARNING_PROOF` ·
`ECON_V4_FORECAST_SKILL` · `ECON_V4_NEGATIVE_KNOWLEDGE_DELTA` ·
`ECON_V4_FOUNDER_BRIDGE_PROOF` · `ECON_V4_PAPER_SHADOW_PROOF` ·
`ECON_V4_LIVE_CYCLE_PROOF` · `ECON_V4_NEXT_30_DAY_VALIDATION`

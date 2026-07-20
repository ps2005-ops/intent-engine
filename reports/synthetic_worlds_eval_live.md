# Synthetic-world reasoning eval — LIVE leg (extraction -> matcher)

*Latest run 2026-07-20, seed 20260719, 89 extraction calls (≈$1.78 estimated), generator v1.1. Frozen prompt sha256 verified before the first call. Every run is archived in synthetic_worlds_runs/ and summarized below — the live leg is non-deterministic, so cross-run variance on the same worlds is part of the measurement.*

SCOPE (recorded so it cannot be misquoted): this is a causal-reasoning diagnostic on constructed fictional worlds. It is NOT a forward-market accuracy measure, NOT calibration evidence, NOT a marketing claim, and it changes no prompt, enum, or library data. Fictional worlds cannot be memorized; that is the point of the design.

- single worlds: constructed truth recovered in 68/69
- mixed worlds: both mechanisms recovered in 12/12
- control worlds (healthy, condition-free): clean silence in 8/8 — no hallucinated conditions on any control this run.

## Run history (append-only)

| run | gen | singles | mixed | controls clean | recall | precision |
|---|---|---|---|---|---|---|
| live_20260720T015341_v1.0 | v1.0 | 68/69 | 12/12 | 3/8 | 1.0 | 0.677 |
| live_20260720T015341_v1.1 | v1.1 | 68/69 | 12/12 | 8/8 | 1.0 | 0.907 |

Per-world detail: synthetic_worlds_eval_live.json (latest) and synthetic_worlds_runs/<run_id>.json (all runs).

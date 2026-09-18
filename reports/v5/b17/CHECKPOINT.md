# V5 BATCH 17 — CHECKPOINT

STARTING founder `545b881` · market `fbcbacc` · manifest 1.0.0 · graph 33/C10/R8/W14/B1

## BACKEND

`CREDITS_EXHAUSTED`, confirmed against the real provider through
`strategic_intelligence.analyst.runner.default_client` (`claude-sonnet-5`),
request `req_011Ce1MT2t4fb8fH1QiSuDCC`. Probed once. Not re-probed.

Breaker-10 was NOT run and nothing was substituted for it.

## COMPLETED VERTICALS

1. **The gate's backend criteria are checked, not asserted.** The six
   BLOCKED_EXTERNAL criteria were a static tuple of titles. Emitting them
   unconditionally asserts a claim the gate never tested — that credit is the
   ONLY thing missing. Each criterion now names a producer probe. A missing
   producer is FAIL, never BLOCK: a block routes the reader to the billing
   page, and for a criterion nothing can compute, that is the wrong page.

2. **The second iteration can now meet the first one's priors.** The wave
   runner rooted every run at a fresh `mkdtemp`, so a rerun met its own priors
   as absent and reported FIRST_OBSERVATION for every company for ever. `--root`
   reuses a previous run's root; a missing root is refused rather than created,
   because creating it reproduces FIRST_OBSERVATION and looks like a pass.

## MEASURED BLOCKER

External credit, and only that — but that sentence is now *verified* rather
than assumed. Before this batch it was false: criterion 14 had no producer at
any credit balance, and the gate could not see it.

## GATE

12 PASS · 0 FAIL · 6 BLOCKED_EXTERNAL · WAVE_30 CLOSED.
All six blocks now carry a named, existence-checked producer.

## STILL MISSING (engineering, not credit)

No producer emits the §48 artifacts `BREAKER10_REOBSERVATION_VALUE.json`,
`BREAKER10_LEARNING_QUALITY.json`, `BREAKER10_FOUNDER_CONSUMPTION.json`. The
underlying vocabularies exist — `learning_attribution` (quality),
`demo_dossier.assembler` (consumption) — and the wave record captures the
fields, so these are aggregation steps over a wave result, not new subsystems.
The re-observation *value* vocabulary (NEW_INFORMATION / REQUIRED_MONITORING /
EXPECTATION_TEST / DECAY_REVIEW / SOURCE_HEALTH_WATCH / SAME_DOCUMENT_NEW_FETCH
/ DUPLICATE_NO_VALUE) exists only in `intent_engine.market`, which the founder
branch cannot import.

## NEXT ACTION

Restore Anthropic credit. Then, unchanged:

```
PYTHONPATH=src python3 scripts/v5_breaker_wave.py --label baseline \
    --env-file /path/to/.env --out reports/v5/b17
```

Note the printed `runtime root`, then run the second iteration against it:

```
PYTHONPATH=src python3 scripts/v5_breaker_wave.py --label second_iteration \
    --env-file /path/to/.env --root <that root> --out reports/v5/b17
```

Then `v5_learning_funnel.py` on the results, then re-run the gate.

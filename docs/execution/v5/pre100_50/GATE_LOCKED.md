# PRE-100 50-COMPANY CYCLE — LOCKED

Locked by the programme owner on 2026-08-22. This file is the authoritative
state of the 50-company cycle. It is not to be re-litigated by a later
session; the targeted-100 cycle is the next unit of work and has NOT started.

```
PRE100_50_COMPANY_GATE          = PASS

CORE_ARCHITECTURE_FROZEN        = YES
50_COMPANY_BASELINE             = FROZEN
LIFECYCLE                       = PASS
INTELLIGENCE                    = PASS
ZERO_ANTHROPIC                  = PASS
PERFORMANCE                     = NOT DONE
RECOMMENDATION_PERSONALIZATION  = NOT DONE
COMPETITOR_ENTITY_QUALITY       = NOT DONE
FULL_UI_VALIDATION              = NOT DONE
TARGETED_100_READY              = YES
```

## What the PASS rests on

| | |
|---|---|
| final SHA | `5c25f9c` (code identical to `336311b`; docs only) |
| baseline | 50/50 captures on `589518f`, `live_captures/589518f/` |
| scores | p10 **8.60** · p50 **9.20** · p90 **9.60** — 40 ≥ 9, 6 in 8–9, 4 below |
| lifecycle | raw 500 **0** · wrong identity **0** · lost run **0** · CSS leak **0** · enum leak **0** · raw repr **0** · redirect loop **0** |
| zero-Anthropic | every number produced with the LLM analyst down (0 successful calls for 23h+) |
| guard | 7125 passed, 16 skipped, 1 xfailed, 0 failed |
| D4 reproof | 8 companies on `336311b`; false substitute removed from NVIDIA, Micron, TI; Qualcomm correctly retained (true positive); 4 controls unchanged |
| SEV-1 proof | 151 ledger-corruption events before the repair, **0** after, across ~9h and 50+ live analyses |

## The four NOT DONE items, with their exact next repair

1. **PERFORMANCE** — `webapp/app.py::_progress` releases only when
   `result_readiness().opens_result`, which requires full composition.
   first-useful p50 163s / p90 377s / p95 480s, 0/50 under 30s. The two-wave
   patch and its 10 tests are preserved at
   `docs/execution/v5/pre100_50/R3_progressive_first_useful.patch`; not
   shipped because a second composition doubles the worker's most expensive
   step. Measure `T_identity`, `T_min_evidence`, `T_economic_model` first.

2. **RECOMMENDATION_PERSONALIZATION** — `strategic_read._action_now`.
   18/50 use the bounded fallback; 4 pharmaceutical companies are
   byte-identical. Every input available to that fallback is a class prior,
   so inverting its precedence changes wording and closes nothing. Raise the
   hit rate of `run_decision.recommended_next_move` (present for 32/50).

3. **COMPETITOR_ENTITY_QUALITY** — named-alternative extractor renders
   "Joint Venture", "The buyer" ×3, "Permian Basin", "LM". ~6 of 10 rendered
   lines. Pre-existing (byte-identical on `589518f` and `336311b`). Require
   the candidate to appear as a grammatical subject or carry a corporate
   suffix. Not a stoplist — that shape failed twice in this cycle.

4. **FULL_UI_VALIDATION** — verified landing, demo entry, autocomplete,
   progress, intro and `/full` at 390 dark and 1440 light on one company
   (`/full` live: 31,375 chars, no CSS in text, no enums, scrollW==clientW).
   The full twelve-surface × six-company × three-width matrix was not run.

## Carried forward unchanged for the targeted 100

harness `scripts/pre100_convergence_batch.py` + `pre100_batch_journey.py`,
scorer `pre100/quality.py::score_corpus`, calibration
`tests/test_the_scorer_is_calibrated_against_filler.py`. See
`TARGETED_100_HANDOFF.md`, including the two selector traps and the detached
launch requirement.

**The 100-company cycle has not been started.**

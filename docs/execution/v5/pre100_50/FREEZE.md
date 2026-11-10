# PRE-100 50-COMPANY BASELINE — FROZEN

## What is frozen

| item | value |
|---|---|
| final SHA | `336311b` |
| baseline captures | `docs/execution/v5/pre100_50/live_captures/589518f/` (50 companies) |
| baseline scores | `BASELINE_50_PRE_REPAIR.json` |
| universe | `UNIVERSE.json`, 50 companies, frozen 2026-08-20 |
| scorer | `src/intent_engine/pre100/quality.py` — `score_corpus` |
| calibration | `tests/test_the_scorer_is_calibrated_against_filler.py` |
| harness | `scripts/pre100_convergence_batch.py` + `pre100_batch_journey.py` |

## Measured baseline (50/50, calibrated scorer, zero-Anthropic path)

```
core_mean   p10 8.60   p50 9.20   p90 9.60
            >=9: 40    8-9: 6     <8: 4
lifecycle   31 FULL    18 THIN    1 LIMITED
leaks       CSS 0      enum 0     raw repr 0
identity    wrong 0    synthetic-demo leak 0
lost runs   0          raw 500s 0
latency     first-useful p50 163s  p90 377s  p95 480s   <=30s: 0/50
```

The four below 8 are all honest bounded outputs, not wrong analyses:
Deere 6.6 ("Limited analysis", 3 pages read), Exxon 7.2 and Pfizer 7.6 (full
analyses with thin independent evidence), Stripe 7.8 (private company, "across
the public record").

**Every number above is the DETERMINISTIC path.** The Anthropic key on this
preview has been out of credit since 2026-08-21 08:26 with zero successful
analyst calls, so the engine produced all of this with no LLM at all. That is
the zero-Anthropic baseline the gate asked for, and it is a property of the
product worth keeping: the deterministic engine alone reaches p50 9.20.

## Defects closed this session, with live proof

1. **Append-only ledger corruption (SEV-1).** `read_all` parsed the whole log
   and raised on the first bad line, so `create_run`, `/progress`,
   `/runs/<id>` and the Q&A route died together and stayed dead. **151
   corruption events** in production before the repair; **zero** in the ~9
   hours and 50+ live analyses since.
2. **Quota charged for runs that never opened.** Every 500 also spent one of
   ten hourly analyses. Now reserve/commit/release.
3. **A stylesheet rendered as the opening content of `/full`**, and the
   `.challenge` card was unstyled on every company. 0/50 after.
4. **Internal enum constants as customer copy on `/evidence`**
   (`DISCOVERY_PARTIAL`, `HAVE_INDEPENDENT`, `DIRECTLY_RELEVANT`). 0/50 after.
5. **An HR sentence as the economic engine.** Meta read "runs on competitive
   compensation and a wide range of benefits"; now "runs on revenue by
   displaying ad products on Facebook, Instagram, Messenger".
6. **D4 — substitutes from a sector prior.** Eight clauses served 22
   companies; seven semiconductor firms were told their customers could
   substitute "rental and used equipment". Now gated on the subject's own
   evidence.
7. **The scorer itself.** Three variants gave p50 9.27 / 7.82 / 10.00 on one
   corpus. Repaired and calibrated against a filler control (5.82 vs 9.20).

## Known limitations carried forward

1. **PERFORMANCE_GATE = FAIL.** first-useful p50 163s, p95 480s, 0/50 under
   30s. Mechanism exact: `/progress` releases only when
   `result_readiness().opens_result`, which requires full composition. The
   two-wave repair is built (`R3_progressive_first_useful.patch`, 10 tests)
   but was not shipped — a second composition doubles the worker's most
   expensive step and turned two existing tests red.
2. **Recommendation collapse on 18 of 50.** The bounded fallback's action is
   class-derived at every available input; four pharmaceutical companies get
   byte-identical text. The repair is to raise the hit rate of
   `run_decision.recommended_next_move`, not to improve the fallback.
3. **18 of 50 reached "did not add enough independent evidence."** Retrieval
   breadth, not reasoning quality.

# Targeted-100 handoff

The 100-company cycle reuses everything below unchanged. It exists to validate
GENERALISATION, not to rebuild the evaluation system.

## What to reuse, exactly as-is

| piece | path |
|---|---|
| orchestrator (lock, quota window, resume, requeue) | `scripts/pre100_convergence_batch.py` |
| customer journey (posts the real form incl. `suggest_domain`) | `scripts/pre100_batch_journey.py` |
| scorer + corpus pass | `src/intent_engine/pre100/quality.py` (`score_corpus`) |
| calibration control | `tests/test_the_scorer_is_calibrated_against_filler.py` |
| boilerplate controls | `tests/test_the_scorer_cannot_score_boilerplate_ten.py` |

## Run it

```bash
python scripts/pre100_convergence_batch.py <OUTDIR>/<SHA> \
  --per-window 10 --window 3600 --concurrency 1 --quota-wait 600
```

Launch it DETACHED (`scripts`-adjacent `detach.py` pattern: `os.setsid()` plus a
double fork). A batch left in the launching shell's process group was silently
killed twice mid-company, with nothing in its log — a silent death is a signal,
and `nohup` alone does not leave the session.

Two selector traps, both measured:

* `--only` splits on a COMMA when no semicolon is present, so
  `--only "Stripe, Inc."` matches nothing. Always pass a trailing semicolon:
  `--only "Stripe, Inc.;"`.
* `load_universe` filters on `resolvable`, which was frozen by asking the SEC
  registrant table and therefore means "has a CIK". An explicit `--only` now
  overrides it, which is how the one private company in the universe is
  reachable at all.

## Scoring rules that must not be relaxed

1. **Run the calibration control before trusting any number.** Three variants
   of this scorer produced p50 9.27 / 7.82 / 10.00 on the SAME captures. The
   filler control is what separates a repair from a re-fit.
2. **Score the corpus, not the company.** `score_corpus` strips section
   furniture and caps passages repeated across companies. Per-company scoring
   cannot see template collapse, which is the defect §14 exists to catch.
3. **A uniform result is an instrument tell.** Five dimensions scoring exactly
   6.00 with zero variance across 19 companies was the scorer, not the product.
   Check the instrument before touching a producer.
4. **Build cues from the product's vocabulary, not the rubric's.**
   `economic_reasoning` looked for "revenue engine" and "unit economics" —
   zero occurrences in 210 pages. `recommendation` said "What to do next"
   while the product's own heading says "What to do now".

## Known limitations carried forward

* First-useful latency: the two-wave progressive path is new and measured on a
  small reproof cohort only. The 100 is where its distribution gets established.
* `recommendation` opens with a shared sentence on 16 of 49 companies.
* 17 of 49 companies reached "did not add enough independent evidence".
* All measurements to date are of the ZERO-ANTHROPIC deterministic path.

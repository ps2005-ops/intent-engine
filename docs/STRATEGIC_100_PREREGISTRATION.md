# Strategic 100 — pre-registration

**Status: BLOCKED** by the interactive performance gate
(`docs/INTERACTIVE_PERFORMANCE.md`). This document is written *before* results
exist so the experiment cannot be reinterpreted after them.

## Why it is blocked

A 50-company batch can pass while an interactive Apple request hangs, because
batch coverage and production request-path performance are different tests. Run
against an unmeasured request path, the 100-company experiment would spend its
budget measuring timeout, network and orchestration defects and report them as
findings about strategic intelligence.

The gate exists so the 100 measures **intelligence** rather than **whether
Render and the retrieval pipeline survive**.

## Unblock conditions (all required)

1. Apple regression passes on the deployed service — cold, warm, retry.
2. Tier-1 cohort: ≥90% core success, p50 ≤30s, p90 ≤45s.
3. No request over the hard budget without either a usable bounded-gap result
   or an explicit terminal failure.
4. No indefinite `RUNNING` jobs; every job reaches a terminal state.
5. Optimized output preserves intelligence quality (§45 parity).
6. Economic intelligence still live.
7. Cold and warm behaviour both measured.
8. Provider failure degrades predictably.
9. The benchmark is of the **deployed** service, not a local run.

Then, and only then: **freeze the optimized SHA** and run the 100 against that
frozen build. Running it against a moving tree would mean the cohort was
analysed by more than one version of the product.

## Pre-registered cohort design

Fixed **before** results. Companies are not chosen or dropped afterwards; a
company that fails is a finding, not a sampling error.

| Class | n | Why it is in |
|---|---|---|
| Mega-cap technology | 12 | highest coverage — the ceiling case |
| Semiconductor | 8 | capital cycle, concentrated customers |
| Financial / banking | 10 | regulated disclosure, unusual unit economics |
| Payments | 5 | two-sided network |
| Industrial / capital goods | 10 | cyclical, backlog-driven |
| Enterprise software | 12 | the archetype the engine was built on |
| Consumer discretionary | 10 | brand and traffic exposure |
| Consumer staples / retail | 8 | thin margin, volume sensitivity |
| Energy / commodity producer | 6 | price-taker economics |
| Healthcare / pharma | 7 | pipeline and regulatory exposure |
| Utilities / rate base | 4 | regulated return |
| Sparse-evidence filers | 5 | little public product surface |
| Outside the validation manifest | 3 | the profile must be sparse and say so |

Complexity tiers: **simple** (single segment, one business model),
**composite** (multi-segment), **conglomerate** (unlike segments).

## Pre-registered measures

Declared with thresholds now, so an inert repair reads as a failure later.

- **Performance SLO** — tier-2 budget: p50 ≤60s, p90 ≤80s, hard ≤120s.
- **Evidence quality** — sources admitted, families covered, independent
  vantage present, provenance complete.
- **DecisionDelta** — a real comparator, never a placeholder.
- **DecisionDamage** — every declared damage kind must have a live detector.
- **Abstention** — reported as a *positive* result. Abstention is the evidence
  the model is selective rather than silent; a cohort with 0% abstention is a
  bug report about the instrument.
- **Company specificity** — per-class prior text must not make companies in
  one class byte-identical.
- **Provenance** — every claim traceable to the span that produced it.
- **CEO usefulness** — answers must differ across companies and industries.
- **Failure semantics** — `COMPLETE`, `COMPLETE_WITH_BOUNDED_GAPS`, or an
  explicit terminal failure. Never a spinner.

## Analysis rules fixed in advance

- Refusals (demo quota, provider rate limit) stay in the denominator and are
  reported separately; they are never quietly dropped.
- Cohort membership is not revised after results.
- A uniform defect across the cohort is treated as an **instrument tell**
  first — 46/46 identical means the scorer is wrong — and only then as a
  finding about the companies.

# Preregistered forward experiments: the original thesis, tested prospectively

Registered 2026-11-25, before any observation used to evaluate it exists.

* **Untouched contracts.** The Nov 9 cohort (977) and the Dec 25 econ cohort
  keep their contracts unchanged.
* **The 2021–2026 holdout is spent.** Its result is known (§3 of
  SCIENTIFIC_RECONSTRUCTION), so it is never used again as untouched data.
* **Evaluation is forward only.** Every experiment below is scored on
  outcomes that occur after its first registration.
* **Shadow only.** Everything runs in shadow. No position is opened and no
  money is involved.

## Common rules

* **Immutable contracts.** Every forecast carries its contract (id, created
  timestamp, information cutoff, target, prediction, mechanism, horizon,
  resolution rule, data source, baseline, model version, evidence ids,
  invalidation). It must pass `core/forecast_quality.py` before it is written.
* **Point-in-time evidence.** Evidence counts only if available before the
  cutoff: SEC acceptance time, ALFRED vintage, or `available_at` from the
  runtime ledger, never `seen_at` alone.
* **Correlation is accounted for.**
  * Effective sample is the number of distinct events, not rows. A company
    contributes at most one forecast per event.
  * Overlapping windows are scored with a block bootstrap by calendar week.
* **Multiple testing.** Holm correction across the experiments in this
  file, at α = 0.05 family-wise.
* **Fixed baselines,** declared per experiment and never replaced after
  outcomes are seen.
* **Promotion.** Nothing leaves shadow without passing its stated criterion
  at its stated minimum sample. A human promotes; no code path promotes.

## Experiments

| ID | Thesis element | Hypothesis | Target and horizon | Model | Baseline | Minimum sample | Success / failure |
|---|---|---|---|---|---|---|---|
| FX1 | Economic surprise | A revenue surprise against estimates, read by `demand_reading.v2.1` from the first independent report after an 8-K 2.02 acceptance, predicts the sign of the 2-session excess return vs SPY better than the base rate | Sign of open(t+1)→open(t+3) excess return, t = acceptance day | v2.1 surprise family → direction; abstain on ABSTAIN | Per-company base rate of up-excess (trailing 2 years); always-abstain | 60 distinct earnings events | Brier skill > 0 with 95% CI excluding 0 after Holm → promising; CI including 0 → no evidence; CI below 0 → refuted |
| FX2 | Public belief change | Direction of analyst estimate or target revisions observed in the week (ledger evidence) predicts 5-session excess return | Sign of 5-session excess return | Net revision direction | Base rate; price momentum (20-day) | 80 company-weeks with a revision | as FX1 |
| FX3 | Company-specific transmission | A macro shock moves a company's 63-session excess return in the direction its evidenced exposure implies | Sign of 63-session excess return | Exposure × shock sign | logit_A (price only) | — | **BLOCKED.** No evidenced company exposure map exists (§0 matrix: transmission not called). Registered so the gap is visible |
| FX4 | Declared intention vs actual behaviour | A guidance revision (intent) predicts the direction of the NEXT reported quarter's revenue acceleration (behaviour), against the company's own trajectory | Sign of next-quarter YoY revenue growth minus this quarter's (SEC XBRL, walled on `filed`) | Guidance direction (v2.1 on GUIDANCE_REVISION evidence) | Persistence (acceleration continues); always-decelerate (mean reversion) | 40 company-quarters | Accuracy above the better baseline with exact binomial p < 0.05 after Holm |
| FX5 | Resource commitment | A stated capex increase predicts the next fiscal year's reported capex growth sign | Sign of next FY capex growth (XBRL) | Capex-intent direction from evidence | Persistence of last year's capex growth sign | 30 company-years | as FX4. Slow: first results 2027 |
| FX6 | Strategic reaction | A competitor action is followed by a matching response within 90 days | Response observed (evidence) | Strategic-interaction pattern | Unconditional response rate | — | **BLOCKED** until the interaction detector stops rejecting every pattern (§0: constructed, never reaches a decision) |
| FX7 | Combined intelligence | FX1 + FX2 + FX4 signals combined beat each alone | as FX1 | Equal-weight vote | Best single component | After components each reach minimum sample | Holm-corrected improvement over the best component |

## Why these horizons

Each horizon is set by the economic mechanism, not to increase the count of
forecasts:

* **2 sessions (FX1).** Surprise is priced at the next open or soon after.
* **5 sessions (FX2).** Belief revisions diffuse over a week.
* **63 sessions (FX3).** Macro transmission to a company is a quarter-scale
  process.
* **One reporting period (FX4, FX5).** Intent is tested against the next
  observation of behaviour.

No daily forecasts are generated. A forecast exists only when its triggering
event exists.

## State today

* **Registered:** this document.
* **Generating forecasts:** none yet.
* **Blocked:** FX3 and FX6, for the reasons stated.
* **Next to implement:** FX1 and FX4. Both rely only on SEC filings
  (acceptance time, XBRL `filed`) and ledger evidence that is already
  captured prospectively.

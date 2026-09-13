# Collective-state research programme

*The experiment that decides whether the collective-human layer survives.*

---

## The question

Does knowing how a population feels predict anything that conventional
economic variables do not already predict?

Not: does it *explain* anything. Every crisis can be retold as fear and every
bubble as greed, and the retelling will fit because it was written afterwards.
**Fitting is free.** The layer gets no credit for explaining events
psychologically after the fact.

## The experiment (§18)

```
MODEL A   GDP, inflation, rates, employment, credit, liquidity,
          market data, company data                          -> score X

MODEL B   everything in Model A + CollectiveHumanState        -> score Y

DELTA  =  X - Y      (a loss; positive means Model B won)
```

Both models forecast the **same targets** from the **same information
cutoffs**. The only difference is the collective feature. So the statistic is
the per-target difference in loss, and its sampling distribution comes from
resampling those paired differences — a percentile bootstrap over 2000 draws,
because forecast losses are skewed and a t-test on them would overstate
significance in exactly the direction that flatters the new feature.

### The refusals

| condition | verdict | why |
|---|---|---|
| fewer than 30 paired forecasts | `INSUFFICIENT_SAMPLE` | a delta on eleven observations is not a weak result, it is not a result |
| mean loss no better | `NO_IMPROVEMENT` | retirement candidate |
| positive point estimate, 95% CI includes zero | `NOT_ROBUST` | consistent with no effect |
| interval clear of zero | `IMPROVEMENT` | **still pending** family-wide FDR |
| any forecast cutoff ≥ its outcome's `knowable_at` | `HindsightLeak` raised | a model scored that way is being credited for reading the answer |

### Multiple testing

Benjamini-Hochberg at **q = 0.10** across the whole family of *tested*
comparisons. 16 constructs × 4 regimes × 3 horizons = 192 tests; at p<0.05
roughly ten will look significant with no signal present at all.

Applied to every tested comparison, not only the winners. Selecting the family
after seeing which tests won is the error the correction exists to prevent.

### Two dates per fact

`Outcome` carries `occurred_at` **and** `published_at`. For revised series
they differ, and scoring against the wrong one leaks hindsight into a backtest
that otherwise looks walled. `knowable_at` returns `published_at` when it
exists.

## Verification that the gate works in both directions

A gate that can only say no is not measuring anything. Both controls were run.

| control | n | result |
|---|---|---|
| construct wired to carry **no** signal | 400 | `NO_IMPROVEMENT`, delta −0.0406 |
| construct wired to carry **real** signal | 400 | `IMPROVEMENT`, delta +0.0423, CI clear of zero |
| sample below the floor | 12 | `INSUFFICIENT_SAMPLE` |
| 20 pure-noise comparisons, family-corrected | 200 each | **0 survived FDR** |
| 20 marginal wins at p=0.5, all verdict `IMPROVEMENT` | 200 each | **0 survived FDR** |
| one strong result at p=0.0005 | 400 | survived FDR |
| forecasts with cutoffs after their outcomes | 50 | `HindsightLeak` raised |

The mutation suite confirms each of these guards is load-bearing: 22 of 22
deliberate defects were caught by a named test, including flipping the delta
sign, dropping the sample floor, disabling the FDR correction, and removing
the hindsight check.

## The episode partition (§§19–20, 40–41)

Nine episodes, six regimes, 1972–2023. The partition is **fixed in source**,
not computed at call time — a partition that drifts as episodes are added
cannot be a holdout.

| partition | episodes |
|---|---|
| **TRAINING** | 1970s stagflation, October 1987, dot-com, 2008 housing/financial crisis |
| **VALIDATION** | euro sovereign crisis, COVID crash, COVID recovery |
| **HOLDOUT** | **2022 inflation and rate shock**, 2023 regional bank failures |

### Why 2022 is the holdout

It is the period where stated sentiment and revealed behaviour diverged most
sharply in the modern record: sentiment collapsed to recessionary levels while
consumption held. That is either the clearest disconfirmation of the whole
behavioural layer, or evidence that the sentiment *instrument* rather than the
*state* broke. A layer that cannot survive it should be retired; one that is
tuned on it proves nothing.

### Why 1987 is in the set

As a **negative case**. It names zero constructs, and the expected answer is
that the collective layer adds nothing — the cascade was a market-participant
phenomenon with almost no household precursor, and the recovery was near
complete within two years. A programme with no episode where the answer should
be NO cannot distinguish a real signal from a flexible one.

### The partition discipline guard

`assert_partition_discipline()` refuses any construct whose *only* testable
episodes are holdout episodes — because testing it at all would then consume
the holdout.

**It fired on the first run.** `perceived_control` — the one construct this
deployment can actually measure — was testable only in `inflation_2022`. It
was added to `gfc_2008` (TRAINING; the labour-market collapse is the canonical
control-destroying event) and `covid_recovery` (VALIDATION; the 2021 quits
surge is the cleanest available test of it). The holdout is intact.

### 2008 is two chains, not one

§20 is explicit: do not start from "fear caused the crash". The upswing
(housing → perceived security → risk appetite → borrowing → housing) and the
downswing (delinquency → anxiety → risk appetite → spreads → capex) are
separate objects in `transmission_seed`, each with its own edges and its own
falsifier, so confirming one cannot carry the other.

## Current results

**None.** No episode has been executed and no real forward comparison has run.

```
COLLECTIVE_STATE_BASELINE_SCORE  = not measured
ECONOMIC_PLUS_COLLECTIVE_SCORE   = not measured
INCREMENTAL_DELTA                = not measured
COLLECTIVE_VARIABLES_PROMOTED    = 0
COLLECTIVE_VARIABLES_RETIRED     = 0
CALIBRATION_STATUS               = PRE_CALIBRATION (n = 0)
```

The dashboard reports `NOT_YET_MEASURED` with `incremental_delta = None`
rather than `0.0`, because a zero would read as "measured, no effect".

### Why not

Running the experiment needs vintage-correct history for both the economic
baseline and the behavioural series. This deployment can read two behavioural
series — BLS JOLTS quits and labour-force participation — and both are
currently returning `REQUEST_NOT_PROCESSED` because the keyless daily quota is
spent by the macro adapter. The other fourteen are behind a FRED key, a vendor
licence, or do not exist as public series.

So the binding constraint is data acquisition, not modelling. See
[`BUILD_STATUS.md`](../architecture/BUILD_STATUS.md#what-would-move-the-biggest-numbers).

## What *has* been demonstrated

`scripts/collective_closed_loop.py` runs the full loop twice against generated
outcomes, with one construct wired to carry signal and one wired to carry
none:

| | iteration 1 → 2 |
|---|---|
| `anger` (wired: no signal) | OBSERVED → **RETIRED** |
| `financial_anxiety` (wired: signal) | OBSERVED → **PROMOTED** |
| transmission chains open to founder surfaces | 0 → 3 |
| readings WMT is allowed to be shown | 0 → 1 |
| the 2022-style bleed | `CANDIDATE_NAMED` → `CORROBORATED` |

**SYSTEM BEHAVIOUR CHANGED BECAUSE IT LEARNED.**

This proves the machinery separates a wired signal from wired noise and that
the consequence propagates to what a CEO is allowed to be told. It proves
**nothing** about the real economy: §39 forbids counting a synthetic
trajectory as market learning, and the script says so in its own output.

## Promotion pipeline (§42)

```
candidate construct
  -> proxy definition          (rationale, sign, range, noise, contested?)
  -> historical reconstruction
  -> measurement reliability
  -> lagged predictive test     at the construct's declared lag band
  -> confounder control          (base model already holds the economics)
  -> incremental value vs base economics
  -> regime robustness           two distinct regimes
  -> out-of-sample test
  -> causal evidence             the ladder, separately
  -> PROMOTE / WEAKEN / RETIRE
```

The lag band matters more than it looks. A comparison run at the wrong lag
finds nothing and retires a construct that was real, which is why `LagModel`
is required on every estimate and carries its basis.

**Known problem:** `institutional_trust` has a 90-day typical lag, and its
most important episode (2023 regional banks) is a three-day bank run. That
construct's lag model cannot describe its own decisive episode. The episode
records this rather than quietly widening the band.

## Retirement is real

`RETIRED` is terminal, `active_dimensions()` excludes it, and
`estimator.estimate()` **stops computing it** — not merely hiding it from a
surface. Filtering at the surface is not removal, and a construct still
computed every cycle has not been retired.

`revive()` exists, requires a stated reason, and returns the construct to
`CANDIDATE` — never to `PROMOTED`.

## The success criterion (§56)

The layer is **not** successful because its graphs look plausible or because
it explains historical crises nicely.

It is successful only on **out-of-sample incremental value**, reported by
forecast family, regime, population and horizon, with confidence interval,
sample count and multiple-testing adjustment.

Until that number exists, every construct is `CANDIDATE` or `OBSERVED` by
definition, and none of them may inform a decision.

# V3: the one replicated signal, attacked

**From:** `277bec62` on `v6/unified`
**Preregistered:** H7 `3a5c4d36259e08a2`, frozen before the V3 panel was scored.
Prior hashes unchanged: V1 `4ae395b62fb60f85`, H2 `69c6732028a20679`,
V2 `d1e266aa7acfc67f`.
**Panel:** `ae00e04e2bcccfd1` — 32 series, 195,886 cells, 580 network calls.

---

## The headline: the previous run's one positive finding was a window artifact

V2 reported, as its single replicated result, that consumer sentiment leads
housing starts by 6–8 months. Adversary test 7 asked whether that was a
property of the *series* or of the *origins that were measured*:

| | subsample (n=482) | full record (n=584) |
|---|---|---|
| UMCSENT → HOUST | lag **+6**, corr +0.298, LEADING | lag **0**, corr **+0.405**, COINCIDENT |
| UMCSENT → INDPRO | lag +7, corr +0.330, LEADING | lag +6, corr +0.402, LEADING |

V2 computed the lag from `v2_paired_deep.jsonl` — the origins that appeared in
its **test folds**. Walk-forward reserves the earliest slice for training, so
the measurement silently began in 1986 while the record begins in 1978. Adding
1978–1986 — the Volcker disinflation and the largest housing cycles in the
sample — removes the housing lead entirely *and raises the correlation*.

A temporal order is a descriptive property of two series. There is no reason to
compute it on an evaluation subsample, and doing so cost the headline finding.

**UMCSENT → HOUST: RETIRE.**

## The industrial lead is robust to the window and still not usable

It survives each confounder taken singly and dies when they are combined:

```
UMCSENT|UNRATE    -> INDPRO  lag +8  corr +0.355  LEADING   SURVIVES
UMCSENT|BAA       -> INDPRO  lag +4  corr +0.352  LEADING   SURVIVES
UMCSENT|CPIAUCSL  -> INDPRO  lag +5  corr +0.383  LEADING   SURVIVES
UMCSENT|ALL       -> INDPRO  lag -11 corr -0.283  LAGGING   KILLED
```

Pre-2008 sentiment *lags* housing by 2 months; post-2008 it leads by 8. Not one
mechanism. Wealth effects are **UNTESTABLE** — no vintage-correct household
wealth series exists in this panel, so that alternative is unchecked, not ruled
out.

**Role: EARLY_REFLECTION_OF_ANOTHER_VARIABLE. H7: INSUFFICIENT_POWER.**

## Housing could not be scored at all

`HOUST` fails the baseline ladder in both arms at both horizons — historical
out-of-sample, the macro block scores 0.2735 against a constant's 0.2525. The
target where the sentiment claim was strongest is **BASELINE_INVALID**, which
§11 insists is a different finding from HUMAN_STATE_FAILED.

## Coverage expansion: 20 probed, 1 admitted to the behavioural block

| verdict | series |
|---|---|
| DEFENSIBLE_PROXY | **UEMP15OV** — extends `underemployment` from 2012 back to **1964** |
| SAME_SERIES | UMCSENT1 — FRED's pre-1978 quarterly segment of UMCSENT itself |
| UNUSABLE | UEMPMEAN — crisis agreement 0.00 |
| WEAK_PROXY | BAA10Y, AAA10Y, BAA, T10Y3M |

The credit spreads have a rank correlation of **+0.04** with household
credit-card delinquency. They do not measure household credit stress and were
refused as behavioural proxies — but they are conventional financial-conditions
controls, so they joined the **base** block, which makes the collective test
harder rather than easier.

UMCSENT1 scored 1.00 on all four equivalence metrics. That is what an identity
looks like through a proxy test, and `SAME_SERIES_NOT_A_PROXY` now exists
because a perfect score is an instrument tell.

## Power went down, and the report says so

| | V2 | V3 |
|---|---|---|
| effective origins | 127.2 | 81.6 |
| episodes | 15 | 15 |
| MDE | 0.00436 | 0.00505 |

Four extra base features changed the base model's predictions and made the
paired differences more autocorrelated across origins. More features is not
more independent information.

## Forward

12 expectations = **6 BASE/AUGMENTED pairs**, immutable, all seven lifecycle
facts proved: opens with a resolution rule, survives reload, refuses a
retrospective edit, resolves only at horizon, resolution appends, calibration
consumes resolved only, unresolved excluded from any accuracy figure. Status:
`AWAITING_REAL_WORLD_RESOLUTION`. Calibration remains `PRE_CALIBRATION`.

Founder integration remains **REFUSED**. History Rewind was **not run** — §24
requires validated episode data and nothing was validated.

## Guards added, and one that was over-broad

`assert_lead_is_not_causal` had no production caller until break proof 9 went
looking for a call site to mutate — the same absence proof 12 found last run.

`calibration.assert_no_unsupported_claim` was a document-wide substring search
that refused an entire research report for containing the word "Brier"
anywhere. It is now **sentence-scoped**: a sentence may quote a historical
figure when it says so in that sentence, and an unqualified claim still raises
even beside a qualified one. That is stricter where it matters — a wall a
truthful sentence cannot satisfy gets removed rather than obeyed.

Break proofs: **12/12 CAUGHT**, each with a positive control. Three initially
reported NOT_CAUGHT for the same reason as last run — they disabled a guard and
then called it — and were rewritten to mutate the producer or the call site.

## What would actually change the answer

1. **(9)** A vintage-correct household credit series before 2012.
2. **(9)** A housing-direction baseline that beats a constant — `MORTGAGE30US`
   and `PERMIT` are on ALFRED and cheap.
3. **(6)** A vintage-correct household wealth series, to close the one
   unchecked adversary.
4. **(1)** More origins. Measured across two runs: the grid is not the
   constraint and has not been for two runs.

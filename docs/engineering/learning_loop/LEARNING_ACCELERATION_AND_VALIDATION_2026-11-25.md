# Learning Acceleration and Validation — first report

2026-11-25. Every number below was measured today, on production records or on
labelled copies. The two kinds of evidence are kept apart throughout:

* **FORWARD**: a prediction recorded before its outcome existed.
* **RECONSTRUCTED**: a rule applied after the fact to data that existed at
  decision time. It can show whether a mechanism carries information. It is
  never evidence of skill the engine actually displayed, and nothing tuned on
  it is scored on it.

## 1. What was written to production today (approved items B and C)

| Ledger | Write | Verification |
|---|---|---|
| `~/intent-engine-market/reports/market/signal_outcomes.jsonl` (new) | 481 outcome events: 359 RESOLVED, 104 UNRESOLVABLE (OLO delisted), 18 PENDING | Fresh backup `canonical-ledgers-20261125-104232` (638 files, 0 restore mismatches). `signal_audit.jsonl` hash unchanged. An immediate rerun appended 0. |
| `~/intent-engine/data/prediction_ledger.db` | 6 superseding rows appended (31 → 37). The 6 original `unresolvable` rows are kept | `integrity_check=ok`. Every observation re-read live from FRED/ALFRED today. |

**A defect caught before the write.** The first production dry run at 10:42 ET
graded three Nov 4 records whose 21-day horizon ends *today*. It used the
live intraday quote; the 04:47 run had used the prior close. Either value
would have been written as terminal. Maturity now requires the horizon-end day
to have passed (`outcome_resolver.py`, two guard sites, each mutated and
caught). Those 4 records, and the 3 decisions they belong to, resolve tomorrow.
The other 481 events match the verified dry run exactly. The same defect class
caused every July failure: the resolver ran before the figure was published
and then treated "not yet" as terminal.

`processed_on` is today's date on every event. Each event keeps the original
`as_of`, horizon, rule (`volatility_feasibility.v1`) and price basis.

## 2. Historical price outcomes: what the engine predicted

**The live market runtime made no directional price prediction.** There is
no probability anywhere in its 674 audit rows, so no Brier score exists.

Error attribution, root cause: `steps.py` `opportunity_step` hardcodes
`fired = False` and the reason text "no direction: |trailing return| below the
noise floor". It never calls `strategy_library.baseline_momentum`. The stated
reason is false for 211 of 231 decisions, where the trailing 20-day move was
above 2%. It also writes `evidence_ids=()` unconditionally. So the
"silence" was a constant, not a judgement, and no evidence-to-price
attribution was ever possible from these rows.

Resolved decisions under the original contract (the opportunity rule, not a
direction):

* 231 distinct decisions, from 359 resolved records; day and night rows of one
  decision collapse.
* 204 of 225 missed-opportunity candidates were confirmed (|21d move| ≥ 2%).
  The unconditional base rate is about 77–84%, so this measures volatility,
  not foresight.

### RECONSTRUCTED: what `baseline_momentum.v1` would have said

The rule is applied as shipped, to closes up to `as_of` only, and graded on
the outcomes written above.

| Slice | Decisions | Fired | Direction right | Hit rate |
|---|---|---|---|---|
| All (overlapping 21-day windows) | 231 | 211 | 67 | **0.318** |
| Non-overlapping windows only | 20 | 17 | 7 | 0.41 |
| SHOP | 85 | 78 | 20 | 0.26 |
| NET | 74 | 72 | 31 | 0.43 |
| NEE | 30 | 28 | 9 | 0.32 |
| MELI | 29 | 22 | 2 | 0.09 |
| CHKP | 7 | 7 | 1 | 0.14 |
| PG | 6 | 4 | 4 | 1.00 |
| Regime SPY 63d up | 221 | 201 | 61 | 0.30 |
| Regime SPY 63d down | 10 | 10 | 6 | 0.60 |

Uncertainty: the block bootstrap over 19 instrument-month blocks gives a 95% CI
of **0.22–0.42** on the hit rate. Effective independent observations are about
17–20, not 211. Correlated daily rows are not separate trials.

**Reading.** Over Aug–Nov 2026, on these six names, 20-day momentum reversed.
Had the constant been a real signal, the engine would have been wrong about
two times in three. This agrees with the 20-year replay, where
`ie_market_momentum` cleared no Holm-adjusted test. It is one regime, four
months long. It does **not** license a reversal strategy: that would be fitted
to these same outcomes. `reversal_1m` is already preregistered as a baseline
in the Nov 9 forward cohort, which will test it out of sample on 2026-12-11.

## 3. July forecasts, corrected (item C)

| | n | Brier |
|---|---|---|
| Engine before correction (SPY rules only) | 4 | 0.125 |
| **Engine after correction** | **10** | **0.139** |
| Ledger baselines (a different question: SPY +2% in 60 days) | 4 | 0.080 |
| Same 6 FRED forecasts, uninformative p=0.5 | 6 | 0.250 |
| Same 6 FRED forecasts, engine | 6 | 0.149 |
| Same 6 FRED forecasts, persistence reference (p=0.9 if the rule already held at creation, else 0.1) | 6 | 0.143 |

The persistence reference was defined today, after the outcomes were known.
It is a yardstick, not a competitor that was entered in advance.

Individual outcomes, all re-verified against FRED/ALFRED today:

| id | Series, rule | p | Outcome | Brier | Original failure |
|---|---|---|---|---|---|
| 4bae2749 | T10Y2Y ≥ 0.30 on 10-16 | 0.72 | happened (0.35) | 0.078 | resolver ran 10-16 10:00 UTC, before that day's print |
| 2d44806f | UNRATE < 5.0 by 10-01 | 0.65 | happened (4.1, first published 11-06) | 0.123 | ran 10-09; October figure not out until 11-06 |
| 0f742abb | T10Y2Y ≥ 0.25 on 09-30 | 0.72 | happened (0.41) | 0.078 | ran same morning |
| 73b2bf49 | T10Y2Y < 0.30 by 09-18 | 0.62 | happened (0.25) | 0.144 | ran same morning |
| e0408859 | UNRATE ≥ 3.4 by 08-31 | 0.58 | happened (4.2, published 10-02) | 0.176 | ran 09-04 |
| 59bcc2e3 | BAMLH0A0HYM2 ≥ 310 by 09-03 | 0.54 | did not happen (2.65) | 0.292 | ran 09-04 |
| 99e07e94, 93384e1d, 03c7cd9d, f30cf99e | SPY rules | 0.58–0.72 | all happened | 0.078–0.176 | — |

Why the engine lost to trivial references:

* **Underconfidence on near-certain claims.** The mean stated p was 0.64; 9 of
  10 happened. Five of the six FRED claims were already true when made
  (persistence was the whole forecast).
* **Defective contracts.** One was already satisfied (UNRATE ≥ 3.4 with 4.2
  known). One was unreachable: a 310 threshold against a series in percent (~2.7).
  Two said "remains above", but the rule checked a single day. Under the
  every-day reading, 4bae2749 and 0f742abb did not hold (minimum 0.20 on 09-21).
* **Calibration.** It cannot be estimated from 10 forecasts on 3 series. **Not
  scientific validation.**

## 4. Evidence-source effectiveness (the 47 graded business expectations)

These are the market runtime's directional expectations, graded against later
evidence rather than prices. 28 confirmed, 19 contradicted: 0.60, with a
cluster-bootstrap 95% CI of 0.51–0.70 over 26 subjects.

| Cut | Confirmed |
|---|---|
| **demand_weakening (DOWN)** | **2 / 15 = 0.13** |
| demand_strengthening (UP) | 23 / 26 = 0.88 |
| pricing_power | 2 / 4 |
| Predicting evidence: regulatory filing | 5 / 6 |
| Predicting evidence: independent reporting | 22 / 37 |
| Predicting evidence: analyst coverage | 4 / 7 |
| Predicting evidence: 2+ distinct source roles | 5 / 5 |
| Predicting evidence: 1 source role | 23 / 42 |
| Stated uncertainty, lower half | 19 / 23 |
| Stated uncertainty, upper half | 9 / 24 |

* **Consistently failing mechanism.** The *demand_weakening* inference is
  contradicted 13 times in 15. UP expectations confirm at 0.81, but the
  base rate of "things reported as growing" in this news mix is unmeasured,
  so UP's success is not shown to be skill.
* **Confidence carries information.** The direction is right: lower stated
  uncertainty confirmed more often. The engine's uncertainty is
  informative, not just decoration.
* **Source diversity.** 5 of 5 confirmed with two or more source roles. That
  is n=5, confounded with subject, and **not** grounds to raise any source's
  weight. Per the instruction, no weight has been changed.
* **Grading independence.** No expectation was graded by the document that
  formed it.

## 5. Model and evidence ablations (the existing paper-validation replay)

This is a preregistered 20-year replay (2007–2026, 237 decision dates, 54
companies plus 25 ETFs). Holm-adjusted p = 1.0 for every policy on both
Brier skill and Sharpe against the benchmark.

| Ablation | Universe | Brier skill vs reference | 95% CI |
|---|---|---|---|
| + macro features (logit_B vs logit_A) | companies | −0.008 | −0.015 to −0.002 |
| + econ-engine features (logit_D vs logit_A) | companies | −0.021 | −0.038 to −0.008 |
| + macro features | ETFs | −0.076 | −0.131 to −0.025 |
| + econ-engine features | ETFs | −0.129 | −0.210 to −0.059 |
| shuffled-label control vs logit_B | companies | +0.002 | −0.003 to +0.007 |
| + news/evidence channel (logit_C) | both | **NOT MEASURED** | no point-in-time news provider is wired |

Adding economic structure made the forecasts measurably **worse**, and the
shuffled-label control is indistinguishable from logit_B. That is the
replay's own preregistered verdict ("no edge found"), reproduced. Abstention
quality: flagged minus unflagged is +0.0025 (CI −0.004 to +0.009), so it is
not shown to help.

## 6. Shadow candidates (preregistered here, scored only on outcomes after today)

| Candidate | Change | Scored on | Promotion criterion |
|---|---|---|---|
| S1 `shadow_momentum` | The audit step computes `baseline_momentum.v1` and records its direction beside `fired=False`. Never trades | runtime decisions with `as_of` ≥ 2026-11-26 | none; it is a measurement, not a policy |
| S2 suppress demand_weakening | Withhold DOWN expectations from the business-expectation stream | expectations preregistered after 2026-11-25 | DOWN confirmation stays < 0.35 on ≥ 15 new graded DOWN expectations; a human promotes |
| S3 reversal baseline | none; already registered on 2026-11-09 | the 977 forward forecasts, 2026-12-11 | the protocol's own `promotion` block |

Nothing here was tuned on the outcomes it reports.

## 7. What the system can now do end to end, with zero Anthropic

On a scratch copy of the paper-validation data, with `ANTHROPIC_API_KEY` unset:
`daily` → `learn` → `register --if-due` → forced `register`.

* **Collected evidence.** 34 FRED series via ALFRED vintages, and prices for
  the full universe.
* **Generated and preregistered.** 977 new forward forecasts, with information
  cutoff 11-24 and decision date 11-25, hash-chained.
* **Resolved and measured.** `daily` scored what was due; nothing is due
  until 12-11.
* **Learned.** `learn`: attribution, calibration drift and belief updates in
  shadow; promotion is human-only.

The production ledger was hash-verified unchanged afterwards.

## 8. Not yet true

* No forward forecast from any engine component has resolved. The first
  meaningful sample is 2026-12-11. Until then there is **no** evidence of
  predictive skill, and the reconstructed momentum result points the other way.
* The market runtime still runs its old code (item A was not approved), so
  `signal_outcomes.jsonl` grows only when the resolver is run by hand.
* The evidence ablation (logit_C) cannot be run historically: no
  point-in-time news archive exists. It can only accumulate forward.

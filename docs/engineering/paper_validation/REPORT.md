# Paper validation of the economic engine: report

Branch `paper-validation/v1` (worktree `~/ie-paper-validation`, cut from
`prospect100/identity` at `e3762f22`). Written 2026-11-09. PAPER ONLY: no
order was placed, no broker was imported, no credential was read, no
production ledger or scheduler was touched.

## Outcome

**In twenty years of walk-forward replay, nothing beat the simple
baselines, and the economic engine's company reading carried no detectable
information at a one-month horizon.** That includes the engine's own
policies, the textbook rules and the fitted models.

* No policy shows positive Brier skill over a point-in-time climatology in
  either universe. The best are indistinguishable from it; the fitted models
  are significantly worse.
* In the ETF universe nothing beats buy-and-hold on net Sharpe. The engine's
  market policy (`baseline_momentum.v1`) loses to it: Sharpe difference
  -0.81, 95% CI [-1.53, -0.11].
* The economic engine flags an adverse transmission on 83% of company-dates.
  Flagged companies did not underperform unflagged ones: +0.25% per period,
  CI [-0.35%, +0.85%], where the engine's claim needs a negative number.
  Against a control that shorts the same number of RANDOM companies each
  date, the annual return difference is -0.03%, CI [-1.33%, +1.19%].
* Adding macro features (B) to price features (A) made out-of-sample Brier
  worse in both universes. Adding the engine's reasoning features (D) made
  it worse again. Logit B is no better than the same model trained on
  shuffled labels.
* The forward shadow ledger holds **977 registered forecasts and 0
  resolved**. The first entries fill at the 2026-11-10 open, and the first
  window closes at the 2026-12-10 open, so nothing can resolve before
  2026-12-11. Any forward claim needs at least 36 resolved decision dates
  (about three years at this cadence).

This is a negative replay result, stated with its intervals. It is not
evidence that the engine has no value: the replay tests one horizon, one
mapping from the engine's output to a trade, and a company list chosen in
2026 (see Limitations). It is evidence that, as wired today, the engine's
economic reading does not move one-month relative returns in a way this
harness can detect.

## What was built

`src/intent_engine/paper_validation/` (new package, 18 modules) and five
test files (60 tests, about 3 s):

| module | role |
|---|---|
| `protocol.py` | the preregistered declaration and its hash |
| `ledger.py` | append-only, hash-chained ledger; REGISTER / RESOLVE / VOID; forward ledger refuses backdating; outcomes must have happened |
| `bars.py` | adjusted daily bars from the keyless Yahoo endpoint (`adjclose`), cached with retrieval time and sha256 |
| `macro.py` | vintage-walled macro features; the engine's regime reading; the engine's company reading rebuilt as of each date; the forward FRED snapshot |
| `universe.py` | 25 ETFs (macro/sector proxies) and 54 US-listed manifest companies; private companies refused a security |
| `observations.py` | one row per (date, instrument), shared by replay and forward registration |
| `policies.py` | baselines, the engine's policies called unchanged, new variants, controls, and named absences |
| `model.py` | `econ.forecast`'s logistic, vectorised, returning `econ.forecast.Model`; parity-tested to 1e-9 |
| `leakage.py` | evidence-date wall, truncation invariance, label purge, the oracle canary |
| `metrics.py` | Brier, log loss, reliability, calibration slope, date-cluster block bootstrap, paired differences, Holm |
| `replay.py` | walk-forward replay, books, summary, the post-hoc specification diagnostic |
| `forward.py` | forward registration, the single resolver, the rehearsal, the CLI |
| `learning_loop.py` | shadow learning: attribution, beliefs, drift, promotion readiness, candidates |
| `evidence_channel.py` | the interface for the news/company-evidence channel (arm C), PENDING |
| `report.py` | renders the tables below from the committed artifacts |

The system-of-record note (`SYSTEM_OF_RECORD.md`) was written before any
code. It records that the canonical market ledger
(`~/intent-engine-market/reports/market/learning_ledger.jsonl`, launchd,
pinned at `195c6f4a`) was read-only throughout. The preregistration
(`PREREGISTRATION.md`) pins protocol hash `d6483796...`. It also discloses
the four analysis choices changed after the first replay; no policy
parameter was changed.

### What the engine's modules contributed (called, not re-implemented)

| engine module | used for |
|---|---|
| `econ.panel.Panel` (vintage-walled reads) | every macro feature, the regime and the state |
| `econ.regime.classify` | the regime at each decision (D features, regime splits) |
| `scripts/publish_econ_state.build_state` | the economic state as of each decision (loaded by path) |
| `external_intel.econ_context.relevant_to`, `econ_decision.transmissions` | the company reading behind `ie_econ_transmission` |
| `executive.company_profile.profile_for` + validation manifest | business-model class of every company |
| `market.strategy_library.baseline_momentum` | `ie_market_momentum` |
| `market.costs` cost.v1, `market.signals.BASELINE_PROBABILITY` | costs and the rule probability (tests pin both) |
| `econ.forecast.Model` / `fit` contract | the logistic (parity test) |
| `paper.portfolio.max_drawdown` | drawdown |
| `learning.LearningLedger` | shadow candidates, at a separate path; its human promotion wall |

Not used, and not claimed: `paper.broker` and `paper.execution` (forbidden
here; a test asserts no import); `econ.bayes` (it accepts only declared
0-1 collective dimensions, not returns); `econ.causal` and
`econ.transmission_seed` (no edge reaches a tradable instrument, so
`causal_filtered` is NOT_IMPLEMENTED); `econ.forward_ledger` (its target is
macro-series direction, not instruments); `market.strategy_library.
mean_reversion` and `volatility_breakout` (their declared horizons are 3-20
sessions, not this protocol's 21; they are not compared rather than compared
off-spec).

## The protocol, in one paragraph

Decide at a session close every 21 SPY sessions, enter at the next open,
exit at the open 21 sessions later (contiguous windows, no overlap). The
target is the sign of the excess return: ETFs against cash at fed funds,
companies against SPY. Costs are cost.v1 (5 bps per side) on the change in
position, plus 30 bps/yr borrow on short legs. Positions are -1, 0 or +1
per instrument, and the book is their mean (no leverage). Intervals come
from a circular block bootstrap over decision dates (blocks of 6, 2,000
draws), carrying each date's whole cross-section, because 25 ETFs on one
day are not 25 observations. The common window is 2007-01-04 to 2026-09-17
(237 decision dates). The replay anchor is 2003, which leaves room for the
273-session feature history and the first model fits.

## Historical replay: reading the tables

The tables are generated from `reports/paper_validation/replay/summary.json`
(sha256 `6a047c8b...`; rerunning the replay reproduces it byte for byte).

**ETF universe.** Buy-and-hold earns net Sharpe +0.58 [+0.11, +1.13] across
25 ETFs. Every other policy's Sharpe difference against it is negative,
and none is better after Holm (every adjusted p is 1.000). The engine's
momentum policy and logit_D are worse, with intervals that exclude zero. `econ_factor_credit`
(the credit-spread baseline) is the closest: Sharpe +0.44, difference
-0.14 [-0.54, +0.28], with lower drawdown (21% vs 40%) because it abstains
45% of the time. It beats the random control (+4.9%/yr [+0.4%, +9.4%]), but
so does buy-and-hold, by more. Random is a low bar.

**Company universe, and the survivorship it exposes.** Long the 54
companies against SPY, always, earns Sharpe +1.31 [+0.95, +1.69]. That is
the signature of a list of 2026 survivors (it includes NVDA, AVGO, LLY,
PLTR). Every company policy therefore has to beat buy-and-hold, not zero.
None does.

**The economic engine's arm.** `ie_econ_transmission` shorts any company
with an adverse transmission. It flags 83% of company-dates, so it is
almost always short almost everything, and its -1.23 Sharpe is mostly the
inverse of the survivorship drift. The fair tests are the two built to be
able to give the same answer:

* flagged minus unflagged relative return: +0.25% per period, CI
  [-0.35%, +0.85%] over 192 dates with both groups. Wrong sign, and
  indistinguishable from zero;
* against `permutation_control` (the same number of shorts per date on
  random companies): annual return difference -0.03% [-1.33%, +1.19%].

The engine's (channel, business-model) signs did not pick the losers. On
2026-11-09 the arm flags all 54 companies. For 40 of them the lead channel
is the 2-year Treasury yield, up on the year. For the 14 banks and
regulated providers, whose rate sign the engine deliberately leaves
unsigned, the lead is inflation. That degeneracy is a property of the arm
as wired, not of the replay.

**The Bayesian variant (new here) learned to stop.** `ie_econ_bayes` keeps a
Beta posterior per business-model class on whether a flag was right, using
only flags whose windows had closed. Its posteriors rarely cleared the
0.52 bar, so it traded 368 of 9,658 flags and abstained on 96%. Its +6.55%/yr
"advantage" over the permutation control is the shorts it stopped placing.
Against random it is +1.11% [-0.58%, +2.85%]. That is learning to abstain,
not skill, and it is reported as that.

## Ablation A / B / C / D

Same model, same rows, paired by date. The full table is below.

| arm | features | status |
|---|---|---|
| A | price (1, 3, 12-1 month returns; volatility; distance from the 200-day mean; relative versions for companies) | measured |
| B | A + nine vintage-walled macro features (curve, credit spread, rates, unemployment, CPI, industrial production) | measured |
| C | B + news / company evidence | **NOT_MEASURED**: the channel (`prospect100/identity`) is not wired; the slot is `evidence_channel.EvidenceProvider` |
| D | B + engine reasoning (regime flags; company adverse/favourable/signed channel counts) | measured, with causal NOT_IMPLEMENTED and C's slot empty |

Every step down the ladder made out-of-sample Brier worse. In the ETF
universe the skill of B over A is -0.076 [-0.131, -0.026], and of D over B
-0.050 [-0.079, -0.023]. In the company universe B over A is -0.008
[-0.015, -0.002] and D over B -0.014 [-0.025, -0.005]. The shuffled-label
control is not worse than B in either universe (ETF +0.025
[-0.017, +0.067]). Through this model, the macro block carried no more
information than noise.

The post-hoc diagnostic says why, family by family
([[misspecified-not-overfitted]]):

* **ETF families: overfitting.** With macro features, in-sample Brier falls
  well below the base rate (commodities 0.231 against 0.249) while
  out-of-sample rises to 0.275 at the protocol's penalty (L2 = 1). At the heaviest
  penalty the model collapses to the base rate and ties it. Nine macro
  features shared by every instrument on a date give about one independent
  observation per date, not one per row, and L2 = 1 does not restrain that.
* **Company family: nothing to fit.** In-sample Brier is flat at 0.249
  across four orders of magnitude of penalty.

No penalty from the sweep was adopted. A stronger fixed penalty would at
best tie the base rate.

## Calibration

Rules state a constant 0.55, so their calibration slope is not defined;
their Brier measures direction only. The fitted models' calibration slopes
are about zero or negative (ETF logit_A -0.00, logit_B -0.02, logit_D
-0.07): their probabilities carry no ordering information. Out of sample,
logit_A's 0.7-0.8 bin is right 45% of the time against a stated 73%, so it
is overconfident at the edges. The reliability table is below.

## Regimes

`econ.regime` classified every decision date as CALM (136) or STRESS (101);
the MIXED cell is empty. Buy-and-hold is stronger in CALM (ETF Sharpe 0.73)
than in STRESS (0.47). `econ_factor_credit` is stronger in STRESS (0.66)
than in CALM (0.20), which is the direction its mechanism predicts, but both
intervals cross zero and overlap each other. No regime result clears the
superiority bar.

<!-- BEGIN GENERATED TABLES (report.py --splice) -->

Protocol hash `d6483796ba0e550ecfa4495fc956709f5d8502aac6cf4c49854e6a90a7410dc4`; common window from 2007-01-01.

#### ETF universe: 237 decision dates (2007-01-04 .. 2026-09-17), 25 instruments

Books (net of costs):

| policy | provenance | net Sharpe [95% CI] | gross Sharpe | ann. excess return | vol | max DD | turnover | cost drag/yr | abstain | vs buy-and-hold Sharpe [CI] | Holm p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | BASELINE | +0.58 [+0.11, +1.13] | +0.58 | +7.1% | 12.3% | 40% | 0.00 | 0.00% | 0% | n/a  | - |
| cash | BASELINE | n/a  | n/a | +0.0% | 0.0% | 0% | 0.00 | 0.00% | 100% | n/a  | - |
| tsmom_12_1 | BASELINE | +0.28 [-0.10, +0.81] | +0.30 | +3.0% | 10.7% | 32% | 0.21 | 0.21% | 0% | -0.30 [-0.89, +0.37] | 1.000 |
| reversal_1m | BASELINE | +0.09 [-0.29, +0.46] | +0.17 | +1.0% | 10.1% | 28% | 0.98 | 0.77% | 0% | -0.49 [-1.12, +0.01] | 1.000 |
| econ_factor_credit | BASELINE | +0.44 [-0.01, +0.94] | +0.46 | +4.1% | 9.3% | 21% | 0.25 | 0.15% | 45% | -0.14 [-0.54, +0.28] | 1.000 |
| ie_market_momentum | EXISTING_ENGINE | -0.23 [-0.59, +0.13] | -0.17 | -2.2% | 9.4% | 52% | 0.78 | 0.54% | 41% | -0.81 [-1.53, -0.11] | 1.000 |
| logit_A | NEW_IN_THIS_WORK | +0.36 [-0.01, +0.85] | +0.37 | +4.0% | 10.9% | 35% | 0.12 | 0.09% | 10% | -0.22 [-0.50, +0.04] | 1.000 |
| logit_B | NEW_IN_THIS_WORK | +0.33 [-0.09, +0.84] | +0.34 | +3.4% | 10.3% | 38% | 0.20 | 0.18% | 9% | -0.25 [-0.55, +0.04] | 1.000 |
| logit_D | NEW_IN_THIS_WORK | +0.06 [-0.30, +0.52] | +0.08 | +0.6% | 9.8% | 43% | 0.23 | 0.21% | 7% | -0.52 [-0.97, -0.10] | 1.000 |
| random_control | CONTROL | -0.19 [-0.55, +0.21] | -0.01 | -0.8% | 4.2% | 18% | 0.99 | 0.75% | 0% | -0.77 [-1.40, -0.15] | - |
| shuffled_label_control | CONTROL | +0.07 [-0.36, +0.58] | +0.08 | +0.7% | 10.2% | 50% | 0.16 | 0.13% | 7% | -0.52 [-0.93, -0.17] | - |

Forecasts and trades:

| policy | forecasts | traded | hit rate [CI] | avg win | avg loss | EV/trade net [CI] | Brier | Brier (climatology) | Brier skill [CI] | log loss | calib. slope | Holm p (skill>0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | 5895 | 5895 | 0.578 [0.543, 0.612] | +3.92% | -3.85% | +0.49% [+0.03%, +0.92%] | 0.2447 | 0.2447 | -0.0002 [-0.0145, +0.0142] | 0.6826 | n/a | 1.000 |
| tsmom_12_1 | 5895 | 5895 | 0.551 [0.522, 0.579] | +3.82% | -3.98% | +0.17% [-0.18%, +0.49%] | 0.2474 | 0.2447 | -0.0110 [-0.0364, +0.0142] | 0.6879 | 0.40 | 1.000 |
| reversal_1m | 5895 | 5895 | 0.495 [0.469, 0.522] | +4.16% | -3.68% | +0.04% [-0.27%, +0.34%] | 0.2530 | 0.2447 | -0.0339 [-0.0663, -0.0025] | 0.6992 | 0.23 | 1.000 |
| econ_factor_credit | 3260 | 3260 | 0.582 [0.536, 0.622] | +3.85% | -3.79% | +0.54% [-0.09%, +1.10%] | 0.2443 | 0.2442 | -0.0003 [-0.0164, +0.0166] | 0.6817 | n/a | 1.000 |
| ie_market_momentum | 3479 | 3479 | 0.501 [0.466, 0.537] | +4.41% | -4.90% | -0.33% [-0.81%, +0.15%] | 0.2524 | 0.2484 | -0.0161 [-0.0468, +0.0157] | 0.6980 | -0.25 | 1.000 |
| logit_A | 5860 | 5325 | 0.570 [0.536, 0.604] | +3.70% | -3.95% | +0.27% [-0.11%, +0.62%] | 0.2507 | 0.2447 | -0.0245 [-0.0413, -0.0117] | 0.6983 | -0.00 | 1.000 |
| logit_B | 5860 | 5381 | 0.558 [0.528, 0.587] | +3.86% | -4.03% | +0.22% [-0.17%, +0.59%] | 0.2697 | 0.2447 | -0.1022 [-0.1710, -0.0428] | 0.7774 | -0.02 | 1.000 |
| logit_D | 5860 | 5473 | 0.532 [0.504, 0.562] | +3.78% | -4.07% | -0.03% [-0.37%, +0.29%] | 0.2831 | 0.2447 | -0.1568 [-0.2528, -0.0758] | 0.8678 | -0.07 | 1.000 |
| random_control | 5895 | 5895 | 0.504 [0.491, 0.517] | +3.89% | -3.91% | -0.10% [-0.25%, +0.03%] | 0.2500 | 0.2447 | -0.0217 [-0.0491, +0.0056] | 0.6931 | n/a | - |
| shuffled_label_control | 5860 | 5458 | 0.543 [0.508, 0.576] | +3.68% | -4.12% | -0.03% [-0.46%, +0.35%] | 0.2630 | 0.2447 | -0.0748 [-0.1380, -0.0264] | 0.7410 | -0.13 | - |

By regime at the decision (econ.regime, point in time):

| policy | CALM periods | CALM Sharpe [CI] | CALM hit | STRESS periods | STRESS Sharpe [CI] | STRESS hit |
|---|---|---|---|---|---|---|
| buy_and_hold | 136 | +0.73 [+0.17, +1.59] | 0.593 | 101 | +0.47 [-0.34, +1.33] | 0.557 |
| tsmom_12_1 | 136 | +0.45 [-0.11, +1.45] | 0.560 | 101 | +0.13 [-0.41, +0.74] | 0.540 |
| reversal_1m | 136 | -0.00 [-0.58, +0.50] | 0.484 | 101 | +0.18 [-0.44, +0.71] | 0.510 |
| econ_factor_credit | 136 | +0.20 [-0.28, +1.13] | 0.589 | 101 | +0.66 [-0.08, +1.35] | 0.575 |
| ie_market_momentum | 136 | -0.22 [-0.70, +0.28] | 0.510 | 101 | -0.26 [-0.84, +0.34] | 0.490 |
| logit_A | 136 | +0.54 [+0.02, +1.33] | 0.587 | 101 | +0.20 [-0.31, +0.95] | 0.547 |
| logit_B | 136 | +0.56 [+0.10, +1.36] | 0.582 | 101 | +0.04 [-0.63, +0.85] | 0.526 |
| logit_D | 136 | +0.41 [+0.06, +1.02] | 0.566 | 101 | -0.37 [-0.99, +0.31] | 0.489 |
| random_control | 136 | +0.10 [-0.42, +0.68] | 0.513 | 101 | -0.50 [-1.05, +0.02] | 0.494 |
| shuffled_label_control | 136 | +0.47 [+0.06, +1.20] | 0.582 | 101 | -0.38 [-1.01, +0.46] | 0.489 |

Ablation (paired, same rows):

| comparison (new vs reference, same rows) | dates | forecasts | Brier new | Brier ref | skill of new over ref [CI] | p (skill<=0) |
|---|---|---|---|---|---|---|
| logit_B_vs_logit_A | 237 | 5860 | 0.2697 | 0.2507 | -0.0758 [-0.1306, -0.0255] | 1.000 |
| logit_C | - | - | - | - | NOT_MEASURED: news/company-evidence provider PENDING | - |
| logit_D_vs_logit_A | 237 | 5860 | 0.2831 | 0.2507 | -0.1291 [-0.2104, -0.0586] | 1.000 |
| logit_D_vs_logit_B | 237 | 5860 | 0.2831 | 0.2697 | -0.0495 [-0.0794, -0.0229] | 1.000 |
| shuffled_label_control_vs_logit_B | 237 | 5860 | 0.2630 | 0.2697 | +0.0248 [-0.0166, +0.0665] | 0.137 |

Controls (paired, same dates):

| comparison | Sharpe diff [CI] | ann. return diff [CI] | p (return diff<=0) |
|---|---|---|---|
| buy_and_hold_vs_random_control | +0.77 [+0.15, +1.40] | +7.93% [+1.96%, +13.45%] | 0.006 |
| econ_factor_credit_vs_random_control | +0.63 [+0.03, +1.20] | +4.90% [+0.37%, +9.44%] | 0.015 |
| ie_market_momentum_vs_random_control | -0.04 [-0.60, +0.49] | -1.36% [-5.01%, +2.55%] | 0.765 |
| logit_A_vs_random_control | +0.55 [+0.01, +1.12] | +4.76% [+0.34%, +8.81%] | 0.020 |
| logit_B_vs_random_control | +0.52 [-0.03, +1.10] | +4.17% [-0.32%, +8.24%] | 0.034 |
| logit_D_vs_random_control | +0.25 [-0.24, +0.80] | +1.41% [-2.61%, +5.15%] | 0.229 |
| reversal_1m_vs_random_control | +0.28 [-0.26, +0.76] | +1.75% [-2.31%, +5.97%] | 0.191 |
| tsmom_12_1_vs_random_control | +0.47 [-0.03, +1.07] | +3.81% [-0.45%, +7.89%] | 0.041 |

#### COMPANY universe: 237 decision dates (2007-01-04 .. 2026-09-17), 54 instruments

Books (net of costs):

| policy | provenance | net Sharpe [95% CI] | gross Sharpe | ann. excess return | vol | max DD | turnover | cost drag/yr | abstain | vs buy-and-hold Sharpe [CI] | Holm p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | BASELINE | +1.31 [+0.95, +1.69] | +1.37 | +6.9% | 5.2% | 6% | 0.01 | 0.31% | 0% | n/a  | - |
| cash | BASELINE | n/a  | n/a | +0.0% | 0.0% | 0% | 0.00 | 0.00% | 100% | n/a  | - |
| tsmom_12_1 | BASELINE | +0.14 [-0.23, +0.55] | +0.22 | +1.1% | 7.7% | 26% | 0.27 | 0.63% | 0% | -1.18 [-1.72, -0.58] | 1.000 |
| reversal_1m | BASELINE | +0.14 [-0.24, +0.50] | +0.38 | +0.9% | 6.4% | 20% | 1.01 | 1.51% | 0% | -1.17 [-1.68, -0.66] | 1.000 |
| ie_market_momentum | EXISTING_ENGINE | -0.68 [-1.07, -0.29] | -0.46 | -4.2% | 6.2% | 64% | 0.94 | 1.36% | 23% | -1.99 [-2.48, -1.50] | 1.000 |
| ie_econ_transmission | EXISTING_ENGINE | -1.23 [-1.64, -0.84] | -1.17 | -6.7% | 5.4% | 74% | 0.07 | 0.33% | 17% | -2.54 [-3.29, -1.83] | 1.000 |
| ie_econ_bayes | NEW_IN_THIS_WORK | -0.06 [-0.48, +0.37] | -0.05 | -0.1% | 1.3% | 6% | 0.01 | 0.02% | 97% | -1.37 [-1.95, -0.78] | 1.000 |
| logit_A | NEW_IN_THIS_WORK | +0.72 [+0.35, +1.09] | +0.79 | +3.7% | 5.1% | 11% | 0.21 | 0.39% | 53% | -0.60 [-0.89, -0.30] | 1.000 |
| logit_B | NEW_IN_THIS_WORK | +0.43 [-0.08, +0.95] | +0.51 | +2.4% | 5.5% | 28% | 0.21 | 0.45% | 32% | -0.88 [-1.46, -0.33] | 1.000 |
| logit_D | NEW_IN_THIS_WORK | +0.28 [-0.23, +0.80] | +0.36 | +1.5% | 5.5% | 31% | 0.21 | 0.46% | 28% | -1.04 [-1.59, -0.50] | 1.000 |
| random_control | CONTROL | -0.34 [-0.88, +0.19] | +0.09 | -1.2% | 3.5% | 30% | 1.02 | 1.52% | 0% | -1.65 [-2.28, -1.05] | - |
| permutation_control | CONTROL | -1.42 [-1.83, -1.05] | -1.30 | -6.6% | 4.7% | 74% | 0.26 | 0.56% | 17% | -2.74 [-3.49, -2.04] | - |
| shuffled_label_control | CONTROL | +0.01 [-0.51, +0.60] | +0.11 | +0.0% | 4.6% | 30% | 0.24 | 0.47% | 39% | -1.30 [-1.90, -0.67] | - |

Forecasts and trades:

| policy | forecasts | traded | hit rate [CI] | avg win | avg loss | EV/trade net [CI] | Brier | Brier (climatology) | Brier skill [CI] | log loss | calib. slope | Holm p (skill>0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | 11644 | 11644 | 0.520 [0.509, 0.531] | +6.01% | -5.38% | +0.39% [+0.22%, +0.58%] | 0.2505 | 0.2496 | -0.0034 [-0.0057, -0.0010] | 0.6942 | n/a | 1.000 |
| tsmom_12_1 | 11644 | 11644 | 0.511 [0.499, 0.524] | +5.68% | -5.72% | -0.05% [-0.30%, +0.18%] | 0.2514 | 0.2496 | -0.0069 [-0.0125, -0.0015] | 0.6959 | 0.19 | 1.000 |
| reversal_1m | 11644 | 11644 | 0.508 [0.496, 0.520] | +5.79% | -5.62% | +0.00% [-0.19%, +0.20%] | 0.2517 | 0.2496 | -0.0083 [-0.0135, -0.0031] | 0.6966 | 0.17 | 1.000 |
| ie_market_momentum | 9005 | 9005 | 0.486 [0.474, 0.499] | +5.75% | -6.17% | -0.50% [-0.78%, -0.23%] | 0.2539 | 0.2498 | -0.0163 [-0.0216, -0.0111] | 0.7009 | -0.35 | 1.000 |
| ie_econ_transmission | 9658 | 9658 | 0.480 [0.467, 0.492] | +5.29% | -6.19% | -0.84% [-1.08%, -0.60%] | 0.2545 | 0.2496 | -0.0195 [-0.0270, -0.0123] | 0.7022 | n/a | 1.000 |
| ie_econ_bayes | 9658 | 368 | 0.511 [0.454, 0.564] | +6.09% | -6.85% | -0.34% [-1.71%, +0.86%] | 0.2503 | 0.2496 | -0.0026 [-0.0063, +0.0007] | 0.6938 | 0.13 | 1.000 |
| logit_A | 11644 | 5492 | 0.520 [0.505, 0.534] | +7.27% | -6.42% | +0.54% [+0.22%, +0.87%] | 0.2502 | 0.2496 | -0.0023 [-0.0048, -0.0001] | 0.6936 | -0.24 | 1.000 |
| logit_B | 11644 | 7954 | 0.512 [0.498, 0.525] | +6.29% | -5.93% | +0.18% [-0.16%, +0.48%] | 0.2521 | 0.2496 | -0.0100 [-0.0190, -0.0035] | 0.6978 | -0.13 | 1.000 |
| logit_D | 11644 | 8369 | 0.503 [0.490, 0.517] | +6.23% | -5.89% | +0.07% [-0.26%, +0.35%] | 0.2555 | 0.2496 | -0.0236 [-0.0423, -0.0096] | 0.7052 | -0.10 | 1.000 |
| random_control | 11644 | 11644 | 0.499 [0.492, 0.506] | +5.70% | -5.71% | -0.17% [-0.32%, -0.02%] | 0.2500 | 0.2496 | -0.0014 [-0.0035, +0.0006] | 0.6931 | n/a | - |
| permutation_control | 9658 | 9658 | 0.476 [0.463, 0.488] | +5.37% | -6.11% | -0.81% [-1.00%, -0.63%] | 0.2549 | 0.2495 | -0.0218 [-0.0295, -0.0145] | 0.7030 | n/a | - |
| shuffled_label_control | 11644 | 7154 | 0.505 [0.490, 0.521] | +5.49% | -5.52% | -0.10% [-0.45%, +0.21%] | 0.2517 | 0.2496 | -0.0082 [-0.0153, -0.0025] | 0.6967 | -0.17 | - |

By regime at the decision (econ.regime, point in time):

| policy | CALM periods | CALM Sharpe [CI] | CALM hit | STRESS periods | STRESS Sharpe [CI] | STRESS hit |
|---|---|---|---|---|---|---|
| buy_and_hold | 136 | +1.42 [+0.91, +1.98] | 0.525 | 101 | +1.26 [+0.72, +1.78] | 0.513 |
| tsmom_12_1 | 136 | +0.29 [-0.20, +0.84] | 0.508 | 101 | +0.01 [-0.52, +0.63] | 0.516 |
| reversal_1m | 136 | -0.26 [-0.87, +0.27] | 0.498 | 101 | +0.58 [+0.16, +1.10] | 0.520 |
| ie_market_momentum | 136 | -0.08 [-0.63, +0.47] | 0.504 | 101 | -1.41 [-1.87, -0.99] | 0.464 |
| ie_econ_transmission | 136 | -1.26 [-1.86, -0.68] | 0.477 | 101 | -1.23 [-1.71, -0.71] | 0.483 |
| ie_econ_bayes | 136 | +0.42 [-0.21, +0.86] | 0.583 | 101 | -0.33 [-0.89, +0.34] | 0.461 |
| logit_A | 136 | +0.88 [+0.48, +1.29] | 0.534 | 101 | +0.58 [+0.02, +1.19] | 0.508 |
| logit_B | 136 | +0.80 [+0.23, +1.34] | 0.524 | 101 | +0.09 [-0.58, +0.87] | 0.500 |
| logit_D | 136 | +0.57 [+0.01, +1.15] | 0.512 | 101 | +0.02 [-0.63, +0.83] | 0.495 |
| random_control | 136 | -0.17 [-0.65, +0.34] | 0.501 | 101 | -0.52 [-1.42, +0.30] | 0.496 |
| permutation_control | 136 | -1.57 [-2.12, -1.09] | 0.468 | 101 | -1.32 [-1.85, -0.77] | 0.485 |
| shuffled_label_control | 136 | +0.57 [+0.02, +1.22] | 0.516 | 101 | -0.37 [-1.08, +0.51] | 0.492 |

Ablation (paired, same rows):

| comparison (new vs reference, same rows) | dates | forecasts | Brier new | Brier ref | skill of new over ref [CI] | p (skill<=0) |
|---|---|---|---|---|---|---|
| logit_B_vs_logit_A | 237 | 11644 | 0.2521 | 0.2502 | -0.0077 [-0.0149, -0.0023] | 1.000 |
| logit_C | - | - | - | - | NOT_MEASURED: news/company-evidence provider PENDING | - |
| logit_D_vs_logit_A | 237 | 11644 | 0.2555 | 0.2502 | -0.0213 [-0.0383, -0.0081] | 1.000 |
| logit_D_vs_logit_B | 237 | 11644 | 0.2555 | 0.2521 | -0.0135 [-0.0254, -0.0046] | 1.000 |
| shuffled_label_control_vs_logit_B | 237 | 11644 | 0.2517 | 0.2521 | +0.0018 [-0.0035, +0.0074] | 0.255 |

Controls (paired, same dates):

| comparison | Sharpe diff [CI] | ann. return diff [CI] | p (return diff<=0) |
|---|---|---|---|
| buy_and_hold_vs_random_control | +1.65 [+1.05, +2.28] | +8.08% [+5.27%, +11.48%] | 0.000 |
| ie_econ_bayes_vs_permutation_control | +1.36 [+0.81, +1.95] | +6.55% [+4.77%, +8.37%] | 0.000 |
| ie_econ_bayes_vs_random_control | +0.28 [-0.25, +0.83] | +1.11% [-0.58%, +2.85%] | 0.102 |
| ie_econ_transmission_vs_permutation_control | +0.19 [-0.03, +0.43] | -0.03% [-1.33%, +1.19%] | 0.505 |
| ie_econ_transmission_vs_random_control | -0.89 [-1.60, -0.18] | -5.47% [-8.32%, -2.49%] | 1.000 |
| ie_market_momentum_vs_random_control | -0.34 [-1.00, +0.30] | -3.00% [-5.94%, -0.07%] | 0.979 |
| logit_A_vs_random_control | +1.05 [+0.48, +1.65] | +4.86% [+2.40%, +7.35%] | 0.000 |
| logit_B_vs_random_control | +0.77 [+0.25, +1.30] | +3.56% [+1.06%, +5.94%] | 0.004 |
| logit_D_vs_random_control | +0.62 [+0.09, +1.17] | +2.71% [+0.04%, +5.19%] | 0.023 |
| reversal_1m_vs_random_control | +0.48 [-0.18, +1.15] | +2.08% [-0.96%, +5.35%] | 0.093 |
| tsmom_12_1_vs_random_control | +0.48 [-0.06, +1.07] | +2.26% [-0.65%, +5.28%] | 0.057 |

Econ flag separation: flagged on 83% of company-dates; flagged minus unflagged mean relative return +0.25% per period, 95% CI [-0.35%, +0.85%], over 192 dates with both groups (the engine's claim needs this NEGATIVE).

Reliability, logit_A (ETF):

| logit_A bin | n | mean p | observed | Wilson 95% (per forecast) |
|---|---|---|---|---|
| 0.0-0.1 | 16 | 0.065 | 0.500 | [0.280, 0.720] |
| 0.1-0.2 | 26 | 0.148 | 0.385 | [0.224, 0.575] |
| 0.2-0.3 | 37 | 0.251 | 0.432 | [0.287, 0.591] |
| 0.3-0.4 | 56 | 0.365 | 0.554 | [0.424, 0.676] |
| 0.4-0.5 | 463 | 0.475 | 0.579 | [0.533, 0.623] |
| 0.5-0.6 | 2467 | 0.561 | 0.587 | [0.567, 0.606] |
| 0.6-0.7 | 2638 | 0.627 | 0.580 | [0.561, 0.598] |
| 0.7-0.8 | 118 | 0.727 | 0.449 | [0.362, 0.539] |
| 0.8-0.9 | 21 | 0.850 | 0.476 | [0.283, 0.676] |
| 0.9-1.0 | 18 | 0.954 | 0.500 | [0.290, 0.710] |

Post-hoc specification diagnostic (not used by any policy):

| family | train / test rows | test Brier of train base rate | set | in-sample Brier at L2 0.1 -> 1000 | out-of-sample Brier at L2 0.1 -> 1000 |
|---|---|---|---|---|---|
| company/company | 6317 / 7263 | 0.2497 | A | 0.2493 / 0.2493 / 0.2493 / 0.2493 / 0.2493 | 0.2497 / 0.2497 / 0.2497 / 0.2497 / 0.2496 |
| company/company | 6317 / 7263 | 0.2497 | B | 0.2491 / 0.2491 / 0.2491 / 0.2491 / 0.2492 | 0.2506 / 0.2506 / 0.2506 / 0.2504 / 0.2498 |
| company/company | 6317 / 7263 | 0.2497 | D | 0.2490 / 0.2490 / 0.2490 / 0.2490 / 0.2492 | 0.2511 / 0.2511 / 0.2511 / 0.2507 / 0.2499 |
| etf/bond | 736 / 846 | 0.2501 | A | 0.2445 / 0.2445 / 0.2446 / 0.2449 / 0.2452 | 0.2498 / 0.2498 / 0.2497 / 0.2497 / 0.2499 |
| etf/bond | 736 / 846 | 0.2501 | B | 0.2391 / 0.2392 / 0.2392 / 0.2405 / 0.2437 | 0.2598 / 0.2596 / 0.2581 / 0.2511 / 0.2485 |
| etf/bond | 736 / 846 | 0.2501 | D | 0.2357 / 0.2357 / 0.2359 / 0.2379 / 0.2425 | 0.2589 / 0.2588 / 0.2581 / 0.2535 / 0.2487 |
| etf/commodity | 379 / 564 | 0.2495 | A | 0.2492 / 0.2492 / 0.2492 / 0.2495 / 0.2498 | 0.2505 / 0.2504 / 0.2502 / 0.2496 / 0.2495 |
| etf/commodity | 379 / 564 | 0.2495 | B | 0.2309 / 0.2311 / 0.2325 / 0.2395 / 0.2472 | 0.2760 / 0.2753 / 0.2693 / 0.2527 / 0.2489 |
| etf/commodity | 379 / 564 | 0.2495 | D | 0.2167 / 0.2168 / 0.2183 / 0.2284 / 0.2435 | 0.2909 / 0.2899 / 0.2816 / 0.2565 / 0.2484 |
| etf/equity_broad | 841 / 846 | 0.2379 | A | 0.2349 / 0.2349 / 0.2349 / 0.2353 / 0.2365 | 0.2428 / 0.2427 / 0.2425 / 0.2410 / 0.2388 |
| etf/equity_broad | 841 / 846 | 0.2379 | B | 0.2206 / 0.2206 / 0.2209 / 0.2246 / 0.2329 | 0.2524 / 0.2521 / 0.2492 / 0.2396 / 0.2382 |
| etf/equity_broad | 841 / 846 | 0.2379 | D | 0.2120 / 0.2121 / 0.2130 / 0.2198 / 0.2306 | 0.2680 / 0.2674 / 0.2622 / 0.2445 / 0.2387 |
| etf/sector | 1287 / 1269 | 0.2408 | A | 0.2356 / 0.2356 / 0.2356 / 0.2359 / 0.2371 | 0.2447 / 0.2447 / 0.2445 / 0.2432 / 0.2416 |
| etf/sector | 1287 / 1269 | 0.2408 | B | 0.2231 / 0.2231 / 0.2233 / 0.2256 / 0.2334 | 0.2618 / 0.2616 / 0.2593 / 0.2478 / 0.2409 |
| etf/sector | 1287 / 1269 | 0.2408 | D | 0.2196 / 0.2197 / 0.2200 / 0.2233 / 0.2313 | 0.2632 / 0.2629 / 0.2605 / 0.2491 / 0.2416 |

Ledgers:

- `reports/paper_validation/forward_shadow_ledger.jsonl` (FORWARD_SHADOW): 977 chained entries, 977 forecasts, by status {'OPEN': 977}
- `reports/paper_validation/rehearsal_ledger.jsonl` (REHEARSAL): 1200 chained entries, 600 forecasts, by status {'RESOLVED': 600}

Guards: oracle canary refused 285/285 dates; truncation checks 570 with 0 violations; 0 voided cells.

<!-- END GENERATED TABLES -->

## Leakage checks that can fail, and did when broken

* **Evidence dates.** Every decision lists its evidence ids (price windows,
  panel cells with their vintage, the econ state's cutoff and node periods).
  `leakage.check_evidence` refuses any input dated after the decision and
  any id with no date.
* **Oracle canary.** On every one of the 285 dates, a decision that peeks at
  its own exit bar goes through the same checker. It was refused 285/285
  times. The replay stops if it is ever accepted.
* **Truncation.** On 570 rows, features were recomputed from bars cut at the
  decision date. There were 0 differences.
* **Purge.** Training rows must have their exit on or before the refit date
  (`assert_purged`). The point-in-time climatology uses only outcomes known
  at the decision.
* **Negative controls.** `random_control` hits 0.504 (ETF) and 0.499
  (company), with Brier skill intervals spanning zero.
  `shuffled_label_control` is statistically indistinguishable from logit_B,
  the model it shadows, and its point estimate is slightly BETTER in both
  universes, which is the finding about logit_B above.

**Break-proofs: 11 of 11 held**, run from inside a pristine `git archive`
export of the final staged code tree (`2eb19e34...`; this report's later
wording edits change no code) with the existing
`break_proof_harness` (five conditions; the mutation never touches the guard
it tests). Each mutated a producer and turned its paired test red for the
stated reason:

1. a price feature reads tomorrow's close;
2. the resolver stops waiting for the exit session;
3. climatology counts outcomes not yet known;
4. training history is not purged;
5. macro reads a revision published after the decision;
6. the chain hash stops covering the payload;
7. a private company is handed a security;
8. the leak checker goes dead, so the canary must stop the replay;
9. the econ state is built later than it says;
10. a record is mislabelled into the wrong ledger kind;
11. the "existing engine" policy stops calling the engine.

The first run held 9 of 11. Proofs 7 and 9 failed for the wrong reason: the
harness mirrors only `src/`, and the manifest and the econ publisher were
located relative to the package. The tests now load the manifest from the
repository root, and the publisher lookup falls back to the working
directory. Both then held.

## Forward shadow ledger

`reports/paper_validation/forward_shadow_ledger.jsonl`, kind
FORWARD_SHADOW, owned by this work.

* **977 registered, 0 resolved, 0 voided.** That is 25 ETFs x 11 policies
  plus 54 companies x 13 policies, abstentions included, because a record
  of only the trades we chose to take has its losers pre-filtered.
* Decided 2026-11-10T01:50Z (2026-11-09 New York), prices complete through
  2026-11-06. Yahoo had no final close for 11-09 when this ran, and the bar
  was dropped rather than used provisionally. Macro came from a FRED
  current-vintage snapshot retrieved the same evening, stamped with its New
  York retrieval date. The replay panel ends 2026-08-28.
* The entry is the 2026-11-10 open and the exit the 2026-12-10 open (21
  sessions; Thanksgiving closed). The resolver was run and left all 977
  OPEN.
* Every record carries: decision timestamp and date, information cutoff
  and price cutoff, instrument, scope, target, direction or abstention with
  its reason, probability, horizon, entry and exit rules, risk budget,
  invalidation condition, expected cost, evidence ids, thesis, causal
  mechanism, competing hypotheses, policy, version and provenance, model
  version (weight hash for fitted models), data vintage, protocol hash,
  regime, and the cash rate the resolution will use.
* **Disclosure.** The first registration run (01:50Z) embedded all 79
  symbols' price vintage in every record (13 MB). It was deleted
  uncommitted and re-run minutes later, with each record carrying only its
  own instrument's and SPY's vintage, plus a batch manifest
  (`forward_batches/2026-11-09.json`). Both runs were before the entry
  session opened. No outcome was knowable, and the decisions come from the
  same code and data.

## Rehearsal: the resolver proven before it is needed

`reports/paper_validation/rehearsal_ledger.jsonl`, kind REHEARSAL. It holds
600 backdated records (24 decision dates, 2024-01 to 2025-12, 25 ETFs) with
FIXED-CONSTANT probabilities (LONG at 0.55; every fifth instrument
abstains). They went through the same record builder and the single
resolver ([[prove-the-resolver-before-it-is-needed]]).

* With the clock at each registration, the resolver closed 550 older
  windows as the clock advanced, and **0** records registered in that same
  step.
* At today's clock, all 600 resolved; none voided. The chain verifies at
  1,200 entries.
* The shadow learning loop ran over it. Attribution: HIT 256, MISS 176,
  NEAR_MISS 12, COST_LOSS 12, ABSTAIN_MISSED 138, ABSTAIN_SPARED 6. Drift:
  STABLE. Promotion: NOT_ELIGIBLE (24 of 36 dates). Beliefs went to the
  rehearsal-only file, and no candidate was proposed.

None of this is evidence about a model. It shows the machinery works.

## Learning loop (shadow)

`learning_loop.run` resolves, attributes each outcome (HIT, COST_LOSS,
NEAR_MISS, MISS, ABSTAIN_SPARED, ABSTAIN_MISSED), and updates Beta beliefs
per (policy, family) in a belief file of the same ledger kind. It refuses
cross-kind learning both ways, and refuses the replay. It tracks
calibration drift over 12-date windows, applies the preregistered promotion
bar as a readiness report, and proposes candidates to
`learning.LearningLedger` at `data/paper_validation_shadow_learning*.db`
(gitignored). That ledger's `promote` refuses any non-human actor (tested),
and nothing here calls it. The only thing a belief changes is the next
shadow decision of `ie_econ_bayes`.

## Remaining scientific limitations

1. **Survivorship and selection.** The company list is the 2026 manifest
   and the ETFs are ones that survived to 2026. Relative buy-and-hold's +1.31
   Sharpe measures this bias. Short-leaning company policies are penalised
   by it and long-leaning ones flattered.
2. **The engine was written after the history it is tested on.** The
   transmission table and its signs were authored in 2026 with 2008 and 2022
   in view. The replay is out of sample for the models, not for the engine's
   design. Only the forward ledger is clean.
3. **The exposure assumption.** The product admits a company's exposure
   only from its own documents. The replay gives every company every channel
   its class has a transmission for, which can only make the arm flag more
   often.
4. **One horizon, one mapping.** Twenty-one sessions, and "any adverse
   channel means short relative". The engine's mechanisms may act over
   quarters, or only on magnitude; neither is tested.
5. **Power.** At 237 periods, a Sharpe interval is about ±0.45 wide, so only
   large edges are detectable. The forward ledger needs 36 resolved dates
   (about three years) before any promotion review, and even then has low
   power.
6. **Constant rule probabilities.** A Brier score for a rule measures its
   direction only, and its calibration slope is undefined.
7. **Costs are flat.** There is no market impact, no short-availability
   constraint (HYG and USO borrow are not always 30 bps), and no
   delisting.
8. **Vintages are uneven.** Monthly series have ALFRED vintages. Daily
   series carry a one-day release lag (MEASURED_STABLE) rather than true
   vintages. Forward macro is stamped at retrieval, which is conservative.
9. **The price source is undocumented.** Yahoo's endpoint and its
   `adjclose` back-adjustment can change. Every cache carries its
   retrieval time and content sha256.
10. **Arm C (news and company evidence) is NOT_MEASURED, and the causal arm
    is NOT_IMPLEMENTED.** The D ablation is therefore B plus regime and
    transmission features only.
11. **Multiple comparisons.** Holm is applied within each universe's two
    families. Regime cells and diagnostics are not corrected.
12. **The regime split is binary in practice.** MIXED never occurred.

## Proposed scheduler (NOT installed)

A human installs this after review. Nothing in this branch installs it.

```xml
<!-- ~/Library/LaunchAgents/com.intentengine.papervalidation.daily.plist (PROPOSED) -->
<key>ProgramArguments</key>
<array>
  <string>/bin/zsh</string><string>-c</string>
  <string>cd /Users/prathamsharma/ie-paper-validation &amp;&amp;
    PYTHONPATH=src .venv/bin/python -m intent_engine.paper_validation resolve &amp;&amp;
    PYTHONPATH=src .venv/bin/python -m intent_engine.paper_validation register --if-due &amp;&amp;
    PYTHONPATH=src .venv/bin/python -m intent_engine.paper_validation learn</string>
</array>
<key>StartCalendarInterval</key><dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>15</integer></dict>
<key>EnvironmentVariables</key><dict><key>TZ</key><string>America/New_York</string></dict>
```

* `register --if-due` registers only when 21 sessions have completed since
  the last registration, so a daily job keeps the protocol's cadence.
* `resolve` records only windows whose exit session is over.
* 19:15 ET is after Yahoo's daily close has usually finalised. An
  unfinished bar is dropped either way.
* The worktree has no `.venv`. Point the job at
  `/Users/prathamsharma/intent-engine/.venv/bin/python` with
  `PYTHONPATH=src` (see the worktree venv trap).
* Commit the ledger after each run. Git history is a second, independent
  timestamp on every registration. This is a human or approved step; the
  job does not push.

## Reproduce

```bash
cd ~/ie-paper-validation
PYTHONPATH=src /Users/prathamsharma/intent-engine/.venv/bin/python -m intent_engine.paper_validation replay
PYTHONPATH=src /Users/prathamsharma/intent-engine/.venv/bin/python -m intent_engine.paper_validation.report --splice
PYTHONPATH=src /Users/prathamsharma/intent-engine/.venv/bin/python -m intent_engine.paper_validation status
/Users/prathamsharma/intent-engine/.venv/bin/python -m pytest tests/test_paper_validation_*.py -q
```

Break-proofs, from a pristine export:

```bash
T=$(git write-tree); E=$(mktemp -d); git archive $T | tar -x -C $E
cd $E && GUARD_PYTHON=/Users/prathamsharma/intent-engine/.venv/bin/python \
  /Users/prathamsharma/intent-engine/.venv/bin/python scripts/break_proofs_paper_validation.py
```

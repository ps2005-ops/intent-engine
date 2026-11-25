# Scientific reconstruction — first results (2026-11-25)

Evidence labels used throughout:

* **IMPLEMENTED**: code exists and is tested.
* **OPERATIONAL**: it runs in production on its own.
* **PROMISING**: a development-set result only.
* **HISTORICALLY VALIDATED**: positive on an untouched holdout.
* **PROSPECTIVELY VALIDATED**: positive on forward outcomes.
* **COMMERCIALLY VALIDATED**: improves a real decision.

**Nothing below reaches the last three.** Every artifact cited is in
`reports/learning_loop/` and every script in `scripts/learning_loop/`.

## 0. Capability matrix: real invocation, not module existence

Evidence: a `sys.setprofile` trace of a full night cycle on 92ce0f39 against
a production copy (314 modules, 3,121 distinct functions called;
`capability_trace_night_2026-11-25.txt`). "Substantive" excludes imports,
dataclass construction and comprehensions. The market cycle issues no traded
forecast; paper-validation forecasts come from `paper_validation/policies.py`.

| Mechanism | Code | Runs in the cycle? (substantive calls) | Affects forecasts | Reaches Founder | Independently evaluated | Contribution |
|---|---|---|---|---|---|---|
| Economic state estimation | `econ/state.py`, `market/macro_state.py` | YES: `known_at`, `as_known_at`, `moved` | paper B/D via `paper_validation/macro.py` | YES, `econ_publish` → state_snapshot | replay ablation | **negative** (§2) |
| Bayesian inference | `econ/bayes.py` | builds records and `summarise` only; no posterior computed in the cycle | `ie_econ_bayes` (paper, 97% abstain) | no | replay | not distinguishable from 0 |
| Public belief / level-k / reflexivity | `econ/levelk.py`, `econ/reflexivity.py`, `econ/collective.py` | YES: `react`, `net_flow`, `armed_loops`, `usable_dimensions` | no | yes, state export | never | unknown |
| Expectation modelling | `econ/belief.py` YES (`declare`, `fragility`); `market/macro_expectation.py` NOT CALLED | business expectations (not prices) | dossiers | 47 grades, 27 inadmissible (§6) | unknown after correction |
| Hidden-state estimation | `market/hidden_state.py` | YES: `observe`, `_renormalise`, `entropy` | no | dossier `hidden_states` | never | unknown |
| Causal inference | `econ/causal.py`, `market/causal_episodes.py` | YES: edge gating, `may_state_causation`; `causal_diagnostics` only constructed | no; no edge reaches an asset return | dossier `causal_pathways` | never | unknown |
| Game theory / strategic interaction | `market/strategic_interaction.py` | dataclasses and `InteractionRejected` only; no pattern reaches a decision | no | dossier `interactions` | never | not operating |
| Business dependency graph | `core/entity_graph.py` | NOT CALLED | no | no | never | not operating |
| Econometrics (method checks) | `market/economic_method.py` | YES: `_fit_ar1`, persistence, drift (1.46M calls) | gates causal language | no | built-in walk-forward vs persistence | method does not beat persistence (its own records) |
| Market regime detection | `econ/regime.py` | NOT CALLED in the market cycle; used by the paper replay | paper D (regime dummies) | no | replay | **negative** (logit_D) |
| Evidence ranking / translation | `market/evidence_translation.py` | YES | expectations | dossiers | relevance audits | precision issues documented in memory |
| Information gain / VOI | `market/research_policy.py` YES (bandit `choose`/`reward`); `econ/voi.py` NOT CALLED | research allocation | no | never against a random policy | unknown |
| Momentum | `market/strategy_library.py` | YES since 92ce0f39 (shadow), never traded | shadow only | no | reconstructed 0.318 (CI 0.22–0.42); replay Holm p=1 | **negative** in 2026 window |
| Mean reversion | `strategy_library.mean_reversion` | NOT CALLED | `reversal_1m` paper baseline | no | replay; forward 12-11 | Holm p=1 |
| Economic transmission | `econ/transmission*.py` NOT CALLED in the cycle; `econ/shock.py` YES | paper `ie_econ_transmission` | yes (shock bands) | replay | Holm p=1; replay says NOT_IMPLEMENTED for causal_filtered |
| Forecast calibration | `econ/calibration.py` NOT CALLED; `market/learning_health.py` YES | no | no | — | calibration measured on 47 grades (see §6 caveat) |
| Risk / zero-trade | `market/paper_engine.py`, `econ/zero_trade.py` | YES (no position ever opened) | no | yes | — | — |
| Belief formation (demand) | `market/belief_formation.py` | YES: `direction_of`, `routes_for`, **the defect** | expectations | 19 dossiers carry its demand-weakening beliefs | graded | **failing** (§6) |
| Outcome resolution | `market/outcome_resolver.py` | YES (operational since the switch) | — | — | 21 tests, mutation-checked | — |

## 1. Production runtime activation (OPERATIONAL)

| Check | Result |
|---|---|
| Before | launchd `market.{day,night,health}` ran `~/intent-engine-market/src` at 195c6f4a, a dirty worktree (87 changed paths) that was also the data root |
| Contained | 195c6f4a is an ancestor of the integration commit. The only dependency change is PyYAML 6.0.3, already installed |
| Backup | `canonical-ledgers-20261125-130158`: 639 files, 0 restore mismatches, July `integrity_check=ok`. Plists and crontab saved in `plists-20261125-130158/` |
| Compatibility found | `load_dotenv()` searches from the CODE's location, so code moved out of the data root would have run without FRED or Tiingo keys. Fixed with a symlink `~/ie-market-runtime/.env` to the one existing file (gitignored; no copy of the secret) |
| Isolated cycle | Night cycle on 92ce0f39 against a copy of production: all 17 steps ok, exit 0. Two new steps: `econ_publish` and `econ_aggregate`, which write only under the market root (single writer kept). Shadow momentum was recorded on new rows. The live runtime was byte-identical before and after |
| Switch | Only `EnvironmentVariables.PYTHONPATH` changed in the three plists, to `~/ie-market-runtime/src` (clean, detached at 92ce0f39). `--root`, interpreter and working directory are unchanged |
| First production run | `market.health` at load: `git 92ce0f39dc3e on HEAD clean`, exit 0. The first scheduled night cycle is 20:30 today, and a verifier is waiting for it |
| Rollback | `~/intent-engine-safety-backups/ROLLBACK_market_runtime_20261125.sh` |
| Automatic now | `resolve_outcomes` and shadow `baseline_momentum.v1` are cycle steps, no longer run by hand |
| 06:00 July resolver | Retired: crontab line commented with its original text, before/after saved, 49 logs kept. Its only duty was rule-bearing July forecasts. 0 remain open, the generator is retired, and corrections go through `supersede_unresolvable` |
| Learning runtime | `~/ie-learning-runtime` re-pinned to 82d0bb07, so the forecast-quality gate is mandatory on tonight's `register --if-due` |
| Premortem 32bbf0c5 | Classified TEST_FIXTURE (`forecast_quality.TEST_FIXTURE_ENTITIES`), as are its two siblings a4446e76 and a5bca63d. Preserved, excluded from real statistics, never resolved |

## 2. Why the economic features failed (diagnosed)

These are controlled experiments on the replay's own observation rows
(20,422), with train before 2015 and test from 2015, the same fitter, and a
block bootstrap over dates (`diag_macro_ablation`, `diag_macro_horizon_regime_trace`).

| Hypothesis | Test | Result | Verdict |
|---|---|---|---|
| Weak information | Macro vectors swapped in from a random other date (placebo) | The placebo damages as much as the real macro (companies −0.0002 vs −0.0009; ETFs −0.006 to −0.013 vs −0.009 to −0.025) | **Primary cause.** No transferable information at this horizon |
| Overfitting / dimensionality | Effective sample, L2 sweep | 107–143 training dates for 9 date-level parameters (12–16 per parameter; yearly refits start far lower). ETFs: in-sample improves, out-of-sample degrades; L2=1000 only shrinks back to the base rate | **Contributing.** It is why "no information" becomes "harmful" |
| Regime change | Univariate coefficient sign before vs from 2015 | 5 of 9 (equity_broad) and 6 of 9 (sector) flip sign. For example d_dff_365d +0.30 → −0.27: hikes during recoveries before 2015, hikes into a drawdown in 2022 | **Primary cause** for ETFs |
| Out-of-distribution extrapolation | End-to-end trace, SPY 2022-03-10 | d_unrate_365d = −2.4 (COVID recovery) is far outside the training range. B gives p=0.36 against A's 0.59; SPY rose +4.1% | Observed mechanism |
| Stale or late data | Macro lagged one decision date | No change | Rejected |
| Wrong horizon | 63-session target | Macro still hurts in every family (−0.003 to −0.028) | Rejected |
| Wrong exposure mapping (companies) | macro × beta interactions | −0.0006 (CI −0.0015, +0.0004) | Rejected for this mapping |
| Leakage / vintages / units | Replay guards, panel vintages, trace | Canary refused 285/285, 0 truncation violations, ALFRED vintages. CPI uses an assumed 50-day lag (later than the real release, so conservative) | Methodology sound |
| Integration defect | Trace | Features reach the model as intended | Rejected |

**Structural finding.** For companies the target is excess return over SPY.
Every macro feature has the same value for every company on a date, and no
company-specific exposure exists. That model can only time the average
company against SPY, which by construction is near 0.5. The original
philosophy (actors, exposures, intentions) was never in the replay's
feature set.

## 3. A bounded test of company-specific, point-in-time information

`exp_point_in_time_fundamentals`. SEC XBRL company facts, walled on the
`filed` date (filed before the decision), for 53 of the 54 companies from
2009-12:

* revenue growth year on year;
* revenue acceleration (growth against the company's own previous quarter;
  historical consensus is UNAVAILABLE and is not invented);
* fiscal-year capex growth (resource commitment);
* filing recency.

The comparison is on matched rows against the price-only model A.

| Split | Gain over A (+ = helps) | 95% CI | Placebo (shuffled across companies) |
|---|---|---|---|
| Validation 2015–2020 | +0.00044 | −0.00020, +0.00109 | −0.00061 |
| **Holdout 2021–2026 (run once)** | **−0.00101** | **−0.00190, −0.00013** | −0.00028 |

Verdict: negative. Public fundamentals, including the capex
resource-commitment signal, do not predict 21-session relative returns in
this universe. Acceleration keeps a small, stable positive weight (0.06 →
0.085) but does not survive out of sample.

## 4. Forecast-quality gate (IMPLEMENTED, OPERATIONAL for paper registration)

`core/forecast_quality.py`. It rejects or quarantines:

* forecasts already true at creation;
* unit mismatches or impossible thresholds;
* claim/rule mismatches;
* missing rule, target or source;
* evidence after the cutoff;
* duplicates;
* fixtures.

A missing mechanism, baseline, model version, provenance or invalidation is
QUARANTINE. It is wired into paper `register`: held forecasts go to
`forward_quarantine.jsonl` with their findings, never silently dropped.

| Ledger | Forecasts | Admit | Quarantine | Reject | Main findings |
|---|---|---|---|---|---|
| July prediction ledger | 17 | **0** | 13 | 4 | 3 fixtures, 1 unit mismatch, 4 already true at creation, 3 claim/rule mismatches. All 17 lack mechanism, baseline, model version, provenance and invalidation |
| Paper forward (Nov 9) | 977 | 977 | 0 | 0 | — |
| Econ forward | 13 | 12 | 1 | 0 | 12 machine contracts were derived from the prose rule on the creation day (flagged WARN). PERMIT has no evidence provenance |

A forced registration on a copy, through the gated path: 977 registered, 0
held.

## 5. Historical news and evidence availability

| Source | Point-in-time? | Usable here | State |
|---|---|---|---|
| SEC XBRL company facts | Yes (`end` and `filed`) | Yes, free | Used (§3) |
| SEC EDGAR filings (8-K items, acceptance time) | Yes | Yes, free | Used for OLO (§7); earnings 8-K 2.02 are available for event studies |
| GDELT 2.0 raw files | Yes (first-seen timestamps, from 2015-02-18) | URLs, organisations and tone, no text; terabyte scale | Reachable; not bounded enough for today |
| GDELT DOC API | Yes | Throttled from this host even at 8 s spacing | Blocked by rate limit |
| Google News RSS (runtime source) | No; current only | Prospective only | Capturing forward daily (5,124 sightings) |
| Paid historical news | — | Not purchased | Needs approval |

The news/evidence ablation (logit_C) therefore stays NOT MEASURED
historically. Prospective capture is running; the evidence has
`available_at`/`observed_at` separate from `seen_at`.

## 6. Mechanism failure: demand_weakening (2 of 15)

All 15 traced (`demand_weakening_15_cases`). The failure is not economic. The
family never measured demand:

* **5 surprises read as declines.** "Revenue falls short at $3,742M" while
  revenue grew; "misses EPS"; "misses on revenue".
* **6 profit, margin or cost.** "Revenue up, profitability falls"; "lowers
  profit forecast on deal costs"; "+36% revenue as restructuring widens GAAP
  loss".
* **1 price.** "Stock falls on Q2 earnings" after a beat-and-raise.
* **2 stale or irrelevant.** A 2017 tax-law sentence; an April headline.
* **1 possibly genuine.** Infosys.

Root cause: `belief_formation.direction_of` reads one up/down word anywhere
in a headline. `_ROUTES` sends any DOWN earnings, surprise or guidance
sentence to demand_weakening.

**Grading defect (affects every mechanism).** The falsifier says "the NEXT
reported figure", but 27 of the 47 graded expectations were graded by
another article about the same report, within days. Admissible grades only:

* demand_strengthening: 6 of 9;
* demand_weakening: 2 of 5.

The 0.88 vs 0.13 gap was mostly this artifact. The runtime's own reported
skill (Brier 0.2365 vs climatology 0.2408) rests on these same grades.

**Repair (IMPLEMENTED, SHADOW): `market/demand_reading.py` (v2).** The
necessary conditions are a demand quantity, moving, against the company's
own past. Surprises are kept as their own family. Price, profit, margin,
cost and headcount abstain. Same-period evidence may not grade. Applied to
the 19 founder-facing dossier beliefs that claim demand is weakening:

* 2 would be opened;
* 3 read as demand STRENGTHENING (Cloudflare, Honda, Sasol);
* 3 are surprises;
* 11 abstain.

This is the development set; it is NOT validation. It is not wired into
belief formation.

## 7. The 104 unresolvable outcomes

All are OLO. SEC record:

* merger agreement 8-K 1.01 on 2025-07-03;
* DEFM14A on 08-08;
* vote on 09-09;
* completion 8-K 2.01/3.01 and Form 25-NSE on 2025-09-12;
* Form 15-12G on 09-23.

The first OLO audit row is 2026-07-31, ten months later. All 169 OLO rows
carry `data_unavailable=true`. This is not delisting during an evaluation
window, so there is no survivorship bias and nothing to recover: no
position was ever possible. The defect is that the universe has no
instrument-liveness check.

## 8. Learning measurement

The runtime's own `learning_health` reports **LEARNING_DEGRADING**:

| Measure | Now (per day) | Prior window (per day) |
|---|---|---|
| Accepted evidence | 56 | 147 |
| Expectations created | 0.29 | 0.86 |
| Validated knowledge | 0 | 0.29 |

* **Mechanisms tested:** 4 of 16.
* **Beliefs never tested:** 129 of 176.
* **Reaching a founder:** UNMEASURABLE. No consumption acknowledgement
  reaches the runtime root.

Our corrections lower the quality side further: 27 of the 47 grades are
inadmissible. Learning is **not yet measurable as accelerating**. The first
forward sample is 2026-12-11.

## 9. Zero-Anthropic

* **Fully independent of any LLM:**
  * market cycle (all 17 steps; proven on a copy with the key absent);
  * paper validation (register, resolve, learn);
  * econ resolver;
  * forecast-quality gate;
  * demand_reading v2.
* **Degraded without an LLM:** the Founder analyst (`strategic_intelligence/analyst/runner.py`
  via `webapp/app.py`). It boots without a reasoning backend and says why on
  `/readyz`, honouring `ZERO_ANTHROPIC`.
* **Requires an LLM, and failing on credit:**
  * retired July generator;
  * the Monday 08:00 `generate_weekly_regime_report.py` cron (last log 11-09:
    "credit balance is too low"; not retired, not approved);
  * premortem, digest and caption tools under `core/` and `simulator/`.

## 10. Not done, and why

* **Groups C/D/E/F/G/H of the experimental ladder.**
  * C (surprise): historical consensus is unavailable. Own-trajectory
    surprise was tested in §3.
  * D (news): no bounded historical archive (§5).
  * F/G (causal, strategic, network): no declared causal edge reaches an
    asset return (the replay's own NOT_IMPLEMENTED), so there is nothing
    honest to evaluate yet.
* **New forward horizons.** None added. Adding one is a protocol amendment
  that has to be preregistered. The only justified candidate is an
  event-triggered 5-session window around 8-K 2.02 filings, not a daily one.
* **Enterprise decision-quality evaluation.** Only the dossier
  demand-belief audit (§6). No full-company runs were repeated.
* **Product transfer.** None. No mechanism here is validated, and the
  dossier change waits on a forward test of v2.

# Build status

*Every capability in the unified world-model specification, tagged.*

Tags, as §2 defines them:

| tag | meaning |
|---|---|
| `LIVE_PROVEN` | it has run against real data and the output was inspected |
| `BUILT_NOT_LIVE_PROVEN` | complete and tested; no live run has exercised it |
| `PARTIAL` | some of the vertical exists; the gap is named |
| `RESEARCH_CANDIDATE` | designed as a hypothesis to be tested, not a capability |
| `PLANNED` | not built |
| `BLOCKED_DATA` | built, and the data it needs cannot be read here |
| `BLOCKED_INFRASTRUCTURE` | built, and blocked on a key, quota or deployment |

**The single most important line in this document:** `CALIBRATION_STATUS =
PRE_CALIBRATION` at **n = 0** real forward resolutions for the collective
layer. Nothing here carries an accuracy claim, and the code refuses to make
one.

---

## The collective-human layer (§§5–8, 13–14, 18, 21–22, 42, 49–50, 56)

| § | capability | module | status | note |
|---|---|---|---|---|
| 5 | `CollectiveStateEstimate` typed subsystem | `econ/collective.py` | **LIVE_PROVEN** | produced by the cycle producer against real BLS node shapes; three-cycle run inspected |
| 5 | rendering rule (no headcount sentences) | `collective.narrate` / `assert_renderable` | **LIVE_PROVEN** | the only supported renderer; break proof confirms removing it fails the suite |
| 6 | multi-scale populations | `collective.Population` | **PARTIAL** | machinery supports 8 scales; production estimates **one** (`US_households`) |
| 6 | `INDIVIDUAL` refused in public core | `collective.Population` | **LIVE_PROVEN** | raises; break proof confirms |
| 7 | frameworks as retirable hypotheses | `econ/construct.py` | **BUILT_NOT_LIVE_PROVEN** | `proposed_by` is recorded so a framework whose constructs all retire can itself be retired; no framework has yet been retired |
| 8 | latent dimension discovery | — | **PLANNED** | interpretable constructs only. Discovery would need a history this deployment cannot read |
| 9 | state-space / Kalman estimation | `econ/bayes.py` | **PARTIAL** | precision-weighted Bayesian updating with uncertainty; no dynamic transition model or filter |
| 10 | evidence-effect classification | `econ/bayes.py` | **LIVE_PROVEN** | three-cycle run: identical rows → `DUPLICATE_EVIDENCE`, 0 informative |
| 13 | psychology → company transmission | `econ/transmission*.py` | **BUILT_NOT_LIVE_PROVEN** | 3 chains + 10 per-company exposures, each naming its own channel; all at evidence level ≤1 |
| 14 | economy → psychology transmission | `econ/transmission_seed.py` | **BUILT_NOT_LIVE_PROVEN** | 2 chains. `bidirectional` asserted by test |
| 15 | reflexivity as separable chains | `econ/transmission_seed.py` | **BUILT_NOT_LIVE_PROVEN** | 2008 upswing and downswing are separate objects so confirming one cannot carry the other |
| 16–17 | causal-temporal graph + ladder | `econ/causal.py` | **LIVE_PROVEN** | pre-existing; extended with behavioural node ends |
| 18 | **incremental predictive value gate** | `econ/incremental.py` | **BUILT_NOT_LIVE_PROVEN** | proven in both directions on controlled data; **no real forward comparison has run** |
| 19–20 | historical episode programme | `econ/episodes.py` | **RESEARCH_CANDIDATE** | 9 episodes, 6 regimes, 1972–2023, train/validation/holdout fixed. **No episode has been executed** — it needs vintage history this deployment cannot read |
| 21–22 | causal bleeds | `econ/bleed.py` | **BUILT_NOT_LIVE_PROVEN** | detection, priority product, and PROMOTED-only corroboration all exercised in the loop demo |
| 42 | promotion / retirement pipeline | `econ/construct.py` | **LIVE_PROVEN** | closed-loop run retired `anger`, promoted `financial_anxiety`, and the register persisted across iterations |
| 49 | `/learning` collective panel | `econ/dashboard.py` + `webapp/app.py` | **LIVE_PROVEN** | rendered against a seeded store; reports its own emptiness with reasons |
| 50 | founder consumption | `econ/founder_view.py` | **LIVE_PROVEN** | five companies produced five different readings or an explicit refusal |
| 52 | Personal AI separation | `PRIVATE_SCALES` | **LIVE_PROVEN** | the public core cannot construct an individual state |
| 56 | out-of-sample delta reporting | `incremental.report` | **BUILT_NOT_LIVE_PROVEN** | reports base / augmented / delta / CI / n / FDR. Status is `NOT_YET_MEASURED` in production |

## The economic world model on the founder product path

*Added by the productization run. Every row here is about the ECONOMIC layer;
the collective-human layer above is unchanged and still `FROZEN_CANDIDATE`.*

| § | capability | module | status | note |
|---|---|---|---|---|
| 4 | `FounderEconomicContext` product contract | `econ/founder_contract.py` | **LIVE_PROVEN** | rendered on the deployed preview; brief and full carry byte-identical economic text for one run |
| 5 | seven failure states, none collapsing into a blank | `founder_contract.STATUSES` | **LIVE_PROVEN** | four of the seven observed live across ten companies |
| 6 | state → exposure → mechanism → decision field | `external_intel/econ_decision.py` | **LIVE_PROVEN** | the join runs on every deployed analysis |
| 8 | decision-damage wall before a surface | `founder_contract.admit` | **LIVE_PROVEN** | refusals are carried on the context and were observed live |
| 9 | company-specific transmission | `executive/company_profile` | **LIVE_PROVEN** | sign and mechanism keyed on (channel, business model); two model classes produce two different readings of one economy |
| 11 | ECONOMIC IMPACT section | `founder_brief/dossier._economic_impact` | **LIVE_PROVEN** | present on `/brief` and `/full`, deployed |
| 12 | provenance on every visible claim | `founder_contract.Provenance` | **LIVE_PROVEN** | source, observation, as_of, evidence class; the series that measured a labelled condition is named |
| 13 | forward status, `PRE_CALIBRATION` | `econ_decision.forward_status` | **LIVE_PROVEN** | "3 forward prediction(s) are open and none has come due" rendered live; no percentage anywhere |
| 14 | rehearsal isolation | contract + reader | **LIVE_PROVEN** | two independent barriers: the reader opens only the real ledger, and the contract refuses a REHEARSAL-sourced record |
| 16 | survives persistence and reload | rebuild from the append-only store | **LIVE_PROVEN** | the context is derived, not stored, so a redeploy reproduces it; asserted and observed |
| 17 | freshness, and a stale state that cannot speak | `founder_contract.freshness_of` | **LIVE_PROVEN** | the context recomputes its own freshness and refuses a producer that disagrees |
| 18 | a missing state leaves the analysis intact | `econ_decision.build` early returns | **LIVE_PROVEN** | ten of ten companies served a full analysis with no state published |
| 19/32 | multi-company matrix | `scripts/live_econ_matrix.py` | **LIVE_PROVEN** | ten companies across nine business-model classes, twice |
| 20 | offline semantic parity with the research arm | `scripts/run_product_parity.py` | **BUILT_NOT_LIVE_PROVEN** | 52/60 identical, 8 explained, 0 unexplained; it is an offline instrument by design |
| 21 | one canonical context across surfaces | per-request memo | **LIVE_PROVEN** | brief and full observed carrying the same sentences for one deployed run |
| 22 | CEO Q&A off the same object | `founder_brief/qa._economic_answer` | **LIVE_PROVEN** | answered live with the context's own provenance |
| 23 | information priority, named | `econ_decision._priorities` | **LIVE_PROVEN** | rendered live: "How much of … is already contracted, hedged or repriced" |
| 26 | product break proofs | `scripts/break_proofs_product.py` | **LIVE_PROVEN** | 16/16 caught, 0 tautologies, against the deployed code paths |
| 39 | operator learning surface | `webapp._econ_decision_block` | **LIVE_PROVEN** | observed on the preview: 13 conditions, 13 open predictions, 0 resolved, `PRE_CALIBRATION` and no percentage |
| 15 | economic History Rewind | — | **PARTIAL** | the history programme exists offline; no supported live case, and it is not blocking |
| — | Founder ← collective human state | `econ/founder_view.py` | **REFUSED** | zero of sixteen constructs promoted; the contract raises on any of them |

**What is NOT proven.** A material live DecisionDelta on a real company. The
seam runs end to end and the abstention and insufficient-evidence paths are
proven live; a company whose own filings establish an exposure to a condition
that is *currently* moving adversely, on a run that also produced a Baseline A,
did not occur in either matrix. That is a conjunction of three facts about the
world, not a gap in the wiring, and it is stated rather than manufactured.

---

## Deliberately not built this tranche

These are specification sections I did **not** deliver, recorded as decisions
rather than left to look like oversights.

| § | capability | status | why not |
|---|---|---|---|
| 8 | latent dimension discovery | **PLANNED** | factor models over a history this deployment cannot read would find structure in the fetch pattern, not the population |
| 23 | typed trajectory objects (`ActualTrajectory` / `ExpectedTrajectory` / `DesiredTrajectory` / `CounterfactualTrajectory`) | **PLANNED** | the *comparison* §23 exists for — expected against actual — is already performed by `bleed.detect`, which measures the gap between a chain's expected transmission and its observed one. What is missing is the typed object. Building it now would add a vertical with **no producer**, which §59 forbids and which this repository's own history names as its most repeated failure: a complete, tested subsystem that nothing imports is a document |
| 24 | three-way counterfactual labelling (`CAUSAL_ESTIMATE` / `STRUCTURAL_SIMULATION` / `SCENARIO_ASSUMPTION`) | **PARTIAL** | `market/counterfactual.py` and `market/synthetic_control.py` exist and `learning_store` carries a `causal_estimate` kind, but the three labels are not applied uniformly at the point of output. This is a real gap and a cheap one — the error it prevents (a scenario assumption read as a causal estimate) is exactly the class this codebase keeps hitting |
| 9 | dynamic state-space transition model | **PARTIAL** | `bayes.py` gives precision-weighted updating with uncertainty; a construct's posterior does not decay toward a prior between observations. With one measurable construct and no forward resolutions, a transition model would be fitted to nothing |

The common thread: each of these is machinery that cannot currently be fed.
The specification's own end condition is explicit that "classes created" and
"tests green" are not the bar, so the honest move was to stop adding verticals
without producers and say so here.

## Behavioural data acquisition (§4, §27)

| series | kind | status | reason |
|---|---|---|---|
| BLS JOLTS quits | `quits` | **LIVE_PROVEN** (adapter) / **BLOCKED_INFRASTRUCTURE** (live) | adapter verified against recorded response shape; the live call currently returns `REQUEST_NOT_PROCESSED` because the keyless BLS daily quota is already spent by the macro adapter |
| BLS labour participation | `labour_participation` | same | same |
| UMich sentiment, saving rate, delinquency, revolving credit, business formation, inflation expectation | 6 kinds | **BLOCKED_INFRASTRUCTURE** | routed through FRED; needs a key this deployment does not hold. Three endpoints were called directly to check: FRED's keyless `fredgraph.csv` did not answer within 12s, the Census BFS API returns *Missing Key*, and a guessed BFS bulk-CSV path 404s |
| trust barometers | `trust_index` | **BLOCKED_DATA** | proprietary and annual; an annual figure cannot support a quarterly-horizon comparison |
| search trends | `search_interest` | **BLOCKED_DATA** | licence forbids the redistribution; unauthenticated endpoints rate-limited to unusability |
| retail order flow | `retail_speculation` | **BLOCKED_DATA** | vendor product; the free proxies are derived from price, which would make it a market signal wearing a behavioural label |
| basket substitution | `trade_down` | **BLOCKED_DATA** | no public series measures it. Company disclosure of it enters as COMPANY evidence and therefore may not corroborate a consumer aggregate built from the same disclosures |
| public tone | `public_language` | **BLOCKED_DATA** | no licensed corpus; a tone index from whatever is scrapeable measures the scrape |

**Net: 1 of 16 constructs is measurable with data this deployment can read.**

## Pre-existing economic core (unchanged by this work)

`EconomicState`, `CompanyEconomicState`, causal graph and ladder, belief and
expectation ledgers, calibration, level-k participants, reflexivity, shocks,
VOI, lineage / double-counting wall, privacy firewall, execution realism,
zero-trade learning, learning acceleration, vintage replay, aggregates — all
**LIVE_PROVEN** by the three market cycles recorded in
`docs/econ/FINAL_REPORT.md`. This document does not re-litigate them.

`CompanyEconomicState` gained one field in this work:
`collective_exposures`, **BUILT_NOT_LIVE_PROVEN**.

## What would move the biggest numbers

1. **A FRED API key.** Six constructs move from BLOCKED_INFRASTRUCTURE to
   measurable, including `financial_anxiety` — the construct every
   transmission chain in the seed depends on. This is the single highest-value
   unblock in the system and it is an afternoon of work, not a research
   programme.
2. **A BLS registration key.** Removes the daily-quota collision with the
   macro adapter so the two LIVE series can actually be read every cycle.
3. **Vintage history.** Without it, §19–20's episode programme cannot execute
   and the gate cannot run on anything real — which is why every collective
   construct is `CANDIDATE` or `OBSERVED` and none is `PROMOTED` in
   production.

## Honest summary

The collective-human layer is **built, wired, guarded, and starved**. Every
vertical is complete from producer to persistence to consumer to UI to failure
semantics. The gate that decides whether any of it is worth keeping works in
both directions and has been shown to retire a construct. What has not
happened is a single real forward test, because the data to run one cannot be
read from this deployment.

That is a data problem, and this document exists so it is not mistaken for a
modelling result.

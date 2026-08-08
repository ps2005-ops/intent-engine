# Execution checkpoint — V3 continuous economic intelligence

Machine-readable continuation state. A completed slice is a checkpoint, not an
endpoint: this file exists so the mission survives a context boundary instead
of restarting from an audit.

Updated 2026-08-07, wave 4.

## Pinned state

| what | where |
|---|---|
| market head | `f85e490` (branch `feat/consumption-telemetry`) |
| market runtime | **`079128b` — NOT repinned; see "Owner action" below** |
| founder preview | `f0a0294` LIVE (branch `feat/consumption-emitter`) |
| production `main` | `119d345` — **untouched, do not target** |
| PAPER | structurally enforced in all three launchd plists (`MARKET_TRADING_MODE=PAPER`) |
| market suite | 4052 passed / 4 skipped / 10 deselected / EXIT=0 |
| founder suite | 4573 passed / 16 skipped / EXIT=0 |

### Owner action required

`git checkout f85e490` in `/Users/prathamsharma/intent-engine-market` was
refused by the permission classifier twice. The runtime therefore still runs
`079128b` and does NOT yet run the wave-4 work. The commit is already fetched
and the worktree is otherwise clean; one command completes it.

## Completed, waves 1–4

| # | slice | commit | evidence it is real |
|---|---|---|---|
| 1–15 | see git history through `079128b` | — | waves 1–3 |
| 16 | Knowledge decay + the four unwired views | `f1ea2a1` | 51 beliefs, 0 stale, every zero refused for a named reason |
| 17 | Economic chain, counterfactual memory, causal calibration | `0feb274` | honda chain 4 KNOWN / 3 UNKNOWN; 5 real episodes |
| 18 | Learning acceleration, quality-gated | `f567bdd` | DEGRADING on self_test_rate 0.8 |
| 19 | Counterparty source acquisition | `6af6f5c` | **25 relationships, 34 actors, 3 families, live** |
| 20 | Wave-4 break proofs | `f85e490` | **35/35**, each demonstrating RED |

## The pattern this mission keeps finding

**A correct module, a call site that never supplies its inputs, and a metric
honestly reporting zero that everyone reads as "nothing has happened yet."**

Six confirmed instances. Wave 4 found the sixth and it was four modules at
once: `belief_maturity`, `knowledge_decay`, `value_of_information` and
`causal_episodes` had all been built, tested and reported as shipped, and NO
operating cycle called any of them. `knowledge_step` now runs all seven
derived views, in both day and night lists.

**Before building a subsystem, check whether it already exists and is simply
not wired.** Six for six.

## SOURCE COVERAGE — closed as a diagnosis, open as an engineering target

### Settled, and `counterparty_sources.measure` REFUSES to re-run them

| family | volume | named counterparties |
|---|---|---|
| news headlines | 219 items | ~1 |
| 10-K / 10-Q | 3,959 sentences | 0 |
| 8-K + exhibits | 7,247 sentences | 0 |

### Measured live this wave, against the real 28-company universe

| family | docs | accepted | /doc | verdict | precision |
|---|---|---|---|---|---|
| `government_award` (USASpending) | 64 | 11 | 0.172 | INTEGRATE | ~100% |
| `customer_case_study` | 22 | 11 | 0.500 | INTEGRATE | ~91% |
| `partnership_release` | 59 | 3 | 0.051 | INTEGRATE | ~100% |

**25 accepted relationships, 34 distinct actors, 2 predicate types
(SELLS_TO 22, PARTNERS_WITH 3).**

Cost: government 16s; case studies 311s; releases 521s. Night-only,
cadence-gated 1 / 7 / 3 days. Scheduling, not removal.

### The two measurement traps, recorded so they are not re-entered

1. **Partnership releases first measured 0.048/doc and the honest conclusion
   would have been "family rejected".** It was wrong: the adapter was
   fetching newsroom INDEX pages averaging 700 characters. With the article
   hop it fetches real releases averaging 8,000. *Measure the retrieval
   before believing the yield.*
2. **Both prose families then measured INTEGRATE while their accepted rows
   contained fabrications** — "P&G SUPPLIES Chain" (from "supply chain"),
   customers called "How Cocunat" and "Shopify Case Studies". *A yield number
   that counts fabrications is worse than no number.* Precision ~40% → ~90%.

## What acquisition did NOT unblock, and why

Interactions are still **0**, now for a precise reason rather than an empty
graph. Every integrated family is COMPANY-PUBLISHED, and a company names its
customers and its partners and never its rivals. All 25 edges are `SELLS_TO`
or `PARTNERS_WITH`; `interaction_binding` needs `COMPETES_WITH`, and
`knowledge_step.world_model` reports that missing predicate by name.

**The next source must be one where a THIRD PARTY names both sides.** Untried
and promising: analyst and industry reports naming competitive sets,
antitrust and merger-review filings (which enumerate rivals by obligation),
and head-to-head comparison pages.

## Canonical measured facts

**NATURAL LEARNING** — canonical informative baseline **5 informative / 3
confirmed / 2 contradicted**. The old 10/8 number is invalid and must never
return.

**KNOWLEDGE DECAY** — 51 beliefs, 0 stale, 0 retired, and every zero is
refused for a named reason: 46 `WINDOW_OPEN`, 5 `TESTED`. Three cadences in
genuine use (120 × 23, 180 × 17, 365 × 11), read off each belief's own
`review_interval_days`; there is no module-level day count that governs any
belief. Next decay window **2026-12-03**. Aged 130 / 200 / 400 / 800 days the
same ledger yields 18 / 35 / 46 / 46 eligible, and the 5 tested beliefs never
decay at any age.

**BELIEF MATURITY** — 43 CANDIDATE / 6 SUPPORTED / 2 WEAKENING / 0 STALE.

**HIDDEN STATES** — 16 companies tracked, 54 observations, competing postures
preserved.

**ECONOMIC CHAIN** — `honda`, scored not chosen (27 observations, 18 from
filings, 1 resolved expectation). 4 of 7 stages KNOWN; MACRO_STATE,
CUSTOMER_STATE and ORDERS have nothing in the ledger at all. Weakest link
`ORDERS → COMPANY_DEMAND`. No link is ever OBSERVED and no constructor can
emit one. Honda's own filing supplies the competing explanation for its
margin move ("due mainly to the impact of EV-related losses…"), which raises
the alternative without promoting the link.

**COUNTERFACTUAL MEMORY** — 5 episodes, 3 strengthened, 2 weakened. Both
lessons are about the CLASSIFIER rather than the companies: a cost signal
sharing a sentence with a revenue signal must not open a demand belief
(cloudflare); price language must not reach a demand family (duolingo).

**CAUSAL CALIBRATION** — 2 UNMEASURABLE / 2 EMERGING / 0 above.
`ESTABLISHED` is absent from the vocabulary. The ladder is monotone in sample
size, after a first draft promoted `demand_strengthening` to
REPEATEDLY_SUPPORTED on three real tests.

**LEARNING ACCELERATION** — **DEGRADING**. 6 cycles ran the pipeline, 1 was
the backlog drain and is excluded from every rate, leaving 5. Only `recent`
(4 cycles) is computable; 7 / 14 / 30 report INSUFFICIENT_HISTORY with the
real count attached. Driven by `self_test_rate` 0.8 — four of five would-be
resolutions were the evidence that opened the belief.

**LLM MIGRATION** — `alternative_explanation.v1`. An LLM may PROPOSE; the
engine owns identity, storage, comparison, testing and retirement. A
PROPOSED row is never offered downstream, and `record_test` has no argument
that sets a standing directly.

**PERFORMANCE** — every derived view is sub-millisecond. The seven new ones
add ~1.1 ms to a cycle: decay 0.26, chain 0.31, acceleration 0.29,
counterfactual 0.12, causal calibration 0.05. The whole derived block is
5.71 ms, dominated by pre-existing `learning_health` at 3.76 ms. No
regression above 10% anywhere. The only expensive addition is source
acquisition, and it is scheduled rather than removed.

**LIVE (founder preview, `f0a0294`)**

| company | result |
|---|---|
| Shopify | full briefing; opening evidence is filing prose; the site's own meta description appears **0** times |
| Grifols | bounded/limited correctly — 4 usable sources vs 5 needed, 2 evidence kinds vs 3; names exactly what is missing |
| Brightledger | attempted live; brightledger.io returns HTTP errors on every path. The failure page names each source's specific failure, invents nothing, exposes the targeted retry, and contains no Connectors entity and no cross-company evidence |

## Remaining queue, highest value first

1. **A source where a THIRD PARTY names both sides** — the only route to
   `COMPETES_WITH`, and therefore to interactions and cross-actor
   expectations. Everything downstream of relationships is blocked on this
   one predicate.
2. **The self-test rate, 0.8** — the acceleration report's own verdict on the
   engine. Beliefs are opened and tested by evidence that arrives too close
   together.
3. **The two classifier lessons in counterfactual memory** are actionable
   fixes to `event_patterns` / `belief_formation`, not merely records.
4. **`CustomerNet`** — one residual case-study false positive (an ASML portal
   read as a customer). One of eleven.
5. Cross-actor expectations; the 30-cycle window; Founder consumption of the
   seven derived views.

## Standing rules

- Commit and push every completed slice. Own your worktree path.
- A break proof only counts if it demonstrates RED before restore. Two waves
  running, the most valuable finding came from a break proof FAILING while
  the suite was fully green.
- Never print a producer's probability as founder confidence. Every market
  belief carries the 0.586 prior a single evidence item opens one at.
- No causal edge is ever `OBSERVED`, and none is promoted by a single test.
- `UNMEASURABLE` is not zero. `INSUFFICIENT_HISTORY` is not zero. Absent
  telemetry and a measured zero are opposite findings.
- Before building a subsystem, check whether it already exists and is simply
  not wired. Six for six.
- Integrate a source family on measured yield, never on how promising it
  sounds — and check the retrieval before believing the yield.

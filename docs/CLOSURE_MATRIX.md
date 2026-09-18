# V3 closure matrix

*§68. One status per capability, with what proves it offline, what proves it
live, what is still limited, and what evidence would move it. No ambiguous
"done".*

Statuses: `LIVE_PROVEN` · `BUILT_NOT_LIVE_PROVEN` · `PARTIAL` ·
`PLANNED_RESEARCH_CANDIDATE` · `BLOCKED_DATA` · `BLOCKED_INFRASTRUCTURE` ·
`REFUSED`

---

| capability | status | offline proof | live proof | known limitation | next evidence needed |
|---|---|---|---|---|---|
| **EconomicState** | LIVE_PROVEN | 13 conditions published from a revision-aware panel; allowlist-validated | read on the deployed preview; `/learning-acceleration` renders it | 6 of 17 dimensions have no readable series here | series acquisition, and none of the six has a company consumer today |
| **CompanyEconomicState** (exposures) | LIVE_PROVEN | `econ.exposure` reads exposures from filings; refuses sector inference | exposures drive live abstention vs delta per company | exposure vocabulary maps 9 dimensions; 4 are measured here | wider panel coverage |
| **FounderEconomicContext** | LIVE_PROVEN | round-trip, three-state, stale, missing, human-state and rehearsal guards | rendered on `/brief` and `/full`, identical text | — | — |
| **DecisionDelta** | LIVE_PROVEN | 25/60 material, 25/25 attributable, frozen rubric | live material deltas on AMD, NVIDIA, Salesforce | a live delta needs three facts to hold at once | more companies whose filings name a condition currently moving |
| **DecisionDamage** | LIVE_PROVEN | 11 of 11 declared kinds have a detector; each attacked adversarially | detector runs on every live analysis; 0 damages | corpus check needs ≥3 analyses to fire | — |
| **Abstention** | LIVE_PROVEN | 35/60 offline; three states kept distinct through every layer | Visa, Starbucks, Deere, Comcast abstained live with distinct reasons | — | — |
| **CEO Q&A** | LIVE_PROVEN | answers lifted from the context, never composed | answered live with provenance | economic router covers six question shapes | — |
| **History Rewind (economic)** | PARTIAL | Caterpillar replayed across two regimes, counterfactuals labelled SCENARIO_ASSUMPTION | not a customer surface | needs vintage-safe outcomes to score reasoning quality | outcomes at the replayed horizons |
| **History Rewind (human state)** | REFUSED | — | — | zero promoted constructs | promotion, which the gate has never granted |
| **belief ledger** | BUILT_NOT_LIVE_PROVEN | append-only, revision-as-new-row | beliefs cross into the shared state and reach the founder contract | no belief has moved in a live cycle | genuinely new evidence |
| **expectation ledger** | LIVE_PROVEN | eight lifecycle facts on the real file | 13 open predictions render on the operator surface | — | — |
| **resolution engine** | BUILT_NOT_LIVE_PROVEN | rehearsal exercised the resolver, state machine and scorer | nothing is due, so nothing has resolved live | correct: no real expectation reaches its horizon before 2026-12 | time |
| **calibration** | BLOCKED_DATA | machinery proven on rehearsal, isolated from real | `PRE_CALIBRATION` rendered, no percentage anywhere | 0 resolved of 13 | the horizons arriving |
| **relation learning** | LIVE_PROVEN | 6 relations, full lifecycle, lag-aware | evaluated each cycle; ledger records next eligible date | 1 SUPPORTED, 5 CANDIDATE because their drivers did not move | driver movement |
| **causal bleed** | BUILT_NOT_LIVE_PROVEN | detection and PROMOTED-only corroboration exercised | not a customer surface | — | — |
| **information priority** | LIVE_PROVEN | named per company from its own channel | rendered live: "How much of … is already contracted, hedged or repriced" | acquisition loop not wired to act on it | a targeted retrieval path |
| **learning acceleration** | LIVE_PROVEN | derived ledgers, reconciliation refuses a divergence | `/learning-acceleration` + the economic panel render live | — | — |
| **stagnation detection** | BUILT_NOT_LIVE_PROVEN | detector exists and has fired on a real gap | not rendered as an alert surface | — | — |
| **company → economy bridge** | BUILT_NOT_LIVE_PROVEN | translation refuses private and directionless evidence, reports what it declined | exposures published on every live run | aggregates need a company panel | more companies analysed |
| **CollectiveHumanState** | REFUSED | 16 constructs, 6 measurable, 0 promoted | contract raises on any of them | frozen by its own gate | out-of-sample incremental value in two regimes |
| **paper market learning** | BUILT_NOT_LIVE_PROVEN | zero-trade learning captured | paper/shadow only | no real-money execution, by design | — |

---

## What "LIVE_PROVEN" required

The deployed SHA contains the capability, real HTTP requests execute it, and
the rendered output exposes it. Tests passing is not that, and neither is a
successful push.

## The three legitimate blockers

1. **Time.** 13 preregistered predictions, none due before 2026-12.
   `PRE_CALIBRATION` holds until they resolve.
2. **Promotion.** The collective-human register is frozen by its own gate. It
   reopens on out-of-sample incremental value, which no construct has shown.
3. **Data.** Six economic dimensions have no readable series here, and none
   of them has a company consumer today — so unblocking any would currently
   buy nothing.

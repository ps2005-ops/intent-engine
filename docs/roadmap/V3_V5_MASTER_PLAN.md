# Master plan: where the world model is, and what comes next

*Supersedes nothing. This is the roadmap view of the unified world model,
including the collective-human layer added in the V6 unification.*

---

## Lineage

| version | what it established | where |
|---|---|---|
| V3 | founder and market as two products with two ledgers | `v3-final/*` branches |
| V4 | the execution OS: planner state as files, frontier selection | `docs/execution/v4/` |
| V5 | the execution graph; a node must name what it would change | `docs/execution/v5/` |
| **V6** | **one repository, one world model, both products crossing into a neutral third package** | `v6/unified` |

V6 is the unification. `intent_engine.econ` is the neutral substrate; the
founder→market import wall is intact and re-asserted by a parsing test,
because unification is exactly the change that would have broken it.

## What V6 delivered

**First tranche** (commit `fe89ab7`) — the economic core: 24 modules, the
canonical `EconomicState` and `CompanyEconomicState`, causal ladder, belief
and expectation ledgers, calibration, lineage, execution realism, zero-trade
learning, learning acceleration, vintage replay. Wired into both market cycles,
the founder analysis path and `/learning`. Three live cycles inspected. Six
defects found by running it.

**Second tranche** (this work) — the collective-human layer as a first-class
typed subsystem: 9 modules, the incremental-value gate, the construct
lifecycle with real retirement, two-way transmission, causal bleeds, the
historical episode partition, the dashboard and the founder gate. One live
behavioural adapter.

## The current binding constraint

**Data acquisition.** One of sixteen constructs is measurable with what this
deployment can read.

This is worth stating precisely because it is easy to mistake for a modelling
result. The architecture is complete: producer, persistence, reload, consumer,
UI, failure semantics, tests, break proofs. The gate works in both directions
and has been shown to retire a construct. What has not happened is a single
real forward comparison, because the series needed to run one are behind a
FRED key, a vendor licence, or do not exist publicly.

## Next, in order of value

### 1. A FRED API key — hours, not weeks

Moves six constructs from `BLOCKED_INFRASTRUCTURE` to measurable, including
**`financial_anxiety`**, which every transmission chain in the seed depends on.
Also unblocks `delinquency`, the discriminating instrument without which
`financial_anxiety` rests on contested proxies alone.

This is the single highest-value action in the entire system right now, and it
is not a research programme.

### 2. A BLS registration key

Removes the daily-quota collision with the macro adapter, so the two genuinely
LIVE behavioural series can be read every cycle rather than losing a race.

### 3. Run one episode end to end

`covid_recovery` (VALIDATION), testing `perceived_control` against the 2021
quits surge. It is the only construct currently measurable and the episode was
placed in VALIDATION specifically so that testing it does not consume the
holdout.

This produces the first real number for
`COLLECTIVE_STATE_BASELINE_SCORE` / `ECONOMIC_PLUS_COLLECTIVE_SCORE` /
`INCREMENTAL_DELTA`, and it is the first thing that could legitimately promote
or retire a construct.

### 4. The market engine's own exposure path

The market cycle still reads headlines through its ledger-shaped exposure
reader. The shared exposure capability is used by the founder path, not yet by
that one. Carried from the previous tranche; still the highest-value repair on
the economic side, and still small.

### 5. Second population

Everything supports cohorts and production estimates one (`US_households`).
`US_executives` is the natural second — it is the population `CAT` and `NET`'s
declared exposures actually depend on, and today they get nothing because the
only population estimated is households.

### 6. Raise a transmission edge above level 1

No chain currently claims causation; all read "ASSOCIATED WITH". Raising one
to level 3 requires a stated structural restriction, and to level 4 an
identified event. The 2023 regional-bank episode is the best candidate — a
sharp, dated, plausibly exogenous shock to institutional trust.

Note the lag problem first: `institutional_trust` has a 90-day typical lag and
that episode is a three-day bank run. The lag model has to be fixed before the
episode can test anything.

## What is deliberately not next

- **Latent dimension discovery (§8).** Factor models over a history this
  deployment cannot read would find structure in the fetch pattern, not the
  population.
- **Real capital (§61).** Paper only. The market system needs a mature forward
  record, calibration, execution validation and governance first, and that is
  a separately authorised phase.
- **More constructs.** Eight of sixteen already have no proxy. Adding a
  seventeenth before measuring the first would be building the part that is
  cheap.

## The standing invariants

These do not change between versions:

- founder ⇄ market import wall, enforced by parsing
- public ⇄ tenant-private, enforced by refusal not filtering
- no individual state in the public core
- no causal language below evidence level 3
- no accuracy claim before the declared forward sample
- no construct informs a decision before it beats the base economic model
- paper only

# Unified economic intelligence architecture — what was built, and what it measured

**Branch** `v6/unified` · **Stage** PAPER ONLY, no live capital · **Runtime** `/Users/prathamsharma/ie-econ-runtime`

---

## 1. The defect, stated precisely

This repository held two intelligence products that had been diverging for
202 and 371 commits from a common ancestor:

| | asks | lives in |
|---|---|---|
| **Company / founder intelligence** | what is happening inside and around this company, and what should management do | `founder_brief`, `external_intel`, `strategic_intelligence`, `demo_dossier` |
| **Market learning** | which economic mechanisms are changing, what should happen next, did our expectations resolve | `market`, `predictions`, `paper`, `learning` |

They did not lack a connection. They lacked a **substrate**.

The canonical object already existed. `market.macro_state` holds a dated,
revision-aware, three-times-per-fact reading of the economy;
`market.transmission` already conditions it on a specific company;
`market.company_exposure` already refuses to infer an exposure from a sector.
All of it was correct. All of it lived inside `intent_engine.market`, which
founder code may not import — and **must** not, because "trading internals
cannot reach a founder's screen" is a property of the import graph rather
than a promise about what people remember.

So the better economic picture was **structurally unreachable** from the
surface that needed it, and every company analysis re-derived a worse one
from whatever documents that company happened to publish.

## 2. What was built

`intent_engine.econ` — a **neutral** package. It imports neither product.
`tests/test_econ_core_is_neutral.py` parses every module in it and fails on
the import edge, and separately re-asserts that the founder packages still
cannot import the market engine. Unification did not weaken that wall; it
added a third package that both sides may cross into.

```
                    intent_engine.econ  (neutral core)
                              ▲                ▲
              publishes into  │                │  reads from
                              │                │
                 intent_engine.market   external_intel / founder
                 (may not be imported by ──X── the founder side, still)
```

| module | what it is |
|---|---|
| `vocabulary` | the words both sides must agree on; closed node-kind set |
| `evidence` | one dated, sourced fact, with visibility and lineage |
| `lineage` | the double-counting wall |
| `causal` + `seed` | directed mechanisms carrying an evidence ladder L0–L5 |
| `shock` | propagation with compounding confidence and order-of-effect |
| `belief` | beliefs and preregistered expectations, append-only |
| `attacks` | shared belief-attack / impossible-hypothesis engine |
| `levelk` | participant classes and their level-k responses |
| `reflexivity` | belief → positioning → price → forced flow → belief |
| `execution` | paper and shadow fills with friction; live refuses |
| `calibration` | `PRE_CALIBRATION` until 30 resolved forward predictions |
| `zero_trade` | learning from what was declined and what was never seen |
| `voi` / `replay` | what to find out next; vintage-correct four-way replay |
| `promotion` | candidate → knowledge, with six overfitting defences |
| `acceleration` | is it learning faster, **and** is it learning as well |
| `exposure` | what a company's own words say it depends on |
| `state` / `company` | `EconomicState`, `CompanyEconomicState` |
| `series` / `store` | cross-asset universe with availability; append-only store |

## 3. Wired, not merely built

A module nothing calls is inert, and this repository has shipped inert
repairs before.

- **market cycle** — `econ_publish` and `econ_aggregate` in **both** the day
  and night step lists, after `knowledge` so the beliefs published are the
  ones that cycle produced.
- **founder run** — `_external_context` reads the shared state and publishes
  this company's public evidence back into it, in the same pass.
- **`/learning`** — answers Section 28's eleven questions from the core, with
  an unanswerable question rendering its absence and reason rather than
  disappearing from the list.
- **cycle report** — a `SHARED ECONOMIC CORE` section. Both steps ran green
  and **invisible** for a full cycle before this, because the report reads
  named keys and nobody added them.

## 4. What the live runs found

### 4.1 The bridge read fields production does not write

The first live cycle reported *"151 beliefs refused — they state no
observable."* They state one. `StrategicBelief` has no `mechanism`, no
`falsifier`, no `expected_observations` and no `probability`; its probability
is `posterior_probability` and the rest live on the **expectation** record,
joined on `hypothesis_id` — **151 of 151 join** — whose `metric` names the
causal family that states the mechanism.

Fixed. **51 of 151** now cross. The other 100 are refused **by family**:
twelve causal families receive evidence and carry no recorded mechanism.
That is a work list, not a wall.

### 4.2 The exposure layer was starved, not broken

`company_exposure` rates **4** exposures across 28 companies and 562 evidence
rows. Its corpus is news headlines with a median length of **95 characters**;
its patterns require a sentence in which the company is the *subject* of a
dependency — "our results are sensitive to fuel prices" — a construction
headlines never contain.

Measured across six control companies, same patterns, same companies:

| corpus | volume | exposures |
|---|---|---|
| market ledger (headlines) | 131 rows, 19,415 chars | **1** |
| founder path (filings) | 46 documents, 3,564,390 chars | **39** |

**184× the text, 39× the exposures.** The capability moved into the shared
core; the founder path extracts at translation time, where the whole document
is still in hand.

### 4.3 Two dead branches inside those patterns

Found by running them over real filings rather than fixtures:

- `\b(\d+\s*%|percent|majority)\b` **could never match a percentage.** The
  alternative ends on `%`, a non-word character, and the trailing `\b` then
  demands a word character — `" of revenue"` is not one. Only the spelled-out
  forms ever rated, and the numeric form is what filings use.
- `capital expenditure` did not match **`capital expenditures`**, the plural
  every filing uses.

Both fixed in both copies, with a test asserting the copies never drift.

### 4.4 The flywheel runs, and the wall holds

Six companies retrieved live → **71 economic nodes** across 5 companies →
three sufficient candidate indicators:

| index | direction | score | panel | largest contributor |
|---|---|---|---|---|
| `capex_intention_index` | UP | 0.60 | 5 | 0.20 |
| `financing_conditions_index` | DOWN | −0.20 | 5 | 0.20 |
| `pricing_pressure_index` | UP | 0.20 | 5 | 0.20 |

All three are **refused** as corroboration of their own inputs by
`lineage.independent`. None is tradable, and no code path makes one so.

## 5. What is deliberately refused

- **Demo search queries as a signal.** There is no function in the bridge
  that takes a query, a session, a visitor, or a count of any of them, and a
  test asserts the absence.
- **Live capital.** `LiveBrokerAdapter.__init__` raises. Enabling it requires
  an authorisation object that does not exist in this repository, so the
  change would be a visible addition rather than a flag flip.
- **Causal language below evidence level 3.** `statement()` constructs a
  different sentence; there is no argument that produces "causes" from a
  level-2 edge.
- **An accuracy figure before 30 resolved forward predictions.** Status is
  `PRE_CALIBRATION` and the headline names the shortfall.
- **Tenant-private evidence in any public aggregate** — a refusal, never a
  filter, because a quietly-smaller aggregate is a breach that also lies
  about its own sample.

## 6. The three layers a shock is reported through

A shock alone invites the error the third layer exists to prevent —
re-estimating a mechanism from a move that was mostly forced flow. Evaluated
against the seed graph on 2026-08-27:

| shock | effects reached | mandates responding | net L1 flow | forced-flow share |
|---|---|---|---|---|
| +100bp high-yield spread | 1 | 2 | SELL | material |
| +10% trade-weighted dollar | 1 | 0 | HOLD | negligible |
| funding stress event | 4 | 1 | HOLD | negligible |
| −20% crude oil | 2 | 0 | HOLD | negligible |
| +50bp real yield | 2 | 1 | SELL | negligible |
| volatility spike | 1 | 3 | SELL | material |

Where the forced-flow share reaches *comparable* or *dominant*, the shock
carries an explicit `learning_warning`: **this move may not be used to
re-estimate the mechanism's magnitude.** Dealer gamma is never guessed — its
sign is unavailable to this deployment, and an unknown gamma leaves the
short-gamma loop *not armed* rather than assumed.

## 7. What is honestly incomplete

- **`market.company_exposure` still reads headlines in its own cycle path.**
  The capability now lives in the shared core and the founder path uses it on
  full documents, but the market side's ledger-shaped reader is unchanged and
  will keep rating ~4 exposures until it consumes the core's company nodes.
- **Twelve causal families carry no recorded mechanism**, so 100 of 151
  beliefs cannot cross into the shared ledger. Each family is named in the
  cycle report.
- **No forward expectation has been written to the shared core yet**, so
  calibration is `PRE_CALIBRATION` at n=0 and will stay there until the
  belief→expectation producer writes into `econ`, not only into the market
  ledger.
- **`series` declares 6 KEYED and 6 UNAVAILABLE quantities** — including OIS,
  cross-currency basis, the VIX complex and dealer gamma. Each carries the
  reason; none is synthesised.

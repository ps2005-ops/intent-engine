# INTENT ENGINE — UNIFIED ECONOMIC INTELLIGENCE ARCHITECTURE
## Final report

**Branch** `v6/unified` · **Baseline** `bfe3b75` · **Stage** PAPER ONLY
**Runtime** `/Users/prathamsharma/ie-econ-runtime` · **Worktree** `/Users/prathamsharma/intent-engine-econ`

---

## The reported fields

| field | value |
|---|---|
| `CANONICAL_ECONOMIC_CORE` | **BUILT AND CONSUMED BY BOTH.** `intent_engine.econ`, 24 modules, neutral — imports neither product. Both sides' import edges into it are asserted; the founder→market wall is re-asserted and intact. |
| `CROSS_ASSET_GRAPH` | **40 series declared**, availability stated rather than assumed: 20 LIVE, 8 DERIVABLE, 6 KEYED, 6 UNAVAILABLE. No series is silently synthesised; a derived series carries its rule and its inputs. |
| `CAUSAL_EVIDENCE_LEVELS` | **L0–L5 on every edge.** Seed graph: 16 edges, 20 quantities — 12 at L1, 1 at L2, 3 at L3. 3 may state causation, 13 are association-only. `statement()` constructs a different sentence below L3; there is no override. |
| `BELIEF_LEDGER` | **Append-only, preregistered.** Identity, proposition, mechanism, falsifier and creation time are immutable; probability moves through recorded revisions. `information_cutoff ≤ created_at` is enforced at construction. Five outcomes including VOID. |
| `IMPOSSIBLE_HYPOTHESIS` | **Shared engine, 5 kinds × 10 categories.** Six required fields or refusal. No template exists: an unfilled slot is reported, never filled, because a template attack is indistinguishable downstream from a real one. |
| `MARKET_LEVEL_K` | **10 participant classes, L0/L1/L2.** Every reaction names the public mandate clause it follows. L2 requires a *named* counterparty. QRE provided and deliberately unused — no rationality parameter has been measured. |
| `EXECUTION_REALISM` | **Almgren–Chriss temporary + permanent impact, spread, fees.** Costs always move price against the order. Participation cap refuses impossible fills. VPIN implemented as a labelled proxy, `ground_truth = False`, `value = None` below its bucket minimum. |
| `ZERO_TRADE_LEARNING` | **Two shapes, seven verdicts.** REJECTED (was the decline correct?) and ABSENT (what evidence was missing, and was it obtainable?). `STRUCTURALLY_INVISIBLE` must state that the evidence was unobtainable — a coverage gap is a source problem, never a threshold to lower. |
| `LEARNING_ACCELERATION` | **Velocity paired with quality in every window.** Rising ingestion with flat belief movement reports PLATEAUING, not ACCELERATING. `INSUFFICIENT_HISTORY` names the shortfall rather than reporting STABLE. |
| `COMPANY_TO_MARKET_BRIDGE` | **LIVE.** 8 declared indices from public corporate evidence. Demo queries, sessions and visitor counts cannot reach an economic node — asserted structurally, by parameter name. |
| `MARKET_TO_COMPANY_BRIDGE` | **LIVE.** The founder reasoning layer receives an `ECONOMY` block carrying real published figures with evidence-node ids. A company with no evidenced exposure gets **no section at all**. |
| `PRIVATE_DATA_ISOLATION` | **Enforced by refusal, not filter.** A tenant-private node reaching an aggregate raises; a company state holding private evidence without a tenant raises; serialisation withholds by default and reports the count withheld. |
| `DOUBLE_COUNTING_WALL` | **Enforced and proven live.** All three sufficient indices are refused as corroboration of their own inputs. Two indices over overlapping panels are one witness. One publisher saying something twice is one source. |
| `REPLAY_VINTAGE_INTEGRITY` | **`available_at` only.** Revisions return the *vintage*, not the latest value. Four-way verdict; `RIGHT_FOR_WRONG_REASON` may not update a belief. |
| `PAPER_PORTFOLIO` | **PAPER, broker `None`, orders submitted 0, open positions 0.** No signal fired; the report states the reason rather than a zero. |
| `REAL_FORWARD_RESOLUTIONS` | **0 in the shared core.** |
| `CALIBRATION_STATUS` | **`PRE_CALIBRATION`** — 0 of the 30 required. No accuracy, win rate, Brier or Sharpe is reported anywhere, and `assert_no_unsupported_claim` refuses prose that implies one. |

---

## What the live runs found

### 1. The bridge read fields production does not write
The first live cycle announced *"151 beliefs refused — they state no observable."* **They state one.** A belief's falsifier and expected observation live on the expectation record, joined on `hypothesis_id` — **151 of 151 join** — and that expectation's `metric` names the causal family that states the mechanism.

Corrected: **51 of 151 cross**. The other 100 are refused *by named family* — twelve families receive evidence and carry no recorded mechanism. That is a work list, not a wall.

### 2. The exposure layer was starved, not broken
`company_exposure` rates **4** exposures across 28 companies and 562 evidence rows. Its corpus is news headlines, median **95 characters**. Its patterns need a sentence in which the company is the subject of a dependency — which a headline never contains.

| corpus | volume | exposures |
|---|---|---|
| market ledger (headlines) | 131 rows, 19,415 chars | **1** |
| founder path (filings) | 46 documents, 3,564,390 chars | **39** |

**184× the text, 39× the exposures — same patterns, same companies.** The capability moved into the shared core.

### 3. Two dead branches inside those patterns
- `\b(\d+\s*%|percent|majority)\b` **could never match a percentage**: the alternative ends on `%`, and the trailing `\b` then demands a word character — `" of revenue"` is not one.
- `capital expenditure` never matched the plural **`capital expenditures`** that filings actually use.

Both fixed in both copies, with a test that fails if the copies drift.

### 4. Direction was the sign of a level
All five published conditions read `UP`, including a consumer price index of 333.918 — a number greater than zero in every month that has ever existed. **Uniformity across every condition is the instrument tell**: a real economy does not move one way in five out of five.

The change was computable the whole time — 23–46 dated observations per condition were already in the graph. Measured before and after, on the same nodes:

| condition | value | prior | before | after |
|---|---|---|---|---|
| fiscal | 41.951 | 42.938 | UP | **DOWN** |
| inflation | 333.918 | 333.952 | UP | **DOWN** |
| labour | 4.1 | 4.2 | UP | **DOWN** |
| treasury_10y | 3.283 | 3.248 | UP | UP |
| wages | 37.62 | 37.60 | UP | UP |

Direction is now computed against the previous observation of the *same*
quantity, two prints of one period are treated as a revision rather than a
movement, and `NO_PRIOR` is a distinct value from `FLAT` — because "we cannot
tell whether it moved" and "it did not move" support different decisions, and
collapsing them makes an unmeasured economy read as a calm one. A reading that
claims a direction must carry the prior it was computed from, or construction
raises.

### 5. Two steps ran green and invisible
`econ_publish` and `econ_aggregate` completed successfully for a full cycle and appeared in neither the markdown nor the JSON, because the report reads named keys and nobody added them.

---

## What is deliberately refused

- **Demo search queries as a trading signal** — no function takes a query, session, visitor or count of any; asserted by parameter name.
- **Live capital** — `LiveBrokerAdapter.__init__` raises. Enabling it needs an authorisation object that does not exist in this repository, so the change is a visible addition, not a flag flip.
- **Causal language below L3** — a different sentence is constructed; no argument produces "causes" from a level-2 edge.
- **An accuracy figure before 30 resolved forward predictions.**
- **Tenant-private evidence in any public aggregate** — a refusal, never a filter.

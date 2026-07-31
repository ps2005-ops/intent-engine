# Operating log

One entry per operating day. The engine is now **operated**, not designed. The
burden of proof has moved onto changing the framework.

---

## 2026-07-30 — Day 1

### Mission

> Continuously discover, test and retire alpha hypotheses that outperform the
> measured baseline (0.500) under honest walk-forward evaluation, while
> maintaining Decision Quality and avoiding lookahead bias.

### 1–5 · What the engine did

| | |
|---|---|
| Companies evaluated | **16** (real websites, live network) |
| Opportunities evaluated | 16 |
| BUY / SELL / HOLD / WATCH / NO_TRADE | 0 / 0 / 0 / **2** / **14** |
| Paper trades opened | **0** |
| Refusals | **16 (100%)** |

Zero paper trades is the correct outcome, not a failure: no company cleared
the evidence gates, and the mission is explicit that trade count is never what
is optimised. Every refusal is recorded with its reason.

Gate distribution: `view_withheld` 7 · `no_strategic_reading` 6 ·
`no_outside_source` 2 · `not_tradable` 1.

### 6–7 · Decision and Outcome Quality

| metric | value | n | confidence |
|---|---|---|---|
| Refusal justification rate | 1.000 | 16 | medium |
| Unjustified refusals | 0 | 16 | medium |
| Position accuracy (live path) | — | 0 | **unmeasurable** |
| Position accuracy (replay, baseline) | **0.500** | 66 | high |

### 8 · Hypothesis revisions

66 recorded on `momentum_persists.v1` — 33 supported, 33 refuted. Confidence
0.55 → 0.55.

### 9 · Learning Value

Unscored, correctly. `information_gain` and `calibration_impact` remain
`UNMEASURABLE`. Novelty-weighted resolvable decisions on the live path: **0**.

### 10 · Coverage

11 sectors · 4 market caps · 4 regions · sector concentration 0.31.
Gaps: Communication Services, micro-cap.

### 11 · Calibration

n=66 for `baseline_momentum.v1` on replay — past `A-M5`'s threshold **for that
signal on that replay only**. The engine's full path has 0 resolved decisions,
so no accuracy claim is made about the engine.

### 12 · Signal bake-off — the day's real work

Pre-registered before any result was seen. **All results reported.**

| signal | n | declined | accuracy | 2σ band | verdict |
|---|---|---|---|---|---|
| `momentum_persists.v1` (baseline) | 66 | 18 | 0.5000 | ±0.123 | indistinguishable from 0.500 |
| `mean_reversion.v1` | 66 | 18 | 0.5000 | ±0.123 | indistinguishable from 0.500 |
| `strong_trend.v1` | 34 | 50 | 0.4706 | ±0.171 | indistinguishable from 0.500 |
| `calm_trend.v1` | 24 | 60 | 0.5000 | ±0.204 | indistinguishable from 0.500 |

**No signal beats the baseline.** Nothing found today.

`mean_reversion.v1` returning exactly 0.500 is the harness passing its own
correctness check: it is the exact negation of the baseline, so on the same
66 decisions it must score 66 − 33 = 33. It does. A directional bug would
have shown here.

Multiple-comparisons discipline was stated in advance: with n≈66 the standard
error near 0.5 is ~0.06, so a 2σ result needs ~0.62 or ~0.38. Everything above
sits inside that band, so **ranking them is meaningless** and picking the
"best" would be manufacturing alpha that does not exist.

### 13 · Engineering prediction accuracy

No engineering prediction was made — no framework change was proposed. Running
total: 6 cycles predicted, 4 wrong bottleneck, 1 wrong scope, 1 correct.

### 14 · Bottleneck half-life

Two closed bottlenecks, both <1 day, both self-inflicted. Neither counts as
evidence of a fast loop. No bottleneck was closed today.

### 15 · Top three proposed improvements

1. **Signals with a mechanism, not a price transform.** All four candidates are
   functions of the same price series, which is why they agree. An earnings
   surprise, a guidance change or a filing event is a genuinely different input
   and the only kind likely to depart from 0.500.
2. **Strategic-reading yield** — `view_withheld` 7/16 remains the gate on the
   live path.
3. **JS-rendered retrieval** — 6/16 produce no evidence.

None of these blocks tomorrow's operation.

### 16 · Recommendation

**CONTINUE OPERATING.**

Nothing prevented today's cycle. The engine ran end to end on real companies,
made real decisions, resolved 66 predictions against real prices and produced
an honest negative result. Engineering spend today: one script, no framework
change — well inside the 20% budget.

**Framework stability: 3** consecutive cycles without core framework
modification.

### What today actually established

The bar is real and nothing clears it. Three candidate signals were proposed,
tested against the baseline with identical methodology, and **all three
retired the same day** — which is what "continuously discover, test and retire"
looks like when the honest answer is no.

A day that finds nothing and proves it found nothing is a successful operating
day. The failure mode would have been reporting `strong_trend.v1` at 0.4706 as
"promising, needs more data".

---

## 2026-07-30 — Day 2 · a different information source

Instruction: stop generating price-transform variants; test genuinely
different information, point-in-time only, and mark anything without
point-in-time evidence **UNTESTABLE** rather than approximating it.

### Hypotheses proposed: 5 · testable: 2 · rejected for unavailable point-in-time data: 3

Full pre-registration with all ten required fields, written before any test:
[`PREREGISTRATION_2026-07-30_day2.md`](PREREGISTRATION_2026-07-30_day2.md).

**Testable** — SEC EDGAR filing dates are point-in-time *by construction*: the
date a document became public is the date it became usable.

- `event_drift.v1` — material-event filings (8-K, 6-K)
- `report_drift.v1` — periodic reports (10-Q, 10-K, 20-F, 40-F)

**Rejected — no point-in-time data**

| hypothesis | why rejected |
|---|---|
| **Earnings surprise** | Requires consensus estimates *as they stood before the announcement*. Yahoo's `earningsHistory` and `earnings` modules both return **HTTP 401**; no keyless historical consensus source exists here. Inferring "surprise" from price reaction would define the surprise by the outcome it is meant to predict — circular. |
| **Guidance change** | Filing text *is* point-in-time and reachable, so this is not a data problem. It is an extraction problem: detecting "guidance raised / lowered / withdrawn" from raw prose is a real NLP task, and a keyword rule would manufacture a signal out of its own error rate. Blocker named precisely so it can be revisited. |
| **Market-vs-evidence disagreement** | The most tempting hypothesis available and the worst lookahead risk. Company evidence comes from **live websites showing today's content**. Using it for a decision dated months ago injects information that did not exist — an edge that would be both invisible and entirely false. Untestable until archived point-in-time snapshots exist. |

### Signal results against the 0.500 baseline

| signal | accuracy | n | naive 2σ | **cluster-corrected 2σ** | verdict |
|---|---|---|---|---|---|
| `momentum_persists.v1` (baseline) | 0.5000 | 66 | ±0.123 | — | baseline |
| `event_drift.v1` | 0.4759 | 290 | [0.441, 0.559] | [0.242, 0.758] | indistinguishable |
| `report_drift.v1` | 0.3594 | 64 | **[0.375, 0.625] → "distinguishable"** | [0.242, 0.758] | **indistinguishable** |

By form: 8-K 0.505 (n=184) · 6-K 0.425 (n=106) · 10-Q 0.325 (n=40) ·
10-K 0.389 (n=18) · 20-F 0.500 (n=6).

### The result that had to be thrown away

`report_drift.v1` at 0.359 initially scored **DISTINGUISHABLE** — the first
apparent departure from 0.500 in the project. It is not real.

Filings cluster in earnings season: **64 report-filings fall in only 15
distinct months**, and every filing within a month shares one market window.
Monthly accuracy swings 0.00 → 1.00 depending on what that month's market did.
Treating 64 correlated observations as 64 independent draws overstates
precision by roughly √(64/15) ≈ 2×, which is exactly the width that
manufactured the result.

Checked and cleared as *not* the explanation: direction balance is 45% up /
55% down, and 47% of 21-day moves were up with a mean of +0.89% — so this is
not simple market drift acting on one-sided signals. The confound is
clustering, not drift.

Corrected for clustering, **neither signal is distinguishable from 0.500.**

### Live decisions and refusals

| | |
|---|---|
| Companies evaluated | 16 (live network) |
| BUY / SELL / HOLD / WATCH / NO_TRADE | 0 / 0 / 0 / 2 / 14 |
| **Paper trades opened** | **0** |
| Refusals | 16 (100%), all justified |
| Evidence produced | 9/16 (56%) — down from 10/16 yesterday |
| Strategic-reading yield | 3/16 (19%) — unchanged |
| Independent source | 0/16 — unchanged |

Gates: `no_strategic_reading` 7 · `view_withheld` 6 · `no_outside_source` 2 ·
`not_tradable` 1. No trades were forced; no gate was relaxed.

### Next measured bottleneck

**Effective sample size, not row count.** Both days now show the same wall: n
looks adequate and n_eff is ~15 independent market windows. More filings from
the same 14 companies over the same 13 months will not fix it — they are the
same windows resampled.

Two ways out, in order of measured leverage:
1. **A longer price history.** 400 days is the current fetch; 5+ years of
   filings would multiply independent windows directly.
2. **More companies**, which adds cross-sectional breadth but *not* new market
   windows — so it is the weaker of the two, which is the opposite of the
   intuition and the reason to measure before building.

### A leakage bug in our own adapter, caught the same day

The pre-commit suite blocked this commit on
`test_no_evidence_is_dated_after_the_run`. Not flaky — a real defect in the
evidence adapter written in cycle 1.

The strategic layer dates an otherwise-undated observation to the **retrieval
time**. When `as_of` is today those agree and nothing is wrong. When `as_of` is
in the past — *every historical replay, which is the only way this engine can
be evaluated* — the observation is dated **after** the decision it feeds.
Reproduced exactly: `as_of=2026-07-30` emitted evidence dated `2026-07-31`.

Fixed by **dropping**, not clamping. Moving the date back to `as_of` would
assert the evidence existed then, which is precisely what is unknown — a
dropped row is a visible gap, a clamped one is an invisible fabrication.

The fix then failed three existing tests, and that is the more uncomfortable
finding: **they had been passing because of the leak.** They pinned `as_of` to
a fixed past date while retrieving live content — the leakage case itself — and
the retrieval-dated observations they relied on are exactly what is now
dropped. They now run against the live path, and the past-`as_of` behaviour is
covered by two explicit leakage regressions.

This is engineering spend on a **measured blocker**: it prevented the commit,
and it silently invalidates historical replay, which is the mission's only
evaluation method. Well inside the 20% budget.

### Recommendation

**CONTINUE OPERATING.**

Nothing blocked the operating cycle itself. Two hypotheses tested and retired,
three correctly refused as untestable, one apparent discovery examined and
withdrawn, one leakage defect found and fixed. **Framework stability: 4** — the
fix was to an adapter, not to the framework.

The day's two most valuable outputs are both things that were *not* claimed:
the 0.359 result, and the evidence that would have leaked into every future
replay.

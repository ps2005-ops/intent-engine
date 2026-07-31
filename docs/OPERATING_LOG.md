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

---

## 2026-07-30 — Day 3 · more data made the sample *smaller*

Instruction: stop looking for price transforms; the bottleneck is effective
sample size. Increase independent information events without lookahead.

### What was added

- **History: 400 days → 10 years.** Measured before use: `range=10y` returns
  2513 daily bars against ~275 for 400d. (`range=max` was rejected — it
  silently switches to a coarser interval and returns 135 bars.)
- **Event types: 6 → 16.** Added ownership (SC 13D/G, Form 4) and proxy
  (DEF 14A, DEFA14A, amendments) alongside the original event and periodic
  forms. Each is a different information shock, not more rows of the same one.
- **`market/sampling.py`** — n_eff computed always, not by hand. Day 2's
  correction was done manually; a result that must be manually second-guessed
  will eventually not be.

### The result, and it is not what more data was supposed to do

| signal | rows | events | **windows** | n_eff | design effect | accuracy | verdict |
|---|---|---|---|---|---|---|---|
| `event_drift.v1` | 1518 | 1393 | **5** | 5 | **303×** | 0.4921 | unmeasurable (n_eff < 30) |
| `report_drift.v1` | 263 | 263 | **49** | 49 | 5.4× | **0.5019** | **indistinguishable from 0.500** |
| `ownership_drift.v1` | 4849 | 2131 | **9** | 9 | **539×** | 0.4745 | unmeasurable (n_eff < 30) |
| `proxy_drift.v1` | 162 | 160 | **26** | 26 | 6.2× | 0.6049 | unmeasurable (n_eff < 30) |

**Rows went up ~5×. Independent windows went DOWN for every dense event type.**

The mechanism is arithmetic, and it inverts the intuition that drove this
day's instruction. A 21-day horizon over ten years admits at most ~174
non-overlapping windows. Fourteen companies filing 8-Ks and Form 4s
continuously produce windows that overlap *everywhere*, so the union collapses
to **5 contiguous spans**. Collecting more of a dense event type does not add
independence — it merges what independence there was.

Quarterly reports survive precisely because they are **naturally spaced**: 263
filings, 49 independent windows.

> **Event frequency is the enemy of independence.** The refinement from
> "observations" to "independent information events" was right and does not go
> far enough: 1393 genuinely distinct 8-K events still yield 5 windows, because
> independence is a property of *time*, not of the event count.

### Day 2's false discovery is now definitively dead

`report_drift.v1` was 0.359 over 13 months and looked significant. Over ten
years and 49 independent windows it is **0.5019** — the first properly-powered
result in this project, and it sits on the baseline. The Day 2 caution was
correct, and this is the confirmation.

### The tempting one, refused

`proxy_drift.v1` at **0.6049** is the most alpha-shaped number the project has
produced. n_eff = 26, below `A-M5`'s 30. **Unmeasurable, not promising.**

Pre-registered for a future day rather than claimed now: if proxy-filing drift
survives to n_eff ≥ 30 *without* changing the rule that produced it, it becomes
testable. Changing the rule to reach 30 faster would be fitting the test to the
answer.

### Signals retired today

`event_drift.v1` and `ownership_drift.v1` — not because they lost, but because
they **cannot be measured at any sample size reachable this way**. Design
effects of 303× and 539× mean a naive error bar is ~17× and ~23× too narrow.
Retired immediately, per instruction.

### Live cycle

Unchanged from Day 2 and re-run: 16 companies, 0/0/0/2/14, **0 paper trades**,
16 justified refusals. No trade forced, no gate relaxed.

### Next measured bottleneck

**Horizon length, not data volume.** n_eff is bounded above by
`history ÷ horizon`. Ten years at a 21-day horizon caps independence at ~174
windows however many companies or event types are added — and dense events
land far below that cap.

Three levers, ranked by measured effect on n_eff:
1. **Shorter horizon** — 5-day windows would raise the ceiling ~4×, and is the
   only lever that raises the *cap* rather than approaching it.
2. **Sparser event types** — quarterly reports already demonstrate this: 263
   rows → 49 windows, versus 4849 rows → 9.
3. **More companies** — adds cross-section, adds **no** new windows. Confirmed
   directly by this run, and it was ranked #2 as recently as Day 2.

### Recommendation

**CONTINUE OPERATING.** Framework stability: **5** — `sampling.py` is new
measurement, not a framework change. 2978 passing.

---

## 2026-07-30 — Day 4 · the honest horizon and the powerful one coincided

Instruction: horizons belong to hypotheses, justified before testing, fixed,
and **never shortened for power**.

Horizons pre-registered with mechanism justifications in
[`PREREGISTRATION_day4_horizons.md`](PREREGISTRATION_day4_horizons.md).

### Results — all five retired

| hypothesis | horizon | rows | events | windows | n_eff | DE | accuracy | verdict |
|---|---|---|---|---|---|---|---|---|
| `event_drift.v1` | 3d | 1529 | 1402 | **400** | 400 | 3.8× | 0.4912 | **retire — on baseline** |
| `report_drift.v1` | 5d | 264 | 264 | **96** | 96 | 2.8× | 0.5341 | **retire — on baseline** |
| `proxy_drift.v1` | 90d | 139 | 137 | 10 | 10 | 13.9× | 0.5108 | retire — unmeasurable |
| `activist_stake.v1` | 120d | 18 | 18 | 3 | 3 | 6.0× | 0.5000 | retire — unmeasurable |
| `insider_buy.v1` | 90d | 4352 | 1806 | **1** | 1 | **4352×** | 0.4809 | retire — unmeasurable |

2σ bands on n_eff: `event_drift` (0.450, 0.550) · `report_drift` (0.398, 0.602).
Both contain 0.500.

### My pre-registered prediction was wrong

I predicted adaptive horizons would **reduce** independent evidence. Measured:

| | Day 3 (uniform 21d) | Day 4 (adaptive) |
|---|---|---|
| total independent windows | 89 | **510** (5.7×) |
| measurable hypotheses (n_eff ≥ 30) | 1 | **2** |

The reasoning behind the prediction was sound and incomplete. I saw that long
horizons cut `n_eff` hard — true, and `insider_buy` at 90d collapses 4352 rows
into **one** window, a design effect of 4352×. What I missed is that the *fast*
mechanisms are also the *dense* ones. Matching an 8-K to a 3-day horizon fixes
the mechanism fit and the power problem in the same move, because unscheduled
news genuinely resolves in days.

> **The honest horizon and the powerful horizon coincided — for fast
> mechanisms.** Not by construction and not by tuning: a mechanism that
> resolves quickly generates independent windows quickly. Slow mechanisms stay
> genuinely unmeasurable, which is the true statement about them.

This is the answer to the day's question. Adaptive horizons **do** increase
independent evidence, without lookahead and without multiple-testing bias —
five hypotheses, one fixed justified horizon each, all five reported.

### Day 3's tempting number is dead

`proxy_drift.v1` scored **0.6049** on Day 3 at a 21-day horizon. Its mechanism
— governance and compensation changes resolving over an annual cycle — implies
90 days. At its own horizon it is **0.5108**.

The most alpha-shaped number this project produced was an artifact of testing a
slow mechanism at a fast horizon. It was never claimed, and now it is retired.

### `event_drift.v1` is the best-powered result in the project

n_eff = 400 independent windows, design effect 3.8×, accuracy **0.4912**, band
(0.450, 0.550). This is not "we lack evidence" — it is a properly-powered
negative result. **8-K/6-K drift over 3 days does not exist at a magnitude this
data could detect.** Retired with confidence rather than for want of power.

### The leakage guard caught the operating script

The live cycle ran first with gates `no_dated_evidence: 2,
no_strategic_reading: 13` and quality **0.1** everywhere — a collapse from
Day 3.

Cause: `reality_run.py` had `AS_OF` hardcoded to a past date while retrieving
live content. Yesterday's leakage guard correctly stripped every
retrieval-dated observation as future-dated, and the cycle's evidence vanished.

**The guard was right and the script was wrong.** A live operating cycle
decides today using today's evidence; `AS_OF` is now the run date. Re-run
restores `no_outside_source: 2, view_withheld: 7, no_strategic_reading: 6`,
quality 0.575 — matching Day 3.

Worth stating plainly: a guard added one day caught a latent defect in the
operating harness the next. That is the guard earning its place.

### Live cycle

16 companies · **0/0/0/2/14** · **0 paper trades** · 16 justified refusals.
Evidence 10/16, yield 3/16, independent 0/16. No trade forced, no gate relaxed.

### Signals surviving: zero

Nine hypotheses have now been proposed, tested and retired across four days.
None beat 0.500. Two were retired **with adequate power** (n_eff 400 and 96);
the rest are unmeasurable with reachable data.

### Next measured bottleneck

**The universe is 14 companies.** Every remaining slow-mechanism hypothesis
fails on `n_eff` because activist stakes and proxy contests are rare *per
company* — 18 SC 13D filings in ten years across fourteen companies.

This is the first time more companies is the right answer, and it is right for
a reason that did not hold before: at **short** horizons, cross-sectional
breadth now adds windows rather than merging them. Day 3 measured the opposite
because everything ran at 21 days. The lever changed when the horizons did.

### Recommendation

**CONTINUE OPERATING.** Framework stability: **6**. 2978 passing.

---

## 2026-07-30 — Day 5 · breadth tripled the rows and cut independent evidence

### Falsification first — the ranking survived, but it had to be proven

| candidate | verdict |
|---|---|
| **A. More historical years** | **Capped.** Yahoo daily stops at 10y; `range=max` silently switches to a coarser interval (135 bars). No lever. |
| **C. More sparse event types** | **Self-defeating.** Sparse is the problem: SC 13D gave 18 rows / 3 windows across 14 companies over 10 years. |
| **D. Better strategic-reading yield** | **Zero replay effect.** Yield gates the live path; replay uses EDGAR + prices and never consults the strategic reading. Real bottleneck, wrong one. |
| **B. More companies** | **#1 — and proven not pseudo-breadth.** |

B was not assumed. Marginal *new* event dates per company added: 100% for the
first, ~65% by the fourteenth, mean **87 new dates each** for the last five. 14
companies covered 1065 unique event dates = 29.2% of calendar days, against a
3-day window ceiling of 1216 — **816 windows of headroom**.

### Expansion: 15 → 27 tradables, chosen for diversity not convenience

Added across regions the engine had never seen — Latin America, Australia,
Middle East, Africa — plus the last missing sector (Communication Services) and
two small-caps. **Regions 4 → 8. Sectors 11 → 12. Sector concentration 0.31 →
0.21.**

### The result, and it is the warning made real

| clustering definition | n | 2σ band |
|---|---|---|
| raw observations | **4991** | (0.486, 0.514) |
| unique events | 4008 | (0.484, 0.516) |
| unique event dates | 1957 | (0.477, 0.523) |
| **non-overlapping windows** | **246** | (0.436, 0.564) |
| regime clusters (quarter) | 41 | (0.344, 0.656) |
| company clusters | 26 | (0.304, 0.696) |
| sector clusters | 11 | (0.198, 0.802) |
| **regional clusters (strictest)** | **8** | (0.146, 0.854) |

Accuracy **0.4959**. Under the strictest defensible clustering — regional,
n=8 — **unmeasurable**, and indistinguishable from 0.500 under every other.

### Breadth increased row count and DESTROYED independent evidence

| | Day 4 (14 co) | Day 5 (27 co) | |
|---|---|---|---|
| raw observations | 1529 | **4991** | ↑ 3.3× |
| unique event dates | 1065 | **1957** | ↑ 1.8× |
| **non-overlapping windows** | **400** | **246** | **↓ 38%** |

Unique event dates nearly doubled. **Independent windows fell by more than a
third.** With 1957 event dates across 3650 calendar days, 54% of days now carry
an event, and 3-day windows chain into 246 contiguous blocks instead of
standing apart.

> Adding companies added **dates** and destroyed **independence**. Independence
> is a property of non-overlapping *time*, and denser events overlap more. The
> falsification measured the right quantity — marginal new dates — and dates
> turned out not to be the binding unit.

### Answering the four questions directly

1. **Row count** — increased, 3.3×.
2. **Independent evidence** — **decreased**, −38% on windows, and the strictest
   clustering (regional, n=8) is worse than Day 4's.
3. **Measurable hypotheses** — **no increase**. Under regional clustering,
   zero.
4. **Decision Quality potential** — unchanged for signal discovery. Genuinely
   improved for the *live* path, which now evaluates 28 companies across 8
   regions instead of 16 across 4 — but that is a different capability from
   finding alpha, and conflating them is the error this day was designed to
   catch.

### The portfolio cap held

Two tests failed on expansion. Not defects: the eligibility gate refused the
surplus with *"portfolio at max open positions (25)"* against a 27-tradable
universe. Risk control working. The tests asserted every tradable becomes an
intent, which was only true while the universe was smaller than the cap; they
now assert the real property — every prediction becomes an intent **or** carries
a stated refusal reason, and nothing is silently dropped.

### Live cycle

28 companies · **0/0/0/3/25** · **0 paper trades** · 28 justified refusals.
Four companies formed a reading (up from three); yield 4/28 = 14%, down from
19% because the added companies are harder to read, not because reading got
worse. Independent sources still **0/28**. No trade forced, no gate relaxed.

### Next measured bottleneck

**Temporal density is now the constraint, and more of anything makes it
worse.** Three levers remain, and two are closed:

- more companies → measured this day to *reduce* independent windows
- more years → capped by the price feed
- **shorter horizons** → raises the window ceiling, but Day 4 established
  horizons belong to mechanisms and must not be shortened for power

The honest conclusion is that **event-drift hypotheses on a 10-year daily
window are exhausted**. Getting more independent evidence needs a genuinely
different axis — intraday resolution, or a data source with point-in-time depth
this project cannot currently reach.

### Recommendation

**CONTINUE OPERATING.** Framework stability: **7**. 2978 passing.

---

## 2026-07-31 — Day 6 · why the engine has never opened a trade

### EXECUTIVE SUMMARY

| | |
|---|---|
| Decision Quality (refusals) | **1.000** · n=28 · medium |
| Decision Quality (positions) | **UNMEASURABLE** — no position has ever existed |
| Paper Trade Win Rate | **UNMEASURABLE** (n=0) |
| Total Return | **UNMEASURABLE** (n=0) |
| Sharpe Ratio | **UNMEASURABLE** (n=0) |
| Maximum Drawdown | **UNMEASURABLE** (n=0) |
| Open Positions | **0** |
| Signals Beating Baseline | **0 of 11 tested** |
| Framework Stability | **8** |

### FALSIFICATION — the finding of the day

Six operating days, 28 companies, **zero paper trades**. Not caution. Traced:

```
discovery      → finds 3 customer_voice candidates (Shopify AND Comcast)
select_diverse → correctly approves 2, outside-classes first
retrieval      → G2          HTTP 403
                 Trustpilot  HTTP 403
               → 0 outside sources retrieved, on every run
reasoner       → no_outside_source cannot pass
               → BUY/SELL structurally unreachable
```

`independent_source` has been **0 on every live run**: 0/16, 0/16, 0/16, 0/28,
0/28. The gate is not selective — it has never once passed in reality.

### The fix that was available, and refused

EDGAR carries filings made **by other entities about** a company. An SC 13G
filed by Vanguard about Shopify is Vanguard's statement, not Shopify's:
technically third-party, free, point-in-time, and it does not block automated
access. Reclassifying those as independent would move `independent_source`
from 0/28 to ~28/28 and unlock trading immediately.

**Not built.** A passive ownership disclosure does not check a company's
account of its own strategy, which is the only reason the gate exists. It
would move the metric and improve the capability by nothing — the exact
failure `METRIC_INTEGRITY.md` exists to prevent, and the first time that
temptation has been concrete rather than theoretical.

### DECISION QUALITY

| | value | n | confidence |
|---|---|---|---|
| Overall | 1.000 | 28 | medium |
| Position | UNMEASURABLE | 0 | — |
| Refusal | 1.000 | 28 | medium |

Every refusal cited a listed gate; zero unjustified.

### TRADING PERFORMANCE · RETURN · RISK · PORTFOLIO

**All UNMEASURABLE (n=0).** Trades opened 0 · closed 0 · win/loss/breakeven
rate, holding period, total and per-trade return, median, best, worst, profit
factor, expectancy (R and %), Sharpe, Sortino, max drawdown, volatility,
risk-adjusted return, average risk/reward, equity curve, cumulative return,
benchmark (SPY) comparison and alpha vs benchmark.

Open positions 0 · sector/region/market-cap exposure none · cash 100% (paper)
· average position size n/a.

Benchmark comparison is the right metric to have asked for and cannot be
populated: there is no equity curve to compare against SPY.

### SIGNAL PERFORMANCE

| signal | accuracy | baseline | n_eff | CI (strictest) | DE | status |
|---|---|---|---|---|---|---|
| `momentum_persists.v1` | 0.5000 | — | 66 | (0.377, 0.623) | — | **RETIRED** (is the baseline) |
| `mean_reversion.v1` | 0.5000 | 0.500 | 66 | (0.377, 0.623) | — | RETIRED |
| `strong_trend.v1` | 0.4706 | 0.500 | 34 | (0.329, 0.671) | — | RETIRED |
| `calm_trend.v1` | 0.5000 | 0.500 | 24 | — | — | RETIRED (unmeasurable) |
| `event_drift.v1` @3d | 0.4959 | 0.500 | **8** (regional) | (0.146, 0.854) | 3.8–624× | RETIRED |
| `report_drift.v1` @5d | 0.5341 | 0.500 | 96 | (0.398, 0.602) | 2.8× | RETIRED |
| `insider_buy.v1` @90d | 0.4809 | 0.500 | 1 | — | 4352× | RETIRED (unmeasurable) |
| `activist_stake.v1` @120d | 0.5000 | 0.500 | 3 | — | 6.0× | RETIRED (unmeasurable) |
| `proxy_drift.v1` @90d | 0.5108 | 0.500 | 10 | — | 13.9× | RETIRED (unmeasurable) |

**Active signals: 0. Signals beating baseline: 0.**

### LEARNING

Hypotheses proposed 11 · retired 11 · revised 66 (all `momentum_persists.v1`,
confidence 0.55 → 0.55). Decision Quality change: none measurable. Calibration
change: none — `A-M5` unreached on the live path. Learning Value:
**unscored**; `information_gain` and `calibration_impact` remain UNMEASURABLE.

Engineering Prediction Accuracy: **6 predictions, 1 correct** (cycle 3, LV
0→1–3, landed at 1). Four wrong bottleneck, one wrong scope, one wrong
direction (Day 4, adaptive horizons — I predicted less independent evidence
and got 5.7× more).

### OPERATIONAL HEALTH

28 companies · 28 opportunities · **0/0/0/2/26** BUY/SELL/HOLD/WATCH/NO_TRADE ·
0 trades opened · 0 closed · **28 refusals** · strategic-reading yield 3/28
(11%) · independent-source yield **0/28** · framework stability 8.

Gates: `no_strategic_reading` 14 · `view_withheld` 11 · `no_outside_source` 2 ·
`not_tradable` 1.

Yield fell 19% → 14% → 11% as the universe grew — the added companies are
harder to read, not the reading worse.

### NEXT STEPS

1. **Highest measured bottleneck — outside-source retrieval.** The only
   independent sources discovery finds are review aggregators that return 403.
2. **Why it dominates.** It is the single cause of every UNMEASURABLE metric in
   this report. Not one trading, return, risk or portfolio number can exist
   until it clears.
3. **Expected Decision Quality impact.** Large but *slow*: it would open the
   position half of Decision Quality, which currently has n=0. At 28 companies
   and a 21-day horizon, `A-M5`'s n≥30 is months away.
4. **Expected Learning Value impact.** Unblocks `resolution_quality` on the
   live path; `information_gain` and `calibration_impact` stay blocked.
5. **Is engineering justified? No.** The only fix reachable today games the
   gate rather than solving it. Genuine outside evidence needs a news or
   analyst feed that does not refuse automated access — a capability this
   project cannot currently reach, and not something to fake.

### RECOMMENDATION

**CONTINUE OPERATING.**

Operation is not blocked: research runs daily, refusals are graded and
justified, and the replay path produces properly-powered results. What is
blocked is the trading half — and the honest response is to record that
precisely rather than to unlock it by weakening the gate that makes the
records trustworthy.

---

## 2026-07-31 — Day 7 · one engineering cycle · typed independent evidence

### FALSIFICATION — the premise was wrong, the architecture still failed

**The proposed premise was factually false.** The gate did not require one
category. Measured:

```
gate accepts       : analyst_coverage, competitor_statement,
                     customer_voice, independent_reporting   (4 categories)
discovery produces : customer_voice                          (1 category)
accepted-but-never-found : analyst_coverage, competitor_statement,
                           independent_reporting
```

The narrowness was in **discovery**, not the gate. Saying otherwise would have
been fixing the wrong layer.

**But the architecture failed anyway, from first principles.** The gate exists
because *"a position taken purely on what a company says about itself is a
position on its marketing."* That sentence contains two conditions the gate
collapsed into one hardcoded list:

| condition | question | old gate |
|---|---|---|
| **Independence** | is the AUTHOR someone other than the subject? | approximated by a class list |
| **Relevance** | does this evidence bear on THIS claim? | **not modelled at all** |

Both were wrong at the edges:

- An **SC 13D** is authored by an activist, not the company — genuinely
  independent, and rejected because its class was not listed.
- **Customer reviews** were accepted as corroboration for *any* claim,
  including governance claims they say nothing about.

### The one engineering task

`market/corroboration.py`. Seven categories, kept distinct and never collapsed
into a score — a single "corroboration score" would let strong evidence of the
wrong kind substitute for weak evidence of the right kind, which is the exact
failure being fixed.

Requirements are stated **per hypothesis kind**, and `required` is a set of
alternatives rather than a conjunction: a customer-adoption claim is
corroborated by customers **or** by an industry observer reporting the same
adoption — but never by a macro series, which cannot speak to one company's
customers.

### The anti-gaming property, now structural

Day 6 found that reclassifying SC 13G as an outside source would move
`independent_source` from 0/28 to ~28/28 and unlock trading while improving
capability by nothing. That was refused by restraint. **It is now impossible by
construction:**

```
assess(["third_party_filing"], hypothesis_kind="customer_adoption")
  -> independent_present: institutional   (the filing IS recognised as
                                           independent — that was never the issue)
  -> missing:             customer_voice
  -> satisfied:           False
```

No relabelling connects them, because the category a filing belongs to is a
fact about its author, not a knob. Asserted by test.

`investor_material` — a company's own SEC filing — remains **COMPANY**, not
regulatory. The venue is official; the author is still the subject.

### VALIDATION — the causal chain, re-run and typed

Against what a live company actually retrieves today (`company_owned`,
`executive_statement`, `investor_material`):

| hypothesis kind | status | missing |
|---|---|---|
| customer_adoption | blocked | `customer_voice` or `industry` |
| governance | blocked | `institutional` or `regulatory` |
| macro_sensitivity | blocked | `macro` |
| expectation_shift | blocked | `analyst` or `industry` |
| competitive_position | blocked | `alternative` or `industry` |
| **price_behaviour** | **unlocked** | — |

A refusal now says *"a customer_adoption claim needs customer_voice or
industry; independent evidence present: none"* instead of `no_outside_source`.

### Report

- **Previous architecture** — one global gate, membership in a 4-class list,
  identical for every claim, no concept of relevance.
- **New architecture** — 7 typed categories; independence decided by
  authorship; relevance decided per hypothesis kind; both checked separately
  and never traded off.
- **Categories observed live** — company only (3 source classes → 1 category).
- **Categories missing** — customer_voice, industry, institutional, regulatory,
  macro, analyst, alternative. **Six of seven never appear.**
- **Decision paths unlocked** — one: `price_behaviour`, which correctly
  requires no company corroboration because it asserts nothing about the
  business. It remains gated on dated evidence and on the market signal.
- **Decision paths still blocked** — all five company-claim kinds.
- **Does BUY/SELL remain unreachable?** On company claims, **yes**. The
  measured blocker is unchanged: no independent evidence of any category is
  retrievable.
- **Did the measured blocker change?** It became *precise*. It was
  "`no_outside_source`, cause unknown". It is now "six of seven evidence
  categories are never retrieved, and here is which claim each would unlock".
- **Did Decision Quality increase?** Not measurably — refusal justification was
  already 1.000. The refusals are now *diagnostic*, which is a prerequisite for
  improving it rather than an improvement itself.
- **Did capability increase?** **Yes.** The engine can now express what would
  corroborate a claim, and can distinguish "found nothing independent" from
  "found plenty of the wrong kind". It could not before.

### Was this worth one engineering cycle?

Yes, and the honest reason is not that it unlocked a trade — it unlocked none.
It is that the previous model **could not have been fixed by more data**.
Retrieving G2 successfully would have satisfied `no_outside_source` for a
governance claim, which is wrong, and nothing in the old architecture could
notice.

### Returning to operating mode

No further architecture work. **Framework stability resets to 0** and starts
counting again. 2990 passing (+12).

### Recommendation

**CONTINUE OPERATING.**

---

## 2026-07-31 — Day 8 · the top category unlocks nothing

### EXECUTIVE SUMMARY

| | |
|---|---|
| Overall Decision Quality | **1.000** · n=28 · medium |
| Position Decision Quality | **UNMEASURABLE** — no position has ever been opened (n=0) |
| Refusal Decision Quality | **1.000** · n=28 · medium |
| Paper trades opened / closed | **0 / 0** |
| Win rate · Total return · Expectancy · Profit factor | **UNMEASURABLE** (n=0 trades) |
| Sharpe · Sortino · Max drawdown | **UNMEASURABLE** (n=0 trades, no equity curve) |
| Open positions | **0** |
| Signals beating baseline | **0 of 11** |
| Framework stability | **1** (reset Day 7) |

### Evidence gap, aggregated: 28 companies × 6 hypothesis kinds = 168 paths

| missing category | paths blocked | share |
|---|---|---|
| **industry** | **84** | **33%** |
| customer_voice | 28 | 11% |
| institutional | 28 | 11% |
| regulatory | 28 | 11% |
| macro | 28 | 11% |
| analyst | 28 | 11% |
| alternative | 28 | 11% |

`industry` blocks 3× any other, because it appears in the required set of
three hypothesis kinds (customer_adoption, expectation_shift,
competitive_position) where every other category appears in one.

- **Independence failures: 140** (no independent evidence of any kind)
- **Relevance failures: 0** — we never hold independent-but-irrelevant
  evidence, because we hold no independent evidence at all
- **Categories present but irrelevant: none**
- **Viable paths today: `price_behaviour` × 28** — the only kind needing no
  company corroboration

### Falsification of the top-ranked category

| category | paths | retrieval (measured) | replay depth | lookahead |
|---|---|---|---|---|
| **industry** | **84** | **HTTP 200** (TechCrunch, GlobeNewswire RSS) | **POOR** — RSS carries recent items only | low |
| customer_voice | 28 | **HTTP 403** | poor | low |
| institutional | 28 | HTTP 200 (EDGAR) | **STRONG** — 10y, point-in-time by construction | low |
| regulatory | 28 | HTTP 200 (EDGAR) | **STRONG** | low |
| macro | 28 | HTTP 400 (needs key) | strong | **REVISIONS** — FRED series are revised, so today's value for a past date is lookahead |
| analyst | 28 | no free source | none | n/a |
| alternative | 28 | no free source | none | high |

Industry wins paths, DQ breadth and retrieval. It **loses historical replay** —
RSS carries recent items only, and walk-forward replay is this project's only
way to test a signal. Institutional and regulatory win replay depth and are
already retrievable, at 3× fewer paths.

**No category clearly dominates across the eight criteria.**

### The decisive test: what would acquiring it actually change?

Simulated, not argued:

```
today                        WATCH   gate=no_outside_source
                                     missing=[customer_voice, industry]
+ industry evidence          WATCH   gate=no_market_evidence   missing=[]
+ industry AND a signal      BUY     gate=-
```

Acquiring the highest-ranked category moves the gate one step deeper and
**produces no trade**, because the next gate is the market signal — and all
eleven signals are retired, none beating 0.500.

> The evidence gap is real and it is **not the binding constraint**. Building
> the adapter would have bought a deeper refusal, not a decision.

### Report

- **Blocked hypotheses by category** — above; industry 84, all others 28.
- **Marginal paths each category would validly unlock** — industry 84,
  every other 28. No double-counting: each is the count of paths where that
  category *alone* satisfies the requirement.
- **Categories present but irrelevant** — none.
- **Independence failures** — 140. **Relevance failures** — 0.
- **Strategic-reading yield** — 3/28 (11%).
- **Independent-evidence yield by category** — customer_voice 0/28,
  industry 0/28, institutional 0/28, regulatory 0/28, macro 0/28,
  analyst 0/28, alternative 0/28. **Zero across all seven.**
- **Highest measured bottleneck** — **no signal beats the baseline.** It sits
  *behind* the evidence gap, and closing the evidence gap does not reach it.
- **Is engineering justified?** **No.** The adapter would change a refusal
  reason and no decision.

### Live cycle

28 companies · **0/0/0/2/26** · **0 paper trades** · 28 justified refusals ·
yield 3/28 · independent-evidence yield 0/28 across all categories. No trade
forced, no gate relaxed, no retired signal revived.

### RECOMMENDATION

**CONTINUE OPERATING.**

Two independent reasons, either sufficient: no category clearly dominates the
eight criteria, and the top-ranked one demonstrably unlocks zero decisions
today. The next advance is a signal that beats 0.500 — not more evidence to
feed signals that do not exist.

---

## 2026-07-31 — Day 9 · falsification failed, and it corrected Day 8

### THE CLAIM UNDER TEST

> "The primary bottleneck is no longer evidence retrieval. It is the absence
> of viable hypotheses."

**FALSIFIED.** Given every evidence category, today's wired signal fires and
produces a position on every hypothesis kind:

```
wired signal: baseline_momentum.v1   fires? True   direction=up

  customer_adoption     BUY   gate=-
  governance            BUY   gate=-
  macro_sensitivity     BUY   gate=-
  expectation_shift     BUY   gate=-
  competitive_position  BUY   gate=-
  price_behaviour       BUY   gate=-
```

The engine is not short of hypotheses that could trade. It is short of the
evidence to corroborate them.

### Day 8 was wrong, and this is the correction

Day 8 reported: *"acquiring the top-ranked category moves the gate one step
deeper and produces no trade."* That statement is **false**, and it was the
load-bearing sentence in that day's recommendation.

The error: my Day 8 simulation passed **no market evidence**, so the reasoner
stopped at `no_market_evidence`. The live sweep calls `_baseline_market()`,
which computes momentum from real prices and **fires**. I conflated *"retired
as an alpha claim"* with *"not wired"* — `baseline_momentum.v1` is measured at
0.500 and remains the live signal.

Day 8's conclusion (CONTINUE OPERATING, no adapter) rested on that error. The
correct reading of Day 8's own data is the opposite: an evidence adapter would
unlock real decisions today.

### Which means the Signal Discovery Engine is NOT the work

The Day 9 instruction was conditional — *"if the answer is no, accept the
ranking"* — and the answer is **yes**. Building a hypothesis generator would
be solving a problem the measurement says this engine does not have. Nine
existing hypothesis kinds already reach BUY the moment they are corroborated.

**Not built.**

### Re-ranked, on corrected facts

| | unlocks | retrievable | replay depth | live-path value |
|---|---|---|---|---|
| **industry** | **84 paths / 3 kinds** | **HTTP 200 (RSS)** | poor | **high** |
| institutional / regulatory | 28 paths / 1 kind | HTTP 200 (EDGAR) | strong | medium |
| customer_voice | 28 | HTTP 403 | poor | blocked |
| macro | 28 | needs key | strong (revision risk) | blocked |
| analyst / alternative | 28 | no free source | none | blocked |

Industry's weakness is historical replay depth. That weakness applies to
**signal testing**, not to **live decisions** — and live decisions are where
every UNMEASURABLE metric in this report comes from. With the Day 8 error
corrected, **industry dominates for the capability that is actually blocked.**

### What an industry adapter would and would not buy

**Would:** position Decision Quality from `n=0` to measurable · paper trades ·
win rate, expectancy, drawdown, Sharpe, equity curve, SPY comparison · the
first live resolutions toward `A-M5`'s n≥30.

**Would not:** an edge. The signal that would fire is measured at **0.500**.
These would be honest, gradable, calibration-producing coin flips — valuable
as feedback, worthless as alpha, and they must not be reported as the latter.

### Live cycle

28 companies · **0/0/0/2/26** · **0 paper trades** · 28 justified refusals ·
yield 3/28 · independent-evidence yield 0/28 across all seven categories.

Unchanged from Day 8, run on the same universe and the same code. No trade
forced, no gate relaxed, no retired hypothesis revived.

### Performance metrics

Overall / Refusal Decision Quality **1.000** (n=28, medium). Position Decision
Quality, win rate, total return, expectancy, profit factor, Sharpe, Sortino,
max drawdown, open positions, equity curve, SPY comparison: **UNMEASURABLE —
zero paper trades have ever been opened.** Signals beating baseline **0 of
11**. Framework stability **2**.

### Report against the requested fields

- **Hypotheses proposed:** 0 — the generator was not built, and the reason is
  measured rather than declined.
- **Rejected before testing:** n/a.
- **Testable today:** all six existing kinds, *if corroborated*.
- **Blocked by missing point-in-time data:** all six, on evidence not
  mechanism.
- **Entering replay:** 0.
- **Immediately retired:** 0.
- **Expected independent evidence required:** industry for three kinds;
  customer_voice, institutional, regulatory, macro, analyst, alternative for
  one each.

### RECOMMENDATION

**PAUSE FOR ONE EVIDENCE ADAPTER — industry.**

The first time in nine days this project has recommended engineering. The bar
was *"a measured blocker prevents meaningful learning"*: position Decision
Quality has been `n=0` for nine days, and today's measurement shows evidence —
not hypotheses — is what holds it there.

Stated plainly: this recommendation exists **because Day 8's contrary
conclusion was based on my own measurement error**, now corrected.

---

## 2026-07-31 — Day 10 · industry evidence adapter

### FALSIFICATION — 4 of 5 checks pass, 1 fails and is stated

| check | result |
|---|---|
| 1. blocks the most executable paths | ✅ 84 of 168, 3× any other |
| 2. retrievable in production | ✅ HTTP 200, 100 company-specific items |
| 3. timestamped correctly | ✅ `pubDate` on **100/100** |
| 4. replayable honestly | ❌ **87 days** of depth against 3650 needed |
| 5. satisfies the evidence framework | ✅ INDUSTRY by authorship |

No other category dominates all eight criteria — institutional/regulatory win
replay depth at 3× fewer paths. Proceeded, with check 4 recorded as a hard
limitation rather than worked around.

> **Industry evidence is a LIVE-PATH capability only.** It can unlock live
> decisions and can never validate a signal. 87 days cannot support a
> ten-year walk-forward.

### ADAPTER METRICS (8 companies, live)

| | |
|---|---|
| documents discovered | **175** |
| accepted (independent **and** relevant) | **5** |
| rejected | 170 |
| retrieval failures | 0 |
| by category | industry 126 · analyst 21 · **company 28** |
| relevance rate | **2.9%** |
| replay depth | 87 days |
| timestamp failures | 0 (documents without a readable date are dropped) |
| lookahead violations | **0** — anything after `as_of` is rejected, never clamped |

**28 documents were classified COMPANY** — a company's own press releases
syndicated through a news aggregator. That is the specific gaming route this
adapter had to keep shut, and it is shut by authorship: the venue never
overrides the author.

The 2.9% relevance rate is the honest number. Most coverage of a company says
nothing about customer adoption, and admitting it would corroborate a claim it
cannot speak to.

### CAUSAL VALIDATION — the mandatory test

| company | with industry | without | verdict |
|---|---|---|---|
| duolingo | **BUY** | WATCH | **GENUINE** |
| caterpillar | **SELL** | WATCH | **GENUINE** |

```
duolingo    2026-07-28  Investing.com   "Scotiabank raises Duolingo stock
                                         price target on user growth"
caterpillar 2026-07-29  Yahoo Finance   "Caterpillar shrugs off tariff hit
                                         as demand holds"
```

Removing the industry evidence returns both to WATCH. **Zero spuriously
unlocked.** The gate that changed is `no_outside_source` → cleared; the
decision then rests on the wired signal as it always did.

**Honest imperfection:** the Duolingo document reports an *analyst* action but
is published by a news outlet, so publisher-based classification calls it
INDUSTRY. Defensible — the journalist is the author and is independent — but
the category reflects who wrote it, not what it is about, and that distinction
will matter when ANALYST becomes its own retrievable category.

### EXECUTIVE SUMMARY

| | |
|---|---|
| Overall / Refusal Decision Quality | **1.000** · n=28 · medium |
| Position Decision Quality | **UNMEASURABLE** — adapter is built and validated but **not wired into the daily sweep**; no paper trade has been opened |
| Paper trades opened / closed | **0 / 0** |
| Win rate · Total return · Expectancy · Profit factor | **UNMEASURABLE** (n=0) |
| Sharpe · Sortino · Max drawdown · Equity curve · SPY alpha | **UNMEASURABLE** (n=0) |
| Open positions | **0** |
| Signals beating baseline | **0 of 11** |
| Framework stability | **0** (engineering cycle) |

### DECISION IMPACT

- **Hypotheses now unlockable:** customer_adoption, expectation_shift,
  competitive_position — the three that accept INDUSTRY.
- **Still blocked:** governance (needs institutional/regulatory),
  macro_sensitivity (needs macro).
- **New BUY / SELL demonstrated:** 1 / 1, both causally genuine.
- **Did position Decision Quality become measurable?** **Not yet** — the
  adapter is not wired into `daily_opportunity_sweep`. The prompt scoped this
  cycle to the adapter alone, and wiring it is an operating decision, not part
  of building it.

### NEXT STEPS

1. **Did the adapter increase capability?** **Yes** — two decisions exist that
   could not previously exist, and both fail without the evidence.
2. **Did it merely increase metrics?** **No.** `independent_source` moved
   because genuinely independent, genuinely relevant documents were retrieved
   — not because anything was relabelled. 28 company press releases were
   *rejected* on exactly that principle.
3. **Did it unlock previously unreachable decisions?** Yes, verified by
   ablation.
4. **Did it improve Decision Quality?** Not yet measurably. It makes position
   DQ *reachable*, which is a precondition, not the improvement.
5. **Is another engineering cycle justified?** **No.**

### RECOMMENDATION

**CONTINUE OPERATING.**

Wire the adapter into the daily sweep as an operating action and accumulate
real decisions. The measured priority is now real-world performance data, not
further architecture — 3005 passing, and the first genuinely unlockable
positions in ten days are waiting on operation rather than on engineering.

---

## 2026-07-31 — Day 11 · evidence semantics · FINAL architectural change

### FALSIFICATION — measured on 175 real documents, not argued

> *Can every document be represented accurately using only one category?*

**No.**

| | |
|---|---|
| documents analysed | 175 |
| **source/subject mismatches** | **13 (7%)** |
| documents with **multiple** subjects | **10 (19% of classified)** |

The mismatches are not edge cases with a single shape:

```
industry  + analyst_opinion    8   journalists reporting an analyst action
analyst   + earnings           2   analyst outlets writing about results
analyst   + macro              2   analyst outlets writing about the cycle
```

One category cannot hold these. And 19% carrying more than one subject means
the subject axis is not single-valued either — it is a **set**.

### The change

`SOURCE` (who wrote it — single, from authorship) and `SUBJECTS` (what it is
about — a set, from content), represented independently.

### The guarantee, asserted rather than promised

**Gates continue to key on SOURCE alone.** Subjects are recorded for future
reasoning and grant nothing today.

```
describe("third_party_filing", "Merchant adoption accelerates")
  -> subjects: [customer_adoption]        ← recorded
  -> assess(["third_party_filing"], "customer_adoption").satisfied = False
```

An institutional document *about* customer adoption still cannot corroborate a
customer-adoption claim. A semantics change that quietly widened a gate would
be the worst possible outcome of this cycle, so it is pinned by a test that
walks every hypothesis kind and asserts the verdict is byte-identical to
before.

### VALIDATION — the two documents that unlocked trades

| | duolingo | caterpillar |
|---|---|---|
| **old** | `category=industry` | `category=industry` |
| **new** | `source=industry` `subjects=[analyst_opinion]` | `source=industry` `subjects=[macro]` |
| decision changes | **No** | **No** |
| gate changes | **No** | **No** |
| category changes | **No** | **No** |

The Caterpillar document turns out to be about **macro** — a tariff/demand
story — which the one-dimensional model recorded as plain industry coverage.
That information now exists and is doing nothing, which is exactly right: it
becomes usable when a macro-sensitivity hypothesis has a macro source to pair
it with.

**No reasoning outcome changed. This was a semantics improvement only.**

3012 passing (+7).

### RETURNING TO OPERATING MODE

This is the final architectural change. No further framework redesign without
measurement proving it necessary.

The standing operating priority, in order:

1. **Wire the industry adapter into `daily_opportunity_sweep`** — an operating
   action, not engineering. Two genuine positions are waiting on it.
2. Accumulate paper trades.
3. Build a real equity curve and a SPY comparison.
4. Reach enough resolved outcomes to make Position Decision Quality measurable
   (`A-M5`: n ≥ 30).
5. Pause for engineering **only** if operating data reveals a new measured
   bottleneck.

### Where this project stands after eleven days

| | |
|---|---|
| Hypotheses proposed / retired | 11 / 11 |
| Signals beating baseline | **0** |
| Best-powered negative result | `event_drift.v1`, n_eff 400, 0.4912 |
| Measured baseline | **0.500** — the bar, established before anyone knew it |
| Paper trades opened | **0** |
| Position Decision Quality | UNMEASURABLE |
| Refusal Decision Quality | 1.000, n=28 |
| False discoveries caught | **3** — a 0.359 clustering artifact, a 0.6049 wrong-horizon artifact, and my own Day 8 measurement error |
| Lookahead bugs caught | **2** — the evidence adapter's retrieval-dated observations, and a stale `as_of` in the operating harness |
| Gaming routes refused | **2** — 13G relabelling, and subject-based gate widening |

The engine has found no alpha. It has become very good at proving it has not.

### RECOMMENDATION

**CONTINUE OPERATING.**

---

## 2026-07-31 — Day 12 · LONG-TERM OPERATION BEGINS

Architecture declared stable. One sanctioned operating action: wire the
validated industry adapter into the daily sweep. No other engineering.

### EXECUTIVE SUMMARY

| | |
|---|---|
| Overall / Refusal Decision Quality | **1.000** · n=28 · medium |
| Position Decision Quality | **UNMEASURABLE** — 0 positions opened (see below) |
| Paper trades opened / closed | **0 / 0** |
| Win rate · Total return · Expectancy · Profit factor | **UNMEASURABLE** (n=0) |
| Sharpe · Sortino · Max drawdown · Volatility | **UNMEASURABLE** (n=0) |
| Equity curve · SPY comparison · Alpha vs SPY | **UNMEASURABLE** (no equity curve) |
| Open positions | 0 |
| Signals beating baseline | **0 of 11** |
| Framework stability | **1** |

### THE MEASURED EFFECT OF WIRING THE ADAPTER

| | Day 6–11 | **Day 12** |
|---|---|---|
| evidence per company | 0–7 | **23–25** |
| **independent source found** | **0/28** | **28/28** |
| companies reaching the deepest gate | 0 | **3** |
| quality of readable companies | 0.27–0.575 | **0.9** |
| `no_outside_source` refusals | 2 | **0** |

```
blocked_by:  view_withheld 24 · no_market_evidence 3 · not_tradable 1
```

**`no_outside_source` has disappeared from the distribution.** It was the
terminal gate for every readable company for eleven days. Shopify, Olo and
Check Point now reach `no_market_evidence` — the deepest gate in the pipeline —
at quality **0.9**, the highest this project has recorded.

### WHY ZERO TRADES, STATED PRECISELY

Three companies are fully corroborated and stop at `no_market_evidence`. That
is **not** the adapter failing. It is the baseline momentum signal declining to
fire for those three today: the trailing move sits inside the noise floor, and
`momentum_evidence` returns an empty signal rather than a guess.

An empty signal is a real answer. The correct behaviour on a day when the only
wired signal has nothing to say is to open nothing.

**Zero trades, and the gate that produced them has moved from "we have no
independent evidence" to "we have complete evidence and no market view."** That
is the whole difference this cycle bought.

### EVIDENCE RETRIEVAL & QUALITY

- Industry documents retrieved across the sweep: **~25 per company**, all
  point-in-time filtered at `as_of`.
- **Independent-evidence yield: 28/28 (100%)** — from 0/28.
- Lookahead violations: **0**. Timestamp failures: **0** (documents without a
  readable date are dropped, never inferred).
- Company press releases syndicated through news feeds: correctly classified
  COMPANY and excluded from corroboration.

### CALIBRATION

Predicted confidence, observed outcomes, calibration curve, Brier score,
reliability: **UNMEASURABLE** — no position has resolved. Confidence is updated
only from resolved evidence, and there is none.

### SIGNAL PERFORMANCE / RESEARCH

11 hypotheses proposed, 11 retired, **0 active**, 0 beating baseline. No new
signals introduced, none revived, no parameters tuned. Best-powered negative
remains `event_drift.v1` at n_eff 400, accuracy 0.4912.

### HYPOTHESIS OUTCOMES

`view_withheld` is now the dominant refusal at **24/28** — the strategic layer
declining to form a view. That is the honest gate working, and it is the first
time in this project that the binding constraint on the live path is *reading
quality* rather than *evidence availability*.

### HIGHEST MEASURED BOTTLENECK

**Strategic-reading yield: 4/28 (14%).** With evidence at 100%, the constraint
has moved decisively upstream to whether a company's public material supports a
view at all. This is the bottleneck that Days 2–5 kept ranking third and that
measurement kept demoting; it is now genuinely first.

### ENGINEERING RECOMMENDATION

**CONTINUE OPERATING.**

Operation is not blocked. Evidence retrieval works at 100%, three companies are
fully corroborated, and the only thing between them and a position is a signal
that honestly has nothing to say today. Under the new constitutional bar —
prove operation is blocked AND that the blocker cannot be resolved by
continuing to operate — neither condition holds.

The next operating days should accumulate: more days give the baseline signal
more chances to fire on a corroborated company, and the first resolved position
is what turns Position Decision Quality, calibration, the equity curve and the
SPY comparison from UNMEASURABLE into data.

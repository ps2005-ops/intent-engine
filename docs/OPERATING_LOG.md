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

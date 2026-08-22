# Pre-registration — Day 18, learning acceleration

**Registered:** 2026-08-01, **before** any implementation. Measurements in §1
were taken first; everything below was written before code was changed.

---

## 1. The measured learning limitation

| measurement | value | source |
|---|---|---|
| companies evaluated per cycle | 28 | run records |
| strategic-view yield | **0.086** mean over 6 observations | `reports/funnel_history.json` |
| signal-evaluated per cycle | 2 | run records |
| signal-opportunity per cycle | 1 | run records |
| **paper positions ever opened** | **0** | run records |
| **resolved outcomes ever** | **0** | run records |
| live research cost per security | **20–28 s** | day-16 sweep 553 s/28, day-17 night 780 s/28 |
| live-position resolution latency | **21 calendar days** | `signal_opportunity.HORIZON_DAYS` |

### What actually blocks a position

`opportunity.classify` applies gate 2 — *a strategic reading must exist* —
**before** anything about the hypothesis is consulted. So **every** position,
of every kind, requires a per-company narrative derived from live web research.

Two consequences, both measured rather than assumed:

1. **It does not scale.** At 25 s/security, the prompt's target universe costs
   `500 × 25 s ≈ 3.5 h` per cycle, ~6.9 h/day across two cycles. A 06:30
   pre-market cycle cannot take three and a half hours.
2. **It is structurally unreachable for ETFs.** A sector or broad-market ETF has
   no company narrative to read. The gate cannot be satisfied by any amount of
   retrieval, so every ETF the mission asks for would terminate at
   `no_strategic_reading` forever.

### Therefore the prompt's premise is half right

Expanding the universe is **not** sufficient and, on the live evidence path, not
even feasible. The binding constraint is **the coupling of every position to a
company narrative**, which caps resolvable experiments at approximately zero and
makes the entire ETF universe inert.

And even if it were removed, the live path resolves one observation per position
per 21 days. **Replay resolves ten years in minutes.** For *expected information
gain per unit time*, replay dominates the live path by orders of magnitude —
which is why the primary intervention targets replay capacity, not trade count.

---

## 2. The intervention

**A price-behaviour strategy path that does not require a company narrative,
held to its own stricter, preregistered standards.**

This is *not* a weakening of an evidence gate, and the distinction is the whole
argument, so it is stated precisely:

* `corroboration.REQUIREMENTS["price_behaviour"]` **already** declares that a
  price claim needs no company evidence — *"A price/momentum claim asserts
  nothing about the business, so no company evidence can corroborate it."* That
  was written on Day 11, long before this cycle, and the reasoner has never been
  able to act on it.
* Requiring a *company strategic narrative* before a *mean-reversion* trade is a
  **category error**, not a safety margin. The evidence appropriate to a price
  claim is price data.
* The price path therefore carries requirements the narrative path does not:
  minimum bars, minimum liquidity, explicit transaction costs and slippage,
  point-in-time membership, and holdout protection.

**Nothing is removed from the narrative path.** Gates 2–4 apply unchanged to
every fundamental hypothesis kind. A test asserts this.

### The honest prior

`baseline_momentum.v1` was measured at **0.500** — no edge. Eleven hypotheses
have been proposed and eleven retired. **The expected result of this cycle is
that no price-behaviour strategy shows edge after costs.** That would be a
successful cycle: it converts an unmeasurable question into a measured negative.

This cycle buys **measurement capacity**, not profit.

---

## 3. Preregistered engineering prediction (cycle 8)

> **Prediction.** The binding constraint on valid learning is the narrative
> coupling, not universe size. Removing it for price-behaviour hypotheses, and
> adding bounded replay, will raise **resolvable experiments per operating day**
> from **0** to **at least 10³**, while **live** paper positions remain at or
> near **0**.

**Success condition.** ≥ 1,000 resolved replay observations produced in one
bounded pilot, with `n_effective` reported separately and `n_effective < n_raw`.

**Failure condition.** Any of: fewer than 1,000 resolved observations; `n_eff`
not separated from `n_raw`; any lookahead violation; any narrative-path gate
weakened; costs absent from any reported return.

**Explicitly NOT a success condition.** Number of trades, positive return, or
any strategy showing edge. A cycle in which every strategy is retired for
having no edge **satisfies** this prediction.

**Evaluation.** Immediately, from the pilot replay in this same cycle.

---

## 4. Strategy pre-registration

Three families only. Each must state an economic hypothesis that could be false.

| id | family | economic hypothesis | horizons | prior |
|---|---|---|---|---|
| `baseline_momentum.v1` | momentum | trailing direction persists | 21 | **measured 0.500 — no edge** |
| `mean_reversion.v1` | mean reversion | short-horizon overextension against a 20-day mean partially reverts | 3, 5, 10 | no edge expected |
| `volatility_breakout.v1` | breakout | a close outside a 20-day range marks a regime change that persists | 5, 10, 20 | no edge expected |

**Not implemented, and why:** `earnings_revision` and `sector_relative_strength`
require point-in-time analyst-estimate and sector-membership data this project
does not have. Implementing them would mean fabricating the input. Recorded as
`GATE 1 — DATA AVAILABILITY: FAIL`, visibly, rather than built on a proxy.

### Horizon assignment is preregistered, not chosen after outcomes

Each strategy declares its horizons **in its specification**, before any replay
runs. Selecting the best-performing horizon afterwards and presenting it as the
intended one is prohibited and asserted against by test.

---

## 5. Experimental design

* **Research window** ≤ 2022-12-31 — thresholds may be set here.
* **Validation window** 2023-01-01 → 2024-12-31.
* **Holdout** 2025-01-01 → present. **Untouched this cycle.** No threshold is
  set from it and no result is reported from it.
* Multiple testing: **Benjamini–Hochberg FDR at q = 0.10**, chosen because the
  question is "which of these families is worth continuing", where controlling
  the false-discovery *proportion* is the right error to control. Family-wise
  methods would be needlessly conservative across only three families;
  deflated-Sharpe machinery is not justified at this sample size.
* Effective sample size adjusts for overlapping holding windows, repeated
  securities, and correlated horizons. **No result may be promoted on `n_raw`.**

---

## 6. Costs

No transaction-cost model existed before this cycle. Preregistered defaults:

| component | value | rationale |
|---|---|---|
| commission | 0 bps | retail equities are commission-free |
| spread/slippage | **5 bps per side** | conservative for liquid large-cap; applied on entry *and* exit |
| total round trip | **10 bps** | subtracted from every reported return |

Every return in every report is **net**. A gross figure is never printed alone.

---

## 7. What this cycle will not claim

* No strategy is alpha. All start as `RESEARCH`; a challenger requires passing
  gates; a champion requires evidence that does not exist yet.
* The holdout is not consulted.
* Live paper positions are expected to stay near zero and that is not a failure.
* Replay observations are **not** independent and are never reported as if they
  were.

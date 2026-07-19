# Mechanism library — state inventory (FINAL, 12/12 episodes)

*Analysis/inventory only. No code, no accuracy claims — this is a map of
what the library contains, not a statement about predictive skill.*

**Curriculum COMPLETE.** All 3 batches (12 episodes) studied, reviewed, and
founder-approved: batch 1 merged 2026-07-19 (→20), batch 2 merged
2026-07-22-loop (→22), batch 3 merged 2026-07-19 loop 8 (→**23**). The
batched enum decision was made against this complete evidence base:
**KEEP FROZEN — all 5 candidates DEFERRED** (founder, 2026-07-19).

## 1. Current live library — 23 mechanisms

### Multi-instance (6) — the best-anchored mechanisms

| Mechanism | Tier | Instances |
|---|---|---|
| `credit_contagion` | well | 1907 (Knickerbocker), 1930 (Caldwell), 2008 (Lehman), 1997 (Asia) |
| `capex_overbuild` | well | 1873 (railroads), 2002 (fiber telecom) |
| `supply_shock_propagation` | well | 1973 (OAPEC), 2021 (semiconductors) |
| `reflexive_bubble` | plausible | 2000 (dot-com), 1990 (Japan asset bubble) |
| `input_cost_inflation_passthrough` | well | 1973 (OAPEC), 2022 (post-pandemic CPI ~9.1%) |
| `policy_tightening_demand_collapse` | well | 1982 (Volcker), 2022 (~525bp Fed hiking cycle) |

`credit_contagion` carries four instances across three centuries — the
strongest evidentiary base in the library.

### Single-instance (17) — real but one anchor each

`prisoners_dilemma_price_war` (1990), `regulatory_capture_race` (2018),
`platform_envelopment` (1998), `ally_drawn_into_linked_conflict` (1914),
`winners_curse_acquisition` (2000), `debt_fueled_capacity_race` (2016),
`leverage_cycle_bust` (2008), `margin_collateral_spiral` (2021),
`bank_run_maturity_mismatch` (2023), `carry_trade_unwind` (2024),
`monetary_tightening_lag` (1982), `sovereign_debt_doom_loop` (2011),
`money_market_contagion` (2008), `debt_deflation_spiral` (1933),
`mechanical_feedback_liquidation` (1987), `crowded_trade_deleveraging`
(1998 LTCM), `exogenous_activity_halt` (2020 COVID).

Tiers: 19 well_documented, 4 plausible, 0 speculative.

## 2. The 12-episode curriculum — final disposition

| # | Episode | Outcome |
|---|---|---|
| 1–4 | 1907, 1929–33, 1973–74, 1980–82 | batch 1: +3 new, +3 enrich |
| 5 | 1987 Black Monday | batch 2: NEW `mechanical_feedback_liquidation` (collision accepted) |
| 6 | Japan 1990 | batch 2: ENRICH `reflexive_bubble` |
| 7 | Asia 1997 | batch 2: ENRICH `credit_contagion`; PARK `currency_peg_break_contagion` |
| 8 | LTCM 1998 | batch 2: NEW `crowded_trade_deleveraging` |
| 9 | Dot-com 2000 | batch 3: ALREADY COVERED (`reflexive_bubble`, `winners_curse_acquisition`, `capex_overbuild`) |
| 10 | GFC 2007–09 | batch 3: ALREADY COVERED (4 mechanisms); PARK `securitized_credit_opacity` |
| 11 | COVID 2020 | batch 3: NEW `exogenous_activity_halt` (collision ratified) |
| 12 | 2021–22 inflation/hiking | batch 3: ENRICH `input_cost_inflation_passthrough` + `policy_tightening_demand_collapse` |

## 3. Parked mechanisms (inexpressible in the frozen enum)

| Episode | Parked mechanism | Blocking gap |
|---|---|---|
| Asia 1997 (batch 2) | `currency_peg_break_contagion` | no currency-peg condition |
| GFC 2007–09 (batch 3) | `securitized_credit_opacity` | expressible trigger set identical to `money_market_contagion`; needs `opaque_securitized_exposure` |

## 4. The accepted drawdown_gt_20pct dual-match class (3 members)

`margin_collateral_spiral` (2021), `mechanical_feedback_liquidation`
(1987), `exogenous_activity_halt` (2020) share the trigger set
{drawdown_gt_20pct}. All three were individually collision-flagged and
individually founder-ratified: distinct causal shapes (margin spiral /
mechanical rule-based selling / exogenous stop shock), and multi-match on
a >20% drawdown is treated as correct behavior, not a bug.

## 5. Enum-candidate list — COMPLETE at 5, decision made: ALL DEFERRED

Founder decision 2026-07-19 (post-batch-3, against the full 12-episode
evidence base): **enum stays frozen; no widening.** The list remains on
record for a future revisit; any widening = founder sign-off + full
Task 3 gate rerun.

| # | Candidate condition | What it would unlock | Surfaced by |
|---|---|---|---|
| 1 | `falling_price_level` (deflation) | separates `debt_deflation_spiral` from `leverage_cycle_bust` | batch 1 (Great Depression) |
| 2 | `outside_liquidity_backstop_perimeter` | 1907-trusts / 2008-shadow-banks "beyond the lender-of-last-resort" pattern | batch 1 (Panic of 1907) |
| 3 | `pegged_currency_with_external_short_term_debt` | un-parks `currency_peg_break_contagion` (Asia '97; also 1992 ERM) | batch 2 (Asian crisis) |
| 4 | `collateral_value_dependence` | Japan land-collateral + 2008 housing-collateral loops as first-class | batch 2 (Japan), reinforced by batch 3 (GFC) |
| 5 | `opaque_securitized_exposure` | un-parks `securitized_credit_opacity`, distinguishes it from `money_market_contagion` | batch 3 (GFC) |

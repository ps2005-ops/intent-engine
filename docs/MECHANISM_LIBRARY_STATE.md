# Mechanism library — state inventory

*Analysis/inventory only. No code, no accuracy claims — this is a map of
what the library contains, not a statement about predictive skill.*

> **⚠️ INTERIM — the curriculum is NOT complete.** The instruction assumed
> all 3 batches (12 episodes) were studied. As of this writing only
> **batch 1 is merged (20 entries)** and **batch 2 is drafted-but-not-
> merged** (awaiting founder verdict; `mechanisms.json` untouched);
> **batch 3 (episodes 9–12: dot-com 2000, GFC 2007–09, COVID 2020,
> 2021–22 hiking) has NOT started** — it is gated on batch-2 feedback,
> which was unfilled this loop. So this doc covers **8 of 12 episodes**.
> The final version (the one meant to inform the batched enum decision,
> which is itself deferred until after batch 3) will be completed once
> batch 3 lands. Everything below is accurate to the current state.

## 1. Current live library — 20 mechanisms (batch 1 merged)

### Multi-instance (3) — the best-anchored mechanisms

| Mechanism | Tier | Instances |
|---|---|---|
| `credit_contagion` | well | 1907 (Knickerbocker), 1930 (Caldwell), 2008 (Lehman) |
| `capex_overbuild` | well | 1873 (railroads), 2002 (fiber telecom) |
| `supply_shock_propagation` | well | 1973 (OAPEC), 2021 (semiconductors) |

These three carry cross-century precedent — the strongest evidentiary base
in the library.

### Single-instance (17) — real but one anchor each

`prisoners_dilemma_price_war` (1990), `regulatory_capture_race` (2018),
`platform_envelopment` (1998), `ally_drawn_into_linked_conflict` (1914),
`winners_curse_acquisition` (2000), `debt_fueled_capacity_race` (2016),
`leverage_cycle_bust` (2008), `margin_collateral_spiral` (2021),
`bank_run_maturity_mismatch` (2023), `carry_trade_unwind` (2024),
`reflexive_bubble` (2000), `monetary_tightening_lag` (1982),
`sovereign_debt_doom_loop` (2011), `money_market_contagion` (2008),
`debt_deflation_spiral` (1933), `input_cost_inflation_passthrough` (1973),
`policy_tightening_demand_collapse` (1982).

Tiers: 17 well_documented, 3 plausible (`prisoners_dilemma_price_war`,
`regulatory_capture_race`, `reflexive_bubble`), 0 speculative.

## 2. Batch 2 (drafted, PENDING merge — not in the live library yet)

- NEW `mechanical_feedback_liquidation` (1987 Black Monday) — **collision-
  flagged**: identical trigger set {drawdown_gt_20pct} to
  `margin_collateral_spiral` (dual-match; your call, same class as
  batch 1's accepted debt_deflation_spiral).
- NEW `crowded_trade_deleveraging` (LTCM 1998) — clean distinct set.
- ENRICH `reflexive_bubble` → +Japan 1990 (would make it multi-instance).
- ENRICH `credit_contagion` → +Asia 1997 (would give it a 4th instance).
- PARKED `currency_peg_break_contagion` (Asia 1997) — inexpressible in the
  frozen enum.
- 2 citations (LTCM, Japan) still PENDING-MAC-VERIFICATION.

If batch 2 merges as-is: 22 mechanisms, 5 multi-instance.

## 3. Episodes that forced a park (mechanism could not be expressed)

| Episode | Parked mechanism | Blocking gap |
|---|---|---|
| Asia 1997 (batch 2) | `currency_peg_break_contagion` | no currency-peg condition in enum |

Batch-1 episodes forced no mechanism parks (all expressible, with noted
precision loss folded into existing entries). Batch 3 is expected to add
at least one (GFC housing-collateral loop).

## 4. Standing enum-candidate list (4, all DEFERRED until after batch 3)

The `TriggerCondition` enum is frozen; widening requires founder sign-off
+ a full Task 3 gate rerun. Candidates accumulated across batches:

| # | Candidate condition | What it would unlock | Surfaced by |
|---|---|---|---|
| 1 | `falling_price_level` (deflation) | separates `debt_deflation_spiral` from `leverage_cycle_bust` (currently collide on trigger set) | batch 1 (Great Depression) |
| 2 | `outside_liquidity_backstop_perimeter` | the 1907-trusts / 2008-shadow-banks "beyond the lender-of-last-resort" pattern as a first-class condition | batch 1 (Panic of 1907) |
| 3 | `pegged_currency_with_external_short_term_debt` | un-parks `currency_peg_break_contagion` (Asia '97; also 1992 ERM) | batch 2 (Asian crisis) |
| 4 | `collateral_value_dependence` | Japan land-collateral loop + 2008 housing-collateral loop as first-class, not folded into `reflexive_bubble`/`leverage_cycle_bust` | batch 2 (Japan); expected reinforced by batch 3 (GFC) |

**Observation for the batched decision (not a recommendation):** candidates
1 and 4 each resolve a *known trigger-set collision* (debt-deflation vs
leverage-cycle; and the batch-2 mechanical-feedback vs margin-spiral
collision would also benefit from a distinguishing condition). Candidates
2 and 3 un-park otherwise-inexpressible mechanisms. Batch 3 is likely to
add weight to #4 (GFC) and possibly a securitization/opacity candidate —
which is exactly why the enum decision was deferred until the full
curriculum is visible.

## 5. What completing batch 3 would add to this map

The final version of this doc will add episodes 9–12, resolve whether
`reflexive_bubble`/`capex_overbuild` gain their dot-com-era co-instances,
record GFC's expected enum park, and present the *complete* candidate list
so the batched enum decision can be made against the whole 12-episode
evidence base rather than 8/12 of it.

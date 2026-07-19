# Mechanism library — Batch 3 review sheet (episodes 9–12, FINAL) — AWAITING APPROVAL

*2026-07-22, overnight loop 7. Unblocked by the batch-2 merge landing this
loop. `mechanisms.json` UNTOUCHED by this sheet (still 22; batch-3 merge
waits for your approval, one data-file commit then). This is the last of
the 12-episode curriculum. Binding batch-1/2 quality bar applied
(dual-match-with-distinct-shape accepted; strict citations; enum frozen).*

## Spend

3 citation fetches this loop (COVID/NBER ✓, GFC/Fed-History ✓ [reused],
2 Fed-History COVID URLs 404'd — their coverage stops earlier), 0 model
calls. Two enrichment citations (2021-22 CPI, 2022 hiking) routed to
`citation_check.sh` as PENDING-MAC (data landing pages; need a real 200
on the Mac before merge), same discipline as batch 2.

## The honest headline: episodes 9–12 are mostly ALREADY COVERED

The library already documents the two biggest episodes well, so batch 3 is
enrichment-and-park-heavy, not new-mechanism-heavy — which is the correct,
non-padded outcome:

- **Ep 9 — dot-com 2000: ALREADY COVERED.** `reflexive_bubble` (2000),
  `winners_curse_acquisition` (AOL–Time Warner 2000), `capex_overbuild`
  (fiber 2002) already capture the bubble, the value-destroying M&A, and
  the overbuild. No new entry forced.
- **Ep 10 — GFC 2007–09: ALREADY COVERED + one park.** `credit_contagion`
  (Lehman 2008), `leverage_cycle_bust` (2008), `money_market_contagion`
  (Reserve Primary 2008), `bank_run_maturity_mismatch` already capture the
  contagion, leverage unwind, and funding runs. **PARKED mechanism
  `securitized_credit_opacity`** — the GFC's distinctive feature
  (opacity of structured/securitized credit + ratings failure → mispriced
  systemic risk) CANNOT be honestly distinguished in the frozen enum: its
  only expressible trigger set {interconnected_counterparty_exposure,
  credit_spreads_elevated} is IDENTICAL to `money_market_contagion`. This
  is the GFC enum candidate you anticipated — recorded, mechanism parked,
  enum NOT widened.

## Proposed changes (1 new, 2 enrichments, 1 park)

### Ep 11 — COVID 2020 → NEW `exogenous_activity_halt`
External non-financial shock forces a simultaneous economy-wide activity
stop → demand+supply collapse together → liquidity scramble + sharp
drawdown → path set by the external event + policy response, not internal
leverage.
- Source (fetched ✓): NBER Business Cycle Dating — peak Feb 2020, trough
  Apr 2020; "so great and so widely diffused… even if quite brief."
- ⚠️ **COLLISION FLAG (your call, same class accepted in batches 1 & 2)**:
  trigger set {drawdown_gt_20pct} is identical to
  `mechanical_feedback_liquidation` (1987) and `margin_collateral_spiral`
  (2021). Causal shapes are genuinely distinct — an exogenous stop shock is
  not mechanical selling and not a margin spiral — and dual-match on a
  >20% drawdown is arguably correct. Flagged for explicit ratification.

### Ep 12 — 2021-22 inflation/hiking → 2 enrichments (modern instances)
- `input_cost_inflation_passthrough` += 2021-22 post-pandemic inflation
  (supply-chain + energy passthrough; US CPI ~9.1% YoY Jun-2022). Citation
  PENDING-MAC (BLS CPI).
- `policy_tightening_demand_collapse` += 2022-23 fastest-in-four-decades
  Fed hiking cycle (~525bp). Citation PENDING-MAC (Fed open-market page).
- Both make existing single-instance mechanisms multi-instance with a
  modern anchor — the same enrichment logic accepted in batches 1-2.

## NEEDS-APPROVAL condition candidates (recorded, NOT added — enum frozen)

Running list now **5**, all DEFERRED (your standing decision: enum
decision batched until after batch 3 — which is now, so this is the
complete list for that decision):

1. `falling_price_level` (deflation) — batch 1; separates
   `debt_deflation_spiral` from `leverage_cycle_bust`.
2. `outside_liquidity_backstop_perimeter` — batch 1; 1907-trusts /
   2008-shadow-banks.
3. `pegged_currency_with_external_short_term_debt` — batch 2; un-parks
   `currency_peg_break_contagion` (Asia '97).
4. `collateral_value_dependence` — batch 2; Japan land + 2008 housing
   collateral loops.
5. `opaque_securitized_exposure` — batch 3; un-parks
   `securitized_credit_opacity` (GFC), distinguishes it from
   `money_market_contagion`.

## Approval options
- **Approve as-is** → one data-file commit (1 new + 2 enrichments → 23
  entries), bar-(e) prompt byte-identity assertion, suite green with
  explicit exit-code check; `securitized_credit_opacity` stays parked;
  2 PENDING-MAC citations cleared via `citation_check.sh` first.
- **Approve minus exogenous_activity_halt** (if the drawdown collision
  bothers you) → it folds into nothing; COVID would be uncaptured.
- This COMPLETES the 12-episode curriculum. On approval, I update
  `docs/MECHANISM_LIBRARY_STATE.md` to the final 12/12 map, and the
  5-candidate enum decision is ready for you to make against the whole
  evidence base.

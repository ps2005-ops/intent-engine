# Mechanism library — Batch 2 review sheet (episodes 5–8) — AWAITING APPROVAL

*2026-07-19/20 overnight loop 2. `mechanisms.json` UNTOUCHED (still 20
entries). Draft entries machine-validated in
`docs/library_batch2_draft_entries.json`; merge waits for your approval,
one data-file commit then. Your binding batch-1 acceptance (dual-match
with distinct causal shapes is correct; strict citation bar; enum frozen)
was applied as the quality bar throughout.*

## Spend (vs ≤10 searches + ≤4 model calls per episode)

7 citation fetches across 4 episodes (~1.75/episode), 0 model calls —
well under budget. Two sources could not be verified FROM THE SANDBOX and
are routed to `citation_check.sh` per your amendment 2 (sandbox failure ≠
citation failure): LTCM (the Fed speech URL returned an empty body) and
Japan (the IMF paper returned HTTP 200 `application/pdf` but too large to
display). Both are marked `PENDING-MAC-VERIFICATION` in the entries and
below.

## Proposed changes (2 new mechanisms, 2 enrichments, 1 parked)

### Episode 5 — Black Monday 1987 → NEW `mechanical_feedback_liquidation`
Portfolio-insurance rules mechanically selling into declines → self-
reinforcing downdraft → liquidity vacuum (DJIA −22.6% in one session).
- Source (fetched ✓, title verified "Stock Market Crash of 1987 |
  Federal Reserve History").
- ⚠️ **COLLISION FLAG (your call, same class you already accepted in
  batch 1)**: trigger set {drawdown_gt_20pct} is IDENTICAL to
  `margin_collateral_spiral` (Archegos 2021). Causal shapes are distinct
  — pre-programmed selling rules vs. margin-call-forced collateral
  liquidation — and dual-match on a >20% drawdown is arguably correct.
  Flagged for the same reason `debt_deflation_spiral` was; approve or
  fold-into-enrichment as you prefer.

### Episode 6 — Japan bubble ~1990 → enrich `reflexive_bubble`
Equity/land valuations detached from fundamentals via a self-reinforcing
collateral-credit loop; Nikkei peak end-1989, multi-year collapse.
- Source: IMF WP/09/241 — **PENDING-MAC-VERIFICATION** (oversized in
  sandbox; URL confirmed to return application/pdf 200).
- **Why enrichment, not new**: the expressible core (valuation
  disconnected from fundamentals) is exactly `reflexive_bubble`; the
  distinctive Japan features (land-as-collateral, zombie-bank
  persistence) are NOT expressible in the frozen enum — see NEEDS-APPROVAL.

### Episode 7 — Asian crisis 1997 → enrich `credit_contagion` + PARK a mechanism
- Enrichment: `credit_contagion` gains the 1997 regional-contagion
  instance (foreign creditors pulling back across economies with similar
  vulnerabilities). Source (fetched ✓, title verified "Asian Financial
  Crisis | Federal Reserve History").
- **PARKED mechanism `currency_peg_break_contagion`** — the crisis's true
  distinguishing mechanism (a currency peg + short-term foreign-currency
  debt → peg breaks → local-currency debt burden explodes → insolvency +
  contagion) CANNOT be honestly expressed without a peg condition the
  enum doesn't have. Per your instruction I recorded the candidate,
  parked the mechanism, and did NOT widen the enum. Candidate:
  `pegged_currency_with_external_short_term_debt` → NEEDS-APPROVAL.

### Episode 8 — LTCM 1998 → NEW `crowded_trade_deleveraging`
Many leveraged players in the same convergence trades, shared
counterparties → simultaneous forced unwind → liquidity evaporates →
losses amplify → coordinated recapitalization halts it.
- Triggers {interconnected_counterparty_exposure, debt_financed_expansion}
  — distinct set, NO collision (checked: distinct from `carry_trade_unwind`
  and `leverage_cycle_bust`).
- Source: President's Working Group report (1999) —
  **PENDING-MAC-VERIFICATION** (the Fed primary-speech URL returned an
  empty body from the sandbox).

## NEEDS-APPROVAL condition candidates (recorded, NOT added — enum frozen)

Batch-2 additions to the running list (batch-1 candidates
`falling_price_level`, `outside_liquidity_backstop_perimeter` still
deferred until after batch 3, per decision):
3. `pegged_currency_with_external_short_term_debt` — unlocks the parked
   `currency_peg_break_contagion` (Asia '97, and applies to 1992 ERM).
4. `collateral_value_dependence` — would let Japan's land-collateral loop
   and 2008's housing-collateral loop be first-class rather than folded
   into `reflexive_bubble`/`leverage_cycle_bust`.

Any enum widening = your sign-off + full Task 3 gate rerun.

## Approval options
- **Approve as-is** → one data-file commit (2 new + 2 enrichments, 22
  total), with the bar-(e) prompt byte-identity assertion and suite
  green; `currency_peg_break_contagion` stays parked.
- **Approve minus mechanical_feedback_liquidation** (if the drawdown
  collision bothers you) → it folds into a `margin_collateral_spiral`
  enrichment instead.
- Batch 3 (dot-com, GFC, COVID, 2021-22) not started, per protocol.

## Two Mac verifications before/at merge (citation_check.sh)
`sh citation_check.sh` now also checks the LTCM PWG report and the IMF
Japan paper URLs. If either returns non-200 on the Mac, that entry's
citation is swapped before merge — flag me and I'll fix forward.

# Mechanism library — Batch 1 review sheet (episodes 1–4) — AWAITING YOUR APPROVAL

*2026-07-19 overnight loop. NO data-file change has been made —
`core/data/mechanisms.json` is untouched. The machine-validated draft
entries live in `docs/library_batch1_draft_entries.json`; on your approval
they merge in ONE data-file commit (with the enum-freeze assertion test).
Your feedback here binds batches 2 and 3. Episodes 5–8 NOT started, per
instruction.*

## Spend (vs ≤10 searches + ≤4 model calls per episode)

6 citation fetches total (~1.5/episode), 0 live model calls (drafting done
in-session). All six source URLs fetched successfully from the sandbox —
titles recorded below, so `citation_check.sh` ships as optional
re-verification only; nothing is pending on it.

## Proposed changes (3 new mechanisms, 3 instance enrichments)

### Episode 1 — Panic of 1907 → enrich `credit_contagion`
New instance: Knickerbocker Trust run severing trust-company call-loan
liquidity to NYSE brokers; call money 9.5%→100% annualized.
- Source (fetched ✓): Moen & Tallman, *The Panic of 1907*, Federal Reserve
  History — title verified: "The Panic of 1907 | Federal Reserve History".
- **Why enrichment, not a new mechanism**: the propagation is
  counterparty-interconnection contagion — same causal family as the
  existing entry's Lehman instance; the sharpest 1907-specific feature
  (trusts sat OUTSIDE the Clearing House's lender-of-last-resort
  perimeter) is not expressible in the closed enum — see NEEDS-APPROVAL.

### Episode 2 — Great Depression 1929–33 → NEW `debt_deflation_spiral` + enrich `credit_contagion`
- New mechanism (well_documented): Fisher's nine-factor chain — liquidation
  → deposit contraction → price-level fall → REAL debt burden rises →
  self-defeating liquidation ("the more the debtors pay, the more they
  owe"). Instance: US 1929-33, Fisher's own 20%-nominal/40%-real
  computation.
  - Sources (fetched ✓): Fisher 1933 Econometrica via FRASER (full text
    verified: "THE DEBT-DEFLATION THEORY OF GREAT DEPRESSIONS BY IRVING
    FISHER"); Richardson, *Banking Panics of 1930-31*, Fed History (title
    verified).
  - ⚠️ **FLAG for your distinctness judgment (bar c)**: trigger set
    {debt_financed_expansion, drawdown_gt_20pct} is IDENTICAL to existing
    `leverage_cycle_bust`. Causal shapes are genuinely different
    (price-level feedback loop vs. leverage unwind), and the matcher can
    return both — but the automated check flagged the overlap and the
    call is yours. The enum's missing deflation condition is why the
    trigger sets collide — see NEEDS-APPROVAL.
- Enrichment: `credit_contagion` gains the Caldwell & Co. correspondent-
  reserve cascade (Nov 1930) — considered a new mechanism, judged an
  instance of interconnection contagion instead (reserve pyramid =
  correspondent-network interconnection).

### Episode 3 — 1973–74 oil shock → NEW `input_cost_inflation_passthrough` + enrich `supply_shock_propagation`
- New mechanism (well_documented): concentrated supplier of an
  economy-wide input → price shock → wholesale→consumer passthrough →
  expectations entrenchment → stagflation. Triggers:
  {concentrated_supplier_base, inflation_rising} — distinct set, no
  overlap flags.
  - Sources (fetched ✓): Corbett, *Oil Shock of 1973-74*, Fed History
    (title verified; $2.90→$11.65 figures from this essay); Blinder &
    Rudd, NBER w14563 (title verified: "The Supply-Shock Explanation of
    the Great Stagflation Revisited").
- Enrichment: `supply_shock_propagation` gains the 1973 OAPEC embargo
  instance (previously its only instance was the 2021 chip shortage —
  a 20th-century anchor materially strengthens a well_documented tier).

### Episode 4 — Volcker disinflation → NEW `policy_tightening_demand_collapse`
- New mechanism (well_documented): entrenched inflation → aggressive,
  credibility-driven tightening held through rising unemployment → curve
  inversion → rate-sensitive sector collapse → lagged disinflation →
  expectations break. Triggers: {inflation_rising, curve_inverted,
  unemployment_momentum_triggered} — distinct set.
  - Sources (fetched ✓): Sablik, *Recession of 1981-82*, Fed History
    (title verified; 20% funds rate / ~11% unemployment / 5% Oct-1982
    figures from this essay); Goodfriend & King, JME 2005 (cited within
    the fetched essay's bibliography).
  - Relation to existing `monetary_tightening_lag` (which already cites
    Volcker): different trigger set and different causal focus (policy
    transmission LAG vs. deliberate credibility-restoring demand
    collapse). Both can legitimately match a tightening regime; noted
    for your judgment.

## NEEDS-APPROVAL condition candidates (recorded, NOT added — enum frozen)

1. `falling_price_level` (deflation) — debt-deflation's true
   distinguishing trigger; its absence is why the ep-2 trigger sets
   collide. Adding it = your sign-off + full Task 3 gate rerun.
2. `outside_liquidity_backstop_perimeter` — 1907 trusts / 2008 shadow
   banks: intermediaries beyond the lender-of-last-resort's reach. Same
   unlock cost.

Neither mechanism was parked — both are expressible (with noted precision
loss) inside the existing enum.

## Approval options

- **Approve as-is** → one data-file commit (3 new + 3 enrichments), with
  a byte-identity assertion on the extraction prompt before/after merge
  (bar e) and suite green.
- **Approve minus debt_deflation_spiral** (if the trigger-set collision
  bothers you more than the causal distinction) → it parks pending the
  `falling_price_level` enum decision.
- Any feedback binds batches 2 (Black Monday, Japan, Asia '97, LTCM) and
  3 (dot-com, GFC, COVID, 2021-22).

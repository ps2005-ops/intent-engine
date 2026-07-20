# Synthetic-world reasoning eval — OFFLINE leg (matcher-level)

*Generated 2026-07-20, seed 20260719, 89 worlds (69 single, 12 mixed, 8 control). Deterministic; 0 model calls; all leakage walls enforced at generation time.*

SCOPE (recorded so it cannot be misquoted): this is a causal-reasoning diagnostic on constructed fictional worlds. It is NOT a forward-market accuracy measure, NOT calibration evidence, NOT a marketing claim, and it changes no prompt, enum, or library data. Fictional worlds cannot be memorized; that is the point of the design.

## What the offline leg does and does not show

Planting a mechanism's exact trigger set and running the
deterministic matcher recovers that mechanism BY CONSTRUCTION —
the interesting quantity is not the recovery rate but the SIZE of
the tied top class: how sharply the frozen enum can discriminate
the constructed truth from its neighbors on its own best evidence.
The reasoning test proper is the LIVE leg (narrative -> extraction
-> matcher), which is staged for the Mac.

## Results by world type

- **control** (n=8): constructed truth recovered in 8/8; uniquely (tied with nothing) in 8/8; top-tier size distribution {0: 8}.
- **mixed** (n=12): constructed truth recovered in 12/12; uniquely (tied with nothing) in 3/12; top-tier size distribution {1: 4, 2: 3, 3: 1, 4: 2, 6: 1, 8: 1}.
- **single** (n=69): constructed truth recovered in 69/69; uniquely (tied with nothing) in 33/69; top-tier size distribution {1: 33, 2: 12, 3: 9, 5: 9, 6: 6}.

## Enum expressiveness map (the extracted learning)

Uniquely identifiable mechanisms — 11/23: `ally_drawn_into_linked_conflict`, `bank_run_maturity_mismatch`, `capex_overbuild`, `crowded_trade_deleveraging`, `debt_fueled_capacity_race`, `input_cost_inflation_passthrough`, `platform_envelopment`, `policy_tightening_demand_collapse`, `prisoners_dilemma_price_war`, `regulatory_capture_race`, `supply_shock_propagation`.

Tied classes (the frozen enum cannot separate these on the tied
members' own best evidence; supersets tie because overlap is
capped by what is observed):

- {`bank_run_maturity_mismatch`, `carry_trade_unwind`, `credit_contagion`, `crowded_trade_deleveraging`, `money_market_contagion`, `sovereign_debt_doom_loop`}
- {`bank_run_maturity_mismatch`, `monetary_tightening_lag`, `policy_tightening_demand_collapse`}
- {`capex_overbuild`, `reflexive_bubble`, `winners_curse_acquisition`}
- {`debt_deflation_spiral`, `exogenous_activity_halt`, `leverage_cycle_bust`, `margin_collateral_spiral`, `mechanical_feedback_liquidation`}
- {`debt_deflation_spiral`, `leverage_cycle_bust`}
- {`money_market_contagion`, `sovereign_debt_doom_loop`}

Relevance to the (deferred) enum decision — evidence, not a
recommendation: candidate #1 (`falling_price_level`) would split
the leverage/deflation tie; #4 (`collateral_value_dependence`) and
#5 (`opaque_securitized_exposure`) would each split a documented
credit-side tie; the drawdown trio stays a deliberate dual-match
class per the founder's ratified decisions.

## Live leg

STAGED, not run (sandbox has no Anthropic egress). Command:
`python scripts/run_synthetic_world_eval.py --live` on the Mac.
Budget: 89 calls ≈ $1.78 at the standing over-estimate; capped at 100 calls; prompt sha256 asserted before any call.

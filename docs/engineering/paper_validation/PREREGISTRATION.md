# Paper validation: preregistration

The machine-readable declaration is `PROTOCOL` in
`src/intent_engine/paper_validation/protocol.py`. Its sha256 is

    d6483796ba0e550ecfa4495fc956709f5d8502aac6cf4c49854e6a90a7410dc4

That hash is written into every replay summary and every forward record
(`protocol_hash`), and `protocol.assert_unchanged` refuses to re-read a
result against a different declaration. A change needs a new protocol
version, not an edit.

## What was fixed before the first replay result existed

* Decision protocol: every 21 SPY sessions, decide at the close, enter at
  the next open, exit at the open 21 sessions after entry. Windows are
  contiguous and never overlap.
* Target: sign of the excess return (ETFs vs cash at fed funds act/360;
  companies vs SPY). `probability` = P(excess > 0).
* Costs: `market.costs` cost.v1 (5 bps per side, 0 commission) on the change
  in position; 30 bps/yr borrow on short legs; company pairs pay both legs.
* Rules state the engine's own `market.signals.BASELINE_PROBABILITY` (0.55)
  in their direction, so Brier compares directions on equal terms.
* Every policy and its parameters (see `PROTOCOL["policies"]`), the macro
  feature list (`macro.MACRO_FEATURES`), the model (L2 logistic, the
  `econ.forecast` defaults: L2 1.0, 400 epochs, lr 0.08, min 40 rows), the
  per-family fit, the yearly refit, the 0.02 trade margin.
* Metrics: circular block bootstrap over decision dates (block 6, 2000
  draws, seed 20261109), Holm within each comparison family, 60 periods
  minimum for any claim, 24 for a regime cell.
* Superiority claim: positive Brier skill vs point-in-time climatology AND a
  positive net Sharpe difference vs the benchmark, each with a 95% CI
  excluding zero and a Holm-adjusted p < 0.05, over >= 60 periods. Win rate
  is not a criterion.
* Forward promotion bar: >= 36 resolved forward decision dates, Brier skill
  CI low > 0, Sharpe-difference CI low > 0, drawdown no worse than the
  benchmark's by more than 5 points, calibration slope in [0.5, 1.5], Holm
  p < 0.05, and a human decision. The learning loop may only propose.

## What changed after the first replay, and why (disclosed, not hidden)

No policy, parameter, threshold, feature or cost changed after a result was
seen. Four ANALYSIS choices did, each because the first output was wrong
in a way the output itself revealed:

1. **Company benchmark: cash -> buy-and-hold (relative).** Against zero,
   `logit_A` read as significant (Sharpe +0.72, Holm p 0.004) while its
   Brier skill was negative: it was collecting the drift of a
   survivorship-biased list (relative buy-and-hold earns Sharpe +1.31).
   The change made every company result LESS favourable. Zero is still
   reported beside it (`vs_zero`).
2. **Paired mean-return differences added for controls.** A Sharpe
   difference between two losing books rewards volatility: the econ arm
   "beat" its permutation control by +0.19 Sharpe with an annual return
   difference of -0.03%.
3. **Calibration-slope estimator damped.** The undamped Newton step
   diverged to values like -2e7 on near-degenerate probability spreads; it
   now returns None when it does not converge.
4. **Gross Sharpe reported beside net**, so cost drag and signal separate.

The L2 sweep in the report is a post-hoc diagnostic and is labelled so; no
penalty it explores feeds back into any policy.

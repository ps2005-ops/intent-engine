# Learning acceleration — activity is not learning

*Canonical. Every number here is DERIVED by `scripts/close_v3.py` from the
canonical ledgers and re-checked by `reconcile()`, which refuses a
disagreement. Nothing on this page is a maintained counter.*

---

## Why the two are separated

A cycle that re-reads eighty pages and changes nothing has been busy, not
productive. Putting the arrival count at the top of a dashboard teaches its
reader to mistake the first for the second, so evidence velocity and
knowledge velocity are reported as different quantities and never summed.

## The reconciliation rule

A dashboard that maintains counters beside the ledger it describes is how a
report and its source come to disagree without either being wrong on its own
terms. `reconcile()` re-derives every displayed count from the canonical
record:

- `real_open` against the forward ledger folded by id
- `material` against the decision-value rows
- `PRE_CALIBRATION` against the resolution count
- the damage vocabulary against the detectors that reference it

`tests/test_v3_closure_ledgers.py` pins that each of those checks can fail.

## The economic dimension ledger

A dimension can be LIVE and useless. LIVE counts a series being readable,
which is a fact about acquisition rather than about value — so the ledger
separates them, and the coverage number cannot be inflated with
infrastructure nothing decides on.

| value | n |
|---|---|
| BLOCKED | 6 |
| LIVE_CONTEXT_ONLY | 6 |
| LIVE_DECISION_RELEVANT | 3 |
| LIVE_UNPROVEN_VALUE | 2 |

| dimension | value | acquisition | company consumers | deltas |
|---|---|---|---|---|
| commodities | BLOCKED | BLOCKED | 0 | 0 |
| fx | BLOCKED | BLOCKED | 0 | 0 |
| liquidity | BLOCKED | BLOCKED | 0 | 0 |
| positioning | BLOCKED | BLOCKED | 0 | 0 |
| real_rates | BLOCKED | BLOCKED | 0 | 0 |
| volatility | BLOCKED | BLOCKED | 0 | 0 |
| credit | LIVE_CONTEXT_ONLY | LIVE | 3 | 0 |
| growth | LIVE_CONTEXT_ONLY | LIVE | 6 | 0 |
| inflation | LIVE_CONTEXT_ONLY | LIVE | 1 | 0 |
| labour | LIVE_CONTEXT_ONLY | LIVE | 4 | 0 |
| policy_rates | LIVE_CONTEXT_ONLY | LIVE | 3 | 0 |
| risk_appetite | LIVE_CONTEXT_ONLY | LIVE | 3 | 0 |
| funding | LIVE_DECISION_RELEVANT | LIVE | 1 | 1 |
| housing | LIVE_DECISION_RELEVANT | LIVE | 3 | 3 |
| yield_curve | LIVE_DECISION_RELEVANT | LIVE | 1 | 1 |
| household_balance_sheet | LIVE_UNPROVEN_VALUE | LIVE | 0 | 0 |
| sentiment | LIVE_UNPROVEN_VALUE | LIVE | 0 | 0 |

The blocked dimensions stay in the denominator. Removing them would raise
coverage by narrowing the question.

## Forward and decision counts

| | |
|---|---|
| real expectations open | 13 |
| real resolved | 0 |
| calibration | **PRE_CALIBRATION** |
| relations evaluated | 6 |
| not tested — driver did not move | 5 |
| not tested — lag pending | 0 |
| A/B cases | 60 |
| material / attributed | 25 / 25 |
| abstained | 35 |
| DecisionDamage | 0 |
| damage kinds with a detector | 11 of 11 |

## The operator surface

`/learning-acceleration` renders the market engine's own learning record and
computes no metric of its own — two definitions of "novel evidence" is how a
dashboard starts disagreeing with the engine it describes. Beneath it,
`_econ_decision_block` shows the economic layer: conditions measured against
the vocabulary, how many moved, supported versus candidate relations, open
and resolved predictions, and the calibration line.

That line states `PRE_CALIBRATION` and **carries no percentage**, and says in
words that the rehearsal ledger is a file this surface does not read. Both
are asserted by test, including a regex that refuses any percentage anywhere
in the block.

## What legitimate stability looks like

Five of six relations are CANDIDATE because their driver did not move. Zero
expectations resolved because none has reached its horizon. Thirty-five of
sixty A/B cases abstained because the state did not bear on the decision.

None of those is stagnation, and the ledger records the reason for each so a
later cycle does not re-report them as failures.

# Signal-audit outcomes — dry run, 2026-11-25

Branch `learning-loop/resolver` (worktree `~/ie-learning-loop`, cut from the
live runtime's commit `195c6f4a`). Grader: `market/outcome_resolver.py`
(`signal_outcome_resolution.v1`) applying the preregistered
`volatility_feasibility.v1` rule. Run on a **copy** of
`~/intent-engine-market/reports/market/signal_audit.jsonl` (sha256
`16074b0b8ac8cf6e…`, verified identical before and after). Prices: the
runtime's own feed (Yahoo chart, split-adjusted, not dividend-adjusted),
fetched 2026-11-25. Nothing was written to the runtime.

Raw output: `reports/learning_loop/signal_outcomes_dryrun_2026-11-25.json`
and the 485 proposed outcome events in `…_2026-11-25.jsonl`.

## What these records are

669 records, all from one signal, `baseline_momentum.v1`. **None fired.**
None carries a direction or a probability. They are a preregistered
counterfactual audit: "was there a gradable opportunity that the silent
signal missed?" They are not forecasts. A Brier score and a trade return
are undefined for them, and none is reported.

The runtime has no other price forecasts. `reports/market/paper/` does not
exist: no paper position has ever opened, because the only entry signal
never fired. The runtime's other forward objects are 176 business-event
expectations (47 reconciled on evidence, none due before 2026-12-03). Those
are not price outcomes.

## Accounting

| | Records |
|---|---:|
| Inspected | 669 |
| Duplicate rows (a cycle run twice, Aug 1–10, same identity) | 71 |
| Not yet mature (21-day horizon not elapsed) | 113 |
| Resolved | 362 |
| Pending, retryable (OLO feed HTTP error, before its final date) | 19 |
| Unresolvable, terminal (OLO feed HTTP error after final date: delisted) | 104 |
| **Sum** | **669** |

The 362 resolved records are 234 distinct decisions (same instrument and
date in the day and night cycles counts once; 128 collapsed).

## Result

| | Value |
|---|---:|
| Distinct resolved decisions | 234 |
| Missed-opportunity candidates among them | 228 |
| Confirmed misses (\|21-day move\| ≥ 2%) | 207 (90.8%) |
| Median \|21-day move\| | 8.9% |
| Unconditional rate, same 6 instruments, every 21-day window 2025-01 → 2026-10 | 76.6% |
| Same, weighted by this sample's instrument mix | ≈ 83.5% |

By instrument: SHOP 73/83, NET 70/74, MELI 25/30, NEE 26/28, CHKP 7/7, PG 6/6.

## What it does and does not show

* **It shows the signal was silent through 228 gradable windows** in which
  the median stock moved 8.9%. A momentum baseline that never fires in four
  months of six volatile names is not "correctly quiet".
* **It does not show predictive skill, positive or negative.** No direction
  was ever stated, so nothing can be right or wrong.
* The opportunity label's lift over the base rate (about +7 points) is weak
  evidence. Windows overlap heavily (6 instruments × ~100 days), so the
  effective sample is far smaller than 228.
* The 2% noise floor is low for these names: 3 in 4 random windows clear
  it. A "confirmed miss" is therefore a weak test. Changing the floor needs
  a new preregistered version. v1 results stand as recorded.

## Defect fixed on the way

The original `signal_opportunity.resolve_outcome` takes the last close on or
before the horizon end as the exit. For an instrument with no bar after
`as_of` (OLO, delisted), that is the entry bar itself, so it would have
recorded a **0.0% return**, an invented outcome. That behaviour is pinned in
`test_no_bar_after_as_of_is_never_a_zero_return`. The new resolver requires
a later exit bar within 5 days of the horizon end.

## Mutation check

Each guard was reverted one at a time in a scratch copy:
exit-after-as_of, terminal-skip, final-grace, decision dedupe and entry
staleness. **All five were caught.** The first was originally NOT_CAUGHT
(the 21-day staleness check masked it), and
`test_on_a_short_horizon_the_entry_bar_can_never_double_as_the_exit` was
added for it.

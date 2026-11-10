# Pre-registration — signal opportunity, definition v1

**Registered:** 2026-07-31 (Day 17), before any result was computed.
**Definition ID:** `volatility_feasibility.v1`
**Implementation:** `src/intent_engine/market/signal_opportunity.py`

---

## 1. The question

Five operating days produced `signal_fired = 0.00` with standard deviation
0.00. Day 16 classified that as *stable at zero* and refused to call it a
defect, correctly: a momentum baseline measured at 0.500 declining to fire may
be the honest behaviour, or the signal may be broken. **"It never fired" is
identical in both worlds.**

The distinguishing question is not *did the signal fire*. It is:

> Should a qualifying opportunity have existed at all?

## 2. The hypothesis

**H1.** A meaningful fraction of company-days on which the signal is silent
carry no qualifying opportunity — i.e. the silence is *correct*, not a defect.

**H0 (null).** Qualifying opportunities are present on essentially all
signal-evaluated company-days, and the signal's silence is therefore a
deficiency in the signal rather than a property of the market.

## 3. The definition

At `as_of`, for (instrument, horizon), a **qualifying opportunity** exists iff:

1. at least **20 closes** exist dated on or before `as_of`; **and**
2. trailing realised volatility over the last **20 closes**, scaled to the
   horizon (`sigma * sqrt(horizon_days)`), is **>= 0.02**.

In words: *does this instrument move enough over this horizon for a directional
call to be gradable rather than a coin flip on noise?*

### Parameters, and where they came from

| parameter | value | provenance |
|---|---|---|
| `MIN_ABS_RETURN` | 0.02 | **imported from `signals.py`**, fixed since Phase 2 day 1 |
| `LOOKBACK` | 20 sessions | standard one-month window |
| `MIN_BARS` | 20 | the same window; below it the volatility estimate is not worth having |
| `HORIZON_DAYS` | 21 | the baseline signal's existing horizon |

**None of the four was chosen by looking at outcomes.** That is the specific
property that makes this pre-registration meaningful rather than decorative,
and it is asserted by test:
`test_the_threshold_is_inherited_from_the_shipped_signal_constant`.

### Why this is not the firing rule restated

It would be worthless if it were. `baseline_momentum.v1` fires on trailing
**direction** (`|trailing return| >= MIN_ABS_RETURN`). This condition is about
**feasible magnitude** (realised volatility over the horizon). An instrument can
be volatile with no net drift — opportunity present, signal silent — and it can
drift steadily while barely moving day to day.

All four cells of the 2x2 are reachable, asserted by
`test_all_four_cells_are_reachable`. If the two conditions were the same rule,
two cells would be unreachable and the layer would measure nothing.

## 4. The states

| state | opportunity | fired |
|---|---|---|
| `CORRECTLY_QUIET` | no | no |
| `MISSED_OPPORTUNITY_CANDIDATE` | yes | no |
| `CORRECT_FIRE` | yes | yes |
| `FALSE_FIRE_CANDIDATE` | no | yes |
| `UNMEASURABLE` | insufficient data | — |

Plus an independent outcome axis: `UNRESOLVED` until the horizon elapses.

**Why "candidate".** A missed opportunity stays a *candidate* because
confirming it requires the realised outcome, and the outcome does not exist at
decision time. Collapsing the two would produce a system that labels its own
past decisions using information it did not have — the most flattering possible
bug and the hardest to see afterwards.

## 5. The lookahead boundary

Two things are kept strictly apart, and the separation is enforced by test:

* **Observable at decision time** — uses only closes dated `<= as_of`. Labels
  live decisions. Never consults a future return.
* **Resolved outcome** — attached only after the horizon has *fully* elapsed,
  used only for evaluation, and it **never rewrites the decision-time label**.

Guarantees, each with a named test:

| guarantee | test |
|---|---|
| future bars cannot change a decision-time label | `test_future_bars_cannot_change_a_decision_time_label` |
| an unelapsed horizon is never graded | `test_an_unelapsed_horizon_is_never_graded` |
| resolution never rewrites the live label | `test_resolution_never_rewrites_the_decision_time_label` |
| a rerun cannot re-grade against a later price | `test_an_already_resolved_record_is_not_regraded_by_a_rerun` |
| a missing close leaves the record unresolved | `test_a_missing_close_leaves_the_record_unresolved_rather_than_guessing` |

The cycle additionally raises `IntegrityViolation` — which fails the whole run,
never a partial — if the bar count used by an estimate ever exceeds the number
of bars dated on or before `as_of`.

## 6. Reporting commitment

**All results are reported, including null and unflattering ones.** Specifically:

* If H1 is supported (a substantial `CORRECTLY_QUIET` fraction), that is
  reported as evidence the signal's silence is defensible. **It is not evidence
  the signal has edge** — the baseline remains measured at 0.500 and stays
  labelled unvalidated.
* If H0 is supported (nearly all silent days carry a qualifying opportunity),
  that is reported as evidence of a deficiency in the signal, and it will be
  reported even though it implies the last sixteen days of silence were a bug.
* If the states are dominated by `UNMEASURABLE`, that is reported as a data
  problem and **no** conclusion is drawn about the signal.

**The definition will not be re-tuned against the observations used to judge
it.** Any change requires a new version string (`v2`) and a new
pre-registration; `v1` results stand as recorded. A `v2` that appears shortly
after a disappointing `v1` result should be read with exactly the suspicion it
deserves.

## 7. What this cannot do

* It cannot validate a signal. Confirming a missed-opportunity candidate needs
  resolved outcomes, and **zero** exist today.
* It cannot run on the replay path at depth: industry evidence has a measured
  87-day ceiling, and price history alone does not carry the evidence gates.
* It says nothing about direction. A qualifying opportunity means the
  instrument *moves*, not which way.

## 8. Status at registration

`confirmed_miss_rate` is **UNMEASURABLE — no candidate has completed its
horizon.** That is the honest starting value and it is what the report prints.

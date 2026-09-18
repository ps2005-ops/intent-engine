# Pre-registration — Day 4 · hypothesis-specific horizons

Written **before any test was run**. Each horizon is justified by the mechanism
it belongs to, fixed for the whole evaluation, and **not** chosen for
statistical power.

## The trap this is avoiding

Day 3 ranked "shorter horizon" as the top lever on `n_eff`, because `n_eff` is
bounded by `history ÷ horizon`. That was optimising the *experiment* rather
than testing the *mechanism*. A 5-day horizon on a proxy-governance hypothesis
would raise the sample count and measure something the hypothesis never
claimed.

**The horizon is part of the hypothesis.** Where a mechanism resolves slowly,
low `n_eff` is a true statement about how much evidence exists — not a problem
to be engineered away.

## Horizons, and why

| hypothesis | mechanism | horizon | justification |
|---|---|---|---|
| `report_drift.v1` | Periodic financials are absorbed by analysts and algorithms within days; any under-reaction is short-lived. | **5d** | Quarterly reports are scheduled and widely parsed. If drift exists it is a days-long absorption effect, not a quarter-long one. |
| `event_drift.v1` | An 8-K/6-K discloses an unscheduled material event; surprise is largest immediately and decays. | **3d** | Unscheduled news is priced fastest. A 21-day window mostly measures whatever else happened that month. |
| `insider_buy.v1` | A Form 4 open-market **purchase** by an officer/director signals private confidence; the market re-rates slowly because the signal is weak individually. | **90d** | Insider-information effects are documented as slow-acting. A 21-day window is too short for the mechanism to express itself. |
| `activist_stake.v1` | A SC 13D is an *activist* stake (13G is passive); the thesis is that governance pressure changes company behaviour. | **120d** | Board changes, strategic reviews and divestitures take months. Anything shorter tests the announcement pop, not the mechanism. |
| `proxy_drift.v1` | Proxy materials disclose governance and compensation changes that resolve over an annual cycle. | **90d** | Carried from Day 3 at 0.6049/n_eff=26 — but **at the wrong horizon (21d)**. This is a *new test at the correct horizon*, not a continuation of that one, and the earlier number does not transfer. |

## What is deliberately NOT done

- **No horizon is shortened to reach n_eff ≥ 30.** Two hypotheses below are
  expected to fail on power precisely because their mechanisms are slow. That
  is the honest outcome.
- **No existing signal is modified.** `report_drift.v1` and `event_drift.v1`
  are re-run at justified horizons; their decision rules are untouched.
- **13D is separated from 13G.** Day 3 pooled them into
  `ownership_drift.v1`, which mixed activist and passive stakes — two different
  mechanisms under one name. Separating them is a correction, not a new search.

## Multiple testing

Five hypotheses, one fixed horizon each: **five tests**, not five × a horizon
sweep. Sweeping horizons and reporting the best would be the multiple-testing
bias this pre-registration exists to prevent. All five results are reported
whatever they show.

## Retirement conditions, fixed now

- Accuracy inside the `n_eff`-based 2σ band of 0.500 → **retire**.
- `n_eff < 30` after using all available history at the justified horizon →
  **retire as unmeasurable**, and record that the mechanism cannot be evaluated
  with the data this project can reach.

## Prediction, recorded before running

Adaptive horizons will **reduce** total independent evidence, not increase it.
Short horizons (3–5d) raise the window ceiling for two hypotheses; long
horizons (90–120d) cut it hard for three. Net: fewer measurable hypotheses than
Day 3's uniform 21d, and that is the correct answer rather than a failure.

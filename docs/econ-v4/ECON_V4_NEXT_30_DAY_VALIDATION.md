# ECON_V4_NEXT_30_DAY_VALIDATION

What must be *observed* — not built — before any claim about predictive
improvement is admissible. Thresholds are written down now, before the data
arrives, because a threshold chosen after seeing the result measures nothing.

## Why this plan exists

The engine currently has 32 resolved expectations and **0 beliefs tested
twice**. Every statistical statement downstream of that is limited by it. No
amount of engineering closes the gap; only elapsed time with a working
reconciliation path does.

## Declared thresholds

| # | question | measure | threshold | earliest readable |
|---|---|---|---|---|
| 1 | Do cycles stop vanishing? | scheduled vs recorded cycles | **≥ 95%** of scheduled cycles present in the ledger over 30 days | day 30 |
| 2 | Are missed cycles visible? | alerts raised / cycles missed | **1.00** — every miss alerts | first miss |
| 3 | Does any belief get tested twice? | beliefs with ≥ 2 `belief_update` rows | **≥ 5** | day 30 |
| 4 | Does the resolution rate move? | reconciliations per cycle | **> 0.30/cycle** (baseline 32/114 ≈ 0.28) | day 30 |
| 5 | Is the hit rate stable? | confirmed / resolved, with Wilson CI | CI width **< 20pp** (needs n ≈ 90) | day 60+ |
| 6 | Do probabilities beat climatology? | Brier skill | **> 0** on n ≥ 50 | day 60+ |
| 7 | Is under-confidence real? | mean reliability gap | gap **> +0.05** persists at n ≥ 50 | day 60+ |
| 8 | Does negative knowledge act? | `LearningDecisionDelta` rows ≠ NO_CHANGE | **≥ 1** traceable to a reliability fall | after Wave 4 |

Items 5–7 are explicitly **not readable in 30 days** at the current
resolution rate. Saying so now prevents a 30-day report from over-reading
n = 40.

## The honest arithmetic on item 6

Brier skill is **−0.0576** at n = 32, and forecasts span 0.564–0.654
(sd 0.019). A model emitting a near-constant probability cannot beat
climatology, because climatology *is* a constant and a better-chosen one.

So item 6 cannot pass by collecting more outcomes alone. It requires the
forecast to vary with the evidence — which is Wave 3 (defensible inference),
not a waiting game. **Do not schedule item 6 as an observation task.**

## The trap to avoid on item 7

Both reliability bins are under-confident (+0.082, +0.254), so raising priors
would improve the Brier score *on these 32 outcomes*. That is fitting the
adjustment to its own evaluation set.

Any recalibration must be fitted on outcomes strictly before a cut date and
scored on outcomes strictly after it, with both n's reported. If there is not
enough data to split, the correct action is to wait, not to fit.

## Instrumentation needed first

1. **Missed-cycle alert** — `learning_health.alerts` must fire when a
   scheduled cycle has no ledger entry. Item 1 and item 2 are unmeasurable
   without it; today the loss is nameable but silent.
2. **Cycle accounting** — scheduled / attempted / completed / intentionally
   skipped / unexpectedly skipped / missed, as six separate counts. The
   current report shows 100% step reliability over the cycles that ran, which
   cannot answer item 1.
3. **Repeated-test counter** — `beliefs with ≥ 2 updates` is not currently
   reported anywhere, so item 3 has no readout.

## Review points

- **Day 7** — items 1, 2 only. Enough to tell whether operation is fixed.
- **Day 30** — items 1–4. Items 5–7 reported as `INSUFFICIENT_OUTCOMES` with
  their n, never as a number.
- **Day 60** — first admissible read on 5–7, if and only if n thresholds are
  met.

A review that reports items 5–7 before their n is reached is the failure mode
this document exists to prevent.

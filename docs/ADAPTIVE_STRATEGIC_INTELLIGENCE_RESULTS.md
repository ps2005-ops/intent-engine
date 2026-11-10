# Adaptive Strategic Intelligence — results

> This document is completed from the frozen live matrix. Until that run
> exists, the sections below state what will be filled in and from where, so
> that nothing here can quietly become an estimate.
>
> Machine-readable form: `ADAPTIVE_STRATEGIC_INTELLIGENCE_RESULTS.json`,
> produced by `scripts/adaptive_results.py` from
> `reports/adaptive_ten_matrix.json`. The harness measures and persists; the
> scorer decides what the numbers mean. They are separate files so a frozen
> run can be re-scored without being re-run — and so a scorer bug cannot
> silently spend a live demo quota.

## Frozen SHA

| | |
|---|---|
| `ADAPTIVE_INTELLIGENCE_QUALIFYING_SHA` | *(filled from the frozen run)* |
| `LOCAL_SHA` | *(verify_deployed_sha.py)* |
| `ORIGIN_SHA` | *(verify_deployed_sha.py)* |
| `LIVE_SHA` | *(`/version` on the deployed service)* |

All three must be identical before the matrix starts, and no product change
may land while it runs. `scripts/verify_deployed_sha.py` is the check; it is
separate from the deploy because a push that succeeded and a service that
restarted on it are different events — the recorded failure is a repair that
landed green and shipped inert.

## Per-company

For each of the ten: business model and where it came from, customer job,
primary strategic asset, top three decision opportunities with their component
scores, primary and secondary lens with why-selected and the refusals, the top
causal chain, thesis or defensible abstention, decision delta,
counter-evidence, information priority, CEO view, Strategy view, Q&A result,
UI result, genericity result, latency, defects.

## What a defensible abstention looks like here

A company can pass without a thesis. The passing shape is:

```
NO STRONG READING
WHY                    the evidence limitation, named
WHAT WE KNOW           the supported facts
WHAT WE CANNOT CLAIM   the unsupported inference, named
INFORMATION PRIORITY   what evidence would change it
```

with the company model correct, the lens correct or explicitly withheld with
its reason, and the gap stated. That is a 10/10 epistemic result and it is
recorded as `DEFENSIBLE_ABSTENTION`, not as a near-miss.

## Manual executive review

Twelve questions per company, answered by reading the live page rather than
the telemetry. Automated checks cannot answer most of them:

1. Does this page feel like it was written for THIS company?
2. Did the system understand how the business creates value?
3. Did it identify the right strategic asset?
4. Is the selected lens defensible?
5. Is the top decision actually important?
6. Is the causal mechanism company-specific?
7. Is there meaningful evidence against the thesis?
8. Would a strategy executive learn something?
9. Is the management implication actionable?
10. Is uncertainty honest?
11. Does the role interface help rather than decorate?
12. Would I be comfortable showing this page to the CEO named in outreach?

Any NO is inspected and classified. During the frozen matrix it is **not**
patched — a qualification that repairs itself mid-run measures the repair.

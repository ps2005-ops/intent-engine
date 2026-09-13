# BREAKER TEN — FIRST WAVE

**Baseline:** `baseline_95d322f85535.json` · runtime `95d322f8` · manifest `1.0.0`
· clean tree · 10/10 attempted, 10/10 completed, 0 crashes, 0 substitutions.

> **THE INTELLIGENCE LAYER WAS NOT MEASURED.** The Anthropic credit balance is
> exhausted, so `analyse()` never produced a strategic conclusion for any
> company. Everything below about identity, retrieval, source health, dossier
> assembly and performance is real. Nothing below is evidence about thesis
> quality, causal identification, adversary reasoning or company
> specialization — those clusters are **UNMEASURED**, not passing.

## What ran

| company | docs | approved | fetch yield | families found | missing core | wall |
|---|---|---|---|---|---|---|
| cloudflare | 9 | 14 | 64% | commercial, customers, identity, investor | strategy | 20.7s |
| advanced-micro-devices | 3 | 14 | 21% | investor | identity, product, customers, strategy | 179.4s |
| boeing | 6 | 14 | 43% | identity, investor, product | customers, strategy | 15.9s |
| bank-of-america | 7 | 14 | 50% | identity, investor, product | customers, strategy | 20.6s |
| alimentation-couche-tard | 7 | 14 | 50% | identity, product, strategy | customers, investor | 10.6s |
| agnico-eagle-mines | 2 | 14 | 14% | investor | identity, product, customers, strategy | 5.8s |
| bce | 9 | 14 | 57% | commercial, customers, identity, investor | strategy | 26.1s |
| stripe | 10 | 14 | 71% | commercial, customers, identity, independent | investor | 22.2s |
| mckinsey | 3 | 14 | 7% | independent | identity, product, customers, investor, strategy | 160.3s |
| johnson-and-johnson | 5 | 14 | 29% | customers, identity, investor | product, strategy | 21.7s |

**Cohort fetch yield: 54/140 = 39%.** Failures: 62 `http_status` (mostly
403/404), 20 `timeout`, 2 `too_large`, 2 `unsafe_redirect`.

Every dossier: `INTELLIGENCE_PARTIAL`, `FOUNDER_AVAILABLE_MARKET_UNAVAILABLE`,
`IMPACT_UNMEASURABLE_FIRST_OBSERVATION`, cohort `DEVELOPMENT`, manifest
`1.0.0`, zero quarantines. All correct: no market engine publishes into this
runtime, and a first dossier has no `before`.

## Defect clusters

Full records in `defects.json`.

| id | class | cluster | status |
|---|---|---|---|
| BW10-001 | B | IDENTITY | **FIXED** `d41f6aa` |
| BW10-002 | B | GENERIC_REASONING | **FIXED** `d41f6aa` |
| BW10-003 | C | PROVENANCE | **FIXED** `d41f6aa` |
| BW10-004 | D | SOURCE_COVERAGE | open |
| BW10-005 | D | PERFORMANCE | open |
| BW10-006 | D | SOURCE_COVERAGE | open |
| BW10-007 | E | TRANSPORT | open |

### The three that were fixed

**BW10-001 — the manifest join was dead for every real company.** The
pipeline resolves a company to its legal name, so `Cloudflare, Inc.` became
the key `cloudflare-inc` and matched no manifest id. Every dossier was filed
where the programme cannot find it, with no cohort and no manifest version —
indistinguishable from a company legitimately outside the universe, and
nothing raised. At 100 companies the entire measurement would have read zero.
Batch 9's join test passed only because its fixture was named bare `Shopify`.

**BW10-002 — a failure was blamed on the evidence.** The analyst returned
`FAILED` on an exhausted balance and the founder was told *"every source here
is the company's own account; independent reporting would strengthen this."*
That reader goes and collects more sources and nothing improves. The branch
was keyed on `!= COMPLETE`, so it caught states that are about us.

**BW10-003 — the diagnosis was discarded.** `BadRequestError` with no message
is the same output for an exhausted balance, an unknown model, an oversized
request and a malformed schema. The wave hit it on every company and could not
say why from its own output.

### The most actionable open one

**BW10-004.** `validation.redirect_allowed` permits the same *registrable*
domain, then requires exact host equality — so `cloudflare.com →
blog.cloudflare.com` and `stripe.com → docs.stripe.com` are refused as
`unsafe_redirect`. But `same_domain()`, which **approves** candidates, accepts
those same hosts. Two functions in one module disagree about what "the same
company" means, and the refused subdomains are exactly where strategy and
customer content lives — the two families missing most often (8/10 and 6/10).

Not fixed here: it touches an SSRF-adjacent guard and deserves its own review
rather than a hurried edit at the end of a wave.

## Performance

p50 **18.5s**, p95 **178.9s**, max **179.4s**.

The tail has one mechanism: **all 20 cohort timeouts fall on AMD and McKinsey,
10 each**, and those are the only two runs over 150s. Every other company
finishes under 30s. This is BW10-005 and it is a bounded-retry problem, not a
general slowness problem.

## Two findings that were mine, not the product's

The first pass of this runner asked for `reason`/`error` on failed sources and
`families_present` on coverage. The producer writes `failure_type`/
`safe_message` and `families`. The wave therefore reported *"unknown"* failure
reasons and *zero evidence families for all ten companies* — two convincing,
entirely fictitious product defects.

Both were caught by checking the producer before writing them up. An
instrument that names its fields wrongly manufactures findings, which is worse
than measuring nothing, and at 100 companies nobody would re-derive them by
hand.

## What this wave cannot tell you

Thesis quality · causal identification and method selection · adversary
specificity · company specialization · evidence independence · MDR/MVE value ·
DecisionImpact. All require the analyst. `EVIDENCE_INDEPENDENCE` remains
`UNAVAILABLE` by contract — no producer exists, and a raw document count was
never promoted into corroboration.

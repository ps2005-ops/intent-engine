# Template collapse — traced to a classification seam, by the deployed UI

## The symptom, measured live

Meta, Caterpillar and Exxon answered **nine of ten** board questions with the
identical sentence, through the deployed Q&A route:

> Yes — on balance the evidence supports that **committing capital to
> capacity ahead of uncertain demand** (moderate confidence).

and all three were offered the same analogy, *"Memory and sensor fabrication
cycles"*. Meta is an advertising auction; Exxon is an oil major.

### Measuring it is harder than it looks — three instruments lied first

| method | result | why it was wrong |
|---|---|---|
| naive similarity over captured answers | 0.915 | inflated by shared page chrome |
| mask company name, test byte-equality | 0/10 | deflated: chrome *after* the answer differs per company |
| mask name variants from a `set` | 0/10 | arbitrary iteration order replaced `Caterpillar` before `Caterpillar Inc.`, leaving a stray `" Inc."` |
| **mask longest-variant-first AND cut at the first chrome marker** | **9/10** | the number |

`scripts/pre100_template_collapse.py` implements the last one and is the only
form that should be quoted.

### The before-number, on the deployed build

Re-measured through the deployed UI on **58ac7ef**, after `e0f9446` landed,
for Meta and Caterpillar with all ten answers captured from the live Q&A
route:

    IDENTICAL ACROSS ALL COMPANIES: 10 / 10

An advertising auction and an equipment manufacturer, byte-identical on every
board question once the company name and the page chrome are removed. This is
the "before" the post-fix pass is measured against, and it is worse than the
9/10 baseline because the tenth question differed only across a wider trio.

## The first diagnosis was right and insufficient

`patterns_for` gated the library by an **exclusion** list. The three model
classes added a cycle earlier appear in nobody's exclusions, because they did
not exist when those lists were written:

    ADVERTISING_PLATFORM   12 of 12 patterns
    MULTI_ENGINE_PLATFORM  12 of 12
    SCALE_RETAIL           12 of 12
    every older class       5 to 11

Repaired in `e0f9446`: applicability is positive (`considered_model_classes`),
`MODEL_CLASSES` became a real registry, and a guard requires every pattern and
every model-keyed table to cover it.

## And it shipped INERT — which only the deployed page showed

After `e0f9446` deployed, `patterns_for("ADVERTISING_PLATFORM")` correctly
excludes `capacity_ahead_of_demand`. Meta's rendered Full Analysis on the same
build still said:

> *"Memory and sensor fabrication cycles — capacity added on forecast, then
> written down when handset demand moved"*
> *"order books and take-or-pay terms are not public"*

for a company with no order book and no take-or-pay terms.

**The cause is a classification seam.** `company_ingestion/service.py`:

```python
def _patterns_for_company(company_name, domain=""):
    model = profile_for(name=company_name, domain=domain).business_model_class
    return patterns_for(model)
```

Name and domain only. Meta is not in the validation manifest, so this returns
`UNKNOWN`, and `patterns_for("UNKNOWN")` deliberately returns the whole
library. Measured:

| company | model from name alone | patterns offered |
|---|---|---|
| **Meta** | **UNKNOWN** | **12 / 12** |
| Caterpillar | `MANUFACTURE_AND_AFTERMARKET` | 10 / 12 |
| NVIDIA | `DESIGN_AND_MANUFACTURE` | 10 / 12 |
| Walmart | `SCALE_RETAIL` | 7 / 12 |
| Exxon | `COMMODITY_PRODUCER` | 5 / 12 |

Caterpillar resolves correctly **because it is in the manifest**, which is
exactly why a three-company comparison read as a pattern-library problem.

`webapp/app.py` already has `classification_inputs()`, which fetches the
registrant SIC and the subject's own filing text so `profile_for` stops
returning UNKNOWN — and its docstring records the identical Meta symptom. The
executive path was fixed; the ingestion path never was. **One defect, two
consumers, one fixed.**

## The guard had the same shape as the bug

`test_a_model_class_registry.py` NAMED two model-keyed tables. A parallel
session discovered **eleven**, of which only three covered the registry —
including `product_eval.defect_taxonomy._MODEL_FOREIGN`, the detector that
exists to catch industrial language in a business with no order book. It had
no row for an advertising platform, so **the leak passed the product's own
defect check**. An enumeration cannot cover what it does not already know
about; the guard must DISCOVER tables, not list them.

## Status

* pattern gate given domain + registrant + subject-only evidence, with an AST
  seam test pinning the call site — **owned by the parallel session**
* all eight uncovered tables filled, `_tables()` discovers rather than names,
  and a `NEW_MODEL_CLASS_13` test requires every discovered table to fail
  closed on an undefined class — **same session**
* live re-measurement against the 9/10 baseline — **pending that deploy**

## What this is evidence for

Backend correctness was not enough, twice in one session. The pattern filter
was right and the page was wrong, because the caller never supplied a class to
filter on. Nothing counts until it is read on the deployed customer UI.

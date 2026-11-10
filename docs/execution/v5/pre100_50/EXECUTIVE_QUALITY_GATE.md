# Executive Quality Gate — first adjudication

`scripts/pre100_quality_gate.py` · scored data in `QUALITY_50.json`

```
EXECUTED           50/50
MECHANICAL_PASS    32/50
CORE_MEAN          8.13      bar 9.0
CORE_MIN           0         bar 8.5
EXECUTIVE_QUALITY  FAIL
```

## What the instrument does and does not claim

Every score is read from MEASURED features of the rendered text — is the
passage present, does it name this company rather than any company, does it
carry a quantity or a named entity, is the surface substantial — and every
score carries the passage it was read from. A dimension whose surface did not
render is NOT_MEASURED, never zero, and a core dimension that is NOT_MEASURED
fails rather than being averaged away.

It does not simulate the persona panel in §28. A measured rubric can
establish that competition names three real rivals with a basis for each; it
cannot establish that a PE operating partner would act on the
recommendation. That judgement is still owed and is not faked here.

## Two of the first three findings were the instrument's own

Both had the shape that should always be suspected — identical across 46 of
46 companies:

- `CORE` named `economic_reasoning`, which `DIMENSIONS` does not define, so
  every company reported it NOT_MEASURED. The two lists are now checked
  against each other at import.
- A cue of `"."` returned the first CHARACTER, so the deck was scored on the
  letter `"N"`.
- Market belief, belief challenge, falsifier and MVE were pointed at `/full`
  when the product writes them on `brief`. Measured across every capture:
  "the market's current belief" appears on brief in 79 captures and on full
  in 31.

Correcting the instrument moved CORE_MEAN 7.09 → 8.19 and `market_belief`
2.0 → 9.7. Reporting 2.0 would have sent a repair wave at a non-defect.

## What survived, ranked by cost

| dimension | mean | reading |
|---|---|---|
| `adversary` | **0.0** (0/42) | Appears on NO surface of ANY company. `deep.py` reads an `adversary` key and an ADVERSARIAL scenario — the concept exists in the model and never reaches a reader. |
| `impossible_hypothesis` | **0.0** (0/42) | Same: absent from every rendered surface, though §23 lists it as required. |
| `micro` | 4.2 | 11 zeros. Price/volume/mix reasoning is thin. |
| `business_model` | 5.9 | **Model-CLASS collapse — see below.** |
| `margin_drivers` | 6.0 | Same sentence family as the model class. |
| `intro` | 5.9 | Inherits the model sentence. |
| `competition` | 7.0 | Strong where it fires; Goldman's rivals read "Banking Supervision and Compensation P" — a filing heading, not a firm. |
| `qa` | 7.1 | 18 companies answer with absence copy. |

Strong and not in need of repair: `presentation` 9.8, `revenue_drivers` 9.8,
`step6` 9.8, `history` 9.6, `market_belief` 9.7.

## The single largest quality defect, measured

The business-model sentence is written per MODEL CLASS, not per company.
Across the 45 companies that render one:

```
pairwise n=990   mean similarity 0.446
byte-identical pairs: 79  (8.0%)
pairs above 0.8 similarity: 87
```

Byte-identical: **Adobe = Cloudflare = Microsoft = Salesforce = Shopify**;
**Alphabet = Meta**; **Amazon = Home Depot**. Six semiconductor companies
share one sentence, six financials share another, five software platforms a
third, five consumer businesses a fourth:

> "semiconductor business that runs on design and manufacture of a physical
> product sold into a capacity-constrained supply chain"  ×6

This is exactly what §21 exists to catch. A CEO who sees the sentence
describing their company also describing four others has been shown a
template with a name inserted.

## Next repair wave, in cost order

1. The model sentence must be built from THIS company's evidence, not
   selected from a per-class table.
2. Render the adversarial response and the impossible hypothesis — the model
   already computes at least the first.
3. Competition must not accept a filing section heading as a rival.
4. Q&A absence copy on 18 companies.

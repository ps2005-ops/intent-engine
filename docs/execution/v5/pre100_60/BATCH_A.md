# Batch A — ontology measurement

Cohort: Meta, Amazon, NVIDIA, JPMorgan Chase, Walmart, Eli Lilly,
Caterpillar, Exxon Mobil. Deliberately cross-industry.

Measured with `scripts/batch_a_ontology.py`, which runs the PRODUCTION
classification path — the registrant's SIC from its own CIK plus its own
10-K text, exactly as `WebApp.classification_inputs` supplies them.

---

## §1 first: the Meta competitive repair was NOT closed

Re-read live on `ebd0a6f`. The defect was still on the page:

> Its position is contested most directly by **AT&T Inc, Alphabet Inc** and
> Automation absorbing the task itself.

And the Full Analysis showed the evidence it was built from:

> AT&T Inc: **Meta Platforms, Inc. names it as a competitor in its own
> filing** — our competitors include but are not limited to: 8x8, Inc.,
> Dialpad, Inc., LogMeIn, Inc., Microsoft Corporation, Nextiva, Inc.,
> Twilio Inc., Ericsson, Zoom, Amazon.com, Inc., AT&T I

**That sentence is RingCentral's.** RingCentral is a UCaaS company; 8x8,
Dialpad, Nextiva and Zoom are *its* rivals. Its 10-K was retrieved because it
mentions Meta, and the extractor read the list as though Meta had written it —
then published every name at **rung 1, NAMED_BY_SUBJECT**, under an
attribution that was false.

Root cause: `_named_rivals` was handed **every document in the run**.
`subject_text` and `competition_text` both filter on source class and both
document why; the producer that feeds rung 1 — and therefore outranks both —
never got the filter. The evidence drawer had the class right the whole time
("a regulatory filing written by another company").

Fixed: only the subject's own published classes reach the rival extractor.
9 tests, 5 of which fail before the repair. The honest cost is stated in the
tests: a run whose only competitive text belongs to somebody else now names
no rival, which is better than naming somebody else's.

---

## §4 ontology measurement

| company | SIC | assigned class | verdict |
|---|---|---|---|
| Meta | 7370 | `ADVERTISING_PLATFORM` | correct |
| Amazon | 5961 | ~~`BRANDED_CONSUMER`~~ → `MULTI_ENGINE_PLATFORM` | **was wrong**, fixed |
| Walmart | 5331 | ~~`BRANDED_CONSUMER`~~ → `SCALE_RETAIL` | **was wrong**, fixed |
| NVIDIA | 3674 | `DESIGN_AND_MANUFACTURE` | coarse, defensible |
| JPMorgan | — | `BALANCE_SHEET_OR_NETWORK` | coarse, **merge is a risk** |
| Eli Lilly | 2834 | `REGULATED_PRODUCT_OR_PROVIDER` | coarse, defensible |
| Caterpillar | 3531 | `MANUFACTURE_AND_AFTERMARKET` | coarse, good |
| Exxon | 2911 | `COMMODITY_PRODUCER` | coarse, defensible |

**Two were economically wrong, not merely coarse.**

*Walmart* was described as a business "where the brand carries pricing power
the product alone would not command" — the exact inverse of the world's
largest discounter, whose whole model is that price is LOW and the rent is in
turns and sourcing power.

*Amazon* was sent to the same class by SIC 5961 (catalog and mail-order). Its
profit is a marketplace take rate, a cloud utility and an ad auction; the
segment carrying the earnings is not the one the code names.

**The other six were left alone deliberately.** §6 says a class is added only
when a real company demonstrates the need, and Caterpillar's assigned class
describes its economics well. Splitting `BANK` out of
`BALANCE_SHEET_OR_NETWORK` needs Visa or Mastercard beside JPMorgan to show
the merge costs something — banks and payment networks have opposite capital
economics — and those arrive in **Batch C**.

### The finding that matters most

**Six of the eight resolve from the hand-curated validation manifest, not
from SIC.** The ten-class vocabulary is encoded in the validation universe
itself, so expanding the ontology is not a matter of improving the SIC
fallback — it means re-classifying manifest rows. Walmart's row was corrected
here because it was a plain data error; the coarse rows are a deliberate
decision that should be taken with evidence from later batches rather than
guessed at now.

---

## Repairs landed

1. `_named_rivals` filters to the subject's own documents (the RingCentral
   attribution defect).
2. `SCALE_RETAIL` added, and SIC major groups 52-59 re-pointed to it —
   those ARE the retail groups; `BRANDED_CONSUMER` belongs to SIC 20-39
   manufacturers.
3. `MULTI_ENGINE_PLATFORM` added, with an evidence discriminator requiring
   segment language plus both a cloud and a commerce engine.
4. Walmart's manifest row corrected to `SCALE_RETAIL`.

   **The sector was deliberately left as `CONSUMER`.** Changing it to
   `RETAIL` was the first attempt and it turned the locked-universe guard
   red across the whole manifest: **cohort assignment is DERIVED from
   sector**, so one row's sector re-derived cohorts for dozens of companies.
   The business-model class is what selects economics, metrics, competitors
   and macro exposure; the sector is a grouping key the validation universe
   is pinned to. Changing the first fixes the analysis, changing the second
   redefines the experiment.
5. `revenue_model_hint` tightened to require a **dominance** claim.

### Two false positives caught before they shipped

*Meta read as multi-engine* — the first detector matched "marketplace", which
is a Facebook **product** name. *Microsoft read as an advertising platform* —
its filing reports "search and news advertising revenue" as one line among
many. Both are pinned by tests. Almost every large platform earns some
advertising revenue; the question is whether it is where the money comes from.

Verified across six live filings: Meta and Alphabet advertising, Amazon
multi-engine, Microsoft / Salesforce / Cloudflare none.

---

## NOT done

The eight live customer journeys were **not run**. This session closed the §1
blocker (which was still live, and worse than reported) and completed the §4
ontology measurement. Scoring the twenty rubric dimensions per company
requires the journeys.

**NEXT_NOT_RUN_COMPANY**: Meta (live journey on the new SHA).
**NEXT_NOT_RUN_BATCH**: A (journeys + scoring), then B.

# Deploy B register — defects found on the b0ec8cb canary

## D1. `challenge_block.CSS` renders as literal text on `/full` (CRITICAL, §13 raw leak)

`webapp/app.py` builds the full analysis as:

```python
strat = (fr.BRIEF_CSS + fn.NARRATIVE_CSS + _charts.CHART_CSS + _cb.CSS
         + fd.render_dossier(...))
```

Three of those four constants begin with `<style>`. `challenge_block.CSS`
does not — it is a bare stylesheet string. `_stylize` hoists `<style>`
elements to `<head>`, so the three wrapped ones move and the fourth stays
where it was: as TEXT, immediately after `<main>`.

Measured on Meta's live capture, the first thing inside the analysis:

> `<main> .challenge{border:1px solid var(--rule);border-radius:10px;padding:1rem 1.15rem; …`

Two consequences, and the second is worse than the first:

1. Every reader of `/full` — and every text extractor, accessibility tree and
   screen reader — gets a stylesheet as the opening content of the analysis.
2. The rules never apply, so the `.challenge` block (the belief-challenge
   card) has been rendering **unstyled** on every company.

Fix: wrap it, and add a structural guard that every CSS constant concatenated
into a page body is `<style>`-wrapped — the defect is the asymmetry between
four siblings, so the guard belongs on the set, not on this one constant.

## D2. Raw enum constants shown to the customer on `/evidence` (CRITICAL, §13)

From Meta's live `/evidence`:

> "Search coverage: **DISCOVERY_PARTIAL** · reading: **HAVE_INDEPENDENT**"
> "Independent voice: yes · Relevance: **DIRECTLY_RELEVANT** · Counts as
> corroboration: yes"

Internal enum values rendered as customer copy. §13 names a raw-object leak a
critical defect, and this codebase has shipped one past a green test before —
the detector matched the comment explaining the enum rather than the enum.
The guard must read the rendered page, not the source.

## D3. `economic_reasoning` and `business_model` cannot measure what §15 asks

See INSTRUMENT_DEFECTS.md — these are scorer defects, not product defects, and
they need no deployment. Both are repaired against the 50 captures, not the 1.

## Predicted, from offline measurement on 11 real 10-Ks — see DEPLOY_B_CANDIDATE_C1.md

`what_is_sold` and `revenue_basis` both match mid-sentence relative clauses,
glossary entries and revenue-recognition policy. Sentence-anchoring repairs 4
of 11 outright and turns 4 wrong answers into honest empties.

---

## D4. Substitutes come from a sector prior, not from the company (CRITICAL, §15)

MEASURED across 22 live companies on `589518f`: **8 distinct substitution
clauses for 22 companies**, and they cluster by sector, not by business.

| clause | n | companies |
|---|---|---|
| "rental and used equipment in place of a new purchase" | 8 | NVIDIA, Broadcom, Qualcomm, Micron, Intel, AMD, Texas Instruments, Applied Materials |
| "non-bank providers reaching the customer directly" | 5 | Bank of America, JPMorgan, Goldman Sachs, Visa, Morgan Stanley |
| "automation absorbing the task itself" | 4 | Adobe, Microsoft, ServiceNow, Shopify |
| "another surface holding the same attention hour" | 2 | Alphabet, Meta |

Only Amazon ("publishers, distributors and the shopper buying the same basket
somewhere cheaper") and Salesforce ("cloud computing application service
providers and AI-native companies") received substitutes derived from their
own evidence.

**And one of them is economically wrong.** "Customers can substitute rental
and used equipment in place of a new purchase" is a capital-equipment
substitution. It is defensible for Applied Materials, whose customers really
can buy used fab tools. It is wrong for NVIDIA, Broadcom, Qualcomm, Micron and
Texas Instruments: nobody rents second-hand DRAM or GPUs instead of buying
chips. §13 names "unrelated competitors presented as direct" a critical
defect, and this is its substitution half.

The NAMED-RIVAL half of the same dimension is working and is genuinely
company-specific — Qualcomm gets "HiSilicon and MediaTek", Visa gets "UnionPay
and WeChat Pay", Cloudflare gets "on-premises network hardware vendors, point
solution vendors and network security vendors". So the repair is not to the
competition producer as a whole; it is to the substitution clause, which
reaches for a sector prior when the filing did not yield one.

This is the same failure this codebase has recorded before under "class prior
must not be the answer", where per-class business-model text made five
software companies byte-identical. The prior is being used as the answer
rather than as the fallback, and a wrong prior is worse than an absent one:
an executive reading "your customers can rent used equipment instead" about a
memory business learns something false.

Smallest repair: derive substitutes from the subject's own filing (its
competition and risk-factor language names them), and where none is found,
say so rather than substituting the sector's. `competition` scores 6 on 18 of
22 companies today; this clause is why.

---

## R3 — progressive first-useful result: BUILT, MEASURED, NOT SHIPPED

PERFORMANCE_GATE fails and the mechanism is exact: `/progress` releases the
reader only when `result_readiness().opens_result` is true, that requires a
composed result, and `_run_analysis` composes only after EVERY approved source
has been fetched. Measured over 49 live companies: p50 165s, p90 377s, p95
480s, fastest 88s, **0 of 49 under 30 seconds**.

The repair was implemented and tested: retrieval in two waves, the first being
the subject's own SEC filing plus its own front page (`fetch_approved` already
accepts an explicit `candidate_ids` subset and is idempotent per
source+content), an early bounded composition between them, then the full
fetch and the final composition. 10 focused tests, all 10 red against
`589518f`.

**It is not in this deploy, deliberately.** Running it against the full suite
turned two existing tests red —
`test_repeated_same_day_analysis_never_500s` and
`test_arbitrary_company_autoruns_recommended_sources` — both with
"analysis worker did not finish", because a second composition roughly doubles
the most expensive step in the worker. That is the honest trade the design
intends for the READER, but it also means total completion time grows, and I
could not establish from the captures what the approved-set-size distribution
is, so any threshold for "when is the split worth a second composition" would
have been a guess.

Shipping an unmeasured change to the core analysis worker on the last
available deploy, against a build that currently runs 50 consecutive live
analyses with zero 500s, is a worse trade than reporting the gate as failed.

Carried forward, complete:

* patch: `R3_progressive_first_useful.patch`
* tests: `R3_test_first_useful.py`

What the next cycle must measure FIRST: the distribution of approved-set size
and the wall-clock split between discover / fetch / compose. If compose is a
large fraction of the 165s, two compositions is the wrong shape and the early
reading needs a cheaper producer than the full one.

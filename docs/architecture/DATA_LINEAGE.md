# Data lineage

*Where every number comes from, and what is allowed to corroborate what.*

---

## Why this document exists

Two failures this repository has actually shipped:

1. A `ConsumerStressIndex` built partly from company disclosures, then cited
   in the same report as independent corroboration of a claim about consumer
   stress — the index corroborating its own inputs.
2. An identical evidence count appearing for every company in a batch, because
   a shared ledger was being read as though it were each company's own
   evidence.

Both are lineage failures. Neither is visible from the number itself.

## The five node classes and their sources

| class | publishers this deployment can actually read | count |
|---|---|---|
| `MACRO` | US Treasury (rates, bill/note, interest expense), Bank of Canada, Statistics Canada, US BLS (CPI, unemployment, earnings) | 20 LIVE of 35 kinds |
| `MARKET_STRUCTURE` | price feeds; derived vol and breadth measures | partial |
| `COMPANY` | SEC EDGAR filings, company IR pages, government awards, partnership releases | live |
| `STRATEGIC` | company disclosure and third-party coverage | live |
| `BEHAVIORAL` | **US BLS only**: JOLTS quits, labour-force participation | **2 LIVE of 26 kinds** |

Every node carries `Provenance(publisher, venue, url, document_id, producer)`
and both `occurred_at` and `available_at`. A node with no `available_at` after
its `occurred_at` is a hindsight leak, and `replay.assert_vintage` reads it.

## The behavioural family in detail

| kind | series | availability | why |
|---|---|---|---|
| `quits` | BLS `JTS000000000000000QUR` | **LIVE** | keyless; verified by calling the endpoint |
| `labour_participation` | BLS `LNS11300000` | **LIVE** | keyless; verified |
| `job_switching` | derived | **DERIVABLE** | quits against participation — a rising quits rate on falling participation is people *leaving* the labour force, the opposite reading |
| `survey_confidence` | `UMCSENT` | KEYED | routed through FRED; no key here. The keyless `fredgraph.csv` endpoint did not answer within 12s |
| `household_expectation` | `MICH` | KEYED | same |
| `saving_rate` | `PSAVERT` | KEYED | same; BEA's own API also requires registration |
| `delinquency` | `DRCCLACBS` | KEYED | **the most damaging gap** — it is the discriminating instrument for financial anxiety, without which that construct rests on contested proxies alone |
| `revolving_balance` | `REVOLSL` | KEYED | same |
| `business_formation` | `BABATOTALSAUS` | KEYED | same; the Census BFS API was called directly and returns *Missing Key*, and a guessed bulk-CSV path 404s |
| `big_ticket_intent` | UMich sub-indices | KEYED | published, not in the free FRED set |
| `trust_index` | trust barometers | UNAVAILABLE | proprietary and annual; an annual figure cannot support a quarterly-horizon comparison |
| `search_interest` | trends | UNAVAILABLE | licence forbids the redistribution; unauthenticated endpoints rate-limited to unusability |
| `retail_speculation` | order-flow share | UNAVAILABLE | vendor product; free proxies are derived from price, which would make it a market signal wearing a behavioural label |
| `defensive_spending` | retail control group | UNAVAILABLE | needs FRED or Census advance report; declared rather than approximated |
| `trade_down` | — | UNAVAILABLE | **see the lineage note below** |
| `public_language` | corpora | UNAVAILABLE | no licensed corpus; a tone index built from whatever is scrapeable measures the scrape, not the population |

These were **first written as LIVE** because the figures are public and the
series ids are real. Then the endpoints were called. The correction from LIVE
to KEYED is the difference between a coverage figure that is true and one that
looks better.

## The `trade_down` lineage note

Basket substitution has no public series. It *is* observable — companies
disclose customer trade-down in earnings calls and filings all the time.

That evidence enters as `COMPANY` evidence, correctly. It may therefore
**never** corroborate a consumer aggregate built from the same disclosures.
Building a "consumer trade-down index" out of retailer commentary and then
citing it as independent support for a claim about retailers is the
double-counting failure in its purest form.

So `trade_down` is declared `UNAVAILABLE` with that reason, rather than
approximated from the company evidence that is sitting right there.

## What may corroborate what

`lineage.independent(graph, a, b)` walks `depends_on` and answers on
derivation, not on source labels.

| claim about | may be corroborated by | may **not** |
|---|---|---|
| a company | that company's filing + a third party | two documents by the same author at different venues |
| a macro aggregate built from company nodes | an independent macro publisher | any of its own contributing companies |
| a collective construct | behavioural evidence | the economic series the base model already holds |
| a causal bleed | a `PROMOTED` construct that moved the right way | a `CANDIDATE` construct, which explains everything equally well |

The third row is the one the collective layer adds, and it is the reason the
incremental-value experiment is meaningful at all: if a construct were
estimated from the same series the base economic model reads, Model B would
contain Model A's features twice and the delta would measure nothing.

This is enforced structurally rather than by review — `BEHAVIORAL` is its own
node class, and no kind appears in both `MACRO` and `BEHAVIORAL`.

## Derived signals

Every derived value stores its rule and its inputs. `SeriesSpec` refuses a
`DERIVABLE` series that does not state both:

> a derived value whose derivation is not recorded is a number with no
> provenance

Derived nodes enter the graph as `INFERRED`, never `OBSERVED`, and carry
`depends_on` so the independence engine can see through them.

## Publication lag is per-series

`behavioral_ingest._published()` computes `available_at` from the reference
period plus a **per-series** lag: JOLTS runs about 40 days behind, the
household survey about 20. One constant for both would date one of them
wrongly, and `test_publication_lag_differs_per_series` pins it.

`available_at > occurred_at` is asserted for every node. A figure dated to its
own reference period is knowable before it was published, which leaks
hindsight into every historical comparison.

## Failure is reported, never absorbed

A publisher that refuses must not look like a population that did not move.
`collect()` returns `sources_failed` and an `empty_because` string that
distinguishes:

- `"every source failed"`
- `"sources answered with no usable rows"`
- `""` (there is data)

The current live state is the first: BLS returns `REQUEST_NOT_PROCESSED`
because the keyless daily quota is spent by the macro adapter, and the cycle
report says exactly that rather than reporting a quiet economy.

## Tenant privacy

Visibility is a property of the **evidence**, not of the reader — a tenant's
board memo is private wherever it is standing.

`assert_public(nodes, where=...)` raises rather than filtering. A public
aggregate silently built from private material and reported as smaller is a
breach that also lies about its own sample size.

Zero cross-tenant learning by default. The public core additionally cannot
construct an `INDIVIDUAL`-scale population at all.

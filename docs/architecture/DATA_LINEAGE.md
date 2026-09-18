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


---

## The economic state: producer, path, and what re-validates it

*Added at V3 closure.*

### Two legitimate producers, one contract

| producer | writes from | used where |
|---|---|---|
| `market.econ_bridge.publish` | the market engine's own ledger | a deployment that runs a market engine |
| `scripts/publish_econ_state.py` | `reports/panel/historical_panel.jsonl` | the founder preview, which cannot mount the engine's disk |

Both write `state_snapshot` to the same store against the same allowlist, and
`provenance.producer` records which one wrote it. This is **not a fallback
inside the reader**: `econ_context.load` reads one store at one path and says
UNAVAILABLE when it is empty, so "wrong root", "unset root" and "genuinely
empty" stay distinguishable — which is why the reader has no fallback and
must not grow one.

### The prior is a year back, chosen by date

`ConditionReading.direction` is computed against the previous observation
published for that quantity. The first version of the panel publisher wrote
the two most recent rows, so every reading was a one-day or one-month change
against a materiality threshold declared for year-on-year change: one of
thirteen conditions cleared it, and it was moving the favourable way.

Chosen **by date**, not by counting observations back — the series are
irregular, and counting gave a "year-ago" prior sixteen days old for the
high-yield spread. A series that does not reach back a year publishes one
observation and reads NO_PRIOR, which says so.

### The unit decides the transform

The producer stamps `percentage_point` on the series
`econ.release.PERCENTAGE_POINT_SERIES` names. The consumer takes an
arithmetic difference for those and a relative change for everything else —
the same rule the research arm uses, looked up on different sides. The
producer knows the series; the consumer knows the condition; neither needs
the other's vocabulary.

A ratio on a zero-crossing series is not a small error: the 3-month/10-year
slope was −0.02 a year ago and 0.83 now, which as a ratio is a 4,250% move.

### Untrusted on the way in

The state on disk may have been written by an older producer, a newer one, or
a hand edit. `econ_context.load` re-validates it against `econ.state.ALLOWED`
— the same allowlist the producer validated against, declared independently
on this side — and refuses a payload carrying a field it does not recognise
rather than rendering it.

### The seam is derived, not stored

`FounderEconomicContext` is not persisted. It is rebuilt per request from the
state snapshot, the run's stored documents and the run meta, so a redeploy
reproduces it rather than losing it. That is why "survives persistence and
reload" is provable by dropping the process cache and comparing verdicts.

### What may cite what

`Provenance.evidence_type` is an allowlist: `published_series`,
`regulatory_filing`, `company_document`, `shared_economic_state`. A class not
on it cannot support a material change, and the constructor refuses it — so a
private or model-internal figure cannot arrive dressed as a public fact.

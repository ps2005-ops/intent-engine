# Deploy A — what was found, fixed, and left measured

## SEV-1, closed: every `POST /analyze` answered HTTP 500, for hours

Root cause, read from the deployed service's own stderr (Render logs), not inferred:

```
IngestionCorruptLogError: data/company_ingestion.jsonl line 145 is malformed:
  Expecting value: line 1 column 1 (char 0)
```

`create_run` -> `stable_id` -> `find_by_idempotency_key` -> `read_all` parses the
ENTIRE append-only log and raised on the first bad line. `/progress`,
`/runs/<id>` and `/runs/<id>/conversation` make the same read, so one
unreadable byte took every surface down at once — 17 unhandled `/analyze`
errors and 60+ across the other routes in the sampled window.

Not a restart and not transient: `/version` reported the same `boot_id`
across the failures, and a single live probe at 06:00 UTC reproduced it on
the same process (`reference 3b81eb1ee43f`), 24 minutes after the batch died.

### Four defects met at that line

| # | Defect | Repair |
|---|---|---|
| 1 | One malformed line bricks the log permanently | Torn TAIL is truncated and recorded; INTERIOR corruption still refuses |
| 2 | A killed write leaves a partial line behind | `append` is all-or-nothing: the file is truncated back to the last complete record on any failure |
| 3 | The failure surfaced as a raw 500 | `RUN_STORE_FAILURE` / `RUN_SCHEDULER_BUSY` / `RUN_TEMPORARILY_UNAVAILABLE` -> honest 503 carrying the company onto a retry |
| 4 | Every 500 still spent one of ten hourly analyses | Quota is a RESERVATION, committed only when work is scheduled, released otherwise |

A duplicate submission also used to spend a second analysis on a run that
already existed; it no longer does.

## Instrument defect: the batch harness was not driving the customer flow

`pre100_batch_journey.run_company` posted `suggest_cik` and `suggest_ticker`
and never `suggest_domain`, so every company opened on the domainless-filer
path and was analysed from EDGAR alone.

Measured across 132 stored captures:

* every single-family run (`families=investor`) ended in
  `TRUE_EVIDENCE_SCARCITY` or `RETRIEVAL_TEMPORARILY_UNAVAILABLE` — **21 of
  21**, not one full analysis;
* **no capture in the entire corpus** ever reached a company-published page;
* 31 of 67 runs with a readable gate were below the floor of 5 usable sources.

`capture.py` had already been repaired for exactly this. The batch drives the
other module, so the repair had no caller. Scoring 50 companies through this
form would have measured the harness and reported it as the product.

## Product defect, fixed: an HR sentence as the economic engine

Meta's live intro on `f8c183f`:

> Meta Platforms, Inc. is a software platform business that **runs on
> competitive compensation and a wide range of benefits, including many
> learning and development resources**; revenue by displaying ad products on
> Facebook, Instagram, Messenger, and third-party mobile applications.

That is the Human Capital section of Meta's own 10-K read as its product. The
VERB was already guarded here ("operate IS NOT SELLING"); the OBJECT was not.

The discriminator is positional, not lexical. On Meta's 2025 10-K "Human
Capital" occurs exactly once, at character 55,533, and all five employment
matches fall between 55,962 and 59,041. Every risk-factor match is past
159,000. Meta's Business section contains no sentence of this shape at all,
so EMPTY is the honest answer.

After: *"Meta Platforms, Inc. is a software platform business that runs on
revenue from advertising on mobile devices."*

Verified against 11 real 10-Ks pulled from EDGAR: Meta fixed, the other ten
byte-identical. Zero regressions.

## Left measured, not repaired — the predicted Deploy B clusters

### C1. `MODEL_EXTRACTION` — `what_is_sold` returns fragments, not models

The same 11-filing offline comparison shows the extractor is broadly wrong,
and this is one producer, not eleven companies:

| Company | Rendered economic engine |
|---|---|
| Caterpillar | "runs on **and the services we provide**" — dangling fragment |
| Cloudflare | "runs on **to paying customers, and, for certain of our products…**" — fragment |
| Walmart | "runs on **our merchandise, merchandise and selection availability…**" — a competition risk sentence |
| Coca-Cola | "runs on **marketing support and from the sale of which we derive… • "Trademark Coca-Cola Beverages"**" — glossary entry with bullets |
| Costco | a bulleted merchandise-category list |
| Pfizer | "runs on **revenue on bill-and-hold arrangements at the point in time…**" — revenue-recognition policy |
| JPMorgan | empty |

Cause: matching `We <verb> <240 chars>` against raw filing text picks up
glossaries, accounting policies, risk factors and mid-sentence fragments.
Not repaired in Deploy A because the fix is a producer redesign and the
mass-empty fallback is its own defect — the class prior must not become the
answer. The 50-company matrix will size it.

### C2. `REGISTRY_HAS_NO_DOMAIN` — 13 of 50 mega-caps carry no domain

Asked of the product's own `/api/companies`: 37 of 50 return a domain;
13 do not, because they resolve from the SEC registrant table rather than the
curated manifest:

> Meta, Alphabet, Amazon, QUALCOMM, Morgan Stanley, American Express,
> Home Depot, PepsiCo, Merck, UPS, FedEx, RTX, ConocoPhillips

A real customer picking those rows posts no `suggest_domain` either, so they
take the EDGAR-only path in the live product — the same path that produced
21/21 non-full outcomes. §10 names several of these as companies that must
never receive scarcity copy. Meta did produce a full analysis on `f8c183f`,
so it is not automatically fatal; the matrix will say how far it costs.

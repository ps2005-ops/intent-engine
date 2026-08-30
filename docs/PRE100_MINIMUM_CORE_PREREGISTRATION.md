# Minimum-CORE preregistration — frozen before source selection changes

Written **before** any change to which sources CORE waits for, so the
comparison that follows measures the change rather than the chooser. §6.

---

## 1. What was measured first, and on what

Local cold acquisition, one company at a time, every outbound HTTP request
wrapped so the ledger is complete (`scripts/perf_acquisition_ledger.py`).
Local numbers are used ONLY for request counts, byte counts and evidence
composition — never for latency, which is measured on the deployed service.

### 1a. The evidence contract closes long before acquisition stops

`readiness.assess_readiness` is the product's own declared contract for
"this evidence may become a full report". Replaying each run's documents in
retrieval order and asking it after every document:

| company | documents fetched | `READY_FOR_FULL_REPORT` at | fetched after the contract was met |
|---|---|---|---|
| NVIDIA | 13 | **5** | 8 documents, 9.18 MB |
| Microsoft | 8 | **5** | 3 documents, 3.49 MB |
| JPMorgan Chase | 10 | **8** | 2 documents, 0.22 MB |

The state never changes again after it is first reached. Every document
after that index is evidence the customer waited for and the readiness
contract did not need.

### 1b. Nine of NVIDIA's fourteen CORE slots were non-English locale pages

| # | slot | page |
|---|---|---|
| 1 | `cs-cz` | `/cs-cz/about-nvidia/` |
| 3 | `cs-cz` | `/cs-cz/geforce/guides/broadcast-app-setup-guide/` |
| 5 | `cs-cz` | `/cs-cz/geforce/news/` |
| 9 | `da-dk` | `/da-dk/geforce/guides/broadcast-app-setup-guide/` |
| 11 | `de-at` | `/de-at/geforce/guides/broadcast-app-setup-guide/` |
| 12 | `cs-cz` | `/cs-cz/products/rtx-spark/` |
| 13 | `da-dk` | `/da-dk/products/rtx-spark/` |
| 10 | `de-de` | `/de-de/customer-stories/` |
| 4 | `en-gb` | `/en-gb/case-studies/` |

One page — a Broadcast app setup guide — took **three** of the fourteen
slots in three languages, and `/products/rtx-spark/` took two. `readiness`
then discarded four of these as unreadable (`is_english` false), so the run
paid 2.4 MB and four slots for evidence its own gate refuses.

**Cause, and it is not ranking.** `parse_sitemap` returns the first
`MAX_SITEMAP_CHILDREN` children of a sitemap index in document order.
NVIDIA's index lists locale sitemaps alphabetically, so the walk queued
`cs-cz, da-dk, de-at, de-ch, de-de, en-gb` and never reached `en-us`. The
English pages were not out-ranked; they were never discovered. The final
per-family sort then breaks a path-length tie lexicographically, which
prefers `cs-cz` over `en-us` even when both are present.

### 1c. The same public metadata is downloaded on every run, twice

`company_tickers.json` — 795,179 bytes, 10,391 rows, identical for every
company and every run — is fetched **twice per analysis** and never cached.
`company_tickers_exchange.json` (521,231 bytes) is a third copy of the same
class of fact.

### 1d. Every request pays a fresh TCP and TLS handshake

`fetch._default_transport` and `edgar._sec_transport` both call
`urllib.request.build_opener(...)` per request. urllib pools nothing, so one
NVIDIA analysis performs ~36 connection setups where ~4 hosts are involved.

---

## 2. The candidate change

**MINIMUM_CORE**: CORE acquisition stops blocking when the run already holds
evidence satisfying `assess_readiness` at `READY_FOR_FULL_REPORT`. Remaining
approved sources are **not dropped** — they are acquired after `core_ready`,
and if they materially change the recommendation the reader is told through
`ANALYSIS_UPDATED` rather than having the page rewritten under them.

**Source ordering**: locale-neutral and English variants are discovered and
ranked ahead of other-language variants of the same page, and a page already
represented in another language does not take a second slot. Where a company
publishes only in another language, nothing changes.

---

## 3. Required parity — declared before the comparison is run

For each of the ten cohort companies, FULL and MINIMUM_CORE must agree on:

| field | rule |
|---|---|
| company identity | identical resolved entity and CIK |
| business model | no material contradiction |
| major exposures | MINIMUM_CORE names no exposure FULL contradicts |
| provenance quality | every claim still carries a source |
| `CompanyEconomicState` | identical state label |
| DecisionDelta / abstention | no run may become MORE specific on less evidence |
| uncertainty | MINIMUM_CORE's uncertainty ≥ FULL's, never lower |
| risk / recommendation | no material reversal |

Tracked and reported as counts, not prose: **material recommendation
changes**, **missing critical evidence**, **false specificity** (a claim in
MINIMUM_CORE with no supporting document), **DecisionDamage**.

## 4. Thresholds, declared now

- **PASS**: 0 material recommendation reversals, 0 false specificity, 0
  DecisionDamage regressions, uncertainty never decreased.
- **FAIL**: any of the above, or usable reports below 10/10.
- A latency improvement accompanied by a quality failure is a **FAIL**, and
  the change is reverted rather than reported with a caveat. This session has
  already shipped one warm path that was 48% faster because it had stopped
  producing a report.

## 5. What this does NOT authorise

- No increase in requests to SEC, no change to `_FETCH_PER_HOST`, no parallel
  EDGAR dispatch. The two reverted attempts stay reverted.
- No deletion of evidence families. Deferral after `core_ready` is not
  removal, and a deferred source that never arrives is recorded as a gap.

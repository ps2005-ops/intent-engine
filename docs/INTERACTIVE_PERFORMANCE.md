# Interactive performance and reliability

Why this document exists: a real customer typed "Apple" into the deployed
preview, watched **"Reading current company evidence" for 4m54s**, and was
given nothing. Every automated company matrix had passed. Batch coverage and
interactive request-path performance are different tests, and only one of them
had ever been run.

This is the contract, the measurements, and the architecture that meets them.

---

## 1. The contract (frozen before optimizing)

Frozen first, deliberately, so "we hit the target" cannot be achieved by moving
the target. Defined in `src/intent_engine/company_ingestion/deadline.py` and
pinned by `tests/test_interactive_performance.py::test_tier_budgets_are_frozen`.

| | p50 | p90 | hard budget |
|---|---|---|---|
| **Tier 1** — well-known public company | 30s | 45s | **60s** |
| **Tier 2** — deeper / sparse / filer-only | 60s | 80s | **120s** |

A run is tier 1 when it has a website *and* resolves to a listed ticker;
everything else is tier 2 (`WebApp._tier_for`). Holding a filer-only run to the
tier-1 budget would not make it faster, only earlier to give up.

**The quality wall.** Speed may not be bought with evidence. No removing
provenance, economic intelligence, evidence gates, company resolution or
scientific walls to hit a latency number. Every optimization below is either
provably output-identical or is a bounded, *labelled* gap.

---

## 2. What was actually measured

The assumed bottleneck — "data pulling is slow" — was **false**. A cold Apple
analysis, profiled end to end (`scripts/perf_critical_path.py`,
`scripts/perf_cpu_profile.py`):

```
total 27.6s   network 7.3s (26%)   CPU 20.3s (74%)
```

Ranked critical path, before:

| # | Stage / function | Cost | Nature |
|---|---|---|---|
| 1 | `observations.owned_match` | **9.4s (32%)** | pure CPU, zero network |
| 2 | `service.fetch_approved` | 7.7s | 14 independent URLs, strictly serial |
| 3 | `service.discover` | 7.6s | 5.3s of it `_third_party_filing_candidates`, which depends on nothing it was waiting behind |
| 4 | everything else | <0.15s each | flat |

`owned_match` made **15,208 phrase scans across 866 MB of text** for one
company, and **13,821 of them (91%) matched nothing at all**.

Economic intelligence was re-measured and is **not** on the critical path: the
largest `external_intel` entry in the profile is 0.019s. It was left alone.

---

## 3. The repairs

### 3.1 Phrase prefilter — output-identical

`_phrase_pattern` joins a phrase's words with `[\s\-/]+` under `re.I`, so every
word must appear literally in any text it matches. Testing for all of them is
therefore a **necessary condition**, and skipping a scan that fails it removes
no evidence.

`casefold()`, not `lower()`: `re.I` matches ASCII `k` against U+212A KELVIN SIGN
and `s` against U+017F LONG S, neither of which `lower()` normalises. Only ASCII
words become probes; anything else falls back to the full scan.

Proven by differential comparison against the unfiltered implementation:
**2,442 comparisons on 11 real Apple documents, 0 differences**, plus
`test_phrase_prefilter_changes_no_answer` and a positive control.

**Result: 15,208 scans → 2,590. 9.4s → 2.9s.**

### 3.2 Concurrent retrieval — decision order preserved

Only the **network** moved. `_prefetch` acquires the approved URLs
concurrently; the decision loop still walks `targets` one at a time, in the
same order, so the ledger, the byte budget and the failure sequence are
unchanged. Verified: candidate order byte-identical across all 47 candidates,
and `test_concurrent_fetch_preserves_documents_and_order` pins it.

Bounded twice — **6 globally, 2 per host**. The per-host cap is what stops a
concurrent pass from looking like a burst to one publisher; SEC answers 429 to
bursts, and a 429 costs more than the serialism it replaced.

The dead-host breaker survives concurrency and is checked **twice**: before
dispatch (a host already killed) and inside the worker (a host that dies while
candidates are queued behind it). Both are load-bearing; each is pinned by its
own test, because removing either alone left the other standing.

**Result: 7.0s → 2.3s.**

### 3.3 The model call — the last unbounded external call

**Found only on the deployed build.** After the acquisition repairs, Apple's
stall *moved*: `Reading current company evidence` completed at 29.5s (was
312.3s) and the run then sat in `Mapping competitors` for 204.2s.

Composition amplified ~30× from local to deployed while retrieval amplified
~4×, and that asymmetry was the tell. The deployed instance has
`ANTHROPIC_API_KEY` set, so `default_client()` builds a real reasoning
backend; the local runs had no key and were silently profiling **a pipeline
with no model call in it**. A local measurement of a request path the customer
does not receive is not a measurement of the product.

`analyst/runner.py` declares `REQUEST_TIMEOUT_S = 60.0` beside
`MAX_ATTEMPTS = 2`, and a docstring promising "one call, a hard token ceiling,
a timeout, at most one retry". **The constant appeared exactly once in the
whole tree — at its own definition.** `LLMClient` built
`Anthropic(api_key=...)` with no timeout and no retry override, so the real
bound was the SDK default of 600s × the SDK's own 2 retries × the runner's 2
attempts: up to forty minutes for a call the code describes as bounded.

The constant was already right; the **wiring** was missing. It is now passed
to the client, `max_retries=0` takes retry policy away from the SDK (the
runner already owns it, and the SDK default made the real attempt count four
while the log explained two), and `call_tool` accepts a per-call override so a
caller holding an interactive budget spends what it has left.

### 3.4 Parallel discovery

`_third_party_filing_candidates` (EDGAR full-text search) and the sitemap walk
need only the company name and website, and were waiting behind a homepage
fetch they have no dependency on. They now start immediately. The two things
that genuinely depend on the homepage — `discover_candidates`, and the EDGAR
*limit* — remain sequential. The list is assembled in the original order.

**Result: 8.6s → 6.6s.**

---

## 4. The budget

One `Deadline` per analysis, created when the work is queued
(`WebApp._analysis_deadlines`), passed into `fetch_approved`, and consulted by
every stage that spends it.

Before this, each component was separately bounded and the **sum was bounded by
nothing**: 14 sources × 8s connect timeout × 3 attempts + exponential backoff
is minutes, and no component owned that number.

- **Acquisition is bounded; composition is not.** `deadline.reserving(20s)`
  holds back time for the step that turns evidence into an answer. Skipping
  composition to hit a latency number would hit it by deleting the product.
- **A call that cannot finish is not started.** Below `MIN_USEFUL_FETCH_S` the
  budget returns 0.0 — a guaranteed timeout buys nothing.
- **Class shares are cumulative**, not per call. Capping each optional call at
  35% of the budget still lets thirty of them consume all of it.
- **The view shares one clock.** `reserving()` shares `started_at`, the gap
  list and per-class spend, so acquisition and composition cannot report two
  different elapsed times for one request.
- **Unreached sources are recorded, not dropped**: failure type
  `deadline_exceeded`, retryable, and explicitly *not* a finding about the
  company or the host — it is a fact about how long we were willing to wait.
- **Batch callers are exempt.** `Deadline.unbounded()` — batch analysis has no
  customer waiting on it.

### Job lifecycle

`STALE_ATTEMPT_SECONDS` was **15 minutes**; it is now **180s**. That check only
ever fires for a run absent from `_analysis_inflight`, and the in-flight entry
is written *before* the work is submitted — so such a run has no worker in this
process at all. Its worker is provably gone. Waiting another quarter of an hour
to say so is how a restarted instance produced a page that polled itself
forever. 180s is still longer than any run is allowed to take, so a live run
can never be mistaken for a dead one.

---

## 5. Verification

- `tests/test_interactive_performance.py` — 13 tests. Deterministic synthetic
  delays prove the *architecture* (N independent sources cost `ceil(N/k)` waves,
  not N); no test asserts wall-clock latency against the real internet.
- `scripts/break_proofs_performance.py` — 12 mutations, **12/12 held** under the
  hardened harness (source changed, green before, red after, red for the stated
  reason, shared tree untouched). No proof mutates a test.
- `scripts/perf_critical_path.py` — per-stage and per-host timings, duplicate-URL
  detection, network vs CPU split.
- `scripts/perf_live_matrix.py` — the deployed service, per company, cold and warm.

**Four proofs first reported `NOT_CAUGHT`, and all four were findings**, not
harness failures: two tests asserted against the constant they were testing or
were masked by a redundant second guard, one proof site was behaviour-preserving,
and one gap was recorded at two sites. Each was repaired by strengthening the
test, not by weakening the proof.

---

## 5a. The harness was also the load

The first live harness polled every 1s for resolution against a 30s target.
On this instance `/healthz` — sixteen characters, no work — costs **1.89s**
(TTFB 0.5–1.0s; DNS 3ms, TLS 21ms, so it is server time, not network). 28
polls spent roughly 50s of the instance's capacity competing with the single
analysis thread for one CPU share **under the GIL** — the WSGI server is
threaded and the analysis is CPU-bound Python, so every poll contends
directly with the work it is waiting for. The harness then reported that
contention as the product's latency.

The poll cadence now matches the progress page's own 4s `meta refresh`, so it
measures what a customer's browser actually causes.

**`/version` staying fast during a stall is not counter-evidence.** A route
that does no work is fast at any CPU share. An earlier session used exactly
that observation to reject a hypothesis and left the real cause unnamed.

## 6. Benchmark methodology

Local timing does not satisfy the gate. The gate is the **deployed** service,
measured through the customer's own flow with a real cookie jar
(`scripts/perf_live_matrix.py`), because `curl` cannot hold the anonymous
session minted in the 303 that answers `POST /analyze`.

The preview allows **10 analyses per IP per rolling hour**. A ten-company cohort
is the entire hour, so every request is logged with its status before the next
is made, and the run stops on the first 429 rather than spending what is left.

Quota refusal, provider rate-limiting, cold start and genuine latency are
reported as **separate statuses**. Conflating them would report an
infrastructure limit as a product defect.

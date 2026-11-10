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

## 7. CPU calibration and the deployed decomposition (14fc0a1a)

### The question a cpu/wall ratio cannot answer

`wall` high with `cpu` low has two causes that demand opposite repairs:
blocking on I/O, and being descheduled while READY to run. The classifier
used to read `cpu_ms/wall_ms < 0.15` and call it `NETWORK_WAIT`. That labelled
`build_report` — which assembles in-memory structures and cannot perform I/O —
as network-bound. Every such verdict on a compute stage was false.

### The instrument

`latency.cpu_yardstick()` runs a fixed SHA-256 chain: deterministic, no
network, no filesystem, no sleeps, no randomness, and it reports the round
count so two readings can be *proven* to have measured the same work. It
returns wall **and** CPU, because those separate two purchases:

    wall up 9x, probe CPU FLAT   -> descheduled. A larger CPU SHARE is the lever.
    wall up 9x, probe CPU UP 9x  -> a slower core. Share buys NOTHING.

An earlier version recorded `cpu_ms` as a hardcoded `0.0` and could not tell
those apart.

Local baseline, unloaded machine: **13.42ms median, n=15, CV 2.3%,
cpu/wall = 99.8%**. That last figure is the positive control — it establishes
the probe is I/O-free, so a deployed ratio materially below it is the machine
and not the workload.

### Result (Apple, preview, 14fc0a1a)

    probe at t=0              112.01ms wall /  25.90ms cpu  ->  8.35x
    probe after composition   196.63ms wall /  27.26ms cpu  -> 14.65x
    core speed                2.04x slower per unit of work
    scheduling stretch        4.32x -> 7.21x wall per ms of CPU granted
    EFFECTIVE_CPU_SHARE_ESTIMATE ~7-12% of one local core

`CPU_SCHEDULING_CONSTRAINT = CONFIRMED` on all five conditions: the I/O-free
yardstick slows materially, multiple compute-only stages match the same
factor, CPU work is comparable once bytes are accounted, the effect reproduces
at both ends of the run, and no hidden I/O is needed to explain it.

### Predict from deployed CPU, never from local wall

`expected = local_wall * slowdown` reported 25-30s "unexplained" and pointed at
an application defect that does not exist. The deployed run had scanned
**457,220 characters against 244,712 locally (1.87x)** — a different workload,
not a different machine. Using each stage's own deployed CPU instead,
`expected = deployed_cpu * stretch`, every compute stage lands within 5-9% of
prediction and the residual falls to **0.0s**.

Any local-vs-deployed comparison must therefore record the WORK done (bytes,
rows, items), not just a count of things: 11 documents against 10 concealed a
1.87x difference in characters.

### Decomposition of the 90.7s CORE

    network wait (I/O)            40.5s   bounded by timeouts/concurrency
    CPU-starved compute           50.0s   a larger CPU share is the lever
    beyond the measured share      0.0s   nothing left to explain

    of which WORK NOTHING READS   18.0s   removable regardless of machine (20%)

Keep the buckets separate. Network wait is *explained by I/O*; folding it into
"unexplained by CPU" would let a hardware verdict absorb 40s of waiting on SEC.

### The application defect a hardware verdict would have buried

`_strategic_report` computed

    evidence = derive_analyst_evidence(documents, company_name)

a second full scan of every retrieved document — and every use of `evidence`
sat after `if not deep: return payload`. On the interactive CORE path the
value was built and discarded: 587.5ms locally, **18.0s deployed, 20% of
CORE**. The function is pure (no I/O, no writes, one return), so this was
established by reading rather than by inference; its cost was predicted from
its structural twin `derive_observations` to within 2% local and 5% deployed
before any span existed to confirm it.

Being "explained by the CPU share" is not the same as "should exist". A faster
machine runs dead code faster.

### Budgets are predictions about a machine

`COMPOSE_RESERVE_S = 20.0` was set from "composition costs 7-11s locally and is
pure CPU, so it is the one stage whose duration we can predict". The premise
holds; the constant does not travel. Composition is 50.29s on the preview and
~26s even after both repairs. A reserve cannot be one number shared by machines
that differ 8-15x in scheduling.

### Rules this cost us

- **Never edit source while a guard or suite runs.** Structural tests and break
  proofs read files from disk; a tree that changes mid-run yields a result
  about no particular revision.
- **Nested spans are a breakdown of a parent, not time beside it.** Summing
  across all spans counts the same seconds up to four times — it produced
  `covered > total` once, and "68.8s of 90.2s unexplained (76%)" once, where
  the true figure was a quarter of that. Sum OWN time.
- **Read `git diff --cached --stat` before every commit** and account for every
  deletion. It has caught a module overwrite, a mis-indented 51-line call, and
  an edit referencing a helper that did not exist.
- **Adding a keyword-only parameter breaks every test double of that method**,
  and the break reports as the failure under test rather than as a broken test.
  Three occurrences here.
- **`find -newermt '-60 minutes'` errors on BSD/macOS** and prints nothing,
  which is indistinguishable from "nothing changed". It reported a clean tree
  while three files were being written by another session.

## 8. PRE-100 product phase: what was repaired, and what the cohort says

### The measurements that drove it

Ten companies, one SHA, same harness, twice — before and after two repairs:

| | c7c28d52 | 7948b3b8 |
|---|---|---|
| CORE p50 | 104.7s | **78.3s** |
| CORE p90 | 134.0s | **87.4s** |
| CORE max | 141.1s | 132.5s |
| usable reports | 10/10 | 10/10 |
| DEEP completed | 4/10 | 7/10 |
| mean discovery | 23.2s | 17.5s |
| mean retrieval | 25.2s | 19.6s |
| mean composition | 44.0s | 21.5s |

Generalization is not in question: ten companies across platforms, payments,
banking, retail and industrials all produced a real report with 7–15 evidence
items, no company-specific behaviour and no failures. The performance gate is.

### What each repair actually did

**The 120s maximum now bounds the stage that spends the time.** `may_start()`
decided whether a *fetch* could begin; nothing bounded composition, which was
44s of a 107s median. The deadline is threaded
`compose_with_quality → compose → _strategic_report → derive_observations`,
and the document loop stops when it expires — **between** documents, never
inside one, because a half-read document yields an excerpt that is not what
the document says. Composition fell 51%.

**An optional source may not decide how long the reader waits.** The
third-party filing search was bounded by `deadline.remaining` — 40s on a 60s
budget after the composition reserve — so the bound existed, was correct, and
never once fired. `CLASS_SHARE` says what a class may spend *cumulatively*; it
had no answer for what one branch may spend *waiting*. Both optional discovery
branches now take an 8s cap on top of the budget. Discovery fell 24%.

**Snapshot reuse works, and does not help a cohort.** `PublicCompanySnapshot`
eliminates discovery on a repeat analysis: −99% (32.8s → 0.17s Microsoft,
23.9s → 0.23s Apple), CORE −21%/−25%, reports composed and evidence intact. A
50-company qualification is 50 *first* analyses, so none of that saving
appears in it. Warm runs are a returning-reader benefit, not a cohort one.

### Why more CPU is not the whole answer

Composition consumes 3.71s of CPU over 25.10s of wall on this instance —
**14.8% of a core**. Scaling only that bucket by the measured share, holding
the network constant:

| CPU | p50 | p90 |
|---|---|---|
| current | 76.5s | 79.0s |
| 2× | 63.0s | 67.6s |
| 4× | 56.1s | 62.2s |
| full core | 53.3s | **60.0s** |

A realistic one-tier jump does not reach the gate. A fully unstarved core
lands exactly on p90 60.0s and still misses the ≤30s p50 preference. The
application repairs bought 26s; CPU is worth roughly another 23s; the
remaining ~37s is network wait against SEC and company hosts, which neither
buys.

### Two acquisition repairs attempted and reverted

Both were plausible latency savings that changed behaviour toward an external
host, and both were refused by something the repository had already recorded.

**Per-host fetch concurrency 2 → 4.** Justified on the grounds that SEC's 429s
are company-correlated rather than cadence-correlated. That claim could not be
cited from this repository, and `docs/INTERACTIVE_PERFORMANCE.md` records the
opposite as measured. `test_concurrency_is_bounded_per_host` asserts a
*literal* 3 rather than `_FETCH_PER_HOST + 1`, precisely so the product cannot
raise its own bound — and it caught this. To revisit: instrument 429s per host
against concurrency on the live service, record the result here, then move the
guard and the constant together.

**EDGAR dispatched in parallel with the homepage fetch.** It waits 11.2s for
an input it never reads — it needs the name and CIK, both already in `meta`.
The only real dependency is its *limit* (5 filings if our own site refused us,
3 if it answered), so early dispatch means asking for 5 and truncating. That
is output-identical in the candidate list and **not** in request count: every
healthy run would make two extra requests to SEC.
`test_the_blocked_budget_is_strictly_larger_and_is_the_one_used` pins the
property that broke. A correct version needs an *offset* on the proposal, so a
blocked run tops up 3 → 5 rather than re-asking for 5.

### Standing limitations

- **Feedback (live):** `BLOCKED_INFRASTRUCTURE`. `feedback_available()`
  requires `DURABLE_PROVEN`; the preview has no persistent disk, so the form
  stays off rather than promising to keep what it is sent. The implementation
  is complete and tested and activates itself when durability is proven.
- **Restart durability:** `BLOCKED_INFRASTRUCTURE`. Snapshots and runs live on
  the ephemeral runtime root and are lost on redeploy. Cold/warm is therefore
  measured inside one deployment lifetime and is **not** restart-survival
  evidence.
- **Benchmark throughput:** 10 analyses per IP per rolling hour. A
  50-company qualification is ~5h of wall clock at that rate.

---

## 9. PRE-100 closure: minimum-evidence CORE

### The measurement that redirected the work

The previous section ends with "the remaining ~37s is network wait", and
that framing was wrong in an instructive way: it named a CATEGORY. Measured
with a complete request ledger (`scripts/perf_acquisition_ledger.py`), the
category contained four separable causes, and the largest was not network at
all.

**The product's own evidence contract closed long before acquisition
stopped.** `readiness.assess_readiness` decides whether evidence may become a
full report, and it was consulted AFTER all fourteen approved sources had
been paid for. Replaying each run's documents in retrieval order and asking
the contract after every one:

| company | fetched | `READY_FOR_FULL_REPORT` at |
|---|---|---|
| NVIDIA | 13 | **5** |
| Microsoft | 8 | **5** |
| JPMorgan Chase | 10 | **8** |

The state never changed again. Two to eight documents per run were acquired
after the contract was satisfied, with the customer waiting on every one.

**Nine of NVIDIA's fourteen CORE slots were non-English locale pages**, one
page took three of them in three languages, and `is_english` then discarded
four. The cause was not ranking: `parse_sitemap` truncated an alphabetical
sitemap index at eight children, so `en-us` was never queued. The English
pages were not out-ranked, they were never discovered.

**`company_tickers.json` — 795,179 identical bytes — was downloaded twice per
analysis**, and every request built a new opener, so ~32 of one run's 36
connections were avoidable handshakes.

### What changed

Acquisition runs in waves and consults the readiness contract after each.
When it closes, CORE stops BLOCKING; the untouched sources are DEFERRED and
acquired after `core_ready` on a FRESH budget (`Deadline.for_continuation`),
because handing the continuation the spent interactive deadline would refuse
every deferred source as `deadline_exceeded` — deferral becoming deletion
wearing a retrieval failure.

"Nothing is dropped" is enforced as an ACCOUNTING property inside one run:
every deferred candidate is either retrieved or carries a recorded failure.
It cannot be tested by comparing a CORE run against a separate FULL run —
measured, one such comparison had the FULL path retrieve FEWER documents than
the CORE path.

Locale-partitioned sites are recognised only in the unambiguous `xx-yy` form
and only when a site exposes two or more distinct ones, so a company that
publishes in one language is unaffected. Registry metadata is cached per
deployment (strictly a SMALLER ask of SEC), and connections are pooled with
stdlib `http.client` — `requests`/`urllib3` are in requirements.txt but NOT
in pyproject, and deployment builds with `pip install -e .`.

### Measured on the deployed service

| | `7948b3b8` | `13732a6b` |
|---|---|---|
| CORE p50 | 78.3s | **60.9s** |
| CORE p90 | 87.4s | **73.0s** |
| usable reports | 10/10 | 9/10 |

Across the ten-company cohort, 92 → 62 documents block CORE. Companies with
nothing to spare defer nothing: JPMorgan and Visa deferred zero, which is the
mechanism behaving as specified — the stop is the contract, not a count.

### Two defects this created, and how they were found

**A read ran the deep pass on the request thread.** Five of ten cohort runs
answered `result_state: FAILED` with `deep_status: RUNNING` — exactly the
five with deferred evidence. `RUNNING` is set before the analyst call and
finished only by `enrich_deep`, so that pair has one producer. `_compose`
defaults to `deep=True` and `_real_result` called it on a stale-cache read,
so a READER asking for a page ran the whole deep pass synchronously and
published its failure over a good core. Code-reading first blamed the
deferred recompose; a local reproduction disproved that. The `deep_status`
field is what named the real path.

**A read stored None and stranded the reader.** The repair returned the
PREVIOUS result when a recompose produced nothing usable — and on a cache
miss "previous" is None, so None was stored under the run's key. That is a
poisoned entry, not a missing one: the key exists, so nothing refills it.
Amazon marked `core_ready` at 58.3s and its page never opened inside 300s.
The FIRST fix for that was worse again — returning early without storing
anything meant every read recomposed, an unbounded rebuild on the request
thread. A read now stores what it composed and only refuses to let a FAILED
recompose replace an answer that already exists.

### A note on diagnosis

A guard was killed at 2h52m on the belief that one test was hung. The test
passes in 100s on an idle machine; the guard was contending with a live
cohort. Two revisions were bisected against a test that had already passed
two full guards, which should have falsified the premise before the bisect
began. Wall-clock on a shared machine is not evidence about code.

### PRE-100 50-company qualification (`229c75eb`)

Frozen cohort, one deployed SHA, paced across the demo quota
(`scripts/pre100_qualify50.py`, resumable, never reordered or cherry-picked).

| | |
|---|---|
| attempted / counted | 50 / 50 |
| usable reports | 44 |
| bounded abstentions | 5 |
| no result | 1 |
| terminal | 48 |
| CORE p50 / p90 / p95 / max | **63.8s / 80.2s / 88.4s / 96.4s** |
| ≤60s / ≤90s / ≤120s | 15 / 40 / 48 |
| enum leaks | 0 |
| Q&A sampled | 5 companies × 5 questions + follow-up, all answered |

**The five abstentions are host-side, not application defects.** Goldman
Sachs, Caterpillar, Ford, J&J and Eli Lilly each retrieved zero documents
under sustained cohort load. Run locally through the same code, Goldman Sachs
retrieves nine documents — its own domain refuses all three requests and SEC
serves sixteen. The product's response is correct: a bounded, labelled
refusal, terminal inside the contract.

**Chevron's `NO_RESULT` was a submission-time capacity refusal**, not an
endless spinner: `run_state` was None, so no run was ever created. Re-run
with two controls it is terminal at 65.0s with five documents. The harness's
abstention detector requires a terminal `run_state` and therefore cannot see
a refusal that happens before a run exists — an instrument limit, recorded
rather than repaired, because the product behaviour is correct.

**Costco at 128.2s** is the only run past the 120s contract, at 96.4s
`core_ready` plus page-open detection at 4s poll granularity.

### PRE-100 requalification on `b5b4bd2a` (admission repair)

Frozen cohort, one SHA, paced across the demo quota. The original `25409f14`
cohort is preserved unchanged in
`reports/perf/pre100_qualify50_25409f14_original.json`.

| | `25409f14` | `b5b4bd2a` |
|---|---|---|
| usable reports | 44 | **26** |
| bounded abstentions | 5 | **23** |
| capacity refused | — | 0 |
| analytical outcomes | 49/50 (98%) | **49/50 (98%)** |
| terminal observed | 48/50 | **49/50** |
| CORE p50 / p90 / p95 | 63.8 / 80.2 / 88.4 | **66.8 / 81.2 / 97.0** |
| page-open ≤120s | 48/50 | **48/49 observed** |
| enum leaks | 0 | **0** |
| distinct briefs | 50/50 | **50/50** |

**The usable/abstain split moved sharply and the reason is load, not code.**
Twenty-three runs reached the evidence-insufficiency path, which renders a
labelled page — verified live on Deere & Company: `run_state FAILED`,
evidence 8, and a reader-facing page naming the refused hosts (g2, trustpilot
answering 401/403) and saying "this run did not add enough independent
evidence to strengthen it. Rather than show a briefing that looks complete
and is not, here is exactly where it stands", with three retry actions. That
is correct behaviour, and it is NOT a usable report; the two are counted
separately here for that reason.

**An abstention is not a capacity refusal and neither is a report.** The
harness records three terminal classes. Only usable reports and abstentions
count toward the usefulness gate; capacity refusal counts only toward
terminal semantics, because "I could not start" is infrastructure behaviour
and "I ran and could not conclude" is analytical behaviour.

**Instrument corrections made during this cohort**, each of which would
otherwise have misreported the product:

- `USABLE_NO_REPORT` was not a product state. The harness read `result_state`
  from `/timing`, which reflects `_results` and is empty for a run whose
  worker took the insufficiency path — so twenty-three correct abstentions
  were recorded as failures until the live page was read.
- The abstention detector required ZERO evidence, so an abstention holding
  four or eight documents fell through it.
- `/timing` and the rendered page do not read the result through the same
  accessor: the page recomposes through `_real_result`, `/timing` does not,
  so a diagnostic surface can report "no result" for a run that renders.

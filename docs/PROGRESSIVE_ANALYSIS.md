# Progressive analysis — CORE_READY before DEEP_READY

The interactive product is the **core analysis**. The strategic reading is an
**enrichment of it**, not a precondition for it.

---

## 1. Why this exists

Measured on the deployed service, in order:

| | Apple, to a readable result |
|---|---|
| Before any performance work | **317.3s**, 312.3s of it in one stage |
| After the acquisition repairs | **240.1s** — evidence stage now ~28s |
| Of that 240s | **~200s was one synchronous model call** inside composition |

The acquisition repairs worked. The model call then became the whole problem,
and **no timeout fixes it**: the call was bounded correctly (60s, `max_retries=0`)
and the number barely moved, because the defect was never the bound — it was
that a reader had to wait for it at all. Bounding it harder truncates the
analysis, which the quality wall forbids.

So the repair is architectural.

## 2. The cut was already in the code

`_strategic_report` builds a complete, evidence-grounded report, labels it
`reasoning_provenance = "pattern_library"`, and *then* calls the model — with
an `AnalystUnavailable` path that already returned the earlier payload.
Progressive analysis is that existing line made explicit.

```
acquire evidence
      │
      ▼
build_strategic_report        ← deterministic, this company's own evidence
      │
      ├──────────────► CORE_READY   published, persisted, openable
      │
      ▼
analyse()  (the model)        ← DEEP
      │
      ▼
merge into the SAME analysis  ← DEEP_READY
```

**The page needed no change.** `_availability` reads `strategic_report` out of
`self._results`, and `result_readiness` opens the analysis the moment one
exists — in flight or not. Publishing the core is what makes it openable.

## 3. What CORE is, and what it refuses to be

CORE carries what this company's **own retrieved evidence** establishes:
observations, shifts, timeline, source coverage, evidence gaps, provenance,
source library, plus the economic seam (CompanyEconomicState, EconomicState,
exposure, DecisionDelta / abstention) which the request already memoizes.

CORE does **not** promote `hypotheses`, `patterns` or `blind_spots` to
findings in order to look complete. Those come from the pattern library, they
are generic by construction, and the codebase already labels them *"structural
scaffolds, not findings about this company."* Filling the gap with them would
hit the latency target by spending the one thing that may not be spent on it.

`strategic_analysis` stays `None`. The state says `DEEP_PENDING`.

### DEEP_PENDING is deliberately not an evidence state

`ResultState` already separates states caused by **the evidence** from states
caused by **us** — because a reader told their evidence is thin goes and
collects more sources, which cannot help when the real answer is "we have not
run the reasoning yet". `DEEP_PENDING` is the second kind, and is excluded
from `EVIDENCE_EXPLAINED` for exactly that reason.

## 4. Deep status

| `deep_status` | meaning |
|---|---|
| `PENDING` | core published; the strategic reading has not started |
| `RUNNING` | the model call is in flight |
| `COMPLETE` | merged into this analysis |
| `FAILED` | the model failed; **the core is untouched and still readable** |
| `UNAVAILABLE` | no reasoning backend configured |

## 5. Merge, never replace

`enrich_deep` mutates the analysis the reader already opened. Only the fields
the reasoning layer owns move — `strategic_analysis`, `result_state`,
`reasoning_provenance`, `critic_findings`, `strategic_memory`, `daily_view`,
`evidence_count`. The evidence, coverage and provenance are the same objects
they were.

There is never a second report, so there is no window in which two documents
about one company disagree.

### Material changes are recorded, not silent

If the deep reading changes a field the executive acts on, `deep_changes`
records `{field, core, deep}`. The fields are enums and identifiers, so a
wording change cannot manufacture one.

## 6. Failure semantics

A deep failure costs the deep half **and nothing else**. It is caught in the
worker, outside the handler that marks a run `FAILED`, because a run that
produced a usable core did not fail. `deep_status` says what happened.

## 7. Two defects this work surfaced

**A shared mutable ledger across threads.** `_prefetch` hands one
`RetryLedger` to up to six workers and every counter on it is a
read-modify-write. A lost `charge()` is not a cosmetic miscount: `remaining()`
decides `mark_exhausted()`, so it can retire a host that was answering, which
presents as "no evidence collected". Now locked.

Its break proof is **structural, and labelled as such**: the stress loop does
not reliably lose a charge under CPython — the GIL usually completes the write
inside one bytecode window — so it passed with the lock removed, measured as
`NOT_CAUGHT`. A guard that cannot fail is not a guard, so the property is
asserted where it is decidable.

**A run-scoped key on per-pass content.** `_record_reasoning` keyed on
`reasoning:{run_id}:{len(documents)}`, which was true while a run reasoned
once. Progressive analysis reasons twice over the same documents, so the count
matched and the payload did not.

The key now names its content — but the real defect was underneath it: a CORE
pass has not called the analyst, so recording it as a reasoning attempt enters
`attempted=True, accepted=False` for a pass that never asked. Since
`reasoning_overview` divides acceptances by attempts, it would have halved the
operator's measured analyst-acceptance rate using runs that never tried. The
core pass is no longer counted as an attempt.

## 8. Verification

- `tests/test_progressive_analysis.py` — 9 tests. Order and survival, not
  seconds: a slow deep pass makes the two milestones separable.
- `scripts/break_proofs_progressive.py` — **10/10 held**.
- `scripts/break_proofs_performance.py` — **18/18 held**.
- `scripts/perf_progressive_matrix.py` — the deployed service, two clocks.

Measured locally with a deliberately slow deep pass: **core readable at
13.12s, worker continued 9.65s afterwards**, deep failed, core survived, run
not marked FAILED.

Five of the ten new proofs first reported `NOT_CAUGHT` or `WRONG_REASON`, and
every one was a finding: a `None or X` no-op mutation, two redundant guards
masking each other, a fake deep payload carrying identical fields, and an
assertion ordered behind a weaker one.

## 9. What the deployed measurement actually found — and what I got wrong

The progressive split works, and it **did not improve deployed latency**.
Both statements are true, and the second one corrects the previous run's
diagnosis.

| | Apple | Microsoft |
|---|---|---|
| Deployed, before progressive (model inside compose) | 240.1s | — |
| Deployed CORE_READY, model deferred | **264.4s** | **200.5s** |
| Local, deterministic, end to end | 12.6s | 28.6s |

### The model was not the dominant cost

The previous run concluded that ~200s of Apple's 240s was the synchronous
model call. That was an **inference, never isolated**: composition amplified
~30x from local to deployed while retrieval amplified ~4x, and the deployed
instance has an API key while the local one does not — so the model looked
like the difference.

It was not. `ANTHROPIC_API_KEY` is absent locally, which means **every local
profile was already the deterministic-only path**. With the model now deferred
out of the core entirely, the same stage still takes ~170–230s. The
deterministic composition and acquisition are the cost.

### The server is not starved either

The other candidate explanation was GIL/CPU contention: the core is published
early but no request can be served while the worker runs, so the publish
cannot be observed. Measured directly, with `/healthz` (sixteen characters, no
work) polled every 3s throughout a live analysis:

```
idle                0.19s
during the run      0.50s median, 1.40s max, 58/58 OK, 0 failures
slowdown            2.6x
```

The server is responsive. Process separation (§28) would not recover the time,
so it is not the repair — which is worth knowing before building it.

### What the cost actually is

Local Microsoft, deterministic: discover 12.99s, fetch 9.65s, **core compose
5.93s**. Deployed CORE 200.5s — roughly 7x end to end, with CPU-bound
composition amplifying far more than network-bound acquisition.

The application architecture is correct: the core is genuinely separable, is
published first, and survives a deep failure. The instance cannot run it
inside a 30-second budget.

### The Tier-1 cohort, deployed

| company | CORE_READY |
|---|---|
| Amazon | 187.3s |
| Microsoft | 200.5s |
| Meta Platforms | 209.8s |
| Alphabet | 212.0s |
| NVIDIA | 214.8s |
| Apple | 264.4s |

**6/6 reached a readable core. Zero failures, zero hangs, zero refusals.**
p50 **210.9s**, p90 214.8s, max 264.4s — and every one of the six is over the
60s hard budget, at 7.0x the 30s p50 target.

The spread is 77s across six very different companies. That tightness is the
finding: a per-company evidence problem would scatter, a fixed CPU multiplier
would not. The cost is systemic.

### DEEP_READY is not measurable with the current instrument

`result_state_detail` renders only when **no key insight cleared the bar**,
and the core produces one from the pattern library — so the `DEEP_PENDING`
sentence never appears on the page and its absence proves nothing.

The harness reports `MARKER_NEVER_SEEN` / `NO_PENDING_ON_FIRST_POLL` rather
than treating absence as success. It would otherwise have reported a DEEP
time of "immediately" on every company, which is the false pass this run was
most at risk of. **DEEP_READY is therefore unmeasured, not passing.**

## 10. Not built in this run

Named rather than counted as done:

- **Evidence snapshot / prewarm** (§32) — not built. Cold path only.
- **Separate worker process** (§28) — not built. Web serving and analysis
  still share one interpreter and contend under the GIL.
- **Persisted job-state machine** with `DEEP_ANALYSING` as a durable state
  (§34) — `deep_status` lives on the analysis, not on a persisted job record.
- **Recompose classification** (§21) — the late-evidence recompose is gated on
  the readiness verdict changing, not on a `DUPLICATE` /
  `MATERIAL_NEW_INFORMATION` taxonomy.

Three §48 break proofs correspond to these and are **not claimed**: there is
nothing to mutate, and a proof against unbuilt behaviour would be theatre.

## 10. Where the deployed time goes — two hypotheses killed, one proven

Section 9 established that the model was never the bottleneck and that the
server stays responsive. It concluded the instance "cannot run it inside a
30-second budget". That conclusion is right, but `/healthz` does not
establish it: a sixteen-character endpoint needs almost no CPU, so it stays
fast on a throttled instance while the WORKER is throttled hard. It rules out
GIL/web contention, which is a different question.

### The measurement that isolates CPU

Serving an already-composed report page is pure CPU and zero network
(`/runs/<id>` reads the cached `_results`; the only `_compose` on a read path
is `/retry`, which is a deliberate second look). Local and deployed pages are
within 2% of the same size, so this is like for like:

| | time | size | rate |
|---|---|---|---|
| local render | 466.9 ms | 29,630 chars | **16.14 ms/KB** |
| deployed `/` | 8,850 ms | 29,081 chars | 311.63 ms/KB — **19.3x** |
| deployed `/brief` | 10,750 ms | 52,516 chars | 209.61 ms/KB — **13.0x** |

### Hypothesis 1 — the append-only ledger. FALSIFIED.

`for_run` is `[r for r in self.read_all() if r.run_id == run_id]` and
`read_all` returns `list(self._cache_rows)`, so every query copies and scans
the WHOLE ledger. Local ledgers hold one run; the preview holds every run ever
made, which would make this a defect that only exists in production. It is
not the cost:

```
ONE RENDER makes: read_all=10  for_run=10

rows=  2,000   store cost ~  0.7 ms
rows= 20,000   store cost ~  7.8 ms
rows=100,000   store cost ~ 92.4 ms
```

92 ms at 100,000 rows is ~1% of the deployed 8,850 ms, and rendering the same
run's page was flat (476.6 -> 471.2 ms, 0.99x) while unrelated runs grew the
ledger 27x. Linear in N, and far too small at any plausible size. Worth
fixing one day for its own sake; it is not this.

### Hypothesis 2 — CPU throughput. HELD.

What remains is that the instance executes the same deterministic Python
13-19x slower. That is consistent with every other observation, and the
alternatives are not: composition amplifies ~30x while network-bound
acquisition amplifies ~4x (CPU-bound work amplifies, I/O-bound work does
not), and the Tier-1 spread is 77s across six very different companies (a
per-company evidence problem scatters; a fixed multiplier does not).

### The requirement, stated exactly

Deployed CORE p50 is 210.9s against a 30s target and a 60s hard budget. The
deterministic work is ~13-19x slower than a developer machine, so the
interactive budget needs roughly an order of magnitude more CPU throughput
than the preview currently has — a dedicated-CPU plan, not a shared one.
`render.yaml` declares `plan: starter` for `intent-engine-web`, but the
preview is configured through the Render dashboard rather than the Blueprint
(`config/preview.yaml`), so its actual plan is not recorded in this
repository and should be read from the dashboard before sizing.

**This is BLOCKED_INFRASTRUCTURE, not a code defect.** The application
architecture is correct: the core is separable, is published before the model
runs, and survives a deep failure. Nothing in this repository will move
210.9s to 30s.

### A broken instrument, found and fixed

`evidence_citations` reported 0 for all six Tier-1 companies. It counted
`https?://` in the body, and the report cites evidence through INTERNAL
routes (`/runs/<id>/evidence/<claim>`) -- the rendered HTML contains no
absolute href at all, so the counter could never return anything but zero.
Six identical zeros were the tell: a real per-company evidence problem
scatters. Fixed to count the link the page actually emits. No conclusion
about evidence coverage should be drawn from any run measured before this.

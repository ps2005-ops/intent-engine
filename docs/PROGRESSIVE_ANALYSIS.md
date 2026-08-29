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

## 9. Not built in this run

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

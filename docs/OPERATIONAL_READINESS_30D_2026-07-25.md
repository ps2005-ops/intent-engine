# Operational Readiness Report — 30 Market-Day Replay

**Date:** 2026-07-25
**Scope:** the hosted daily/weekly/monthly job cycle (`intent_engine.hosted.jobs`),
paper execution + reconciliation, prediction resolution, durable storage, and
the dashboard read path.
**Method:** a deterministic 30-market-day operational replay that drives the
**real** job code (not a mock of it) through the durable store and the Alpaca
paper broker fake, with adversarial faults injected, then audits durable state
for invariant violations.

This report is evidence-first. Every claim below is reproducible with:

```
python scripts/ops_replay_30d.py reports/ops30_replay_ledger.json     # one run
for i in $(seq 1 15); do python scripts/ops_replay_30d.py /tmp/l.json \
  | grep failures; done                                               # repeat run
```

The replay is run **repeatedly**, not once. A single run is not evidence of
reliability: two of the eight defects below were **timing-dependent** and a lone
run showed them green. Only repeating the run (crossing wall-clock second
boundaries) exposed them — which is exactly how they would have manifested in
production, silently, days later.

The full machine-readable ledger for the run this report describes is committed
at [`reports/ops30_replay_ledger_2026-07-25.json`](../reports/ops30_replay_ledger_2026-07-25.json).

---

## 1. Method — why this is a stress test, not a demo

`scripts/ops_replay_30d.py` runs the actual `JOBS` registry over 30 business
days. Prices, research, and predictions are injected deterministically; the
jobs, durable store (`DurableStore`), order/prediction repositories, and the
`FakeAlpacaPaperBroker` are the real production objects. Seven realistic faults
are injected so latent defects surface instead of hiding:

| Injection | Day | What it exercises |
|---|---|---|
| Scheduler **miss** (after-close skipped) | 2026-01-12 | catch-up recovery |
| **Double-fired** generation + submit | 2026-01-15 | idempotency (no double-trade) |
| **Transient missing price** on resolve | 2026-01-19 | must not crash; retries next run |
| Broker **reject** | 2026-01-22 | reconcile to rejected, never fills |
| Market **holiday** (all jobs skipped) | 2026-01-29 | gap then resume |
| Persistent **downtrend** (DUOL) | all | losing book → learning candidate |
| **Future-dated evidence** every refresh | all | leakage must be blocked daily |

After the run, the harness audits durable state for reconciliation invariants
(R1–R6), dashboard consistency (D1–D2), and equity-snapshot coverage.

---

## 2. Headline result (final run)

```
market_days                : 30
job_runs                   : 210   (210 succeeded, 0 failed)
failures                   : 0
skipped_jobs               : 2     (1 injected scheduler miss + 1 holiday)
scheduler_misses           : 2     (both injected; both recovered next run)
reconciliation_issues      : 0
prediction_errors          : 43    (genuine misses — recorded, not defects)
dashboard_inconsistencies  : 0
learning_candidates        : 3
leakage_blocked            : 116   (future-dated evidence blocked every refresh)
```

**Verdict: ready for a supervised going-forward paper run.** All injected faults
were absorbed with no lost or duplicated records, no crash, and no invariant
violation, held **stable across 15 consecutive runs** (0 failures each). The
open reliability defect from the first pass (positions held after resolution) is
closed and tested; two further timing-dependent crash defects surfaced by
repeated runs are root-caused and fixed (§3.1). Remaining caveats — all about
the *environment* the replay stands in for, not the code — are in §7.

---

## 3. Defects found and fixed

The replay surfaced **eight** material defects. All eight are fixed; none was a
cosmetic change. Each row is a correctness or reliability defect that a
going-forward run would actually hit.

| # | Defect | Root cause | Fix | Evidence it's closed |
|---|---|---|---|---|
| 1 | Job wrapper **crashes** when a job fires twice in one second | execution `run_id` built from `name:as_of:now()` at **second** resolution → idem-key collision | ULID per invocation (`hosted/records.py`) | 210/210 job runs succeed incl. double-fire day |
| 2 | After-close job **fails** as evidence accrues | `CandidateStore.propose` froze idempotency on `cand:{id}`, but a candidate's evidence changes as outcomes accrue → `IdempotencyConflict` | content-signature idem key (`hosted/candidates.py`) | `failures: 0`; 3 candidates evaluated over 28 samples |
| 3 | **Double exposure** from double-fired generation | generation not idempotent per (company, day) | skip company already predicted today (`hosted/jobs.py`) | R4 `duplicate_same_day_exposure: 0` |
| 4 | **Multiple simultaneous positions** in one instrument | no portfolio-level "one open position per instrument" gate at submit | exposure gate in `paper-order-submit`; all rejects persisted | 84 `duplicate_instrument_exposure` rejections persisted; R6 simultaneous exposure = 0 |
| 5 | Weekly-eval **crash** on rapid re-run | `record_evaluation` keyed idempotency on a wall-clock second | content-signature idem key | `failures: 0` across 5 weekly evals |
| 6 | **82 positions held at the broker after resolution** (buying power consumed without bound) | position opened per prediction but **never closed** at horizon | idempotent, catch-up `close_resolved_positions` wired into after-close (`paper/reconciliation.py`, `hosted/jobs.py`) | **stranded_after_resolution: 82 → 0** (see §6) |
| 7 | After-close job **crashes** when a company's metrics are flat day-over-day | `propose`'s content-signature excluded `created_at`, but the **persisted payload still carried** a wall-clock `created_at` → same idem_key, different bytes → `IdempotencyConflict` | store ignores volatile write-stamps in the idempotency fingerprint (§3.1) | A/B proof: pre-fix crashes, post-fix dedupes to 1 row |
| 8 | Submit job **crashes** re-recording a repeated rejection | `_reject` payload embedded `at: now()` under stable key `reject:{pred}:{inst}:{rule}` → same key, different second → `IdempotencyConflict` | same root fix (§3.1) | forced advancing-clock re-record x3 → no crash |

Defects #6, #7, #8 were completed in this pass; #1–#5 in the first pass and
re-verified green here.

### 3.1 The idempotency-under-wall-clock bug class (root-caused)

Defects #1, #5, #7 and #8 are the **same class**: a durable record keyed by a
stable `idem_key` but carrying a wall-clock "when-written" stamp (`created_at`,
`at`) in its payload. The store fingerprints the whole payload to decide "same
idem_key → same content?", so two writes of the same logical record a second
apart looked like *different* content and raised `IdempotencyConflict` — crashing
the wrapping job. This is insidious because it is **timing-dependent**: writes
inside the same second are fine, so it passes in tests and single runs and only
bites in production where days are genuinely separate.

#1 and #5 were fixed at the call site (a per-invocation ULID / a content
signature). #7 showed that call-site patching leaves the landmine for the next
author — the #2 signature fix was correct but the payload still shipped a live
`created_at`. So the class is now closed at the **root**: the store's idempotency
fingerprint (`storage/durable.py:_fingerprint`) ignores a defined set of volatile
write-stamp keys (`created_at`, `at`, `ts`, `updated_at`, `resolved_at`, …).
Logical/meaningful time (e.g. `as_of`, a trading day) is deliberately **kept** and
still counts toward identity. Net effect: a record re-written a moment later
dedupes to a no-op (correct idempotency); a genuine content change still raises.
Guarded by `tests/test_storage_durable.py::test_idempotent_ignores_wall_clock_write_stamps`
and a caller-level test on the candidate re-propose path.

Fixing this at the store also closes a **sibling instance the replay did not
directly exercise**: the monthly promotion packet
(`hosted/evaluation.py` appends to `PACKET_STREAM` with a stable
`packet:{day}:{n}` idem_key while carrying a wall-clock `prepared_at` in the
payload — a double-fired monthly run on the same day would have raised
`IdempotencyConflict` on the second fire; it now dedupes). That is the point of a
root-cause fix over another call-site patch: the same mistake by the next author
who writes a `*_at` stamp into a keyed record no longer becomes a production
crash. (Note: this covers only records that flow through the `DurableStore`
idempotency path; the event consumer's dead-letter stamps use a separate store
and are unaffected either way.)

---

## 4. Evidence by requested category

### Failures — 0
All 210 job invocations returned `succeeded`. Distribution:

```
company-intelligence-refresh   29    intraday-paper-reconciliation  29
daily-prediction-generation    30    after-close-recon-and-learning 28
paper-order-submit             30    prediction-resolution          29
synthetic-daily                29    weekly-evaluation               5
monthly-promotion-review        1
```

(28/29 counts reflect the two injected skip days; see below.)

### Skipped jobs — 2, both recovered
- `2026-01-12` — injected after-close **scheduler miss**.
- `2026-01-29` — market **holiday** (all jobs skipped).

Recovery is proven, not asserted: after-close ran on `2026-01-13` and
`2026-01-30` (the days after each gap). Resolution is catch-up by construction
(`repo.due(as_of)` returns everything overdue), so the skipped day's outcomes
were resolved by the next run. The only durable gaps are the two expected
equity-snapshot holes on the skipped/holiday days — every other market day has
a snapshot (audit D2 = 0 unexpected gaps).

### Reconciliation issues — 0
R1 (no order for a private company), R2 (no orphan orders), R3 (≤1 open order
per prediction), R4 (no duplicate same-day exposure), R5 (resolved count ==
outcome-record count), R6 (no simultaneous same-instrument exposure; no position
held after resolution) — **all clean.**

### Prediction errors — 43 (signal, not defect)
Of 84 resolved predictions, 41 `happened` / 43 `did_not_happen`. The misses are
concentrated on the injected DUOL downtrend and choppy NET series — exactly what
the harness set up — and each is recorded in the outcome stream and fed to
learning. These are correct predictions that lost, not system errors.

### Scheduler misses — 2 injected, recovery verified
Covered above. No third, unexpected miss occurred.

### Dashboard inconsistencies — 0
The dashboard assembles without error; its universe count, filled-order count,
and database-health flag all match the store. Equity snapshots present for all
non-skipped days.

### Learning candidates — 3
```
cand:cloudflare:overconfidence   evaluated   n=28
cand:duolingo:overconfidence     evaluated   n=28
cand:shopify:losing_paper_book   evaluated   n=28
```
Each was proposed from real accrued outcomes and re-proposed idempotently as
evidence grew (the fix for defect #2). Promotion remains **human-gated** by
design — the monthly review prepares a packet, it does not self-promote.

### Leakage blocked — 116
A future-dated (`2099-01-01`) evidence item was injected into **every** research
refresh. All 116 (29 refresh days × 4 prediction companies) were blocked before
reaching a prediction. Leakage prevention fired every single day.

---

## 5. Fault-absorption matrix

| Injected fault | Expected safe behavior | Observed |
|---|---|---|
| Double-fired generation + submit | one prediction, one order | ✅ no duplicate (R3/R4 = 0) |
| Scheduler miss (after-close) | next run catches up | ✅ recovered 2026-01-13 |
| Transient missing price | skip, retry next run, no crash | ✅ 0 failures |
| Broker reject | reconcile to rejected, no fill | ✅ order not filled |
| Market holiday | gap then resume | ✅ resumed 2026-01-30 |
| Future-dated evidence | blocked pre-prediction | ✅ 116 blocked |
| Persistent downtrend | losing book → candidate | ✅ 3 candidates |

---

## 6. Lifecycle integrity — the position-closing fix (defect #6)

The deepest finding was that the engine opened one paper position per prediction
but **never closed it**. Over 30 days that is unbounded position growth; against
a real ~$100k paper account (~$4.4k/position) buying power is exhausted in
~30–45 days and submits begin failing — a genuine "run-forever" reliability
defect.

`close_resolved_positions` now runs in the after-close job: for every filled
open whose prediction has resolved, it places an idempotent, deterministic,
opposite-side exit for the full quantity, keyed so a re-run never double-closes,
and catch-up so a skipped/holiday after-close is recovered by the next.

**Before → after, from the same replay:**

```
filled opens whose prediction resolved : 82
  ...that now HAVE a horizon-exit close : 82
  ...STRANDED (resolved, never closed)  : 0     (was 82)

close orders placed                    : 82   (78 filled, 4 fill next session)
broker net positions at end-of-run     : 3    (all close-pending, not stranded)
```

The 3 residual broker positions are fully explained by the audit: they are
resolved predictions whose exit orders were **placed on the final day(s)** and
fill on the next session — the same mechanic a real going-forward run uses. Zero
are genuinely stranded. The realized-P&L link was hardened to always read the
**entry** leg (never the exit), so the sign cannot flip; a regression test
(`tests/test_paper_execution.py::test_close_resolved_positions_flattens_and_is_idempotent`)
locks in flatten + idempotency + entry-leg P&L.

---

## 7. Residual risks & what this run does **not** prove

Honest boundaries on the evidence:

1. **Broker is a deterministic fake, not the live paper network.** The replay
   proves the *engine's* lifecycle and idempotency. It does not prove Alpaca
   HTTP error handling, partial fills mid-session, or rate limits. The
   next step is a small supervised live-paper run (`AlpacaPaperBroker`) to
   confirm the same invariants against real order acknowledgements.
2. **Prices are a synthetic, gap-free series.** Real market-data outages,
   halts, and corporate actions are not modeled beyond the single transient-miss
   injection.
3. **Close orders that fill next session are assumed to fill.** Under the fake
   they always do. Live, a horizon-exit could itself be rejected — the catch-up
   design will retry, but this path is unverified against a real broker.
4. **Universe is the default 4-company set.** Behavior at larger universe /
   budget-cap boundaries is covered by the budget tests, not this replay.
5. **Determinism hides ordering races.** Real GitHub-Actions concurrency (two
   runners in the same second) is *modeled* by the double-fire injection and
   defended by ULID + content-signature idem keys, but a true multi-process race
   against a shared Postgres was not run here.

None of these is a code defect; each is an environment the replay stands in for.

---

## 8. Reproduce

```
# full 30-day replay + audit + ledger (single run)
python scripts/ops_replay_30d.py reports/ops30_replay_ledger.json

# determinism / timing-race check — must be 0 failures every run
for i in $(seq 1 15); do python scripts/ops_replay_30d.py /tmp/l.json \
  | grep '"failures"'; done

# the regression tests that lock in the fixes
python -m pytest tests/test_paper_execution.py tests/test_predictions_learning.py \
                 tests/test_hosted_acceptance.py tests/test_storage_durable.py -q
```

Key tests added/updated this pass:
- `test_paper_execution.py::test_close_resolved_positions_flattens_and_is_idempotent` (#6)
- `test_storage_durable.py::test_idempotent_ignores_wall_clock_write_stamps` (#7/#8 root)
- `test_predictions_learning.py::test_reproposing_unchanged_candidate_on_a_later_day_is_a_noop` (#7)

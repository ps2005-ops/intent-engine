# System equilibrium — session 2026-11-26 (afternoon)

Base: `integration/unified-2026-11-25` @ `fa8ed6c2`. Production runtime
unchanged at `f7690938` (no runtime upgrade this session).

Scope actually completed: Phase 0 (truth), Phase 1.1 (scheduled-cycle
receipts and one operational defect), and the first dependency of Phase 2
(an upstream classifier defect that was manufacturing beliefs), plus the
16-mechanism observability matrix. Everything else in the 25-phase brief is
**not started** in this session and is listed in §6 rather than implied.

## 1. The "missing qualification work" is not missing

The previous integration session reported `~/ie-prospect100-resume`,
`qual/prospect100-resume` and commits `0a675240`, `568e200c`, `d6bb2d10` as
unfindable. All exist on this host (`prathams-MacBook-Air.local`, user
`prathamsharma`), locally and on `origin`:

| Item | State |
|---|---|
| Worktree `~/ie-prospect100-resume` | registered, branch `qual/prospect100-resume` |
| `0a675240`, `568e200c`, `d6bb2d10` | present, contained in local and `origin/qual/prospect100-resume` |
| Branch head | `7d128431` — "R12 scored: 95/95 journeys, mean 7.742, C 89" (2026-11-26 07:59) |
| Rounds after R7 | R8 `35a09899`, R9 `f8aac885`, R10 `c48dfac0`, R11 `d6c3186e`, R12 `deb6a2d5` → `7d128431` |
| `pending_r8/` | present: `founder_economy.py`, `r8_patch.py` (applied as R8) |
| Artifacts | `reports/prospect100_resume/r5…r12` (untracked, local only) |
| Port 8607 / live server | nothing listening; no other qualification process running |

So the qualification program advanced from Round 7 to Round 12 in a session
that the integration session never saw. Cause of the contradiction: the
integration session looked in the wrong place, not a different host. The
Round 12 artifacts (8,562 screens, `ui_matrix_r12_full.json`) are **not**
backed up remotely — they are untracked under `reports/`.

## 2. Scheduled cycles on `f7690938` (receipts)

Source of record: `~/intent-engine-market/status/market_cycles.jsonl`; code
identity from the hourly health check (`git f7690938671a on HEAD clean`).

| Run | Status | Started→finished (UTC) | Note |
|---|---|---|---|
| 2026-11-26 day | COMPLETED | 11:30:05 → 12:35:58 | US holiday; 14/14 steps ok incl. `econ_publish`, `econ_aggregate` |
| 2026-11-25 night | SKIPPED_NO_NEW_MARKET_SESSION | 01:30 → 02:38 | all steps ok; bar 11-24 already ingested by the day cycle |
| 2026-11-25 learning (19:15) | OK | — | econ_resolve: 13 open, 0 resolved; FX4 registered 0 (no trigger) |

Not yet occurred at time of writing (16:30 EST): 2026-11-26 19:15 learning,
2026-11-26 20:30 night. Not claimed.

### 2.1 Defect: night cycles overran 11–22 h and cost five day cycles

| Night | Wall time | Day cycle next morning |
|---|---|---|
| 11-18 | 11.3 h | 11-19 SKIPPED_LOCK_CONTENTION |
| 11-19 | 22.2 h | 11-20 SKIPPED_LOCK_CONTENTION |
| 11-20 | 10.8 h | 11-21 SKIPPED_LOCK_CONTENTION |
| 11-21 | 16.0 h | 11-22 SKIPPED_LOCK_CONTENTION |
| 11-22 | 12.1 h | 11-23 SKIPPED_LOCK_CONTENTION |
| 11-23 → 11-25 | 0.9–1.2 h | COMPLETED |

The lock did its job (a slow night correctly blocked a concurrent day run).

> **CORRECTED in session 2 (2026-11-26 evening).** This section originally
> said laptop sleep was *falsified*. That was wrong: the `pmset` parser
> counted "Wake Requests" bookkeeping lines as wake transitions. Re-measured
> with real transitions only: every slow night was **on battery** with
> 60–248 sleep entries (11-19: 248; asleep ~21.7 of 22.2 h, ~32 min of
> DarkWake), every fast run had ~0. The hourly health check, also a launchd
> job, did not fire for 35 h (11-19 12:40 → 11-20 23:45) — consistent only
> with sleep. A `caffeinate` assertion has been held since ~Nov 9, and macOS
> honours PreventSystemSleep only on AC power. The cause is host sleep, not a
> software bottleneck: the cycle advanced only in Power Nap wakes.

Repair (this session): `Step.seconds` — wall time per step, retries
included, written to the cycle ledger (`cycle.py`, `test_cycle_step_timing`).
The next overrun will name its step. Not deployed: lands with the next
qualified runtime.

### 2.2 Observation, not a defect: night ingests nothing on trading days

`expected_bar_date` makes the night cycle expect the previous session; the
06:30 day cycle ingests that bar first, so the 20:30 night reports
BAR_UNCHANGED. Each session is still ingested exactly once — one cycle late.
On every night since 11-19 the probe returned the previous day's bar even at
20:30. Not reproducible today (holiday). **Continuation:** on the next
trading-day evening, record the raw SPY payload at 20:30 to decide whether
the feed lags or the last bar arrives with a null close.

### 2.3 Operational note

`status/market_cycles.jsonl` is 91 MB (full step detail per run, appended
hourly by health). No rotation exists. Not acted on.

## 3. Defect: fund holding notices were forming beliefs

Found while measuring the observation gap. The commercial event classifier
read "Royal Fund Management LLC **Cuts Position** in Honda Motor Co." as a
LAYOFF and "Plato Investment Management Ltd **Purchases New Stake** in
Cloudflare" as MA_ACTIVITY; "Caterpillar CEO holds 11,234 **share-linked
units**" as EXECUTIVE_CHANGE. A holder trading the stock is not the company
acting.

**Damage on the live ledger:** 11 of 206 expectations (and their beliefs)
rest *entirely* on such sentences — 7 of the 17 `margin_protection` beliefs,
3 `consolidation_posture`, 1 `leadership_transition`. They are referenced by
14 `knowledge_effect` rows and appear as belief-reference counts in 10
`demo_snapshots/*.json`. By code reading the dossier carries the ids as
counts, not the proposition text, so the false sentences do not render on
founder pages; the counts are inflated by one or two. No grade depends on
them (all three families are unbound).

**Repair:**
* `event_patterns.HOLDING_NOTICE_PATTERNS`, spliced into `_NON_EVENT`.
  Phrased on the holding, not the publisher. A company's strategic stake
  ("acquires a 49% stake in") still classifies; "market share position in"
  is excluded by look-behind after it was caught matching a JPMorgan slide.
* Recall repair found by a positive control: "ETSY Cuts 12% Of Workforce"
  classified as nothing; "N% of (its) workforce" is now a LAYOFF object.
* **Measured over every distinct live sentence (1,538):** 52 change class,
  52 are holding notices or unit grants, 0 others. Break proof on a mirrored
  `src` with the block deleted: 8/8 negative tests fail (CAUGHT).
* Harness finding: `pytest.ini` sets `pythonpath = src`, which silently
  overrides a `PYTHONPATH` mirror. A break proof must pass
  `-o pythonpath=<mirror>/src`, or it tests the unmutated tree and passes.

**Existing beliefs — PROPOSED, not applied:**
`learning_store.BELIEF_INVALIDATION` masks the belief, its expectation and
its knowledge effects in the row view, *positionally* (only rows before the
invalidation), because belief ids are keyed on (subject, family) and a later
genuinely evidenced belief must not be hidden. Idempotent; never rewrites a
line. `scripts/learning_loop/invalidate_non_event_beliefs.py` proposes 11
(`reports/learning_loop/PROPOSED_belief_invalidations_2026-11-26.jsonl`),
scoped strictly to this rule. Apply **refuses** unless the importable store
defines `BELIEF_INVALIDATION`, because appending to a runtime that does not
mask the record would look like a correction and change nothing.

Residuals deliberately excluded from the proposal: the Cloudflare
`demand_weakening` belief (rejected by an earlier fix; already covered by
`belief_corrections_2026-11-25`), the JPMorgan slide-text `margin_protection`
belief (not a holding notice; still classifies LAYOFF — separate defect), and
one class-action solicitation basis for `regulatory_pressure`.

## 4. The 16 mechanisms — observability matrix

`src/intent_engine/market/mechanism_observability.py`, pinned by
`tests/test_mechanism_observability.py` (all 16 families accounted for; DIRECT
is exactly `observation_binding.FALSIFIABLE`; only DIRECT may be presented as
a calibrated predictive claim; sources equal the routing table).

| Class | Families | Next work |
|---|---|---|
| DIRECT (4) | demand_strengthening, demand_weakening, pricing_power, market_share_seeking | bound today |
| PROXY (2) | capacity_hiring (LAYOFF refutes), margin_protection (HIRING refutes) | bind the cross-type falsifier; withdraw the 7 holding-notice margin beliefs first |
| PARTIAL (7) | capacity_expansion, capital_return_posture, consolidation_posture, partner_led_distribution, procurement_momentum, productization, regulatory_pressure | reversal reader + per-subject base rate |
| UNOBSERVABLE (2) | supply_constraint, competitor_aggression | a source that carries the observation (4 rows each) |
| RESEARCH_ONLY (1) | leadership_transition | an agreed operational definition |

**Why PARTIAL is not bound now (measured, not assumed):** for the 12 unbound
families, later same-subject evidence of the relevant type existed for 78 of
139 expectations, and genuine reversal wording appeared in it once — Stripe
abandoning a PayPal bid, which is about PayPal as a *target*. A reversal
reader built today would yield ≈0 contradictions; binding "further X" as
confirmation without a base rate would build the ratchet `observation_binding`
was written to refuse.

## 5. Verification

* New tests: `test_cycle_step_timing` (2), `test_holding_notice_is_not_an_event`
  (14), `test_belief_invalidation` (4), `test_mechanism_observability` (7).
* Cycle suites (101) pass with the timing change.
* Full suite: **13,165 passed, 6 failed, 17 skipped, 1 xfailed** (13 min).
  The 6 failures are all `*_live` tests that read the production ledger
  directly (`calibration_consistency_live` ×1, `causal_calibration_live` ×1,
  `counterfactual_memory_live` ×3, `self_test_contamination_live` ×1). The same
  6 fail identically on an unmodified `git archive` of `fa8ed6c2`, so they are
  pre-existing, caused by ledger contents moving since they were written, not
  by this change. `calibration_consistency_live` reports 3 real incoherences
  (e.g. `demand_strengthening` presented above its CONTESTED causal ceiling) —
  a data finding to investigate, not a test to relax. Not weakened.

## 6. Not done in this session (honest scope)

Phases 3–21 were not started: calibration rebuild, reader independent
annotation, Bayesian audit, FX4 sibling experiments, strategic/causal/regime
audits, research prioritisation, promotion registry, learning equilibrium,
graph, economic→founder verification, 100-company R13+, 75-company
regression, unseen-company evaluation, device matrix, V3/V4/V5,
zero-Anthropic audit, release gates, equilibrium controller. No deliverable
in §24 beyond 1, 2 (partial), 3, 5 and part of 7 exists from this session.

## 7. Continuation, in dependency order

1. Upgrade the runtime to a commit containing §2.1 and §3 (backup + rollback
   per `ROLLBACK_market_runtime_20261126-004830.sh` pattern), then
   `invalidate_non_event_beliefs.py --apply ~/intent-engine-market <PROPOSED>`
   with the runtime's `src` on PYTHONPATH. Republish demo snapshots.
2. Bind the two PROXY families (cross-type falsifier through the existing
   `bind` guard sequence, not a parallel binder).
3. Read the next overrun's `seconds` to name the slow night step.
4. 20:30 trading-day SPY probe (§2.2).
5. Back up `reports/prospect100_resume/r12` off-machine with checksums.

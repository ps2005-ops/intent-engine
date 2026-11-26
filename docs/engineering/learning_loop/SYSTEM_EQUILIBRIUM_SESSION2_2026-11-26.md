# System equilibrium — session 2 (2026-11-26 evening)

Continues `SYSTEM_EQUILIBRIUM_2026-11-26.md` from `78c30238`. Machine-readable
status: `docs/engineering/equilibrium/PHASE_TRACKER.json`. Session start:
`scripts/session_identity_check.sh`.

## 1. Work protected (P1)

| Item | State |
|---|---|
| Files | 59,820 under `reports/prospect100_resume/` (R5–R12, regression75, unseen, research_memory, stores, pending patches) + `tests/data` |
| Manifest | `~/ie-backups/prospect100_r5_r12_20261126.sha256` (per-file SHA-256) |
| Local backup | `~/ie-backups/prospect100_r5_r12_20261126.tar` (10.2 GB); extracted and **all 59,820 files matched** |
| Encrypted copy | `.tar.enc`, AES-256-CBC, PBKDF2 200k; decrypts byte-identical to the tar |
| Key | `~/ie-backups/keys/prospect100_20261126.key` (0600). Store it in a password manager; the `.enc` is useless without it |
| Off-machine | **Not done — needs you.** No authorised destination exists on this machine. Copy the `.tar.enc` (not the `.tar`) to a destination you choose |
| Non-sensitive scorecards | already tracked on `qual/prospect100-resume` (62 files under `docs/engineering/prospect100/resume/`) |
| Verification dir | `~/ie-backups/verify_prospect100_r5_r12_20261126` (10 GB, the restore test) can be deleted |

## 2. The three ledger inconsistencies and the six failing tests (P2)

The incoherences were real states of the evidence, not corruption:

1. `demand_strengthening` graded ESTABLISHED (17/21 confirm) under a CONTESTED causal family.
2. `vale` `demand_weakening` belief SUPPORTED under a FAILING mechanism (2/8).
3. `johnson_johnson` `demand_weakening` belief SUPPORTED under the same.

Nothing was wrong in the ledger. Two things were wrong around it:

* **`knowledge_step` parsed the ledger file itself**, bypassing the store's
  invalidation mask. The 30 grade invalidations of 2026-11-25 were invisible
  to belief maturity, knowledge decay (which *writes* lifecycle rows), value
  of information (research priorities), causal calibration and
  counterfactual memory — while `learning_health` honoured them. Measured:
  37 vs 21 demand_strengthening tests. Fixed: `LearningStore.rows()` is the
  one reader; a structural test pins it.
* **No belief-level cap existed.** The mechanism cap was applied in
  `learning_health`; a belief above its mechanism ceiling was published
  uncapped. Added `calibration_consistency.cap_belief_maturities`, applied
  where `knowledge_step` publishes maturity; the uncapped state is kept
  beside it for audit.

The six failures, each resolved by its cause:

| Test | Verdict | Change |
|---|---|---|
| `calibration_consistency_live` | asserted "zero incoherences" — a state, not an invariant | now asserts every incoherence is **capped where published**; reads the masked view |
| `causal_calibration_live` | `contradicted == 0` until real contradictions arrived | asserts `tests == supported+contradicted+ambiguous` (open windows in neither) |
| `counterfactual_memory_live` ×3 | `len == 1` while the corpus grew | membership: the Cloudflare / Duolingo episodes are retrieved; every analogy carries no evidence |
| `self_test_contamination_live` | **a genuine defect, then a ratio** | Google News redirect URLs are per-click tokens, so the same article kept two "sources"; occurrence identity now uses the headline's outlet. 108 more duplicates collapse, 0 bindings lost, evidence ids frozen. Residual 4/16 are true syndication (Zacks via Yahoo and Globe and Mail), pinned deterministically |

Break proofs on a mirrored tree with `-o pythonpath`: raw-parse, dropped
cap, disabled aggregator identity — **3/3 CAUGHT**.

## 3. The 11–22 h night cycles (P3) — cause established

**Host sleep on battery.** Every slow night (Nov 18–22) was on battery with
60–248 sleep entries; every fast run since had ~0. The hourly health job
did not fire for 35 h (Nov 19 12:40 → Nov 20 23:45). A `caffeinate`
assertion held since ~Nov 9 prevents sleep **only on AC power**. The cycle
advanced in seconds-long Power Nap wakes.

Session 1 reported sleep as *falsified*. That was wrong — its `pmset`
parser counted "Wake Requests" bookkeeping lines as wake transitions. The
session-1 report carries a correction block. No software bottleneck was
found, so none was "corrected".

Changes:
* Steps record `seconds` (wall) **and** `awake_seconds`
  (`mach_absolute_time`, which pauses in sleep). A suspended step now looks
  different from a slow one.
* The day cycle **waits for the lock until 09:25** (its pre-market
  deadline) instead of skipping; the night cycle still fails fast. The lock
  holder (run id, pid, time) is written beside the lock and named in
  contention errors. The wait is wall-clock, so it cannot stretch with sleep.

**Operational requirement (you):** keep the machine on AC power overnight.
No code can schedule work on a sleeping laptop.

## 4. December readiness (P15)

**977 forward-shadow forecasts.** One cohort registered 2026-11-09, entry
session 2026-11-10, exit 2026-12-10, resolvable from **2026-12-11** by the
19:15 learning job. 79 instruments. Fixture maturity simulation on a copy
of the ledger with synthetic bars (production ledger hash unchanged):

| Scenario | Result |
|---|---|
| Dec 10 20:00 | 0 resolved, 977 wait |
| Dec 11 19:15, one feed (ADBE) a week behind | 964 resolved in 0.46 s, 13 wait |
| Dec 19, past the 7-day grace | 13 void with a stated reason; due date unchanged |
| Re-run | 0 rows appended (idempotent) |

The ledger independently refuses any outcome whose exit session has not
completed by its own clock, so nothing can resolve early. Risks: the job
needs the host awake (launchd runs a missed calendar job on wake); 977
forecasts over 79 instruments and one date are heavily correlated — the
effective sample is far below 977.

**Econ expectations.** Only **1 of 13** is due 2026-12-25 (PERMIT,
120 days, DOWN vs 2026-06-01, ALFRED vintage in force at the horizon). The
other 12 mature 2027-02-23 → 2027-08-22. The brief's "13 due Dec 25" is
incorrect.

## 5. Runtime upgrade and the eleven withdrawals (P18, P7) — APPLIED

* **Market runtime upgraded** to `2216bd07` at the immutable worktree
  `~/ie-market-runtime-v3` (17:3x EST). Qualification: guard 13,154 passed;
  separate live-data audit 158 passed / 0 failed; rehearsal below. Fresh
  ledger backup with SHA256SUMS verified before the switch. **Rollback
  tested:** rollback restored `ie-market-runtime-v2`, re-upgrade restored
  v3. Health check on the new code: OK, `2216bd07 clean`.
* **Withdrawals applied** under the market-cycle lock with the runtime's own
  src: 11 `belief_invalidation` rows appended, re-apply appended 0, live
  beliefs 206 → 195, their expectations and knowledge effects masked. The
  first 35,756 ledger lines are byte-identical to the pre-upgrade backup.
* **Pending, not claimed:** the demo snapshots are republished by the
  scheduled cycle's strategic export; the first scheduled cycle on
  `2216bd07` is tonight's 20:30 night run. Verify the 10 affected
  snapshots' belief counts after it.

Rehearsal (before the switch):

On a copy of the production ledger with the candidate code: 11 appended,
re-apply appends 0, beliefs 206 → 195, their expectations and 7 knowledge
effects masked, `knowledge_step` runs in 13.8 s with Vale and J&J capped,
the apply **refuses** against the current runtime, production unchanged.

Upgrade and rollback scripts:
`~/intent-engine-safety-backups/UPGRADE_market_runtime_20261126-evening.sh`
and `ROLLBACK_market_runtime_20261126-evening.sh` (backs up the market
reports, status, econ and the forward ledger with SHA256SUMS; creates an
immutable `~/ie-market-runtime-v3`; repoints the three plists; refuses
while a cycle holds the lock). The learning runtime stays at `f7690938`:
nothing in this candidate changes what it runs, and changing it before the
Dec 11 resolution adds risk without benefit.

## 6. Actor attribution beyond holding notices (P6)

`names_the_subject` applied to the 195 surviving beliefs' opening evidence
finds 33 whose basis never names the subject. A mechanical rule would be
wrong: the helper misses aliases ("Check Point", "J&J", "(GRFS)",
accents). Model labels (one annotator, **not** human review) in
`reports/learning_loop/REVIEW_actor_attribution_2026-11-26.tsv`:
21 NOT_SUBJECT_EVENT (boilerplate, navigation text, another company's
news, analyst opinion, an insider sale filed as regulatory pressure),
10 REAL_SUBJECT_EVENT (alias gaps), 1 MISROUTED, 1 UNCLEAR. No withdrawal is
proposed from these until labelled independently.

## 7. Why 100-company qualification stalled (P16, P17)

From the committed R4–R12 scorecards (`scripts/prospect100/stagnation.py`):

* 0 qualifiers in all 8 rounds; no company is blocked by exactly one metric.
* **History passes exactly the 12 SEC filers. Independence passes 7 private
  companies. Economics passes 7. Independence ∩ history = ∅ and
  independence ∩ economics = ∅.** Under the preserved rubric no company can
  reach 10/10 by improving any other metric. Six rounds moved strategy and
  presentation, which were never binding.
* The public cohort is the reachable target: FactSet, Morningstar, Workday,
  BILL, BlackLine and N-able sit at 8.5 failing only independence (1
  origin), economics and presentation, all with "no decision could be
  formed from the evidence". Their analyses "rest on company-published
  sources" despite heavy independent press coverage.

Next round: fix independent-evidence acquisition for SEC filers, run the 12
public companies only, then the representative failures, then all 95.

## 8. Not done (honest scope)

P4 catch-up after 09:25 and the failure-injection suite; P5 trading-day
20:30 probe (needs a trading evening); P8–P12 observation mechanisms; P18
the upgrade itself; master-plan phases 4–14 and 17–24. The tracker lists
each with its acceptance criterion.

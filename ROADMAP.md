# Roadmap: overnight autonomous task queue

Seeded from real, already-documented backlog items in `PROGRESS.md` — nothing
here is invented for this file. Every RUNNABLE task has a definition-of-done
that is a concrete test or check `nightly_agent.sh` (or a human) can actually
run and get a pass/fail from. Tasks without one are marked **NEEDS-SPEC** and
are never picked by the nightly loop — see each entry for why it's not
runnable yet.

Status values: `RUNNABLE` (loop may pick it), `IN-PROGRESS` (a branch exists,
not yet merged/closed), `DONE`, `NEEDS-SPEC` (real backlog item, no verifiable
done-condition yet — skipped, not guessed at).

The nightly loop picks the lowest `priority` number among `RUNNABLE` tasks.

---

## T001 — Add real tests for `simulator/cli.py`'s `main()`

- **Status**: DONE — completed 2026-07-15 via `nightly_agent.sh`'s first
  real rehearsal (Auto mode), commit `8e0dbac` on `agent/T001`. Reviewed
  and merged into `main` 2026-07-16 via merge commit `ac962d8` (regular
  merge, no history rewrite). Post-merge full offline suite: 468 passed
  (463 pre-merge + 5 new), 2 skipped, zero regressions — the 5 pre-existing
  `test_simulator_e2e.py` failures (external API-credit exhaustion, not
  code) are unchanged and excluded from this count. See
  `MORNING_REPORT.md` / `reports/` for the original rehearsal record.
- **Priority**: 1
- **Size**: S
- **Source**: PROGRESS.md line 418 — "nothing in the test suite calls
  `cli.main()` — the CLI's argparse layer... has no automated coverage, only
  the live manual run performed during review."
- **Files in scope**: `tests/test_simulator_cli.py` (new), read-only reference
  to `src/intent_engine/simulator/cli.py` (no source changes expected; if a
  small testability change is genuinely required — e.g. making `main()`
  accept `argv` — that's in scope too, but the argparse behavior itself must
  not change).
- **Definition of done**: `tests/test_simulator_cli.py` exists and calls
  `main()` directly (not just the functions it wires together) for at least:
  (a) the real `--entity-id` required-flag behavior, (b) one real end-to-end
  invocation against a fixture in `tests/fixtures/business_decisions.json`
  asserting a normal exit code and an entity-memory write. Check:
  `.venv/bin/python -m pytest tests/test_simulator_cli.py -q` passes, and the
  full suite (`.venv/bin/python -m pytest -q`) passes with no regressions.

## T002 — Rename `JsonlEntityMemoryWriter` to a backend-accurate name

- **Status**: DONE — completed 2026-07-16, commit `b7ecf34`. Pure rename to
  `SqliteEntityMemoryWriter` across 23 files (8 src, 15 tests), 94
  insertions/94 deletions. `grep -rln "JsonlEntityMemoryWriter" src tests`
  returns zero matches. Offline suite identical before/after: 468 passed, 2
  skipped, same 5 pre-existing e2e API-credit failures — zero behavior
  change.
- **Priority**: 2
- **Size**: M
- **Source**: PROGRESS.md, Data foundation pass Stage 1 — "kept anyway rather
  than renamed, because a rename touches all 18 call sites... Tracked as a
  real followup... do a small, dedicated rename pass on its own."
- **Files in scope**: `src/intent_engine/core/entity_memory.py` and every
  real importer: `core/mom_fitness_captions.py`, `core/brother_music_captions.py`,
  `core/scrap_estimate.py`, `core/draft_generator.py`, `voice/context_schema.py`,
  `voice/pipeline.py`, `simulator/cli.py`, and their corresponding test files
  (`tests/test_entity_memory.py`, `tests/test_mom_fitness_captions.py`,
  `tests/test_brother_music_captions.py`, `tests/test_pattern_watcher.py`,
  `tests/test_context_schema.py`, `tests/test_voice_cli.py`,
  `tests/test_luck_test.py`, `tests/test_scrap_estimate.py`,
  `tests/test_draft_generator.py`, `tests/test_voice_pipeline.py`).
- **New name**: `SqliteEntityMemoryWriter` (states the real backend, matching
  this project's own naming convention elsewhere — `StubGmailReader`,
  `GoogleCalendarReader`, etc., each name states what it actually is).
- **Definition of done**: `grep -rln "JsonlEntityMemoryWriter" src tests`
  returns zero files (a pure rename, not a re-export shim — no backward-compat
  alias). Full suite passes with the exact same test count as before the
  change (a rename must not add, remove, or change what any test verifies).

## T003 — Widen `anchors_on_offered_context`'s documented rationale

- **Status**: DONE — completed 2026-07-17 (Cowork session, direct-to-main),
  commit `25cb4b5`. Rationale now documents BOTH mechanisms explicitly
  (classification bias / episode 3, generation-leak-imitation / episode 4)
  plus the shared diagnostic test. New test
  `test_anchoring_rationale_documents_both_failure_shapes` asserts
  generation+imitation AND classification+bias terms present. Offline
  suite: 553 passed, zero regressions.
- **Priority**: 3
- **Size**: XS
- **Source**: `scripts/replay_diagnosis_registry.py`'s own finding on episode 4
  (the mom's-captions prefix leak) — matched the signature via a genuinely
  different mechanism (generation-leak/imitation) than the signature's
  original description (classification-bias), flagged as worth widening the
  documented definition explicitly.
- **Files in scope**: `src/intent_engine/core/diagnosis_registry.py` (the
  `anchors_on_offered_context` `RegistryEntry.rationale` string only — no
  signature/fix-category values change), `tests/test_diagnosis_registry.py`.
- **Definition of done**: a new test asserts the rationale text explicitly
  covers BOTH failure shapes — e.g. asserts a generation/imitation-related
  term (such as `"generat"` or `"imitat"`) is present in the rationale,
  alongside the existing classification-bias language. Full suite passes.

## T004 — Add the 7th diagnosis-registry signature: `stable_but_non_discriminating`

- **Status**: DONE — completed 2026-07-17 (Cowork session, direct-to-main),
  commit `5342fec`. 7th signature + `design_level_fix_required` fix category
  added, registry row explicitly marked ENCODED, UNVALIDATED;
  `check_discrimination_bar()` built as the narrowly-scoped deterministic
  detector (real backtest-v1 regression fixture: 66.7% vs 61.1% flags True,
  including the exact 14.3%-specificity reconstruction; 94.4% on the same
  real ground truth returns False). Replay episode 5 reclassified under the
  new signature with verdict ENCODED_UNVALIDATED — deliberately NOT scored
  as a match, per this task's own definition-of-done. Offline suite: 557
  passed, zero regressions.
- **Priority**: 4
- **Size**: M
- **Source**: The approved Part 5 Step-1 design (already proposed in detail
  this session, awaiting build) plus independent out-of-sample confirmation
  from the job-application-agent case-study replay (the `top_n=10` bullet-selection
  degeneracy).
- **Files in scope**: `src/intent_engine/core/diagnosis_registry.py` (add
  `"stable_but_non_discriminating"` to `FailureSignature`, add
  `"design_level_fix_required"` to `FixCategory`, add the registry row with a
  real rationale, add a narrowly-scoped `check_discrimination_bar(predictions,
  ground_truth, baseline_predictions, margin=...)` helper next to it — NOT a
  general shared bar-tier module, per the already-recorded "documented
  pattern, not shared code" resolution), `tests/test_diagnosis_registry.py`,
  `scripts/replay_diagnosis_registry.py` (update episode 5's row to reflect
  the new, more precise classification).
- **Definition of done**: new tests cover (a) `diagnose("stable_but_non_discriminating")`
  returns `"design_level_fix_required"`, (b) `check_discrimination_bar` returns
  `False` on a real baseline-beating case and `True` (fails/flags) on a real
  baseline-losing case, matching the backtest-v1 real numbers (66.7% vs.
  61.1%) as a real regression fixture, not synthetic. Re-running
  `scripts/replay_diagnosis_registry.py` shows episode 5 classified under the
  new signature (not the generic `novelty_or_scope_gap` catch-all) — **still
  correctly marked as having no validated real fix to compare against**, per
  the explicit "encoded, unvalidated" instruction; the task is NOT done if it
  claims episode 5 as a "match." Full suite passes.

---

## T009 — Synthetic-world reasoning eval (HIGH priority per founder, 2026-07-19)

- **Status**: OFFLINE LEG DONE / LIVE LEG STAGED — 2026-07-19 (loop 8),
  commit `2034536`. Founder approved the EVALUATION variant (explicitly
  not training), raised it to high priority, and directed maximum realism
  ("as close to the real world as possible; work the base well").
  Built: `core/synthetic_worlds.py` — 89 deterministic fictional worlds
  (23×3 single + 12 mixed + 8 healthy controls) with analyst-brief
  realism and a 6-part leakage wall (zero memorization risk, asserted) —
  plus `scripts/run_synthetic_world_eval.py` and 16 bar tests.
  Offline finding (reports/synthetic_worlds_eval.md): only **11/23
  mechanisms are uniquely identifiable** under the frozen enum; 6 tied
  classes derived — recorded as evidence for the deferred enum decision.
- **Next human action**: run the live leg on the Mac —
  `python scripts/run_synthetic_world_eval.py --live` (≈$1.78, ≤100
  calls, frozen-prompt sha256 asserted before any call). That leg is the
  LLM reasoning diagnostic proper.
- **Walls**: reasoning diagnostic only — NOT forward-market accuracy, NOT
  a marketing claim; prompts/enum/library untouched; training use of the
  generator = separate founder-gated capability.

## T008 — REGIME_VOCAB widening

- **Status**: DONE — 2026-07-19 (loop 8), commit `3495768`. Founder
  approved the spec (docs/REGIME_VOCAB_WIDENING_SPEC.md) as written:
  +6 terms (ipo, merger, acquisition, stock, buyback, guidance), 36→42,
  additive only, scoring logic untouched. All 4 spec bars asserted as
  tests in tests/test_headline_feed.py; bar-c control set stayed at 0 so
  no term was dropped. This is the headline vocab — NOT the frozen
  TriggerCondition enum (which stays frozen per the same-day founder
  decision recorded in docs/MECHANISM_LIBRARY_STATE.md).

## T006 — Wire the premortem->ledger bridge into the live pipeline

- **Status**: DONE — 2026-07-20 (loop 9). Live bar (a) PASS on the
  founder-run fixture: 3 rows source="premortem" (p 0.72/0.65/0.58, all
  future resolve_by, resolvable claims), verified by direct DB read;
  append-only held (pre-existing rows untouched); one transient 328-char
  length retry within budget. Built 2026-07-19 (loop 8),
  commit `a236604`, founder green-light via the morning-list
  continuation. Wiring per the approved spec, T005's shape: opt-in
  `--record-predictions` flag (off by default), `bridge_client` kwargs on
  `run_premortem`, additive `PremortemResult.ledgered_predictions`
  (default None — caller-compat tested). Bars (b)(c)(d)(e) asserted
  offline (7 tests incl. append-only proof + exactly-one-drafting-call);
  combined analyzer prompt and bridge drafting prompt untouched.
- ~~Remaining human action~~ CLOSED: the live run happened 2026-07-20; kept for the record — it was: one live run on the
  Mac with `--record-predictions` on a fixture decision, then verify the
  1-3 source="premortem" rows by direct DB read. On PASS → flip to DONE.

## T007 — Mechanism explanation depth

- **Status**: DONE — 2026-07-22. Built to green under the founder-ratified
  OPTION 1 (docs/T007_PARK_FINDING.md): the language wall applies to the
  system-authored framing lines only; verbatim `causal_chain` steps + the
  cited source are exempt (bar (c) guarantees they're unedited quotes of
  documented history, not the system's predictive voice). All six bars
  pass — (a) condition-traceability, (b) cited-instance presence, (c)
  verbatim causal-chain fidelity, (d) system-line language wall, (e)
  correct silence, (f) additive/no-regression — asserted across the whole
  real 20-mechanism library. The decisive proof (test + trace): a
  wall-tripping mechanism (`carry_trade_unwind`, whose verbatim chain says
  "unwind (sell … buy back …)") renders its history correctly while the
  system framing stays clean. Suite **635 passed** (627 + 8 new), 0 live
  calls, one commit.
- **Files**: `simulator/mechanism_section.py`
  (`render_mechanism_explanation` + `assert_explanation_system_walls`),
  `simulator/cli.py` (`--explain` flag, off by default, additive),
  `tests/test_mechanism_explanation.py` (8 bar tests).
- **Walls honored**: 0 model calls (a model call here is a park
  condition); no probability/prediction attached to any explanation;
  `render_mechanism_section` one-liner untouched (bar f); enum & prompts
  untouched.

## T005 — Wire mechanisms into premortem output (overnight Task 4)

- **Status**: DONE — 2026-07-22. Mocked bars (c)(d)(e) green since
  2026-07-18; live bars (a)(b) run on the Mac, BOTH PASS (founder-reported,
  outputs in reports/overnight_trace.md): (a) supplier decision renders the
  section with a real concentrated_supplier_base match + dated instances;
  (b) neutral decision renders no section (correct silence). 2 of <=8 live
  calls used. Spec: docs/TASK4_SPEC_PROPOSAL.md.
  <!-- historical detail retained below -->
  Implementation + mocked bars (c)(d)(e) committed this session, suite
  green. Live bars (a)/(b) are staged in `T005_LIVE_RUNS.md` (2 Mac
  one-liners, 2 of the <=8 live-call budget) — NOT done until both pass
  and outputs land in reports/overnight_trace.md. NOT runnable by the
  nightly agent (live bars are human-run by definition).
- **Priority**: 1. **Size**: S (built).
- **Files touched**: `src/intent_engine/simulator/mechanism_section.py`
  (new), `simulator/pipeline.py` (additive field + kwarg),
  `simulator/cli.py` (--mechanisms flag), `tests/test_mechanism_section.py`.
- **Walls honored**: combined premortem prompt untouched; extraction
  prompt duplicated verbatim from the gate-verified design (editing it
  re-opens the Task 3 gate); closed-enum schema; word-boundary language
  walls on the rendered section; no ledger wiring (Task 5's job).

## T010 — Event-sourced Decision Record (Slice 1, data layer)

- **Status**: DONE 2026-07-20 — data layer (commit 8abb2dd, hardened:
  FKs, append-only triggers on all four tables, atomic supersession,
  payload validation, validated folding, idempotency-key scoping) +
  Slice 1B wiring (commit 524296e: `prediction_ledger.decision_id`
  reference, bridge stamping, idempotent intake in `run_premortem` +
  `premortem --decision-record`, typed AnalysisFailed /
  PredictionLoggingFailed recovery events). 23 + 9 tests; offline suite
  green + EXIT=0 at each commit.
- **Priority**: 1. **Size**: M.
- **Source**: `docs/V1_COMPLETION_ROADMAP.md` Part E (Slice 1),
  founder-reviewed 2026-07-20 (event-sourced; 10 final decisions locked).
- **Files in scope**: `src/intent_engine/core/decision_ids.py` (new),
  `src/intent_engine/core/decision_record.py` (new),
  `tests/test_decision_record.py` (new). Prediction-ledger nullable FK and
  intake wiring are T010's *subsequent* steps (separate commits), not this
  one.
- **Definition of done (bars)**: (a) **fold** — create → append a hand-built
  event sequence → `get_current_state` returns the correct
  decision/execution/evaluation axes; (b) **idempotency** — re-running
  `create_decision` with the same `idempotency_key` returns the existing
  record and creates zero duplicate rows; (c) **dual ID** — `decision_id` is
  a 26-char ULID, `decision_key` matches `DEC-YYYY-NNNNNN`, both UNIQUE;
  (d) **transition validator** rejects an illegal sequence (e.g.
  `DecisionApproved` before `DecisionSubmitted`); (e) **canonical
  relationships** — one direction stored, inverse derived on read;
  (f) **schema-version guard** rejects an unsupported future major version;
  (g) **no raw sensitive intake text** is copied into any event payload;
  (h) **append-only** enforced (UPDATE/DELETE raise). Check:
  `python -m pytest tests/test_decision_record.py -q` passes, then the full
  offline suite passes with EXIT=0, zero regressions.
- **Walls**: stdlib only (sqlite3/json/hashlib — no new dependency, A3);
  `PremortemAnalyzer` combined-call prompt + `TriggerCondition` enum
  untouched; append-only; one commit per step.

## T011 — Decision Record → founder report wiring (Slice 2A)

- **Status**: DONE 2026-07-20 (commit bfa0b3f) — identity header, folded
  three-axis status badge, owner, supersession cross-links by
  decision_key, record schema version in the audit trail. Reads only
  (zero events appended — tested); absent record → unchanged output;
  walls pass on every new line. +4 tests.
- **Priority**: 1. **Size**: M.
- **Source**: `docs/V1_COMPLETION_ROADMAP.md` P1 verdict ("split per
  review point 11 → Slice 2A"), founder-reviewed 2026-07-20.
- **Files in scope**: `scripts/render_founder_report.py` (extend
  `build_premortem_sections()` / `write_pdf()`),
  `tests/test_render_founder_report.py` / `tests/test_founder_report_pdf.py`.
- **Definition of done (bars)**: given a decision_id, the report renders
  (a) Decision ID/key header; (b) folded status badge (three axes, read
  via `DecisionService.get_current_state`, never inferred); (c) current
  owner; (d) `supersedes`/`superseded_by` links when present; (e) report
  metadata + component versions (engine version already rendered; add
  record/event schema versions); (f) absent record → report renders
  unchanged (additive default); (g) language walls + accuracy-claim wall
  still pass on every new section; offline suite green + EXIT=0.
- **Walls**: PDF writer stays dependency-free (no HTML build, per the
  accepted P1 verdict); reads only — the report never writes decision
  events; frozen prompts untouched.

## T012 — Approved founder-report polish (Slice 2B)

- **Status**: DONE 2026-07-20 (commits 6e8d1b0, b34a9d3, 74d9b1f) —
  three-axis Evidence Confidence (finding #7 resolved: unrequested legs
  lower coverage, never evidence quality), Alternatives Considered
  (structured inputs only; NONE DOCUMENTED honestly), nine-stage
  lifecycle read from the fold + event history (terminal decisions mark
  unreachable stages), per-page footer with decision key, PDF /Info
  metadata, hard-break wrapping. +26 tests; three sample scenarios
  visually inspected. Founder Report V1: BUILT.
- **Priority**: 1. **Size**: M.
- **Source**: `docs/V1_COMPLETION_ROADMAP.md` P1 verdict (the deferred
  v3 polish), founder-reviewed 2026-07-20.
- **Files in scope**: `scripts/render_founder_report.py`,
  `tests/test_founder_report_pdf.py`.
- **Definition of done (bars)**: (a) **3-axis Evidence Confidence** —
  the single gauge splits into Evidence Quality / Reasoning Coverage /
  Prediction Confidence, each rule-computed from existing check inputs
  (resolves V1 roadmap finding #7: "leg not requested" no longer
  penalizes like "evidence weak"); (b) **Alternatives Considered**
  section rendered from the scenario set + stated constraints only (no
  new facts); (c) **9-stage lifecycle presentation** — the decision loop
  rendered as explicit stages with the record's current position when a
  Decision Record is attached; (d) PDF polish stays inside the existing
  dependency-free writer; (e) walls pass on all new content; absent
  record/legs degrade honestly (UNAVAILABLE, never guessed); offline
  suite green + EXIT=0.
- **Walls**: no new dependency; no accuracy claims (A-M5 untouched);
  frozen prompts untouched; reads only.

## T013 — Company Event System (root: append-only log, envelope, first producer)

- **Status**: DONE 2026-07-20 (commits 20a9c2a, bfc0059, b181f34,
  dd3079d) — all bars (a)–(h) proven: fsync'd append-only events.jsonl,
  closed taxonomy with one authoritative producer per type,
  idempotent publisher, one-way DecisionEvent bridge (total mapping:
  bridged or explicitly skipped; replay = zero duplicates), per-consumer
  checkpoints advancing only on success, bounded retry → append-only
  dead letters → explicit idempotent redrive, replay CLI
  (`PYTHONPATH=src python -m intent_engine.events`), human-only
  approval-wall transitions with a structural published-requires-approved
  check. Canonical contract: `src/intent_engine/events/envelope.py`.
  41 tests. Company Event System V1: BUILT. Consumers: NOT BUILT.
- **Priority**: 1. **Size**: L.
- **Source**: `docs/COMPANY_OS.md` Part 3 (the catalogue and transport
  are already specified there — this task builds them; no new design).
- **Files in scope**: new `src/intent_engine/core/company_events.py`,
  new `tests/test_company_events.py`; NO consumer systems (CRM,
  analytics, knowledge, marketing C3+) in this task.
- **Definition of done (bars)**: (a) **append-only log** —
  `events/events.jsonl` rows gain, never mutate; (b) **typed envelope**
  — `event_id` (ULID), `event_type` (closed set = the Part 3 catalogue),
  `key` (one of decision_id / prediction_id / prospect_id / event_id),
  `occurred_at`/`recorded_at`, actor + source, `payload`,
  `schema_version`, `idempotency_key`; unknown event types rejected;
  (c) **idempotent publisher** — same `idempotency_key` appends zero
  duplicate rows; (d) **DecisionEvent bridge** — decision_events rows
  fan one-way into the company log as its FIRST producer, idempotent on
  replay, the decision store stays the source of truth; (e) **consumer
  checkpoints** — consumers are pure functions with a persisted offset;
  re-running from a checkpoint reprocesses nothing; (f) **retry +
  dead-letter** — a consumer failure writes a typed dead-letter row and
  never blocks the log or other consumers; (g) **approval-wall events**
  — `ApprovalQueued` / `PublishApproved` are first-class envelope types;
  `PublishApproved` requires `actor_type=human` structurally; (h) fan-out
  reaches DRAFTS only; nothing publishes; offline suite green + EXIT=0.
- **Walls**: stdlib only (A3 — the log IS the bus; no broker); frozen
  prompts untouched; the two walls remain the only human-emitted
  transitions; 0 model calls.

## T014 — CRM and customer intelligence (first substantial event consumer)

- **Status**: DONE 2026-07-20 (commits cb4c68a, 17bdaef, e206061,
  c6991be, 9ea6951, fd1f89b) — all bars proven: append-only
  `marketing/crm/crm.jsonl` with opaque ULID identity (attributes never
  keys; exact-match resolution, no fuzzy merge), three folded axes with
  validated transitions and explicit-only terminal reopen, typed
  decision links (Decision Record stays authoritative), checkpointed
  idempotent company-event consumer (no identity guessing; replay =
  zero duplicate facts), versioned health/conversion signals (missing
  data = UNKNOWN/UNAVAILABLE, no probabilities), outreach wall
  structural (sent requires prior human approval per draft). Canonical
  contract: `src/intent_engine/crm/events.py`. 55 tests. CRM V1: BUILT.
- **Priority**: 1. **Size**: L.
- **Source**: `docs/COMPANY_OS.md` P8 verdict + PLAN_2026-07-21 C5 spec
  (extend, not reinvent); first real consumer of the T013 log.
- **Files in scope**: new `marketing/crm/` (append-only `crm.jsonl`),
  new CRM event consumer using the T013 consumer protocol, tests. NO
  analytics/knowledge/growth systems in this task.
- **Definition of done (bars)**: (a) append-only `crm.jsonl` keyed by
  `prospect_id`; reads collapse to latest per id; (b) lifecycle
  prospect → contacted → engaged → customer → advocate with validated
  transitions (waitlist funnel included); (c) intelligence fields
  (industry, stage, company size, decision type, pain points) plus
  health score and likelihood-to-convert COMPUTED by code from rows,
  never stored as opinions; (d) every report-generated interaction row
  links the `decision_id`; (e) approval wall structural: no `sent` row
  without a prior `approved` row with non-null `approved_by`; (f) a CRM
  consumer (T013 protocol, own checkpoint) consumes decision.* and
  report.generated events idempotently — re-drain writes zero duplicate
  rows; (g) no scraped lists; metrics computed not stored; offline
  suite green + EXIT=0.
- **Walls**: append-only; nothing sends without per-item human
  approval; no accuracy claims (A-M5); 0 model calls in the suite.

## T015 — Analytics and calibration (read-side consumers)

- **Status**: DONE 2026-07-20 (commits 60b8ae8, aac36c8, 40dfd50,
  a27bba8) — all bars proven: versioned MetricResult contract
  (`src/intent_engine/analytics/models.py`), event-derived decision
  lifecycle metrics with stalled.v1, calibration views behind the A-M5
  gate (29→TOO FEW / 30→count gate with founder-review caveat;
  brier_summary reused, never forked), CRM funnel with
  history-vs-current separation and UNAVAILABLE denominators, report
  metrics with NO OBSERVATION SOURCE honesty, per-consumer health
  (lag/retry/DLQ/NEVER STARTED) proven read-only, one AnalyticsService
  + read-only CLI, language wall over the full snapshot. 34 tests.
  Analytics and Calibration V1: BUILT.
- **Priority**: 1. **Size**: M.
- **Source**: `docs/COMPANY_OS.md` P10 verdict — analytics as a
  CONSUMER of authoritative stores, never a parallel logger; every
  metric ships with why-it-exists / who-consumes-it / what-decision-it-
  improves.
- **Files in scope**: new `src/intent_engine/analytics/` (computed
  read models + an event consumer with its own checkpoint), tests. NO
  dashboards, NO PostHog wiring in this task (LATER-gated per
  TOOLS.md), NO knowledge promotion.
- **Definition of done (bars)**: (a) decision lifecycle metrics
  (counts/durations per axis) computed from DecisionService reads;
  (b) prediction calibration view reuses `brier_summary` and renders
  "too few resolved to claim calibration" until the A-M5 gate (≥30
  resolved per source) clears — asserted by test, no side door around
  the claim wall; (c) CRM funnel metrics computed from crm.jsonl rows
  (conversion counts by stage; metrics computed, never stored);
  (d) event-consumer health: DLQ depth + checkpoint lag per consumer
  from the T013 store; (e) an analytics event consumer (own checkpoint)
  is idempotent under replay; (f) every metric carries its why/who/
  which-decision annotation (structural, tested); offline suite green +
  EXIT=0.
- **Walls**: read-side only — analytics never mutates any store; no
  accuracy claims; no new dependency; 0 model calls.

## T016 — Knowledge promotion and feedback (human-gated learning loop)

- **Status**: DONE 2026-07-21 (commits 6db7d83, 3859b8e, eb57aba) — all
  bars proven: append-only `data/feedback.jsonl` with the exact-text,
  exact-use, human-only quote-consent gate (revocation blocks future
  use; history preserved); typed citations resolved through read-only
  readers with uncited items rejected and below-gate analytics unable to
  support a positive claim; insight lifecycle where systems propose and
  only humans validate, bound to the exact revision; knowledge promotion
  requiring mandatory scope + limitations + citations, versioned
  supersession and typed retraction; mechanism proposals queued for
  human review with `mechanisms.json` byte-identical; checkpointed
  idempotent observation-only consumer. Canonical contract:
  `src/intent_engine/knowledge/records.py`. 30 tests.
  Feedback Ledger V1 / Knowledge Promotion V1 / Mechanism Proposal
  Queue: BUILT. Frozen-library update workflow: NOT BUILT.
- **Priority**: 1. **Size**: L.
- **Source**: `docs/COMPANY_OS.md` P9 verdict + PLAN_2026-07-21 C4
  (feedback ledger). One append-only store, many item types — not many
  stores.
- **Files in scope**: new `src/intent_engine/knowledge/` +
  `knowledge/knowledge.jsonl` + `marketing/feedback/feedback.jsonl`;
  review-queue artifacts for mechanism proposals. The mechanism library
  and diagnosis registry are NOT edited (frozen, A3).
- **Definition of done (bars)**: (a) append-only feedback store (C4
  fields: useful 1–5, what was wrong, what surprised, would pay, can we
  quote); "quote=yes" is the ONLY testimonial-eligible path and still
  requires founder approval before use (structural); (b) append-only
  `knowledge.jsonl` with typed items; every item cites its source
  (decision_id / prediction_id / feedback ref) — an uncited item is
  rejected; (c) promotion path feedback → insight → validated →
  knowledge item as explicit events; validation and promotion are
  HUMAN-only transitions; nothing auto-promotes; (d) mechanism
  candidates go to a review-queue draft with citations; the frozen
  library is untouched and promotion stays behind its existing
  reliability gate; (e) knowledge items may link Decision Records
  (references only — no decision state copied); (f) replay/idempotency:
  re-running any promotion flow creates zero duplicates; offline suite
  green + EXIT=0.
- **Walls**: append-only; human-gated promotion; frozen prompts/library
  untouched; no accuracy claims; 0 model calls in the suite.

## T017 — Marketing automation C3–C8 (approved-workflow automation only)

- **Status**: DONE 2026-07-21 (commits 30bc874, f962738, c5d9129,
  5405abc, b77f6e9, 6226a08) — all bars proven. Plan mapping: **C4 and
  C5 were already BUILT** (T016 feedback/quote gate; T014 CRM) and are
  reused here, not reimplemented; this task built **C3** (ledger→content
  fan-out as a checkpointed consumer), **C6** (commit-triggered
  changelog + social drafts), **C7** (predictions / leaderboard /
  mechanism-library pages taking calibration language verbatim from the
  analytics view), **C8** (roadmap page via the nightly loop's own
  parser), plus the workflow spine: campaigns, deterministic CRM
  audience selection, evidence resolution honoring every source's
  status, versioned briefs and drafts, claim review through the
  existing company-event gate, quote checks through the T016 gate,
  human-only draft and handoff approval, observational publication
  recording, performance observations, and a KnowledgeService-only
  feedback loop. Canonical contract:
  `src/intent_engine/marketing/records.py`. 77 tests.
  Marketing Automation C3–C8 V1: BUILT. External publishing,
  autonomous publishing, autonomous outreach: NOT BUILT.
- **Priority**: 1. **Size**: L.
- **Source**: `PLAN_2026-07-21.md` C3–C8 + `marketing/MARKETING_PLAN_V2.md`
  ("automate generation, gate publication and claims"). Extends the
  built C1 content engine; consumes T013 events, T014 CRM, T016 consent.
- **Files in scope**: `marketing/content_engine/` (extend),
  `marketing/content_engine/from_commits.py` (new), page generators,
  a marketing event consumer, tests. NO growth experiments, NO agents.
- **Definition of done (bars)**: (a) **C3** a `prediction.recorded` /
  `report.generated` company-event consumer (own checkpoint, idempotent)
  fans one ledger fact into the existing draft set — re-drain produces
  zero duplicate drafts and zero publishes; (b) **C4** feedback capture
  routes through the T016 ledger (no second feedback store) and the
  quote gate is the ONLY testimonial path — a draft containing an
  unconsented quote fails to render; (c) **C5** CRM integration writes
  outreach drafts through `CRMService` (no `sent` without prior human
  approval — reuse, do not reimplement); (d) **C6** commit-triggered
  changelog + social drafts from a fixture commit range, all
  trace-audited, none published; (e) **C7** public page generators
  (predictions, leaderboard, mechanism library, case studies, changelog)
  render from real data and show raw rows + "too few resolved to claim
  calibration" until the A-M5 gate clears — asserted by reusing the
  analytics calibration view, never a parallel computation; (f) **C8**
  the roadmap page regenerates from `ROADMAP.md` with no manual
  duplication; (g) every generated asset carries the T:1–T:6 trace table
  and passes the existing claim audit; `PUBLISHING_ENABLED` remains off
  and no network call occurs in the suite; offline suite green + EXIT=0.
- **Walls**: drafts only — nothing publishes, nothing sends; no accuracy
  claims (A-M5); frozen prompts/library untouched; 0 model calls in the
  suite; no parallel CRM/feedback/analytics implementations.

## T018 — Growth platform and experiments (pre-registered, design-gated)

- **Status**: DONE 2026-07-21 (commits f8a0717, a90d2f0, f137501,
  ec3cb7d, 526196d) — all bars proven: pre-registration frozen at human
  approval (metric immutable; amendments create new versions and
  historical rows keep theirs), deterministic reproducible
  randomization with no reassignment path, idempotent exposure,
  registered-metric-only observations, the survivorship funnel on every
  result, stdlib-only self-describing statistics that return
  UNAVAILABLE with the failed assumption named, a label vocabulary with
  no `winner` field, stopping rules that record a fact rather than act,
  recorded interim reads, exploratory analyses that cannot move a
  label, first-class founder overrides, human-only review feeding a
  Decision Record, KnowledgeService-only learnings, frozen reproducible
  snapshots, namespaced synthetic/production separation. Canonical
  contract: `src/intent_engine/growth/records.py`. 79 tests.
  Growth & Experiment Intelligence V1: BUILT. Automatic rollout /
  rollback, Bayesian analysis, sequential corrections: NOT BUILT.
- **Priority**: 1. **Size**: L.
- **Source**: `docs/COMPANY_OS.md` P7 verdict + `marketing/MARKETING_PLAN_V2.md`
  funnel. Experiments are **pre-registered** (the synthetic-worlds
  discipline) and their results become knowledge items through T016.
- **Files in scope**: new `src/intent_engine/growth/` (experiment
  registry + exposure/outcome records + read views), tests. States live
  on the CRM ledger (T014) and metrics on the analytics views (T015) —
  NO new prospect store, NO new metric engine, NO agents.
- **Definition of done (bars)**: (a) **experiment identity** — opaque id
  + hypothesis + audience definition + control/treatment definitions +
  outcome definition, all recorded BEFORE any exposure (a
  post-hoc-registered experiment is rejected); (b) **exposure records**
  are append-only, reference `crm_entity_id`, and one entity cannot be
  exposed to two arms of the same experiment; (c) **outcome records**
  reference the pre-registered outcome definition only — a metric
  chosen after results exist is rejected; (d) **sample-size honesty** —
  every read reports observed n and renders `INSUFFICIENT SAMPLE` below
  the experiment's own pre-registered minimum; no p-value, no
  significance language, no lift claim without it; (e) **stopping
  rules** are declared at registration and a stop is an explicit human
  event; (f) **no causal claim without design support** — an experiment
  without control/treatment separation may report observations only,
  asserted by test; (g) results promote to knowledge ONLY through
  `KnowledgeService` (human validation unchanged); (h) marketing
  artifact links and CRM links are references, never copies; offline
  suite green + EXIT=0.
- **Walls**: append-only; human-gated stopping and promotion; no
  accuracy or significance claims; reuse CRM/analytics/knowledge —
  no parallel implementations; 0 model calls in the suite.

## T019 — Research & Evidence Intelligence Platform (propose-only agent)

- **Status**: DONE 2026-07-21 (commits eee7934, d611bea, dbf69b7) — all
  bars proven. Six separated layers (Request → Plan → Session →
  **Evidence Index** → Package → Conclusion); pre-registered plans with
  a mandatory failure definition and an enforced tool allowlist;
  canonicalized sources with rule-based grading proven independent of
  agreement, independence groups, freshness by domain, and RETIRED
  distinct from STALE; the Evidence Index as never-model-written
  research memory with lineage and self-checked invariants; an
  anti-hallucination wall a model cannot emit provenance through;
  stances including NOT INVESTIGATED, with MIXED carrying a reason and
  below-floor disagreement listed rather than discarded; coverage,
  budget, and research debt; immutable structured conclusions separate
  from regenerable narrative; package AND graph snapshots; draft-only
  mechanism proposals. Canonical contract:
  `src/intent_engine/research/records.py`. 43 tests.
  Research & Evidence Intelligence V1: BUILT. Autonomous crawling,
  recursive browsing, agent promotion: NOT BUILT.
- **Priority**: 1. **Size**: XL.
- **Source**: `docs/V1_COMPLETION_ROADMAP.md` P12 verdict (mechanism
  library **frozen, A3**) + `docs/TOOLS.md` (crawling LATER-gated).
  Scope expanded 2026-07-21: this is the first *agent* subsystem, and
  the patterns it sets are reused by T020–T023. **An agent here is a
  constrained producer of reviewable artifacts, not a thing that
  answers questions.**
- **Files in scope**: new `src/intent_engine/research/`, tests. Writes
  to other subsystems happen ONLY through `KnowledgeService`. Sources
  are **supplied** — no autonomous crawling, no recursive browsing.
- **Definition of done (bars)**: (a) **four separated layers** —
  Request → Plan → Session → Evidence Package → Conclusion, never
  collapsed (a Conclusion cannot exist without a Package; a Package
  cannot exist without an approved Plan); (b) **research plans are
  pre-registered** — questions, evidence requirements, stopping
  conditions, a **failure definition**, and a tool allowlist, all
  human-approved BEFORE any source is acquired; evidence stays
  attributed to its plan version; (c) **source registry** with
  mandatory content hash + retrieval timestamp, a closed source-class
  set, and **rule-based versioned quality grading**
  (HIGH/MEDIUM/LOW/UNKNOWN with reasons) that is provably independent
  of whether the source agrees; `llm_generated` never above LOW;
  (d) **verification + freshness policy** — hash mismatch marks rather
  than deletes; unknown domain gets the conservative policy; stale
  packages are labelled with the oldest load-bearing source age;
  (e) **evidence items** each resolve to exactly one registered source
  and carry a class (observation / mechanism / opinion / prediction /
  recommendation / methodology / unknown); an `opinion` never becomes a
  `mechanism` automatically and a `recommendation` cannot support a
  conclusion; (f) **anti-hallucination wall** — a model may propose
  candidates only; a model-emitted URL, citation, author, or date can
  never enter the store, and an extraction failure is a typed fact, not
  an empty success; (g) **evidence graph + contradiction detection**
  with stance summaries SUPPORTED / CONTRADICTED / MIXED /
  INSUFFICIENT / UNKNOWN, thresholds taken from the plan, MIXED never
  collapsed to a majority; (h) **uncertainty vocabulary** — every
  conclusion carries exactly one of KNOWN / LIKELY / SPECULATIVE /
  CONFLICTING / UNKNOWN, and UNKNOWN is a legitimate success;
  (i) **mechanism proposals are drafts only** into the T016 queue,
  citations resolving to registered sources, `mechanisms.json`
  byte-identical (asserted); (j) **duplicate-request detection** by
  deterministic fingerprint with freshness-aware reuse; (k) **frozen
  reproducible snapshots** recording tool/model/prompt versions and
  retrieval timestamps; (l) language wall over the full serialized
  output; **0 live model calls and no network in the suite**; offline
  suite green + EXIT=0.
- **Walls**: propose-only — no promotion, no validation, no decisions;
  frozen library and prompts untouched; reuse the T016 citation model,
  never a second one; no web ingestion until its own founder gate; the
  deterministic/model boundary is explicit in code.

## T020 — Product Strategy & Roadmap Intelligence Platform (propose-only)

- **Status**: DONE 2026-07-21 (commits 15d494f, 0975417, f689ab6,
  c573958, 9932620, 1cd5282, ec71d86) — all bars proven. Five separated
  layers (Problem → Opportunity → Proposal → Spec Draft → Founder
  Review), with the **Problem Index and the Opportunity Index** as
  never-model-written product memory, rebuilt deterministically from
  append-only rows, rejecting orphans, self-checking their invariants,
  and answering lineage proposal → opportunity → problem → evidence →
  source → request (the last hops delegated to T019 rather than
  rebuilt). Problem-first throughout: a problem with zero evidence
  references is rejected, `why_now` and `what_changes_if_ignored` are
  mandatory, a statement phrased as its own solution is rejected, and
  dedup is exact-match so near-duplicates never silently merge.
  Problems EVOLVE (active / split / merged / retired / superseded); one
  problem carries a SOLUTION SET of competing proposals. Deterministic
  multi-dimensional scoring with UNAVAILABLE never zero, a composite
  that names its gaps rather than imputing them, strategic alignment
  only from a human declaration, FOUR separate confidences (problem /
  opportunity / proposal / execution), and **cost of delay computed
  apart** from the opportunity score. Automatic intake from T019
  research debt (every kind T019 can emit is mapped, asserted against
  `DEBT_KINDS`), T018 INCONCLUSIVE / TOO FEW / GUARDRAIL BREACHED, and
  T014 churn / at-risk facts — deterministic, idempotent, origin-citing,
  and carrying the origin's uncertainty forward as a confidence cap.
  Spec drafts bounded to nine sections with structurally rejected
  execution fields, checkable acceptance criteria, and derived SPEC
  DEBT. Eight-edge proposal graph with derived structural edges that
  cannot drift, no cycles, no orphans, and symmetric `alternative_to`.
  Portfolio → Strategic Themes → Initiatives → Opportunities →
  Proposals → Specs rollup in one deterministic call, plus a balance
  report measured against a human-declared band (withheld with none),
  DECISION DEBT, priority / sequencing / blocking / readiness kept
  separate, and an executive summary built for T021. Roadmap candidates
  and a PROPOSED diff only — `roadmap_diff.py` opens no file at all, so
  the wall is structural rather than promised, and `ROADMAP.md` is
  byte-identical after a full run (asserted). Canonical contract:
  `src/intent_engine/product/records.py`. 194 tests.
  Product Strategy & Roadmap Intelligence V1: BUILT. Roadmap writing by
  the agent: NOT BUILT and never will be. Execution, scheduling,
  ticketing: NOT BUILT.
  *Deviation from the plan, recorded:* the package is
  `src/intent_engine/product/`, not `src/intent_engine/pm/` as the
  original Files-in-scope line said — the subsystem owns product
  strategy rather than project management, and the name follows the
  thing.
- **Priority**: 1. **Size**: XL.
- **Scope expanded 2026-07-21**: this is not "a PM agent". It is the
  subsystem whose job is to read ACROSS every other subsystem and turn
  what they collectively know into artifacts the founder can accept,
  reject, merge, or defer. It owns **product proposals, not product
  decisions**, and it gets a canonical memory — the **Opportunity
  Index** — exactly as Research got the Evidence Index, so T021–T023
  read one substrate instead of rebuilding it.
- **Additional bars (beyond those below)**: (i) **Opportunity Index** —
  deterministic, rebuilt from append-only rows, never model-written,
  rejects orphans, self-checks invariants, answers lineage proposal →
  opportunity → evidence → source → request; (j) **problem-first** — a
  problem records evidence references, affected customers, why-now, and
  what-changes-if-ignored BEFORE any solution exists; a solution
  recorded before its problem is rejected; (k) **three-way separation**
  of Problem / Solution / Spec, so one problem may carry several
  competing solutions; (l) **lifecycle with no skipped steps**
  Opportunity → Proposal → Spec Draft → Founder Review → Decision
  Record → Execution Candidate, with `merged_into` and `deferred` as
  first-class terminal states because those are real founder answers;
  (m) **multi-dimensional scoring** — opportunity_score, confidence,
  evidence/customer/experiment/research coverage, strategic_alignment,
  freshness — each computed separately, each carrying version, inputs,
  formula and reasons; a missing input is UNAVAILABLE never 0;
  strategic_alignment is UNAVAILABLE without a human declaration
  (an agent does not infer strategy); (n) **automatic intake** turning
  T019 research debt, T018 INCONCLUSIVE/TOO-FEW/GUARDRAIL results, and
  CRM churn/at-risk facts into candidate opportunities that cite their
  origin and inherit its uncertainty; (o) **spec drafts bounded** to
  goals / non-goals / requirements / constraints / acceptance criteria /
  unknowns / dependencies / risks / open questions — an implementation,
  estimate, or assignee field is rejected, and an unfalsifiable
  acceptance criterion is rejected; (p) **proposal graph** with
  addresses / supports / depends_on / blocks / alternative_to /
  implements / supported_by / supersedes, no cycles and no orphans;
  (q) **portfolio rollup** Portfolio → Initiatives → Opportunities →
  Proposals → Specs, folded from the log in one deterministic call;
  (r) **known / unknown / assumptions mandatory** on every proposal — a
  proposal claiming no unknowns is rejected.
- **Source**: `docs/V1_COMPLETION_ROADMAP.md` P11 verdict — the PM Agent
  is **read/propose-only**, never auto-promotes a NEEDS-SPEC item, and
  never edits `src/` prompts. It is the second agent, and it inherits
  the T019 agent patterns rather than inventing new ones.
- **Files in scope**: new `src/intent_engine/pm/`, tests. It READS the
  Evidence Index (T019), decisions (T010), growth results (T018),
  analytics (T015), CRM (T014), and knowledge (T016); it WRITES only
  its own append-only store plus proposals through existing services.
- **Definition of done (bars)**: (a) **backlog item identity** with
  append-only history and a folded state; (b) **every proposed item
  cites its evidence** — a proposal referencing no Evidence Index entry,
  decision, experiment, or metric is REJECTED (no opinion-only backlog);
  (c) **priority is computed deterministically and versioned** from
  recorded inputs (linked decision status, experiment label, research
  stance, CRM signal, analytics status) with visible inputs — never a
  model-assigned score; (d) **research debt and INCONCLUSIVE experiment
  results become first-class candidate items**, so gaps drive the
  roadmap rather than vanishing; (e) **NEEDS-SPEC is never
  auto-promoted** — a proposed item enters a review queue and only a
  human marks it RUNNABLE, asserted by test; (f) **ROADMAP.md is never
  written by the agent** — it emits a proposed diff for human
  application, and `ROADMAP.md` is byte-identical after a full run;
  (g) **technical-debt items** may be proposed from recorded failure
  facts (DLQ depth, extraction failures, guardrail breaches) and must
  cite them; (h) uncertainty and language walls inherited from T019 —
  no "should", "must", or "obviously" without cited support;
  0 model calls in the suite; offline suite green + EXIT=0.
- **Walls**: propose-only; no roadmap writes; no promotion of anything;
  no ticketing, scheduling, or execution; reuse the Evidence Index
  rather than re-deriving evidence; reuse analytics rather than
  computing metrics; 0 network.
- **Repository invariants** (standing from T020 onward — every remaining
  subsystem must prove these): exactly one canonical contract, one
  append-only store, one folded-state implementation, one deterministic
  scoring implementation, one graph implementation where applicable, one
  snapshot implementation, and one CLI surface per subsystem; no
  duplicated business logic across subsystems; replay reproduces every
  derived artifact; every output traces back to append-only history.
  Asserted by source inspection, as T018 and T019 already do. These
  compound: by T025 the release audit becomes mechanical rather than
  archaeological.

## T021 — Executive Decision Intelligence Platform (decision candidates only)

- **Status**: DONE 2026-07-21 (commits 029f714, c6f89b9, 775dee8,
  0324e1c, b0730d3, 3fe77db, c384a37, 4553cbf) — all bars proven. Six
  separated layers (Candidate → Context → Package → Founder Review →
  Decision Record → Outcome → Knowledge), with the **Decision Index** as
  the third canonical index (folded from the executive log alone, never
  model-written, orphan-rejecting, self-checking, lineage-answering),
  completing the layering Evidence → Opportunities → Decisions. The
  load-bearing design decision, resolved and asserted by test: the
  Decision Index stores `decision_id` REFERENCES and resolves decision
  state through `DecisionService` at read time rather than mirroring it,
  so it stays reproducible from its own log — no executive module writes
  `decisions.db`, creates a decision, or records a decision event. A
  **Decision Context** carries a horizon and a class and fingerprints
  every load-bearing input, so recent-changes, expiry, and replay all
  fall out of one mechanism; **expiry follows a changed input, never a
  clock** (a test advances `as_of` a year against unchanged inputs and
  nothing expires). A **typed conflict taxonomy** (nine kinds, staleness
  distinct from timeline) produces a **Conflict Summary** with both sides
  named and no average anywhere — asserted by parsing the module. **Six
  independent readiness dimensions**, no overall score; financial
  readiness structurally UNAVAILABLE without a human declaration;
  decision-readiness a YES/NO with every gap named, not a confidence.
  **Impact** computed from scope (an irreversible decision raised one
  level); **reversibility** declared per option and aggregated to the
  least reversible. **Decision packages** with mandatory **alternative
  decisions** (option sets, each carrying benefits/costs/risks/unknowns/
  dependencies/reversibility), an **escalation** decision (who should
  decide) separate from the recommendation, an explicit **no-recommendation**
  outcome, and a **founder override** that keeps both the chosen and the
  preferred option immutably. **Three partitioned triage queues**
  (strategic / operational / maintenance) ordered by a fixed-precedence
  tuple, never a blended score, with unrankable candidates listed
  separately. An **executive portfolio** that reads T020's rollup rather
  than standing up a second hierarchy, and a **health dashboard** for the
  T023 briefing. **Traceability to a terminal state** — rejected and
  deferred legitimate — as a new standing invariant. Reproducible
  snapshots across all eight subsystems; a replay-safe consumer on
  checkpoint `executive`; a reads-only CLI; the recommendation wall over
  the full serialized run. Canonical contract:
  `src/intent_engine/executive/records.py`. 112 tests.
  Executive Decision Intelligence V1: BUILT. Autonomous execution,
  agent-created Decision Records: NOT BUILT and never will be.
- **Priority**: 1. **Size**: XL.
- **Bars (retained for the record)** — amended 2026-07-21 (after T020
  closed) from a synthesis framing to a **triage** framing. The question this subsystem answers
  is *"given everything we know, what decision deserves the founder's
  attention next?"* — not "what should the company do", and not "what
  should the AI execute". That is a ranking question before it is a
  writing question, so the primary artifact is a **queue of decision
  candidates**, and a decision package is what opening one yields. The
  prior bars described producing a good package and said nothing about
  ordering; an agent that writes excellent packages nobody reads in the
  right order has failed the actual question.
- **Scope**: the third agent, and the first that reasons ACROSS the
  whole company rather than owning a domain. It READS the Decision
  Platform (T010), the Prediction Ledger (T010 1B), the Company Event
  log (T013), CRM (T014), Analytics (T015), Knowledge (T016), Marketing
  (T017), Growth (T018), the **Evidence Index** (T019), and the
  **Problem and Opportunity Indexes** (T020). It **owns exactly one
  thing: decision candidates.** It owns no Decision Record, no
  prediction, no proposal, no experiment, and no metric. It reuses both
  existing agent memories rather than building a third; if it needs a
  fact, it reads the subsystem that owns it.
- **Source**: `docs/V1_COMPLETION_ROADMAP.md` revised agent sequence
  (2026-07-21) — an Executive Decision Agent is deliberately built
  BEFORE AgentOS, because generalizing a kernel from three real
  orchestrating agents produces a better kernel than designing one
  ahead of its users. The layering this completes: Evidence (what is
  known) → Opportunities (what could be built) → Decisions (what
  deserves founder attention next).
- **Files in scope**: new `src/intent_engine/executive/`, tests. It
  READS every subsystem's public surface and WRITES only its own
  append-only store. It creates no Decision Record, no proposal, no
  experiment, no campaign, and no roadmap entry.
- **Definition of done (bars)**:

  (a) **canonical contract** — one envelope, one taxonomy, one
  append-only store (`data/executive.jsonl`) with the established
  discipline (flock, fsync, fingerprinted idempotency, loud corruption,
  no mutation API, `(mtime_ns, size)` parse cache, one `_stable_id`
  helper), and one folded-state implementation.

  (b) **THE DECISION INDEX** — the executive memory, and the
  centrepiece, built exactly as the Evidence Index and the Opportunity
  Index were: folded deterministically from append-only rows, NEVER
  model-written, orphan-rejecting, self-checking its own invariants, and
  answering lineage. It holds open decisions, blocked decisions, expired
  decisions, decision debt, decision opportunities, conflicts,
  recommendations, and review packages — and nothing else.
  **The load-bearing design constraint:** the other two indexes are
  reproducible because they fold only their own subsystem's rows. This
  one spans the executive log AND `DecisionService` (SQLite), which
  would break that property. Resolution: the index stores `decision_id`
  **references** and treats `DecisionService` as a RESOLVER — the same
  shape T020 uses for evidence references — so it stays reproducible
  from its own log. Mirroring decision state into the executive log is
  explicitly REJECTED: it is easier to query and it materializes a copy
  that can drift.

  (c) **decision lifecycle, nothing skipped** — Decision Candidate →
  Decision Package → Founder Review → Decision Record → Outcome
  Observation → Prediction Scoring → Knowledge Feedback. Each step
  individually tested; the Decision Record is created by a human
  through `DecisionService`, and this subsystem only references it.

  (d) **the triage queue** — the primary artifact. A deterministic,
  versioned ordering of decision candidates from recorded facts, with
  its inputs, formula, and per-candidate reasons visible, and with
  candidates that cannot honestly be ranked listed separately rather
  than ranked against those that can (as T020 does for unrankable
  proposals). No model-assigned ordering.

  (e) **DECISION DEBT** — the counterpart of research debt (T019) and
  spec debt (T020), continuously surfaced: `need_founder_choice`,
  `need_legal_review`, `need_pricing`, `need_experiment`,
  `need_customer_validation`, `need_research`, `need_budget`,
  `need_engineering_estimate`. Every item cites what it is waiting on
  and what would clear it.

  (f) **cross-system conflict surfacing, with a typed taxonomy** —
  where subsystems disagree (Growth LIKELY against Research
  CONFLICTING against Analytics UNAVAILABLE against a high-urgency CRM
  signal), the package produces a **Conflict Summary** rather than an
  average. Closed taxonomy: `evidence_conflict`, `metric_conflict`,
  `priority_conflict`, `timeline_conflict`, `staleness_conflict`,
  `strategy_conflict`, `dependency_conflict`, `resource_conflict`,
  `unknown`. `staleness_conflict` is kept distinct from
  `timeline_conflict`: two inputs that were true at different times and
  were never reconciled is a different problem from two inputs that
  disagree about scheduling. Averaging away a disagreement is the
  failure this bar exists to prevent. (The taxonomy is built HERE and
  extracted by T022 — per the standing no-speculative-abstraction rule,
  it is not generalized before it has a second user.)

  (g) **six independent readiness dimensions, never one overall score**
  — evidence readiness, execution readiness, strategic readiness,
  financial readiness, operational readiness, and decision readiness.
  Each computed separately, each carrying its version, inputs, formula,
  reasons, and status; a dimension with no recorded input is
  UNAVAILABLE, never 0. **Decision readiness is separate from
  confidence** and is a YES/NO with stated reasons (missing experiment,
  missing strategy, missing budget, missing owner, missing evidence).
  **Financial readiness is structurally UNAVAILABLE** absent a human
  declaration — this repository records no budget or revenue data, and
  proxying one is how an invented figure later gets quoted as measured.

  (h) **decision packages** — each stating the decision, supporting
  evidence **by reference** into the owning subsystem, contradictions,
  unknowns, dependencies, risks, predictions, **alternative decisions**,
  research debt, spec debt, decision debt, and a recommended next
  review. A package with no stated unknown is rejected, and so is one
  with no alternative.

  (i) **alternative decisions are mandatory** — never `approve / reject`,
  always an OPTION SET (Option A / B / C) with explicit tradeoffs per
  option. Structurally this is T020's solution set (one problem, several
  competing proposals); reuse that shape rather than inventing a
  parallel one.

  (j) **explicit founder override, never overwritten** — when the
  founder chooses B and the recorded recommendation preferred A, both
  are retained with the founder's reason, as an immutable fact.
  Precedent to reuse: T018's `FOUNDER OVERRIDE RECORDED` modifier, which
  states in its own text that the data did not make the decision. Later
  prediction scoring reads these; nothing is ever silently replaced.

  (k) **"expired" is computed, not timed** — a decision expires when a
  load-bearing input changes underneath it (a superseding research
  conclusion, an experiment whose label flipped, a churned customer),
  derived from the freshness and supersession machinery T019 and T020
  already compute. Age alone never expires a decision: a clock
  manufactures urgency, which is the opposite of this subsystem's job.

  (l) **executive portfolio** — reads T020's existing rollup (Portfolio
  → Strategic Themes → Initiatives → Opportunities → Proposals → Specs)
  and extends it with Decision Packages and Decision Candidates. It does
  NOT stand up a second hierarchy; strategic themes remain human-created
  in T020, and a conflicting ordering of the same hierarchy is a defect.

  (m) **deterministic synthesis** — package assembly, every readiness
  dimension, every queue ordering, every conflict classification, every
  coverage figure, and every wall computed from recorded facts and
  versioned. A model may draft prose only, behind an injectable client,
  and may never emit a reference, an identifier, a score, a priority, a
  decision id, or a citation; a violation is a recorded typed
  rejection, and a model failure is a typed fact rather than an empty
  success. Tested adversarially, as T020 tests it.

  (n) **UNAVAILABLE propagates** — a recommendation resting on an
  UNAVAILABLE input says so and names the gap; uncertainty travels from
  every origin, so an INCONCLUSIVE experiment or a CONFLICTING research
  stance caps what any decision derived from it can claim.

  (o) **human-only disposition** — accept, reject, defer, and merge are
  founder acts bound to an exact package version; a revised package is a
  new version and a prior review does not carry forward.

  (p) **no autonomous execution** — no Decision Record creation, no
  experiment start, no campaign, no scheduling, no ticketing, no
  promotion, no roadmap write; asserted by test that the service exposes
  no such surface at all.

  (q) **frozen reproducible snapshots** — freezing the Decision Index,
  Opportunity Index, Evidence Index, knowledge, growth-label, analytics
  metric, and prediction versions, plus the source high watermarks that
  reproduce them. Recapturing the same `as_of` returns the original.

  (r) **company-event consumer** with checkpoint `executive`, replay
  creating zero duplicates, and a failure that cannot break any upstream
  system.

  (s) **CLI** of reads and idempotent consumption only — no accept, no
  apply, no schedule command.

  (t) **the recommendation wall** — reject `do this`, `must`, `best`,
  `optimal`; require `current evidence suggests`, `tradeoff`, `review
  required`, `option`, `candidate`. Word-boundary matched for single
  words, applied over the full serialized output of a run.
  **0 live model calls and no network in the suite**; offline suite
  green + EXIT=0.

- **Decision Principles** (declared in one place in the canonical
  contract, as T020 declares its Product Principles, and asserted by
  test): every recommendation has alternatives; every recommendation
  cites evidence; every recommendation cites uncertainty; every
  recommendation cites conflicts; every recommendation cites
  predictions; every recommendation cites assumptions; every
  recommendation is reviewable; nothing executes automatically; nothing
  hides disagreement; every recommendation can be replayed.
- **Walls**: recommend-only; the founder decides; no autonomous action
  of any kind; reuse the Evidence Index and the Opportunity Index rather
  than re-deriving either; reuse T020's portfolio rollup rather than
  building a second hierarchy; reuse analytics rather than computing
  metrics; reuse `DecisionService` for every decision read and never
  mirror its state; frozen library and prompts untouched; 0 network.
- **Repository invariants**: the standing section above binds here in
  full, asserted by source inspection as T018, T019, and T020 already
  do. **One new standing invariant is added by this task**: every
  recommendation is traceable along `recommendation → Decision Record →
  Prediction → Outcome → Knowledge` **to a terminal state** — where
  `rejected` and `deferred` are legitimate terminals. Stated that way
  deliberately: a hard chain would make a recommendation the founder
  declined into a violation, which is the same distortion T020 removed
  when it made `deferred` and `merged_into` first-class. No dead-end
  recommendations; no punished refusals.

## T022 — AgentOS Shared Kernel (extracted, not designed)

- **Status**: DONE 2026-07-21 (commits 3105125, 02e5a67) — an EXTRACTION
  session, not a feature session. `src/intent_engine/agentos/` holds the
  infrastructure the three agents were reimplementing in parallel,
  lifted once: `AppendOnlyStore` (the flock / fsync / fingerprinted-
  idempotency / parse-cache discipline three stores held byte-identical
  copies of — the three agent stores now subclass it and keep only their
  domain query methods, 338 → 123 lines of store code), `stable_id`, the
  `scan_banned_language` word-boundary + phrase matcher (vocabulary
  passed in), `model_provenance` and the recursive `find_forbidden_fields`
  scan, the Store / Index / Consumer / Snapshot / Replayable protocols
  (structural, no forced inheritance), the agent registry, the
  Read/Write/Model/Publish/Human-only permission vocabulary, and
  read-only telemetry/budgeting. **No behavioural change** — the full
  suite passed byte-for-byte identical before and after (1421 → 1448,
  the +27 being kernel tests only). **No new abstraction invented** — a
  test proves no domain concept (scoring, readiness, conflicts, any debt,
  either portfolio, any graph, the Decision Context) entered the kernel,
  and the kernel imports no domain module. Intentionally left local, and
  recorded: research's source-anchored model wall, each agent's
  model-boundary exception subclass, and the T013–T018 subsystem stores
  (events, crm, knowledge, marketing, growth — out of the three-agent
  scope, some with genuine variations, not disturbed under the
  zero-regression rule). AgentOS Shared Kernel V1: BUILT. New autonomous
  authority: NOT BUILT — the kernel is plumbing, not an actor.
- **Priority**: 1. **Size**: XL.
- **Scope**: the shared foundation, extracted FROM three production
  agents — Research (T019), Product (T020), Executive (T021) — and
  nothing else. The rule is **extraction, not design**: an abstraction
  enters the kernel because three real implementations already contain
  it, not because it seems likely to be useful. No speculative
  abstraction; no capability the three agents do not already share.
- **Source**: `docs/COMPANY_OS.md` Part 2 (the AgentOS sketch) and
  `docs/V1_COMPLETION_ROADMAP.md` — deliberately built AFTER three
  agents exist, so the kernel is generalized from its users rather than
  ahead of them.
- **Files in scope**: new `src/intent_engine/agentos/`, tests, and
  **refactors of the three agents to consume the kernel** where the
  extraction is a genuine simplification (not a mechanical move). It
  writes no store of its own; it provides the shapes the agents already
  reimplement in parallel.
- **The shapes proven by three implementations, and therefore eligible**
  (name each in the audit, with the three call sites):
  (a) **the append-only store discipline** — flock, fsync,
  fingerprinted idempotency, loud corruption, no mutation API, the
  `(mtime_ns, size)` parse cache, and the one `_stable_id(key)` helper —
  reimplemented in `research/store.py`, `product/store.py`,
  `executive/store.py`; (b) **the canonical index contract** — folded
  from append-only rows, never model-written, orphan-rejecting,
  self-checking, lineage-answering — the Evidence, Opportunity, and
  Decision Indexes; (c) **the folded-state + transition-validation
  pattern**; (d) **the human-wall pattern** (`HUMAN_ONLY_EVENTS` + the
  actor check in `_record`); (e) **the model boundary** — injectable
  client, prompt/model versions recorded, the single recursive
  forbidden-field scan, a typed rejection on overreach, a typed fact on
  failure; (f) **the snapshot shape** — frozen versions across
  contributing subsystems plus source high watermarks, reproducible from
  the log; (g) **the company-event consumer + checkpoint + replay
  pattern**; (h) **the language wall** with word-boundary matching; (i)
  **the debt vocabulary shape** (research debt / spec debt / decision
  debt); (j) **the typed conflict taxonomy** (built in T021, now with a
  potential second user).
- **Definition of done (bars)**: (a) **the kernel is extracted, not
  invented** — every kernel module cites the three pre-existing
  implementations it generalizes, asserted by an audit test that fails
  if a kernel abstraction has fewer than the agents that already
  contained it; (b) **at least three agents consume each extracted
  shape** — a kernel primitive with fewer than two real consumers after
  the refactor is rejected as speculative; (c) **behaviour is unchanged**
  — the three agents' full test suites pass byte-for-byte in outcome
  after the refactor, and every replay still reproduces every derived
  artifact; (d) **one canonical implementation per shape**, replacing
  three, with the per-subsystem invariants tests updated to point at the
  kernel; (e) **agent registry** — a declared list of the production
  agents and their contracts, read-only; (f) **no new store, no new
  network, no new autonomous authority** — the kernel is plumbing, not a
  new actor; (g) language and determinism walls inherited; **0 live
  model calls and no network in the suite**; offline suite green +
  EXIT=0.
- **Walls**: extraction-only — no abstraction without three existing
  implementations; no behaviour change during a move; the three agents
  keep their contracts; the kernel writes no store and holds no
  autonomous authority; frozen library and prompts untouched; 0 network.
- **Repository invariants**: the standing section binds. This task is
  where the invariants stop being per-subsystem assertions and become
  the kernel's own contract — after T022, "one canonical implementation
  of each shape" is enforced in one place rather than re-proven in each
  agent.

## T023 — Personal AI Workspace (the first founder-facing product)

- **Status**: DONE 2026-07-21 (commits f59120f, 764e12c) — the first
  founder-facing product, built as a **conductor, not an analyst**:
  `src/intent_engine/personal/` owns conversation, memory, and
  orchestration, and **zero business intelligence** (a test proves no
  score / readiness / conflict / metric is computed in `personal/` and no
  fourth index is built). The canonical chain is structural — domain
  artifact → `SourceRef` → `SourceClaim` → composition → optional model
  wording over a **closed ClaimSet** → deterministic claim validation →
  cited answer — so an answer cites source ARTIFACTS (not merely agents),
  and a model narrative referencing a claim id outside the ClaimSet is
  rejected. Read **adapters** are the anti-corruption boundary: each
  normalizes one subsystem's public reads into `SourceClaim`s and derives
  / scores / ranks nothing. Disagreement is preserved (SUPPORTED /
  PARTIALLY_SUPPORTED / CONFLICTED / STALE / UNAVAILABLE / OUT_OF_SCOPE);
  freshness travels (CURRENT / STALE / HISTORICAL / UNKNOWN, never CURRENT
  by default). The morning brief is assembled and cited, with structured
  **investigations** (not imperatives); explainability expands any
  conclusion into Finding → Evidence → Confidence → Reasoning → Source
  Agent → Replay ID; three report profiles ship (morning brief, weekly
  founder review, board update draft), the rest registered-but-deferred. A
  board update is a **draft** and stays one — the service exposes no
  publish / send / execute / modify surface, and every cross-subsystem
  write would go through an existing human wall. Three memory lifecycles
  are kept apart, and a conversation turn is not durable memory unless the
  founder pins/saves/opens it; secrets are refused before storage.
  Snapshots capture source high-watermarks and state replay semantics
  honestly (deterministic artifacts byte-identical; model prose semantic).
  The dependency-gap protocol is exercised: competitor intelligence has no
  owner and degrades to OUT_OF_SCOPE (`docs/T023_DEPENDENCY_GAPS.md`).
  Canonical contract: `src/intent_engine/personal/records.py`. 43 tests,
  built against the real T019–T022. **Zero regression: every T019–T022
  test passed unchanged and those source trees are byte-untouched.**
  Personal AI Workspace V1: BUILT. Public onboarding / the packaged
  Executive Brief / any execution: NOT BUILT (T023.5 and later).
- **Priority**: 1. **Size**: XL.
- **Renamed 2026-07-21** from "Personal AI Layer". "Layer" is
  architecture; "Workspace" is a product — and this is the first
  founder-facing product, not another backend subsystem. Nothing before
  T023 changes: T019–T022 are stable, boring, and complete. The product
  evolves on top of them; the backend does not get rewritten because the
  product vision moved.
- **Mission**: turn AgentOS into a **believable executive partner** — the
  environment where a human *experiences* the reasoning the operating
  system can now produce. Not autonomy. Not marketing. Not execution.
  **Trust.** At the end of T023 the founder can sit down and spend a real
  hour working entirely inside the workspace.
- **Philosophy — conductor, never analyst**: the Personal AI owns
  conversation, context, and orchestration. It owns **zero business
  intelligence of its own.** Every fact, score, conflict, and conclusion
  comes from an existing agent; the workspace never invents knowledge, it
  asks the appropriate agent and merges the answers into one narrative. No
  agent ever talks directly to another — everything routes through the
  kernel.
- **The Personal AI owns**: conversations, memory, workspace state,
  sessions, personalization, briefings, orchestration, explanations,
  routing, citations, task management, and context assembly. It owns
  **no** domain reasoning.
- **Source**: `docs/COMPANY_OS.md` Part 9 (Personal AI as the
  orchestrator that learns the *why*), built AFTER the kernel so it
  composes one substrate rather than four bespoke ones.
- **Files in scope**: new `src/intent_engine/personal/`, tests. It READS
  every subsystem's public surface and the three agent indexes through
  the kernel (T022); it WRITES only its own append-only workspace log —
  the founder's questions, the briefings it assembled, the investigations
  it opened, the findings it pinned — and even that records the session,
  never an operational fact owned elsewhere.
- **Definition of done (bars)**:
  (a) **workspace foundation** — canonical contract, append-only store,
  and folded session state, built on the kernel's `AppendOnlyStore`
  (subclassed, not reimplemented); the language wall and model boundary
  are inherited from the kernel.
  (b) **the morning brief is assembled, not authored** — a deterministic
  composition of what the subsystems already report: research highlights,
  executive decisions, risks, open questions, and **recommended
  investigations** (not recommendations — investigations, the thing a
  founder acts on). Every line resolves by reference to the subsystem that
  owns it, and a gap is named rather than filled.
  (c) **conversation is the heart** — the founder asks questions ("why are
  we losing confidence?", "show the evidence", "what should I investigate
  next?", "challenge this assumption", "draft a board update") and every
  answer is composed from the agents and **cites its source agent**.
  Nothing is invented; a claim with no source agent is not produced.
  (d) **explainability, end to end** — any conclusion expands into
  Finding → Evidence → Confidence → Reasoning → **Source Agent** →
  **Replay ID**, so the founder can always see why the workspace believes
  something and reproduce it. This is a defining product characteristic,
  not a debug feature.
  (e) **workspace memory** — projects, open investigations, goals,
  questions, pinned findings, conversations, and reports. It references
  AgentOS; it **never copies operational data** into its own store,
  asserted by source inspection.
  (f) **executive reports** — daily / weekly / monthly / board / investor
  / hiring / product / research, each assembled entirely from existing
  agents, each line cited, each reproducible.
  (g) **cross-agent orchestration** — the workspace can ask Research →
  Product → Executive → Analytics → Knowledge and merge the answers into
  one narrative; no agent talks to another, everything routes through the
  kernel, asserted by source inspection.
  (h) **human authority, bounded** — the workspace may summarize,
  prioritize, explain, organize, and **draft**. It may **not** publish,
  email, modify business state, or execute any external action — asserted
  by test that it exposes no publish / send / execute / modify surface.
  Every cross-subsystem write goes through that subsystem's existing human
  wall.
  (i) **reproducible workspace snapshots**, a replay-safe read, and a
  **reads-only CLI**; **0 live model calls and no network in the suite**;
  offline suite green + EXIT=0.
- **Explicitly deferred to T023.5 (not in T023)**: entering an arbitrary
  company name + website; the public intelligence pass; the packaged
  Executive Brief / Proof of Understanding; any growth action; any
  publish. T023 is the *internal* founder workspace; T023.5 is where it
  becomes a public product.
- **Completion test (the hour)**: the founder can ask strategic questions,
  retrieve company knowledge, inspect executive decisions, review
  research, generate reports, build investigations, receive a morning
  briefing, and understand *why* the AI believes something — entirely
  inside the workspace. The founder cannot yet onboard an arbitrary
  company, generate the packaged Executive Brief, execute growth, or
  publish. Those are intentionally deferred.
- **Walls**: founder-facing, orchestration-only; owns no operational data
  and no business intelligence; no autonomous authority; every
  cross-subsystem write goes through an existing human wall; reuse the
  kernel and the three indexes rather than building a fourth memory;
  frozen library and prompts untouched; 0 network.
- **Repository invariants**: the standing section binds, enforced through
  the kernel — the workspace subclasses `AppendOnlyStore`, uses the shared
  language wall and model boundary, and adds no second copy of any kernel
  shape.

---

## The version roadmap (T023.5 onward — product expansion, not prerequisites)

*Rationale (2026-07-21): T001–T023.5 is the engineering journey to the
first sellable product. Everything after is expansion of capabilities, not
a prerequisite for launch. So numbering switches from tasks to product
versions at T023.5 — it communicates, internally and externally, that the
platform is complete enough to sell and the rest is growth. **Nothing
before T023 changes; everything after T023 is reframed.***

- **T023.5 — Founder Intelligence Experience** *(the commercial milestone)*
  — **Status: RUNNABLE.** Where the workspace becomes a public SaaS: a CEO
  enters a **company name + website**, the system runs a **public
  intelligence pass**, and presents (1) **Proof of Understanding** —
  company profile, business model, customer segments, competitor
  landscape, each with confidence and evidence; (2) **Executive
  Perspective** — perceived strengths, blind spots, where to spend
  executive attention, assumptions we'd investigate, what surprised us,
  questions we'd ask leadership, executive confidence, and *what we don't
  believe yet*; (3) **Conversation** — challenge any conclusion, show
  evidence, explore alternatives, generate board reports.
  - **Files in scope**: new `src/intent_engine/founder_experience/` (or an
    additive `personal/onboarding` surface), tests. It composes T023's
    workspace and the existing agents; it writes only its own session log.
  - **Bars**: (a) **the public intelligence pass is founder-gated and
    additive** — do NOT assume autonomous crawling; the ingestion path is
    whatever is founder-approved (supplied documents, an approved fetch),
    and a missing capability is a recorded dependency gap, not a silent
    scrape; (b) **Proof of Understanding cites evidence** — every profile
    claim carries a `SourceRef` and a confidence read from an agent, and an
    unsupported claim is UNAVAILABLE, never invented; competitor
    intelligence closes dependency gap 1 or is honestly OUT_OF_SCOPE;
    (c) **Executive Perspective preserves what we DON'T believe** — blind
    spots, unresolved assumptions, and *what we don't believe yet* are
    first-class sections, not omitted; disagreement is preserved;
    (d) **still proposal-first, still human-disposed** — the experience
    presents and drafts; it decides and executes nothing, asserted by
    test; (e) **every conclusion still cites its source agent and replay
    id**, reusing T023's exact answer contract so the public UI and the
    internal workspace share one provenance model; (f) **onboarding an
    arbitrary company writes no operational store** — the company's
    intelligence lives in the experience's own session log as references;
    (g) reproducible snapshots; a reads-only public surface; **0 live model
    calls and no network in the suite**; offline suite green + EXIT=0.
  - **Walls**: founder-gated ingestion only; no autonomous crawling; no
    execution; presents and drafts; reuse T023's provenance contract and
    the agents rather than a second intelligence engine; 0 network in the
    suite. This closes **V1.0**.

- **V1.0 — Company Intelligence Platform** *(T001 → T023.5)*: the first
  sellable product. The operating system that reasons, plus the founder
  workspace and the public intelligence experience that let a human trust
  and use that reasoning. **Everything through T023.5 is V1.0.**

- **V2.0 — Founder Growth Studio**: planning + the Creative Strategy Loop
  on top of V1.0. Still proposal-first; still human-disposed.

- **V2.5 — Execution Layer**: approval-based actions — the first time the
  system may act on the world, and only through explicit per-item human
  approval. Everything the earlier walls forbade lives here, behind a
  gate, never before.

- **V3.0 — Continuous Company Operator**: the standing, always-on
  composition of every prior layer. The end state, deliberately last.

The through-line is unchanged from T001: propose/recommend-first, the
human disposes, nothing acts without approval. The version scheme records
that V1.0 is a **launch boundary**, not just the next task.

## NEEDS-SPEC (real backlog items, no verifiable done-condition — never guessed at)

- **Overnight Task 4 — mechanism rendering in the premortem** — UNBLOCKED
  2026-07-18 (Task 3 unparked by human review after the v2 gate's two
  consecutive PASSes; see reports/overnight_trace.md addendum). Needs a
  written spec + bars before entering the runnable queue.
- **All-bucket baselines (option 2, docs/BA_ACCELERATION_PROPOSAL.md
  follow-up) — LATER by direct decision 2026-07-18**: extend the baseline
  pair to horizon buckets {14,30,90} alongside 60d. Momentum rule
  generalizes trivially; the base-rate constants require three new
  one-time frozen computations (per M8's own never-auto-refresh rule) —
  a deliberate, documented human decision pending. Do NOT implement
  until decided.

- **Recipient-verb-gate revisit** — PROGRESS.md's mom/brother-captions backlog
  note: "Revisit whether recipient-extraction should gate non-message domains
  during the data-foundation pass." No design decided; "revisit" is not a
  done-condition.
- **`gmail_act` recipient resolution** — PROGRESS.md line 530: contacts
  lookup vs. entity-memory learning vs. user disambiguation, explicitly "not
  yet decided how."
- **Multi-correction content-persistence gap** — PROGRESS.md line 702:
  recurring content elements don't reliably persist through a *second*
  correction. Explicitly "deferred until a real usage pattern forces the
  design" — the right fix isn't known, only the symptom.
- **Absorption-capacity `BusinessContext` field** — the bet-magnitude/reversibility
  proposal. Touches `PremortemAnalyzer`'s live prompt for a real user-facing
  feature; real design judgment required (which of the 3 extraction paths,
  exact threshold rules) even though a schema sketch exists. Too consequential
  for unattended execution regardless of spec completeness — excluded from
  the loop, not just unspecified.
- **3 job-agent-sourced candidate signatures** (`confounded_comparison`,
  `unvalidated_heuristic_edge_case`, `silent_state_collapse`) — named in the
  cross-project replication note, but no fix-category mapping, rationale
  text, or second confirming case has been designed yet. Real candidates,
  not ready to build.
- **Evaluation-stage build** — explicitly build-deferred by direct decision
  (no validation path exists yet: new held-out cases or the forward paper-log).
  Not a gap in specification — deliberately excluded from any task queue,
  autonomous or not, until that decision changes.
- **T001 test-quality nits, found in review, not fixed** — `tests/test_simulator_cli.py`: `test_main_requires_entity_id_flag` duplicates `test_build_parser_requires_entity_id`'s required-flag check, and `test_main_end_to_end_writes_entity_memory` asserts exact stdout/stderr wording (`"Saved to entity memory: ..."`), which a harmless copy edit would break. Flagged for a future cleanup pass only.

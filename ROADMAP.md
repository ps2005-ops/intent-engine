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

- **Status**: RUNNABLE
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

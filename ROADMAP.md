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

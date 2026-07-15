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
  real rehearsal (Auto mode), commit `8e0dbac` on `agent/T001` (local
  branch, no remote configured — not yet merged to `main`, pending
  review). 5 new tests, 470 passed / 1 skipped, zero regressions, real
  cost $0.9347. See `MORNING_REPORT.md` / `reports/` for the full record.
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

- **Status**: RUNNABLE
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

- **Status**: RUNNABLE
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

- **Status**: RUNNABLE
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

## NEEDS-SPEC (real backlog items, no verifiable done-condition — never guessed at)

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

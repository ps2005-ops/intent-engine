# Overnight trace

Session start: 2026-07-15 (real UTC timestamps recorded per task below).
Executing `~/Downloads/overnight-execution-plan.md` directly in this
session (not via `nightly_agent.sh`, which is separate infrastructure
built earlier tonight and not yet rehearsed) — this session already holds
full project context, so the plan's Part A protocol is applied here
directly rather than delegated to an unverified subprocess.

Pre-flight: baseline suite confirmed green (`test_simulator_e2e.py`'s
5 tests, which failed earlier tonight on Anthropic API credit exhaustion,
now pass — credits were added mid-session, confirmed via a real re-run,
not assumed). Starting branch: `main`, clean working tree.

Legend: **DONE** / **PARKED** / **SKIPPED-DEPENDENCY**.

---

## Task 1 — Prediction ledger (calibration substrate) — **DONE**

- Bars: (a) mocked round-trip + Brier math hand-checked against 3 known
  cases (0.9/happened=0.01, 0.2/did_not_happen=0.04, 0.5/happened=0.25,
  mean=0.10) — **PASS**, verified by direct pytest run, not assumed.
  (b) Full suite: 437 passed, 1 skipped, 1 deselected (the known-slow
  live vision test, separately confirmed passing earlier tonight) — zero
  regressions. **PASS**. (c) Zero changes outside new files + one new db
  table (`data/prediction_ledger.db`, created lazily on first write,
  not committed) — **PASS**.
- Spend: 0 live API calls (pure code + mocked tests, as scoped).
- Commit: `3024ef8`.
- Adjacent discoveries: none.

## Task 2 — Mechanism library v1 — **DONE**

- Bars: (a) all 8 present, each with >=1 real historical instance;
  well_documented tier ones carry a real citation URL, checked directly by
  a test — **PASS**. (b) mocked matcher tests (exact-match ranking,
  overlap-count ranking, genuine no-match returns `[]`) — **PASS**.
  (c) Full suite: 447 passed, 1 skipped, 1 deselected, zero regressions —
  **PASS**.
- Spend: 9 web searches (budget <=10), 0 model calls (matcher is pure
  code, confirmed by a signature-inspection test).
- Commit: `465d25b`.
- Adjacent discovery: 3 of 8 mechanisms' real citations are
  educational/advocacy-quality rather than primary/major-outlet —
  tiered "plausible" rather than "well_documented" on that basis, noted
  in the module docstring, not silently smoothed over.
- Design note (not a park — a reasonable, stated interpretation): 
  `match_mechanisms()` takes an already-extracted `List[str]` of trigger
  conditions rather than a `structured_intent` object, since no such
  object with trigger conditions exists until Task 3/4. Flagged in the
  commit and module docstring for human review, not hidden.

## Task 3 — Mechanism-extraction reliability gate — **PARKED**

- Real protocol run: `scripts/mechanism_extraction_reliability_gate.py`,
  5 runs × 3 decision texts, isolated + information-hidden extraction
  call (no mechanism names in the prompt).
- Real distributions:
  - `clear_supply_shock`: 5/5 identical — `['concentrated_supplier_base']`
  - `clear_price_war`: 5/5 identical — `['few_dominant_competitors', 'symmetric_competitor_response_expected']`
  - `ambiguous`: 5/5 identical — `['few_dominant_competitors', 'frequent_regulatory_interaction']` — **before** strengthening
  - `ambiguous`, round 2 (strengthened negative instruction): 5/5 identical, **same two conditions again**
- Bar (a) (>=4/5 modal agreement on both clear cases): **PASS** (5/5 both).
- Bar (b) (ambiguous case not confidently unanimous): **FAIL**, twice —
  parked per the task's own protocol, not pushed through with a guess.
- Spend: 20 live calls (budget <=40).
- Commit: `65e5d55`.
- **What a human should decide**: the two clear cases were narrow and
  precise (1-2 conditions each, not an over-triggering pattern), which
  suggests the "ambiguous" test text itself wasn't actually ambiguous on
  the two conditions it plainly stated ("some regulatory oversight," "a
  handful of larger companies") — a test-design issue, not necessarily
  proof the extraction over-triggers generally. But this script cannot
  rule out the latter on its own, and does not resolve the ambiguity by
  judgment per house rules. Two real options for a human to choose
  between: (1) redesign the ambiguous case to be genuinely uncertain on
  its own stated conditions and re-run the gate, or (2) treat this as
  evidence the extraction schema itself needs an explicit
  "insufficient evidence, select nothing" affordance made more prominent,
  and re-test that version.

## Task 4 — Wire mechanisms into simulator output — **SKIPPED-DEPENDENCY**

- Explicitly gated on Task 3's PASS verdict (plan's own dependency rule).
  Task 3 parked, so Task 4 was never attempted, per Part A4 ("if a
  dependency parked, park the dependent too"). No code touched, no bars
  checked, nothing to commit.

## Task 5 — Premortem to prediction-ledger bridge — **DONE**

- Path taken: Task 4 parked, so this bridges against **plain premortem
  output only** (RiskAudit.failure_modes), per the plan's own explicit
  fallback clause.
- Bars: (a) drafting schema structurally lacks any record/include/id
  field — checked directly by a test — **PASS**. (b) real run: 3
  predictions, all `0 < probability < 1`, all real DB-read-verified — 
  **PASS**, but only after a real fix (below). (c) full suite 454
  passed, 1 skipped, 1 deselected, zero regressions — **PASS**.
- **Real bug found and fixed within this task's own scope**: the first
  live run produced `resolve_by` dates in 2025 — already past relative
  to the real session date (2026-07-15) — because the model was never
  told the actual current date. Fixed: stated today's real date
  explicitly in the prompt, AND added a code-level backstop that rejects
  any non-future or malformed `resolve_by` before persisting (never
  trusted on the prompt instruction alone). Re-verified live after the
  fix: all 3 predictions had real future dates.
- Spend: 4 live calls (2 premortem + 2 bridge, across the pre-fix and
  post-fix verification rounds; budget <=6).
- Commit: `0eca6a9`.
- **Adjacent discovery, not fixed here** (per A3's "no task may expand
  its own scope" — flagged, not silently patched): `prediction_ledger.py`
  (Task 1, already committed) does not normalize `entity_id`, unlike
  `core/entity_memory.py`'s established `normalize_entity_id` convention
  — the same real fragmentation risk ("Sarah's Startup" vs. "sarahs
  startup" becoming different entities) that convention exists to
  prevent. A human should decide whether to add normalization to
  `record_prediction()` to match the rest of the codebase.

## Task 6 — Scrap supply-web graph v0 — **DONE**

- Bars: (a) node/edge counts hand-derived independently against
  real-record-shaped fixtures (4 nodes, 3 edges from 3 scrap-checks + 1
  reinforcing weigh-in, computed by hand in the test, not copied from the
  implementation) — **PASS**. (b) `affected_by()` correct on a
  hand-checkable constructed 6-node graph at hops 1/2/3, including a
  cap-respected-exclusion test proving the BFS doesn't silently walk
  past its stated limit — **PASS**. (c) every edge carries real
  `source_record_ids` — **PASS**. (d) full suite 464 passed, zero
  regressions — **PASS**.
- Spend: 0 live calls (deterministic, as scoped).
- Commit: `9397415`.
- **Real, honest finding, not glossed over**: this repo's actual
  `data/entity_memory.db` has zero real scrap-check records as of
  tonight — checked via a direct query before writing any code, not
  assumed. A dedicated smoke test asserts the graph builder handles this
  real-but-empty input honestly (0 nodes, 0 edges returned), rather than
  only ever being tested against synthetic fixtures.
- **Adjacent, structural honesty**: `buyer` nodes and
  `buys_from`/`ships_material` edges are schema-supported (per the
  task's own NamedTuple shape) but have zero real population source
  anywhere in this codebase — no "who bought the processed scrap"
  concept exists yet. Left empty rather than fabricated to look
  populated.

## Session close-out

All 7 tasks in Part B executed, in order, per Part A's protocol.

**Final tally**: 5 DONE (Tasks 1, 2, 5, 6, 7), 1 PARKED (Task 3), 1
SKIPPED-DEPENDENCY (Task 4). 6 real commits, one per task
(`3024ef8`, `465d25b`, `65e5d55`, `0eca6a9`, `9397415`, `a0db12a`), plus
one prior commit for the already-finished, separately-built
nightly-agent infrastructure (`ba0bd58`) and one for the cross-project
replication analysis (`8318e9d`) that preceded this plan tonight.

**Final, complete suite run** (not deselected — includes the one
known-slow live vision test): **465 passed, 1 skipped, zero
regressions**, 392.10s.

**Working tree**: clean, on `main`, no stray branches, no dirty state
left behind. This plan committed directly to `main` throughout (per Part
A2's literal instruction — no per-task branches), unlike the separate
`nightly_agent.sh` infrastructure built earlier tonight, which uses
`agent/<task-id>` branches for its own, different, not-yet-rehearsed
subprocess-based flow.

**Total real spend**: 20 (Task 3) + 4 (Task 5) = 24 live API calls,
9 web searches (Task 2). No task exceeded its stated budget.

**What a human needs to decide, collected in one place** (each also
detailed in its own task entry above):
1. Task 3's PARK: redesign the "ambiguous" test case and re-run the
   reliability gate, or add a more prominent "insufficient evidence"
   escape hatch to the extraction schema — real, un-resolved choice.
2. Task 1's adjacent discovery: should `prediction_ledger.py`'s
   `entity_id` be normalized, matching `core/entity_memory.py`'s
   established convention? Not fixed under Task 5's scope, per house
   rules on scope walls.
3. Once Task 3 is resolved, Task 4 (mechanism rendering) can be
   attempted for real.

No hard walls were crossed. No new external dependencies were added. No
force-pushes, no history rewrites, no deletions. Every live-API bar was
checked against a real value, never assumed.

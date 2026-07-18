# OVERNIGHT EXECUTION PLAN — Causal Intent Engine Focus
*This document is the primary authority for unsupervised overnight sessions.
If a task's instructions conflict with the Global Protocol, the Protocol
wins. If reality conflicts with this document (a file doesn't exist, a test
fails unexpectedly), PARK the task — never improvise through a conflict.*

=====================================================================
## PART A — GLOBAL AUTONOMY PROTOCOL (applies to every task, every night)
=====================================================================

### A1. The prime rule
You are running without a human gate. Every gate the human normally
supplies ("show me real output," "that's not verified," "stop") must be
replaced by the machine-checkable bars in each task. If a situation arises
that no bar covers, PARK (A4) — do not resolve ambiguity by judgment.

### A2. Task lifecycle
1. Read the task's GOAL, BARS, SCOPE WALLS, BUDGET.
2. Execute. Apply the fix library (PROGRESS.md design principles) before
   inventing solutions.
3. Self-check every bar. A bar is a deterministic predicate — run it, don't
   assess it.
4. ALL bars pass -> commit (one commit per task, message references the
   task ID), write the task's TRACE entry, proceed to next task.
5. ANY bar fails after reasonable attempts within budget -> PARK.

### A3. Hard walls (never cross, any task, any reason)
- No new external dependencies. If a task seems to need one, PARK.
- No vendor accounts, no OAuth flows, no network calls beyond the Anthropic
  API and (where a task explicitly grants it) web search / yfinance.
- No modifications to: PremortemAnalyzer's combined-call prompt,
  entity_memory schemas (additive columns ONLY where a task explicitly
  grants), the scrap-metal live path, voice/cli.py wiring.
- No rule/model changes tuned against the 18 backtest cases (overfitting
  guard — permanent).
- No force-pushes, no history rewrites, no deleting files (archive instead).
- No task may expand its own scope. Adjacent discoveries -> TRACE notes.

### A4. Parking protocol
A parked task gets a TRACE entry: task ID, what was attempted, which bar
failed or what ambiguity arose, exact error/output, what a human should
decide. Then move to the NEXT task — a parked task never blocks the queue
unless it is a declared dependency of the next task (dependencies are
explicit in Part B; if a dependency parked, park the dependent too).

### A5. Budget discipline
- Per-task API budget stated in each task (units: individual API calls).
- Track spend per task in the TRACE. Budget exhausted -> PARK with spend
  recorded.
- Live-model reliability tests are the expensive item: never exceed the
  stated run counts. Mocked tests are free — prefer them for plumbing.

### A6. The morning contract (write this file every session)
Write/overwrite reports/overnight_trace.md containing, per task:
STATUS (done/parked/skipped-dependency), bars checked with real values,
commit hash if done, spend, and any adjacent-discovery notes. This file is
the product of the night as much as the code is.

### A7. Suite discipline
Full offline suite (pytest -q, excluding known live-API tests) must be
green before EVERY commit. A regression introduced by task N must be fixed
within task N's budget or task N is reverted and parked — never leave the
suite red for the next task.

=====================================================================
## PART B — THE TASK QUEUE (execute in order; dependencies noted)
=====================================================================

The strategic frame (from the reviewed direction): the Intent Engine's next
form is structural-not-statistical guessing with earned confidence — four
pillars: (1) causal entity-relationship graph, (2) game-theory
formalize-solve-interpret, (3) calibration as the measure of knowing,
(4) a mechanism library. Sequencing: calibration and mechanisms first (they
upgrade the flagship immediately and need no new data), graph scoped to the
scrap supply web (real entities, real invoices, an expert user), game
theory LAST (needs the graph's extraction layer to exist first).

---
### TASK 1 — Prediction ledger (calibration substrate)  [BUILD]
GOAL: core/prediction_ledger.py + SQLite table `predictions`:
(id, created_at, source: Literal["premortem","scrap","digest","manual"],
entity_id, claim_text, probability: float 0-1, resolve_by: date,
resolved_at, outcome: Literal["happened","did_not_happen","unresolvable"],
brier_component: float, resolution_note). Functions: record_prediction(),
resolve_prediction() (computes Brier component in code at resolution —
never model-asserted), brier_summary(source=..., window=...) returning
count/mean-Brier/calibration-buckets (predicted-decile vs. realized rate).
BARS: (a) mocked tests: record/resolve/summary round-trip, Brier math
asserted against hand-computed values for 3 known cases, unresolvable
excluded from Brier; (b) suite green; (c) zero changes outside new files +
db schema addition.
SCOPE WALLS: no wiring into PremortemAnalyzer or any live path yet. No
backfilling old predictions. No UI.
BUDGET: 0 live API calls (pure code+mocked). 
DEPENDS: nothing.

---
### TASK 2 — Mechanism library v1 (data + schema + matcher)  [BUILD]
GOAL: core/mechanism_library.py + data/mechanisms.json. A Mechanism is:
(mechanism_id, name, closed-taxonomy trigger_conditions:
List[Literal[...]] — design the Literal set from the seed mechanisms
below, keep it small and honest, causal_chain: List[str] (ordered,
human-readable steps), historical_instances: List[{case, year, source}],
confidence_tier: Literal["well_documented","plausible","speculative"]).
Seed with EXACTLY these 8, researched via web search with real citations
(if a citation can't be found, tier it "speculative" and say so — never
fabricate a source): supply-shock propagation, prisoner's-dilemma price
war, regulatory-capture race, platform envelopment, credit contagion,
ally-drawn-into-linked-conflict, winner's-curse acquisition, debt-fueled
capacity race. Matcher: match_mechanisms(structured_intent) -> ranked
candidate mechanisms via deterministic trigger-condition overlap (code,
not LLM).
BARS: (a) all 8 mechanisms present, each with >=1 historical instance;
well_documented tier requires a real citation string; (b) mocked matcher
tests: a constructed intent matching exactly the expected mechanisms, a
no-match case returning empty (not forced); (c) suite green.
SCOPE WALLS: matcher is NOT wired into PremortemAnalyzer's output. No LLM
call in the matcher itself. Web search allowed for citations only.
BUDGET: <=10 web searches, 0 model calls.
DEPENDS: nothing.

---
### TASK 3 — Mechanism-extraction reliability gate  [TEST-ONLY]
GOAL: the one new LLM capability this plan needs: extracting a decision's
trigger-condition profile (the closed taxonomy from Task 2) from decision
text, isolated call, information-hiding (no mechanism names/library in the
prompt — extraction sees only the taxonomy of trigger conditions).
Standard reliability protocol: 5 runs x 3 decision texts (construct one
clearly matching supply-shock triggers, one clearly matching price-war
triggers, one deliberately ambiguous).
BARS: (a) stable modal extraction on the two clear cases (>=4/5 agreement);
(b) the ambiguous case must NOT produce confident unanimous triggers —
if it does, apply strengthened-negative-instruction once and re-run; if
still overconfident, PARK with distributions recorded; (c) real
distributions in the TRACE, per house rules.
SCOPE WALLS: test scaffolding only — no production wiring regardless of
outcome. This task's verdict gates Task 4.
BUDGET: <=40 live calls (2 protocol rounds max).
DEPENDS: Task 2.

---
### TASK 4 — Wire mechanisms into simulator output  [BUILD, GATED]
ONLY IF Task 3 passed. GOAL: a separate, additive section in the premortem
rendering: "Structural mechanisms possibly in play: [name] (tier,
matched on: conditions, historical instance: X)" — extraction call (Task
3's prompt) -> deterministic matcher (Task 2) -> rendered list. The
combined-call prompt is UNTOUCHED (hard wall A3) — this is the LuckTest
isolation pattern.
BARS: (a) one real end-to-end premortem run on a fixture decision showing
the mechanism section rendering with a genuinely matched mechanism; (b) a
no-match decision rendering NO section (silence correct, no forced match);
(c) suite green, zero regressions; (d) every rendered mechanism claim
carries its matched-condition provenance.
SCOPE WALLS: no probability/prediction language in the rendering ("possibly
in play," never "will happen"). No ledger wiring yet.
BUDGET: <=8 live calls.
DEPENDS: Tasks 2, 3.

---
### TASK 5 — Premortem -> prediction-ledger bridge  [BUILD]
GOAL: after a premortem run, derive 1-3 RESOLVABLE predictions from its
risk flags (e.g. "burn exceeds revenue growth within 2 quarters") via one
isolated LLM drafting call whose schema has ONLY claim_text/probability/
resolve_by fields — inclusion/recording is code; the model cannot record
anything itself (house pattern). Record to the ledger source="premortem".
Render nothing new to the user yet.
BARS: (a) mocked: drafting schema structurally lacks any record/include
field (assert absence, Stage-2-citation style); (b) one real run producing
1-3 predictions with sane probabilities (0<p<1) and future resolve_by
dates, recorded rows verified by direct DB read; (c) suite green.
SCOPE WALLS: no auto-resolution, no scoring display, no backfill.
BUDGET: <=6 live calls.
DEPENDS: Tasks 1, 4 (if 4 parked, this may still proceed against plain
premortem output — note which path was taken).

---
### TASK 6 — Scrap supply-web graph, v0 (dad's domain)  [BUILD, SCOPED HARD]
GOAL: the #1 pillar at its smallest honest scale. core/entity_graph.py +
SQLite tables nodes(node_id, kind: Literal["supplier","material","buyer",
"entity"], label) and edges(src, dst, kind: Literal["supplies","buys_from",
"ships_material"], first_seen, source_record_ids). Population is
DETERMINISTIC ONLY in v0: derive nodes/edges from existing scrap-check and
weigh-in records in the real DB (supplier entities, material types) — NO
LLM extraction of news/filings yet (that's the future, not tonight).
One propagation primitive: affected_by(node, hops<=2) returning the
reachable subgraph with edge-path provenance.
BARS: (a) graph built from the repo's REAL data — node/edge counts
asserted against a hand-derived expected set in the test (compute the
expectation from the same fixtures, independently); (b) affected_by()
returns correct reachable sets on a constructed 6-node test graph
(deterministic, hand-checkable); (c) every edge carries source_record_ids;
(d) suite green.
SCOPE WALLS: no news ingestion, no LLM population, no shock semantics
(that needs mechanism integration — later, supervised). No rendering in
any CLI yet.
BUDGET: 0 live calls.
DEPENDS: nothing (parallel-safe).

---
### TASK 7 — Documentation close-out  [DOCS]
GOAL: PROGRESS.md gains a "Causal-engine pillar status" section: what each
of the four pillars now has (ledger, mechanisms+gate result, bridge, graph
v0), what was parked and why (from the TRACE), and the explicit statement
that game theory (#2) remains unstarted BY DESIGN — it needs the
extraction layer matured first. Update the context doc's plan section is
NOT your job (human/chat-side artifact) — note in TRACE that it needs
updating instead.
BARS: section present, accurate against the night's actual TRACE, committed.
BUDGET: 0.
DEPENDS: all prior (runs regardless of parks — it documents reality).

=====================================================================
## PART C — WHAT THIS PLAN DELIBERATELY DOES NOT DO (so the agent
## doesn't "helpfully" do it)
=====================================================================
- No game-theory solver work (pillar #2) — gated on extraction maturity.
- No LLM population of the graph from news/filings — a supervised future
  phase with its own reliability gates.
- No Brier-based confidence-interval adjustment anywhere — the ledger must
  ACCUMULATE resolved predictions first; earned confidence comes later.
- No changes to scrap, captions, digest, observer, or voice domains.
- No evaluation-stage build (still validation-gated), no Part 5
  orchestrator build (its replay verdict is still the open gate), no
  retrieval restructuring.
- No cleanup pass (deferred to end of build phase, standing decision).
- Nothing user-facing changes its wording/behavior except Task 4's
  additive mechanism section.

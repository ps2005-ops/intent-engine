# MORNING HANDOFF — loop 22 (2026-07-21) — Personal AI Workspace V1 BUILT (V1.0 boundary)

*Suite at close: **1491 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-22 commits: `f59120f` (contract + SourceRef/SourceClaim + store +
three memory classes + adapters + router), `764e12c` (brief, conversation
with claim-set model validation, explainability, reports, service,
snapshots, CLI, founder-usefulness fixture) + docs. **Personal AI
Workspace V1: BUILT.** 43 new tests, built against the real T019-T022.*

**This is the V1.0 launch boundary.** The numbered auto-task queue
T001-T023 is complete. What remains — T023.5 (Founder Intelligence
Experience) and the V-series — is human-sequenced product expansion,
recorded in the version roadmap as bullets, deliberately NOT `## T0NN`
headings. `pick_next_runnable` now returns None and the nightly loop stops
cleanly at the boundary: a commercial milestone is a human decision to
start, not an unattended overnight run.

**The five things worth knowing.**

1. **It is a conductor, not an analyst — enforced, not just intended.** The
   workspace owns conversation, memory, and orchestration and ZERO business
   intelligence. A test proves `personal/` computes no score, readiness,
   conflict, or metric and builds no fourth index. Every fact comes from an
   agent, read through an adapter the workspace owns.
2. **Trust is the product, and provenance is how it's earned.** An answer
   cites source ARTIFACTS, not merely agents: SourceRef names one artifact
   with its replay id, snapshot version, as_of, and freshness. The chain is
   structural — domain artifact -> SourceRef -> SourceClaim -> composition
   -> optional model wording over a CLOSED ClaimSet -> deterministic claim
   validation -> cited answer. A model narrative that references a claim id
   outside the ClaimSet is rejected; the model never writes an identifier
   or a citation.
3. **Disagreement and freshness travel; nothing is smoothed.** A CONFLICTED
   research conclusion stays CONFLICTED in the answer; an UNAVAILABLE metric
   stays UNAVAILABLE; a stale claim says so. "Summarize competitors" has no
   owning subsystem and degrades to OUT_OF_SCOPE honestly rather than
   inventing — the dependency-gap protocol in action
   (`docs/T023_DEPENDENCY_GAPS.md`).
4. **It drafts; it does not act.** A board update is a DRAFT and stays one.
   The service exposes no publish / send / execute / modify surface, and
   writes no other subsystem's store. Durable memory (goals, pins,
   investigations) is a founder-only act — a conversation turn does not
   become durable memory merely because it was said. Secrets are refused
   before storage.
5. **Zero regression, and the frozen trees are byte-untouched.** The full
   suite passed 1448 before and 1491 after, the +43 being only the new
   personal tests. T019-T022 source trees are unchanged since the session
   baseline — the workspace composed the backend, it did not touch it.

**Two honest scope calls (your improvements, folded in):** the read
adapters are anti-corruption boundaries (they normalize and cite; they do
not derive/score/rank), and snapshots state replay semantics precisely —
deterministic artifacts replay byte-identically, model prose replays
semantically only when the NarrativeCandidate or the same fake client is
reused. Exact conversational reproduction of free-running model prose is
not promised.

## Previous handoff (loop 21, 2026-07-21) — AgentOS Shared Kernel V1 BUILT (extraction)

*Suite at close: **1448 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-21 commits: `3105125` (extract the kernel), `02e5a67` (migrate the
three agents onto it; invariants + zero-regression) + docs. **AgentOS
Shared Kernel V1: BUILT.** 27 new tests, all kernel; not one existing
test changed its expectation.*

**This was an extraction session, not a feature session — on purpose.**

You now have three production agents (Research, Product, Executive). T022
was the moment most projects wreck their architecture by "generalizing"
too early. The rule I held: **three implementations before one
abstraction.** Nothing entered `src/intent_engine/agentos/` that did not
already exist, byte-for-byte, in all three agents.

**The four things worth knowing.**

1. **The kernel is real code now, extracted not designed.**
   `agentos/append_only.py` holds the flock/fsync/idempotency/parse-cache
   store discipline the three agents each carried an identical copy of —
   the three agent stores now subclass it and keep only their domain query
   methods. Same for the language wall, the model boundary (provenance +
   the recursive forbidden-field scan), and the stable-id helper. Agent
   store code went from 338 lines to 123; about ~250 lines of triplicated
   infrastructure are gone.
2. **Zero behavioural change, and I mean zero.** The full suite passed
   1421 before and 1448 after — and the +27 are only the new kernel tests.
   No existing test changed its expectation (the one exception is the
   `test_pick_next_task` queue marker, `{T022}` → `{T023}`, which moves
   once per session by design). A test rebuilds a store through the kernel
   and asserts byte-identical replay.
3. **Nothing domain-specific entered the kernel, and a test enforces it.**
   Scoring, the six readiness dimensions, the conflict taxonomy, every
   debt vocabulary, both portfolios, every graph, and the Decision Context
   all stayed in their agents. `test_domain_concepts_never_entered_the_kernel`
   fails if any of them appears in `agentos/`, and the kernel imports no
   research/product/executive/growth/crm/marketing/knowledge module.
4. **Two honest scope calls, both recorded.** Research's model wall is a
   different, stricter, source-anchored check (a claim must be locatable in
   its registered source), so only its provenance shape was shared — the
   wall itself stayed local. And the older T013-T018 stores (events, crm,
   knowledge, marketing, growth) were NOT migrated: they predate the agent
   pattern, some carry genuine variations (the event bus's checkpoints,
   growth's namespacing), and disturbing stable code would risk the
   zero-regression rule for no in-scope benefit. Migrating them is a clean,
   separate follow-up — deliberately not done here.

**The audit trail you asked for** is `docs/AGENTOS_EXTRACTION_REPORT.md`:
the shape-by-shape extraction table, what was removed, what was
intentionally left local and why, which public APIs changed (none), and
which tests prove behaviour is identical.

## Previous handoff (loop 20, 2026-07-21) — Executive Decision Intelligence V1 BUILT

*Suite at close: **1420 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-20 commits: `029f714` (contract + append-only store + lifecycle
fold), `c6f89b9` (the Decision Index + the DecisionService resolver
boundary), `775dee8` (decision debt, aging, expiry, intake), `0324e1c`
(the typed conflict taxonomy + Conflict Summary), `b0730d3` (readiness,
impact, reversibility, context), `3fe77db` (packages, options,
escalation, no-recommendation, override), `c384a37` (triage queues,
portfolio, health dashboard, traceability), `4553cbf` (snapshots,
consumer, CLI, end-to-end, repository invariants) + docs. **Executive
Decision Intelligence V1: BUILT.** 112 new tests (1308 -> 1420).*

**The five things worth knowing.**

1. **It owns exactly one thing — decision candidates — and the queue is
   the artifact.** The question is triage: "given everything we know,
   what decision deserves your attention next?" A decision package is
   what you get when you open a queued candidate. There are three
   queues, not one — strategic, operational, maintenance — because a bug
   fix and an acquisition are not comparable, and forcing them into one
   list produces a ranking nobody can act on. Ordering within a queue is
   a fixed-precedence tuple (decision-ready first, then escalation,
   conflicts, impact, debt, id), never a blended score, so every
   position is explainable field by field.
2. **It never averages a disagreement.** When Growth, Research,
   Analytics, and CRM point different ways, you get a typed Conflict
   Summary naming both sides, not a blended number — the disagreement is
   the most useful thing in the room, and a test proves no averaging
   code path exists. Nine conflict kinds, with staleness (two inputs
   true at different times, never reconciled) kept distinct from timeline
   (a scheduling disagreement).
3. **The Decision Index does not copy your decision store.** The other
   two indexes fold from their own log; this one would have to span the
   executive log AND DecisionService (SQLite). Rather than mirror
   decision state — which queries better and drifts — it stores
   decision_id references and resolves status live through
   DecisionService. A test proves no executive module writes
   decisions.db, creates a decision, or records a decision event.
4. **Six readiness dimensions, never one score, and a decision-readiness
   that is YES/NO.** A single number would hide which dimension is
   missing, and which is missing is the actionable part. Financial
   readiness is UNAVAILABLE unless you declare a budget — this repository
   holds no money data and will not invent one. Decision-readiness is
   not a confidence: you get "no — the experiment has not run and nobody
   owns it", which you can act on, rather than "0.62", which you cannot.
5. **Every recommendation carries alternatives, and declining is an
   answer.** Never approve/reject — always an option set, each option
   with benefits, costs, risks, unknowns, dependencies, and a declared
   reversibility (Type 1 vs Type 2). "No recommendation" is a
   first-class outcome with a stated gap and a review date. When you
   override — choose B where the recorded preference was A — both
   survive, immutably, for later prediction scoring. And every
   recommendation traces to a terminal state, where rejected and
   deferred are legitimate terminals; declining is never a dead end.

**Two design decisions I made explicitly (your §5 in the prompt).**

- **`growth.result_labelled` — left unclosed, deliberately.** It is in
  the company-event taxonomy with producer `growth_platform`, but no
  T018 path emits it. I did NOT wire it this session: the executive
  consumer does not need it (it consumes `decision.resolved`, which has
  a real producer, and reads accepted proposals from T020 directly), so
  closing it would be scope I do not need. It remains a clean, small
  T018 follow-up. Recorded rather than silently depended on.
- **No `product.proposal_ready` event either.** T020's bars anticipated
  one "if a real consumer exists (T021 will be one)". But adding it means
  modifying a closed taxonomy and T020's service, and the proposal
  intake I need is already deterministic and idempotent through
  `intake_from_accepted_proposals`, which reads the Product subsystem
  directly — the same discipline the CRM path used in T020. Adding the
  event stays a clean follow-up when a second consumer justifies it.

**Housekeeping done:** the Research agent (T019) registry entry, flagged
outstanding in the loop-19 handoff, is now written in `docs/AGENTS.md`
alongside the new Executive entry.

## Previous handoff (loop 19, 2026-07-21) — Product Strategy & Roadmap Intelligence V1 BUILT

*Suite at close: **1308 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-19 commits: `15d494f` (contract + append-only store + lifecycle
fold), `0975417` (problem statements, dedup, the Problem Index and the
Opportunity Index), `f689ab6` (automatic intake from research debt,
growth, CRM), `c573958` (deterministic multi-dimensional scoring),
`9932620` (proposals, spec drafts, proposal graph), `1cd5282`
(portfolio rollup, roadmap candidates, the proposed-diff wall),
`ec71d86` (snapshots, consumer, CLI, end-to-end, repository
invariants) + docs. **Product Strategy & Roadmap Intelligence V1:
BUILT.** 194 new tests (1114 -> 1308).*

**The five things worth knowing.**

1. **Nothing in this subsystem writes `ROADMAP.md`, and it is not a
   promise — it is a structure.** `product/roadmap_diff.py` never opens
   a file; the caller passes the roadmap text in and gets diff text
   back. There is no filesystem path through which a write could be
   added later by accident. The agent also cannot mark a candidate
   RUNNABLE: only a person moves an item into the queue the nightly
   loop picks from. Both are asserted, and `ROADMAP.md` is proven
   byte-identical after a full run.
2. **Problems are separate from opportunities, on purpose.** One
   problem — "new accounts stall before first value" — routinely
   carries three competing opportunities (a walkthrough, an email
   sequence, a pricing change). Collapsing them into one record
   destroys exactly the fan-out you choose between, so there are two
   indexes: a Problem Index and an Opportunity Index. Problems also
   evolve rather than sitting static: split, merged, retired,
   superseded.
3. **A missing input is UNAVAILABLE, never zero.** When no research
   package is linked, evidence coverage does not read 0.0 — it reads
   UNAVAILABLE, and the composite score is withheld with the gap
   *named* rather than imputed. Strategic alignment stays UNAVAILABLE
   until you declare it, because an agent does not decide strategy.
   Cost of delay is computed separately from the opportunity score, and
   its revenue component waits on a figure you declare, since this
   repository holds no revenue data and a fabricated one would get
   quoted later as though it were measured.
4. **Uncertainty travels.** An experiment labelled INCONCLUSIVE cannot
   produce a confidently-scored opportunity: the origin label is
   recorded at intake and caps every confidence derived from it, with
   the reason naming the label. The same holds for CONFLICTING
   research. `deferred` and `merged_into` are first-class review
   answers alongside accept and reject, because a system that models
   only two distorts the answer you actually gave.
5. **Every proposal states its unknowns, and a proposal claiming none
   is rejected.** `known`, `unknown`, and `assumptions` are stored
   separately and all three are mandatory. Spec drafts are bounded to
   nine sections — an `implementation`, `estimate`, `assignee`, or
   date field is rejected structurally — and every acceptance criterion
   has to state something a person other than its author can check.

**Two honest notes from this loop.**

- **A flaky test, observed once and not reproduced.**
  `tests/test_growth_store.py::test_concurrent_writers_do_not_corrupt`
  (a T018 concurrency test, 3 threads x 6 writes) failed once during a
  full-suite run, then passed 5 consecutive full-suite runs and 5
  isolated runs afterwards. No T020 code path touches growth. Recorded
  as a pre-existing load-sensitive flake rather than fixed, because
  fixing what I could not reproduce would be guessing. Worth watching.
- **`growth.result_labelled` has no producer yet.** It is in the
  company-event taxonomy with producer `growth_platform`, but no T018
  code path emits it — T018 publishes only `experiment_started` and
  `experiment_stopped`. The product consumer handles it correctly when
  it arrives, and the test publishes a real event on the real bus under
  the declared producer rather than changing T018 from this session.
  Closing this is a small T018 follow-up, named rather than improvised.
- *Housekeeping:* the loop-18 handoff (T019, Research & Evidence
  Intelligence) was never written — that loop updated `PROGRESS.md` and
  `ROADMAP.md` but not this file. Recorded so the gap is visible; the
  T019 record itself is complete in `ROADMAP.md` and `PROGRESS.md`.

## Previous handoff (loop 17, afternoon) — Growth & Experiment Intelligence V1 BUILT

*Suite at close: **1071 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-17 commits: `f8a0717` (contract + namespaced store + versioned
fold), `a90d2f0` (pre-registration, immutability, amendment
versioning), `f137501` (randomization, assignment, exposure,
survivorship funnel), `ec3cb7d` (stdlib statistics, labels, stopping,
founder overrides), `526196d` (snapshots, integrations, consumer, CLI,
e2e) + docs. **Growth & Experiment Intelligence V1: BUILT.***

**The four things worth knowing.**

1. **There is no `winner` field, anywhere.** A result is a label plus
   reasons plus its survivorship funnel. `DIFFERENCE OBSERVED` still
   carries `REVIEW REQUIRED` and says in its own text that it is not a
   conclusion. Without a control arm an experiment reads
   `OBSERVATIONAL ONLY` permanently, at any sample size.
2. **A satisfied stopping rule is a fact, not an action.** Nothing
   stops, rolls out, rolls back, launches, or reassigns itself — there
   is no such API at any layer. Stopping early without a satisfied rule
   degrades every later read, and your override, if you make one, is
   recorded as its own immutable fact that says the data did not make
   the decision.
3. **Statistics are stdlib-only and refuse to bluff.** You get per-arm
   counts, rates, a difference point estimate, and a 95% normal
   interval *only when its assumptions hold* — otherwise `UNAVAILABLE`
   with the failed assumption named. **Deliberately not implemented and
   awaiting your decision**: p-values, Bayesian posteriors, sequential
   corrections, CUPED. Each needs a declared numerical dependency
   (A3) and a design review; the point estimate still stands without
   them.
4. **Synthetic and production experiments cannot mix.** Separate store
   files, separate consumer checkpoints, independent replay — a
   cross-namespace row is a loud corruption error.

*Also fixed a real defect from loop 12: the `events/` gitignore rule was
unanchored and matched the source package `src/intent_engine/events/`,
not just the runtime log. Now `/events/`. Still open for you: the two
T009 live runs (A1); Calendar API enablement (403, GCP 965657964785).
Queue: **T019 — Research Agent** (propose-only; frozen library stays
frozen; no web ingestion until its own gate).*

## Previous handoff (loop 16, midday) — Marketing C3–C8 V1 BUILT

*Suite at close: **992 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-16 commits: `30bc874` (marketing contract + append-only store +
folded state), `f962738` (CRM audience + evidence honesty), `c5d9129`
(briefs, drafts, and the claim/quote/review/handoff walls), `5405abc`
(publication recording, performance observations, feedback loop),
`b77f6e9` (C3/C6/C7/C8 generators), `6226a08` (consumer, CLI, e2e) +
docs. **Marketing Automation C3–C8 V1: BUILT** — and note the honest
mapping: the plan's **C4 and C5 were already built** (T016 quote gate /
T014 CRM), so this session reused them instead of creating second
implementations, and built C3, C6, C7, C8 plus the campaign→brief→draft
→review→handoff→observation spine.*

**Two things for you specifically.**

1. **Your Monday cron fired.** `data/daily_runner_spend.jsonl` holds a
   real row: `2026-07-20, status ok, 2 model calls, 10 data calls, 3
   predictions recorded, 2 baselines`. That closes the PLAN_2026-07-21
   **A2** question ("verify live ledger accrual actually started") —
   accrual has started. The file is a runtime artifact and is now
   gitignored like the other data logs.
2. **Still yours to run**: the two remaining T009 live control-world runs
   (**A1**), and enabling the Google Calendar API for GCP project
   965657964785 (the live test's 403 is unchanged and stays outside the
   offline gate).

*Walls held: nothing published or sent; publication is only ever an
externally supplied observed fact; mechanisms.json and the analyzer
module are byte-identical after a full vertical run (asserted in-suite);
0 sandbox model calls. Queue: **T018 — Growth platform and experiments**
(pre-registered design, sample-size honesty, no causal claim without
design support).*

## Previous handoff (loop 15, morning) — Knowledge Promotion V1 BUILT

*Suite at close: **915 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-15 commits: `6db7d83` (append-only feedback ledger + quote-consent
gate — consent binds to the exact text AND intended use, approval is
human-only, revocation blocks future use, history preserved), `3859b8e`
(typed citations with uncited items rejected and below-gate analytics
unable to support a positive claim; insights proposed by systems but
validated only by humans against an exact revision; knowledge promoted
with mandatory scope/limitations/citations, versioned supersession,
typed retraction; mechanism proposals queued for human review),
`eb57aba` (checkpointed observation-only company-event consumer, CLI,
end-to-end promotion/rejection/wall coverage) + docs. **The frozen
mechanism library was never written to — asserted by byte identity in
two tests.** Consumption creates observations only; nothing
auto-promotes. Queue: **T017 — Marketing automation C3–C8** (drafts
only; publication and claims stay human-gated; reuse CRM/knowledge/
analytics rather than reimplementing). Still open for you: two T009
live runs (A1); Calendar API enablement (403, GCP 965657964785).*

## Previous handoff (loop 14, early) — Analytics V1 BUILT

*Suite at close: **885 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-14 commits: `60b8ae8` (metric models + decision lifecycle views —
versioned MetricResult, explicit UTC windows, UNAVAILABLE never
conflated with zero, stalled.v1), `aac36c8` (calibration views behind
the A-M5 gate: 29→TOO FEW RESOLVED TO CLAIM CALIBRATION, 30→count gate
with the founder-review caveat stated; brier_summary reused, never
forked), `40dfd50` (CRM funnel history-vs-current separation, report
metrics with NO OBSERVATION SOURCE honesty, per-consumer
lag/retry/DLQ health proven read-only), `a27bba8` (AnalyticsService +
read-only CLI + e2e incl. gate flip at exactly 30 + language wall over
the full snapshot) + docs. **Analytics and Calibration V1: BUILT.**
Analytics writes to no store (byte-identity tested). Queue: **T016 —
Knowledge promotion and feedback** (human-gated promotion; frozen
mechanism library untouched — proposals go to a review queue). Still
open for you: two T009 live runs (A1); Calendar API enablement (403,
GCP 965657964785).*

## Previous handoff (loop 13, late night) — CRM V1 BUILT

*Suite at close: **851 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-13 commits: `cb4c68a` (CRM store + identity — opaque ULID, exact
match only, no fuzzy merge), `17bdaef` (three folded lifecycle axes,
validated transitions, explicit-only terminal reopen), `e206061` (typed
decision links + the FIRST real company-event consumer: checkpointed,
idempotent, explicit-link-only identity, replay = zero duplicates),
`c6991be` (versioned health/conversion signals — missing data reads
UNKNOWN/UNAVAILABLE, never optimism, no probabilities), `9ea6951`
(outreach wall structural: no sent without prior human approval per
draft — the tracking-ledger-schema wall, now code), `fd1f89b` (e2e +
replay coverage incl. corrupted-CRM-cannot-break-the-platform) + docs.
**CRM and Customer Intelligence V1: BUILT.** Nothing sends anything;
`marketing/outreach/ledger.jsonl` untouched (empty; no migration
needed). Queue: **T015 — Analytics and calibration** (read-side
consumers; the A-M5 ≥30-resolved claim gate stays load-bearing). Still
open for you: two T009 live runs (A1); Calendar API enablement (403,
GCP 965657964785).*

## Previous handoff (loop 12, night) — Company Event System V1 BUILT

*Suite at close: **796 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit.
Loop-12 commits: `20a9c2a` (typed append-only company event store +
idempotent publisher — canonical contract in
`src/intent_engine/events/envelope.py`), `bfc0059` (DecisionEvent
bridge, one-way, replay = zero duplicates), `b181f34` (consumer
checkpoints, bounded retry, dead letters, replay CLI), `dd3079d`
(approval-wall events + real producers, observation-only) + docs. The
two walls are now STRUCTURAL: publication/claim transitions require a
human actor, and `content.published` requires a prior human
`content.approved` for the same subject. Decision state still folds
ONLY from the DecisionEvent store — the integration log never owns it.
**Company Event System V1: BUILT. Consumers: NOT BUILT.** Queue:
**T014 — CRM and customer intelligence** (first substantial consumer;
bars in ROADMAP.md). Still open for you: two T009 live runs (A1) and
the Calendar API enablement (403, GCP 965657964785).*

## Previous handoff (loop 11, evening) — Decision Platform V1 + Founder Report V1 BUILT

*Suite at close: **755 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit (guard
enforced). Loop-11 commits: `8abb2dd` (T010 Decision Record data layer,
hardened), `524296e` (Slice 1B: decision_id intake→record→ledger wiring,
idempotent, typed recovery events), `bfa0b3f` (Slice 2A: report reads
the record), `6e8d1b0`/`b34a9d3`/`74d9b1f` (T012 Slice 2B: three-axis
Evidence Confidence resolving the finding-#7 concern you flagged,
Alternatives Considered, nine-stage lifecycle, PDF metadata/footer) +
docs/status commits. Walls held: prompts/enum/mechanism library
untouched; **0 sandbox model calls**; nothing published, no accuracy
claim anywhere. **Decision Platform V1: BUILT. Founder Report V1:
BUILT.** Queue: **T013 — Company Event System** (bars in ROADMAP.md,
built from COMPANY_OS Part 3; no consumer systems until the log
exists). Still open for you: the two T009 live runs (A1) and the
Calendar API enablement (403 accessNotConfigured, GCP 965657964785).*

## Previous handoff (loop 10, afternoon) — B1/B2/C1/C2 DONE; A1 awaits your runs

*Suite at close: **694 passed, 0 failed, 2 skipped, 10 deselected
(live/networked)**, EXIT=0 explicitly checked before every commit (now
also enforced by a pre-commit hook). Loop-10 commits: `1c0aa1a` (B1
housekeeping), `97c586d` (B2 guard), `6190be2` (C1 content engine),
`fc392be` (C2 premortem PDF), `1ded8a1` (report v2 — your 12 feedback
items + Decision Intelligence architecture) + this handoff. Walls held: prompts/enum/
mechanism library untouched; **0 sandbox model calls** (the live e2e
tests were explicitly deselected/stripped of the API key in every suite
run); nothing published, no accuracy claim anywhere.*

## What closed this loop (PLAN_2026-07-21, run a day early)

1. **B1 — git state resolved.** The staged `git rm --cached` on the
   synthetic-worlds tree was undone (files re-added; contents were
   identical to HEAD, so nothing was lost). Finding: the "uncommitted
   pipeline edits" the plan listed were already in `0e2a0d1`/`9cd3c7d` —
   the scary status was an out-of-sync index, not lost work. Run-3
   outputs (archive + history row 3 + cross-run table), both plan docs,
   and `.gitignore` hygiene are committed. `git status` is clean.
2. **B2 — recurrence guard.** `scripts/precommit_guard.sh` (installed as
   the pre-commit hook; `scripts/install_precommit_hook.sh` re-installs
   it) blocks any commit with a staged-deleted/untracked
   synthetic-worlds tree and runs the offline suite with an explicit
   EXIT=0 check. 4 tests prove it triggers on the exact B1 failure mode.
3. **C1 — content engine.** `marketing/content_engine/render.py`:
   ContentSource (reuses the founder-report parser; parse-park on
   unknown shapes) → 5 drafts (website article, LinkedIn, X thread,
   newsletter, founder email), each carrying the T:1–T:6 trace table,
   each passing a *coded* claim audit (the outreach checklist rule as
   code) + the language walls. Drafts go to
   `marketing/content_engine/drafts/<date>/` — queue only, zero
   network, zero publish. 7 tests, including the real 2026-07-17 run
   rendered with the socket layer disabled.
4. **C2 — productized premortem PDF.** `render_premortem_pdf()` in
   `scripts/render_founder_report.py` emits the approved 9-section set
   ending in Prediction, via a dependency-free PDF writer (no new
   packages needed on your Mac). The "what we could not verify" block
   is mandatory and renders even when empty-labelled; honesty markers
   throughout; language + accuracy-claim walls run before any byte is
   written. 4 tests on a real analyzer fixture (fake client, 0 calls).

5. **Report v2 — your 12 feedback items, all implemented** (`1ded8a1`).
   Into the premortem PDF: Company Snapshot (#8), boxed Recommendation
   as a *decision framework with an explicit delay path* (#1),
   rule-computed Evidence Confidence gauge (#2 — and it says in the
   report itself that it means confidence in the analysis, not the
   future), numbered Assumptions with the "re-run because assumption #N
   changed" trigger (#4), facts/inference separation (#3), risk-level
   grouping HIGH/TAIL/MEDIUM/LOW (#10), "What would change this" (#5),
   auditable Appendix (#9), decision-loop framing (#12), and visuals —
   gauge, risk bars, boxed callouts, scenario tree (#11). Content
   engine: educational NONE MATCHED with all three beats (#7) and
   positioning-forward email/newsletter openers (#6). Your "don't make
   it AI-like" instruction is now enforced by a test: no exclamation
   marks, no emoji, no hype words in body copy.
   **One design note for your review**: Evidence Confidence counts
   "mechanism read not requested" and "no prediction recorded" as
   crosses, so a quick run without those legs reads LOW. That is
   deliberate (a thinner run *is* weaker evidence), but if you'd rather
   those be neutral rather than penalising, say so and I'll re-weight —
   it's a two-line rule change.
6. **Decision Intelligence architecture** — `docs/DECISION_INTELLIGENCE_
   ARCHITECTURE.md` captures the platform tree you sketched, maps every
   box to real repo paths, and grades the decision loop honestly. The
   one genuine gap it identifies is the **Decision Journal**: without
   it, a report is a snapshot rather than a living document. That's the
   highest-value next build in that direction and it pairs naturally
   with C4 (feedback loop) — both write append-only rows keyed to a
   decision.

## LEDGER SNAPSHOT (2026-07-20 ~12:00 ET, direct DB read)

- **Total: 12** (7 market, 3 premortem, 2 baseline) · resolved: 0 ·
  gate: ≥30 LIVE resolved per source. No accuracy claim until then.
- `data/daily_runner_spend.jsonl` does **not exist yet** — expected: the
  cron's first fire is **today 18:30 ET**. After ~18:35, that file plus
  new market/baseline ledger rows are the evidence it fired. If neither
  appears, the cron line was never installed — paste 1 from
  `cron_lines_to_install.txt` (idempotent), and note it fired late.

## YOUR LIST (the only founder-gated items)

1. **A1 — two more T009 live runs** (~$1.78, ≤100 calls each, any day):
   `python scripts/run_synthetic_world_eval.py --live` — run twice.
   Each auto-appends to the run history. That gives 5 total runs; I'll
   then compute the control-clean rate + spread across all 5 and close
   or quantify the stability question (A3 folds it into ROADMAP T009).
2. **After 18:30 ET today**: nothing to do if the cron fired — I'll
   verify the spend-log row + ledger growth by DB read next session.
3. One workspace note: a few zero-byte `.git/stale-lock.discarded` /
   `.git/objects/*/tmp_obj_*` files accumulated (the sandbox can create
   but not delete files in the repo). Harmless to git; delete at leisure:
   `find .git -name 'tmp_obj_*' -delete && rm -f .git/stale-lock.discarded .git/probe_a`

## NEXT BUILD ITEMS (C3–C8 backlog, DoD-ready in PLAN_2026-07-21)

C3 ledger→content event hook → C4 feedback loop → C5 lightweight CRM →
C6 commit-triggered content → C7 public SEO pages → C8 public roadmap
page. All emit drafts into the approval queue; publish/claim walls
unchanged. Phase 2 (weekly sector spanning) recommendation unchanged:
let a week of live v2 ledger data accrue first.

**Recommended re-sequencing after report v2**: pull the **Decision
Journal** forward and build it *with* C4. The report now produces a
recommendation, an assumption set, and a watch list — all three are
exactly what a journal entry needs, and without one the report can't yet
say "re-run because assumption #2 changed," which is the whole point of
numbering them. C4 + Decision Journal together close the loop in
`docs/DECISION_INTELLIGENCE_ARCHITECTURE.md`; C3/C5–C8 are unaffected.

*Recurring note: densification's value is DENSITY and BREADTH, not being
right; the synthetic eval's value is DIAGNOSIS, not a claim. Nothing this
loop tunes, filters, or cherry-picks; every marketing artifact is a
draft behind the approval + PUBLISHING_ENABLED walls.*

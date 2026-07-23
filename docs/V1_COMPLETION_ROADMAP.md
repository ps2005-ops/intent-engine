# V1 Completion — architecture review & implementation roadmap

*Written 2026-07-20, acting as Principal Architect / Staff Engineer.
Treats the current architecture as **Version 1 Complete**. The goal is no
longer adding ideas — it is to **finish incomplete systems, remove
duplication, connect isolated systems, and automate**, so the repository
gets simpler as it grows. This is a **review + sequencing artifact**: per
the standing gate, no code is written until a slice's eight-point
Definition of Done (Part E) is accepted.*

*Relationship to existing docs: this is the detailed build sequence that
`COMPANY_OS.md` Part 14 points to, the same way `overnight-execution-plan.md`
Part B is the detailed queue behind `ROADMAP.md`. It **feeds** `ROADMAP.md`:
an item here becomes a RUNNABLE roadmap task only once it has bars. It
replaces nothing.*

---

## Part A — Architecture review: the drift audit (evidence-grounded)

The biggest risk now is architectural drift, not missing features. Seven
findings, each verified against the code/docs this session, ordered by
severity. Some drift is **self-inflicted from the prior COMPANY_OS pass** —
named honestly, because a steward fixes its own drift first.

| # | Finding | Evidence (this session) | Severity | Fix → where |
|---|---|---|---|---|
| 1 | **The keystone gap: `decision_id` is prose, not code.** The event bus, CRM, APIs, cross-links, and knowledge base are all designed *on* a Decision Record that does not exist. | `COMPANY_OS.md` cites `decision_id`/Decision Record **14×**; `prediction_ledger.py` schema has **no** `decision_id` column (keys: `id`, `entity_id`, `source`); `grep decision_id src scripts marketing` → **0**. | **Critical** | Build the Decision Record first — Phase 1, Slice 1. |
| 2 | **Scratchpad ≠ repo.** The v2 architecture (Decision ID) and v3 report (3-axis confidence, Alternatives, versioning, 9-stage lifecycle) exist only in the working scratchpad. | Repo `render_founder_report.py` is **v2**: single Evidence-Confidence gauge, `Engine version` only, 7-step decision loop, no Alternatives, no Decision ID. | High | Land them **the repo's way** — Phase 1, Slices 2–3. |
| 3 | **Self-referential doc drift.** `COMPANY_OS.md` cites "the Decision-record backbone from `DECISION_INTELLIGENCE_ARCHITECTURE.md`" — but that doc doesn't contain it. | Repo `DECISION_INTELLIGENCE_ARCHITECTURE.md`: `grep "Decision ID\|decision_id\|Decision Record"` → **0**; it is still v1 (Decision Journal = the named gap). | High | Land v2 DI-arch so the reference resolves — Slice 3. |
| 4 | **Dangling source-of-truth.** A doc referenced as authoritative is absent at root. | `AGENTS.md §1/§4` and `PORTFOLIO.md` reference `market-engine-execution-plan.md`; not present at repo root. | Medium | Restore from git history or update the references — Part D. |
| 5 | **Doc proliferation at root.** Overlapping handoff/context/plan files; one 3,012-line history doc. | Root: `COWORK-HANDOFF-2026-07-17.md`, `MORNING_HANDOFF.md`, `MORNING_REPORT.md`, `intent-engine-context-3.md`, `overnight-execution-plan.md`; `PROGRESS.md` = 3,012 lines. | Medium | Docs index + one living handoff format + `docs/archive/` — Part D. |
| 6 | **Terminology overlap risk.** Two "operating system" docs with no stated boundary. | `COMPANY_OS.md` (company scope) and `DECISION_INTELLIGENCE_ARCHITECTURE.md` (engineering/decision scope) both use "Decision Operating System." | Low | One-line scope boundary in each header — Part D. |
| 7 | **An open design question, now resolvable.** The Evidence-Confidence "thin run reads LOW" concern was left for founder decision. | `MORNING_HANDOFF.md` §5 design note; `render_founder_report.py` computes one `level` from `n_cross`, so "leg not requested" penalizes like "evidence weak." | Low (win) | The v3 **3-axis split** resolves it — Slice 2. |

**The through-line:** the design is ahead of the implementation, and the
gap is concentrated in one primitive. Close the Decision Record and most
of the fifteen priorities stop being independent projects and become
consumers of one record — which is exactly the coherence the brief asks
for.

---

## Part B — The sequencing principle (dependency order, not list order)

The fifteen priorities are **not** independent, so they should not be built
in listed order. Their real dependency graph has one root:

```
                    ┌─ P1  Report lock (cross-links, lifecycle nav, badges)
                    ├─ P8  CRM keyed by decision_id
   P2 DECISION  ────┼─ P13 Event keys (decision_id payloads)
   RECORD (root)    ├─ P14 Public APIs (read from Decision Records)
                    ├─ P9  Knowledge (architectural decisions = records)
                    └─ P6  Personal AI (reasons over decision history)

   P13 EVENT BUS ───┬─ P10 Analytics (consumes events)
                    ├─ P8  CRM updates (consumes events)
                    ├─ P9  Knowledge updates (consumes events)
                    └─ P11 PM Agent (coordinates via events)

   P5 AgentOS / P6 Personal AI / P14 APIs = design early, BUILD when a real
   second consumer exists (avoid premature abstraction — TOOLS.md ethos).
```

So the build order is: **Decision Record → Report + DI-arch lock →
Event bus → {CRM, Analytics, Knowledge, Feedback} → {Growth, Research,
PM, Company-OS governance} → {AgentOS extraction, Personal AI, Public
APIs}.** Documentation + consolidation (P15) runs across every phase.

**A note on right-sizing the spec (repo-consistent).** This document gives
the **full eight-point DoD only for the first slice** (Part E), the one
you can approve and build now. Every later item carries a compact verdict
(the six questions + files + phase). Full bars are written when an item
reaches the front of the queue — the same discipline `ROADMAP.md` uses
("NEEDS-SPEC until it has a verifiable done-condition; never guessed at").
Writing eight-point bars for all fifteen now would itself be the bloat this
review is meant to prevent.

---

## Part C — The fifteen priorities, placed and verdicted

Each verdict answers: **Belongs? · Problem solved · Already exists? ·
Extend what? · Reduces complexity? · Sane at 100×?** — then names the files
and phase. Where the answer to "does this already exist / can it be
extended" makes a *build* unnecessary, it says so.

### Phase 1 — The keystone and the lock

**P2 · Decision Record** *(root dependency — build first)*
Belongs: yes, it is the backbone everything else keys to. Problem: artifacts
(report, ledger, CRM, content) share no identity, so a decision cannot be
retrieved as one history. Exists? Only the *ID concept* in prose. Extend:
the ledger (`prediction_ledger.py`) + a new `core/decision_record.py`.
Complexity: reduces it — one key replaces four implicit joins. 100×: an
addressable record is the only version that scales. → **Slice 1, Part E.**

**P1 · Lock the pre-mortem report** *(no new analysis sections)*
Belongs: yes — the report is feature-complete; this is polish + wiring, not
features. Problem: it shows a single confidence gauge, no Decision ID, no
navigation. Exists/extend: extend `build_premortem_sections()` +
`write_pdf()` in `render_founder_report.py`. Add **only**: Decision ID
header, status badge, owner, related-decisions/lifecycle nav (all reads of
the Decision Record), and land the deferred v3 polish — **3-axis Evidence
Confidence** (Evidence Quality / Reasoning Coverage / Prediction
Confidence, which *resolves finding #7*), Alternatives Considered,
component versioning, 9-stage lifecycle. **Not** the static v3 HTML — the
repo's PDF writer is dependency-free by design; the change is Python +
tests. Preserves: `assert_language_walls`, `_assert_no_accuracy_claim`,
parse-park. **Split per review point 11 → Slice 2A** (record wiring:
Decision ID/key, folded status badge, owner, `supersedes`, report metadata,
component versions) **and Slice 2B** (approved polish: 3-axis confidence,
Alternatives, lifecycle presentation, PDF polish) — one purpose per commit.

**P3 · Lock the Decision Intelligence architecture** *(engineering constitution)*
Belongs: yes. Problem: the repo doc is v1 and is *referenced by* COMPANY_OS
as if it carried the Decision-record backbone (finding #3). Extend, do not
rewrite: land the v2 content (Decision ID backbone, lifecycle, versioning)
and add only what P3 scopes — API layer, permission model, Decision Graph,
Decision-Record relationships, developer docs. No philosophy/terminology
change. Files: `docs/DECISION_INTELLIGENCE_ARCHITECTURE.md`. → **Slice 3.**

### Phase 2 — The nervous system and the record's consumers

**P13 · Event architecture** — append-only `events.jsonl` drained by the
nightly loop (no new dependency); payloads keyed by `decision_id` /
`prediction_id` / `prospect_id` / `event_id`; fan-out to drafts only; the
two walls are the only human-emitted events. Extends the existing
ledger→content fan-out and `premortem_prediction_bridge.py`. Already
specified in `COMPANY_OS.md` Part 3; this phase builds it. Sane at 100×:
swap the log for a broker without touching producers/consumers.

**P8 · CRM → customer intelligence** — extend C5 (`marketing/crm/`,
append-only `crm.jsonl`, keyed `prospect_id`). Add the intelligence fields
(industry, stage, company size, decision type, pain points, health score,
likelihood-to-convert, decision/referral history) and **link each to
`decision_id`** when a report is generated. Metrics computed by code;
per-message approval wall structural (no `sent` without prior `approved` +
`approved_by`). No scraped lists.

**P10 · Analytics** — PostHog (NOW-tier) as a **consumer** of the event
bus, not a parallel logger. Every metric ships with **why it exists / who
consumes it / what decision it improves** (the brief's rule, already
tabled in `COMPANY_OS.md` Part 11). Calibration stays gated behind A-M5 —
analytics never becomes a side door around the claim wall.

**P9 · Knowledge base promotion workflow** — one append-only
`knowledge/knowledge.jsonl`, many item types (not many stores). Complete
the promotion path *feedback → insight → validated → knowledge item →
mechanism → permanent reusable knowledge*, graduating validated lessons
*into code* (`diagnosis_registry.py`, `mechanism_library.py`) under their
existing gates. Every item cites its source, like every mechanism does.
Architectural decisions are stored as Decision Records (P2) with rationale.

### Phase 3 — The company layer

**P11 · Product Manager Agent — BUILT as the Product Strategy & Roadmap
Intelligence Platform (T020).** Read/propose-only, as specified. It turns
research debt, unsettled experiments, and customer facts into *candidate
opportunities*, and those into problem-first proposals, bounded spec
drafts, and roadmap candidates emitted as a proposed diff. It never
auto-promotes NEEDS-SPEC, never edits `src/` prompts, and — the wall that
turned out to be the load-bearing one — **never writes `ROADMAP.md`**:
the diff module opens no file at all, so the constraint is structural
rather than remembered. It gets the Problem Index and the Opportunity
Index as its canonical memory, exactly as Research got the Evidence
Index. Canonical contract: `src/intent_engine/product/records.py`.

**P12 · Research Agent** — paper ingestion, mechanism discovery, evidence
ranking, source verification, contradiction detection, citation
management. **Constraint (load-bearing):** it touches the mechanism
library, which is **frozen** (A3) and grows only through the reliability-
gated historical-study track. So Research Agent is **design-first**: it
drafts candidate mechanisms with citations into a review queue; promotion
stays human-gated. News/filings ingestion (Crawl4AI/Firecrawl) is
LATER-gated per `TOOLS.md`. Do not build ingestion ahead of its gate.

**P7 · Growth system** — documentation + plans for acquisition /
activation / retention / revenue / referral / lead scoring / lifecycle /
experiments / dashboard. Built on the funnel already in
`MARKETING_PLAN_V2.md`; states live on the CRM ledger (P8), not a new
store; experiments are pre-registered (the synthetic-worlds discipline) and
their results become knowledge items (P9). Every growth metric carries its
"why" (P10).

**P4 · Finish Company OS as the constitution** — add to `COMPANY_OS.md`:
core/architectural principles (partly present as Part 0), a capability
matrix, and the **governance** the brief names — decision-making process,
ownership model, review process, deprecation policy, versioning policy,
design-review + architecture-proposal workflows. This is the "how the
company works" layer; it formalizes the walls and the six-question gate
already in use.

### Phase 4 — Platform generalization (design early, build when forced)

**P5 · AgentOS as a real kernel** — design the kernel doc now (promote
`overnight-execution-plan.md` Part A → `docs/AGENTOS.md`): memory,
planning, scheduling, execution, permissions, events, logging, monitoring,
recovery, versioning, shared services — each already backed by a real
mechanism (`COMPANY_OS.md` Part 2). **Extract to a shared package only when
a second repo consumes it** (`job-application-agent` is the likely first).
Until then the kernel is a document agents follow, like `superpowers`.

**P6 · Personal AI** — design the memory hierarchy (working / long-term /
knowledge / project / relationship / preference) and reasoning modules
(planning, reflection, self-critique, decision support, simulation,
learning). The key requirement — *understand **why** decisions were made* —
is met by making its knowledge model the **Decision Records + rationale**
(P2/P9), not file recall. Build on `voice/` + the personal-domain apps
(`core/` scrap/fitness/music) once the record exists. Gated by
`permissions.py` and the two walls.

**P14 · Public APIs** — REST / MCP / SDK / webhooks / internal API, all
**reading from Decision Records** (P2), no duplicated logic. Gated on the
record existing **and** a real external consumer. An MCP server is the
natural first surface (it fits the existing tool ecosystem). Do not build
five surfaces ahead of one consumer.

### Cross-cutting

**P15 · Documentation + repo-wide consolidation** — runs alongside every
phase; the concrete plan is Part D. Every subsystem doc answers the seven
questions (purpose / how / depends / events / metrics / automation /
future); cross-reference instead of restating; archive obsolete docs,
never delete history.

---

## Part D — Consolidation plan (one source of truth per topic)

Concrete, additive, archive-not-delete (A3):

1. **`docs/README.md` index** — classify every doc into the five buckets
   (sources of truth / architecture / specs / knowledge / reports) so
   nothing is found by `ls`. (COMPANY_OS Part 5.)
2. **One living handoff format.** Keep `MORNING_HANDOFF.md` as the single
   living handoff; move `COWORK-HANDOFF-2026-07-17.md`, `MORNING_REPORT.md`,
   and `intent-engine-context-3.md` to `docs/archive/` with a one-line
   index entry each. History preserved, root de-cluttered.
3. **Fix the dangling reference (finding #4):** locate
   `market-engine-execution-plan.md` in git history and restore it, or
   update the `AGENTS.md`/`PORTFOLIO.md` references to point to
   `reports/market_engine_trace.md` (the surviving record).
4. **Terminology boundary (finding #6):** one header line in each OS doc —
   `COMPANY_OS.md` = *company scope*; `DECISION_INTELLIGENCE_ARCHITECTURE.md`
   = *engineering/decision scope*; both share the "Decision Operating
   System" internal lens.
5. **One-source-of-truth table** (add to the docs index):

   | Topic | Single source of truth |
   |---|---|
   | Autonomy protocol | `overnight-execution-plan.md` Part A → `docs/AGENTOS.md` |
   | Task queue | `ROADMAP.md` |
   | Marketing strategy | `marketing/MARKETING_PLAN_V2.md` |
   | Agent registry | `docs/AGENTS.md` |
   | Tooling decisions | `docs/TOOLS.md` |
   | Company architecture | `docs/COMPANY_OS.md` |
   | Engineering/decision map | `docs/DECISION_INTELLIGENCE_ARCHITECTURE.md` |
   | Build sequence | this file |
   | History + design principles | `PROGRESS.md` |

No prompts, agents, or automation are duplicated today (verified); the
duplication that exists is **documentation**, and it is resolved by
indexing + archiving, not rewriting.

---

## Part E — Slice 1, revised & fully specified: the Decision Record (event-sourced)

*Status (2026-07-20): **Phase 1 BUILT** — Slice 1 data layer commit
8abb2dd (hardened: FKs, append-only triggers on all four tables, atomic
supersession, payload validation, validated folding, idempotency-key
scoping); Slice 1B wiring commit 524296e (ledger reference, bridge
stamping, idempotent intake, typed failure/recovery events); Slice 2A
record → report wiring commit bfa0b3f; Slice 2B approved polish commits
6e8d1b0 / b34a9d3 / 74d9b1f (three-axis Evidence Confidence resolving
finding #7, Alternatives Considered, nine-stage lifecycle, PDF
metadata/footer polish). **Decision Platform V1: BUILT. Founder Report
V1: BUILT.** All bars proven by test; 0 live model calls. Slice 4 — the
**Company Event System — is now also BUILT** (T013, commits 20a9c2a /
bfc0059 / b181f34 / dd3079d: append-only log, canonical envelope in
`src/intent_engine/events/envelope.py`, idempotent publisher, one-way
DecisionEvent bridge, consumer checkpoints, bounded retry + dead
letters + explicit redrive, human-only approval-wall transitions).
**CRM and Customer Intelligence V1 is now also BUILT** (T014, commits
cb4c68a / 17bdaef / e206061 / c6991be / 9ea6951 / fd1f89b: append-only
CRM facts, folded three-axis lifecycle, typed decision links, the first
real checkpointed company-event consumer, versioned health/conversion
signals, structural outreach approval wall — canonical contract in
`src/intent_engine/crm/events.py`). **Analytics and Calibration V1 is
now also BUILT** (T015, commits 60b8ae8 / aac36c8 / 40dfd50 / a27bba8:
versioned read-side metrics, A-M5-gated calibration views reusing
brier_summary, CRM funnel + report + consumer-health views, one
AnalyticsService + read-only CLI — canonical contract in
`src/intent_engine/analytics/models.py`). **Knowledge Promotion and
Feedback V1 is now also BUILT** (T016, commits 6db7d83 / 3859b8e /
eb57aba: append-only feedback ledger with the exact-text human quote
gate, typed citations, human-gated insight validation and knowledge
promotion with versioning and typed retraction, mechanism proposal queue
that never writes the frozen library — canonical contract in
`src/intent_engine/knowledge/records.py`). **Marketing Automation C3–C8
V1 is now also BUILT** (T017, commits 30bc874 / f962738 / c5d9129 /
5405abc / b77f6e9 / 6226a08 — plan C4/C5 were already covered by
T016/T014 and are reused, not rebuilt; canonical contract in
`src/intent_engine/marketing/records.py`). **Growth & Experiment
Intelligence V1 is now also BUILT** (T018, commits f8a0717 / a90d2f0 /
f137501 / ec3cb7d / 526196d — pre-registration, deterministic
randomization, survivorship accounting, honest stdlib statistics,
label vocabulary without a `winner`, human-gated stopping and review;
canonical contract in `src/intent_engine/growth/records.py`).
**Research & Evidence Intelligence V1 is now BUILT** (T019, commits
eee7934 / d611bea / dbf69b7 — the Evidence Index is the shared evidence
substrate T020-T023 read instead of rebuilding; canonical contract in
`src/intent_engine/research/records.py`).
**Product Strategy & Roadmap Intelligence V1 is now also BUILT** (T020,
commits 15d494f / 0975417 / f689ab6 / c573958 / 9932620 / 1cd5282 /
ec71d86 — the Problem Index and the Opportunity Index are the shared
product substrate T021-T023 read instead of rebuilding; problem-first
proposals, deterministic multi-dimensional scoring with UNAVAILABLE never
zero, bounded spec drafts, an eight-edge proposal graph, portfolio rollup
with balance and decision debt, and roadmap candidates emitted as a
proposed diff that no code applies; canonical contract in
`src/intent_engine/product/records.py`).
**Executive Decision Intelligence V1 is now also BUILT** (T021, commits
029f714 / c6f89b9 / 775dee8 / 0324e1c / b0730d3 / 3fe77db / c384a37 /
4553cbf — the Decision Index is the third shared substrate; a triage
queue of decision candidates, a typed conflict taxonomy that never
averages, six independent readiness dimensions, mandatory alternative
decisions, founder override, expiry from a changed input rather than a
clock, and traceability to a terminal state; canonical contract in
`src/intent_engine/executive/records.py`).
**AgentOS Shared Kernel V1 is now also BUILT** (T022, commits 3105125 /
02e5a67 — the append-only store, language wall, model boundary, contracts,
registry, permissions, and telemetry extracted from the three production
agents with zero behavioural change and no new abstraction; audit in
`docs/AGENTOS_EXTRACTION_REPORT.md`). Personal AI (next: `ROADMAP.md`
T023), public APIs: **NOT YET BUILT**. Roadmap writing by an agent,
product execution, autonomous decisions, scheduling, ticketing, and any
new autonomous authority in the kernel: **NOT BUILT, and out of scope by
design**.*

*Revised agent sequence (2026-07-21). The infrastructure phase is
complete; what remains is composing these subsystems into agents. The
order below inserts an **Executive Decision Agent before AgentOS**
deliberately: generalizing a kernel from three real orchestrating agents
produces a better kernel than designing one ahead of its users.*

```
T019 — Research & Evidence Intelligence    BUILT. Evidence Index is the
                                           shared evidence substrate.
T020 — Product Strategy & Roadmap          BUILT. Problem Index and
       Intelligence                        Opportunity Index are the shared
                                           product substrate. Owns proposals,
                                           never decisions; never writes
                                           ROADMAP.md.
T021 — Executive Decision Intelligence     BUILT. Decision Index is the
                                           shared executive substrate.
                                           Answers "what decision deserves
                                           the founder's attention next" — a
                                           triage queue of decision
                                           CANDIDATES, with a package behind
                                           each. Owns candidates, never
                                           decisions. No autonomous
                                           execution.
T022 — AgentOS Shared Kernel               BUILT. Extracted FROM three
                                           production agents, not designed
                                           ahead of them: the append-only
                                           store, language wall, model
                                           boundary, contracts, registry,
                                           permissions, telemetry. Zero
                                           behavioural change.
T023 — Personal AI Layer                   founder workspace on AgentOS.
                                           Briefings, strategic conversation,
                                           portfolio navigation, decision
                                           history. No operational authority.
T024 — Public APIs & SDK                   read-only + approved-write surfaces;
                                           auth, versioning, SDKs, webhooks.
                                           Internal stores stay encapsulated.
T025 — V1 Stabilization & Release Audit    architectural integrity, replay
                                           correctness, docs consistency,
                                           dependency + security review, API
                                           stability, migration verification,
                                           frozen-asset validation, RC prep.
```

*Two substrates now anchor the agent tier: the **Evidence Index** (what
is true, and how well we know it) and the **Opportunity Index** (what is
worth doing, and why). T021–T023 read both rather than reconstructing
either — that is what makes the AgentOS extraction at T022 an extraction
rather than a redesign.*

*Revised 2026-07-20 after founder review. The one insisted change is
adopted in full: the record is **event-sourced**. State is never stored as
mutable fields on one record; it is **folded from an append-only event
stream**. This preserves the append-only wall, strengthens the audit
trail, and makes the future Decision Graph, CRM, analytics, and APIs
buildable without rewriting the foundation. All fifteen review points are
incorporated below.*

**GOAL.** An immutable `DecisionRecord`, an append-only `DecisionEvent`
store, and a `DecisionService` as the only coordinator. Current status,
owner, relationships, and lifecycle are **computed by folding events** —
never mutated in place. Identity is dual: an opaque internal `id` plus a
human-readable `decision_key`.

**Schema (v1) — immutable base + append-only events (points 1, 3, 6, 7):**

```
DecisionRecord            written once, never mutated
  id                    ULID  (sortable, collision-safe, distributed-safe)
  decision_key          DEC-YYYY-NNNNNN  (human-facing: display + search only)
  created_at, created_by(actor)
  initial_owner, initial_status
  supersedes            nullable id
  record_schema_version
  metadata              non-sensitive analytical metadata only

DecisionEvent             append-only — the source of truth for ALL state
  event_id              ULID
  decision_id           FK -> DecisionRecord.id
  event_type            DecisionCreated | OwnerAssigned | OwnerTransferred |
                        RecommendationIssued | DecisionApproved | DecisionDeclined |
                        ExecutionStarted | ExecutionPaused | DecisionCancelled |
                        DecisionResolved | DecisionCalibrated | DecisionSuperseded |
                        AssumptionChanged | RedactionRequested | AccessRestricted |
                        Anonymized | Tombstoned
  occurred_at
  actor_type            human | agent | system                    (point 8)
  actor_id              founder | business_analyst_agent | nightly_runner | ...
  source                web_intake | cli | report_review | crm | api
  idempotency_key                                                 (point 9)
  payload               typed per event_type; NO raw sensitive content (point 10)
  event_schema_version

decision_entities         append-only — a decision may concern MANY entities (point 5)
  decision_id, entity_id, relationship_type
                        subject | competitor | partner | acquirer | market | benchmark

decision_relationships    append-only typed edges — the Decision Graph foundation (point 6)
  from_decision_id, to_decision_id, relationship_type
                        supersedes | superseded_by | depends_on | blocks | contradicts |
                        implements | caused_by | follow_up_to | alternative_to |
                        same_initiative_as
```

**Three folded state dimensions — never one collapsed status (point 2):**

```
decision_status:   draft | under_review | approved | declined | cancelled | superseded
execution_status:  not_started | executing | paused | completed | abandoned
evaluation_status: unresolved | partially_resolved | resolved | calibrated
```

`get_current_state()` folds the event stream into these three independent
axes, so "approved but not executing" or "resolved but not calibrated" are
representable and awkward combinations are impossible by construction.

**Identity (point 3).** Internal `id` = ULID via a **stdlib-only
implementation** (time + `os.urandom`; ~15 lines) — no new dependency (A3);
sortable and safe for independent/concurrent allocation by distributed
agents. `decision_key` (`DEC-YYYY-NNNNNN`) is human-facing only; it never
carries referential load, so a yearly counter needs no cross-agent
coordination and sequence collisions cannot corrupt storage.

**Ownership is folded, not stored (point 7).** Current owner derives from
`OwnerAssigned` / `OwnerTransferred` events. v1 implements
`accountable_owner` only, but the vocabulary (`decision_owner`,
`accountable_owner`, `execution_owner`, `reviewer`) is in the contract so
adding roles later is additive, not a migration.

**The DecisionService is the only coordinator (point 12).** The prediction
ledger stays a *reference*, never a god object:

```
DecisionService
  create_decision(intake, idempotency_key)  -> DecisionRecord      (idempotent)
  attach_prediction(decision_id, prediction)-> one-way link
  record_decision_event(event)              -> append
  supersede_decision(old_id, new_id)
  get_decision(id|key) · get_decision_events(id)
  get_current_state(id) · get_related_decisions(id)
```

`prediction_ledger.py` gains only a **nullable `decision_id` reference
column** (additive, matching its existing 5-nullable-field pattern). It
never allocates decisions, infers status, or writes records. Integration is
strictly one-way: **the Decision Record owns identity; the ledger
references it.**

**Schema versioning from day one (point 4).** Every record and event
carries its schema version. v1 readers **reject unsupported future major
versions**; minor additive fields stay backward-compatible; migrations are
deterministic and tested. The most foundational stored data must never need
a retroactive migration.

**Transaction boundary & recovery (point 13).** The premortem flow is
ordered and each step appends an event; a later failure never erases
earlier facts:

```
intake_received -> DecisionCreated -> analysis_completed
   -> prediction rows appended -> report_generated -> ReportGenerated
(a failed render appends a Failure event and stays recoverable — the
 decision and predictions are not rolled back)
```

**Privacy/retention — mechanism defined now, enforcement later (point 10).**
Sensitive customer content is never embedded raw across events; payloads
separate immutable analytical metadata from PII / confidential content. The
redaction / access-restriction / anonymize / tombstone event types exist so
the mechanism is designed; the event history survives while sensitive
payloads can be encrypted, restricted, or tombstoned by policy.

**The eight-point Definition of Done.**
1. *Belongs* — the backbone every consumer keys to (report, ledger, CRM,
   events, APIs, Personal AI).
2. *Existing insufficient* — ledger/entity keys identify predictions and
   entities, not decisions; one decision spans many of both.
3. *Files* — new `core/decision_record.py` (record + event store +
   `DecisionService`), new `core/decision_ids.py` (stdlib ULID + key
   allocator), additive nullable `decision_id` column in
   `prediction_ledger.py`, intake wiring in `simulator/cli.py` /
   `pipeline.py`, `tests/test_decision_record.py` + migration tests.
4. *Why those places* — core, domain-agnostic append-only state beside
   `prediction_ledger.py` / `entity_memory.py`; the ledger link is a FK, so
   a column, not a parallel table.
5. *Integration* — `premortem_prediction_bridge.py` stamps the
   `decision_id` one-way; the report (Slice 2A) reads the record; the
   DecisionEvent store later becomes **one producer** of the Company-OS
   event bus (P13) — it is not that bus.
6. *Agent inheritance* — a kernel shared-service; agents touch decisions
   only through `DecisionService`, never re-implementing identity.
7. *Complexity* — one identity replaces four implicit joins; folding
   replaces mutable-field bookkeeping.
8. *Drift* — `decision_id` is metadata, not a prompt (the frozen
   combined-call prompt and enum are untouched, A3); append-only; IDs are
   stdlib-only (no new dep, A3); one commit, suite green + `EXIT=0`.

**BARS (verifiable done-conditions).**
(a) **fold** — create → append a hand-built event sequence → `get_current_state`
returns the correct three-dimensional state; (b) **idempotency (point 9)** —
reprocessing the same accepted intake with the same `idempotency_key`
returns the existing record and creates **zero** duplicate ledger rows;
(c) a premortem run stamps **one** `decision_id` across its ledger rows and
its report, verified by direct read; (d) **dual ID** — `id` opaque/unique,
`decision_key` well-formed and immutable; (e) typed relationships +
`decision_entities` round-trip; (f) **version guard** — a record with an
unsupported future *major* version is rejected, a *minor* additive field
loads; (g) full suite green, zero regressions, prompts/enum untouched.
**Budget: 0 live model calls** (pure code + mocked).

**Slice 1 non-goals — does NOT build (point 15):** dashboards, CRM, public
APIs, content generation, the full Company-OS event bus, Personal AI,
decision-graph *traversal/queries*, customer-facing lifecycle UI, automatic
knowledge promotion. Slice 1 creates **only** the identity + storage
primitive those systems will consume.

---

## The gate, and the revised sequence

**Documentation is corrected before any code (review point 14)** — so
implementation never runs against outdated docs. This pass lands that
batch:

1. **Land the Decision Intelligence architecture** with the event-sourced
   Decision Record model → `docs/DECISION_INTELLIGENCE_ARCHITECTURE.md`
   (done this pass; fixes the self-referential drift, finding #3).
2. **Docs index + one-source-of-truth table** → `docs/README.md` (done
   this pass).
3. **Dangling reference (finding #4)** — `market-engine-execution-plan.md`
   was **not found in git history from the sandbox** (possibly the known
   git-lock state). Resolution: repoint `AGENTS.md` / `PORTFOLIO.md` to the
   surviving record, `reports/market_engine_trace.md`; verify on the Mac
   before deleting either reference. Recorded in the docs index.
4. **Scope boundary** between `COMPANY_OS.md` (company scope) and
   `DECISION_INTELLIGENCE_ARCHITECTURE.md` (engineering/decision scope) —
   one header line in each (done this pass).

**Then implement Slice 1, in this order (review's ten steps):** (1) ID
allocator (stdlib ULID + `decision_key`) → (2) `DecisionRecord` store →
(3) `DecisionEvent` store + fold → (4) `prediction_ledger.decision_id`
reference → (5) intake integration → (6) retrieval service
(`DecisionService`) → (7) migration + compatibility tests → (8) idempotency
tests → (9) end-to-end **mocked** premortem test → (10) one clean commit,
full offline suite green + `EXIT=0`. **0 live model calls.**

**After Slice 1:**
- **Slice 2A — record → report wiring:** Decision ID/key header, folded
  status badge, current owner, `supersedes` link, report metadata,
  component versions.
- **Slice 2B — approved report polish:** 3-axis Evidence Confidence
  (resolves finding #7), Alternatives Considered, 9-stage lifecycle
  presentation, PDF polish.
- **Slice 3 — lock the DI architecture** (mostly landed as docs this pass;
  any remaining developer-doc/API stubs).
- **Slice 4 — the broader Company-OS event bus** (the DecisionEvent store
  becomes its first producer), then the CRM / analytics / feedback /
  knowledge consumers.

**The steward rule that governs every accepted change:** optimize for
coherence, not novelty. Each change must leave the repository easier to
understand, extend, and operate five years from now than it is today — or
it does not ship.

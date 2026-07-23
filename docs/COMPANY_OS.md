# Company Operating System — the top-level architecture

*Written 2026-07-20. This is the organizing document that sits **above**
engineering (`docs/DECISION_INTELLIGENCE_ARCHITECTURE.md`), marketing
(`marketing/MARKETING_PLAN_V2.md`), autonomy
(`overnight-execution-plan.md`), and the agent registry
(`docs/AGENTS.md`). It renames nothing, moves no files, and rewrites no
code. It gives every existing system and every future agent a defined
place, so the next capability is an **application on one operating system**
rather than a separate AI project.*

*Scope boundary: this file is the **company** map;
`docs/DECISION_INTELLIGENCE_ARCHITECTURE.md` is the **engineering /
decision** map. Both use the internal "Decision Operating System" lens.
Where they meet, the engineering map owns the **decision primitive** (the
Decision Record); this file owns **how the company's systems consume it**.*

*This is a **review artifact**. Per the founder instruction, nothing here
is implemented until it is reviewed and accepted. Part 14 is the phased
execution plan; everything before it is design.*

---

## How to read this (and what is a source of truth)

This document is a **map, not a territory**. Where a real source of truth
already exists, this file points at it and never restates it:

| Source of truth | Owns | Status |
|---|---|---|
| `ROADMAP.md` | the RUNNABLE task queue | unchanged |
| `PLAN_2026-07-21.md` | the near-term execution queue | unchanged |
| `overnight-execution-plan.md` (Part A) | the autonomy protocol | **promoted** to the AgentOS kernel (Part 2), not rewritten |
| `docs/AGENTS.md` | the agent registry | **extended** (Part 2), not replaced |
| `docs/TOOLS.md` | the NOW/LATER/NEVER tooling ledger | unchanged |
| `marketing/MARKETING_PLAN_V2.md` | the marketing strategy of record | **extended** (Part 8), not replaced |
| `docs/DECISION_INTELLIGENCE_ARCHITECTURE.md` | the engineering/decision map | referenced |
| `docs/POSITIONING.md`, `docs/CAPABILITY_BOUNDARIES.md` | the honest claim surface | referenced |
| `PROGRESS.md` | history + the design-principle fix library | referenced |

If this document and a source of truth ever disagree, **the source of
truth wins** and this file is the thing that gets corrected.

### Deliverables index (the 15 requested pieces → where they live here)

1. Company OS architecture → **Part 1**
2. AgentOS architecture → **Part 2**
3. Complete agent hierarchy → **Part 2C**
4. Event architecture → **Part 3**
5. Repository restructuring → **Part 4**
6. Documentation restructuring → **Part 5**
7. Automation roadmap → **Part 6**
8. Knowledge architecture → **Part 7**
9. Marketing integration → **Part 8**
10. Personal AI integration → **Part 9**
11. Growth architecture → **Part 10**
12. Analytics architecture → **Part 11**
13. CRM architecture → **Part 12**
14. Product management architecture → **Part 13**
15. Execution roadmap with phases → **Part 14**

---

## Part 0 — The constitution (the rule that keeps this coherent at scale)

Everything in this document is subordinate to one principle, because it is
the principle that separates an ecosystem from a mess:

> **Before creating any folder, document, agent, or subsystem, check
> whether the capability already exists. Prefer extending and integrating
> existing systems over creating parallel ones. The repository must get
> progressively simpler as it grows, not more fragmented.**

This is not new to the project — it is already how the repo behaves. The
`entity_id`-normalization park in `docs/PORTFOLIO.md` is flagged precisely
because `prediction_ledger.py` not sharing `entity_memory.py`'s
normalization is "the same fragmentation risk that convention exists to
prevent." `PORTFOLIO.md` itself "records status — it does not reorganize,
rename, or restructure anything." This document inherits that restraint.

**Every proposal below was required to answer these six questions** (the
founder's quality standard). Proposals that could not are marked
NEEDS-SPEC and excluded, exactly as `ROADMAP.md` does:

1. Why is this necessary?
2. Why is this better than what exists?
3. What existing problem does it solve?
4. How does it integrate with the current architecture?
5. Does it create unnecessary complexity?
6. Would it still make sense if the company were 100× larger?

### The preservation ledger (walls this document may never relax)

These are load-bearing. They are restated here only so that "integrate
naturally" can never be misread as "quietly loosen." Each cites its owner.

- **The two walls** (`MARKETING_PLAN_V2.md`, `AGENTS.md §3`): *automate
  generation; gate publication and claims.* Nothing posts/sends without
  per-item founder approval + `PUBLISHING_ENABLED`; no predictive-accuracy
  claim before **≥30 live-resolved predictions per source AND the founder
  calibration review** (A-M5).
- **Append-only everywhere** (`prediction_ledger.py`, entity memory,
  outreach/CRM ledgers): ledgers gain rows, never mutate. Misses are never
  deleted (`POSITIONING.md`).
- **Deterministic bars over LLM self-assessment** (`overnight-execution-plan.md`
  A2): a bar is run, not judged.
- **Park, don't improvise** (A1/A4): unresolved ambiguity is parked with a
  TRACE entry, never resolved by guesswork.
- **One commit per task; offline suite green + `EXIT=0` before every
  commit** (A7; the pre-commit hook, `scripts/precommit_guard.sh`).
- **Frozen generation surface**: `PremortemAnalyzer`'s combined-call
  prompt, the `TriggerCondition` enum, and the mechanism library are not
  edited by marketing/agent work (A3, `MARKETING_PLAN_V2.md`).
- **A-M3** — no LLM historical backtesting as a decision signal (permanent
  overfitting guard). **A-M5** — no weight tuning against the 18 backtest
  cases.
- **No new external dependencies, no agent-created vendor accounts/OAuth,
  no sentiment feeds as signals, no autonomous financial action, no swarm
  orchestration inside the engines** (`TOOLS.md` NEVER; A3).
- **Compose-scope OAuth only; real sends/submissions run on the Mac with
  per-item approval** (`AGENTS.md §2`).

If a new capability cannot route through these walls, it does not ship.
This is the same sentence `MARKETING_PLAN_V2.md` already uses.

---

## Part 1 — The Company Operating System

### The shift this names

The project has already changed what it optimizes for. It was: *build an
excellent business-analysis engine.* It now is: *build an excellent
company around that engine.* Engineering, research, marketing, growth,
customer success, analytics, and operations become **first-class
systems**, not side effects of the engine.

### The operating-system lens

`docs/DECISION_INTELLIGENCE_ARCHITECTURE.md` already reads the product
internally as a **Decision Operating System** — memory, state, scheduling,
applications, permissions, lifecycle, events, shared services. The Company
OS is the same lens widened from *one decision* to *the whole company*.
The value of the lens is that it is not aspirational: every OS primitive
already maps to something in the repo.

| OS primitive | Company-scope meaning | Where it already lives |
|---|---|---|
| Memory | everything the company knows, addressable | `entity_memory.py`, `entity_graph.py`, `prediction_ledger.py`, `PROGRESS.md`; unified in Part 7 |
| State | where each unit of work is in its life | ledger rows, CRM states, ROADMAP status, the Decision Lifecycle |
| Scheduling | what comes due, and when | `nightly_agent.sh` (launchd), the 18:30 cron, daily/weekly/monthly BA cadence |
| Applications | what a user actually runs | Pre-Mortem Machine (`simulator/`), Cognitive Delegate (`voice/`), the scrap/fitness/music domain apps in `core/` |
| Permissions | what may run, ship, or be claimed | `permissions.py` (deny-by-default), the two walls, `TOOLS.md` gates |
| Lifecycle | the defined path work travels | the Decision Lifecycle; the ROADMAP task lifecycle (A2) |
| Events | what happens after an action | the ledger→content fan-out, `premortem_prediction_bridge.py`; formalized in Part 3 |
| Shared services | what every application calls | the ledger, mechanism library, permissions, render/report layer, LLM client |

### The systems catalogue

The company is **18 systems**. Each carries the same nine-field contract
the founder asked for. Crucially, the "Owner" is an agent from Part 2 and
the "Home" is an existing path wherever one exists — *new* is the
exception, not the rule.

The contract for every system: **purpose · owner · inputs · outputs ·
events · automation · metrics · dependencies · approval gates.**

| # | System | Owner (agent) | Home today | New? |
|---|---|---|---|---|
| 1 | Engineering (the Intent Engine) | Intent/Market-Engine Agent | `src/intent_engine/` | exists |
| 2 | Research (mechanisms, macro, history) | Research role of BA Agent | `mechanism_library.py`, `regime_engine.py`, historical-study track | exists |
| 3 | Content | Marketing Agent | `marketing/content_engine/render.py` | exists (C1 built) |
| 4 | SEO | Marketing Agent | `MARKETING_PLAN_V2.md §8`, C7 | specced |
| 5 | Growth | Marketing Agent | Part 10; funnel in `MARKETING_PLAN_V2.md` | partly specced |
| 6 | Sales / CRM | Marketing Agent | `marketing/crm/` (C5), `outreach/tracking_ledger_schema.md` | specced |
| 7 | Outreach | Marketing Agent | `marketing/outreach/` | exists (drafts) |
| 8 | Analytics | BA Agent + PostHog | Part 11; PostHog (NOW), calibration checkpoints | partly exists |
| 9 | Feedback | Marketing Agent | `marketing/feedback/` (C4) | specced |
| 10 | Product Management | **PM Agent (new role)** | `ROADMAP.md` steward; Part 13 | new role |
| 11 | Community | Marketing Agent | — | future (Part 8) |
| 12 | Documentation | Documentation role (any agent, Task-7 pattern) | `docs/`, `PROGRESS.md` close-out | exists |
| 13 | Release | inherited by every agent | one-commit-per-task, pre-commit guard, `nightly_agent.sh` | exists |
| 14 | Customer Success | Marketing/CRM Agent | report delivery + feedback + follow-up | partly specced |
| 15 | Knowledge Base | PM Agent (steward) | Part 7; `PROGRESS.md`, `diagnosis_registry.py` | consolidation |
| 16 | Automation | inherited kernel service | `nightly_agent.sh`, cron, Part 6 | exists |
| 17 | Experimentation | Growth + BA Agents | Part 10; A/B + the synthetic-worlds eval discipline | partly exists |
| 18 | Reporting / Operations | every agent (morning contract) | TRACE files, `reports/`, `MORNING_HANDOFF.md` | exists |

The full nine-field expansion for each system is given inline in the Part
that owns it (marketing systems in Part 8, growth in Part 10, analytics in
Part 11, CRM in Part 12, PM/knowledge in Parts 13/7). This table is the
index; the Parts are the detail. **No system in this catalogue is a new
parallel store** — every one either exists or extends a specced item.

---

## Part 2 — AgentOS (the shared foundation every agent inherits)

The goal the founder set: *do not begin by building individual agents;
build the shared foundation they all inherit, so a new agent later
requires very little duplicated work.* That foundation is **not new** — it
is `overnight-execution-plan.md` Part A (the Global Autonomy Protocol)
plus `docs/AGENTS.md` (the registry). AgentOS is the act of naming those
two as a reusable kernel and generalizing them from `intent-engine` to
every repo.

**Status update (T022, BUILT 2026-07-21).** The kernel below is no longer
only the autonomy protocol plus the registry — it is now also a concrete
code package, `src/intent_engine/agentos/`, **extracted from three
production agents** (Research T019, Product T020, Executive T021) rather
than designed ahead of them. It owns the append-only store discipline
(one `AppendOnlyStore` the three agent stores subclass), the language
wall, the model boundary (provenance + the recursive forbidden-field
scan), the Store/Index/Consumer/Snapshot/Replayable protocols, the agent
registry, the permission vocabulary, and read-only telemetry/budgeting. It
owns **no domain intelligence** — scoring, readiness, conflicts, debt,
portfolios, graphs, and the Decision Context all stay in their agents, and
a test enforces that none entered the kernel. The extraction removed
~250 lines of triplicated infrastructure with **zero behavioural change**
(the full suite passed byte-for-byte identical, 1421 → 1448, the +27 being
kernel tests only). The audit trail is
`docs/AGENTOS_EXTRACTION_REPORT.md`; the canonical contract surface is
`src/intent_engine/agentos/__init__.py`. The governing rule was
**extraction, not invention**: three implementations before one
abstraction, and nothing anticipated for a fourth agent that does not yet
exist.

### 2A. The kernel (the twelve shared services)

Every agent inherits these. Each is a real mechanism today, not a
promise. This is the "every future agent automatically receives…" list,
grounded:

| Shared service | What the agent inherits | Backing mechanism (today) |
|---|---|---|
| Shared memory | read/write to company memory, addressable | `entity_memory.py`, `entity_graph.py`, `prediction_ledger.py` (Part 7) |
| Shared event system | emit/consume events without knowing consumers | ledger→content fan-out, `premortem_prediction_bridge.py` (Part 3) |
| Shared planning | one task grammar with a definition-of-done | `ROADMAP.md` / `PLAN` house style; `scripts/pick_next_task.py` |
| Shared documentation | one doc template + the docs index | `docs/`, the Task-7 close-out pattern (Part 5) |
| Shared testing | deterministic bars, suite-green gate | pytest bars, `precommit_guard.sh` (A7) |
| Shared analytics | one event stream, one store | PostHog + calibration checkpoints (Part 11) |
| Shared approval workflows | the two walls + permission checks | `permissions.py`, `publer_pipeline.py`, approval-checklist |
| Shared logging | the morning-contract TRACE | `reports/overnight_trace.md`, `market_engine_trace.md` (A6) |
| Shared versioning | one-commit-per-task + component versions | git discipline (A7); the Decision-record version stamp |
| Shared safety rules | the preservation ledger (Part 0) | A3 hard walls; `TOOLS.md` NOW/LATER/NEVER |
| Shared company philosophy | the honest-claim posture | `POSITIONING.md`; "Claims wait. Marketing does not." |
| Shared reasoning standards | the fix library + park-don't-improvise | `diagnosis_registry.py`; `PROGRESS.md` design principles |

**Why this earns its place (the six questions).** *Necessary* because
each new agent otherwise re-implements memory, gating, logging, and
testing — the exact duplication the constitution forbids. *Better* because
the kernel already exists and is battle-tested (694 passing tests, a live
ledger, a nightly loop). *Solves* the "16 agents become 16 disconnected
projects" risk. *Integrates* by promotion, not rewrite. *Complexity*: it
removes complexity — one kernel replaces N copies. *At 100×*: an operating
system with a small, stable kernel and many applications is exactly the
shape that scales; a pile of scripts is not.

### 2B. The agent contract

An agent is **a configuration over the kernel**, not new plumbing. Every
agent — the four that exist and every future one — is defined by the same
schema `docs/AGENTS.md` already uses, extended with the event and metric
fields this document adds:

```
Agent:
  id, purpose, repo/home
  may_touch            (scoped write surface)
  hard_walls           (inherited from Part 0 + agent-specific)
  inherits             (the AgentOS kernel — always)
  authorized_tools     (per-agent .claude/skills/, superpowers global — TOOLS.md)
  inputs               (what it reads)
  outputs              (what it produces — always drafts behind the walls)
  events_consumed      (Part 3)
  events_emitted       (Part 3)
  metrics              (how its success is measured, each with a WHY)
  owner                (the founder, until delegated)
```

Creating a new agent = writing one of these records + provisioning its
scoped skills. No new memory store, no new logger, no new approval path —
those are inherited. This is what makes "very little duplicated work"
true.

### 2C. The agent hierarchy (the 16 requested agents, mapped)

The founder listed 16 agents plus the Personal AI. The anti-fragmentation
reading: **most are roles of the four standing agents, not new
processes.** Spawning 16 OS processes would be the fragmentation the
constitution forbids. The mapping:

| Requested agent | Status | Home / owning standing agent |
|---|---|---|
| Research | **role** | BA Agent (`AGENTS.md §4`) + mechanism/historical track |
| Business Analyst | **exists** | BA Agent (`AGENTS.md §4`) |
| Content | **exists** | Marketing Agent · `content_engine/render.py` |
| SEO | **role** | Marketing Agent · `claude-seo` (gated, TOOLS.md) |
| Growth | **role** | Marketing Agent · Part 10 |
| CRM | **role** | Marketing Agent · `marketing/crm/` (C5) |
| Outreach | **role** | Marketing Agent · `marketing/outreach/` |
| Analytics | **role** | BA Agent · PostHog · Part 11 |
| Feedback | **role** | Marketing Agent · `marketing/feedback/` (C4) |
| Product Manager | **new role** | PM Agent — roadmap steward (Part 13) |
| Marketing | **exists** | Marketing Agent (`AGENTS.md §3`) |
| Community | **future** | Marketing Agent · gated (no publishing path yet) |
| Documentation | **role** | any agent · Task-7 close-out pattern (Part 5) |
| Release | **inherited** | every agent · one-commit + guard + nightly loop |
| Customer Success | **role** | Marketing/CRM Agent · delivery + feedback + follow-up |
| Knowledge Base | **steward role** | PM Agent · Part 7 |
| Automation | **inherited** | kernel service · `nightly_agent.sh` + cron (Part 6) |

Net new *processes*: **one** (the PM Agent, and even that is a read/
propose-only steward, like the BA Agent). Everything else is a role or an
inherited service. That is the point — the hierarchy is deep in
capability and shallow in moving parts.

---

## Part 3 — Event architecture

The founder asked for an event-driven design and gave the canonical flow.
`MARKETING_PLAN_V2.md §2` already commits to it ("Marketing is
event-driven, not calendar-driven") and the `premortem → ledger` bridge is
a working event edge today. This Part formalizes the catalogue.

### The event catalogue

Each event is append-only, carries a stable key, and fans out to **drafts
only** — the two walls remain the sole manual steps.

```
DecisionSubmitted        key: decision_id      emit: simulator/CLI intake
   → AnalysisGenerated   key: decision_id      emit: PremortemAnalyzer
   → PredictionLogged    key: prediction_id    emit: prediction_ledger (append)
   → ReportGenerated     key: decision_id      emit: render_founder_report
   → CRMUpdated          key: prospect_id      emit: marketing/crm
   → ContentGenerated    key: decision_id      emit: content_engine/render
   → ApprovalQueued      key: draft_id         emit: approval queue   [WALL]
   → AnalyticsUpdated    key: event_id         emit: PostHog sink
   → FollowUpScheduled   key: prospect_id      emit: CRM lifecycle
   → FeedbackRequested   key: decision_id      emit: marketing/feedback
   → CaseStudyEligible   key: decision_id      emit: knowledge base (gated)
```

Every payload is keyed to one of four identities so a full history is
retrievable: **`decision_id`** (the Decision-record backbone from
`DECISION_INTELLIGENCE_ARCHITECTURE.md`), `prediction_id`, `prospect_id`,
`event_id`. `PublishApproved` and any accuracy claim are the only
transitions a human makes.

### How it is built (without a new dependency)

The event bus is **an append-only `events.jsonl` the nightly loop drains**
— the same discipline as every ledger here, and therefore **no new
external dependency** (A3). Producers append; consumers are pure functions
the loop calls; re-running is idempotent (the C3 definition-of-done
already requires this). *At 100×*, the log can be swapped for a real broker
without changing a single producer or consumer, because they only know the
event contract, not the transport. That is the whole reason to define the
contract now.

**Approval gates are events, not exceptions.** `ApprovalQueued` is a
first-class state; nothing downstream of it fires until a human emits
`PublishApproved`. This is how the event system and the two walls coexist:
the walls *are* two events only a human can emit.

**Status (2026-07-20): BUILT** as T013 — `src/intent_engine/events/`.
The canonical envelope contract and taxonomy live in ONE place,
`src/intent_engine/events/envelope.py` (this document describes the
architecture; the code file owns the contract; do not restate it
elsewhere). Implemented event names use dotted form
(`decision.created`, `content.approved`, `content.published`,
`claim.approved`, …); the flow above is realized by the DecisionEvent
bridge + the pipeline/report producers. The walls are structural:
approval/rejection/publication transitions require `actor_type=human`,
and `content.published` requires a prior human `content.approved` for
the same subject. Consumer status (2026-07-20): **CRM: BUILT** (T014,
`src/intent_engine/crm/` — canonical CRM contract in `crm/events.py`;
append-only `marketing/crm/crm.jsonl`; checkpointed idempotent consumer
of decision.* + report.generated with explicit-link-only identity;
versioned code-computed health/conversion signals; structural
no-sent-without-human-approval outreach wall). **Analytics: BUILT**
(T015, `src/intent_engine/analytics/` — canonical metric contract in
`analytics/models.py`; read-side only; versioned metrics; calibration
behind the A-M5 gate with brier_summary authoritative; consumer health
proven read-only). **Knowledge promotion: BUILT** (T016,
`src/intent_engine/knowledge/` — canonical contract in
`knowledge/records.py`; feedback → insight → knowledge kept separate;
human-only validation and promotion; citations mandatory; mechanism
proposals queue for review and never write the frozen library).
**Marketing automation C3–C8: BUILT** (T017,
`src/intent_engine/marketing/` — canonical contract in
`marketing/records.py`; campaigns, CRM-derived audiences, evidence that
preserves each source's status, versioned briefs and drafts, claim
review through THIS event system's gate, quotes through the T016 gate,
human-only approvals, observational publication recording, performance
observations, KnowledgeService-only feedback). **Growth & Experiment Intelligence: BUILT** (T018,
`src/intent_engine/growth/` — canonical contract in `growth/records.py`;
pre-registered experiments with human approval, deterministic
randomization, survivorship accounting, stdlib-only statistics that
render UNAVAILABLE rather than approximate, a label vocabulary with no
`winner`, and stopping rules that record facts rather than act).
**Research & Evidence Intelligence: BUILT** (T019,
`src/intent_engine/research/` — canonical contract in `research/records.py`;
six separated layers with the **Evidence Index** as the research-memory
substrate later agents read; pre-registered plans; source grading
independent of agreement; contradictions surfaced rather than smoothed;
propose-only). Product Manager Agent: **NOT BUILT** — next
(`ROADMAP.md` T020). External
publishing, autonomous publication, autonomous outreach, automatic
rollout and rollback: **NOT BUILT** and not planned without their own
founder gates.

---

## Part 4 — Repository restructuring proposal

**Finding first:** the honest move is to restructure *very little now.*
`PORTFOLIO.md` deliberately reorganized nothing; the repo's discipline is
to move files only when a real case forces it. Premature extraction is the
fragmentation risk in its other form.

**The real structure today:** two repos (`~/intent-engine`,
`~/job-application-agent`) plus a marketing workspace living inside
`intent-engine/marketing/`. `intent-engine/.env` is already the single
shared secrets store (`TOOLS.md`).

**Proposal (phased, additive):**

1. **Now (doc-only):** promote `overnight-execution-plan.md` Part A to a
   standalone `docs/AGENTOS.md` as the canonical kernel both repos cite.
   No code moves. This is the one restructuring with immediate payoff: the
   kernel stops being buried inside one repo's overnight plan.
2. **When a second repo needs to inherit code (not before):** extract the
   kernel's *interfaces* (memory, ledger, event, approval) into a small
   versioned package the repos depend on. Gated on a real second consumer —
   `job-application-agent` is the likely first, once it shares the ledger
   or event bus. Until then, the kernel is a **document** agents follow,
   not a library, exactly as `superpowers` is today.
3. **Never:** a monorepo merge or a swarm orchestrator (`TOOLS.md` NEVER).
   The single-agent, deterministic-bar model is a standing architectural
   decision.

*Six-question check:* extraction is *necessary* only when duplication is
real (two repos, one kernel); doing it earlier *adds* complexity for one
consumer. So the proposal is a document now, a package later — the repo
gets simpler, not more forked.

---

## Part 5 — Documentation restructuring proposal

**The real problem:** documentation is proliferating. There are 20+ files
in `docs/`, plus root-level `PROGRESS.md`, `ROADMAP.md`, `PLAN_*.md`,
`MORNING_HANDOFF.md`, `MORNING_REPORT.md`, `COWORK-HANDOFF-*.md`,
`intent-engine-context-3.md`, and `overnight-execution-plan.md`. Several
overlap (three handoff/context files; multiple proposals now DONE).

**Two moves, both additive:**

1. **One doc template.** Every subsystem doc answers the founder's seven
   questions: *why it exists · how it works · what depends on it · what
   events trigger it · what metrics define success · what automations
   exist · what future work remains.* This becomes the required shape for
   any new `docs/` file (and the section skeleton this document uses).
2. **One index (`docs/README.md`).** A single navigation map classifying
   every doc into five buckets, so nothing is discovered by `ls`:
   - **Sources of truth** — ROADMAP, PLAN, MARKETING_PLAN_V2, AGENTS,
     TOOLS, AGENTOS, COMPANY_OS.
   - **Architecture / maps** — DECISION_INTELLIGENCE_ARCHITECTURE,
     COMPANY_OS, POSITIONING, CAPABILITY_BOUNDARIES.
   - **Specs / proposals** — the TASK*/`*_PROPOSAL`/`*_SPEC` files, each
     tagged OPEN or DONE.
   - **Knowledge / history** — PROGRESS.md (Part 7).
   - **Reports / traces** — `reports/`, the morning-contract files.

**Consolidation (archive, never delete — A3):** DONE proposals move under
`docs/archive/`; the three handoff/context files collapse to **one living
handoff format** plus an archive. This is the "reduce duplication" the
founder asked for, done the repo's way (archive, don't rewrite history).

---

## Part 6 — Automation roadmap

**Today:** `nightly_agent.sh` (launchd, 1am, budget-capped) drains
RUNNABLE ROADMAP tasks; a cron fires daily market predictions at 18:30 ET;
the BA cadence runs daily resolve / weekly regime / monthly calibration;
the pre-commit hook enforces suite-green + `EXIT=0`.

**Target:** the **event bus (Part 3) is the automation spine.** Each
agent's cadence becomes a scheduled *drain* of the events it consumes.
Phases, each preserving every wall:

- **Phase 1 — one loop, one bus.** The nightly loop also drains
  `events.jsonl` and calls the existing fan-out (C3). No new scheduler.
- **Phase 2 — cadence per agent.** Analytics sink (Part 11), CRM
  follow-ups (Part 12), feedback requests (C4) run on their own cadence,
  triggered by events, not the calendar.
- **Phase 3 — the morning contract auto-assembles.** `MORNING_HANDOFF.md`
  is generated from the night's TRACE + ledger deltas (the `scripts/
  generate_morning_report.py` seed already exists).

Every automation output is a **draft or a display**, never a publish or a
claim. The prime rule (A1) holds: any situation no bar covers is parked,
not improvised.

---

## Part 7 — Knowledge architecture

The founder wants a permanent knowledge system accumulating: customer
feedback, feature requests, bugs, marketing insights, won/lost
experiments, sales objections, common questions, case studies,
architectural decisions, lessons learned.

**Finding:** most of this already exists, scattered. The
anti-fragmentation move is **one append-only knowledge base, many item
types — not many stores.**

| Knowledge type | Already lives in | Under the KB |
|---|---|---|
| Lessons learned (as code) | `diagnosis_registry.py` (failure signatures) | promoted, not replaced |
| Reusable causal knowledge | `mechanism_library.py` (cited) | the citation discipline is the KB's model |
| Design principles / history | `PROGRESS.md` (the fix library) | indexed |
| Customer feedback | `marketing/feedback/feedback.jsonl` (C4) | emits KB items |
| Sales objections / pipeline notes | `marketing/crm/` (C5) | emits KB items |
| Architectural decisions + rationale | **new** — Decision records | Part 9 (Personal AI) |

**The one abstraction:** an append-only `knowledge/knowledge.jsonl`, one
row per item, each row `{type, source, decision_id?, claim, citation,
created_at}` — the **same discipline as every ledger**, and every item
**carries its source** the way each mechanism carries a real citation. No
knowledge item is a bare assertion; that is what makes the base
trustworthy rather than a dumping ground.

**The promotion path** (the Decision Lifecycle's "Reusable Knowledge"
stage, now concrete): a validated lesson graduates from `knowledge.jsonl`
into code — a new `diagnosis_registry` signature or a new
`mechanism_library` entry — under its existing gates. Knowledge flows
*up* into reusable code; it does not sprawl sideways into new files.

---

## Part 8 — Marketing integration (extends MARKETING_PLAN_V2, replaces nothing)

`MARKETING_PLAN_V2.md` is the strategy of record and stays verbatim. This
Part only *places* its pieces on the Company OS and names owners/events —
it adds no strategy and relaxes no wall.

| V2 subsystem | Company system (Part 1) | Event edges (Part 3) | Status |
|---|---|---|---|
| Content Engine (§1) | Content | `AnalysisGenerated`→`ContentGenerated` | built (C1) |
| Event fan-out (§2) | Automation | `PredictionLogged`→ draft set | next (C3) |
| Productized report (§3) | Engineering/CS | `AnalysisGenerated`→`ReportGenerated` | built (C2) |
| Feedback (§4) | Feedback | `ReportGenerated`→`FeedbackRequested` | next (C4) |
| CRM (§5) | Sales/CRM | `ReportGenerated`→`CRMUpdated` | next (C5) |
| Commit content (§6) | Content | git commit→ draft | next (C6) |
| Distribution (§7) | Growth | weekly evergreen series | specced |
| SEO pages (§8) | SEO | ledger→ indexable page | next (C7) |
| Public roadmap (§9) | Documentation | `ROADMAP.md`→ page | next (C8) |

**Genuinely new (future, owned, gated):** Community and Referral/Lifecycle
automation. Both are Marketing-Agent roles, both blocked on the same
publishing-path wall (`PUBLISHING_ENABLED`) and per-item approval. They
enter the systems catalogue as future entries with owners — not as new
infrastructure.

Restated because it is load-bearing: **every marketing artifact is a draft
behind the approval + `PUBLISHING_ENABLED` walls, and no accuracy claim
exists anywhere until A-M5.** Marketing integration changes *where* a draft
comes from, never *whether* a human approves it.

---

## Part 9 — Personal AI integration (the orchestrator that learns the *why*)

**Status: BUILT as the Personal AI Workspace (T023).** Canonical contract:
`src/intent_engine/personal/records.py`. The first founder-facing product,
built on the AgentOS kernel — a **conductor, not an analyst**. It owns
conversation, memory, and orchestration, and **zero business
intelligence**: every fact comes from an existing agent, read through an
adapter the workspace owns, and every answer cites source ARTIFACTS (a
`SourceRef` with a replay id), not merely source agents. Disagreement and
freshness travel with every claim; the morning brief is assembled and
cited; explainability expands any conclusion into Finding → Evidence →
Confidence → Reasoning → Source Agent → Replay ID; a board update is a
draft and stays one. It may summarize, prioritize (by preserving an
owner's ordering), explain, organize, and draft — it may not publish,
email, execute, or modify business state. The chain that makes it
trustworthy is structural: *domain artifact → SourceRef → SourceClaim →
composition → optional model wording over a closed ClaimSet → deterministic
claim validation → cited answer* — not *question → model writes a plausible
answer → scan it*. The public onboarding experience (a CEO enters a company
name + website) is deliberately deferred to T023.5, which closes V1.0.

**Status update — the public experience is now PRODUCT BUILT (T023.5).**
`src/intent_engine/founder_intelligence/` is the first public-facing
product built directly on this workspace's provenance chain: a founder
enters a company name + website and receives an evidence-backed executive
experience in one trust-earning order — prove knowledge (Proof of
Understanding) → reveal perspective (market view, blind spots, assumptions,
attention, skepticism, questions) → invite investigation → converse
(structurally enforced; no perspective precedes understanding). It reuses
the T023 `SourceClaim`/`SourceRef` contract unchanged, computes **no**
business intelligence of its own, holds **no** action surface, invents no
competitor and no statistic, asserts no unsupported causality, and has no
company master score. SSRF/secret walls reject unsafe URLs and credentials
before storage; a wrong-company identity **stops** rather than merges; runs
are company-scoped for isolation. Presentation is a stdlib HTML renderer
(no web framework exists in the repo — the disciplined lightest option),
accessible (labels, semantic headings, status stated in text). A
deterministic synthetic demo runs end to end. **Separate facts** (see
`docs/T0235_PRODUCT_ACCEPTANCE.md`): PRODUCT BUILT — yes; CONTROLLED DEMO
READY — yes; DEPLOYMENT READY / PUBLICLY DEPLOYED / LAUNCHED — **no** (no
server, no auth, no live ingestion; gaps in
`docs/T0235_DEPENDENCY_GAPS.md`). This closes **V1.0 as a built product**,
not a deployed one, with T019–T023 source trees byte-untouched. The next
human-started milestone is V2.0 — Founder Growth Studio.

The long-term vision below is the *why* this workspace serves — it should
**understand why architectural decisions were made, not merely remember
files** — and T023 realizes the first hour of it.

**How this is made real, using systems that already exist:**

1. **Architectural decisions become Decision records.** Every consequential
   decision — the marketing redesign, the enum freeze, the A-M3 hold — is
   written as a record keyed by a `decision_id`
   (`DECISION_INTELLIGENCE_ARCHITECTURE.md`), carrying not just the choice
   but its **rationale**. The founder's own example becomes a stored
   record:

   > `DEC — marketing-timing`: *Waiting until November delayed audience
   > growth. Resolution: claims wait; marketing does not.* (rationale, not
   > instruction.)

2. **The rationale is the training signal.** The Personal AI's knowledge
   model is the Knowledge Base (Part 7) filtered to decision-records +
   `POSITIONING.md` + the `PROGRESS.md` design principles. It reasons from
   *why* past calls were made, so a new call is checked against precedent —
   the same way a mechanism match is checked against cited history.

3. **It orchestrates through the kernel, gated.** The Personal AI routes an
   intent to the right agent (Part 2) and inherits `permissions.py`
   (deny-by-default) and the two walls. The `voice/` pipeline is its
   embryo; the scrap/fitness/music apps in `core/` are its first personal
   applications. It proposes and coordinates; it does not bypass a single
   approval gate.

*Six-question check:* *necessary* to keep decisions consistent as agents
multiply; *better* than a memory of files because rationale generalizes and
file-recall does not; *integrates* by reusing the decision-record backbone
and the KB rather than inventing a "brain"; *at 100×*, an orchestrator that
reasons from a durable, cited decision history is the only version of this
that stays coherent.

---

## Part 10 — Growth architecture

Owner: Marketing Agent (Growth role) + BA Agent (experiments). Built on the
funnel `MARKETING_PLAN_V2.md` already defines: *Waitlist → Free report →
Feedback → Updated report → Invite → Case study → Referral.*

- **Funnel / activation / retention:** states on the CRM ledger (Part 12),
  not a new store. Activation = first report delivered; retention =
  returning for a second decision (both are `decision_id`/`prospect_id`
  events).
- **Referrals:** a CRM state (`advocate`) + a gated referral asset. Future,
  owned, walled.
- **Experiments / A-B:** every experiment is **pre-registered** (the
  synthetic-worlds eval discipline: a frozen setup before any run) and its
  result — won or lost — is a Knowledge Base item (Part 7). No experiment
  tunes a frozen prompt/enum (A3) or a claim before A-M5.
- **Lead scoring:** computed by code from CRM events, never hand-tallied
  (the C5 definition-of-done already requires code-computed metrics).

**Every growth metric is defined with a WHY in Part 11** — the founder's
rule that no metric is collected without a reason it matters is enforced
there, not duplicated here.

---

## Part 11 — Analytics architecture

Store: **PostHog** (NOW-tier, provisioned in `TOOLS.md`), fed from the
event bus (Part 3) — analytics is a *consumer* of `AnalyticsUpdated`, not a
parallel logger. Below, every metric carries the reason it matters,
because *"do not collect metrics without defining why they matter."*

| Metric | Why it matters (the decision it informs) |
|---|---|
| Landing-page conversion | is the *positioning* landing, before spend scales |
| Demo / report-completion | does the product deliver its value in one session |
| PDF downloads | is the productized report (C2) worth its build |
| Waitlist growth | is "marketing now" actually building audience (the V2 bet) |
| Meetings booked | is interest converting to real pipeline (CRM) |
| Feedback score (1–5) | is the report useful, per the people who read it (C4) |
| Return visitors | is the public-ledger "watch us earn it" story retaining |
| Referrals | is trust compounding into advocacy (the moat) |
| Email performance | is the one distribution channel we own working (listmonk) |
| Content performance | which analyses earn attention → what to render more of |
| Feature adoption | which engine capabilities get used → ROADMAP priority |

**The calibration exception.** Predictive-accuracy/calibration is the one
analytic that is **gated**: raw ledger rows and "too few resolved to claim
calibration" show now; a derived accuracy number appears only after A-M5.
Analytics never becomes a side door around the claim wall.

---

## Part 12 — CRM architecture

Owner: Marketing Agent (CRM role). Extends C5 exactly as specced:
`marketing/crm/` append-only `crm.jsonl` keyed by `prospect_id`, built on
`marketing/outreach/tracking_ledger_schema.md`.

- **Lifecycle:** `Prospect → Contacted → Interested → Report generated →
  Meeting → User → Referral → Advocate`; reads collapse to the latest row
  per id.
- **The approval wall is structural, not procedural:** no `status="sent"`
  row without a prior `approved` row and a non-null `approved_by` — the C5
  definition-of-done asserts this in code.
- **Linked to decisions:** when a prospect receives a report, the CRM row
  carries its `decision_id`, so a prospect's history and the Decision
  record resolve to the same backbone (Part 3).
- **Metrics by code:** contacted→interested→user rates, per variant and
  segment, computed, never stored. No scraped bulk lists — real research
  only (the unchanged v1 rule).

---

## Part 13 — Product management architecture

**Status: BUILT (T020).** Canonical contract:
`src/intent_engine/product/records.py`. A **read/propose-only steward**,
never a builder.

The subsystem that reads across every other subsystem and turns what they
collectively know into artifacts the founder can act on. It owns
**product proposals, not product decisions**.

**The five separated layers, never collapsed:**

```
Problem  ->  Opportunity  ->  Proposal  ->  Spec Draft  ->  Founder Review
                                        ->  Decision Record (by a human)
                                        ->  Execution Candidate
```

**The product memory.** Research got the Evidence Index; product gets the
**Problem Index and the Opportunity Index** (`product/index.py`). Both are
built only from append-only rows, are never written by a model, reject
orphans, enforce their own invariants, and answer lineage proposal →
opportunity → problem → evidence → source → request — with the last hops
delegated to T019 rather than rebuilt. They are two indexes rather than
one because a single problem routinely carries several competing
opportunities, and collapsing them destroys the fan-out the founder
chooses between. T021–T023 read this substrate instead of reconstructing
it.

**Problem-first, structurally.** Every artifact begins with a problem, its
evidence references, why now, and what changes if it is ignored — before
any solution exists. A problem with zero evidence references is rejected;
a statement phrased as its own solution is rejected; dedup is exact-match,
because near-duplicate merging silently folds two different problems into
one. Problems evolve: active, split, merged, retired, superseded.

**Deterministic scoring, never intuition.** Separate dimensions —
evidence, customer, experiment, and research coverage, strategic
alignment, freshness — each carrying its version, inputs, formula,
reasons, and status. A dimension with no recorded input is UNAVAILABLE,
never zero. A composite containing one is itself UNAVAILABLE with the gap
named. Strategic alignment comes only from a human declaration. Four
confidences (problem / opportunity / proposal / execution) are tracked
separately, and **cost of delay is computed apart** from the opportunity
score, because "how valuable" and "how expensive to postpone" are
different questions.

**Automatic intake** closes the loops the earlier sessions opened: T019
research debt, T018 INCONCLUSIVE / TOO FEW / GUARDRAIL BREACHED results,
and T014 churn / at-risk facts each become candidate opportunities that
cite their origin and inherit its uncertainty as a confidence cap.

**The portfolio** rolls up Portfolio → Strategic Themes → Initiatives →
Opportunities → Proposals → Specs in one deterministic call, and reports
balance against a human-declared band (withholding the verdict when none
is declared), decision debt, and an executive summary. Priority,
sequencing, blocking, and readiness are four separate questions.

**How it coordinates:** it consumes `growth.result_labelled` and
`decision.resolved` on checkpoint `product`, each creating at most one
candidate opportunity. It reads the CRM store directly for churn and
at-risk facts, which are CRM facts rather than company events.

**The ROADMAP wall.** The agent emits a roadmap *candidate* and a
*proposed diff*; a person applies it. `product/roadmap_diff.py` opens no
file at all — the caller passes the roadmap text in — so the wall is
structural rather than promised. A candidate is NEEDS-SPEC unless every
bar is checkable, and the agent can never mark one RUNNABLE.

**Metrics (each with a why):** roadmap RUNNABLE depth (is the loop ever
starved), NEEDS-SPEC age (are real items rotting), evidence-to-proposal
latency (does what customers show reach the plan), portfolio balance
against declared bands (is the work lopsided), decision debt (what is
waiting on a person).

*Six-question check:* *necessary* because 19 systems and a growing agent
set need a coordinator or they drift; *better* than the founder holding it
all in `MORNING_HANDOFF.md` by hand; *integrates* by reading existing
subsystems and consuming existing events; *complexity*: one propose-only
agent, one append-only store, zero duplicated logic; *at 100×*, a product
function that proposes from evidence and never decides is how a many-agent
company stays coherent.

---

## Part 15 — Executive decision architecture

**Status: BUILT (T021).** Canonical contract:
`src/intent_engine/executive/records.py`. A **read/recommend-only**
steward, and the first agent that reasons ACROSS the whole company rather
than owning a domain.

The subsystem that answers a triage question — *given everything we know,
what decision deserves the founder's attention next?* It owns **decision
candidates, not decisions**.

**The three-index layering this completes.** Each agent memory has the
same shape — folded from append-only rows, never model-written,
orphan-rejecting, self-checking, lineage-answering — which is what lets a
future kernel (T022) treat them as one standardized replayable read model:

```
Evidence Index      (T019)  what is known
Problem + Opportunity Index (T020)  what could be built
Decision Index      (T021)  what deserves a decision next
```

**The load-bearing design decision.** Decision state lives in
`DecisionService` (SQLite), a different store from the executive log.
Mirroring it in would query better and materialize a copy that drifts. So
the Decision Index stores `decision_id` REFERENCES and resolves through
`DecisionService` at read time — the same shape T020 uses for evidence
references — and stays reproducible from its own log. No executive module
writes `decisions.db`, creates a decision, or records a decision event.

**What it refuses to do quietly: average a disagreement.** Where Growth,
Research, Analytics, and CRM point different ways, the output is a typed
**Conflict Summary** (nine kinds, staleness distinct from timeline), not a
blended number — because the disagreement is the most useful thing in the
room.

**Six independent readiness dimensions, never one score** — evidence,
execution, strategic, financial, operational, and decision readiness. A
missing input is UNAVAILABLE, never 0. Financial readiness is structurally
UNAVAILABLE without a human declaration. Decision readiness is a YES/NO
with every gap named, not a confidence, because "no — the experiment has
not run and nobody owns it" is actionable and "0.62" is not.

**Decision packages** carry mandatory alternatives (option sets, each with
benefits / costs / risks / unknowns / dependencies / a declared
reversibility), an **escalation** decision (who should decide, separate
from what to recommend), an explicit **no-recommendation** outcome, and a
**founder override** that keeps both the chosen and the preferred option.
Impact is computed from scope; reversibility is Type 1 / Type 2, declared
not inferred.

**The primary artifact is a triage queue** — three partitions (strategic /
operational / maintenance) ordered by a fixed-precedence tuple, never a
blended score. Expiry follows a changed load-bearing input, never a clock.
Every recommendation traces to a terminal state, where rejected and
deferred are legitimate — a new standing invariant.

**How it coordinates:** it consumes `decision.resolved` on checkpoint
`executive`, each event creating at most one candidate; and it reads
accepted proposals from T020 directly. The health dashboard is the
substrate for the Personal AI daily briefing (Part 9 / T023).

*Six-question check:* *necessary* because a founder with ten agents
surfacing work needs one triage surface or drowns; *better* than a
priority list that averages incomparable decisions; *integrates* by
reading the three indexes and DecisionService; *complexity*: one
recommend-only agent, one append-only store, zero duplicated logic; *at
100×*, a decision function that triages from evidence, states every
disagreement, and never decides is how a founder stays the decider.

---

## Part 14 — Execution roadmap (phased; reviewed before built)

The detailed, dependency-ordered build sequence lives in
**`docs/V1_COMPLETION_ROADMAP.md`** — the architecture review plus the
fifteen priorities placed into phases, each with its Definition of Done.
It is to this document what `overnight-execution-plan.md` Part B is to
`ROADMAP.md`, and it is kept as the **single source of truth for the build
order** so this file does not duplicate it.

In one paragraph: the **Decision Record is the keystone** and is built
first (it is currently designed but absent from code); the report and the
engineering-architecture doc are then locked to consume it; then the event
bus and its consumers (CRM, analytics, knowledge, feedback); then the
company layer (PM agent, research, growth, governance); and last —
designed early, built only when a real second consumer exists — AgentOS
extraction, the Personal AI, and public APIs.

**The standing sequencing rule (unchanged):** a task enters a phase only
when it has bars; until then it is NEEDS-SPEC and the loop never picks it.
Nothing is built until the sequence in `V1_COMPLETION_ROADMAP.md` is
accepted.

---

## Preservation & integration audit (why this is safe to accept)

Every requested piece maps to **exists / extends / new**, and every wall
is intact:

- **Preserved, unrelaxed:** the two walls, append-only, deterministic bars,
  park-don't-improvise, one-commit + suite-green, frozen prompt/enum/
  library, A-M3, A-M5, no new deps, no agent OAuth/vendor accounts, no
  sentiment feeds, no autonomous financial action, no swarm, compose-scope
  OAuth, Publer-only publishing, per-agent skills. (Part 0.)
- **Extended, not replaced:** `AGENTS.md` (registry → contract),
  `overnight-execution-plan.md` Part A (protocol → kernel),
  `MARKETING_PLAN_V2.md` (strategy → placed on the OS), the ledger/CRM/
  feedback stores (→ event producers + KB emitters).
- **Genuinely new:** one read-only PM Agent; one append-only knowledge
  base; one append-only event log; one docs index + template; one
  promoted `docs/AGENTOS.md`. Five additions, each replacing duplication
  rather than adding it.
- **Fragmentation check:** no new memory store (memory unifies in Part 7),
  no new logger (TRACE stays), no new approval path (the walls stay), no
  file moves before a real case forces them (Part 4). The repo gets
  *simpler* — one kernel, one bus, one KB, one index — as it grows.
- **100× check:** small stable kernel, many applications, one event
  contract, one honest-claim posture. That is the shape that scales.

*No accuracy claim appears in this document; the only performance statement
remains the load-bearing disclaimer that none can be made until the ledger
earns it.*

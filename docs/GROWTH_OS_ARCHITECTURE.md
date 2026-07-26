# Growth Operating System — Architecture

**Date:** 2026-07-26
**Status:** foundation + first modules implemented tonight; remainder specified for dependency-ordered build.
**Scope discipline:** this document is Section-20 step 4. No V2/V3/V4 features; no unrelated core systems modified; integration points only.

---

## 0. What this is

A continuously-learning marketing intelligence platform built on the **same
philosophy and the same foundation as the trading engine**: everything is
event-sourced, carries provenance and confidence, is timestamped, is replayable,
is measurable, produces learning candidates, and stays human-gated where
required. No black-box optimization — every recommendation ships with evidence.

It is a set of **modular services**, each independently testable, that *reuse*
the existing platform rather than duplicate it.

---

## 1. Audit of the current marketing subsystem (Section-20 steps 1–2)

The platform already contains a mature, event-sourced, human-gated marketing/
growth stack. Measured tonight:

| Existing package | LOC | What it already is | Spec module it satisfies |
|---|---:|---|---|
| `intent_engine.marketing` (T017) | 2,068 | campaigns, audience selection, briefs, drafts, review packages, publish handoffs, performance observations; reuses claim gate, quote-consent gate, CRM, analytics honesty markers. "Drafting may be automated. Approval and publication may not." | §7 Content Creation, §11 Campaign Planner (artifacts), §12 Publishing (handoff), §2 Audience (selection) |
| `intent_engine.growth` (T018) | 2,045 | pre-registered experiments; no `winner` field, no auto-rollout, honest statistics, survivorship carried, synthetic/production never mixed | §14 Experiment Engine |
| `intent_engine.growth_studio` (V2.0) | 1,025 | bounded continuous planning loop orchestrating Marketing/Growth/analytics by reference; can neither publish nor send | §11 Campaign Planner, §18 Autonomous Loop |
| `intent_engine.crm` (T014) | 872 | contacts/relationships/lifecycle; human-only outreach wall | §10 CRM |
| `intent_engine.analytics` (T015) | 828 | read-only metrics; explicit `UNAVAILABLE` instead of misleading zeroes | §13 Analytics |

**Foundation already shared platform-wide (reused, never reimplemented):**

- `intent_engine.storage.durable.DurableStore` + the per-module append-only
  JSONL store pattern (flock + fsync-before-success + fingerprint idempotency +
  deterministic folds) — **event sourcing + replay**.
- `intent_engine.core.decision_ids` (`new_ulid`, `is_ulid`) — sortable ids.
- `intent_engine.events` (CompanyEventBus) — delivery + approval walls.
- `intent_engine.knowledge` / `intent_engine.learning` — the **Learning Ledger**
  and promotion gates (a human-accepted `LearningCandidate` → `AcceptedLearning`).
- `intent_engine.simulator.synthetic_worlds` — **Synthetic Worlds** for
  historical/counterfactual evaluation.
- `intent_engine.research` — company research (distinct from growth research).

### Gaps (measured: 0 files each) — the intelligence front-end

The autonomous loop's *head* — turning the world into evidence — is missing:

| Missing module | Spec § | Status |
|---|---|---|
| **Growth Research** | §1 | **built tonight** |
| **Brand Memory** | §6 | **built tonight** |
| Trend Intelligence | §3 | specified below |
| SEO Intelligence | §4 | partial (3 files) → specified |
| Content Intelligence | §5 | specified below |
| Media Generation (provider-abstracted) | §8 | specified below |
| Email Marketing (drip/segmentation/A-B) | §9 | partial in `marketing` → specified |

---

## 2. Comparison with proven open-source patterns (Section-20 step 3)

Patterns adopted (concepts, not code):

- **Event sourcing + CQRS** (write path appends immutable events; reads are
  deterministic folds) — as in EventStoreDB / Axon. Already the house style; the
  new modules follow it exactly.
- **Provenance/lineage records** (source URI, retrieval method, license, observed
  vs recorded time) — the OpenLineage / W3C PROV idea, reduced to a small typed
  `Provenance` value carried on every intelligence record.
- **Confidence as a first-class field with a stated basis** — like a feature
  store's quality flags; we refuse a silent default, mirroring analytics'
  `UNAVAILABLE`.
- **Segmentation + drip as state machines** (Mautic/Listmonk) for §9 Email.
- **Experiment registry with pre-registration** (GrowthBook/Statsig) — already
  embodied by `intent_engine.growth`; new modules feed it, never bypass it.
- **Provider abstraction for outbound side-effects** (publishing, media) — a
  narrow interface with swappable implementations, no hardcoded vendor (§8, §12).

Explicitly **not** adopted: anything that auto-optimizes or auto-publishes, or
that stores a metric without its source.

---

## 3. Foundation built tonight: `growth_os.foundation`

Every intelligence module shares one contract so provenance/confidence/timestamps/
replay/learning are structural, not per-module discipline:

- **`Provenance`** — `source` (kind), `uri`, `method` (how obtained: `api`,
  `rss`, `export`, `manual`, `synthetic`), `license`, `retrieved_at`. A record
  with no provenance cannot be constructed. **No scraping in violation of ToS**
  is expressible: `method` names the *permitted* access path.
- **`Confidence`** — `value` in [0,1] **plus** a `basis` string (why). A
  confidence with no basis is rejected — no black-box numbers.
- **`IntelRecord`** — the event envelope: `record_id` (ULID), `stream`,
  `event_type`, `actor` (`human|agent|system`), `observed_at`, `recorded_at`,
  `provenance`, `confidence`, `payload`, `idempotency_key`, `schema_version`.
  `content_fingerprint()` excludes the wall-clock `recorded_at` (the same
  idempotency lesson already fixed in `DurableStore`).
- **`IntelStore`** — append-only JSONL, flock + fsync + fingerprint idempotency +
  deterministic folds + full replay (`read_all`, `replay`). Mirrors the marketing/
  CRM/knowledge store discipline; generic over `IntelRecord`.
- **`LearningCandidate`** — `statement`, `evidence` (record ids), `confidence`,
  `success_metric`, `proposed_by`; `status` starts `proposed`. **Only a human
  transitions it** to `accepted`/`rejected`; nothing self-promotes. Bridges to
  the existing Learning Ledger.

Human-gating is enforced in each service by a `HUMAN_ONLY_EVENTS` set, exactly
as `marketing`/`crm` do.

---

## 4. Modules built tonight

### 4.1 Growth Research (§1) — `growth_os.research`
Turns raw signals from permitted sources into **understood intent**, not
keywords. Record types: `topic`, `pain_point`, `question`, `objection`,
`language` (terminology), `community`, `recurring_discussion`. Each carries the
research domain (AI, founders, SaaS, BI, forecasting, agents, dev-tools, …),
an **intent classification**, confidence-with-basis, and provenance. Evolution is
first-class: the same topic re-observed appends a new record, and
`topic_evolution()` folds the trajectory (rising/steady/fading) over time.
Recurring, well-evidenced, rising intent **emits a LearningCandidate** for a human
to accept into the ledger — the head of the autonomous loop. Human-gated:
promoting research into an approved campaign theme is human-only.

### 4.2 Brand Memory (§6) — `growth_os.brand`
The persistent, versioned brand model: `voice`, `tone`, `messaging`, `value`,
`positioning`, `claim`, `proof`, `case_study`, `customer_story`, `quote`,
`visual_style`. **Every brand fact is human-approved** before it is `active`
(agents may only `propose`). The load-bearing guarantee — *never contradict
previously approved messaging* — is enforced by `check_consistency(text)`, which
scans against active `messaging`/`positioning`/`claim` facts and their explicit
`contradicts` markers, returning conflicts with the offending record id. This is
the gate the content modules call before a draft can advance.

Both are independently testable, offline, deterministic.

---

## 5. Integration points (Section-17, only where required)

- **Learning Ledger:** research/brand emit `LearningCandidate`s in the shape the
  existing `knowledge`/`growth_studio` acceptance path already consumes; a human
  accepts them there. Growth OS never writes `AcceptedLearning` directly.
- **Event bus:** intelligence records can be projected as company events for
  delivery/approval, reusing `intent_engine.events` (no new bus).
- **Marketing:** Brand Memory's `check_consistency` is the gate
  `marketing.drafts`/`generators` call before a draft advances — the one wiring
  seam. Growth Research themes reference marketing campaigns by id.
- **Company graph / Synthetic Worlds:** research domains key to company entities;
  candidate evaluation can run through `simulator.synthetic_worlds` before live
  validation — same as trading.

No existing module's storage or write path is modified.

---

## 6. Design decisions & why

1. **Shared `foundation` for the new intelligence modules** rather than copying
   the store 6×: the five remaining front-end modules are all "observe the world
   → evidence" shaped, so one enforced envelope (provenance+confidence) prevents
   drift. The mature *workflow* modules (marketing/growth/crm) keep their own
   stores untouched.
2. **Confidence requires a basis; provenance requires a method.** Makes the
   "no black-box, no ToS violation" rules *unrepresentable-if-broken*, not just
   documented.
3. **Human-gating by event-type set**, identical to `marketing`/`crm`, so the
   autonomous loop can never self-promote or self-publish.
4. **Reuse the JSONL append-only pattern** (not a new DB) for parity with every
   sibling module and zero new infra.

---

## 7. Remaining work, in dependency order

1. ✅ `foundation` (records/store/provenance/confidence/learning) — **done**
2. ✅ Growth Research (§1) — **done**
3. ✅ Brand Memory (§6) — **done**
4. Trend Intelligence (§3) — `foundation` + permitted APIs/RSS adapters behind a
   `TrendSource` provider interface; per-trend structural analysis (why it
   spread / emotion / format / CTA), pattern-learning only, never copying.
5. Content Intelligence (§5) — study performance of *our own* published artifacts
   (reads `marketing` performance observations + `analytics`) → pattern candidates.
6. SEO Intelligence (§4) — extend the 3 existing files into clusters + semantic
   graph + article-opportunity candidates.
7. Media Generation (§8) — `MediaProvider` interface (storyboard/shotlist/VO/
   captions), one adapter; no hardcoded vendor.
8. Email Marketing (§9) — segmentation + drip state machines on `crm` + `foundation`.
9. Growth Dashboard (§13/§16) — read-only projection over all module stores.
10. Autonomous loop wiring (§18) in `growth_studio`, human-gated at Promote.

Each ships with tests + docs before the next begins.

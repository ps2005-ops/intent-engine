# Intent Engine v2: Entity Memory + Permission-Gated Actions

**Supersedes:** the original 26-week schedule's Week 5+ direction (on-device learning,
generic personal context ingestion) for the voice assistant / personal product track.
**Does not change:** Weeks 1-3 (business simulator) or Week 4 (voice foundation) as
already built — those become the foundation this architecture builds on top of.

---

## What changed, in one paragraph

The original spec treated "personal context" as data to ingest (calendar, email
patterns) so the assistant could classify intents and suggest actions. The revised
vision is bigger: the system should build an accumulating, structured, causally-
organized understanding of a specific person or company over time — not a snapshot,
a living model that gets more accurate the longer it runs — and reason over that
history the way a longtime chief-of-staff or cont would, surfacing patterns
the person hasn't consciously connected. Action-taking is explicitly permission-gated
per domain (Gmail: maybe, WhatsApp: maybe not), decided by the person, not assumed.

---

## Current state

**Stage A (entity memory) and Stage B (permission registry): built and verified.**

- `core/entity_memory.py` — `EntityMemoryRecord` (with `outcome` reserved, unused,
  for Stage D+), `normalize_entity_id`, `EntityMemoryWriter` (a `Protocol`,
  deliberately not a `Stage` — see the docstring for why), `JsonlEntityMemoryWriter`,
  `read_records`.
- `core/permissions.py` — `PermissionRegistry`, deny-by-default, constructor-config
  only (no persistence yet, nothing to gate yet).
- Wired into `simulator/cli.py`: `--entity-id` is a required flag; every `premortem`
  run writes an `EntityMemoryRecord` after `run_premortem()` returns, with a visible
  `Saved to entity memory: <normalized_entity_id>` confirmation.
- Verified, not just written: `normalize_entity_id` tested against real collision
  cases; a real live `premortem` CLI run confirmed end-to-end (flag → write →
  correct normalized content on disk, pasted verbatim during review); round-trip
  read/write test covering cross-entity isolation; 24/24 offline tests passing.
- Known gap, tracked: nothing calls `cli.main()` in the test suite — the CLI's
  argparse layer (including the `--entity-id` requirement and the write path) has
  no automated coverage, only the live manual run performed during review. See
  `PROGRESS.md` backlog note.

**Not yet built**: Stage C (real integrations), Stage D (hypothesis formation),
`PersonalContext`/`voice/` (in progress next — see amendment note in
`docs/weekly/week-04-plan.md`), any grants persistence for `PermissionRegistry`.

---

## The two-engine architecture

**Reasoning engine** — unrestricted. Can think about anything in accumulated entity
memory, propose actions in any domain, form and revise hypotheses about the entity
("this founder accelerates risk-taking under low-runway pressure") over time.

**Action engine** — permission-gated. Can only execute in domains explicitly
authorized by the person (a scope registry, similar to OAuth scopes: Gmail on,
files on, WhatsApp off, photos off). Every proposed action is checked against
current grants before execution, regardless of what the reasoning engine concluded.
If a domain isn't authorized, the system states what it *would* do, clearly labeled
as blocked, rather than either silently skipping it or doing it anyway.

This separation is what lets reasoning stay ambitious while on stays safe —
they are not the same gate.

---

## Where this sits relative to your existing timeline

- **Weeks 1-3 (business simulator):** unchanged, already built, already a working
  instance of "structured domain understanding + causal grounding + generative
  reasoning." This is proof the pattern works — it's the template.
- **Week 4 (voice foundation):** unchanged in its immediate build (VoiceIntent
  classification, mock PersonalContext, text-first testing) — but its role changes.
  It's no longer "the voice product," it's "the first data-writing surface that
  feeds entity memory."
- **Week 5 onward (was: on-device learning, generic context ingestion):**
  replaced with the entity-memory + permission-gated action architecture below.
  This is a genuinely bigger scope than the original Week 5-8 plan — expect it to
  span roughly Weeks 5-12, not 5-8, with real checkpoints, not a single sprint.

---

## Build sequence (incremental, each phase checkpointed before the next)

### Stage A — Pentity Memory (was: Week 5)
- A structured, append-only store (not a chat log) that every interaction writes
  to: decisions made, stated goals, observed outcomes, timestamps.
- Starts simple — plain structured records, not "hypotheses" yet. Get writing
  and retrieval working before adding any reasoning sophistication.
- Both the business simulator AND voice assistant write into this same store —
  this is the first real point where "shared Intent Engine" becomes true in
  practice, not just in naming.

### Stage B — Permission / Scope Registry (was: not in original spec)
- A first-class, explicit grant system per integration domain (Gmail, files,
  calendar, Notion, WhatsApp, photos...).
- Every action proposal is checked against this registry before execution.
- Build this BEFORE any real integration beyond mock data — it should exist as
  a gate from day one of Stage C, not retrofitted after integrations exist.

### Stage C — Real Integrations, Gated (was: Week 8's Gmail/Calendar/Notion ingesti integrations the original spec named, but now explicitly routed through
  the Stage B permission gate — reading is likely lower-risk than acting, worth
  distinguishing "read for memory" grants from "act on my behalf" grants as two
  separate permission tiers.

### Stage D — Hypothesis Formation (was: not in original spec)
- The system proposes structured hypotheses about the entity from accumulated
  memory ("pattern noticed: X tends to precede Y") — tested/revised as new
  evidence arrives, not fixed at creation.
- This is the layer that produces the "tells you the real reason" value —
  causal reasoning over the person's own accumulated history, clearly labeled
  as pattern-based and conditional, not predictive certainty.

### Stage E — Gated Action Generation (was: your n8n idea)
- Once a pattern is identified and the relevant domain is authorized, generate
  a concrete, inspectable action (e.g., an n8n workflow) — visible to the person,
  revocable, not silently running.
- Unauthorized domstem states what it would do, doesn't do it.

---

## Guardrails carried over from the rest of this build

- Multi-run latency testing before trusting any single measurement (this
  architecture adds real complexity — memory writes/reads, permission checks —
  worth re-establishing a latency budget explicitly at Stage A, not assuming
  Week 4's numbers still hold).
- New external dependencies (a real database for entity memory, any new vendor
  for integrations) get flagged for your sign-off before installing, same as
  every vendor decision so far.
- Don't let "predict 5 years out" become a literal target metric — it's
  direction-setting language, not a spec requirement. The buildable target is
  depth and accuracy of *pattern recognition over accumulated history*, framed
  conditionally, not long-horizon prediction as a claimed capability.

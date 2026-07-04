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

**`voice/` built and verified**: `PersonalContext` (a view computed from real
`entity_memory.read_records()`, not a standalone snapshot — see the amendment note
in `docs/weekly/week-04-plan.md`), `VoiceIntentClassifier` (own prompt/schema, Haiku,
measured well under the <3s voice latency target), `process_voice_interaction()`
(composes classification + entity-memory write, source="voice", every interaction
written with no filtering by salience). `EntityMemoryRecord.salience` added
(`Optional[Literal["low","medium","high"]]`, voice-only) as the signal Stage D will
query/weight by later. Salience calibration is an open, partially-characterized
question — real 10-run distributions showed `intent_type` perfectly stable but
`salience` varying on ambiguous utterances specifically, correlated with
`PersonalContext` injection; documented as a code comment in `voice/classifier.py`,
not resolved.

**Stage C started, Calendar only**: `voice/calendar.py` — `StubCalendarReader`/
`StubCalendarActor`, gated on `"calendar_read"`/`"calendar_act"`. Proves the
two-tier read/act permission distinction end-to-end (a read grant does not
authorize act, and vice versa — both directions tested). Stub only: no real
Google Calendar API, no OAuth, no new dependencies. **Domain-string convention
locked in** (see `core/permissions.py`'s docstring): every future integration uses
`"{integration}_read"`/`"{integration}_act"`, never a single shared domain string.

**Calendar stub wired into the real voice pipeline, end-to-end, verified**:
`voice/pipeline.py`'s `process_voice_interaction()` now routes `calendar_block`
`VoiceIntent`s through `PermissionRegistry` to `StubCalendarActor` directly —
not a second stub, the same pipeline every other intent goes through. Returns
`VoiceInteractionResult(voice_intent, calendar_action)`; `calendar_action` stays
`None` for every non-`calendar_block` intent. Order is fixed: entity-memory write
happens unconditionally, before the permission check — a denied action still
leaves a durable record that it was requested (verified: both the authorized and
denied scenarios below produced a persisted JSONL line). Verified with a real
live run (real Haiku classification call, real file writes, real
`PermissionRegistry`, no mocks) for both an authorized and a denied
`calendar_act` grant on the same utterance ("block off Thursday afternoon for
the board meeting") — both produced correct `CalendarActResult`s and both wrote
an `EntityMemoryRecord`. 46 offline tests passing (3 new pipeline-wiring tests
added, covering authorized, denied, and non-calendar-intent pass-through).

**Stage C, Gmail: both tiers stubbed, neither wired**: `voice/gmail.py` —
`StubGmailReader` (`"gmail_read"`) and `StubGmailActor.create_draft()`
(`"gmail_act"`), mirroring Calendar's shape. Not wired into the pipeline:
`gmail_read` has no natural `intent_type` trigger (unlike `calendar_block`);
`gmail_act`'s trigger (`email_draft`) looks obvious but isn't wired either,
because examining it alongside `gmail_read` surfaced the compound-action
question above — wiring `email_draft` to `create_draft()` as originally shaped
would silently mishandle the reply case. Notion integration not started.

**Not yet built**: the concrete Gmail compound-action implementation (schema
changes to distinguish fresh-compose vs. reply-to-existing, the actual
both-grants check), Notion integration, Stage D (hypothesis formation), any
grants persistence for `PermissionRegistry`, real OAuth for any integration.

**Action-domain wiring shape, locked in with Calendar and binding for every
future action domain** (Gmail, Notion, WhatsApp, etc. — same treatment as the
domain-string convention, decided once so it isn't reopened at Gmail):
1. **Unconditional entity-memory write happens before any gate check.** A
   denied or not-applicable action must never suppress the record that it was
   requested.
2. **Dispatch is by `intent_type`.** Each action domain owns exactly the
   `intent_type` value(s) that route to it; no domain infers from unstructured
   content.
3. **Every gated action returns an explicit authorized/denied result, never
   silent.** No domain handler skips a response or throws instead of returning
   a typed refusal — same "state what it would do, don't silently skip"
   principle as the two-engine design above.

What's explicitly NOT locked in by this: the exact shape of a domain's actor
class, its internal methods, or how many gated calls a single intent triggers
— those stay domain-specific and get designed per integration.

**Compound-action pattern, locked in from the Gmail read/act interaction check,
binding for any future domain with the same shape**: Calendar's `act` is
self-contained — `create_event()` needs nothing from `calendar_read` to produce
a correct action. Gmail's is not, for at least one real case: drafting a *reply*
requires the source message's content, not just a `gmail_act` grant — a data
dependency, not merely a second permission check. This means a single
`intent_type` (`email_draft`) can cover two different action shapes (fresh
compose vs. reply-to-existing), and the existing action-domain wiring pattern
above — one gated call, one domain, self-contained — was proven on the case
where that distinction doesn't exist.

Locked-in resolution: **an act domain's gated call may internally depend on a
read domain's gated call and grant, when the intent requires referencing
existing content.** Concretely, for such cases: both the relevant `_read` and
`_act` grants must be authorized before the compound action proceeds — a
`gmail_act`-only grant is not sufficient to draft a reply, only a fresh
compose. This is a second binding shape alongside the single-domain one, not a
replacement for it — most actions (Calendar's, Gmail fresh-compose) stay
single-domain; only actions that inherently reference another domain's content
use the compound shape. **The rule above is locked in. The mechanism is
explicitly open — not a placeholder "TBD," a real underspecified problem found
by trying to design it and stopping before locking in something that fits one
case and breaks on the others:**

1. **At least three distinct reference shapes exist**, found by considering a
   second hypothetical case rather than generalizing from Gmail reply alone:
   *content-reference* (act needs one prior-read item's content to compose
   against — "reply to Sarah's email"), *target-resolution* (act needs to find
   *which* existing item to modify, not attach content to a new one — e.g. a
   future Calendar case, "move my meeting with Sarah to Friday"), and
   *aggregate-reference* (act needs a *set* of prior-read items, not one —
   "summarize my unread emails and draft a status update"). A single optional
   reference field only fits the first shape, and only awkwardly.
2. **A resolution step is missing from the pipeline entirely, independent of
   field shape.** `VoiceIntentClassifier` only ever sees the raw utterance plus
   `PersonalContext` — it has no access to live read-domain data at
   classification time, so it cannot itself emit a concrete reference (a
   message ID, an event ID) for anything described in natural language ("Sarah's
   email about the board deck"). Populating any reference mechanism requires an
   actual read call *between* classification and the act call, searching/
   matching read results against the utterance's description — a real pipeline
   step nothing today designs for, not something a classifier field can paper
   over.

**Do not build anything for compound actions until a real case forces the
resolution-step question to be answered concretely** — most likely when
`gmail_act`'s reply case, or the read/act-triggering question below, actually
gets picked up for real build work, not before.

**Known gap, deliberately deferred, not a bolt-on**: no field or record anywhere
captures whether a gated action was actually executed, denied, or not applicable
— `EntityMemoryRecord` records what was *requested* (`decision_text`, `salience`,
etc.), not what happened as a result. This is a real design question in its own
right (a field on `EntityMemoryRecord` vs. a separate linked record entirely —
arguably action-outcome is a different *kind* of fact than "what was requested"),
close to the same territory as `outcome`'s existing reserved-but-unused field and
Stage D's "hypothesis formation over accumulated history." Deliberately left open
for its own deliberate design pass at or near Stage D, not decided under the
momentum of the Calendar-wiring checkpoint.

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

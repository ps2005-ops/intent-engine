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

**`voice/` built AND now wired into the live path**: `PersonalContext` (a view
computed from real `entity_memory.read_records()`, not a standalone snapshot —
see the amendment note in `docs/weekly/week-04-plan.md`), `VoiceIntentClassifier`
(own prompt/schema, Haiku, measured well under the <3s voice latency target),
`process_voice_interaction()` (composes classification + entity-memory write,
source="voice", every interaction written with no filtering by salience).
`EntityMemoryRecord.salience` added (`Optional[Literal["low","medium","high"]]`,
voice-only) as the signal Stage D will query/weight by later. Salience
calibration is an open, partially-characterized question — real 10-run
distributions showed `intent_type` perfectly stable but `salience` varying on
ambiguous utterances specifically, correlated with `PersonalContext` injection;
documented as a code comment in `voice/classifier.py`, not resolved.

**The `PersonalContext` wiring gap (found by direct code read: `build_personal_context()`
was defined and tested in isolation but never called from the live path — every
real voice interaction classified with `context=None`) is now closed.**
`process_voice_interaction()` builds `PersonalContext` internally by default
(`context = context or build_personal_context(entity_id, mock_data=MockPersonalData(),
path=entity_memory_path, permission_registry=registry)`), same idiom as every
other collaborator in that function — a real default, not an inert `None` a
caller has to remember to supply. Uses the `entity_id` parameter already
required for the entity-memory write; no new required input.

This same change also answers the `gmail_read`/`calendar_read` triggering
question, per Step 3's finding that both were one unresolved design question:
`build_personal_context()` now also pulls gated `StubGmailReader`/
`StubCalendarReader` data unconditionally, on every classification, independent
of `intent_type` — no dedicated intent type needed for this (ambient) case. The
result is three-valued (`GmailContext`/`CalendarContext.state`: `"fetched"`,
`"not_authorized"`, `"skipped_for_cost"`), not a bool, from day one — mirrors
`CalendarReadResult`/`GmailReadResult`'s "state what it would do, don't silently
skip" principle, and `"skipped_for_cost"` is reserved, unused today, the same
pattern as `EntityMemoryRecord.outcome`.

**Explicitly OPEN, not decided**: whether these pulls should stay unconditional,
become conditionally gated (e.g. only pull when relevant), or get cached is
deliberately deferred — deciding it now would mean guessing against a cost (real
Stage C vendor latency) that doesn't exist yet with stubs, the same trap already
avoided with `entity_id` normalization and the compound-action schema. Today's
interim strategy (unconditional, matching today's real near-zero stub cost) is
not a permanent default — when this gets decided with real Stage C latency
numbers in hand, it changes which strategy populates the `state` field, not the
field shape itself.

Verified with two real live runs (real Haiku classification, real file writes,
no mocks), same utterance, same seeded prior entity-memory history, two
permission scenarios: authorized (`gmail_read`+`calendar_read` both granted) —
`PersonalContext.to_prompt_text()` showed real prior history AND 3 fetched Gmail
messages AND 3 fetched Calendar events; deny-by-default (no grants) — the same
prompt text explicitly stated "Gmail: Not authorized to read Gmail." and
"Calendar: Not authorized to read calendar." rather than silently omitting
either section. 80 offline tests passing (6 new in `test_context_schema.py`
covering all three states and prompt-text separation, 2 new in
`test_voice_pipeline.py` confirming the pipeline actually builds and uses
context when not supplied).

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

**Stage C, Gmail: `gmail_act` wired (fresh-compose only), `gmail_read`
unwired**: `voice/gmail.py` — `StubGmailReader` (`"gmail_read"`) and
`StubGmailActor.create_draft()` (`"gmail_act"`), mirroring Calendar's shape.
`process_voice_interaction()` now routes `email_draft` `VoiceIntent`s through
`PermissionRegistry` to `StubGmailActor` directly, same shape as
`calendar_block`. **Scoped to fresh-compose only, deliberately**: there is no
field distinguishing "compose new" from "reply to existing," so every
`email_draft` intent is treated as fresh-compose, including reply-style
utterances this pipeline cannot yet detect — a known, documented limitation,
not a silent gap, tied directly to the tabled compound-action mechanism above.
Verified with a real live run (real API call, real file writes, no mocks) for
both an authorized and a denied `gmail_act` grant on the same utterance
("draft an email to Sarah about pushing the board deck review to Friday") —
both produced correct `GmailActResult`s and both wrote an `EntityMemoryRecord`.
Observed gap from that live run, not fixed: the classifier's `target` field
comes back as a bare name ("Sarah"), not an email address — tracked as its own
named, open gap ("recipient resolution for `gmail_act`") in `PROGRESS.md`, not
duplicated in full here. 57 offline tests passing.

**Update: the ambient-context half of this question is now resolved (see above)
— `gmail_read`/`calendar_read` data reaches every classification via
`PersonalContext`, gated, independent of `intent_type`.** What remains
genuinely separate and still unresolved: `gmail_read`/`calendar_read` as
**first-class, explicitly-triggerable intents** (e.g. "what's on my calendar
today" as a dedicated `intent_type`, mirroring `calendar_block`/`email_draft`'s
action-domain pattern, with the read result surfaced back to the user directly
rather than only fed silently into classifier context). That's a different
capability than ambient enrichment — no evidence yet that any classified
utterance needs it — and stays explicitly out of scope: **do not build
`gmail_read`/`calendar_read` as first-class triggerable intents**, per Step 3's
original finding, until a real case forces the question. Notion integration
not started.

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

### Known, permanent limitation: the correction/refinement loop is an imitation-learner, not a criterion-calibrator

`core/draft_generator.py`'s shadow-guess-and-correct loop (the current, concrete
implementation of Stage E's "generate a concrete, inspectable action" for the
`recurring_message` domain) works by imitation: it gathers real prior instances
of an artifact and asks an LLM to produce the next one in the same style, then
treats a person's correction as a restated instance of that same artifact,
feeding future generation. This works precisely because `recurring_message`'s
artifact (a message to send) has a STYLE to match — tone, phrasing, format.

This does **not** generalize to every future domain, confirmed by direct code
analysis (the image-verification architecture-generalization audit), not
assumed. Some domains produce artifacts with a DECISION RULE to calibrate
instead — a verdict, a threshold, a criterion — and a "correction" there means
something structurally different: not "here's what the message should have
said," but "here's how the criterion should be adjusted" (e.g. "that photo's
actually fine, you're being too strict about the barcode"). Feeding that kind
of correction into `generate_draft()`'s imitation prompt as another instance
to stylistically imitate does not do anything useful — there is no "next
instance's style" for a decision rule to imitate.

**Before applying this mechanism to any new domain, classify it first:** is a
"correction" in this domain a restated instance of the artifact itself
(imitation-shaped — this mechanism applies as-is), or a criterion adjustment
(rule-shaped — this mechanism does NOT apply as-is, and needs a different
feedback shape, e.g. accumulating standing exceptions/threshold adjustments
fed into the judgment prompt rather than more examples to imitate)? Getting
this classification wrong before building is the likeliest way this
mechanism would silently fail on a second domain.

**Update: this is no longer a paper finding — it is CONFIRMED BY A REAL
FAILURE CASE.** `core/image_verification.py`'s `verify_image()` was built for
real (not audited on paper) specifically to test this. A real verification
result (`"Verdict: incomplete. Missing: Amount visible..."`, produced by a
live Claude vision call against a constructed test image with the amount
field cropped out of frame) was reacted to with exactly the kind of reply
this section already anticipated above: *"you're being too strict about the
barcode, that's fine."* `classify_draft_reply()` classified this as
`"correction"` — defensible — but the resulting `correction_text` was not
merely a poor conceptual fit, it was concretely wrong: it **fabricated a
"Barcode" field that was never on the checklist and never mentioned in the
original judgment**, hallucinated from the reply's incidental wording, and
the result was internally self-contradictory — it still read
`"Verdict: incomplete"` even though the person said "that's fine," so the
one adjustment the reply actually asked for wasn't reflected at all. See
`PROGRESS.md`'s "Architecture-generalization audit + second real domain:
image-verification" section for the full real output. One real failure case
is evidence the mechanism doesn't apply as-is; it is deliberately NOT treated
as evidence of what the right mechanism should be (a running exceptions
list? per-checklist-item override? something else?) — designing that from a
single data point would repeat the exact mistake already avoided twice this
project (the compound-action mechanism deferral, the PersonalContext
pull-strategy deferral). Deferred until real usage across this or another
criterion-shaped domain exists to shape it properly, not guessed at now.

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

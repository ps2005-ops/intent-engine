# Week 4 Plan: Voice Assistant Intent Engine Foundation

**Status: plan only, not started.** No code written, no dependencies installed.
Written the night of Week 3's close-out, for review before any Week 4 build begins.

## Spec recap (Week 4 milestone)

- Voice input pipeline: transcription (Deepgram) → intent inference → suggested
  action → response.
- Personal context model, parallel to `BusinessContext`: calendar, email patterns
  (mock data initially), goals/projects, relationships.
- 10-15 intent types: reminder, email draft, calendar block, task creation,
  context retrieval, etc.
- Milestone: working voice interface, **<3s latency** (spec's own fallback: "accept
  2-3s for now, optimize later"), tested end-to-end on 10 personal intent examples.

## Question 1: New lighter pipeline in `core/`, separate from `simulator/`?

**Yes — but more precisely, a new voice-specific module, not a shared schema
crammed into the existing `core/classifier.py`.**

Reasoning:
- `core/classifier.py`'s `IntentClassifier` already exists (Sonnet, `StructuredIntent`
  schema: `decision_summary`, `goals`, `constraints`, `risk_tolerance`) and was
  measured at **~4.5s** in isolated Week 1 testing — comfortably fine for the
  business simulator's ~10s budget, hopeless against voice's <3s budget on its own,
  before transcription or response synthesis are even counted.
- `StructuredIntent`'s fields are wrong for voice anyway — `risk_tolerance` and
  `goals`/`constraints` don't map to "remind me to follow up with Sarah in 5 days."
  Voice needs its own schema, not a reuse of the business one.
- This mirrors exactly how `simulator/` was built in Week 1: a domain module with
  its own schema and prompt, sharing only `core/llm_client.py` (the API wrapper)
  and `core/pipeline.py` (the `Stage` contract) — not a shared business-shaped
  schema. Voice should follow the identical pattern: `voice/` gets its own
  `classifier.py` (or `analysis.py`) with its own prompt and schema, built from
  the same `core/` primitives.
- This is also the direct answer to "without risking the simulator pipeline": if
  voice's classifier is a physically separate file with its own prompt string and
  schema dict, there is no code path by which Week 4 work can regress
  `simulator/analysis.py`. The only shared surface is `core/llm_client.py`, which
  hasn't changed shape since Week 1 and shouldn't need to.

## Question 2: What does the lighter schema look like?

Proposed `VoiceIntent` (flat schema, matching the lesson from Week 1's
nested-object Haiku failures — parallel/flat fields, not nested structures):

```
intent_type:  enum, one of the 10-15 types (reminder, email_draft, calendar_block,
              task_creation, context_retrieval, ... — full list TBD, seed with the
              spec's examples and extend as real test examples demand more)
target:       short string — who/what this is about (e.g. "Sarah", "the Q3 planning doc")
when:         short string — the RAW time phrase from the utterance (e.g. "in 5 days"),
              not parsed into a datetime; parsing/scheduling is a downstream concern,
              not the LLM's job
content:      short string — the actual substance (e.g. "follow up", the email body
              gist, the task description)
```

Four fields, all flat strings/enum — deliberately much smaller than the simulator's
~13-field schema. `target`/`when`/`content` are optional (many intent types won't
use all three) but even at full length this is a fraction of the simulator's prompt.

**Not yet decided, needs your input before building**: should `suggested_action` (a
short human-readable description of what the assistant proposes to do, e.g.
"Creates a recurring reminder tied to Sarah's communication pattern") be a 5th
field generated in the same call, or a second, even-cheaper step (template-based,
like the causal-relationships/retrieval-digest pattern — pure code, no LLM)? Given
the <3s budget has essentially no room for a second LLM call, I'd lean toward
generating it in the same call, but this needs to be checked against real latency
numbers, not assumed.

## Question 3: Minimal build sequence, without touching the simulator pipeline

In dependency order — each step should be checkpointed before the next, same
discipline as Weeks 1-3 (measure before committing to an architecture):

1. **Measure the real latency budget first, before building anything.** A single
   isolated Haiku call with a schema this size (roughly comparable to the Week 1
   classifier-alone test, which measured ~2.9s at the time) needs to be measured
   fresh, since the exact schema hasn't been written yet. This number determines
   how much room is actually left for transcription + synthesis inside the <3s
   target — if the LLM call alone eats 2.5s, the <3s target may need the same
   "typical-case, not hard gate" treatment the simulator's 10s target got, and
   that should be an explicit, deliberate decision (like the last one), not a
   discovery made mid-debugging.
2. **`voice/context_schema.py`** — `PersonalContext`, parallel to `BusinessContext`.
   Spec says mock data initially — no live Gmail/Calendar API integration yet, so
   this is just a plain data class populated by hand for the 10 test examples, not
   a real integration.
3. **`voice/schemas.py`** — `VoiceIntent` (see Question 2), following the
   `simulator/schemas.py` pattern (kept out of `core/` since these are
   voice-specific concepts, not domain-agnostic ones).
4. **`voice/classifier.py`** — the new Stage-based intent classifier, own prompt,
   own schema, own `LLMClient` instance (model choice — Haiku almost certainly,
   but confirm against step 1's measurement). Test against **text input first**,
   not audio — decouples "does intent classification work and hit budget" from
   "does the Deepgram/TTS integration work," so the riskiest new external
   dependency doesn't block validating the core logic. Mirrors how the business
   simulator's CLI took text input before any voice concerns existed.
5. **10 personal intent test examples** (`tests/fixtures/personal_intents.json` or
   similar), mirroring the 5 business fixtures pattern — covering the 10-15 intent
   types the spec asks for.
6. **Voice I/O wiring** (Deepgram STT, OpenAI TTS or ElevenLabs) — **new external
   API dependencies, new API key(s), explicitly flagged for your sign-off before
   installing anything**, same as the embedding-backend decision. This is the
   last step, not the first, so steps 1-5 are validated on cheap, fast, offline-testable
   text input before any new vendor/cost is introduced.
7. **End-to-end latency verification** — same multi-run-before-trusting-any-number
   discipline established this session (the pricing-increase/asia-expansion
   variance lesson applies here too, probably more so given the tighter budget).

**Explicit scope boundary for Week 4**: "suggested action" means generating and
displaying/speaking the proposed action, not executing it against real Gmail/
Calendar APIs — that's later-week integration work per the spec's own schedule.
Week 4 proves the intent engine works on personal context and hits its latency
target; it doesn't wire up real side effects yet.

## Open questions for you to resolve before I start building

1. Confirm the `voice/` module boundary and flat `VoiceIntent` schema shape above,
   or redirect.
2. `suggested_action`: same call or separate step (Question 2's open item)?
3. Voice backend choice: Deepgram for STT is spec's explicit suggestion — any
   preference between OpenAI TTS and ElevenLabs for synthesis, or should I bring
   a comparison (cost, latency, quality) before you decide, same as the embedding
   backend question?
4. Should step 1 (measure a bare intent-classification call) happen as a
   throwaway experiment I report back on, or do you want to review the exact
   schema/prompt before I even run that measurement?

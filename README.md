# Intent Engine

## Mission

Build a shared **Intent Engine** — a reusable module that infers a person's underlying
goals, constraints, and risk tolerance from raw context — and apply it to two products
over a 26-week build:

- **Pre-Mortem Machine** (business decision simulator): a founder describes a decision
  and their business context; the system returns a structured risk audit before they commit.
- **Cognitive Delegate** (personal voice assistant): the same Intent Engine applied to
  personal context (calendar, email, goals) via voice.

The business simulator comes first (Weeks 1–8) because it has lower privacy/trust
friction, a clearer feedback loop, and more constrained intent inference than the voice
assistant. Once the Intent Engine works on business data, extending it to personal
context is domain adaptation, not rearchitecture. Full 26-week schedule: see the
original planning doc (not tracked in this repo).

## Status: Weeks 1-3 complete; Stage A/B (entity memory + permissions) complete; voice pipeline + Stage C (Calendar wired, Gmail act wired fresh-compose-only, Gmail read unwired) complete

**Week 1 goal:** a working CLI that takes a business decision as text + context and
outputs a structured risk audit in under 10 seconds, validated on 5 example decisions.

**Week 2 goal:** the simulator also classifies the founder's primary priority
(growth/profitability/survival/optionality) and runs 3 scenarios (upside/base/downside),
grounded in hand-coded causal relationships — while staying under the same 10s budget.

**Week 3 goal:** ground the simulation in similar past decisions with known outcomes,
retrieved via similarity search against a curated reference set.

**Stage A/B goal** (per `docs/weekly/intent-engine-v2-entity-memory.md`, which
supersedes the original Week 5+ direction): a structured, append-only entity-memory
store both `simulator/` and `voice/` write into, plus a deny-by-default permission
registry gating future action-taking. `--entity-id` is now required on every
`premortem` run — see `core/entity_memory.py` and `core/permissions.py`.

**Voice pipeline + Stage C goal**: `voice/PersonalContext` (a view computed from
entity memory), `voice/VoiceIntentClassifier`, and `process_voice_interaction()`
(classification → unconditional entity-memory write) are built and verified.
Both Calendar and Gmail's act tier are wired directly into the voice pipeline
end-to-end: `calendar_block` → `StubCalendarActor` and `email_draft` →
`StubGmailActor`, each flowing classification → entity-memory write →
permission check → the stub actor, gated on `"{domain}_read"`/`"{domain}_act"`.
`email_draft` is scoped to fresh-compose only — reply-to-existing needs a
compound-action mechanism (an act domain depending on a read domain's grant
*and* content) that's deliberately tabled rather than designed from a single
case; see `docs/weekly/intent-engine-v2-entity-memory.md`. This wiring shape
(unconditional write before any gate check, `intent_type`-based dispatch,
gated actions always return an explicit authorized/denied result) is locked in
as binding for every future action domain. `gmail_read` is built and tested but
deliberately not yet wired — there's no natural `intent_type` trigger for a
read the way there is for an action. See
`docs/weekly/intent-engine-v2-entity-memory.md` for the full account.

**Weeks 1-3, all done.** All 5 fixtures average ~7.9-10.0s across repeated runs — comfortably
meeting <10s as a *typical-case* target. Multi-run testing showed ~5% of individual
calls spike to 11-13s from API-side variance independent of content length or fixture,
so <10s is treated as an average to hit, not a strict per-call gate (the CLI prints a
"still working" message so an occasional slow call doesn't read as broken). See
[PROGRESS.md](PROGRESS.md) for the full tuning history, including two rounds of latency
debugging, two distinct malformation bugs fixed at their root cause rather than
patched, and an embedding-backend reversal (sentence-transformers → TF-IDF) made after
measuring — not guessing — its real cost.

**Pipeline:** `Raw Context Input → Intent Classification → Structured Intent Output
(goals, constraints, risk tolerance) → Causal-Grounded Scenario Generation → Outcome
Simulation → Risk Audit`

The simulator's live pipeline (`simulator/analysis.py`, `PremortemAnalyzer`) runs this as
**one combined Claude call** on Haiku 4.5, not multiple sequential calls — an early
two-call version (Sonnet, intent then audit separately) measured 21-23s end-to-end, well
over budget. `core/classifier.py` and `simulator/outcome_simulation.py` still implement
the Week-1-only version of the pipeline as two separate, independently testable stages,
kept for reuse where the tighter latency budget doesn't apply — they're just not what the
CLI calls today.

**Positioning layer:** the risk audit carries a `narrative_summary` — one vivid,
second-person sentence (regret-avoidance framing, explicit pattern-recognition authority,
cost-of-inaction) that sits above the quantified audit, per the "Pre-Mortem Machine"
positioning strategy (Rory Sutherland framework) in the original spec. The quantified
audit itself — failure modes, likelihood tags, stress-tests — is unchanged in structure
from Week 1; only the wording tone and this new field were added.

**Causal + scenario layer:** `simulator/causal_model.py` holds 8 hand-coded causal
relationships for early-stage SaaS (CAC/LTV, hiring/burn, pricing/churn, etc.), keyword-
matched per decision and injected into the prompt as grounding context. Scenarios are
represented as a short situational tag + terse delta line per branch (e.g. `UPSIDE
(strong fundraising): +$2M runway, +2 hires`), matching the Week 2 spec's own example
format rather than full narrative sentences per scenario — cheaper to generate and more
spec-faithful.

**Retrieval layer:** `simulator/retrieval.py` finds the top-3 most similar past
decisions from an 18-entry hand-curated reference set (`simulator/data/reference_decisions.json`)
via TF-IDF + cosine similarity (not a true semantic embedding model — see PROGRESS.md
for why that reversal happened), formats them into short digest lines with a bucketed
match-quality tag (`strong match`/`loose match`) and structured `team_size`/`runway_months`
deltas against the decision-time snapshot of each reference case, and injects the digest
into the same combined call — no second LLM call, no raw text dump.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

## Usage

`--entity-id` is required on every run — it tags the entity-memory record this
decision gets written under (see `core/entity_memory.py`). Free text is fine;
`"Acme Inc"` and `"acme inc."` accumulate under the same normalized entity.

```bash
# From a JSON file (decision_text + context):
premortem --input tests/fixtures/business_decisions.json --entity-id "Acme Inc"   # (see below re: batch format)

# Ad hoc:
premortem --decision "We're expanding into Asia with \$2M over 18 months." \
  --entity-id "Acme Inc" \
  --revenue "\$60k MRR" --growth-rate "10%/mo" --team-size 12 --runway-months 16 \
  --market "B2B SaaS" --competitive-position "two larger incumbents" \
  --founder-goals "establish APAC foothold before a competitor does"

# JSON output instead of formatted text:
premortem --decision "..." --entity-id "Acme Inc" --json
```

Note: `tests/fixtures/business_decisions.json` is a list of 5 decisions used for testing,
not a single-decision input file — `--input` expects `{"decision_text": ..., "context": {...}}`
for one decision. To run all 5 fixtures at once and read the output, use:

```bash
python scripts/run_examples.py
```

## Running tests

```bash
pytest                    # unit tests always run; live-API e2e tests skip without a key
ANTHROPIC_API_KEY=sk-... pytest tests/test_simulator_e2e.py -v   # run the live e2e tests
```

## Repo structure

```
src/intent_engine/
  core/        # shared Intent Engine — domain-agnostic, reused by simulator and (later) voice
  simulator/   # Pre-Mortem Machine: business context schema, causal model, retrieval, CLI
               # (analysis.py is the live combined-call pipeline; causal_model.py + schemas.py
               # hold the Week 2 causal relationships + Scenario/ScenarioSet shapes;
               # retrieval.py + data/reference_decisions.json hold the Week 3 retrieval layer)
  voice/       # Cognitive Delegate: context_schema.py (PersonalContext), classifier.py
               # (VoiceIntentClassifier), pipeline.py (process_voice_interaction, the
               # calendar_block + email_draft wiring), calendar.py (Stage C Calendar
               # stub, wired), gmail.py (Stage C Gmail stub -- act wired fresh-compose-
               # only, read not yet wired), schemas.py
tests/         # unit tests (mocked) + live e2e test against the 5 fixture decisions
scripts/       # run_examples.py — manual review of the 5 fixture decisions
docs/weekly/   # per-week notes
```

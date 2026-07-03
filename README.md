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

## Current week: Week 1 — Intent Engine Scaffolding + Simulator Proof-of-Concept

**Goal:** a working CLI that takes a business decision as text + context and outputs a
structured risk audit, validated on 5 example decisions. **Done** — verified reliably
under a 12s latency budget against the live API (see [PROGRESS.md](PROGRESS.md) for why
this moved from the original 10s target).

**Pipeline:** `Raw Context Input → Intent Classification → Structured Intent Output
(goals, constraints, risk tolerance) → Outcome Simulation → Risk Audit`

The simulator's live pipeline (`simulator/analysis.py`, `PremortemAnalyzer`) runs this as
**one combined Claude call** on Haiku 4.5, not two sequential calls — the two-call version
(Sonnet, intent then audit separately) measured 21-23s end-to-end, well over budget.
`core/classifier.py` and `simulator/outcome_simulation.py` still implement the pipeline as
two separate, independently testable stages and are kept for reuse where the tighter
latency budget doesn't apply — they're just not what the CLI calls today. See
[PROGRESS.md](PROGRESS.md) for why.

**Positioning layer:** the risk audit also carries a `narrative_summary` — one vivid,
second-person sentence (regret-avoidance framing, explicit pattern-recognition authority,
cost-of-inaction) that sits above the quantified audit, per the "Pre-Mortem Machine"
positioning strategy (Rory Sutherland framework) in the original spec. The quantified
audit itself — failure modes, likelihood tags, stress-tests — is unchanged in structure;
only the wording tone and this new field were added. See PROGRESS.md for the tuning
process, including why the latency budget moved to 12s.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

## Usage

```bash
# From a JSON file (decision_text + context):
premortem --input tests/fixtures/business_decisions.json   # (see below re: batch format)

# Ad hoc:
premortem --decision "We're expanding into Asia with \$2M over 18 months." \
  --revenue "\$60k MRR" --growth-rate "10%/mo" --team-size 12 --runway-months 16 \
  --market "B2B SaaS" --competitive-position "two larger incumbents" \
  --founder-goals "establish APAC foothold before a competitor does"

# JSON output instead of formatted text:
premortem --decision "..." --json
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
  simulator/   # Pre-Mortem Machine: business context schema, risk-audit stage, CLI
  voice/       # placeholder for the Week 4+ Cognitive Delegate module
tests/         # unit tests (mocked) + live e2e test against the 5 fixture decisions
scripts/       # run_examples.py — manual review of the 5 fixture decisions
docs/weekly/   # per-week notes
```

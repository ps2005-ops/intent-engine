# Progress

Weekly milestone tracker against the 26-week schedule. Update this every Sunday
(per the plan's weekly execution checklist): what shipped, what's blocked, what the
decision-gate signal says.

## Week 1: Intent Engine Scaffolding + Simulator Proof-of-Concept

**Spec goal:** CLI that takes a business decision as text + context, outputs a
structured risk audit in <10s, tested on 5 example decisions.

**Status:** In progress.

- [x] Repo scaffolded (core/simulator/voice module split, tests, docs)
- [x] Git initialized
- [x] Intent classification stage (Claude tool use → `StructuredIntent`)
- [x] Outcome simulation / risk audit stage (Claude tool use → `RiskAudit`)
- [x] `premortem` CLI
- [x] 5 test business decisions written as fixtures
- [x] Unit tests (mocked, no API calls) passing
- [ ] Live e2e run against real API on all 5 decisions, confirming <10s each — **blocked on ANTHROPIC_API_KEY**
- [ ] Manual quality review of the 5 risk audits (`scripts/run_examples.py`)

**Notes / deviations from spec:**
- Used Claude Sonnet 5 (not Llama-2) with tool use for structured extraction — two
  sequential tool calls (intent, then risk audit) rather than one combined call, so each
  stage is independently swappable per the "swappable module" requirement.
- Skipped Week 1's optional LoRA fine-tuning learning exercise — not required for the
  CLI to work, can revisit if classification quality needs it.
- Business context fields (revenue, growth_rate) are free text, not strict numeric
  types, to avoid guessing units/formats this early.

## Week 2+

Not started.

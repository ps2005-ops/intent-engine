# Documentation index

*The navigation map for this repository's docs. This file is an **index**,
not a source of truth — it points at the canonical documents and never
restates them. Added 2026-07-20 per the architecture review
(`V1_COMPLETION_ROADMAP.md`, Part D). Purpose: nothing important should be
discoverable only by `ls`.*

## One source of truth per topic

If two documents disagree, the one named here wins and the other is
corrected.

| Topic | Single source of truth |
|---|---|
| Company architecture (company scope) | `docs/COMPANY_OS.md` |
| Engineering / decision map (engineering scope) | `docs/DECISION_INTELLIGENCE_ARCHITECTURE.md` |
| Build sequence for V1 completion | `docs/V1_COMPLETION_ROADMAP.md` |
| Autonomy protocol (the agent kernel) | `overnight-execution-plan.md` Part A → to be promoted to `docs/AGENTOS.md` |
| Autonomous task queue | `ROADMAP.md` |
| Near-term execution queue | `PLAN_2026-07-21.md` |
| Marketing strategy | `marketing/MARKETING_PLAN_V2.md` |
| Company event contract (envelope + taxonomy + producer ownership) | `src/intent_engine/events/envelope.py` (architecture: `docs/COMPANY_OS.md` Part 3) |
| CRM contract (identity + taxonomy + lifecycle axes) | `src/intent_engine/crm/events.py` (architecture: `docs/COMPANY_OS.md` P8) |
| Analytics contract (MetricResult + versions + windows) | `src/intent_engine/analytics/models.py` (architecture: `docs/COMPANY_OS.md` P10) |
| Knowledge contract (feedback/insight/knowledge + consent + citations) | `src/intent_engine/knowledge/records.py` (architecture: `docs/COMPANY_OS.md` P9) |
| Marketing contract (campaign/brief/draft/handoff + claim classes) | `src/intent_engine/marketing/records.py` (strategy: `marketing/MARKETING_PLAN_V2.md`) |
| Growth contract (experiment envelope + labels + namespaces) | `src/intent_engine/growth/records.py` (architecture: `docs/COMPANY_OS.md` P7) |
| Agent registry | `docs/AGENTS.md` |
| Tooling decisions (NOW / LATER / NEVER) | `docs/TOOLS.md` |
| Honest claim surface / positioning | `docs/POSITIONING.md`, `docs/CAPABILITY_BOUNDARIES.md` |
| History + design-principle fix library | `PROGRESS.md` |
| Cross-project status | `docs/PORTFOLIO.md` |

## The five buckets

**1 · Sources of truth** — `COMPANY_OS.md`, `DECISION_INTELLIGENCE_ARCHITECTURE.md`,
`V1_COMPLETION_ROADMAP.md`, `AGENTS.md`, `TOOLS.md`, `POSITIONING.md`,
`CAPABILITY_BOUNDARIES.md`, `PORTFOLIO.md`; root: `ROADMAP.md`,
`PLAN_2026-07-21.md`, `overnight-execution-plan.md`,
`marketing/MARKETING_PLAN_V2.md`.

**2 · Architecture / maps** — `COMPANY_OS.md` (company),
`DECISION_INTELLIGENCE_ARCHITECTURE.md` (engineering/decision). Scope
boundary is stated in each header.

**3 · Specs & proposals** — `TASK4_SPEC_PROPOSAL.md`,
`TASK5_WIRING_SPEC_PROPOSAL.md`, `BA_ACCELERATION_PROPOSAL.md`,
`CADENCE_V2_PROPOSAL.md`, `MECHANISM_EXPLANATION_DEPTH_SPEC.md`,
`MECHANISM_LIBRARY_EXPANSION_PROPOSAL.md`, `REGIME_VOCAB_WIDENING_SPEC.md`,
`AP_FEED_DECISION_PREP.md`, `T007_PARK_FINDING.md`,
`MECHANISM_LIBRARY_STATE.md`, `library_batch{1,2,3}_review_sheet.md`. Each
should be tagged OPEN or DONE in its header; DONE proposals are archival
candidates (below).

**4 · Knowledge / history** — `PROGRESS.md` (history + the design-principle
fix library), `docs/weekly/`.

**5 · Reports / traces / handoffs** — `reports/` (overnight_trace,
market_engine_trace, synthetic-worlds evals), `MORNING_HANDOFF.md` (the
single living handoff), `T005_LIVE_RUNS.md`, `docs/report_mockup/`.

## The doc template (every new subsystem doc answers these)

Purpose · How it works · What depends on it · What events trigger it ·
What metrics define success · What automations exist · What future work
remains. (Cross-reference other docs; never restate them.)

## Open housekeeping (proposed, archive-not-delete — A3)

- **Handoff/context consolidation.** Keep `MORNING_HANDOFF.md` as the
  single living handoff. `COWORK-HANDOFF-2026-07-17.md`, `MORNING_REPORT.md`,
  and `intent-engine-context-3.md` overlap it → move to `docs/archive/`
  with a one-line pointer each. *Proposed; not yet executed (file moves are
  founder-gated and touch the git-lock state noted in `PORTFOLIO.md`).*
- **Dangling reference (review finding #4).** `AGENTS.md §1/§4` and
  `PORTFOLIO.md` reference `market-engine-execution-plan.md`, which is **not
  at repo root and was not found in git history from the sandbox** (possibly
  the known git-lock state). Resolution: verify on the Mac; if truly absent,
  repoint those references to `reports/market_engine_trace.md` (the
  surviving record of the M1–M9 market-engine work). *Flagged; the
  reference edits are a small, founder-gated follow-up.*
- **DONE proposals** in bucket 3 → `docs/archive/` once confirmed DONE,
  leaving a pointer. History preserved.

# AGENTS.md — the standing agents

*Sections 1–4 are the Workstream 1 one-time capability audit; section 5
onward registers the subsystem agents built since (T020 Product; T019
Research is flagged as outstanding in section 5). Defines purpose, scope
walls, and authorized tooling for each of the agents referenced across
`overnight-execution-plan.md`, `market-engine-execution-plan.md`, and the
standing Cowork operations brief. Every agent inherits the Global Autonomy
Protocol (`overnight-execution-plan.md` Part A) in full: deterministic bars
over LLM self-assessment, park-don't-improvise on ambiguity, one commit per
task, suite green before every commit, spend tracked and reported, TRACE
discipline (append to the relevant trace file after every completed or
parked task).*

---

## 1. Intent / market engine agent

**Repo**: `~/intent-engine`.

**Purpose**: builds and maintains the causal intent engine — Pre-Mortem
simulator, Cognitive Delegate, the four causal-engine pillars (calibration
substrate, mechanism library, entity graph, eventual game theory), and the
market-intelligence extension (M1-M9). Picks up RUNNABLE tasks from
`ROADMAP.md` via `nightly_agent.sh` (launchd, 1am, budget-capped) and
executes `overnight-execution-plan.md` / `market-engine-execution-plan.md`
task queues.

**May touch**: `src/`, `tests/`, `scripts/`, `data/` (additive schema
changes only where a task explicitly grants it), `ROADMAP.md`,
`PROGRESS.md`, `reports/overnight_trace.md`,
`reports/market_engine_trace.md`. Branch `agent/<task-id>` for autonomous
runs; direct-to-main only in a supervised Cowork session with the human
present.

**Hard walls** (inherited from Part A3, restated because they're load-bearing
for this agent specifically): no new external dependencies without PARK; no
vendor accounts/OAuth flows; no network calls beyond the Anthropic API and
explicitly-granted web search/yfinance/FRED/Tiingo; no modifications to
PremortemAnalyzer's combined-call prompt, entity_memory schemas (additive
only), the scrap-metal live path, or voice/cli.py wiring; no rule/model
tuning against the 18 backtest cases (permanent overfitting guard); no
force-pushes/history-rewrites/file deletion (archive instead); no
self-expansion of task scope.

**Authorized skills/tools**: `superpowers` (global — TDD/planning
methodology, well-aligned with this agent's own park-don't-improvise and
verification-before-completion discipline). No marketing/design/SEO skills
— out of scope for this agent. FRED/Tiingo/Anthropic API access via `.env`
(human-provisioned keys only, never printed/logged).

---

## 2. Personal assistant agent

**Repo**: `~/job-application-agent` (also: calendar, general task
coordination across both repos when acting as the user's day-to-day
Cowork agent).

**Purpose**: runs the job-collection pipeline (launchd 09:30/17:00),
prepares tailored materials and outreach drafts, and processes the
standing application queue per Workstream 4's dry-run/real split.

**May touch**: `apply_agent/`, `scripts/`, `config/`, `runs/`, `evidence/`,
`applications/APPLICATION_LEDGER.md`, Gmail compose-scope drafts. Playwright
submission and Gmail sending are real, live capabilities in this repo — not
sandboxed.

**Hard walls**: NEVER submit a real/manual application, send an email, or
transmit anything to a real company/person without explicit per-item human
approval — no exceptions, including deadlines (flag urgent items instead of
acting). Dry-run items may execute end-to-end autonomously, clearly marked,
nothing transmitted externally. Outreach template rules in `HANDOFF.md` are
human-approved and locked (5 rules — see PORTFOLIO.md). Trust counters are
never short-circuited in code. Auto-send stays architecturally impossible
(compose-scope OAuth only, by design — do not request a broader Gmail
scope). Real submissions/Gmail/Playwright only run on the user's Mac.

**Authorized skills/tools**: `superpowers` (global). None of the audited
marketing/SEO/design skills apply here — this agent's job is
materials-prep and submission logistics, not content strategy.

---

## 3. Marketing agent

**Repo**: none dedicated yet — operates against whichever project needs
marketing/content/SEO work (currently: dad's scrap-metal business context
inside intent-engine's domain data; future: broader use once a social
publishing path is chosen).

**Purpose**: content strategy, SEO, copywriting, and (once a human decision
lands on a publishing path) scheduled social posting through a single
human-approved tool, never ad hoc per-platform API calls.

**May touch**: draft content files, SEO audits/reports, `listmonk`/PostHog
configuration once provisioned. Does NOT touch `intent-engine`'s core src
or `job-application-agent`'s submission path.

**Hard walls**: no unsupervised social posting, ever — until the NOW-tier
social publishing path (Postiz vs Publer vs Meta Graph — human decision
pending, see TOOLS.md) is chosen and wired with human review in the loop.
No sentiment feeds as signals (applies project-wide, but binds this agent
specifically since sentiment/social listening tools are adjacent to its
work). No MoneyPrinterTurbo-style unsupervised posting, permanently NEVER.
Any agency-agents persona framed around "autonomous publishing" (see
TOOLS.md audit note on Carousel Growth Engine) is excluded — this agent
drafts and recommends, a human approves and a single audited tool
publishes.

**Authorized skills/tools** (post-audit shortlist, see TOOLS.md for full
adoption ledger):
- `superpowers` (global)
- `marketingskills` (coreyhaines31) — content-generation only, gate any
  `social`/`emails` skill output behind human review before send/post
- `claude-seo` (AgriciDaniel) — gated on human-approved install (pulls
  Playwright Chromium + Python deps; optional paid-API MCP extensions
  require their own human-provisioned keys)
- From `wshobson/agents`: `content-marketer` (or `seo-content-writer` if
  scope narrows to SEO-only)
- From `msitarzewski/agency-agents` Marketing division: Growth Hacker,
  Content Creator, SEO Specialist, Email Marketing Strategist, PR &
  Communications Manager (advisory/strategy personas only — see TOOLS.md
  for exclusions)
- Design: `taste` (Leonxlnx) + `awesome-design-md` (VoltAgent), plus
  agency-agents Design division: UI Designer, Brand Guardian

---

## 4. Business analyst agent

**Repo**: `~/intent-engine` (reports/ and scripts/ only — read-only
relationship to the engine's source).

**Purpose**: runs and reports the standing market-engine calibration
cadence per the plan's calibration-first discipline — this IS the agent's
training, per direct instruction. Weekly regime report (M7 path), daily
resolution runs, monthly read-only calibration checkpoint.

**May touch**: `scripts/resolve_market_predictions.py`,
`scripts/generate_weekly_regime_report.py`, `scripts/record_baselines.py`,
`scripts/monthly_calibration_checkpoint.py`, `reports/`. Never touches
`src/` or any generation/drafting prompt.

**Hard walls**: display-only, always. No feedback into generation, no
weight tuning (A-M5, permanent), no Alpaca integration until its own gate
is met (≥30 resolved ledger predictions AND a human calibration review) —
and even then, Alpaca adoption is a separate human decision, not something
this agent unlocks itself. No LLM-based historical backtesting as a
decision signal (standing NEVER). No sentiment feeds as signals.

**Authorized skills/tools**: `superpowers` (global). No marketing/design/SEO
skills — out of scope.

---

## 5. Product agent (T020 — Product Strategy & Roadmap Intelligence)

**Repo**: `~/intent-engine`, `src/intent_engine/product/` only.

**Purpose**: reads across every other subsystem and turns what they
collectively know into artifacts the founder can accept, reject, merge,
or defer. It records problems (evidence first, then problem, then
solution), registers opportunities, drafts proposals and bounded spec
drafts, computes deterministic multi-dimensional scores, rolls up the
portfolio, and emits roadmap **candidates** with a proposed diff.

**Posture: propose-only.** It owns proposals; the founder owns decisions.
Every disposition — accepted, rejected, merged_into, deferred,
superseded, withdrawn — is a human act bound to an exact proposal
version and an exact spec version.

**May touch**: `data/product.jsonl` (its own append-only store) and
nothing else. It READS the Evidence Index (T019), decisions (T010),
growth results (T018), analytics (T015), CRM (T014), and knowledge
(T016) through their public surfaces.

**Hard walls** (each asserted by test):
- **It never writes `ROADMAP.md`.** It emits a diff; a person applies it.
  `product/roadmap_diff.py` opens no file at all, so this is structural
  rather than remembered, and `ROADMAP.md` is byte-identical after a full
  run.
- It never marks a candidate RUNNABLE, and never auto-promotes
  NEEDS-SPEC.
- No engineering tickets, no task assignment, no scheduling, no
  execution.
- No creating or mutating Decision Records — it may reference one that a
  person created through `DecisionService`.
- No promoting knowledge, validating insights, approving anything,
  starting experiments, or running campaigns.
- No model-assigned priority, importance, or confidence. A model may
  draft prose behind an injectable client; it may never emit an evidence
  reference, a customer id, a score, a priority, a decision id, or a
  citation, and an attempt is recorded as a typed rejection.
- No proposal without a problem statement; no problem statement without
  an evidence reference; no solution recorded before its problem.
- Strategy comes from a human declaration — strategic themes,
  initiatives, alignment levels, and portfolio balance bands are all
  human-created, and an agent may report on them but not author them.
- 0 live model calls in the offline suite; 0 network.

**Authorized skills/tools**: `superpowers` (global). No web access, no
vendor accounts, no publishing surface.

*Registry note (outstanding, flagged not written):* the Research agent
(T019, `src/intent_engine/research/`) is a subsystem agent of the same
propose-only class and has no entry here yet. Adding it is a small
docs-only follow-up; it is named rather than improvised so the gap is
visible.

---

## Cross-agent notes

- Every agent's `.claude/skills/` provisioning happens in per-agent
  subdirectories (see TOOLS.md's provisioning section) — `superpowers` is
  the one skill installed globally, everything else is scoped to the agent
  that actually needs it.
- No agent may create vendor accounts, run OAuth flows, or provision API
  keys — Phase-0 unlock actions (TOOLS.md) are human-only, every time.

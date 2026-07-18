# TOOLS.md — tiered adoption ledger

*Workstream 1. Records tooling decisions as already made (per standing
instruction — not relitigated here), plus this session's audit findings for
the skill/agent packs that needed review before provisioning. Every skill
below was fetched and read as UNTRUSTED text and evaluated against this
project's hard walls before any provisioning decision.*

---

## NOW

| Tool | Status | Notes |
|---|---|---|
| One social publishing path | **Decided: Publer** (2026-07-17) | API key provisioned to `intent-engine/.env` as `PUBLER_API_KEY` — provisional location (see note below); nothing actually posts yet, no marketing-agent code exists to consume it. |
| listmonk | NOW | Self-hosted newsletter/mailing list — human sets up instance + credentials. |
| PostHog | NOW | Analytics — human provisions project + API key. |
| superpowers | NOW, global | Installed at the global `.claude/skills/` level (see Provisioning below) — audited this session, no conflicts found, strong alignment with park-don't-improvise/TDD discipline. |
| Curated marketing/SEO skills, post-audit | NOW (shortlist below) | See Audit section — specific skills/subagents approved, not the full raw repos. |

## LATER (explicit unlock gate)

| Tool | Gate |
|---|---|
| Gladia | Supervised voice-path task exists first. |
| Telnyx | Real telephony need exists first. |
| Playwright-MCP | Browser automation need exists first (note: `job-application-agent` already uses Playwright directly, not via MCP — that's a separate, already-authorized real capability, not this gate). |
| Crawl4AI OR Firecrawl (one only) | Graph-population phase (Pillar 1 causal graph, news/filings ingestion) — not started; `claude-seo`'s optional Firecrawl MCP extension inherits this same gate if ever enabled. |
| TimesFM + Kronos | Part C-M baseline conditions met. |
| Higgsfield | Human-reviewed video workflow exists first. |
| Alpaca | ≥30 resolved ledger predictions AND human calibration review — currently 0 resolved (see `reports/market_engine_trace.md`), nowhere near this gate. |
| Supabase | Multi-user need exists first. |
| Langflow | Visual MCP pipeline need exists first. |

## NEVER

| Item | Reason |
|---|---|
| Increase / banking rails for agents | No agent gets financial-transaction capability, permanently. |
| ruflo / swarm orchestration inside intent- or market-engine repos | Standing architectural decision — single-agent, deterministic-bar discipline, not a swarm. |
| Sentiment feeds as signals | Standing decision — not a data source for any prediction/generation path. |
| MoneyPrinterTurbo unsupervised posting | Direct conflict with no-unsupervised-posting rule. |
| LLM historical backtesting (A-M3) | Permanent overfitting guard — no rule/threshold is ever tuned against historical outcomes. |

---

## Audit — external skill/agent packs (untrusted until reviewed)

Fetched and read this session (not installed). Each entry: what it is, any
conflict with this project's hard walls, verdict.

**marketingskills** (`coreyhaines31/marketingskills`) — 46 markdown
content-strategy skills, no execution/network capability. No inherent
conflict; gate `social`/`emails` skill *outputs* behind human review before
any send/post action (the skill itself doesn't send anything). **Adopt.**

**claude-seo** (`AgriciDaniel/claude-seo`) — 25 sub-skills + 18 sub-agents,
`install.sh` pulls Python deps + Playwright Chromium; optional paid-API MCP
extensions (DataForSEO, Firecrawl, Ahrefs, etc.) need the user's own
credentials, human-provisioned. **Real conflict**: auto-installs external
dependencies — this project requires explicit human approval before any new
dependency. **Adopt, but gate the install step itself on human approval**;
the skill logic (deterministic scoring, falsifiability checks) is otherwise
sound.

**obra/superpowers** — TDD/planning methodology skills
(`brainstorming`, `writing-plans`, `test-driven-development`,
`subagent-driven-development`, etc.). No conflicts found — already
implements park-don't-improvise and verification-before-completion.
**Adopt globally.**

**wshobson/agents** — 184+ subagent personas across 25 categories.
**Real conflict**: `quant-analyst` and `risk-manager` (Finance category)
are framed around trading strategies and portfolio risk — directly abuts
the no-autonomous-financial-action and no-backtesting-as-signal rules.
**Exclude those two specifically.** Shortlist adopted (max 3-4, per
instruction): `python-pro`, `data-scientist`, `test-automator`, and
`content-marketer` (or `seo-content-writer` if scope narrows to SEO-only —
human's call at provisioning time).

**taste** (`Leonxlnx/taste-skill`) — pure markdown design-taste guidance,
no execution. No conflicts. **Adopt.**

**UI-UX-pro-max** (`nextlevelbuilder/ui-ux-pro-max-skill`) — heavier
footprint (npm CLI + local Python BM25 search + CSV taxonomy), functionally
redundant with `taste` for the same "avoid generic AI UI" goal, plus
embedded premium-tier upselling in its own output. No hard-wall conflict,
but **not adopted** — redundant, not because it's unsafe.

**awesome-design-md** (`VoltAgent/awesome-design-md`) — static corpus of
70+ real-brand `DESIGN.md` token files. No conflicts, genuinely
non-overlapping with `taste` (reference corpus vs. generative principles).
**Adopt.**

**msitarzewski/agency-agents** — audited via the uploaded `AGENCY
Guide.pdf` plus a direct fetch of the actual GitHub repo (the PDF itself is
promotional material with affiliate links to a paid community —
treated as untrusted marketing copy, not neutral documentation; its claim
of the repo's popularity was independently checked against the live page
rather than taken at face value, and the number is implausibly high for a
repo this size/niche — **do not treat star count as a trust signal for
this repo; it was evaluated on content alone**). 147+ agent personas,
16 divisions, MIT-licensed, markdown-only (no execution capability beyond
whatever the persona instructs the host session to do).
**Real conflict found**: the Marketing division's "Carousel Growth Engine"
agent is explicitly described as doing "autonomous publishing" —
direct conflict with the no-unsupervised-posting rule. **Excluded.**
Several other Marketing-division agents (Twitter Engager, TikTok
Strategist, etc.) describe "real-time engagement" — adopted personas from
this set are treated as strategy/draft-only, never wired to actual posting
credentials, same as every other marketing skill here.
Per the side-task instruction (marketing/design divisions only, max 5-8
agents total): **shortlist adopted** —
Marketing: Growth Hacker, Content Creator, SEO Specialist, Email Marketing
Strategist, PR & Communications Manager.
Design: UI Designer, Brand Guardian.
(7 total, under the 5-8 cap.)

---

## Provisioning (this session)

Per-agent `.claude/skills/` directories, `superpowers` installed globally:

- **intent-engine agent** (`~/intent-engine/.claude/skills/`): `superpowers` only (inherited from global).
- **personal assistant agent** (`~/job-application-agent/.claude/skills/`): `superpowers` only (inherited from global).
- **marketing agent**: no dedicated repo yet — skills recorded here as
  *approved for provisioning* (`marketingskills`, `claude-seo` gated,
  `taste`, `awesome-design-md`, the `wshobson/agents` and
  `msitarzewski/agency-agents` shortlists above) but not physically copied
  anywhere, since there's no target directory for this agent until one
  exists. Provision at the point a marketing-agent workspace is created.
- **business analyst agent**: `superpowers` only (inherited from global);
  no marketing/design/SEO skills, out of scope per AGENTS.md.

None of the raw external repos (`claude-seo`, `wshobson/agents`,
`msitarzewski/agency-agents`, etc.) were cloned or installed this session —
only read via web fetch for the audit above. Actual installation
(`git clone` + `install.sh`, or `npx skills add`) is a human action, listed
below.

---

## Phase-0 human actions to unlock each NOW service

- **Social publishing path**: **done** — Publer chosen, `PUBLER_API_KEY`
  added to `intent-engine/.env` (2026-07-17), confirmed gitignored
  (`git check-ignore -v .env`). **Standing placement, per direct
  instruction (2026-07-17)**: `intent-engine/.env` is the permanent home
  for this key, not a temporary one — when the marketing-agent workspace
  is created, it reads `PUBLER_API_KEY` from this same file rather than
  getting its own copy. intent-engine's own code has no reason to read
  this variable itself; it just holds it as the project's one shared
  secrets store.
- **listmonk**: stand up the instance (self-hosted), create an admin user,
  add `LISTMONK_URL`, `LISTMONK_USERNAME`, `LISTMONK_PASSWORD` (or API
  token if using token auth) to `.env`.
- **PostHog**: create a project at app.posthog.com (or self-host), copy the
  project API key, add `POSTHOG_API_KEY` and `POSTHOG_HOST` to `.env`.
- **superpowers**: `git clone` the repo and run its installer to place
  skills under the global `.claude/skills/` directory — no API key needed,
  but the install step itself is a human action (Cowork's sandbox can only
  read external repos via fetch, not clone+install into the real
  filesystem's global skills directory).
- **marketingskills**: `npx skills add` (or plugin marketplace install) —
  no API key needed, content-only skill.
- **claude-seo**: `git clone`, review `install.sh` before running (per this
  audit's gate), then run it — installs Python deps + Playwright Chromium
  locally. Optional: create accounts + API keys for any of DataForSEO /
  Firecrawl / Ahrefs / SE Ranking / Profound / Bing Webmaster / Banana if
  those extensions are wanted later (each is its own separate decision,
  stored under `~/.config/claude-seo`, not this repo's `.env`).
- **wshobson/agents shortlist**: copy just the 4 approved subagent `.md`
  files into the marketing agent's `.claude/agents/` once that workspace
  exists — no API key needed.
- **msitarzewski/agency-agents shortlist**: copy just the 7 approved
  Marketing/Design `.md` files (not the full 147-agent install) into the
  marketing agent's `.claude/agents/` once that workspace exists — no API
  key needed.
- **taste / awesome-design-md**: copy skill files in — no API key needed.

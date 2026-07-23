# V2.0 — Extraction and reuse audit (mandatory, before coding)

Verdict: the Studio is **orchestration only**. Every heavy capability
already exists; nothing is rebuilt. No replacement subsystem is created.

| Capability | Marketing existing surface | Growth existing surface | Reuse directly | Adapter needed | Missing |
|---|---|---|---|---|---|
| Campaigns | `create_campaign`, `archive_campaign`, state machine | — | YES | read adapter for portfolio index | — |
| Briefs | `create_brief`, `revise_brief`, `get_brief` | — | YES | none | — |
| Drafts | `create_draft`, `revise_draft`, `revalidate_draft` | — | YES | none | — |
| Claims review | `request_claim_review`, `approved_claim_ids` | — | YES | none | — |
| Quote consent | marketing evidence gates | — | YES | none | — |
| Audience selection | `define_audience` | — | YES | none | — |
| Events | append-only `MarketingRow` store | append-only `GrowthEvent` store | YES | none | — |
| Growth experiments | — | full: hypothesis, arms, metric, guardrails, randomization, stopping rules, registration approval, interim reads, review | YES | read adapter for experiment portfolio | — |
| Analytics observations | `record_performance_observation`, `observation_ratio` | `record_observation`, `statistics` | YES | none | — |
| CRM lifecycle | — (CRM subsystem) | `assign_entity`/`exclude_entity` against CRM ids | YES | none | — |
| Feedback | `link_feedback` | `record_review` | YES | none | — |
| Existing CLIs | `marketing` CLI | `growth` CLI | YES | Studio adds its own thin CLI | — |
| Stores and snapshots | marketing store | growth store + snapshots | YES | none | — |
| Product events (funnel) | — | — | YES (T023.5 `fi.telemetry_event`) | read adapter (never rewrites raw events) | — |
| Daily briefing | — | — | — | — | NEW (thin: composes reads) |
| Learning memory | — | — | — | — | NEW (append-only, human-accepted only) |
| Loop state machine | marketing state (campaign) | growth state (experiment) | partial | — | NEW (thin: references both) |
| Channel policy walls | banned-language scan exists | — | partial | — | NEW (channel-specific checks) |

New code therefore = loop states + briefing + learning acceptance +
channel policies + fixture + adapters. All heavy machinery (experiment
science, claim gates, draft revision, approval flows) is reused as-is.
Studio records store **references** (campaign_id, experiment_id,
claim ids), never copies of Marketing/Growth records.

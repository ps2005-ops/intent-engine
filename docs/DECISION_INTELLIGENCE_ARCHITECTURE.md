# Decision Intelligence — the top-level architecture

*Written 2026-07-20 from the founder's architecture note. This is the
organizing concept that sits **above** the engineering, marketing, and
growth systems already built. It renames nothing and rewrites no code —
it gives every existing component and every future agent a defined place,
so new work becomes an application on one platform rather than a separate
AI project.*

---

## The one-sentence framing

> Everything here exists to help someone make a better decision — and to
> be held accountable for whether it did.

That second clause is what makes this a platform rather than a report
generator. A decision that is never graded is a story. The prediction
ledger is what converts advice into a record.

## The platform

```
Decision Intelligence Platform
│
├── Business Analyst Engine          src/intent_engine/simulator/
│                                    extraction, risk audit, scenarios
├── Prediction Ledger                src/intent_engine/core/prediction_ledger.py
│                                    append-only, code-graded, public
├── Evidence & Mechanism Library     mechanisms.json + core/regime_report.py
│                                    cited historical episodes, deterministic match
├── Report Generator                 scripts/render_founder_report.py
│                                    productized PDF + founder HTML
├── Marketing & Content Engine       marketing/content_engine/
│                                    one analysis -> many drafts, approval-gated
├── Growth & CRM System              marketing/crm/ (C5, specced)
│                                    append-only lifecycle + funnel
├── Personal AI (Decision OS)        future — same loop, personal decisions
└── AgentOS                          future — scheduling/orchestration layer
```

Every box above is either built and tested today, or specced with a
definition-of-done in `PLAN_2026-07-21.md`. Nothing here is aspirational
branding: the tree is a map of the repo.

## Why this framing earns its place

1. **It makes the next feature obvious.** A Sales Agent, Investment
   Agent, or Product Manager Agent is not a new product — it's a new
   *application* that reuses the same four primitives: evidence,
   mechanism match, scenario framing, ledgered claim.
2. **It makes the walls global.** The publish wall, the claim wall
   (≥30 resolved per source + founder calibration review), append-only
   discipline, and honesty markers are properties of the *platform*, not
   of any one script. Any new application inherits them or doesn't ship.
3. **It explains the ledger to outsiders.** "We grade ourselves in
   public" is the product, not a compliance detail.

## The decision workspace loop

The report is one pass through a loop, not a terminal artifact:

```
Today's Decision
      ↓
   Evidence            (facts, separated from inference)
      ↓
 Recommendation        (a decision framework — conditions, not a forecast)
      ↓
   Watch List          (metrics + "what would change this")
      ↓
 Decision Journal      (what was decided, and on what basis)
      ↓
   Outcome             (90 days later, on the resolve-by dates)
      ↓
  Calibration          (code-graded; feeds the public ledger)
```

**Where the loop stands today** — honest status, no roadmap inflation:

| Stage | Status |
|---|---|
| Today's Decision | built (simulator CLI / founder intake) |
| Evidence | built — facts and inference now rendered separately |
| Recommendation | built — boxed decision framework in the PDF |
| Watch List | built — Metrics to watch + What would change this |
| Decision Journal | **not built** — the report is currently a snapshot |
| Outcome | built — ledger rows resolve on their dates |
| Calibration | built, **gated** — 0 resolved today; no accuracy claimed |

The one genuine gap is the Decision Journal: the artifact that makes a
report a living document rather than a PDF someone files. That is the
highest-value next build in this direction, and it slots naturally
alongside C4 (feedback loop) — both write append-only rows keyed to a
decision.

## What does not change

- **Claims stay last and stay gated.** Nothing in this framing licenses
  an accuracy claim before ≥30 live-resolved predictions per source plus
  the founder calibration review.
- **Generation is automated; publication and claims are not.**
- **Tone stays restrained.** The report's credibility comes from what it
  refuses to say. No conversational fluff, no emoji, no padding — a
  platform framing must not become a licence to inflate the language.
- **Marketing never edits engine `src/` generation prompts** (AGENTS.md §3).

## Where this lands in the existing docs

- `ROADMAP.md` remains the task-level source of truth.
- `marketing/MARKETING_PLAN_V2.md` remains the marketing strategy of record.
- This file is the *structural* frame both hang from — read it first when
  deciding **where** a new capability belongs, then use the other two to
  decide **when** it gets built.

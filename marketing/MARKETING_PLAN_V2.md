# Marketing Plan v2 — the launch redesign

*Supersedes the scattered v1 (README.md + drafts/ + outreach/) as the
strategy of record. Written 2026-07-20 to be executed by Fable 5 starting
2026-07-21 (see `PLAN_2026-07-21.md` at repo root for the task queue).
v1 was ~80–85% of a launch plan; this closes the missing 15–20%:
distribution, productization, feedback loops, and automation.*

---

## The one-sentence change

**v1 assumed marketing begins after validation. v2 splits that in two:**

> **Claims begin after validation. Marketing begins immediately.**

Nothing about the honesty discipline relaxes. What changes is that we stop
waiting until November to have a public presence. We build audience,
distribution, and a real funnel *now*, on expertise and transparency —
and we still don't assert predictive accuracy until the ledger earns it.

## Keep exactly as decided (do not touch)

These four are genuinely differentiating and stay verbatim:

1. **Claim tracing** — every capability/performance claim carries an
   inline `[T:n]` trace to a gate-passed capability or a ledgered fact.
   Very few AI startups can say every claim links to evidence. Keep.
2. **The prediction ledger** — append-only, code-graded. **Change from
   v1: make it public from day one** instead of hiding it until November.
   People like watching things develop; the young ledger *is* the honest
   artifact. Publishing a prediction is not a claim of accuracy.
3. **Honesty markers** — `NONE MATCHED`, `UNAVAILABLE`, `NOT ENOUGH
   DATA`, `UNKNOWN`. Trust builders. Keep, render always.
4. **Dry-run publishing** — `publer_pipeline.py` stays dry-run until the
   founder creates `PUBLISHING_ENABLED`. Automate generation; never
   automate the publish click. Keep.

## The governing principle for everything new

> **Automate generation. Gate publication and claims.**

Every automation below produces a *draft into an approval queue*. The two
walls are untouched and are the only manual steps that matter:

- **Publish/send wall**: nothing posts or emails without per-item founder
  approval + the `PUBLISHING_ENABLED` flag (`publer_pipeline.py`,
  `marketing/outreach/approval_checklist_template.md`).
- **Claim wall**: no predictive-accuracy claim anywhere until **≥30
  live-resolved predictions per source AND the founder calibration
  review** (A-M5). Public ledger/leaderboard show *raw rows* + "too few
  resolutions to claim calibration," never a derived accuracy number.

If a new feature can't route through those two gates, it doesn't ship.

---

## Phase 1, redesigned

v1 flow:

```
Research → [wait until November] → Marketing
```

v2 flow:

```
Research → Content → Users → Community → Validation → Claims
                                             │           │
                                     (ledger matures) (≥30 resolved
                                                       + review)
```

Marketing has already started. Claims are still last, and still gated.

---

## 1. One content engine (not six channels)

Stop treating landing page / LinkedIn / newsletter / blog / X / YouTube as
separate surfaces. They are all *renders of one object*.

**The core object** already exists in the engine — a structural analysis /
weekly regime read / prediction, produced by `src/intent_engine/core/
regime_report.py`, `prediction_ledger.py`, and `scripts/
render_founder_report.py`. Normalize it into one `ContentSource` record:

```
Analysis → Evidence → Mechanisms → Prediction → Summary
```

From that one object, generate (as drafts):

```
Website article   LinkedIn post   X thread     Newsletter issue
Video script      Podcast outline GitHub example  PDF report
Founder email
```

**One analysis → eight-plus assets, no extra authoring.** Build target:
`marketing/content_engine/render.py` — pure functions
`source -> {asset_type: draft}`, each carrying the shared `[T:1..T:6]`
trace table, each written to `marketing/content_engine/drafts/<date>/` for
approval. Zero network, zero publish. Reuses the existing report renderer;
never invents facts not in the source object.

## 2. Marketing is event-driven, not calendar-driven

v1: "Monday → write a post." v2: the *event* triggers the drafts.

```
Prediction created (ledger append)
        │
        ▼
Content generated (content_engine)  →  Approval queue  →  [human] Publish
```

Every ledger append fans out to a fixed artifact set — all drafts, all
queued, none published:

```
Prediction ─┬─ ledger row (exists today)
            ├─ markdown page (site content)
            ├─ SEO page (structured, indexable)
            ├─ newsletter draft
            ├─ LinkedIn draft
            ├─ X thread draft
            ├─ founder summary
            ├─ GitHub example
            └─ internal analytics event
```

Build target: a post-append hook in `prediction_ledger.py` (or a watcher
over the ledger file) that calls the content engine. **No extra human
work per prediction** beyond the approval skim that already exists.

## 3. Productize the report (make it feel like McKinsey)

Don't send raw markdown. The founder-facing deliverable becomes a
structured PDF:

```
Executive Summary → Decision → Mechanisms → Evidence → Contradictions
→ Scenario tree → Metrics to watch → 90-day checklist → Prediction → PDF
```

Build target: extend `scripts/render_founder_report.py` to emit this
section set and render to PDF (use the repo's `pdf` skill / a headless
renderer). Honesty markers render in every section; the "what we could not
verify" block is mandatory, not conditional. Layout follows the existing
`docs/report_mockup/` house style.

## 4. A feedback loop on every report

Every delivered report ends with a short, auto-stored survey:

```
Was this useful? (1–5) → What was wrong? → What surprised you?
→ Would you pay? → Can we quote you?
```

Build target: `marketing/feedback/` — append-only `feedback.jsonl` (same
discipline as every ledger here), one row per response, metrics computed
by code. "Can we quote you? = yes" is the only path that unlocks a
testimonial (still per-item founder approval before it appears anywhere).

## 5. A lightweight CRM (the biggest v1 gap)

v1 had outreach drafts but no pipeline. Add a real one, built on the
outreach ledger discipline already specced
(`marketing/outreach/tracking_ledger_schema.md`).

Prospect lifecycle:

```
Prospect → Contacted → Interested → Report generated → Meeting
→ User → Referral → Advocate
```

Founder funnel (the real one):

```
Waitlist → Free report → Feedback → Updated report → Invite
→ Case study → Referral
```

Build target: `marketing/crm/` — append-only `crm.jsonl` keyed by
`prospect_id`, states as above, reads collapse to latest row. Every
interaction (draft, approval, send, reply, report delivered, feedback,
conversion) writes a row. Metrics (contacted→interested→user rates,
per-variant, per-segment) computed by code, never hand-tallied. No scraped
bulk lists; real research only (v1 rule, unchanged).

## 6. Commit-triggered content (build in public)

Nobody does this well — so do it:

```
Git commit → summarize → generate changelog → LinkedIn draft
→ X draft → approval queue
```

Build target: a `post-commit` hook (or a nightly `git log` walker) →
`marketing/content_engine/from_commits.py` → drafts to the same approval
queue. Turns engineering progress into distribution for free. Drafts only;
publish stays gated.

## 7. Distribution: publish expertise weekly, starting now

Don't wait to "build an audience." Ship a weekly evergreen series that
sells nothing:

```
Business Breakdown #N → "Why <company> ..." → Mechanisms → Evidence
→ Prediction → Ledger link
```

Sourced 1:1 from the cited mechanism library (`mechanisms.json`) and real
weekly runs. This is Format B/A from v1, promoted to the spine of
distribution. No product pitch, just the analysis and the public ledger
link.

## 8. New pages = SEO assets (not just Landing/Pricing/About)

Add pages that are content, compounding, and indexable:

```
Predictions   Case Studies   Mechanism Library   Research
Changelog     Leaderboard
```

- **Predictions** — the live public ledger view (rows + honesty markers,
  no accuracy claim until the gate clears).
- **Leaderboard** — our predictions vs. the dumb baselines we must beat,
  shown honestly once resolutions exist; until then, "too few resolved."
- **Mechanism Library** — the cited catalogue (evergreen SEO).
- **Case Studies / Research / Changelog** — generated from the content
  engine and commit feed.

## 9. A public roadmap (Linear-style)

People like watching progress:

```
Done │ In Progress │ Testing │ Next │ Ideas
```

Auto-generated from `ROADMAP.md` + the task queue, published as a page.
Drafts to approval queue like everything else.

---

## The end-to-end pipeline (how it runs like a SaaS company)

```
Website Form
      │
      ▼
Lead Database (CRM)
      │
      ▼
Qualification
      │
      ▼
Intent Engine  ──►  Structural Analysis
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
      Prediction Ledger          PDF Report
              │                       │
              ▼                       ▼
      Content Generator          Founder Email
              │                       │
              └──────────►  Approval Queue  ◄──┘
                                 │
                                 ▼   [human approves]
                              Publish
                                 │
                                 ▼
                             Analytics
                                 │
                                 ▼
                          Follow-up Automation
                                 │
                                 ▼
                        Case Study / Referral
```

**Manual steps kept — deliberately, forever or until the founder flips
them:**

- Approving outbound emails.
- Approving social posts (until comfortable — `PUBLISHING_ENABLED`).
- Reviewing customer-specific reports before they're sent.
- Making any predictive-performance claim (gated on ≥30 resolved +
  calibration review).

**Everything else is automated**: report generation, CRM updates, draft
creation, analytics, reminders, content repurposing, changelog.

---

## Priorities from today to mid-August

Stop adding engine research features unless they directly improve the
founder report. The technical base is mature (live prediction logging,
eval underway). Spend the remaining time on four things, in order:

1. **Polished founder-facing experience** — submit a decision → receive a
   beautiful productized PDF report. (§3)
2. **The content engine** — one analysis → many reusable assets. (§1, §2)
3. **Lightweight CRM + outreach workflow** — every interaction tracked and
   followed up. (§5)
4. **Operations pipeline** — automate everything except approval and
   scientifically-gated claims. (the diagram above)

## What stays true from v1 (unchanged walls index)

- Publer is the single publishing tool; dry-run until `PUBLISHING_ENABLED`.
- Per-message outreach approval + append-only tracking ledger.
- Claim-trace table `T:1–T:6` on every asset; zero accuracy claims today.
- No sentiment feeds as signals; no agent-created vendor accounts/OAuth.
- Marketing agent never touches intent-engine core `src/` or the
  job-application submission path (AGENTS.md §3).

## Claim-trace note

Every asset the content engine emits inherits the v1 trace table
(`marketing/drafts/landing_page_copy.md`, T:1–T:6). The only performance
statement permitted anywhere remains the explicit disclaimer that no
accuracy is claimed. This is asserted by the same audit the outreach
checklist uses.

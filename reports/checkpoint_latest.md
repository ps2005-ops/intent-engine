# CHECKPOINT — 2026-07-17 (Cowork session)

*2-minute read. Anything awaiting your approval is always at the top.*

---

## ⏳ AWAITING YOUR APPROVAL / ACTION

1. **Job applications — 20 items prepared-awaiting-approval**, packets
   built, sitting in the review UI (`~/job-application-agent`,
   `scripts/review.sh`). Nothing sent or submitted. Full list:
   `applications/APPLICATION_LEDGER.md`.
2. **Gmail OAuth token expired** (`invalid_grant`) — blocks new outreach
   drafts. Re-auth (`gmail_token.json`/`gmail_compose_token.json`,
   compose-scope) before any further packet prep, or it'll just accumulate
   more failed drafts.
3. **intent-engine git lock files still present** — `.git/index.lock`,
   `.git/HEAD.lock`, `.git/objects/maintenance.lock`,
   `.git/refs/heads/main.lock`. Run this on the Mac before any new commit
   in that repo (working tree already matches HEAD, verified — this just
   rebuilds the stale index):
   ```
   cd ~/intent-engine && rm -f .git/index.lock .git/HEAD.lock .git/refs/heads/main.lock .git/objects/maintenance.lock && git reset
   ```
4. **Lever adapter unverified on a real page** — before the 29-item
   adapter batch (real Playwright submissions) runs, verify one real Lever
   screenshot first: `python scripts/batch_execute.py --only adapter
   --limit 10 --yes` (your call to run it, not run this session — it
   submits for real).
5. **Cron/Task Scheduler entries below** — installing these is your call;
   I didn't set any schedule.
6. **Social publishing path** — still an open human decision (Postiz vs
   Publer vs Meta Graph), blocks the marketing agent's NOW-tier tooling.
7. **Task 3's park** (mechanism-extraction ambiguous-case gate, intent-engine) —
   your read needed: flawed test case, or does the extraction schema need a
   more prominent "insufficient evidence" escape hatch? Gates Task 4.

---

## What finished this session

- **Market engine (Workstream 2)**: verified M5-M9 all DONE (commits
  `45428e0`, `6b7242c`, `01800d7`, `5e0e30b`, `1019949` — no work needed,
  queue was already complete). Ran the daily resolve cadence for the first
  time (`scripts/resolve_market_predictions.py` — correct no-op, nothing
  due yet). Built `scripts/monthly_calibration_checkpoint.py` (new,
  read-only, display-only per A-M5 — verified it runs clean, currently
  0 resolved predictions in every source). Offline suite reconfirmed
  green: 557 passed.
- **Cadence recommendation (Workstream 2)**, exact commands to install
  yourself:
  - Daily resolve, 6am: `0 6 * * * cd /Users/prathamsharma/intent-engine && .venv/bin/python scripts/resolve_market_predictions.py >> logs/resolve_market_predictions_$(date +\%Y-\%m-\%d).log 2>&1`
  - Weekly regime report, Monday 8am (needs fresh real headlines by hand
    each week — see `market_engine_trace.md`'s own caveat, not a literal
    unattended cron candidate yet): `0 8 * * 1 cd /Users/prathamsharma/intent-engine && .venv/bin/python scripts/generate_weekly_regime_report.py --entity-id "macro-watch" --headline "<real headline>" --headline "<real headline>" --output "reports/weekly_regime_report_$(date +\%Y-\%m-\%d).txt" && .venv/bin/python scripts/record_baselines.py --entity-id "macro-watch" >> logs/weekly_regime_$(date +\%Y-\%m-\%d).log 2>&1`
  - Monthly checkpoint: no auto-schedule recommended yet — run
    `python scripts/monthly_calibration_checkpoint.py` by hand once a
    month; it's read-only and cheap (0 API calls), no urgency to automate
    until there's real resolved data to show.
- **Workstream 3**: `docs/PORTFOLIO.md` created — full per-project status
  for both repos.
- **Workstream 4**: `applications/APPLICATION_LEDGER.md` created — backlog
  snapshot (410 total: 29 adapter / 381 manual), the 20
  prepared-awaiting-approval items, historical real submissions (18,
  pre-dating this session, human-approved), blockers. Nothing submitted or
  sent this session.
- **Workstream 1**: `docs/AGENTS.md` and `docs/TOOLS.md` created. Audited
  9 external skill/agent resources (untrusted-until-reviewed): 7 from the
  original list plus `msitarzewski/agency-agents` (added mid-session per
  your request, cross-checked against the uploaded promotional PDF and the
  live repo directly — the PDF's ~129k-star claim was verified against the
  real page and is treated as an unreliable/inflated signal, evaluated on
  content instead). One real conflict found and excluded: agency-agents'
  "Carousel Growth Engine" persona explicitly describes autonomous
  publishing. One conflict found and gated, not excluded:
  `wshobson/agents`'s `quant-analyst`/`risk-manager` (trading-strategy
  framing) — excluded from adoption. `claude-seo`'s installer pulls new
  dependencies — gated on human approval before install. Full shortlist in
  `docs/TOOLS.md`.

## What parked and why

- **intent-engine commits**: none attempted this session — the git
  index/lock corruption (see ⏳ #3) makes `git add`/`git commit` unsafe
  right now. Nothing needed committing anyway (the resolve run was a
  no-op; the new docs/script are intentionally left uncommitted until the
  lock clears).
- **job-application-agent packet prep for 361 remaining manual-path
  items**: parked behind the Gmail OAuth fix (⏳ #2) — running more packets
  now would just add more `gmail-draft-error` rows.
- **Adapter batch (29 real-submission items)**: parked behind Lever
  verification (⏳ #4) and your explicit approval — never run with `--yes`
  on a real-submission path without it.
- **Task 3 mechanism-extraction gate**: parked in a prior session, still
  open (⏳ #7) — restated here since it gates Task 4.

## Spend since last checkpoint

- Market engine: 0 DATA calls (nothing due to resolve), 0 MODEL calls.
- Job-application-agent: 0 new calls — no scripts run against real
  services this session, only read existing state.
- Workstream 1 audit: web search/fetch only (no billed API spend against
  either repo's budget).

## Next 3 queued actions per workstream

- **Workstream 1**: none queued — audit complete pending your Phase-0
  actions (see `docs/TOOLS.md`) and, once the marketing agent has an
  actual workspace, physically provisioning the approved skill shortlist
  into it.
- **Workstream 2**: (1) install the daily/weekly cron entries if you want
  them automated, (2) decide Task 3's park, (3) spec at least one new
  RUNNABLE roadmap task once Task 3 is resolved.
- **Workstream 3**: none queued — PORTFOLIO.md is current as of this
  checkpoint; next update is the next checkpoint.
- **Workstream 4**: (1) re-auth Gmail, (2) approve/reject the 20 prepared
  items, (3) decide on the Lever-verification + adapter-batch step.

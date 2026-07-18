# PORTFOLIO — cross-project status

*Standing doc, Workstream 3. Updated at every checkpoint. This file records
status — it does not reorganize, rename, or restructure anything. Written
2026-07-17, Cowork session.*

---

## intent-engine (`~/intent-engine`)

**Current phase**: causal-engine pillar build (calibration + mechanisms +
graph v0), Part B of `overnight-execution-plan.md`, largely complete;
roadmap queue (`ROADMAP.md`) drained of RUNNABLE tasks. Market-engine
extension (`market-engine-execution-plan.md`, tracked in
`reports/market_engine_trace.md`) M1-M9 all DONE — standing cadence
(daily resolve, weekly regime report, monthly calibration checkpoint) now
established this session.

**Last commit**: `84639c2` ("Update real-roadmap picker test: queue
drained... empty set + None") — verified via `git log`/`git show`, content
matches HEAD.

**Open parks**:
- Part B **Task 3 — mechanism-extraction reliability gate: PARKED.** The
  deliberately-ambiguous test case stayed confidently unanimous even after
  a strengthened-instruction re-run (2 full rounds, 20/40 budget spent).
  Dependent Task 4 (wiring mechanisms into simulator output) correctly
  SKIPPED-DEPENDENCY, not attempted with a fallback.
- **`entity_id` normalization** — `prediction_ledger.py` doesn't normalize
  `entity_id` the way `entity_memory.py` does; same fragmentation risk that
  convention exists to prevent. Flagged, not fixed.
- **Git index/lock corruption** (found this session) — `.git/index.lock`,
  `.git/HEAD.lock`, `.git/objects/maintenance.lock`,
  `.git/refs/heads/main.lock` are still present from the Cowork sandbox's
  inability to unlink files. Working tree content matches HEAD (verified
  directly, byte-for-byte on the affected files) but `git status`/`git
  diff` report false modifications. **No commits were attempted this
  session** for this reason — see `reports/market_engine_trace.md`, Session
  4.
- 5 NEEDS-SPEC roadmap items (see `ROADMAP.md`): recipient-verb-gate
  revisit, `gmail_act` recipient resolution, multi-correction
  content-persistence gap, absorption-capacity `BusinessContext` field
  (explicitly excluded from autonomous execution regardless of spec
  completeness), 3 job-agent-sourced candidate diagnosis signatures,
  evaluation-stage build (deliberately excluded until a validation path
  exists).

**Next human gate**:
1. Run the git-lock cleanup one-liner on the Mac (see checkpoint —
   required before any new intent-engine commit):
   `cd ~/intent-engine && rm -f .git/index.lock .git/HEAD.lock .git/refs/heads/main.lock .git/objects/maintenance.lock && git reset`
2. Decide Task 3's park: flawed test case vs. a real need for a more
   prominent "insufficient evidence" escape hatch in the extraction schema.
   Gates Task 4 (mechanism rendering in the premortem).
3. Spec at least one new RUNNABLE roadmap task so the nightly loop
   (`nightly_agent.sh` + launchd, currently a safe no-op) has something to
   pick up again.

**Next agent task**: none queued (roadmap empty by design — never
auto-promote NEEDS-SPEC). Standing cadence (this session, ongoing): daily
`scripts/resolve_market_predictions.py`, weekly
`scripts/generate_weekly_regime_report.py` (human-triggered per its own
headline-sourcing caveat — see cadence section of checkpoint), monthly
`scripts/monthly_calibration_checkpoint.py` (new this session, read-only).

---

## job-application-agent (`~/job-application-agent`)

**Current phase**: standing collection + review pipeline armed (launchd
09:30/17:00), batch-materials-prep tooling built this session
(`scripts/batch_execute.py`), first tranche of the accumulated backlog
processed to packet-ready.

**Last commit**: `80dcf27` ("Initial commit: job application agent
pipeline") — this is the ONLY commit in this repo's git history. All work
described in `HANDOFF.md` and `COWORK-HANDOFF-2026-07-17.md` (submission
bridge, screening prefill, outreach templates, `batch_execute.py`, the
resume bullet fix) exists only in the uncommitted working tree
(`git status` confirmed: modified + untracked files matching that work).
**Not a lock/index issue here — genuinely uncommitted.** Flagged, not
fixed — committing this is a real decision (what to include, whether
`data/`/`docs/`/log files belong in git) that wasn't made this session.

**Open parks**:
- **Gmail OAuth token expired** (`invalid_grant`), found this session —
  blocks new outreach-draft creation. See `applications/APPLICATION_LEDGER.md`.
- **Lever adapter unverified on a real page** — only fixture-tested;
  `HANDOFF.md`'s own recommended next step (verify one real Lever
  screenshot before the 29-item adapter batch) not yet done.
- 361 of 390 remaining backlog items not yet packet-prepared (blocked
  behind the Gmail OAuth fix — packet prep without working outreach drafts
  would just accumulate more `gmail-draft-error` rows).
- `config/screening_qa_bank.yaml` non-work-auth entries still `REPLACE_ME`.
- No adapter-level "knockout" enforcement (sponsorship dropdown detection)
  — real form-option inspection needed at the adapter layer.
- `resume_base.json`'s bullet fix is done in the JSON; the source docx
  (wherever the user's master resume lives) still shows the placeholder.

**Next human gate**:
1. Re-auth Gmail (compose-scope) — unblocks outreach drafting.
2. Approve/reject the 20 `prepared-awaiting-approval` items in the review
   UI (`scripts/review.sh`) — see `applications/APPLICATION_LEDGER.md`.
3. Decide whether/when to run the Lever-verification step and then the
   29-item adapter batch (both require your per-item approval per standing
   protocol — never run with an unattended `--yes` on adapter/real paths).

**Next agent task**: once Gmail is re-authed, resume packet prep for the
remaining 361 manual-path items (`scripts/batch_execute.py`, prepare-only,
no `--yes` on adapter path) — parked pending that fix.

---

## Cross-project notes

- Both repos' `.env` files hold real API keys (Anthropic, FRED, Tiingo for
  intent-engine; Gmail OAuth + others for job-application-agent) — never
  printed, never logged, human-provisioned only, confirmed gitignored
  before any read this session.
- No file structures were reorganized or renamed in either repo this
  session — this document is the only new "organization" artifact.

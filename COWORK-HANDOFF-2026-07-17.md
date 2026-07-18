# COWORK HANDOFF — 2026-07-17
*Paste-or-mount this for any new Claude Cowork session. It covers BOTH repos
(`~/intent-engine`, `~/job-application-agent`) and the automation state as of
this session's end. If this doc conflicts with the repos, trust the repos.
Read `intent-engine-context-3.md` (project context) and each repo's
PROGRESS.md / HANDOFF.md for depth — this file is the operational delta.*

---

## 1. The two agents and who runs what

- **intent-engine** (`~/intent-engine`): the flagship project — Pre-Mortem
  simulator, Cognitive Delegate (family domains), scrap-metal arc, market
  engine, Part 5 iteration-loop layer. Autonomous work runs via
  `nightly_agent.sh` + launchd (`com.pratham.intentengine.nightlyagent`,
  1am, Claude Code `claude -p` under scoped permissions, budget-capped,
  branch `agent/<task-id>`, writes MORNING_REPORT.md). Rehearsed once for
  real (T001, $0.93). To enable:
  `cp ~/intent-engine/com.pratham.intentengine.nightlyagent.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.pratham.intentengine.nightlyagent.plist`
- **job-application-agent** (`~/job-application-agent`): collects jobs
  (launchd 09:30 + 17:00, armed), review UI (`scripts/review.sh`, Flask
  :5050), Playwright submission for Greenhouse/Lever only, Gmail
  compose-scope drafts (auto-send architecturally impossible). Read
  `HANDOFF.md` there — its outreach-template rules and trust-counter
  semantics must not be regressed.

## 2. What this Cowork session did — intent-engine (all committed to main)

| Commit | What |
|---|---|
| `25cb4b5` | T003: `anchors_on_offered_context` rationale widened to document BOTH mechanisms (classification bias, episode 3; generation-leak/imitation, episode 4) + test asserting both. |
| `5342fec` | T004: 7th diagnosis-registry signature `stable_but_non_discriminating` → `design_level_fix_required`, explicitly ENCODED-UNVALIDATED; deterministic `check_discrimination_bar()` with the REAL backtest-v1 fixture (66.7% vs 61.1%, 14.3% specificity reconstruction); replay episode 5 reclassified, deliberately NOT scored a match. |
| `fb8eb87` | ROADMAP.md: T003/T004 marked DONE with evidence. |
| `84639c2` | Picker test updated: queue drained → expects empty set / `pick_next_runnable() is None`. |

Suite after all of it: **557 passed offline, zero regressions** (live tests
excluded: `tests/*_live.py` + `test_simulator_e2e.py`).

**Roadmap queue is now EMPTY.** Everything left is NEEDS-SPEC (human design
decisions): absorption-capacity field, evaluation-stage validation path,
overnight plan's Task 3 park (mechanism-extraction ambiguous-case gate),
`prediction_ledger.entity_id` normalization question, 3 job-agent-sourced
candidate signatures. The nightly loop no-ops safely until new RUNNABLE
tasks are specced (that's by design — never auto-promote NEEDS-SPEC).

**MUST-DO on the Mac before any git work in intent-engine** (Cowork's
sandbox mount can't unlink files, so stale locks were left behind):

```
cd ~/intent-engine && rm -f .git/index.lock .git/HEAD.lock .git/refs/heads/main.lock .git/objects/maintenance.lock && git reset
```

(`git reset` rebuilds the stale index from HEAD — working tree already
matches HEAD, verified. `.git/objects/*/tmp_obj_*` junk files are harmless.)

## 3. What this Cowork session did — job-application-agent

- **`scripts/batch_execute.py` (new)**: batch executor over the ENTIRE
  accumulated backlog (all `runs/collect-*`, deduped, already-acted-on
  excluded). Current state: **410 unique pending — 29 adapter-submittable
  (Greenhouse/Lever), 381 manual-path** (packet + Gmail draft is the
  automation ceiling for those; nothing can auto-submit them). Replays the
  review UI's exact Approve path; screening gaps → NEEDS-HUMAN skip
  (override `--allow-gaps`); consolidated CSV to `reports/`. User decision
  on record: max automation across all 431 (now 410).
- **Tranche 1 ran (user's Mac, 20 jobs)**: all manual-path, packet-ready,
  but ALL outreach drafting failed — **Anthropic API key out of credits**
  (top up at console.anthropic.com/settings/billing — the human's job, the
  only current blocker). Failed drafts were cached as `email_draft: None`;
  batch_execute.py now auto-detects those poisoned cache entries and
  recomputes them live once (fix committed to the script, verified
  compiling + dry-run).
- **Resume placeholder fixed**: `resume_base.json`'s `intent-engine-3`
  bullet `[X]` filled with the REAL verified count: "ten classification
  tasks" (scrap ×4: category-proportions, sub-type, copper-richness,
  deviation; luck test; Scale/Leverage/Luck extraction; image
  verification; draft-reply classification; voice intent classification;
  trend extraction — each confirmed LLM + closed-taxonomy in src). The
  tailoring filter now re-includes the bullet. No source docx exists under
  `resume/` — the user's master resume doc (wherever it lives) still shows
  the placeholder.
- **Recommended next run order** (after billing top-up):
  1. `python scripts/batch_execute.py --only adapter --limit 10 --yes` —
     the Playwright path has had ZERO real runs (tranche 1 was all
     manual), and the Lever adapter has never touched a real page. Verify
     one Lever screenshot in `evidence/` before proceeding.
  2. `python scripts/batch_execute.py --yes` — full backlog (hours, real $).

## 4. Operating rules the next session must keep (hard-won, do not relearn)

- intent-engine house rules live in `intent-engine-context-3.md` §3/§7 and
  PROGRESS.md: fix library first, deterministic-over-model-asserted,
  information hiding, reliability gates, overfitting guard (never tune
  against the 18 backtest cases), one commit per task, suite green before
  every commit, PARK don't improvise.
- job-agent: outreach template rules in HANDOFF.md are human-approved and
  locked; auto-send must remain impossible (compose scope only); trust
  counters are never to be short-circuited in code — batch approvals were
  a direct user instruction, not a default.
- Cowork sandbox quirks: bash calls cap at 45s and background processes
  DIE between calls (chunk long work; the full offline suite runs in ~9s
  on Linux, so just run it directly); the mount cannot unlink files (git
  leaves stale locks — if blocked, use plumbing with
  `GIT_INDEX_FILE=/tmp/x` + `git commit-tree` + write the loose ref, or
  have the user rm locks on the Mac); macOS `.venv` binaries don't run in
  the sandbox (pip install deps fresh, `--break-system-packages`).
- Real submissions/Gmail/Playwright only run on the user's Mac, never from
  the sandbox.

## 5. Open items, in priority order

1. **Human: add Anthropic API credits** (blocks all outreach drafting).
2. Run the git-lock cleanup one-liner (§2) on the Mac.
3. Adapter tranche with Lever verification (§3), then full backlog.
4. Spec new RUNNABLE roadmap tasks for intent-engine's nightly loop (queue
   is drained) — candidates listed in ROADMAP.md's NEEDS-SPEC section and
   `reports/overnight_trace.md`'s "what a human needs to decide".
5. Decide the overnight plan's Task 3 park (ambiguous-case gate redesign
   vs insufficient-evidence escape hatch) — gates Task 4 (mechanism
   rendering in the premortem).
6. Update the user's master resume doc to match the fixed bullet.
7. Standing highest-value non-code action (unchanged): real usage — dad's
   Phase-0 relay / real weigh-ins.

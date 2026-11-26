# Handover manifest: integrated intelligence engine (2026-11-26)

**Read this first in any new session.** A copy lives at
`~/intent-engine-safety-backups/HANDOVER_MANIFEST_latest.md`.

## Exact state

| What | Value |
|---|---|
| Branch | `integration/unified-2026-11-25` on origin (github.com/ps2005-ops/intent-engine). Not merged to main; nothing deployed to Render |
| Final code commit | `f7690938` (later commits on the branch are docs only; see `git log`) |
| Market runtime (launchd market.day 06:30, night 20:30, health hourly) | `~/ie-market-runtime-v2`, detached at f7690938. Plists set only `PYTHONPATH` |
| Previous market runtime (rollback target) | `~/ie-market-runtime`, detached at 92ce0f39, untouched |
| Learning runtime (launchd learning.daily 19:15; daily, learn, register --if-due, econ resolver, FX4) | `~/ie-learning-runtime`, detached at f7690938 |
| Candidate scratch runtime | `~/ie-market-runtime-next` (f7690938; not scheduled) |
| Development worktree | `~/ie-integration` (never scheduled) |
| Monday 08:00 regime report (cron) | `~/ie-learning-runtime/scripts/weekly_regime_report_deterministic.py` (regime v2, no LLM) |

## Data ownership (single writer per file)

| Data | Path | Writer |
|---|---|---|
| Market data root | `~/intent-engine-market` (its own checkout, 195c6f4a, is NOT the running code) | market.day/night only |
| Paper forward ledger (977, resolvable 2026-12-11) | `~/ie-paper-validation/reports/paper_validation/forward_shadow_ledger.jsonl` | learning.daily |
| Econ forward ledger (13, first due 2026-12-25) | `~/intent-engine-econ/reports/real_forward_expectations.jsonl` | learning.daily |
| FX4 ledger | `~/ie-paper-validation/reports/experiments/fx4_intent_behaviour.jsonl` (created on first registration) | learning.daily |
| Dossier corrections sidecar | `~/intent-engine-market/reports/market/strategic/belief_corrections.jsonl` | audits only (append) |
| July ledger | `~/intent-engine/data/prediction_ledger.db` | frozen; generator and 06:00 resolver retired |

**Secrets.** The `.env` files in runtime worktrees are SYMLINKS to
`~/intent-engine-market/.env` (market) and `~/intent-engine/.env`; they are
never copied. To verify key loading, use a script FILE or `-m`, never
`python -c` (python-dotenv then searches the cwd).

## Backups and rollback

* **Canonical ledgers:** `~/intent-engine-safety-backups/canonical-ledgers-20261126-004830`
  (taken right before the switch; earlier ones from the 25th are kept).
* **Scheduler state:** `plists-20261126-004830/` (plists and crontab).
* **Rollback:** `ROLLBACK_market_runtime_20261126-004830.sh` restores market
  jobs to 92ce0f39. For the learning runtime:
  `git -C ~/ie-learning-runtime checkout --detach 3536cf41`.
* **100-company research cache:** `prospect100-research-cache-20261125-231939`
  (8,481 files, checksummed). Originals are untracked in
  `~/ie-prospect100/reports/prospect100_*`.

## Completed (see docs/engineering/learning_loop/FINAL_COMPLETION_2026-11-26.md)

* **Runtime:** upgraded and qualified (isolated cycles on 9b4910a8 and
  f7690938). Switched with controlled verification.
* **Corrections:** 30 grade invalidations and 104 OLO corrections applied,
  append-only and idempotent.
* **Grading:** admissibility rules (previews, case studies, other companies,
  same quarter, cadence; v2.1 direction).
* **Bayes:** dependence-aware (local level plus shared construct error).
* **Exposure:** the capital-intensity pattern requires ownership (the
  JPMorgan movements).
* **Regime:** protocol amendment A1 (v2), prospective from 2026-11-26.
* **Eligibility:** point-in-time instrument eligibility.
* **FX4:** actor mapping, plus an end-to-end historical fixture.
* **Review packages:** human annotation (19) and blind enterprise review (5).
* **Health:** the false DEGRADED status (lock) and the wrong runtime sha in
  learning health are both fixed.

## Pending: needs a human or the future

1. **Human labels** for `reports/learning_loop/human_annotation/` (19
   items). Then run `score_annotations.py`.
2. **Domain reviewers** for `reports/learning_loop/enterprise_review/`
   (5 pairs).
3. **2026-12-11:** first resolution of the 977 forward forecasts (automatic).
   **2026-12-25:** econ PERMIT expectation (automatic).
4. **About 2026-12-09:** the next paper cohort registers under amendment A1
   (protocol hash 354e1bf9).

## Pending: engineering, recommended order

1. **Observation channels.** 12 of 16 belief families are
   UNFALSIFIABLE_BY_OBSERVATION, so 189 of 206 beliefs can never be tested.
   Give each family an observation rule.
2. **Attribution at ingestion.** 25 analyst actions on other companies are
   filed under JPMorgan, plus case studies and stale tables. They are now
   refused at grading but still enter belief FORMATION.
3. **Promote demand_reading v2.1 into belief formation**, but only after the
   human labels confirm it.
4. **Strategic-interaction detector** (constructs and rejects every pattern;
   FX6 blocked).
5. **Company exposure map** (FX3 transmission blocked).
6. **Browser sweep** of the corrected dossiers across every founder surface,
   with screenshots (part of the qualification program below).

## 100-company qualification: resume point

* **Not found anywhere on this Mac or on origin** (searched every git repo
  under `~` and `git ls-remote`): the qualification branch
  `qual/prospect100-resume`, commit `0a675240`, and
  `docs/engineering/prospect100/resume/PROGRESS_MANIFEST.json`. The same
  applies to the 75-company regression coverage, the mobile-navigation fixes,
  the light-mode link corrections and the cross-device checks you described.
  They must live in another environment (for example a cloud session) and
  need to be pushed to origin before they can be reconciled.
* **What exists and is integrated:** branch `prospect100/identity` (worktree
  `~/ie-prospect100`, head cc04b23a, passes 1–4). `cc04b23a` is an ancestor
  of this branch, so all of it is here. That covers the news channel
  (49edf9d3), the presentation-crash fixes (7729503d) and the
  `docs/engineering/prospect100/` scorecards (`pass2/3/4_scorecard.json`,
  `QUALIFICATION_100.md`, `qualification_100_pass4.json`).
* **Last measured state (pass 4):** decision-grade 49 of 95; companies with
  no independent evidence 85 → 45; 0 of 100 at 10/10. The binding gap is
  independent evidence.
* **Resume:**
  1. Push `qual/prospect100-resume` from wherever it lives.
  2. `git fetch`, then merge it into a new branch cut from this one, in a
     fresh worktree. Never in the runtime worktrees.
  3. Rerun the qualification harness (`scripts/prospect100/`,
     `live_pass.py`, `rerender_pass.py`) against a local server on the new
     code.
  4. Hold the full bar: 10/10 on every metric, with real browser checks on
     laptop and phone, light and dark mode.

## Guard and conventions

* **Commits:** `GUARD_PYTHON=/Users/prathamsharma/intent-engine/.venv/bin/python git commit ...`.
  The full suite takes 15–35 minutes; never use `--no-verify`.
* **Probes:** `PYTHONPATH=src`. After a same-length mutation, delete the pyc
  under `~/Library/Caches/com.apple.python/<abs path>`.
* **Approvals:** never push or deploy without one. Production ledger writes go
  under `JobLock(market-cycle)`, append-only.

## Progress log

* 2026-11-25 22:45: corrections applied (30 invalidations, 104 OLO).
* 2026-11-26 00:48: backup, then switch to f7690938 (market and learning).
  Health: `f7690938671a on HEAD clean`. Controlled dry-run night on production
  root: 17/17 ok, ledgers unchanged. First scheduled day cycle: 06:30 2026-11-26.

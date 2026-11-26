# Handover manifest (living checkpoint, updated through 2026-11-25/26)

## Where things are
| What | Location | State |
|---|---|---|
| Integration branch | `integration/unified-2026-11-25` on origin (github.com/ps2005-ops/intent-engine) | pushed at e7528e80 (2026-11-25 22:22) |
| Integration worktree | `~/ie-integration` | development; never run by a scheduler |
| Market runtime code | `~/ie-market-runtime` (detached, pinned) | 92ce0f39, launchd market.{day,night,health} |
| Market upgrade candidate | `~/ie-market-runtime-next` (detached) | 930e4aed, qualified in isolation 2026-11-25 |
| Market DATA (single writer: the three market jobs) | `~/intent-engine-market` | data root; its own checkout (195c6f4a) is NOT the code |
| Learning runtime code | `~/ie-learning-runtime` (detached) | 3536cf41, launchd learning.daily 19:15 |
| Paper forward ledger (977, Dec 11) | `~/ie-paper-validation/reports/paper_validation/forward_shadow_ledger.jsonl` | owner: learning.daily |
| Econ forward ledger (13, Dec 25) | `~/intent-engine-econ/reports/real_forward_expectations.jsonl` | owner: learning.daily |
| July ledger | `~/intent-engine/data/prediction_ledger.db` | frozen; generator + 06:00 resolver retired |
| Backups | `~/intent-engine-safety-backups/` | canonical-ledgers-*, plists-*, crontab-*, ROLLBACK_market_runtime_20261125.sh |
| Reports and evidence | `~/ie-integration/reports/learning_loop/`, `docs/engineering/learning_loop/` | see INTELLIGENCE_INTEGRITY_2026-11-25.md |
| Human-review packages | `reports/learning_loop/reader_eval/`, `reports/learning_loop/enterprise_review/` | awaiting humans |
| Secrets | `.env` files are SYMLINKS to `~/intent-engine-market/.env` and `~/intent-engine/.env`; never copied | |

## Resume instructions
1. `cd ~/ie-integration && git fetch && git status` (branch above).
2. Read `docs/engineering/learning_loop/INTELLIGENCE_INTEGRITY_2026-11-25.md` and this file.
3. Guarded commits: `GUARD_PYTHON=/Users/prathamsharma/intent-engine/.venv/bin/python git commit ...` (never --no-verify).
4. Ad-hoc probes: `PYTHONPATH=src ~/intent-engine/.venv/bin/python ...`.

## Progress log (appended as work completes)
- 2026-11-25 22:30 checkpoint written; approvals 1-4 received (runtime upgrade, 33 invalidations, 104 OLO corrections, regime protocol amendment).
- 2026-11-25 22:45 APPLIED to production (under the market cycle lock, idempotent, rerun appended 0):
  30 grade invalidations (of 33 proposed; Etsy, P&G and Canadian National were graded by a
  genuinely later, different figure and were withdrawn) -> learning_ledger.jsonl;
  104 OLO INELIGIBLE corrections -> signal_outcomes.jsonl. Files:
  reports/learning_loop/APPLIED_grade_invalidations_2026-11-25.jsonl, scripts/learning_loop/apply_corrections.py.
  Backup before: ~/intent-engine-safety-backups/canonical-ledgers-20261125-222913.

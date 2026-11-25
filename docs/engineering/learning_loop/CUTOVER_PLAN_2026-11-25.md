# Production cutover plan — awaiting one consolidated approval

Prepared 2026-11-25. **Nothing below has been executed.** Every step is
local to this Mac. Nothing is pushed, so the public preview is unaffected.

## What changes

| # | Change | Writes to | Reversible by |
|---|---|---|---|
| A | Point the three market launchd jobs at a new runtime worktree on `integration/unified-2026-11-25` (resolver included) | plists in `~/Library/LaunchAgents` | restoring the saved plists |
| B | Move the runtime's **data** to that worktree, or keep `--root ~/intent-engine-market` and change only `PYTHONPATH` and the python path | depends on option (below) | step A rollback |
| C | First real `resolve_outcomes` run: appends ~485 events to `reports/market/signal_outcomes.jsonl` (new file; `signal_audit.jsonl` untouched) | runtime `reports/market/` | delete the new file (nothing else reads it yet) |
| D | Append 6 superseding rows to the July ledger (`propose_july_supersessions.py --in-place`) | `~/intent-engine/data/prediction_ledger.db` | restore the db from backup |
| E | Install `com.intentengine.paper.daily` (19:15 ET), `WorkingDirectory` = the one owner of `forward_shadow_ledger.jsonl` | new plist; `reports/paper_validation/daily_runs.jsonl` | `launchctl bootout` + remove the plist |
| F | Disable the July generator cron line (18:30, fails every weekday on credit) | crontab | re-add the line |

**Recommended option for B: code and data stay apart.** Keep
`--root /Users/prathamsharma/intent-engine-market` (the data never moves, and
the single writer stays the same path). Change only `PYTHONPATH` and the
interpreter to a new, clean runtime worktree pinned by SHA. This follows
the existing launchd "pinned by SHA" practice and avoids the shared-venv
import trap ([[market-runtime-deployment]]).

## Preconditions (all checked before step A)

1. A fresh backup taken at cutover time. Rehearsed today:
   `~/intent-engine-safety-backups/canonical-ledgers-20261125-044724`
   holds 636 files, every hash verified on restore, July db `integrity_check=ok`.
2. No cycle running: no process, and no holder on `locks/market-cycle.lock`.
   Cut over between 07:30 and 20:00 ET.
3. Full guarded suite green on the integration HEAD that gets pinned.
4. An isolated cycle (`--root` = a copy of the runtime data, `--dry-run` then
   real) on the integration code: before/after ledger diff, idempotent rerun.
5. Single writer: only one plist points at each ledger; the 3 stray roots
   (`data/`, `dryrun/`, `~/ie-econ-runtime`) have no scheduler.

## Rollback

```
launchctl bootout gui/$(id -u)/com.intentengine.market.{day,night,health}
cp <saved plists> ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.intentengine.market.{day,night,health}.plist
# data: shasum -a 256 -c SHA256SUMS in the backup, copy back the subtree
```

## Decisions that are yours alone

* The premortem `32bbf0c5` ("sales pipeline remains below 5 opportunities by
  2026-11-20", p=0.72) has no machine rule. Did it happen?
* Anthropic credits: the market runtime and the paper ledger need none. Only
  the retired July generator and Founder narrative generation do.

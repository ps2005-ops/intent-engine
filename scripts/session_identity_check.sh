#!/bin/zsh
# Run FIRST in every session. Prints where the work actually is, so nothing
# is declared "missing" because a session looked in the wrong worktree.
# (2026-11-26: a session reported qual/prospect100-resume lost; it was at R12.)
echo "host=$(hostname) user=$(whoami) date=$(date -u +%FT%TZ)"
cd ~/intent-engine 2>/dev/null && git worktree list
for w in ~/ie-integration ~/ie-prospect100-resume ~/ie-market-runtime-v2 ~/ie-learning-runtime; do
  [ -d $w ] && printf "%-34s %s %s\n" "$w" "$(git -C $w rev-parse --short HEAD)" "$(git -C $w rev-parse --abbrev-ref HEAD)"
done
echo "--- scheduler"; launchctl list | grep intentengine
echo "--- last cycles"; python3 -c "
import json
rows=[json.loads(l) for l in open('$HOME/intent-engine-market/status/market_cycles.jsonl')]
for r in rows[-4:]: print(r['run_id'][:20], r['status'], r['started_at'][:16], '->', r['finished_at'][:16])"
echo "--- qualification artifacts"; ls ~/ie-prospect100-resume/reports/prospect100_resume | tr '\n' ' '; echo
echo "--- backups"; ls -la ~/ie-backups/*.tar* 2>/dev/null
echo "--- tracker: docs/engineering/equilibrium/PHASE_TRACKER.json"
